"""Native track-freeze acceptance and retained private diagnostic probes."""

import json
import argparse
import asyncio
import os
from pathlib import Path
import sys
import uuid
import wave
import zipfile
import difflib

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vocaloid_bridge.native_client import NativeClient
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import verify_features as v


@v.feature("freeze.lifecycle", "freeze", "project_edit", "project_save", "project_clone", "project_open")
async def freeze_lifecycle(check):
    async with check.project(score=True) as sid:
        before, _ = await check.save(sid, "freeze-authoring-before")
        state = await check.edit(sid, "track.freeze_state", track_index=0)
        v.require(not state["frozen"], "New source is already frozen")
        state = await check.edit(sid, "track.freeze", track_index=0)
        v.require(state["frozen"] and state["owned"], "Native freeze did not create an owned cache")
        caches = list((v.ROOT / ".runtime" / sid).glob("frozen-*.wav"))
        v.require(len(caches) == 1 and caches[0].stat().st_size > 44, "Frozen cache is missing")
        await check.rejected("project_edit", "unfreeze", session_id=sid, operation="note.update",
                             options={"track_index": 0, "part_index": 0, "note_index": 0, "number": 61})
        saved, path = await check.save(sid, "freeze-authoring-saved")
        v.require(saved == before, "Freeze altered serialized authoring state")
        clone = (await check.call("project_clone", session_id=sid))["session_id"]
        v.require(not (await check.edit(clone, "track.freeze_state", track_index=0))["frozen"],
                  "Clone incorrectly persisted a runtime cache flag")
        cloned, _ = await check.save(clone, "freeze-authoring-clone")
        v.require(cloned == before, "Frozen source clone changed authoring state")
        await check.close(clone)
        await check.edit(sid, "track.unfreeze", track_index=0)
        v.require(not caches[0].exists(), "Unfreeze left the owned cache behind")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        v.require(not (await check.edit(reopened, "track.freeze_state", track_index=0))["frozen"],
                  "Saved project persisted a runtime freeze flag")
        await check.close(reopened)
        empty = (await check.edit(sid, "track.create", type="MidiAi", name="Empty freeze probe"))["track_index"]
        await check.rejected("project_edit", "placement|freeze", session_id=sid, operation="track.freeze",
                             options={"track_index": empty})
        v.require(not list((v.ROOT / ".runtime" / sid).glob("frozen-*.wav")), "Failed freeze leaked a private cache")
        check.evidence("freeze_authoring", {"saved": str(path), "state": state, "authoring_equal": True})


@v.feature("freeze.dvqm_noop", "freeze", "project_create", "project_edit", "project_library", "project_status", "voicebanks", "vocaloid_features")
async def freeze_dvqm_noop(check):
    product = (await check.call("vocaloid_features"))["product"]
    voices = (await check.call("voicebanks"))["voices"]
    voice = next(item for item in voices if item["name"] == "asa" and item["available_in_sequence"])
    async with check.project() as sid:
        await check.edit(sid, "track.create", type="MidiAi", name="Frozen no-op")
        await check.edit(sid, "part.create", track_index=0, start_tick=0, duration_tick=1920)
        scope = {"track_index": 0, "part_index": 0}
        await check.edit(sid, "voice.set", **scope, **({"scope": "track"} if product == "VOCALOID7" else {}),
                         ai_voice_bank_id=voice["comp_id"])
        await check.edit(sid, "note.add", **scope, start_tick=0, duration_tick=480,
                         number=60, lyric="\u3042", phonemes="a", lang_id=0)
        state = await check.edit(sid, "track.freeze", track_index=0)
        v.require(state["frozen"] and state["owned"], "Native freeze did not create an owned cache")
        caches = list((v.ROOT / ".runtime" / sid).glob("frozen-*.wav"))
        v.require(len(caches) == 1 and caches[0].stat().st_size > 44, "Frozen cache is missing")
        cache_bytes = caches[0].read_bytes()
        status = await check.call("project_status", session_id=sid)
        history = await check.edit(sid, "history.status")
        for is_attack in (True, False):
            target = {**scope, "note_index": 0, "is_attack": is_attack}
            selection = await check.library("dvqm_get", sid, **target)
            v.require(selection["is_empty"] and await check.library("dvqm_clear", sid, **target) == selection,
                      "Frozen-track empty DVQM clear did not remain a no-op")
        v.require((await check.call("project_status", session_id=sid))["dirty"] == status["dirty"]
                  and await check.edit(sid, "history.status") == history and caches[0].read_bytes() == cache_bytes
                  and (await check.edit(sid, "track.freeze_state", track_index=0))["frozen"],
                  "Empty DVQM clear changed a frozen track, cache or history")
        await check.rejected("project_edit", "unfreeze", session_id=sid, operation="note.update",
                             options={**scope, "note_index": 0, "number": 61})
        await check.edit(sid, "track.unfreeze", track_index=0)
        v.require(not caches[0].exists(), "Unfreeze left the owned cache behind")


