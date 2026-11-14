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
    is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
    async with check.project(score=True) as sid:
        scope = {"track_index": 0, "part_index": 0, "scope": "track" if is_v7 else "part"}
        before = await check.edit(sid, "performance.get", **scope)
        applicability = "applicable_to_current_track" if is_v7 else "applicable_to_current_part"
        applicable = {item["name"] for item in before["voice_colors"] if item[applicability]}
        expected = {"S5Expression", "S5Air", "S5Character"}
        v.require(expected <= applicable <= expected | ({"S5Attack"} if is_v7 else set()),
                  "AI VoiceColor applicability is incorrect", before)
        v.require(all(item["applies_to"] == ("MidiAi" if item["name"].startswith("S5") else "Midi")
                      for item in before["voice_colors"]), "VoiceColor engine mapping is inconsistent")
        colors = {}
        for field in before["voice_colors"]:
            if is_v7 and not field[applicability]:
                continue
            low, high = field["setting"]["LowerBoundValue"], field["setting"]["UpperBoundValue"]
            candidate = round(low + (high - low) * 0.25)
            colors[field["name"]] = candidate if candidate != field["value"] else min(high, candidate + 1)
        take = before["take"]
        lane = (take["max_take_number"] if take["take_number"] != take["max_take_number"] else 0) if is_v7 else (take["setting"]["UpperBoundValue"] if take["lane"] != take["setting"]["UpperBoundValue"] else take["setting"]["LowerBoundValue"])
        changed = await check.edit(sid, "performance.set", **scope, voice_colors=colors,
                                   **{"take_number" if is_v7 else "take_lane": lane})
        v.require({field["name"]: field["value"] for field in changed["voice_colors"] if field["name"] in colors} == colors, "VoiceColor readback differs")
        v.require(changed["take"]["take_number" if is_v7 else "lane"] == lane, "Take readback differs")
        if is_v7:
            _, path = await check.save(sid, "all-performance-fields")
            reopened = (await check.call("project_open", path=str(path)))["session_id"]
            try:
                v.require(await check.edit(reopened, "performance.get", **scope) == changed,
                          "Performance fields did not survive reopen")
            finally:
                await check.close(reopened)
            check.evidence("performance", {"values": changed, "vpr": str(path),
                                          "media_roundtrip": "unsupported on VOCALOID7; not exercised"})
            return
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


@v.feature("session.breath_audio", "session", "vocaloid_features", "voicebanks", "project_create", "score_compose",
           "project_edit", "project_render_part", "project_save", "project_open")
async def breath_audio(check):
    is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
    scope = {"track_index": 0, "part_index": 0}
    settings_scope = {**scope, **({"scope": "track"} if is_v7 else {})}
    report = {"product": "VOCALOID7" if is_v7 else "VOCALOID6"}
    if is_v7:
        candidates = [item for item in (await check.call("voicebanks"))["voices"]
                      if str(item["version"]).startswith("7.") and item["is_ai"]
                      and item["available_in_sequence"]]
        if not candidates:
            raise v.Blocked("An installed available V7 AI voicebank is required")
        voice = next((item for item in candidates if item["name"] == "GekiyakuV"), candidates[0])
        gaps = (48, 96, 192, 384, 768, 1536) * 2
        starts = [480]
        for gap in gaps:
            starts.append(starts[-1] + 384 + gap)
        report["fixture"] = {"voice": voice, "bpm": 120, "duration_tick": 384,
                             "start_ticks": starts, "gap_ticks": gaps}
        sid = (await check.call("project_create", title="V7 Breath effect probe", bpm=120))["session_id"]
        await check.edit(sid, "track.create", type="MidiAi", name="V7 Breath")
        await check.edit(sid, "part.create", track_index=0, start_tick=0, duration_tick=starts[-1] + 1920)
        await check.edit(sid, "voice.set", **settings_scope, ai_voice_bank_id=voice["comp_id"])
        for index, start in enumerate(starts):
            await check.edit(sid, "note.add", **scope, start_tick=start, duration_tick=384,
                             number=60 + (index % 3) * 2, lyric="あ", phonemes="a", lang_id=0)
    else:
        seed = await check.call("score_compose", output_name=check.output("breath-seed"),
                                title="Breath effect probe", bpm=120,
                                notes=[{"start": start, "duration": 0.8, "pitch": 60 + (index % 3) * 2,
                                        "lyric": "あ", "phoneme": "a", "lang_id": 0}
                                       for index, start in enumerate((0, 1, 4, 5, 8, 9, 12, 13))])
        sid = seed["native_session"]["session_id"]
    check.evidence("breath_audio", report)
    try:
        state = await check.edit(sid, "performance.get", **settings_scope)
        report["initial"] = state["breath"]
        high = state["breath"]["setting"]["UpperBoundValue"]
        low = state["breath"]["setting"]["LowerBoundValue"]
        async def render(label):
            result = await check.call("project_render_part", session_id=sid, **scope,
                                      output_name=check.output("breath-" + label, ".wav"))
            metadata, samples = v.read_audio(result["path"])
            v.require(metadata["rms"] > 1e-5, "Breath probe is silent", metadata)
            return result["path"], samples

        await check.edit(sid, "performance.set", **settings_scope, bypass={"Breath": True})
        baseline_path, baseline = await render("bypassed")
        report["baseline"] = baseline_path
        configurations = (("female-often", "Female", "Often", high),
                          ("male-often", "Male", "Often", high),
                          ("female-low", "Female", "Often", low),
                          ("female-rarely", "Female", "Rarely", high))
        primary = None
        for label, kind, mode, volume in configurations:
            actual = await check.edit(sid, "performance.set", **settings_scope, breath_mode=mode,
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
        _, rare_path = await check.save(sid, "breath-rarely")
        rare_reopened = (await check.call("project_open", path=str(rare_path)))["session_id"]
        try:
            rare_state = await check.edit(rare_reopened, "performance.get", **settings_scope)
            v.require(rare_state["breath"] == report["female-rarely"]["state"],
                      "Rarely Breath parameters changed on reopen")
            rare_audio = await check.call("project_render_part", session_id=rare_reopened, **scope,
                                          output_name=check.output("breath-rarely-reopened", ".wav"))
            _, rare_samples = v.read_audio(rare_audio["path"])
            v.require(rare_samples.shape == primary.shape, "Reopened Breath output shape changed")
            report["rarely_reopened"] = {"path": rare_audio["path"], "state": rare_state["breath"],
                "difference_from_female_often_rms": float(np.sqrt(np.mean((rare_samples - primary) ** 2)))}
        finally:
            await check.close(rare_reopened)
        v.require(report["female-rarely"]["difference_from_female_often_rms"] > 1e-5,
                  "Breath frequency had no measurable effect on the gapped phrase", report)
        await check.edit(sid, "performance.set", **settings_scope, breath_mode="Often", breath_type="Female",
                         breath_exhalation=high, bypass={"Breath": False})
        _, path = await check.save(sid, "breath-enabled")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        try:
            restored = await check.edit(reopened, "performance.get", **settings_scope)
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
