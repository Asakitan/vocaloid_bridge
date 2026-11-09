"""Focused real-MCP interchange checks; the runner never builds the host.

Examples:
  .venv/Scripts/python.exe tools/check_interchange_remaining.py --case remaining.clone_audio
  .venv/Scripts/python.exe tools/check_interchange_remaining.py --case remaining.vsqx3 --vsqx3-fixture .runtime/vsqx3-reference.vsqx
  .venv/Scripts/python.exe tools/check_interchange_remaining.py --case remaining.ppsf3 --ppsf3-fixture PATH
"""
from pathlib import Path
import json
import zipfile

import numpy as np
import verify_features as v


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


async def identity_roundtrip(check, path: Path | None, label: str, signature: bytes | None = None):
    if path is None or not path.is_file():
        raise v.Blocked("A real native fixture is required for " + label)
    path = path.resolve()
    original = path.read_bytes()
    if signature is not None:
        v.require(original.startswith(signature), "Fixture has the wrong format signature")
    identifier = (await check.call("project_import", path=str(path), prefer_ai=False))["session_id"]
    tracks, notes = await v.vsqx_native_notes(check, identifier)
    async def voices(session, items):
        return [await check.edit(session, "voice.get", track_index=t["track_index"], part_index=i)
                for t in items if t["type"] in ("Midi", "MidiAi") for i in range(t["part_count"])]
    before = await voices(identifier, tracks)
    v.require(notes and before, "Fixture has no vocal notes or parts")
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
    path = check.arguments.ppsf_fixture
    if path is None or not path.is_file():
        raise v.Blocked("A real classic PPSF V2 fixture is required")
    identifier = (await check.call("project_import", path=str(path.resolve()), prefer_ai=False))["session_id"]
    tracks, _ = await v.vsqx_native_notes(check, identifier)
    identities = []
    for track in tracks:
        parts = []
        for part in range(track["part_count"]):
            parts.append(await check.edit(identifier, "voice.get", track_index=track["track_index"], part_index=part))
        identities.append(parts)
    v.require(all(t["type"] == "Midi" for t in tracks), "Candidate requires classic MIDI tracks")
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
    after = [[await check.edit(reopened, "voice.get", track_index=t["track_index"], part_index=i)
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
    path = check.arguments.ppsf_fixture
    if path is None or not path.is_file():
        raise v.Blocked("A real classic PPSF V2 fixture is required")
    source = (await check.call("project_import", path=str(path.resolve()), prefer_ai=False))["session_id"]
    source_tracks, _ = await v.vsqx_native_notes(check, source)
    source_voices = [await check.edit(source, "voice.get", track_index=t["track_index"], part_index=0)
                     for t in source_tracks]
    target = (await check.call("project_create", title="Duplicate candidate", bpm=120))["session_id"]
    await check.call("project_merge", session_id=target, path=str(path.resolve()), include_tracks=True)
    tracks, _ = await v.vsqx_native_notes(check, target)
    voices = [await check.edit(target, "voice.get", track_index=t["track_index"], part_index=0) for t in tracks]
    check.evidence("after_duplicate", {"tracks": tracks, "voices": voices})
    v.require(tracks == source_tracks and [x["voice_bank_id"] for x in voices] ==
              [x["voice_bank_id"] for x in source_voices], "Native duplicate changed track type or voice ID")
    _, destination = await check.save(target, "classic-duplicate")
    reopened = (await check.call("project_open", path=str(destination)))["session_id"]
    saved_tracks, _ = await v.vsqx_native_notes(check, reopened)
    saved_voices = [await check.edit(reopened, "voice.get", track_index=t["track_index"], part_index=0)
                    for t in saved_tracks]
    check.evidence("after_reopen", {"tracks": saved_tracks, "voices": saved_voices})
    v.require(saved_tracks == source_tracks and saved_voices == source_voices,
              "Duplicate plus native save/reopen changed classic identity")
    await check.close(reopened)
    await check.close(target)
    await check.close(source)


@v.feature("remaining.classic_created", "interchange", "project_create", "project_edit", "project_save", "project_open")
async def classic_created(check):
    await check.call("voicebanks")
    target = (await check.call("project_create", title="Classic created", bpm=120))["session_id"]
    track = (await check.edit(target, "track.create", type="Midi", name="Classic"))["track_index"]
    part = (await check.edit(target, "part.create", track_index=track, start_tick=0, duration_tick=1920))["part_index"]
    before_track = (await check.edit(target, "track.list"))["tracks"]
    before = await check.edit(target, "voice.get", track_index=track, part_index=part)
    sequence, destination = await check.save(target, "classic-created")
    reopened = (await check.call("project_open", path=str(destination)))["session_id"]
    after_track = (await check.edit(reopened, "track.list"))["tracks"]
    after = await check.edit(reopened, "voice.get", track_index=track, part_index=part)
    check.evidence("classic_created", {"before_track": before_track, "before_voice": before,
                                       "serialized_type": sequence["tracks"][0]["type"],
                                       "after_track": after_track, "after_voice": after})
    v.require(before_track == after_track and before == after, "Fresh classic track changed on reopen")
    await check.close(reopened)
    await check.close(target)


if __name__ == "__main__":
    raise SystemExit(v.main())
