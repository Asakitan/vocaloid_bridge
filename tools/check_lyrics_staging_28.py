"""Check lyric and phoneme operations do not commit unrelated staged edits."""
import sys
import verify_features as v


@v.feature("library.lyrics_staged_guard_28", "library", "score_compose", "project_open",
           "project_get", "project_items", "project_set", "project_edit", "project_library", "project_save")
async def lyrics_staged_guard(check):
    seed = await check.call("score_compose", output_name=check.output("lyrics-stage-seed"),
                            title="Lyric staging", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    sid = (await check.call("project_open", path=seed["path"]))["session_id"]
    try:
        notes_before = await check.edit(sid, "note.list", track_index=0, part_index=0)
        tempos = (await check.call("project_get", session_id=sid, member="Tempos"))["value"]
        item = (await check.call("project_items", session_id=sid, ref=tempos["$ref"]))["items"][0]
        value = (await check.call("project_get", session_id=sid, ref=item["$ref"], member="Value"))["value"]
        await check.call("project_set", session_id=sid, ref=item["$ref"], member="Value", value=value + 100)
        status = await check.call("project_status", session_id=sid)
        history = await check.edit(sid, "history.status")
        tempo = await check.edit(sid, "tempo.list")
        v.require(history["staged"] and status["dirty"], "Fixture did not stage a tempo edit")

        part = {"track_index": 0, "part_index": 0, "language_id": 0}
        for operation, options in (
            ("lyrics_apply", {**part, "note_index": 0, "lyrics": "い"}),
            ("phonemes_apply", {**part, "note_index": 0, "phonemes": "i"}),
            ("lyrics_reset", part),
            ("phonemes_reset", part),
        ):
            await check.rejected("project_library", "pending native edits", session_id=sid,
                                 operation=operation, options=options)
            v.require(await check.call("project_status", session_id=sid) == status and
                      await check.edit(sid, "history.status") == history and
                      await check.edit(sid, "tempo.list") == tempo and
                      await check.edit(sid, "note.list", track_index=0, part_index=0) == notes_before,
                      "Rejected lyric operation changed pending state", operation)

        rolled = await check.edit(sid, "history.rollback")
        v.require(rolled["rolled_back"] and not (await check.edit(sid, "history.status"))["staged"],
                  "Explicit rollback did not clear the test edit")
        result = await check.library("lyrics_apply", sid, **part, note_index=0, lyrics="い", protect=False)
        v.require(result["affected_length"] == 1 and result["notes"][0]["lyric"] == "い" and
                  result["notes"][0]["phonemes"] == "i", "Normal lyric operation failed", result)
        saved, path = await check.save(sid, "lyrics-stage-saved")
        v.require(saved["tracks"][0]["parts"][0]["notes"][0]["phoneme"] == "i",
                  "Normal lyric operation did not save")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        try:
            notes = (await check.edit(reopened, "note.list", track_index=0, part_index=0))["notes"]
            v.require(notes[0]["lyric"] == "い" and notes[0]["phonemes"] == "i",
                      "Normal lyric operation did not reopen", notes)
        finally:
            await check.close(reopened)
    finally:
        await check.close(sid)


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "library.lyrics_staged_guard_28"])
    raise SystemExit(v.main())
