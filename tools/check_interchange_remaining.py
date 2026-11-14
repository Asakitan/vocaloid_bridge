"""Focused real-MCP interchange checks; the runner never builds the host.

Examples:
  .venv/Scripts/python.exe tools/check_interchange_remaining.py --case remaining.clone_audio
  .venv/Scripts/python.exe tools/check_interchange_remaining.py --case remaining.vsqx3 --vsqx3-fixture .runtime/vsqx3-reference.vsqx
  .venv/Scripts/python.exe tools/check_interchange_remaining.py --case remaining.ppsf3 --ppsf3-fixture PATH
"""
from pathlib import Path
import json
import shutil
import struct
import subprocess
import sys
import uuid
import zipfile

import numpy as np
import verify_features as v


def inspect_long_render(path):
    """Decode a bounded long WAV in blocks without triggering another render."""
    import soundfile as sf
    with sf.SoundFile(path) as audio:
        v.require(audio.format in ("WAV", "WAVEX") and audio.channels in (1, 2)
                  and 0 < audio.frames <= audio.samplerate * 600, "Unexpected rendered audio bounds")
        frames, rate, channels, subtype = audio.frames, audio.samplerate, audio.channels, audio.subtype
        peak, power, count = 0.0, 0.0, 0
        for samples in audio.blocks(blocksize=65536, dtype="float64", always_2d=True):
            v.require(np.isfinite(samples).all(), "Rendered audio contains nonfinite samples")
            peak = max(peak, float(np.max(np.abs(samples))))
            power += float(np.sum(samples * samples))
            count += samples.size
    metadata = {"frames": frames, "sample_rate": rate, "channels": channels, "subtype": subtype,
                "duration_seconds": frames / rate, "peak": peak, "rms": (power / count) ** 0.5}
    v.require(peak > 0 and metadata["rms"] > 0, "Selected Dnn render is silent")
    return metadata


def static_classic_audit():
    """Emit bounded, version-specific disassembly and prior runtime evidence."""
    sys.path.insert(0, str(v.ROOT / ".tools" / "analysis"))
    import capstone
    import pefile

    install = Path(r"C:\Program Files\VOCALOID6\Editor")
    vsm = pefile.PE(str(install / "VSM.dll"))
    vdm = pefile.PE(str(install / "VDM.dll"))
    disassembler = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    def instructions(pe, rva, length):
        return [{"rva": hex(item.address - pe.OPTIONAL_HEADER.ImageBase),
                 "mnemonic": item.mnemonic, "operands": item.op_str, "bytes": item.bytes.hex()}
                for item in disassembler.disasm(pe.get_data(rva, length), pe.OPTIONAL_HEADER.ImageBase + rva)]

    def string_at_rva(pe, rva):
        return pe.get_data(rva, 80).decode("utf-16le", errors="ignore").split("\x00")[0]

    enum = subprocess.run([str(v.ROOT / ".tools" / "ilspycmd.cmd"), "-t",
                           "Yamaha.VOCALOID.VDM.VDMVoiceBankType", str(install / "VOCALOID6.dll")],
                          capture_output=True, text=True, check=True).stdout
    version = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "[Reflection.AssemblyName]::GetAssemblyName('C:\\Program Files\\VOCALOID6\\Editor\\VOCALOID6.dll').Version.ToString()"],
                             capture_output=True, text=True, check=True).stdout.strip()
    v.require(version == "6.13.3.1", "Static audit offsets are only checked for editor 6.13.3.1", version)
    v.require(string_at_rva(vsm, 0x2f7d00) == "voice" and string_at_rva(vsm, 0x2f79a0) == "aiVoice",
              "Installed VSM does not match the audited offsets")
    receipt_path = v.ROOT / "artifacts/feature-acceptance-012574702338/synthesis.blank_authoring.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    voices = next(call["result"]["voices"] for call in receipt["calls"] if call["tool"] == "voicebanks")
    counts = {kind: sum(voice["kind"] == kind for voice in voices) for kind in ("Dse", "Dnn")}
    report = {
        "kind": "static-native-interchange-audit", "binary_specific": True,
        "assembly_version": version, "enum_source": enum,
        "vtable_entries": {hex(rva): hex(struct.unpack("<Q", vsm.get_data(rva, 8))[0] - vsm.OPTIONAL_HEADER.ImageBase)
                           for rva in (0x301500, 0x301510)},
        "prior_runtime_receipt": str(receipt_path), "prior_runtime_voice_counts": counts,
        "disassembly": {
            "vdm_count_export": instructions(vdm, 0x5560, 0x1d),
            "vdm_compid_export": instructions(vdm, 0x55e0, 0x18),
            "helper_count_checks": instructions(vsm, 0xadb36, 0x2c),
            "helper_result_checks": instructions(vsm, 0xadf44, 0x47),
            "classic_type_dispatch": instructions(vsm, 0xae359, 0x2e),
            "classic_creation_selection": instructions(vsm, 0xae5d1, 0x8b),
            "voice_field_lookup": instructions(vsm, 0xaddd9, 0x13),
            "ai_voice_field_lookup": instructions(vsm, 0xadbfd, 0x14),
        },
        "string_literals": {"voice": string_at_rva(vsm, 0x2f7d00),
                            "aiVoice": string_at_rva(vsm, 0x2f79a0),
                            "compID": string_at_rva(vsm, 0x2f7960)},
        "limits": "Static slot matching and historic runtime counts; no classic bank or authorization changed. "
                  "Object provenance and all per-voice cases remain unverified.",
    }
    destination = v.ROOT / "artifacts" / ("classic-native-audit-" + uuid.uuid4().hex[:12] + ".json")
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(destination)


