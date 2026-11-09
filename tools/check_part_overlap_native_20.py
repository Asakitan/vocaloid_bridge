"""Observe native cross-track part movement into an occupied destination."""
import sys
import verify_features as v


@v.feature("preservation.part_overlap_native_20", "preservation", "score_compose", "project_edit", "project_save")
async def part_overlap_native_20(check):
    seed = await check.call("score_compose", output_name=check.output("overlap-seed"), title="Overlap probe", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    try:
        await check.edit(sid, "track.duplicate", track_index=0, name="Other")
        before, _ = await check.save(sid, "overlap-before")
        error = None
        try:
            result = await check.edit(sid, "part.move", track_index=0, part_index=0, to_track_index=1, start_tick=0)
        except v.ToolFailure as exc:
            error = str(exc)
            result = None
        after, _ = await check.save(sid, "overlap-after")
        check.evidence("overlap", {"error": error, "result": result,
                                   "before_parts": [len(t.get("parts", [])) for t in before["tracks"]],
                                   "after_parts": [len(t.get("parts", [])) for t in after["tracks"]]})
        if error:
            v.require(after == before, "Rejected occupied move changed the project")
        else:
            await check.edit(sid, "undo")
            undone, _ = await check.save(sid, "overlap-undo")
            v.require(undone == before, "Accepted occupied move did not undo")
    finally:
        await check.close(sid)


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "preservation.part_overlap_native_20"])
    raise SystemExit(v.main())