@v.feature("freeze.extended", "freeze", "score_compose", "project_edit", "project_library", "project_audio",
           "project_open", "project_save", "project_clone", "project_inspect", "vocaloid_features", "vocaloid_operations")
async def freeze_extended(check):
    is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
    attack_catalog = await check.library("dvqm_catalog", is_attack=True, limit=1)
    if not attack_catalog["entries"]:
        raise v.Blocked("An installed native Attack preset is required")
    attack = attack_catalog["entries"][0]
    async with check.project(score=True) as sid:
        scope = {"track_index": 0, "part_index": 0}
        await check.edit(sid, "pitch.set", **scope, note_index=0, points=[{"tick": 100, "value": 60.5}])
        await check.edit(sid, "controller.set", **scope, type="Dynamics", points=[{"tick": 100, "value": 42}])
        lane = await check.edit(sid, "automation.list", scope="track_volume", track_index=0)
        await check.edit(sid, "automation.set", scope="track_volume", track_index=0,
                         points=[{"tick": 480, "value": lane["minimum"]}])
        styles = (await check.library("style_list", query="asa"))["styles"]
        style = next(item for item in styles if item["name"] == "asa Warm Chorus")
        await check.library("style_apply", sid, **scope, **({"scope": "track"} if is_v7 else {}),
                            style_id=style["style_id"], include_audio=True)
        sequence, native_path = await check.save(sid, "freeze-extension-native")
    _, members = v.read_vpr(native_path)
    marker = "x_freeze_48"
    track = sequence["tracks"][0]
    part = track["parts"][0]
    note = part["notes"][0]
    sequence[marker], track[marker], part[marker], note[marker] = "root", "track", "part", "note"
    conflict_note = part["notes"][1]
    conflict_note.pop("singingSkill", None)
    conflict_note["dvqm"] = {"attack": {"compID": attack["component_id"], "levelNames": attack["level_names"],
                                        "isProtected": True, "speed": 77, "topFactor": 1.0}}
    note["directPitches"][0][marker] = "pitch"
    next(item for item in part["controllers"] if item["name"].lower() == "dynamics")["events"][0][marker] = "controller"
    next(item for item in track["volume"]["events"] if item["pos"] == 480)[marker] = "automation"
    effect = (track if is_v7 else part)["audioEffects"][0]
    effect[marker] = "effect"
    if effect.get("parameters"):
        effect["parameters"][0][marker] = "parameter"
    extra = "Project/bridge-probe/freeze-extra.bin"
    members[extra] = b"freeze-extra-resource\x00\x01"
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("freeze-extension-source")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        original_state, _ = await check.save(sid, "freeze-extension-original")
        await check.edit(sid, "note.update", track_index=0, part_index=0, note_index=0, number=61)
        baseline, _ = await check.save(sid, "freeze-extension-before")
        history = await check.edit(sid, "history.status")
        discovery = await check.call("project_inspect", session_id=sid, feature="freeze", track_index=0)
        templates = {item["arguments"]["operation"]: item for item in discovery["contract"]["write_calls"]}
        v.require(set(templates) == {"track.freeze", "track.unfreeze"} and all(
              item["tool"] == "project_edit" and item["arguments"]["session_id"] == sid
              and item["arguments"]["options"] == {"track_index": 0} for item in templates.values()),
              "Freeze templates did not bind the selected session and track")
        catalog = await check.call("vocaloid_operations", domain="score", operation="track.freeze")
        v.require("freeze" in catalog["domains"]["score"]["operations"][0]["features"],
              "Track freeze operation is not linked to its feature")
        presend = (await check.edit(sid, "sequence.get"))["presend_time_sec"]
        mix = await check.audio(sid, "mixdown", track_indices=[0], output_name=check.output("freeze-extension-mix", ".wav"),
                    sample_rate=44100, channels=2, bits_per_sample=16, bypass_effects=False)
        mix_metadata, mix_samples = v.read_audio(mix["path"])
        state = await check.edit(sid, "track.freeze", **templates["track.freeze"]["arguments"]["options"])
        v.require(state["frozen"] and state["owned"], "Extension project did not freeze")
        conflict_target = {"track_index": 0, "part_index": 0, "note_index": 1, "is_attack": True}
        conflict_before = await check.library("dvqm_get", sid, **conflict_target)
        v.require(not conflict_before["is_empty"], "Frozen conflict fixture lost its Attack")
        await check.rejected("project_library", "identity transaction|unfreeze|cannot preserve", session_id=sid,
                     operation="dvqm_clear", options=conflict_target)
        v.require(await check.library("dvqm_get", sid, **conflict_target) == conflict_before,
              "Rejected frozen Attack clear changed the selection")
        caches = list((v.ROOT / ".runtime" / sid).glob("frozen-*.wav"))
        v.require(len(caches) == 1, "Extension project frozen cache is missing")
        cache_metadata, cache_samples = v.read_audio(caches[0])
        padding = round(presend * mix_metadata["sample_rate"])
        v.require(cache_metadata["peak"] > 0 and len(cache_samples) == len(mix_samples) + padding
              and np.all(cache_samples[:padding] == 0)
              and np.allclose(cache_samples[padding:], mix_samples, atol=2 / 32768, rtol=0),
              "Extension project frozen cache differs from the native mix or presend alignment")
        saved, path = await check.save(sid, "freeze-extension-frozen")
        v.require(saved == baseline and v.read_vpr(path)[1][extra] == members[extra],
                  "Frozen save changed extension-bearing authoring data")
        clone = (await check.call("project_clone", session_id=sid))["session_id"]
        try:
            clone_state = await check.edit(clone, "track.freeze_state", track_index=0)
            cloned, clone_path = await check.save(clone, "freeze-extension-clone")
            v.require(not clone_state["frozen"] and cloned == baseline and v.read_vpr(clone_path)[1][extra] == members[extra],
                      "Frozen clone lost extension data or retained the cache")
        finally:
            await check.close(clone)
        await check.edit(sid, "track.unfreeze", **templates["track.unfreeze"]["arguments"]["options"])
        unfrozen, unfrozen_path = await check.save(sid, "freeze-extension-unfrozen")
        v.require(unfrozen == baseline and v.read_vpr(unfrozen_path)[1][extra] == members[extra]
                  and not caches[0].exists() and await check.edit(sid, "history.status") == history,
                  "Unfreeze changed extension data, history, or retained the cache")
        await check.edit(sid, "undo")
        undone, undo_path = await check.save(sid, "freeze-extension-undo")
        v.require(undone == original_state and v.read_vpr(undo_path)[1][extra] == members[extra],
                  "Undo after unfreeze did not restore extension-bearing history")
        await check.edit(sid, "redo")
        redone, redo_path = await check.save(sid, "freeze-extension-redo")
        v.require(redone == baseline and v.read_vpr(redo_path)[1][extra] == members[extra],
                  "Redo after unfreeze did not restore extension-bearing history")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        try:
            restored, restored_path = await check.save(reopened, "freeze-extension-reopened")
            v.require(restored == baseline and v.read_vpr(restored_path)[1][extra] == members[extra],
                      "Reopening lost extension data or resources")
        finally:
            await check.close(reopened)
    finally:
        await check.close(sid)
    v.require(source.read_bytes() == original, "Source extension project changed")