@v.feature("remaining.clone_audio", "interchange", "project_clone", "project_audio", "project_close")
async def clone_audio(check):
    source = await check.audio_input()
    _, expected = v.read_audio(source)
    identifier = (await check.call("project_create", title="Audio clone", bpm=120))["session_id"]
    imported = await check.audio(identifier, "import_audio", path=str(source), position_tick=0)
    selected = {"track_index": imported["track_index"], "part_index": imported["part_index"]}
    clone = (await check.call("project_clone", session_id=identifier))["session_id"]
    end = imported["begin_tick"] + (imported["end_tick"] - imported["begin_tick"]) // 2
    await check.audio(clone, "edit_audio", **selected, end_tick=end, name="Clone only")
    source_part = await check.audio(identifier, "edit_audio", **selected, position_tick=imported["position_tick"])
    v.require(source_part["name"] == imported["name"] and source_part["end_tick"] == imported["end_tick"],
              "Clone edit affected source", source_part)
    await check.close(identifier)
    for original in (False, True):
        exported = await check.audio(clone, "export_audio", **selected, original=original,
                                     output_name=check.output("clone-audio", ".wav"))
        _, actual = v.read_audio(exported["path"])
        v.require(actual.shape == expected.shape and np.allclose(actual, expected, atol=2 / 32768, rtol=0),
                  "Clone audio differs after source close")
    await check.save(clone, "clone-audio")
    await check.close(clone)


@v.feature("remaining.vprx", "interchange", "project_save", "project_open", "project_import", "project_revert", "score_patch")
async def vprx_roundtrip(check):
    product = (await check.call("vocaloid_features"))["product"]
    async with check.project(score=True) as identifier:
        output_name = check.output("native-format", ".VPRX")
        if product != "VOCALOID7":
            await check.rejected("project_save", "VOCALOID7", session_id=identifier,
                                 output_name=output_name)
            _, baseline = await check.save(identifier, "v6-source")
            rejected_source = baseline.with_suffix(".VPRX")
            shutil.copyfile(baseline, rejected_source)
            for operation in ("project_open", "project_import"):
                await check.rejected(operation, "VOCALOID7", path=str(rejected_source))
            return
        saved = await check.call("project_save", session_id=identifier, output_name=output_name)
        v.require(saved.get("native") is True and saved.get("saved") is True,
                  "VPRX was not saved by the native project path", saved)
        patched = await check.call("score_patch", path=saved["path"],
                                   output_name=check.output("vprx-extension", ".vprx"),
                                   operations=[{"op": "add", "path": "/bridgeVprx51", "value": {"kept": True}}])
        source = Path(patched["path"])
        with zipfile.ZipFile(source, "a") as archive:
            archive.writestr("bridge-vprx51/resource.bin", b"\x00VPRX-resource\xff")
        original, resources = v.read_vpr(source)
        resources.pop("Project/sequence.json")
        source_bytes = source.read_bytes()
        for operation in ("project_open", "project_import"):
            opened = await check.call(operation, path=str(source))
            await check.rejected("project_save", "original", session_id=opened["session_id"],
                                 output_name=source.name, overwrite=True)
            restored = await check.call("project_revert", session_id=opened["session_id"],
                                        discard_changes=True)
            identifier_copy = restored["session_id"]
            exported = await check.call("project_save", session_id=identifier_copy,
                                        output_name=check.output("vprx-roundtrip", ".vprx"))
            actual, actual_resources = v.read_vpr(Path(exported["path"]))
            actual_resources.pop("Project/sequence.json")
            v.require(actual["tracks"] == original["tracks"] and actual_resources == resources
                      and actual.get("bridgeVprx51") == original["bridgeVprx51"],
                      "VPRX roundtrip changed tracks or resources")
            await check.close(identifier_copy)
        v.require(source.read_bytes() == source_bytes, "VPRX source was modified")


