"""Focused actual-MCP checks for private styles, Singing Skill and HMM media data."""
import verify_features as v

if __name__ == "__main__":
    v.CASES.clear()


@v.feature("remaining.operation_catalog", "remaining", "vocaloid_operations", "vocaloid_features")
async def operation_catalog(check):
    from generate_operation_catalog import generate
    expected = generate()
    actual = await check.call("vocaloid_operations")
    v.require(actual["total"] == sum(len(data["operations"]) for data in expected["domains"].values()), "Operation count mismatch")
    for domain, data in expected["domains"].items():
        observed = [{"operation": entry["operation"], "contract_rows": entry["contract_rows"]}
                    for entry in actual["domains"][domain]["operations"]]
        v.require(observed == data["operations"], "Native dispatch differs from exposed index", domain)
        v.require(all(entry["contract_rows"] and all(row.startswith("| `" + entry["operation"] + "` | ")
                      for row in entry["contract_rows"]) for entry in data["operations"]),
                  "A structured operation lacks its exact contract row", domain)
        sample = data["operations"][0]["operation"]
        detail = await check.call("vocaloid_operations", domain=domain, operation=sample, include_documentation=True)
        v.require(detail["total"] == 1 and detail["domains"][domain]["documentation_text"], "Operation contract missing", sample)
    for domain, operation, fields in (
        ("score", "automation.set", ("scope", "track_index", "points")),
        ("score", "note.add", ("track_index", "part_index", "start_tick", "duration_tick")),
        ("score", "controller.set", ("track_index", "part_index", "type", "points")),
        ("score", "note.batch_update", ("track_index", "part_index", "note_indices")),
        ("clipboard", "cut", ("kind", "indices", "track_index", "part_index")),
        ("clipboard", "paste", ("clipboard_id", "offset_tick")),
        ("audio", "mixdown", ("output_name", "sample_rate", "channels")),
        ("library", "lyrics_apply", ("track_index", "part_index", "note_index", "lyrics")),
    ):
        detail = await check.call("vocaloid_operations", domain=domain, operation=operation)
        rows = detail["domains"][domain]["operations"][0]["contract_rows"]
        v.require(detail["total"] == 1 and rows and all("`" + field + "`" in " ".join(rows) or
                  "`" + field + "=" in " ".join(rows) for field in fields),
                  "Targeted operation contract is missing selectors or options", operation)
    await check.rejected("vocaloid_operations", "domain", domain="absent")
    await check.rejected("vocaloid_operations", "operation", operation="absent")
    check.evidence("counts", {domain: len(data["operations"]) for domain, data in expected["domains"].items()})


