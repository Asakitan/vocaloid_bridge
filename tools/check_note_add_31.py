"""Focused native AI note.add bootstrap, coverage and transaction regression."""
import sys
import verify_features as v


@v.feature("score.note_add_31", "score", "project_create", "voicebanks", "project_edit", "project_save", "project_open")
async def note_add(check):
    voices = (await check.call("voicebanks"))["voices"]
    voice = next(item for item in voices if item["name"] == "asa" and item["kind"] == "Dnn")
    is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
    sid = (await check.call("project_create", title="Native note bootstrap", bpm=120))["session_id"]
    scope = {"track_index": 0, "part_index": 0}
    expected = [("い", "i", 0), ("cat", "kh { t", 1), ("ni", "n i", 4)]
    try:
        await check.edit(sid, "track.create", name="AI")
        for index, (lyric, phoneme, language) in enumerate(expected):
            await check.edit(sid, "part.create", track_index=0, start_tick=index * 3840, duration_tick=1920, name=str(index))
            if not is_v7 or index == 0:
                await check.edit(sid, "voice.set", track_index=0, part_index=index, ai_voice_bank_id=voice["comp_id"],
                                 **({"scope": "track"} if is_v7 else {}))
            options = {"track_index": 0, "part_index": index, "start_tick": 0, "duration_tick": 240,
                       "number": 60, "velocity": 72, "lyric": lyric, "expression": {"Accent": 37}}
            if index:
                options["lang_id"] = language
            inserted = await check.edit(sid, "note.add", **options)
            v.require((inserted["lyric"], inserted["phonemes"], inserted["lang_id"]) == (lyric, phoneme, language)
                      and inserted["velocity"] == 72 and inserted["expression"]["Accent"] == 37,
                      "First note did not resolve using the assigned voice", inserted)
        await check.edit(sid, "note.add", **scope, start_tick=960, duration_tick=240, number=64,
                         lyric="あ", phonemes="a", lang_id=0)
        await check.save(sid, "note-add-before-failure")
        before = await check.edit(sid, "note.list", **scope)
        history = await check.edit(sid, "history.status")
        status = await check.call("project_status", session_id=sid)
        for lyric, language in (("こんにちは", 0), ("ni3", 4)):
            await check.rejected("project_edit", "G2PA", session_id=sid, operation="note.add", options={
                **scope, "start_tick": 480, "duration_tick": 240, "number": 62, "lyric": lyric, "lang_id": language})
            v.require(await check.edit(sid, "note.list", **scope) == before
                      and await check.edit(sid, "history.status") == history
                      and await check.call("project_status", session_id=sid) == status,
                      "Rejected automatic insertion changed notes/history/state", lyric)
        default = await check.edit(sid, "note.add", **scope, start_tick=1440, duration_tick=240, number=65)
        v.require((default["lyric"], default["phonemes"], default["lang_id"]) == ("あ", "a", 0),
                  "Omitted lyric did not use the native language default", default)
        after = await check.edit(sid, "note.list", **scope)
        await check.edit(sid, "undo")
        v.require(await check.edit(sid, "note.list", **scope) == before, "Automatic insertion was not one undo step")
        await check.edit(sid, "redo")
        v.require(await check.edit(sid, "note.list", **scope) == after, "Redo did not restore the inserted note")
        _, path = await check.save(sid, "note-add-complete")
    finally:
        await check.close(sid)
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    try:
        for index, target in enumerate(expected):
            loaded = (await check.edit(reopened, "note.list", track_index=0, part_index=index))["notes"][0]
            v.require((loaded["lyric"], loaded["phonemes"], loaded["lang_id"]) == target,
                      "Saved automatic note did not reopen", loaded)
    finally:
        await check.close(reopened)


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "score.note_add_31"])
    raise SystemExit(v.main())
