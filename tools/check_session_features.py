"""Focused MCP checks for native VPR import and full native expression records."""
from __future__ import annotations

import math
import numpy as np
import verify_features as v


def compare_fields(actual, expected, label):
    v.require(actual.keys() == expected.keys(), label + " fields differ")
    for name, value in expected.items():
        if isinstance(value, float):
            v.require(math.isclose(actual[name], value, abs_tol=1e-6), label + "." + name, actual[name])
        else:
            v.require(actual[name] == value, label + "." + name, actual[name])


@v.feature("session.vpr_import", "session", "project_import", "project_save", "project_open", "project_edit")
async def vpr_import(check):
    async with check.project(score=True) as original:
        _, path = await check.save(original, "vpr-import-source")
        original_bytes = path.read_bytes()
        expected = await check.edit(original, "note.list", track_index=0, part_index=0)
        imported = (await check.call("project_import", path=str(path)))["session_id"]
        try:
            v.require(await check.edit(imported, "note.list", track_index=0, part_index=0) == expected,
                      "VPR import changed native notes")
            await check.edit(imported, "note.update", track_index=0, part_index=0, note_index=0, number=72)
            _, saved = await check.save(imported, "vpr-import-edited")
            reopened = (await check.call("project_open", path=str(saved)))["session_id"]
            try:
                v.require((await check.edit(reopened, "note.list", track_index=0, part_index=0))["notes"][0]["number"] == 72,
                          "Imported native edit did not survive reopen")
            finally:
                await check.close(reopened)
            v.require(path.read_bytes() == original_bytes, "VPR source was changed")
            check.evidence("vpr_import", {"source": str(path), "edited": str(saved)})
        finally:
            await check.close(imported)


@v.feature("session.expression_records", "session", "project_edit", "project_save", "project_open", "project_render_part")
async def expression_records(check):
    async with check.project(score=True) as sid:
        scope = {"track_index": 0, "part_index": 0}
        before = (await check.edit(sid, "note.list", **scope))["notes"][0]
        bounds = await check.edit(sid, "note.expression_bounds", **scope)
        updates = {}
        for group in ("expression", "ai_expression"):
            data = bounds[group]
            v.require(data["minimum"].keys() == data["maximum"].keys() == data["defaults"].keys() == before[group].keys(),
                      "Native expression range is incomplete", group)
            update = {}
            for name, old in before[group].items():
                low, high = data["minimum"][name], data["maximum"][name]
                v.require(low <= old <= high, "Current expression outside native range", (group, name, low, old, high))
                if isinstance(old, bool):
                    update[name] = not old if low != high else old
                elif isinstance(old, int):
                    candidate = round(low + (high - low) * 0.25)
                    update[name] = candidate if candidate != old else min(high, candidate + 1)
                else:
                    candidate = low + (high - low) * 0.25
                    update[name] = candidate if not math.isclose(candidate, old) else low + (high - low) * 0.75
            updates[group] = update
        await check.edit(sid, "note.update", **scope, note_index=0, **updates)
        current = (await check.edit(sid, "note.list", **scope))["notes"][0]
        for group, expected in updates.items():
            compare_fields(current[group], expected, group)
        _, path = await check.save(sid, "all-expression-fields")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        try:
            after = (await check.edit(reopened, "note.list", **scope))["notes"][0]
            for group, expected in updates.items():
                compare_fields(after[group], expected, "reopened " + group)
            audio = await check.call("project_render_part", session_id=reopened, **scope,
                                     output_name=check.output("all-expression-fields", ".wav"))
            v.require(audio["audio"]["peak"] > 0, "Expression-edited part rendered silent")
            check.evidence("expressions", {"bounds": bounds, "changed": updates, "vpr": str(path), "wav": audio["path"]})
        finally:
            await check.close(reopened)