@v.feature("remaining.private_styles", "remaining", "project_library", "project_edit", "project_audio", "project_save", "project_open", "vocaloid_features")
async def private_styles(check):
    is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
    async with check.project(score=True) as sid:
        scope = {"track_index": 0, "part_index": 0, **({"scope": "track"} if is_v7 else {})}
        audio_scope = {"track_index": 0, "part_index": 0, "scope": "track" if is_v7 else "part"}
        performance = await check.edit(sid, "performance.get", **scope)
        colors = {item["name"]: item["setting"]["UpperBoundValue"]
                  for item in performance["voice_colors"]
                  if item["applicable_to_current_track" if is_v7 else "applicable_to_current_part"]}
        controls = [
            ("VoiceColor", {"voice_colors": colors}),
            ("Breath", {"breath_exhalation": performance["breath"]["setting"]["UpperBoundValue"]}),
            ("RobotVoice", {"robot_mode": performance["robot"]["mode"]}),
        ]
        if not is_v7:
            controls.append(("Take", {"take_lane": performance["take"]["setting"]["UpperBoundValue"]}))
        for effect, fields in controls:
            disabled = await check.edit(sid, "performance.set", **scope, **fields, bypass={effect: True})
            v.require(next(item["bypassed"] for item in disabled["bypass"] if item["effect"] == effect),
                      "Parameter edit ignored explicit bypass", effect)
            enabled = await check.edit(sid, "performance.set", **scope, **fields)
            v.require(not next(item["bypassed"] for item in enabled["bypass"] if item["effect"] == effect),
                      "Parameter edit left its effect bypassed", effect)
        expected_performance = await check.edit(sid, "performance.get", **scope)
        effects = await check.audio(sid, "effects", scope="catalog")
        gain = next(effect for effect in effects["effects"] if effect["name"] == "Gain")
        original_chain = await check.audio(sid, "effects", **audio_scope)
        ids = {effect["effect_id"] for effect in original_chain["effects"]}
        extra = next(effect for effect in effects["effects"] if effect["effect_id"] not in ids)
        await check.audio(sid, "set_effect", action="add", effect_id=extra["effect_id"], **audio_scope)
        captured = (await check.library("style_capture", sid, **scope, name="Private style " + check.run_id,
                                        sub_genres=["original"], colors=["warm"]))["style"]
        style_id = captured["style_id"]
        try:
            v.require(captured["audio_effect_count"] == len(ids) + 1 and captured["midi_effect_count"] > 0, "Native style capture lost effects", captured)
            source_sequence, source_path = await check.save(sid, "captured-style-source")
            source_linked = (v.contains_atom(source_sequence["tracks"][0], style_id)
                             and v.contains_atom(source_sequence["tracks"][0], captured["name"]))
            color_enabled = not next(item["bypassed"] for item in expected_performance["bypass"]
                                     if item["effect"] == "VoiceColor")
            check.evidence("authoring", {"source_linked": source_linked, "voice_color_enabled": color_enabled,
                                         "source_vpr": str(source_path)})
            v.require(source_linked and color_enabled,
                      "Style capture did not link its source or parameter editing left the effect bypassed",
                      {"source_linked": source_linked, "voice_color_enabled": color_enabled})
            updated = (await check.library("style_update", sid, style_id=style_id, name="Updated " + check.run_id,
                                          add_sub_genres=["additional"], add_colors=["bright"]))["style"]
            v.require(set(updated["sub_genres"]) == {"original", "additional"} and set(updated["colors"]) == {"warm", "bright"}, "Property update lost existing tags", updated)
            target = (await check.edit(sid, "track.create", type="MidiAi", name="Style target"))["track_index"]
            await check.edit(sid, "part.create", track_index=target, start_tick=0, duration_tick=1920)
            target_scope = {**scope, "track_index": target}
            target_audio_scope = {**audio_scope, "track_index": target}
            if is_v7:
                source_voice = await check.edit(sid, "voice.get", **scope)
                await check.edit(sid, "voice.set", **target_scope, ai_voice_bank_id=source_voice["ai_voice_bank_id"])
            target_performance = await check.edit(sid, "performance.get", **target_scope)
            target_audio = await check.audio(sid, "effects", **target_audio_scope)
            await check.library("style_apply", sid, style_id=style_id, **target_scope)
            applied_performance = await check.edit(sid, "performance.get", **target_scope)
            fields = ("robot", "breath", "voice_colors", "bypass") if is_v7 else ("robot", "breath", "take", "voice_colors", "bypass")
            for field in fields:
                v.require(applied_performance[field] == expected_performance[field],
                          "Applied private style lost " + field,
                          {"expected": expected_performance[field], "actual": applied_performance[field]})
            before = await check.audio(sid, "effects", **target_audio_scope)
            await check.edit(sid, "undo")
            v.require(await check.edit(sid, "performance.get", **target_scope) == target_performance,
                      "Style undo did not restore all MIDI parameters in one step")
            undone_audio = await check.audio(sid, "effects", **target_audio_scope)
            v.require(undone_audio["effects"] == target_audio["effects"], "Style undo did not restore the audio chain")
            await check.edit(sid, "redo")
            v.require(await check.edit(sid, "performance.get", **target_scope) == applied_performance,
                      "Style redo did not restore MIDI parameters")
            sequence, path = await check.save(sid, "private-style")
            v.require(v.contains_atom(sequence["tracks"][target], style_id)
                      and v.contains_atom(sequence["tracks"][target], updated["name"]),
                      "Saved VPR lost the applied style identity", sequence["tracks"][target])
            reopened = (await check.call("project_open", path=str(path)))["session_id"]
            try:
                after = await check.audio(reopened, "effects", **target_audio_scope)
                v.require(after["effects"] == before["effects"], "Applied private style changed after reopen")
                reopened_performance = await check.edit(reopened, "performance.get", **target_scope)
                for field in fields:
                    v.require(reopened_performance[field] == applied_performance[field],
                              "Saved private style lost " + field, reopened_performance[field])
            finally:
                await check.close(reopened)
            overwritten = (await check.library("style_capture", sid, **scope, name="Overwritten " + check.run_id,
                                              overwrite_style_id=style_id))["style"]
            v.require(overwritten["style_id"] == style_id and overwritten["name"].startswith("Overwritten"), "Explicit style overwrite changed identity")
            check.evidence("private_style", {"style_id": style_id, "captured": captured, "updated": updated, "vpr": str(path)})
        finally:
            async with check.project() as cleanup:
                await check.library("style_delete", cleanup, style_id=style_id)


