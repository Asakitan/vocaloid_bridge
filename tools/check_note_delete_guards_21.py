"""Verify direct-pitch deletion guards remain intact on a synthetic AI project."""
import json
import sys
import zipfile

import verify_features as v


@v.feature("preservation.note_pitch_delete_guards_21", "preservation", "score_compose", "project_open", "project_edit", "project_save")
async def note_pitch_delete_guards(check):
    seed = await check.call("score_compose", output_name=check.output("delete-guard-seed"), title="Pitch delete guard", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    try:
        await check.edit(sid, "pitch.set", track_index=0, part_index=0, note_index=0,
                         points=[{"tick": 100, "value": 60}])
        sequence, path = await check.save(sid, "delete-guard-native")
    finally:
        await check.close(sid)
    sequence["tracks"][0]["parts"][0]["notes"][0]["directPitches"][0]["x_guard21"] = {"nested": [True, None]}
    _, members = v.read_vpr(path)
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    fixture = v.ROOT / "output" / check.output("delete-guard-input")
    with zipfile.ZipFile(fixture, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = fixture.read_bytes()
    sid = (await check.call("project_open", path=str(fixture)))["session_id"]
    try:
        before, _ = await check.save(sid, "delete-guard-before")
        history = await check.edit(sid, "history.status")
        for operation, options in (("note.remove", {"track_index": 0, "part_index": 0, "note_index": 0}),
                                   ("note.clear", {"track_index": 0, "part_index": 0}),
                                   ("part.remove", {"track_index": 0, "part_index": 0}),
                                   ("track.remove", {"track_index": 0})):
            await check.rejected("project_edit", "direct pitch extension", session_id=sid, operation=operation, options=options)
            after, _ = await check.save(sid, "delete-guard-after")
            v.require(after == before and await check.edit(sid, "history.status") == history,
                      "Pitch deletion guard changed state or history", operation)
    finally:
        await check.close(sid)
    v.require(fixture.read_bytes() == original, "Pitch deletion guard changed source archive")


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "preservation.note_pitch_delete_guards_21"])
    raise SystemExit(v.main())