@v.feature("session.performance_records", "session", "project_edit", "project_library", "project_save", "project_open")
async def performance_records(check):
    async with check.project(score=True) as sid:
        scope = {"track_index": 0, "part_index": 0}
        before = await check.edit(sid, "performance.get", **scope)
        v.require({item["name"] for item in before["voice_colors"] if item["applicable_to_current_part"]} ==
                  {"S5Expression", "S5Air", "S5Character"}, "AI VoiceColor applicability is incorrect")
        v.require(all(item["applies_to"] == ("MidiAi" if item["applicable_to_current_part"] else "Midi")
                      for item in before["voice_colors"]), "VoiceColor engine mapping is inconsistent")
        colors = {}
        for field in before["voice_colors"]:
            low, high = field["setting"]["LowerBoundValue"], field["setting"]["UpperBoundValue"]
            candidate = round(low + (high - low) * 0.25)
            colors[field["name"]] = candidate if candidate != field["value"] else min(high, candidate + 1)
        take = before["take"]
        lane = take["setting"]["UpperBoundValue"] if take["lane"] != take["setting"]["UpperBoundValue"] else take["setting"]["LowerBoundValue"]
        changed = await check.edit(sid, "performance.set", **scope, voice_colors=colors, take_lane=lane)
        v.require({field["name"]: field["value"] for field in changed["voice_colors"]} == colors, "VoiceColor readback differs")
        v.require(changed["take"]["lane"] == lane, "Take lane readback differs")
        clip = (await check.library("media_capture", sid, **scope, name="Full performance " + check.run_id))["clip"]
        try:
            target = (await check.edit(sid, "track.create", type="MidiAi", name="Performance clone"))["track_index"]
            await check.library("media_import", sid, clip_id=clip["clip_id"], track_index=target, position_tick=0)
            v.require(await check.edit(sid, "performance.get", track_index=target, part_index=0) == changed,
                      "Media lost full performance values")
            _, path = await check.save(sid, "all-performance-fields")
            reopened = (await check.call("project_open", path=str(path)))["session_id"]
            try:
                v.require(await check.edit(reopened, "performance.get", track_index=target, part_index=0) == changed,
                          "Performance fields did not survive reopen")
            finally:
                await check.close(reopened)
            check.evidence("performance", {"values": changed, "vpr": str(path)})
        finally:
            await check.library("media_delete", sid, clip_id=clip["clip_id"])


@v.feature("session.breath_audio", "session", "score_compose", "project_edit", "project_render_part", "project_save", "project_open")
async def breath_audio(check):
    seed = await check.call("score_compose", output_name=check.output("breath-seed"),
                            title="Breath effect probe", bpm=120,
                            notes=[{"start": start, "duration": 0.8, "pitch": 60 + (i % 3) * 2,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}
                                   for i, start in enumerate((0, 1, 4, 5, 8, 9, 12, 13))])
    sid = seed["native_session"]["session_id"]
    scope = {"track_index": 0, "part_index": 0}
    report = {}
    check.evidence("breath_audio", report)
    try:
        state = await check.edit(sid, "performance.get", **scope)
        report["initial"] = state["breath"]
        high = state["breath"]["setting"]["UpperBoundValue"]
        low = state["breath"]["setting"]["LowerBoundValue"]
        async def render(label):
            result = await check.call("project_render_part", session_id=sid, **scope,
                                      output_name=check.output("breath-" + label, ".wav"))
            metadata, samples = v.read_audio(result["path"])
            v.require(metadata["rms"] > 1e-5, "Breath probe is silent", metadata)
            return result["path"], samples

        await check.edit(sid, "performance.set", **scope, bypass={"Breath": True})
        baseline_path, baseline = await render("bypassed")
        report["baseline"] = baseline_path
        configurations = (("female-often", "Female", "Often", high),
                          ("male-often", "Male", "Often", high),
                          ("female-low", "Female", "Often", low),
                          ("female-rarely", "Female", "Rarely", high))
        primary = None
        for label, kind, mode, volume in configurations:
            actual = await check.edit(sid, "performance.set", **scope, breath_mode=mode,
                                      breath_type=kind, breath_exhalation=volume, bypass={"Breath": False})
            path, samples = await render(label)
            v.require(samples.shape == baseline.shape, "Breath probe changed the output shape")
            if primary is None:
                primary = samples
            report[label] = {"path": path, "state": actual["breath"],
                             "difference_from_bypassed_rms": float(np.sqrt(np.mean((samples - baseline) ** 2))),
                             "difference_from_female_often_rms": float(np.sqrt(np.mean((samples - primary) ** 2)))}
        v.require(report["female-often"]["difference_from_bypassed_rms"] > 1e-5,
                  "Enabled Breath had no measurable effect on the gapped phrase", report)
        v.require(report["female-low"]["difference_from_female_often_rms"] > 1e-5,
                  "Breath exhalation had no measurable effect on the gapped phrase", report)
        v.require(report["female-rarely"]["difference_from_female_often_rms"] > 1e-5,
                  "Breath frequency had no measurable effect on the gapped phrase", report)
        await check.edit(sid, "performance.set", **scope, breath_mode="Often", breath_type="Female",
                         breath_exhalation=high, bypass={"Breath": False})
        _, path = await check.save(sid, "breath-enabled")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        try:
            restored = await check.edit(reopened, "performance.get", **scope)
            v.require(restored["breath"] == report["female-often"]["state"], "Breath parameters changed on reopen")
            v.require(not next(item for item in restored["bypass"] if item["effect"] == "Breath")["bypassed"],
                      "Breath bypass changed on reopen")
            report["reopened"] = restored["breath"]
        finally:
            await check.close(reopened)
    finally:
        await check.close(sid)


if __name__ == "__main__":
    import sys
    if not any(argument in ("--case", "--category") for argument in sys.argv[1:]):
        sys.argv.extend(["--category", "session"])
    raise SystemExit(v.main())