async def mcp_smoke(fixture, run):
    original = fixture.read_bytes()
    params = StdioServerParameters(command=sys.executable, args=["-m", "vocaloid_bridge"], cwd=str(ROOT),
        env={**os.environ, "VOCALOID_WORKSPACE": str(ROOT), "PYTHONUTF8": "1"})
    result = {"fixture": str(fixture), "transport": "mcp-stdio"}
    session = None
    clone = None
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as client:
            await client.initialize()
            async def call(tool, **options):
                response = await client.call_tool(tool, options)
                if response.isError or response.structuredContent is None:
                    raise RuntimeError(f"{tool}: {response.content}")
                return response.structuredContent
            try:
                session = (await call("project_open", path=str(fixture)))["session_id"]
                async def edit(operation, **options):
                    return (await call("project_edit", session_id=session, operation=operation, options=options))["result"]
                notes = await edit("note.list", track_index=0, part_index=0)
                before = await call("project_save", session_id=session, output_name=f"freeze-mcp-{run}-before.vpr")
                result["before"] = await edit("track.freeze_state", track_index=0)
                assert not result["before"]["frozen"]
                stems_before = set((ROOT / "output").glob("freeze-stem-*.wav"))
                result["freeze"] = await edit("track.freeze", track_index=0)
                assert result["freeze"]["frozen"] and result["freeze"]["owned"]
                assert set((ROOT / "output").glob("freeze-stem-*.wav")) == stems_before
                owned = list((ROOT / ".runtime" / session).glob("frozen-*.wav"))
                assert len(owned) == 1
                denied = await client.call_tool("project_edit", {"session_id": session, "operation": "note.update",
                    "options": {"track_index": 0, "part_index": 0, "note_index": 0, "number": 61}})
                assert denied.isError, "Frozen session accepted a score mutation"
                result["edit_guard_rejected"] = True
                saved = await call("project_save", session_id=session, output_name=f"freeze-mcp-{run}-saved.vpr")
                def sequence(path):
                    with zipfile.ZipFile(path) as archive:
                        return json.loads(archive.read("Project/sequence.json"))
                assert sequence(before["path"]) == sequence(saved["path"])
                assert (await edit("track.freeze_state", track_index=0))["frozen"] and owned[0].exists()
                clone = (await call("project_clone", session_id=session))["session_id"]
                clone_state = await call("project_edit", session_id=clone, operation="track.freeze_state", options={"track_index": 0})
                assert not clone_state["result"]["frozen"]
                clone_saved = await call("project_save", session_id=clone, output_name=f"freeze-mcp-{run}-clone.vpr")
                assert sequence(before["path"]) == sequence(clone_saved["path"])
                result["clone_unfrozen_authoring_equal"] = True
                await call("project_close", session_id=clone, discard_changes=True)
                clone = None
                result["unfreeze"] = await edit("track.unfreeze", track_index=0)
                assert not result["unfreeze"]["frozen"] and not owned[0].exists()
                assert await edit("note.list", track_index=0, part_index=0) == notes
                empty = await edit("track.create", type="MidiAi", name="Freeze failure probe")
                failure = await client.call_tool("project_edit", {"session_id": session, "operation": "track.freeze",
                    "options": {"track_index": empty["track_index"]}})
                assert failure.isError, "Freeze unexpectedly accepted an empty track"
                assert set((ROOT / "output").glob("freeze-stem-*.wav")) == stems_before
                assert not list((ROOT / ".runtime" / session).glob("frozen-*.wav"))
                result["failed_freeze_cleanup"] = True
                await call("project_close", session_id=session, discard_changes=True)
                session = (await call("project_open", path=saved["path"]))["session_id"]
                result["reopened"] = await edit("track.freeze_state", track_index=0)
                assert not result["reopened"]["frozen"]
                assert await edit("note.list", track_index=0, part_index=0) == notes
                result["source_unchanged"] = fixture.read_bytes() == original
                assert result["source_unchanged"]
                result["status"] = "passed"
            finally:
                if clone:
                    await call("project_close", session_id=clone, discard_changes=True)
                if session:
                    await call("project_close", session_id=session, discard_changes=True)
    destination = ROOT / "artifacts" / f"freeze-mcp-{run}.json"
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"receipt": str(destination), **result}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--flag", action="store_true")
    parser.add_argument("--mcp", action="store_true")
    parser.add_argument("--chain", action="store_true")
    parser.add_argument("--layout", choices=("zero", "offset", "multipart", "multipart_gain", "multipart_gain_only", "multipart_volume_only"), default="zero")
    args = parser.parse_args()
    run = uuid.uuid4().hex[:12]
    fixture = ROOT / "output/feature-7085da10d352-001-robot-seed.vpr"
    if args.mcp:
        asyncio.run(mcp_smoke(fixture, run))
        return
    if args.chain:
        chain(fixture, run, args.layout)
        return
    client = NativeClient(ROOT)
    session = None
    try:
        session = client.request("open", {"path": str(fixture)})["session_id"]
        def method(name, args, reference=None):
            target = {"session_id": session, "ref": reference}
            methods = client.request("members", target)["methods"]
            matching = [m for m in methods if m["member_id"].startswith(name + "(") and len(m["parameters"]) == len(args)]
            assert len(matching) == 1, matching
            return client.request("call", {**target, "member_id": matching[0]["member_id"], "args": args})["value"]
        track = method("GetTrack", [0])["$ref"]
        def state():
            return {"is_frozen": client.request("get", {"session_id": session, "ref": track, "member": "IsFrozen"})["value"],
                    "can_freeze": method("CanFreeze", [], track)}
        before = state()
        rendered = client.request("render_part", {"session_id": session, "track_index": 0, "part_index": 0,
            "output_name": f"freeze-probe-{run}.wav"})
        after = state()
        result = {"fixture": str(fixture), "before_render": before, "after_render": after,
                  "native_part_render": rendered, "mutated_freeze_state": False}
        if args.flag:
            result["set_flag"] = client.request("set", {"session_id": session, "ref": track, "member": "IsFrozen", "value": True})
            result["after_flag"] = state()
            result["history"] = client.request("score_edit", {"session_id": session, "operation": "history.status", "options": {}})["result"]
            result["mutated_freeze_state"] = True
            try:
                result["flag_only_mix"] = client.request("audio_op", {"session_id": session, "operation": "mixdown", "options": {
                    "track_indices": [0], "output_name": f"freeze-flag-only-{run}.wav", "bypass_effects": True,
                    "sample_rate": 44100, "channels": 2, "bits_per_sample": 16}})
            except Exception as error:
                result["flag_only_mix_error"] = str(error)
        destination = ROOT / "artifacts" / f"freeze-probe-{run}.json"
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"receipt": str(destination), **result}, ensure_ascii=False))
    finally:
        if session:
            client.request("close", {"session_id": session, "discard": True})
        client.close()