@v.feature("remaining.note_skill_media", "remaining", "project_library", "project_edit", "project_save", "project_open")
async def note_skill_media(check):
    async with check.project(score=True) as sid:
        scope = {"track_index": 0, "part_index": 0, "note_index": 0}
        changed = await check.library("note_skill_set", sid, **scope, duration_tick=120, pre_weight=42, post_weight=87)
        v.require(changed == {"duration_tick": 120, "pre_weight": 42, "post_weight": 87}, "HMM weights did not change", changed)
        check.evidence("source_after_set", await check.library("note_skill_get", sid, **scope))
        captured = (await check.library("media_capture", sid, track_index=0, part_index=0, name="HMM " + check.run_id))["clip"]
        import json
        from pathlib import Path
        check.evidence("captured_clip", json.loads(Path(captured["path"]).read_text(encoding="utf-8")))
        check.evidence("source_after_capture", await check.library("note_skill_get", sid, **scope))
        try:
            track = (await check.edit(sid, "track.create", type="MidiAi", name="HMM target"))["track_index"]
            await check.library("media_import", sid, clip_id=captured["clip_id"], track_index=track, position_tick=0)
            destination = {**scope, "track_index": track}
            v.require(await check.library("note_skill_get", sid, **destination) == changed, "Media import lost HMM weights")
            _, path = await check.save(sid, "note-skill")
            reopened = (await check.call("project_open", path=str(path)))["session_id"]
            try:
                v.require(await check.library("note_skill_get", reopened, **destination) == changed, "Save/reopen lost HMM weights")
                reset = await check.library("note_skill_reset", reopened, **destination)
                v.require(reset["pre_weight"] == 64 and reset["post_weight"] == 64, "Native HMM reset failed", reset)
            finally:
                await check.close(reopened)
            check.evidence("weights", {"changed": changed, "vpr": str(path)})
        finally:
            await check.library("media_delete", sid, clip_id=captured["clip_id"])


@v.feature("remaining.singing_skill", "remaining", "project_library", "project_edit", "project_save", "project_open")
async def singing_skill(check):
    is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
    catalog = await check.library("singing_skill_catalog")
    v.require(catalog["skills"] and all(skill["plugin_id"] for skill in catalog["skills"]), "Native Singing Skill catalog empty")
    plugin = next((skill for skill in catalog["skills"] if skill["available"]), None)
    if plugin is None:
        raise v.Blocked("No installed Singing Skill plugin is available")
    async with check.project() as sid:
        track = (await check.edit(sid, "track.create", type="Midi", name="Classic Singing Skill"))["track_index"]
        await check.edit(sid, "part.create", track_index=track, start_tick=0, duration_tick=1920)
        scope = {"track_index": track, "part_index": 0, "scope": "track" if is_v7 else "part"}
        before = await check.library("singing_skill_get", sid, **scope)
        changed = await check.library("singing_skill_set", sid, **scope, plugin_id=plugin["plugin_id"],
                                      skill=before["skill_bounds"]["UpperBoundValue"],
                                      amount=before["amount_bounds"]["LowerBoundValue"], bypassed=False)
        v.require(changed["plugin_id"] == plugin["plugin_id"] and not changed["bypassed"], "Singing Skill parameters did not apply", changed)
        v.require(changed["skill"] == before["skill_bounds"]["UpperBoundValue"] and changed["amount"] == before["amount_bounds"]["LowerBoundValue"], "Singing Skill readback mismatch", changed)
        await check.rejected("project_library", "installed", operation="singing_skill_set", session_id=sid, options={**scope, "plugin_id": "unknown"})
        await check.library("singing_skill_set", sid, **scope, bypassed=True)
        voices = (await check.call("voicebanks"))["voices"]
        if not any(voice["kind"] == "Dse" and voice["available_in_sequence"] for voice in voices):
            check.evidence("singing_skill", {"catalog": catalog, "parameters": changed,
                                             "save_reopen": "blocked: missing_classic_bank"})
            raise v.Blocked("missing_classic_bank: Singing Skill parameters read back, but classic save/reopen requires an installed available Dse voicebank")
        _, path = await check.save(sid, "singing-skill")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        try:
            saved = await check.library("singing_skill_get", reopened, **scope)
            v.require(saved["plugin_id"] == changed["plugin_id"] and saved["skill"] == changed["skill"] and saved["amount"] == changed["amount"], "Singing Skill parameters did not survive reopen", saved)
        finally:
            await check.close(reopened)
        check.evidence("singing_skill", {"catalog": catalog, "parameters": changed, "vpr": str(path), "render_requires_installed_classic_voice": True})


if __name__ == "__main__":
    raise SystemExit(v.main())