@v.feature("remaining.vprx_compose", "interchange", "score_compose", "project_save", "score_replace_notes")
async def vprx_compose(check):
    product = (await check.call("vocaloid_features"))["product"]
    for automatic in (False, True):
        note = {"start": 0, "duration": 1, "pitch": 60, "lyric": "\u3042", "lang_id": 0}
        if not automatic:
            note["phoneme"] = "a"
        output_name = check.output("vprx-compose", ".vprx")
        if product != "VOCALOID7":
            await check.rejected("score_compose", "VOCALOID7", output_name=output_name,
                                 title="VPRX compose", bpm=120, notes=[note])
            v.require(not (v.ROOT / "output" / output_name).exists(), "Rejected V6 compose published a VPRX")
            continue
        composed = await check.call("score_compose", output_name=output_name,
                        title="VPRX compose", bpm=120, notes=[note])
        identifier = composed["native_session"]["session_id"]
        saved = await check.call("project_save", session_id=identifier,
                                output_name=check.output("vprx-composed-native", ".vprx"))
        await check.close(identifier)
        replaced = await check.call("score_replace_notes", path=saved["path"],
                                    output_name=check.output("vprx-replaced", ".vprx"), notes=[note])
        data, _ = v.read_vpr(Path(replaced["path"]))
        authored = data["tracks"][0]["parts"][0]["notes"]
        v.require(len(authored) == 1 and authored[0]["number"] == 60 and authored[0]["phoneme"],
                  "VPRX note replacement lost the note or phoneme")


async def voice_scope(check):
    product = (await check.call("vocaloid_features"))["product"]
    return {"scope": "track" if product == "VOCALOID7" else "part"}


async def require_classic_banks(check, tracks, identities):
    if not any(track["type"] == "Midi" for track in tracks):
        return
    installed = (await check.call("voicebanks"))["voices"]
    available = [voice for voice in installed if voice["kind"] == "Dse" and voice["available_in_sequence"]]
    check.evidence("classic_requirements", {"tracks": tracks, "identities": identities,
                                            "available_dse": available})
    if not available:
        raise v.Blocked("missing_classic_bank: native import preserved classic identity, but save/reopen requires an installed available Dse voicebank; no replacement was selected")


