"""Focused V7 screenshot controls and opaque-project roundtrip via real MCP."""
from __future__ import annotations

import json
import zipfile

import verify_features as verification


SCOPE = {"scope": "track", "track_index": 0}
PART = {"track_index": 0, "part_index": 0}
MARKER = "x_v7_controls_46"
RESOURCE = "Project/bridge-probe/v7-controls.bin"
RESOURCE_BYTES = b"v7-control-preservation\x00\x01"


@verification.feature("v7.controls_46", "v7", "voicebanks", "score_compose", "project_edit",
                      "project_library", "project_open", "project_save", "project_render_part",
                      "project_inspect", "project_ai_adjust", "vocaloid_features")
async def controls(check):
    banks = (await check.call("voicebanks"))["voices"]
    candidates = [bank for bank in banks if str(bank.get("version", "")).startswith("7.")
                  and bank.get("available_in_sequence") and bank.get("is_ai")]
    if not candidates:
        raise verification.Blocked("An installed available V7 AI voicebank is required")
    voice = next((bank for bank in candidates if "gekiyaku" in bank["name"].lower()), candidates[0])
    check.evidence("voicebank", voice)
    seed = await check.call("score_compose", output_name=check.output("v7-controls-seed"),
                            title="V7 controls", bpm=132,
                            notes=[{"start": index * 2, "duration": 1, "pitch": pitch,
                                    "lyric": "\u3042", "phoneme": "a", "lang_id": 0}
                                   for index, pitch in enumerate((60, 64, 67))])
    identifier = seed["native_session"]["session_id"]
    await check.edit(identifier, "voice.set", **SCOPE, ai_voice_bank_id=voice["comp_id"])
    styles = await check.library("style_list", identifier, query=voice["name"])
    default_style = next((style for style in styles["styles"] if "Default" in style["name"]), None)
    verification.require(default_style is not None, "The V7 singer has no discoverable default style", styles)
    applied_style = await check.library("style_apply", identifier, **SCOPE,
                                        style_id=default_style["style_id"], include_audio=True)
    check.evidence("style", applied_style)
    sequence, seed_path = await check.save(identifier, "v7-controls-native")
    await check.close(identifier)
    _, members = verification.read_vpr(seed_path)
    sequence[MARKER] = "root"
    sequence["tracks"][0][MARKER] = "track"
    sequence["tracks"][0]["parts"][0][MARKER] = "part"
    sequence["tracks"][0]["parts"][0]["notes"][0][MARKER] = "note"
    sequence["voices"][0][MARKER] = "voice"
    effect = sequence["tracks"][0]["midiEffects"][0]
    effect[MARKER] = "effect"
    if effect.get("parameters"):
        effect["parameters"][0][MARKER] = "parameter"
    members["Project/sequence.json"] = json.dumps(sequence).encode("utf-8")
    members[RESOURCE] = RESOURCE_BYTES
    source = verification.ROOT / "output" / check.output("v7-controls-extended")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    original = source.read_bytes()
    identifier = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        catalog = await check.call("vocaloid_features")
        verification.require(catalog["product"] == "VOCALOID7" and not catalog["matrix_applies_to_selected_product"],
                              "V6 evidence was misattributed to V7")
        for feature in ("voice_type", "attack", "volume", "time_signature", "ai_adjust"):
            inspected = await check.call("project_inspect", session_id=identifier, feature=feature, **PART)
            verification.require(inspected["read_only"] and inspected["readbacks"],
                                  "Feature inspection did not return native values", feature)
        voice_state = await check.edit(identifier, "voice.get", **SCOPE)
        verification.require(voice_state["voice_type_supported"] and voice_state["voice_types"],
                              "V7 voice types are not discoverable", voice_state)
        selected_type = voice_state["voice_types"][-1]["voice_type_id"]
        changed_voice = await check.edit(identifier, "voice.set", **SCOPE, voice_type_id=selected_type)
        verification.require(changed_voice["voice_type_id"] == selected_type, "Voice Type change failed")
        initial = await check.edit(identifier, "performance.get", **SCOPE)
        check.evidence("initial_performance", initial)
        color_rows = [row for row in initial["voice_colors"] if row["applicable_to_current_track"]]
        verification.require({"S5Expression", "S5Air", "S5Character", "S5Attack"}.issubset(
            {row["name"] for row in color_rows}), "V7 screenshot colors are missing", color_rows)
        colors = {}
        for row in color_rows:
            lower = row["setting"]["LowerBoundValue"]
            upper = row["setting"]["UpperBoundValue"]
            colors[row["name"]] = lower + (upper - lower) // 3
        updates = {"voice_colors": colors, "robot_mode": initial["robot"]["modes"][0],
                   "breath_mode": initial["breath"]["modes"][-1],
                   "breath_exhalation": initial["breath"]["setting"]["UpperBoundValue"],
                   "take_number": initial["take"]["default_take_number"],
                   "bypass": {"RobotVoice": True, "Breath": False, "VoiceColor": False}}
        changed = await check.edit(identifier, "performance.set", **SCOPE, **updates)
        verification.require({row["name"]: row["value"] for row in changed["voice_colors"]
                              if row["name"] in colors} == colors, "V7 color readback mismatch")
        await check.edit(identifier, "undo")
        verification.require(await check.edit(identifier, "performance.get", **SCOPE) == initial,
                              "Performance undo did not restore state")
        await check.edit(identifier, "redo")
        verification.require(await check.edit(identifier, "performance.get", **SCOPE) == changed,
                              "Performance redo did not restore state")
        await check.edit(identifier, "batch.run", operations=[
            {"operation": "note.update", "options": {**PART, "note_index": 0, "number": 62}},
            {"operation": "performance.set", "options": {**SCOPE, "voice_colors": colors}},
        ])
        initial_pitches = [await check.edit(identifier, "pitch.list", **PART, note_index=index) for index in (0, 1)]
        verification.require(all(not pitches["points"] for pitches in initial_pitches),
                              "The AI fixture unexpectedly contains direct pitches")
        automatic = await check.call("project_ai_adjust", session_id=identifier, **PART)
        verification.require(automatic["generation"]["result"]["generated"], "Native AI generation did not complete")
        verification.require(automatic["generation"]["result"]["status"]["rendered_score_valid"],
                              "AI generation returned no valid rendered score")
        check.evidence("ai_generation", automatic)
        vibrato = await check.edit(identifier, "vibrato.set", **PART, note_index=0, reset_ai_defaults=True)
        verification.require(vibrato["curve_model"] == "AiEstimatedBase", "Native AI vibrato reset failed", vibrato)
        preserved = await check.call("project_ai_adjust", session_id=identifier, **PART,
                                     preserve_pitch=True, note_indices=[0, 1])
        capture = preserved["generation"]["result"]["preservation"]
        verification.require(capture["atomic"] and len(capture["notes"]) == 2
                              and all(note["point_count"] > 0 for note in capture["notes"]),
                              "Native AI did not preserve both notes", capture)
        captured_pitches = [await check.edit(identifier, "pitch.list", **PART, note_index=index) for index in (0, 1)]
        await check.edit(identifier, "undo")
        verification.require([await check.edit(identifier, "pitch.list", **PART, note_index=index) for index in (0, 1)]
                              == initial_pitches, "AI pitch preservation did not undo atomically")
        await check.edit(identifier, "redo")
        await check.rejected("project_ai_adjust", "already has direct pitches", session_id=identifier,
                             **PART, preserve_pitch=True, note_indices=[0, 1])
        verification.require([await check.edit(identifier, "pitch.list", **PART, note_index=index) for index in (0, 1)]
                              == captured_pitches, "Rejected AI overwrite changed pitch data")
        check.evidence("ai_preservation", preserved)
        saved_sequence, saved_path = await check.save(identifier, "v7-controls-edited")
        _, saved_members = verification.read_vpr(saved_path)
        verification.require(saved_sequence[MARKER] == "root"
                              and saved_sequence["tracks"][0][MARKER] == "track"
                              and saved_sequence["tracks"][0]["parts"][0][MARKER] == "part"
                              and saved_sequence["tracks"][0]["parts"][0]["notes"][0][MARKER] == "note"
                              and saved_sequence["voices"][0][MARKER] == "voice"
                              and saved_sequence["tracks"][0]["midiEffects"][0][MARKER] == "effect"
                              and saved_members[RESOURCE] == RESOURCE_BYTES,
                              "V7 edits lost opaque project data")
        if effect.get("parameters"):
            verification.require(saved_sequence["tracks"][0]["midiEffects"][0]["parameters"][0][MARKER]
                                  == "parameter", "V7 effect parameter metadata was lost")
        reopened = (await check.call("project_open", path=str(saved_path)))["session_id"]
        try:
            verification.require((await check.edit(reopened, "voice.get", **SCOPE))["voice_type_id"] == selected_type,
                                  "Voice Type did not survive save/reopen")
            verification.require(await check.edit(reopened, "performance.get", **SCOPE) == changed,
                                  "V7 performance did not survive save/reopen")
            verification.require((await check.edit(reopened, "note.list", **PART))["notes"][0]["number"] == 62,
                                  "V7 note edit did not survive save/reopen")
            verification.require([await check.edit(reopened, "pitch.list", **PART, note_index=index) for index in (0, 1)]
                                  == captured_pitches, "AI pitch preservation did not survive save/reopen")
            rendered = await check.call("project_render_part", session_id=reopened, **PART,
                                        output_name=check.output("v7-controls-render", ".wav"))
            verification.require(rendered["audio"]["peak"] > 0 and rendered["audio"]["frames"] > 0,
                                  "V7 edited project produced no audio")
            check.evidence("render", rendered)
        finally:
            await check.close(reopened)
        verification.require(source.read_bytes() == original, "Source project was modified")
        check.evidence("roundtrip", {"source": str(source), "saved": str(saved_path), "performance": changed})
    finally:
        await check.close(identifier)


if __name__ == "__main__":
    raise SystemExit(verification.main())