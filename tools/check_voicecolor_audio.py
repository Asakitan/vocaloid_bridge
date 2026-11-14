"""One actual-MCP, native VoiceColor parameter and bypass audio probe."""
import sys
import numpy as np
import verify_features as v

EXPECTED = {"Exciter", "Growl", "Breathiness", "Air", "Mouth", "Character", "S5Expression", "S5Air", "S5Character"}

def metrics(reference, changed, threshold):
    v.require(reference.shape == changed.shape, "Native render sample shape changed", {"baseline": reference.shape, "actual": changed.shape})
    delta = changed - reference
    active = np.maximum(np.abs(reference), np.abs(changed)) > 1e-4
    return {"frames": len(reference), "active_samples": int(np.count_nonzero(active)),
            "changed_samples_above_1_lsb16": int(np.count_nonzero(np.abs(delta) > 1 / 32768)),
            "changed_active_samples_above_1_lsb16": int(np.count_nonzero((np.abs(delta) > 1 / 32768) & active)),
            "delta_rms": float(np.sqrt(np.mean(delta ** 2))), "delta_peak": float(np.max(np.abs(delta))),
            "active_delta_rms": float(np.sqrt(np.mean(delta[active] ** 2))) if np.any(active) else 0.0,
            "detection_threshold_rms": threshold}

@v.feature("voicecolor.audio", "voicecolor", "vocaloid_features", "voicebanks", "project_create", "project_edit",
           "project_render_part", "score_compose")
async def probe(check):
    is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
    selected = {"track_index": 0, "part_index": 0}
    settings_scope = {**selected, **({"scope": "track"} if is_v7 else {})}
    if is_v7:
        candidates = [item for item in (await check.call("voicebanks"))["voices"]
                      if str(item["version"]).startswith("7.") and item["is_ai"]
                      and item["available_in_sequence"]]
        if not candidates:
            raise v.Blocked("An installed available V7 AI voicebank is required")
        voice = next((item for item in candidates if item["name"] == "GekiyakuV"), candidates[0])
        sid = (await check.call("project_create", title="V7 VoiceColor audio probe", bpm=120))["session_id"]
        await check.edit(sid, "track.create", type="MidiAi", name="V7 VoiceColor")
        await check.edit(sid, "part.create", track_index=0, start_tick=0, duration_tick=1920)
        await check.edit(sid, "voice.set", **settings_scope, ai_voice_bank_id=voice["comp_id"])
        for index, pitch in enumerate((60, 64, 67)):
            await check.edit(sid, "note.add", **selected, start_tick=index * 480, duration_tick=288,
                             number=pitch, lyric="あ", phonemes="a", lang_id=0)
    else:
        seed = await check.call("score_compose", output_name=check.output("color-seed"), title="VoiceColor audio probe", bpm=120,
            notes=[{"start": index, "duration": 0.6, "pitch": pitch, "lyric": "あ", "phoneme": "a", "lang_id": 0}
                   for index, pitch in enumerate((60, 64, 67))])
        sid = seed["native_session"]["session_id"]
    report = {"fields": {}, "errors": []}
    check.evidence("voicecolor_audio", report)
    try:
        state = await check.edit(sid, "performance.get", **settings_scope)
        fields = state.get("voice_colors") or []
        expected = EXPECTED | ({"S5Attack"} if is_v7 else set())
        v.require({field["name"] for field in fields} == expected, "Unexpected native VoiceColor field inventory", fields)
        v.require(next((x for x in state["bypass"] if x["effect"] == "VoiceColor" and x["available"]), None), "VoiceColor is not available")
        originals = {x["name"]: x["value"] for x in fields}
        await check.edit(sid, "performance.set", **settings_scope, bypass={"VoiceColor": False})

        async def render(label):
            result = await check.call("project_render_part", session_id=sid, output_name=check.output(label, ".wav"), **selected)
            metadata, samples = v.read_audio(result["path"])
            return result, metadata, samples

        base, base_meta, base_pcm = await render("color-baseline")
        repeat, repeat_meta, repeat_pcm = await render("color-control-repeat")
        control = metrics(base_pcm, repeat_pcm, 0)
        threshold = max(base_meta["rms"] * 0.01, control["delta_rms"] * 5, 1e-6)
        report.update(baseline={"path": base["path"], **base_meta}, control_repeat={"path": repeat["path"], **repeat_meta},
                      control_difference=control, detection_threshold_rms=threshold, initial_state=state)
        strongest = None
        for field in fields:
            name, initial, settings = field["name"], field["value"], field["setting"]
            lo, hi = settings["LowerBoundValue"], settings["UpperBoundValue"]
            result = report["fields"][name] = {"initial": initial, "minimum": lo, "maximum": hi, "default": settings["DefaultValue"]}
            if is_v7 and not field["applicable_to_current_track"]:
                result["status"] = "not_applicable_to_ai_track"
                continue
            if lo == hi:
                result["status"] = "no_distinct_native_value"
                continue
            target = hi if abs(hi - initial) >= abs(initial - lo) else lo
            result["target"] = target
            try:
                state = await check.edit(sid, "performance.set", **settings_scope, voice_colors={name: target}, bypass={"VoiceColor": False})
                result["readback"] = next(x["value"] for x in state["voice_colors"] if x["name"] == name)
                v.require(result["readback"] == target, "VoiceColor readback mismatch", name)
                audio, meta, pcm = await render("color-" + name)
                result.update(path=audio["path"], audio=meta, comparison=metrics(base_pcm, pcm, threshold))
                result["status"] = "audio_difference" if result["comparison"]["delta_rms"] > threshold else "no_detectable_difference"
                if strongest is None or result["comparison"]["delta_rms"] > strongest[1]:
                    strongest = (name, result["comparison"]["delta_rms"], target)
            except Exception as error:
                result.update(status="error", error=f"{type(error).__name__}: {error}")
                report["errors"].append(name)
            finally:
                await check.edit(sid, "performance.set", **settings_scope, voice_colors={name: initial})
        if strongest and strongest[1] > threshold:
            name, _, target = strongest
            try:
                await check.edit(sid, "performance.set", **settings_scope, voice_colors={name: target}, bypass={"VoiceColor": False})
                enabled, _, on_pcm = await render("color-bypass-enabled")
                await check.edit(sid, "performance.set", **settings_scope, bypass={"VoiceColor": True})
                disabled, _, off_pcm = await render("color-bypass-disabled")
                comparison = metrics(on_pcm, off_pcm, threshold)
                report["bypass"] = {"field": name, "target": target, "enabled": enabled["path"], "disabled": disabled["path"],
                                    "comparison": comparison, "status": "audio_difference" if comparison["delta_rms"] > threshold else "no_detectable_difference"}
            except Exception as error:
                report["bypass"] = {"status": "error", "error": f"{type(error).__name__}: {error}"}
                report["errors"].append("bypass")
        else:
            report["bypass"] = {"status": "unverified_no_changed_field"}
        report["original_values"] = originals
        v.require(not report["errors"], "VoiceColor operations failed", report["errors"])
    finally:
        await check.close(sid)

if __name__ == "__main__":
    if not any(argument in ("--case", "--category") for argument in sys.argv[1:]):
        sys.argv.extend(["--category", "voicecolor"])
    sys.exit(v.main())
