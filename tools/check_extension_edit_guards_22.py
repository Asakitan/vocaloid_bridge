"""Verify reviewed track/controller editing guards remain active."""
import json
import sys
import zipfile

import verify_features as v


@v.feature("preservation.extension_edit_guards_22", "preservation", "score_compose", "project_edit",
           "project_open", "project_save")
async def extension_edit_guards(check):
    seed = await check.call("score_compose", output_name=check.output("edit-guards-seed"), title="Edit guards", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    try:
        await check.edit(sid, "controller.set", track_index=0, part_index=0, type="Dynamics",
                         points=[{"tick": 60, "value": 30}])
        sequence, path = await check.save(sid, "edit-guards-native")
    finally:
        await check.close(sid)
    _, members = v.read_vpr(path)
    cases = [
        ("track.create", {"type": "MidiAi", "name": "New AI"}),
        ("part.create", {"track_index": 0, "start_tick": 3840, "duration_tick": 960}),
        ("part.update", {"track_index": 0, "part_index": 0, "name": "Changed"}),
        ("part.move", {"track_index": 0, "part_index": 0, "start_tick": 240}),
        ("part.resize", {"track_index": 0, "part_index": 0, "duration_tick": 2400}),
        ("note.add", {"track_index": 0, "part_index": 0, "start_tick": 960, "duration_tick": 240, "number": 65}),
        ("note.update", {"track_index": 0, "part_index": 0, "note_index": 0, "number": 62}),
        ("note.batch_update", {"track_index": 0, "part_index": 0, "note_indices": [0], "transpose": 2}),
    ]
    for kind in ("track", "controller"):
        content = json.loads(json.dumps(sequence))
        track = content["tracks"][0]
        if kind == "track":
            track["volume"]["events"][0]["x_guard22"] = {"lane": "track"}
            selected = cases
            error = "track automation mutation"
        else:
            lane = next(lane for lane in track["parts"][0]["controllers"] if lane["name"] == "dynamics")
            lane["events"][0]["x_guard22"] = {"lane": "controller"}
            selected = cases[-3:]
            error = "controller extension mutation"
        fixture = v.ROOT / "output" / check.output("edit-guards-" + kind)
        data = dict(members)
        data["Project/sequence.json"] = json.dumps(content, ensure_ascii=False).encode("utf-8")
        with zipfile.ZipFile(fixture, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in data.items():
                archive.writestr(name, payload)
        original = fixture.read_bytes()
        sid = (await check.call("project_open", path=str(fixture)))["session_id"]
        try:
            before, _ = await check.save(sid, "edit-guards-before")
            history = await check.edit(sid, "history.status")
            for operation, options in selected:
                await check.rejected("project_edit", error, session_id=sid, operation=operation, options=options)
                v.require(await check.edit(sid, "history.status") == history, "Guard changed history", operation)
            after, _ = await check.save(sid, "edit-guards-after")
            v.require(after == before and fixture.read_bytes() == original, "Guard changed project or source")
        finally:
            await check.close(sid)


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "preservation.extension_edit_guards_22"])
    raise SystemExit(v.main())