def chain(fixture, run, layout):
    client = NativeClient(ROOT)
    session = None
    original = fixture.read_bytes()
    result = {"fixture": str(fixture), "diagnostic_only": True, "layout": layout}
    try:
        session = client.request("open", {"path": str(fixture)})["session_id"]
        def edit(operation, **options):
            return client.request("score_edit", {"session_id": session, "operation": operation, "options": options})["result"]
        def mix(name):
            return client.request("audio_op", {"session_id": session, "operation": "mixdown", "options": {
                "track_indices": [0], "output_name": name, "bypass_effects": False,
                "sample_rate": 44100, "channels": 2, "bits_per_sample": 16}})
        def samples(path):
            with wave.open(path, "rb") as wav:
                params = [wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()]
                return params, np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float64) / 32768
        def probe(name, fn):
            try:
                result[name] = {"status": "passed", "value": fn()}
            except Exception as error:
                result[name] = {"status": "failed", "error": str(error)}
            print(name, json.dumps(result[name], ensure_ascii=False), flush=True)

        if layout in ("offset", "multipart", "multipart_gain", "multipart_gain_only", "multipart_volume_only"):
            edit("part.move", track_index=0, part_index=0, start_tick=1920)
        if layout in ("multipart", "multipart_gain", "multipart_gain_only", "multipart_volume_only"):
            edit("part.duplicate", track_index=0, part_index=0, start_tick=9600)
        if layout in ("multipart_gain", "multipart_gain_only"):
            def audio_op(operation, **options):
                return client.request("audio_op", {"session_id": session, "operation": operation, "options": options})
            catalog = audio_op("effects", scope="catalog")
            gain = next(item for item in catalog["effects"] if "gain" in item["name"].lower())
            metadata = audio_op("effects", scope="catalog", effect_id=gain["effect_id"])
            parameter = next(item for item in metadata["parameters"] if "gain" in item["name"].lower())
            result["gain"] = audio_op("set_effect", scope="track", track_index=0, action="add",
                effect_id=gain["effect_id"], parameters={parameter["name"]: 0.75}, bypass=False)
        if layout in ("multipart_gain", "multipart_volume_only"):
            bounds = edit("automation.list", scope="track_volume", track_index=0)
            value = max(bounds["minimum"], bounds["default_value"] - 30)
            result["automation"] = edit("automation.set", scope="track_volume", track_index=0,
                points=[{"tick": 0, "value": bounds["default_value"]}, {"tick": 4800, "value": value}])
        def notes_snapshot():
            parts = edit("part.list", track_index=0)["parts"]
            return [{"part": {k: v for k, v in part.items() if k not in ("voice_name", "ai_voice_name")},
                     "notes": edit("note.list", track_index=0, part_index=part["part_index"])} for part in parts]
        notes = notes_snapshot()
        result["before_notes"] = notes
        saved_before = client.request("save", {"session_id": session, "output_name": f"freeze-chain-{run}-before.vpr"})
        result["saved_before"] = saved_before
        baseline = mix(f"freeze-chain-{run}-baseline.wav")
        stems_before = set((ROOT / "output").glob("freeze-stem-*.wav"))
        frozen = edit("track.freeze", track_index=0)
        assert frozen["frozen"] and frozen["owned"], frozen
        assert set((ROOT / "output").glob("freeze-stem-*.wav")) == stems_before
        owned_files = list((ROOT / ".runtime" / session).glob("frozen-*.wav"))
        assert len(owned_files) == 1, owned_files
        frozen_path = owned_files[0].resolve()
        assert frozen_path.is_relative_to((ROOT / ".runtime").resolve()), frozen_path
        result["freeze"] = frozen
        def frozen_mix():
            output = mix(f"freeze-chain-{run}-frozen.wav")
            a, b = samples(baseline["path"]), samples(output["path"])
            assert a[0] == b[0], (a[0], b[0])
            difference = float(np.sqrt(np.mean((a[1] - b[1]) ** 2)))
            baseline_rms = float(np.sqrt(np.mean(a[1] ** 2)))
            assert baseline_rms > 0 and difference <= baseline_rms * 0.01, {"baseline_rms": baseline_rms, "difference_rms": difference}
            return {"output": output, "baseline_rms": baseline_rms, "difference_rms": difference}
        probe("frozen_mix", frozen_mix)
        assert notes_snapshot() == notes
        saved = client.request("save", {"session_id": session, "output_name": f"freeze-chain-{run}.vpr"})
        result["saved"] = saved
        def sequence_lines(path):
            with zipfile.ZipFile(path) as archive:
                return json.dumps(json.loads(archive.read("Project/sequence.json")), ensure_ascii=False, sort_keys=True, indent=2).splitlines()
        before_lines, after_lines = sequence_lines(saved_before["path"]), sequence_lines(saved["path"])
        result["vpr_sequence_equal"] = before_lines == after_lines
        result["vpr_sequence_diff"] = list(difflib.unified_diff(before_lines, after_lines, fromfile="before", tofile="frozen", n=2))
        result["post_save_live_state"] = edit("track.freeze_state", track_index=0)
        assert result["post_save_live_state"]["frozen"] and frozen_path.exists()
        assert result["vpr_sequence_equal"], "Frozen authoring snapshot differs: " + "\n".join(result["vpr_sequence_diff"])
        def unfreeze():
            state = edit("track.unfreeze", track_index=0)
            assert not state["frozen"]
            assert not frozen_path.exists(), "Native unfreeze did not remove its session-owned WAV"
            assert notes_snapshot() == notes
            output = mix(f"freeze-chain-{run}-unfrozen.wav")
            return {"state": state, "output": output}
        probe("unfreeze_before_close", unfreeze)
        client.request("close", {"session_id": session, "discard": True})
        session = client.request("open", {"path": saved["path"]})["session_id"]
        result["reopened_state"] = edit("track.freeze_state", track_index=0)
        result["reopened_notes"] = notes_snapshot()
        result["reopened_notes_equal"] = result["reopened_notes"] == notes
        probe("reopened_mix", lambda: mix(f"freeze-chain-{run}-reopened.wav"))
        if result["reopened_state"]["frozen"]:
            probe("unfreeze_after_reopen", unfreeze)
        result["source_bytes_unchanged"] = fixture.read_bytes() == original
    except Exception as error:
        result["fatal_error"] = str(error)
    finally:
        if session:
            client.request("close", {"session_id": session, "discard": True})
        client.close()
        destination = ROOT / "artifacts" / f"freeze-chain-{run}.json"
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("RECEIPT", destination, flush=True)
    if ("fatal_error" in result or any(item.get("status") == "failed" for item in result.values() if isinstance(item, dict))
            or not result.get("source_bytes_unchanged") or not result.get("reopened_notes_equal") or not result.get("vpr_sequence_equal")):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
