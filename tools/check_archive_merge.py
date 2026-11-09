"""Focused synthetic acceptance for archive-aware project merge."""
import json
import zipfile
import verify_features as v


@v.feature("preservation.merge_transfer", "preservation", "score_compose", "project_open",
           "project_merge", "project_edit", "project_save")
async def merge_transfer(check):
    seed = await check.call("score_compose", output_name=check.output("merge-seed"), title="Merge fixture", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0},
                                   {"start": 1, "duration": .5, "pitch": 62, "lyric": "い", "phoneme": "i", "lang_id": 0}])
    seed_id = seed["native_session"]["session_id"]
    await check.edit(seed_id, "tempo.set", start_tick=1920, bpm=95)
    sequence, seed_path = await check.save(seed_id, "merge-source-tempo")
    await check.close(seed_id)
    _, members = v.read_vpr(seed_path)
    track = sequence["tracks"][0]; part = track["parts"][0]; position = part["pos"]
    track["x_merge"] = "track"; part["x_merge"] = "part"
    for i, note in enumerate(part["notes"]): note["x_merge"] = "note-" + str(i)
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("merge-source")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    for extended_target in (False, True):
        target = (await check.call("project_open", path=str(source)))["session_id"] if extended_target else (await check.call("project_create", title="Merge target"))["session_id"]
        try:
            await check.call("project_merge", session_id=target, path=str(source), offset_tick=960,
                             include_tracks=True, include_tempo=False)
            def verify(value):
                v.require(len(value["tracks"]) == (2 if extended_target else 1), "Merged track count changed")
                imported = value["tracks"][-1]; copied_part = imported["parts"][0]
                v.require(imported["x_merge"] == "track" and copied_part["x_merge"] == "part", "Parent extension lost")
                v.require(copied_part["pos"] == position + 960, "Merge offset changed")
                v.require([n["x_merge"] for n in copied_part["notes"]] == ["note-0", "note-1"], "Note extensions mismatched")
            saved, _ = await check.save(target, "merge-transfer"); verify(saved)
            await check.edit(target, "undo")
            undone, _ = await check.save(target, "merge-undo")
            v.require(len(undone.get("tracks", [])) == (1 if extended_target else 0), "Merge undo failed")
            await check.edit(target, "redo")
            redone, _ = await check.save(target, "merge-redo"); verify(redone)
        finally:
            await check.close(target)
    target = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        before = await check.edit(target, "tempo.list")
        await check.call("project_merge", session_id=target, path=str(source), offset_tick=0,
                         include_tracks=False, include_tempo=True, replace_tempo=True)
        after = await check.edit(target, "tempo.list")
        v.require(after["tempos"] == before["tempos"], "Tempo-only merge changed the source map", after)
        saved, _ = await check.save(target, "merge-tempo-only")
        v.require(saved["tracks"][0]["x_merge"] == "track", "Tempo merge lost target metadata")
    finally:
        await check.close(target)
    guarded = json.loads(json.dumps(sequence)); guarded["x_merge_root"] = "unknown-root"
    guarded_members = dict(members)
    guarded_members["Project/sequence.json"] = json.dumps(guarded, ensure_ascii=False).encode("utf-8")
    guarded_path = v.ROOT / "output" / check.output("merge-guarded-source")
    with zipfile.ZipFile(guarded_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in guarded_members.items(): archive.writestr(name, payload)
    guarded_original = guarded_path.read_bytes()
    async with check.project() as target:
        before = await check.call("project_status", session_id=target)
        await check.rejected("project_merge", "source root or master extensions",
                             session_id=target, path=str(guarded_path), include_tracks=True)
        v.require(await check.call("project_status", session_id=target) == before,
                  "Rejected merge modified the target")
    v.require(guarded_path.read_bytes() == guarded_original, "Rejected merge changed its source")
    v.require(source.read_bytes() == original, "Source VPR changed")


if __name__ == "__main__":
    raise SystemExit(v.main())