async def identity_roundtrip(check, path: Path | None, label: str, signature: bytes | None = None):
    if path is None or not path.is_file():
        raise v.Blocked("A real native fixture is required for " + label)
    path = path.resolve()
    original = path.read_bytes()
    if signature is not None:
        v.require(original.startswith(signature), "Fixture has the wrong format signature")
    try:
        identifier = (await check.call("project_import", path=str(path), prefer_ai=False))["session_id"]
    except v.ToolFailure as error:
        if "missing_classic_bank:" not in str(error):
            raise
        v.require(path.read_bytes() == original, "Rejected native import changed its source fixture")
        installed = (await check.call("voicebanks"))["voices"]
        check.evidence("rejected_classic_import", {"fixture": str(path), "source_unchanged": True,
                                                  "voices": installed, "error": str(error)})
        raise v.Blocked(str(error)) from error
    tracks, notes = await v.vsqx_native_notes(check, identifier)
    scope = await voice_scope(check)
    async def voices(session, items):
        return [await check.edit(session, "voice.get", **scope, track_index=t["track_index"], part_index=i)
                for t in items if t["type"] in ("Midi", "MidiAi") for i in range(t["part_count"])]
    before = await voices(identifier, tracks)
    v.require(notes and before, "Fixture has no vocal notes or parts")
    v.require(path.read_bytes() == original, "Source fixture changed during import")
    await require_classic_banks(check, tracks, before)
    _, destination = await check.save(identifier, label)
    reopened = (await check.call("project_open", path=str(destination)))["session_id"]
    after_tracks, after_notes = await v.vsqx_native_notes(check, reopened)
    after = await voices(reopened, after_tracks)
    v.require((tracks, notes, before) == (after_tracks, after_notes, after),
              "Native format identity/notes changed after VPR reopen",
              {"before_tracks": tracks, "after_tracks": after_tracks,
               "before_voices": before, "after_voices": after})
    v.require(path.read_bytes() == original, "Source fixture changed")
    check.evidence("identity_roundtrip", {"fixture": str(path), "vpr": str(destination), "notes": len(notes)})
    await check.close(reopened)
    await check.close(identifier)


@v.feature("remaining.vsqx3", "interchange", "project_import", "project_save", "project_open")
async def vsqx3(check):
    await identity_roundtrip(check, check.arguments.vsqx3_fixture, "vsqx3-identity")


@v.feature("remaining.vsqx4", "interchange", "project_import", "project_save", "project_open")
async def vsqx4(check):
    await identity_roundtrip(check, check.arguments.vsqx_fixture, "vsqx4-identity")


@v.feature("remaining.ppsf3", "interchange", "project_import", "project_save", "project_open")
async def ppsf3(check):
    await identity_roundtrip(check, check.arguments.ppsf3_fixture, "ppsf3-identity", b"PK\x03\x04")


