"""Private style and media operations on extension-bearing projects."""
import json
import zipfile
from pathlib import Path

import verify_features as v
from check_archive_audio_transfer import make_wave


@v.feature("preservation.library_independent", "preservation", "score_compose", "project_edit",
           "project_open", "project_library", "project_save")
async def library_independent(check):
    seed = await check.call("score_compose", output_name=check.output("archive-library-seed"), title="Archive library", bpm=120,
                            notes=[{"start": 0, "duration": 0.5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    seed_id = seed["native_session"]["session_id"]
    await check.edit(seed_id, "part.duplicate", track_index=0, part_index=0, start_tick=3840)
    seq, path = await check.save(seed_id, "archive-library-native")
    await check.close(seed_id)
    _, members = v.read_vpr(path)
    seq["x_library_root"] = "root"
    seq["tracks"][0]["x_library_track"] = "track"
    seq["tracks"][0]["parts"][0]["x_library_part"] = "part"
    seq["tracks"][0]["parts"][0]["notes"][0]["x_library_note"] = "note"
    seq["masterTrack"]["tempo"]["events"][0]["x_library_tempo"] = "tempo"
    members["Project/sequence.json"] = json.dumps(seq, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("archive-library-source")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    style_id = clip_id = None
    try:
        await check.edit(sid, "note.update", track_index=0, part_index=0, note_index=0, number=61)
        before = await check.call("project_status", session_id=sid)
        history = await check.edit(sid, "history.status")
        style = (await check.library("style_capture", sid, track_index=0, part_index=0,
                                     name="Archive style " + check.run_id))["style"]
        style_id = style["style_id"]
        updated = (await check.library("style_update", sid, style_id=style_id,
                                       name="Archive updated " + check.run_id))["style"]
        v.require(updated["style_id"] == style_id and updated["name"].startswith("Archive updated"),
                  "Private style update failed")
        await check.rejected("project_library", "archive.*(extension|metadata)", session_id=sid,
                             operation="media_capture", options={"track_index": 0, "part_index": 0,
                                                                  "name": "Unsupported unknown media"})
        clip = (await check.library("media_capture", sid, track_index=0, part_index=1,
                                    name="Archive clip " + check.run_id))["clip"]
        clip_id = clip["clip_id"]
        changed = (await check.library("media_update", sid, clip_id=clip_id,
                                       name="Archive updated clip " + check.run_id))["clip"]
        v.require(changed["clip_id"] == clip_id and changed["name"].startswith("Archive updated clip"),
                  "Private media update failed")
        async with check.project() as target:
            await check.edit(target, "track.create", type="MidiAi", name="Captured media")
            await check.library("media_import", target, clip_id=clip_id, track_index=0, position_tick=0)
            notes = (await check.edit(target, "note.list", track_index=0, part_index=0))["notes"]
            v.require(len(notes) == 1 and notes[0]["number"] == 60, "Native media import changed captured notes")
        await check.library("media_delete", sid, clip_id=clip_id); clip_id = None
        await check.library("style_delete", sid, style_id=style_id); style_id = None
        v.require(await check.call("project_status", session_id=sid) == before and
                  await check.edit(sid, "history.status") == history, "Private library operations changed source history")
        await check.edit(sid, "undo")
        undone, _ = await check.save(sid, "archive-library-undo")
        v.require(undone["tracks"][0]["parts"][0]["notes"][0]["number"] == 60, "Library operations damaged undo")
        await check.edit(sid, "redo")
        saved, path = await check.save(sid, "archive-library-redo")
        v.require(saved["x_library_root"] == "root" and saved["tracks"][0]["x_library_track"] == "track" and
                  saved["tracks"][0]["parts"][0]["x_library_part"] == "part" and
                  saved["tracks"][0]["parts"][0]["notes"][0]["x_library_note"] == "note" and
                  saved["masterTrack"]["tempo"]["events"][0]["x_library_tempo"] == "tempo",
                  "Library operations lost source extensions")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        await check.close(reopened)
        v.require(source.read_bytes() == original, "Private library operation changed source VPR")
    finally:
        if clip_id is not None:
            await check.library("media_delete", sid, clip_id=clip_id)
        if style_id is not None:
            await check.library("style_delete", sid, style_id=style_id)
        await check.close(sid)


@v.feature("preservation.offline_audio", "preservation", "score_compose", "project_open", "project_audio", "project_save")
async def offline_audio(check):
    import numpy as np

    seed = await check.call("score_compose", output_name=check.output("archive-offline-seed"), title="Archive offline", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    seq, members = v.read_vpr(seed["path"])
    seq["tracks"][0]["parts"][0]["notes"][0]["x_offline"] = "note"
    members["Project/sequence.json"] = json.dumps(seq, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("archive-offline-source")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    wav = v.ROOT / "output" / check.output("archive-offline-input", ".wav")
    make_wave(wav, .03)
    wav_original = wav.read_bytes()
    _, samples = v.read_audio(wav)
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        before = await check.call("project_status", session_id=sid)
        history = await check.edit(sid, "history.status")
        output = await check.audio(sid, "process_audio", action="reverse", path=str(wav),
                                   output_name=check.output("archive-offline-reverse", ".wav"))
        actual, reversed_samples = v.read_audio(output["path"])
        v.require(output["session_id"] == sid and output["backend"] == "WOR.reverse" and
                  samples.shape == reversed_samples.shape and
                  np.allclose(reversed_samples, samples[::-1], atol=2 / 32768, rtol=0),
                  "Native reverse output differs from the source")
        await check.rejected("project_audio", "overwrite its source", session_id=sid, operation="process_audio",
                             options={"action": "reverse", "path": str(wav), "output_name": wav.name, "overwrite": True})
        v.require(await check.call("project_status", session_id=sid) == before and
                  await check.edit(sid, "history.status") == history and wav.read_bytes() == wav_original,
                  "Offline processing changed source state")
        saved, _ = await check.save(sid, "archive-offline-after")
        v.require(saved["tracks"][0]["parts"][0]["notes"][0]["x_offline"] == "note" and source.read_bytes() == original,
                  "Offline processing changed project extensions")
        check.evidence("offline_reverse", {"path": output["path"], "audio": actual})
    finally:
        await check.close(sid)


if __name__ == "__main__":
    raise SystemExit(v.main())
