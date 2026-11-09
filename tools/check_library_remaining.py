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
        v.require(actual["domains"][domain]["operations"] == data["operations"], "Native dispatch differs from exposed index", domain)
        sample = data["operations"][0]["operation"]
        detail = await check.call("vocaloid_operations", domain=domain, operation=sample, include_documentation=True)
        v.require(detail["total"] == 1 and detail["domains"][domain]["documentation_text"], "Operation contract missing", sample)
    await check.rejected("vocaloid_operations", "domain", domain="absent")
    await check.rejected("vocaloid_operations", "operation", operation="absent")
    check.evidence("counts", {domain: len(data["operations"]) for domain, data in expected["domains"].items()})


@v.feature("remaining.private_styles", "remaining", "project_library", "project_edit", "project_audio", "project_save", "project_open")
async def private_styles(check):
    async with check.project(score=True) as sid:
        scope = {"track_index": 0, "part_index": 0}
        effects = await check.audio(sid, "effects", scope="catalog")
        gain = next(effect for effect in effects["effects"] if effect["name"] == "Gain")
        original_chain = await check.audio(sid, "effects", scope="part", **scope)
        ids = {effect["effect_id"] for effect in original_chain["effects"]}
        extra = next(effect for effect in effects["effects"] if effect["effect_id"] not in ids)
        await check.audio(sid, "set_effect", scope="part", action="add", effect_id=extra["effect_id"], **scope)
        captured = (await check.library("style_capture", sid, **scope, name="Private style " + check.run_id,
                                        sub_genres=["original"], colors=["warm"]))["style"]
        style_id = captured["style_id"]
        v.require(captured["audio_effect_count"] == len(ids) + 1 and captured["midi_effect_count"] > 0, "Native style capture lost effects", captured)
        try:
            updated = (await check.library("style_update", sid, style_id=style_id, name="Updated " + check.run_id,
                                          add_sub_genres=["additional"], add_colors=["bright"]))["style"]
            v.require(set(updated["sub_genres"]) == {"original", "additional"} and set(updated["colors"]) == {"warm", "bright"}, "Property update lost existing tags", updated)
            target = (await check.edit(sid, "track.create", type="MidiAi", name="Style target"))["track_index"]
            await check.edit(sid, "part.create", track_index=target, start_tick=0, duration_tick=1920)
            await check.library("style_apply", sid, style_id=style_id, track_index=target, part_index=0)
            before = await check.audio(sid, "effects", scope="part", track_index=target, part_index=0)
            _, path = await check.save(sid, "private-style")
            reopened = (await check.call("project_open", path=str(path)))["session_id"]
            try:
                after = await check.audio(reopened, "effects", scope="part", track_index=target, part_index=0)
                v.require(after["effects"] == before["effects"], "Applied private style changed after reopen")
            finally:
                await check.close(reopened)
            overwritten = (await check.library("style_capture", sid, **scope, name="Overwritten " + check.run_id,
                                              overwrite_style_id=style_id))["style"]
            v.require(overwritten["style_id"] == style_id and overwritten["name"].startswith("Overwritten"), "Explicit style overwrite changed identity")
            check.evidence("private_style", {"style_id": style_id, "captured": captured, "updated": updated, "vpr": str(path)})
        finally:
            await check.library("style_delete", sid, style_id=style_id)


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
    catalog = await check.library("singing_skill_catalog")
    v.require(catalog["skills"] and all(skill["plugin_id"] for skill in catalog["skills"]), "Native Singing Skill catalog empty")
    plugin = next(skill for skill in catalog["skills"] if skill["available"])
    async with check.project() as sid:
        track = (await check.edit(sid, "track.create", type="Midi", name="Classic Singing Skill"))["track_index"]
        await check.edit(sid, "part.create", track_index=track, start_tick=0, duration_tick=1920)
        scope = {"track_index": track, "part_index": 0}
        before = await check.library("singing_skill_get", sid, **scope)
        changed = await check.library("singing_skill_set", sid, **scope, plugin_id=plugin["plugin_id"],
                                      skill=before["skill_bounds"]["UpperBoundValue"],
                                      amount=before["amount_bounds"]["LowerBoundValue"], bypassed=False)
        v.require(changed["plugin_id"] == plugin["plugin_id"] and not changed["bypassed"], "Singing Skill parameters did not apply", changed)
        v.require(changed["skill"] == before["skill_bounds"]["UpperBoundValue"] and changed["amount"] == before["amount_bounds"]["LowerBoundValue"], "Singing Skill readback mismatch", changed)
        await check.rejected("project_library", "installed", operation="singing_skill_set", session_id=sid, options={**scope, "plugin_id": "unknown"})
        await check.library("singing_skill_set", sid, **scope, bypassed=True)
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