@v.feature("remaining.classic_candidate", "interchange", "project_import", "project_save", "project_open")
async def classic_candidate(check):
    scope = await voice_scope(check)
    path = check.arguments.ppsf_fixture
    if path is None or not path.is_file():
        raise v.Blocked("A real classic PPSF V2 fixture is required")
    identifier = (await check.call("project_import", path=str(path.resolve()), prefer_ai=False))["session_id"]
    tracks, _ = await v.vsqx_native_notes(check, identifier)
    identities = []
    for track in tracks:
        parts = []
        for part in range(track["part_count"]):
            parts.append(await check.edit(identifier, "voice.get", **scope, track_index=track["track_index"], part_index=part))
        identities.append(parts)
    v.require(all(t["type"] == "Midi" for t in tracks), "Candidate requires classic MIDI tracks")
    await require_classic_banks(check, tracks, identities)
    _, native_path = await check.save(identifier, "classic-native")
    _, members = v.read_vpr(native_path)
    sequence = json.loads(members["Project/sequence.json"])
    voices = {}
    for track, parts in zip(sequence["tracks"], identities, strict=True):
        for part, identity in zip(track["parts"], parts, strict=True):
            voice = identity["voice_bank_id"]
            v.require(bool(voice), "Candidate requires a source voice ID")
            part["voice"] = {"compID": voice, "langID": identity["lang_id"]}
            voices[voice] = identity["voice_name"]
    sequence["voices"] = [{"compID": key, "name": value} for key, value in voices.items()]
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    candidate = v.ROOT / "output" / check.output("classic-candidate")
    with zipfile.ZipFile(candidate, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    reopened = (await check.call("project_open", path=str(candidate)))['session_id']
    after_tracks, _ = await v.vsqx_native_notes(check, reopened)
    after = [[await check.edit(reopened, "voice.get", **scope, track_index=t["track_index"], part_index=i)
              for i in range(t["part_count"])] for t in after_tracks]
    check.evidence("classic_candidate", {"path": str(candidate), "source_tracks": tracks,
                                          "opened_tracks": after_tracks, "source_voices": identities,
                                          "opened_voices": after})
    v.require(after_tracks == tracks and after == identities,
              "Native loader did not preserve standard candidate voice identity",
              {"tracks": after_tracks, "voices": after})
    await check.close(reopened)
    await check.close(identifier)


@v.feature("remaining.classic_duplicate", "interchange", "project_import", "project_merge", "project_save", "project_open")
async def classic_duplicate(check):
    scope = await voice_scope(check)
    path = check.arguments.ppsf_fixture
    if path is None or not path.is_file():
        raise v.Blocked("A real classic PPSF V2 fixture is required")
    source = (await check.call("project_import", path=str(path.resolve()), prefer_ai=False))["session_id"]
    source_tracks, _ = await v.vsqx_native_notes(check, source)
    source_voices = [await check.edit(source, "voice.get", **scope, track_index=t["track_index"], part_index=0)
                     for t in source_tracks]
    await require_classic_banks(check, source_tracks, source_voices)
    target = (await check.call("project_create", title="Duplicate candidate", bpm=120))["session_id"]
    await check.call("project_merge", session_id=target, path=str(path.resolve()), include_tracks=True)
    tracks, _ = await v.vsqx_native_notes(check, target)
    voices = [await check.edit(target, "voice.get", **scope, track_index=t["track_index"], part_index=0) for t in tracks]
    check.evidence("after_duplicate", {"tracks": tracks, "voices": voices})
    v.require(tracks == source_tracks and [x["voice_bank_id"] for x in voices] ==
              [x["voice_bank_id"] for x in source_voices], "Native duplicate changed track type or voice ID")
    _, destination = await check.save(target, "classic-duplicate")
    reopened = (await check.call("project_open", path=str(destination)))["session_id"]
    saved_tracks, _ = await v.vsqx_native_notes(check, reopened)
    saved_voices = [await check.edit(reopened, "voice.get", **scope, track_index=t["track_index"], part_index=0)
                    for t in saved_tracks]
    check.evidence("after_reopen", {"tracks": saved_tracks, "voices": saved_voices})
    v.require(saved_tracks == source_tracks and saved_voices == source_voices,
              "Duplicate plus native save/reopen changed classic identity")
    await check.close(reopened)
    await check.close(target)
    await check.close(source)


@v.feature("remaining.classic_created", "interchange", "project_create", "project_edit", "project_save", "project_open")
async def classic_created(check):
    scope = await voice_scope(check)
    await check.call("voicebanks")
    target = (await check.call("project_create", title="Classic created", bpm=120))["session_id"]
    track = (await check.edit(target, "track.create", type="Midi", name="Classic"))["track_index"]
    part = (await check.edit(target, "part.create", track_index=track, start_tick=0, duration_tick=1920))["part_index"]
    before_track = (await check.edit(target, "track.list"))["tracks"]
    before = await check.edit(target, "voice.get", **scope, track_index=track, part_index=part)
    await require_classic_banks(check, before_track, [before])
    sequence, destination = await check.save(target, "classic-created")
    reopened = (await check.call("project_open", path=str(destination)))["session_id"]
    after_track = (await check.edit(reopened, "track.list"))["tracks"]
    after = await check.edit(reopened, "voice.get", **scope, track_index=track, part_index=part)
    check.evidence("classic_created", {"before_track": before_track, "before_voice": before,
                                       "serialized_type": sequence["tracks"][0]["type"],
                                       "after_track": after_track, "after_voice": after})
    v.require(before_track == after_track and before == after, "Fresh classic track changed on reopen")
    await check.close(reopened)
    await check.close(target)


@v.feature("remaining.classic_separate", "interchange", "project_open", "project_edit")
async def classic_separate(check):
    path = check.arguments.ppsf_fixture
    if path is None or not path.is_file() or path.suffix.lower() != ".vpr":
        raise v.Blocked("Pass an existing saved VPR via --ppsf-fixture")
    sequence, _ = v.read_vpr(path)
    expected = [track["type"] for track in sequence["tracks"]]
    v.require(expected and all(track_type == 0 for track_type in expected),
              "Expected a saved classic-only VPR")
    opened = (await check.call("project_open", path=str(path.resolve())))["session_id"]
    tracks = (await check.edit(opened, "track.list"))["tracks"]
    check.evidence("independent_host_open", {"path": str(path.resolve()), "serialized_types": expected,
                                               "native_tracks": tracks})
    v.require(all(track["type"] == "Midi" for track in tracks),
              "Fresh host reopened serialized type 0 tracks as non-classic", tracks)
    await check.close(opened)


@v.feature("remaining.integrity_guard", "interchange", "project_import", "project_save", "project_open", "project_edit")
async def integrity_guard(check):
    scope = await voice_scope(check)
    fixture = check.arguments.ppsf_fixture
    if fixture is None or not fixture.is_file():
        raise v.Blocked("A genuine PPSF V2 fixture is required")
    counts = (await check.call("voicebanks"))["voices"]
    if any(item["kind"] == "Dse" for item in counts) or not any(item["kind"] == "Dnn" for item in counts):
        raise v.Blocked("This regression requires Dse=0 and Dnn>0")
    async with check.project() as empty_classic:
        await check.edit(empty_classic, "track.create", type="Midi", name="Classic guard fixture")
        _, raw_vpr = await check.save(empty_classic, "integrity-classic")
    fixture = fixture.resolve()
    raw_before = raw_vpr.read_bytes()
    source_before = fixture.read_bytes()
    await check.rejected("project_open", "missing_classic_bank", path=str(raw_vpr))
    v.require(raw_vpr.read_bytes() == raw_before, "Rejected open changed the VPR source")
    async with check.project() as blank:
        _, destination = await check.save(blank, "integrity-existing")
    existing = destination.read_bytes()
    source = (await check.call("project_import", path=str(fixture), prefer_ai=False))["session_id"]
    before_tracks, before_notes = await v.vsqx_native_notes(check, source)
    v.require(before_tracks and before_notes, "Classic source is empty")
    before_voice = await check.edit(source, "voice.get", **scope, track_index=0, part_index=0)
    v.require(before_voice["voice_bank_id"], "Fixture has no classic voice ID")
    await check.rejected("project_clone", "project_integrity|missing_classic_bank", session_id=source)
    cloned_tracks, cloned_notes = await v.vsqx_native_notes(check, source)
    cloned_voice = await check.edit(source, "voice.get", **scope, track_index=0, part_index=0)
    v.require((cloned_tracks, cloned_notes, cloned_voice) == (before_tracks, before_notes, before_voice),
              "Rejected clone changed the source session")
    await check.rejected("project_save", "project_integrity", session_id=source,
                         output_name=destination.name, overwrite=True)
    v.require(destination.read_bytes() == existing, "Rejected save overwrote an existing destination")
    after_tracks, after_notes = await v.vsqx_native_notes(check, source)
    after_voice = await check.edit(source, "voice.get", **scope, track_index=0, part_index=0)
    v.require((after_tracks, after_notes, after_voice) == (before_tracks, before_notes, before_voice),
              "Rejected save changed the source session")
    v.require(fixture.read_bytes() == source_before, "Rejected save changed the source fixture")
    await check.close(source)
    reopened = (await check.call("project_open", path=str(destination)))["session_id"]
    await check.close(reopened)
    check.evidence("integrity_guard", {"fixture": str(fixture), "existing_destination": str(destination),
                                       "classic_vpr": str(raw_vpr)})


@v.feature("remaining.integrity_ai", "interchange", "score_compose", "project_save", "project_open", "project_edit")
async def integrity_ai(check):
    scope = await voice_scope(check)
    async with check.project(score=True) as identifier:
        tracks, notes = await v.vsqx_native_notes(check, identifier)
        voice = await check.edit(identifier, "voice.get", **scope, track_index=0, part_index=0)
        saved, path = await check.save(identifier, "integrity-ai")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        after_tracks, after_notes = await v.vsqx_native_notes(check, reopened)
        after_voice = await check.edit(reopened, "voice.get", **scope, track_index=0, part_index=0)
        resaved, second_path = await check.save(reopened, "integrity-ai-reopened")
        def languages(sequence):
            return [{"voice": track.get("voice"), "parts": [
                {"aiVoice": part.get("aiVoice"), "voice": part.get("voice"),
                 "note_languages": [note.get("langID") for note in part.get("notes", [])]}
                for part in track.get("parts", [])]} for track in sequence["tracks"]]
        v.require(languages(saved) == languages(resaved), "Serialized AI voice or note language changed on reopen/resave")
        v.require(all(note.get("langID") == 0 for track in saved["tracks"]
                      for part in track.get("parts", []) for note in part.get("notes", [])),
                  "Saved AI note language differs from the Japanese seed")
        cache_fields = {"lang_id", "ai_lang_ids"} if scope["scope"] == "track" else set()
        before_identity = {key: value for key, value in voice.items() if key not in cache_fields}
        after_identity = {key: value for key, value in after_voice.items() if key not in cache_fields}
        check.evidence("ai_identity", {"before_voice": voice, "after_voice": after_voice,
                                        "serialized_languages": languages(saved), "vpr": str(path),
                                        "resaved_vpr": str(second_path), "runtime_cache_fields": sorted(cache_fields)})
        v.require((tracks, notes, before_identity) == (after_tracks, after_notes, after_identity),
                  "Ordinary AI VPR identity changed")
        await check.close(reopened)


@v.feature("remaining.ppsf3_selected_voice", "interchange", "project_import", "voicebanks", "project_edit",
           "project_save", "project_open", "project_render_part")
async def ppsf3_selected_voice(check):
    fixture = check.arguments.ppsf3_fixture
    if fixture is None or not fixture.is_file():
        raise v.Blocked("A genuine PPSF V3 fixture is required")
    fixture = fixture.resolve()
    original = fixture.read_bytes()
    with zipfile.ZipFile(fixture) as archive:
        ppsf = json.loads(archive.read("ppsf.json"))["ppsf"]
    singer = ppsf["project"]["dvl_track"][0]["singer"]
    voices = (await check.call("voicebanks"))["voices"]
    chosen = next((item for item in voices if item["kind"] == "Dnn" and item["name"] == "asa"
                   and item["available_in_sequence"] and item["synthesizable_version"] and 0 in item["lang_ids"]), None)
    if chosen is None:
        raise v.Blocked("Installed Japanese-compatible asa Dnn voice is required")
    identifier = (await check.call("project_import", path=str(fixture), prefer_ai=False))["session_id"]
    tracks = (await check.edit(identifier, "track.list"))["tracks"]
    v.require(tracks and tracks[0]["type"] == "MidiAi" and tracks[0]["part_count"],
              "First imported NT track is not a native AI vocal part")
    selected = {"track_index": 0, "part_index": 0}
    settings = {**selected, **(await voice_scope(check))}
    notes = (await check.edit(identifier, "note.list", **selected))["notes"]
    invalid = [note["note_index"] for note in notes if not note["is_valid_phonemes"]]
    if invalid:
        raise v.Blocked(f"Imported part contains invalid phonemes at {invalid[:20]}; no notes were changed")
    before = await check.edit(identifier, "voice.get", **settings)
    assigned = await check.edit(identifier, "voice.set", **settings, ai_voice_bank_id=chosen["comp_id"])
    v.require(assigned["ai_voice_bank_id"] == chosen["comp_id"], "Explicit Dnn assignment failed")
    assigned_notes = (await check.edit(identifier, "note.list", **selected))["notes"]
    v.require([(n["lyric"], n["phonemes"], n["is_valid_phonemes"]) for n in assigned_notes] ==
              [(n["lyric"], n["phonemes"], n["is_valid_phonemes"]) for n in notes],
              "Explicit voice assignment changed lyrics or phonemes")
    _, path = await check.save(identifier, "ppsf3-explicit-voice")
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    after = await check.edit(reopened, "voice.get", **settings)
    v.require(after["ai_voice_bank_id"] == chosen["comp_id"], "Explicit Dnn assignment did not persist")
    rendered = await check.call("project_render_part", session_id=reopened, **selected,
                                output_name=check.output("ppsf3-explicit-voice", ".wav"))
    metadata = inspect_long_render(rendered["path"])
    v.require(fixture.read_bytes() == original, "Explicit assignment changed the source PPSF")
    check.evidence("explicit_selected_voice", {"source": str(fixture), "nt_singer_name": singer.get("singer_name"),
        "nt_library_id": singer.get("library_id"), "before": before, "selected_dnn": chosen["comp_id"],
        "after": after, "vpr": str(path), "wav": rendered["path"], "audio": metadata,
        "note": "Explicit test assignment; NT and VOCALOID identities are distinct."})
    await check.close(reopened)
    await check.close(identifier)


if __name__ == "__main__":
    if sys.argv[1:] == ["--static-classic-audit"]:
        static_classic_audit()
        raise SystemExit(0)
    raise SystemExit(v.main())
