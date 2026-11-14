"""Private style and media operations on extension-bearing projects."""
import json
import zipfile
from pathlib import Path

import verify_features as v
from check_archive_audio_transfer import make_wave


@v.feature("preservation.library_independent", "preservation", "score_compose", "project_edit",
           "project_open", "project_library", "project_save")
async def library_independent(check):
    product = (await check.call("vocaloid_features"))["product"]
    is_v7 = product == "VOCALOID7"
    style_scope = {"scope": "track", "track_index": 0} if is_v7 else {"track_index": 0, "part_index": 0}
    check.evidence("library_scope", {"product": product, "style_scope": style_scope, "media_supported": not is_v7})
    def style_owner(sequence):
        return sequence["tracks"][0] if is_v7 else sequence["tracks"][0]["parts"][0]

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
    seq["tracks"][0]["parts"][0]["audioEffects"][0]["x_library_effect"] = "audio"
    seq["tracks"][0]["parts"][0]["midiEffects"][0]["x_library_effect"] = "midi"
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
        style = (await check.library("style_capture", sid, **style_scope,
                                     name="Archive style " + check.run_id))["style"]
        style_id = style["style_id"]
        captured, _ = await check.save(sid, "archive-style-captured")
        v.require(v.contains_atom(style_owner(captured), style_id),
              "Extended source did not retain the captured style identity")
        updated = (await check.library("style_update", sid, style_id=style_id,
                                       name="Archive updated " + check.run_id))["style"]
        v.require(updated["style_id"] == style_id and updated["name"].startswith("Archive updated"),
                  "Private style update failed")
        await check.library("style_apply", sid, style_id=style_id, **style_scope)
        applied, _ = await check.save(sid, "archive-style-applied")
        v.require(v.contains_atom(style_owner(applied), updated["name"]),
              "Extended source did not retain the applied style name")
        before = await check.call("project_status", session_id=sid)
        history = await check.edit(sid, "history.status")
        if is_v7:
            await check.rejected("project_library", "VOCALOID7.*media|VOCALOID7.*VMM|not supported",
                                 session_id=sid, operation="media_capture",
                                 options={"track_index": 0, "part_index": 0, "name": "Archive V7 media"})
        else:
            extended = (await check.library("media_capture", sid, track_index=0, part_index=0,
                                            name="Archive extended clip " + check.run_id))["clip"]
            clip_id = extended["clip_id"]
            await check.library("media_delete", sid, clip_id=clip_id); clip_id = None
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
        undo_style, _ = await check.save(sid, "archive-style-undo")
        v.require(undo_style["tracks"] == captured["tracks"],
              "Style undo did not restore extended MIDI/audio state in one step")
        await check.edit(sid, "undo")
        undo_capture, _ = await check.save(sid, "archive-style-capture-undo")
        v.require(not v.contains_atom(style_owner(undo_capture), style["style_id"])
              and undo_capture["tracks"][0]["parts"][0]["notes"][0]["number"] == 61,
              "Style capture undo did not restore its source identity independently")
        await check.edit(sid, "undo")
        undone, _ = await check.save(sid, "archive-library-undo")
        v.require(undone["tracks"][0]["parts"][0]["notes"][0]["number"] == 60, "Library operations damaged undo")
        for step in range(3):
            await check.edit(sid, "redo")
        saved, path = await check.save(sid, "archive-library-redo")
        v.require(saved["x_library_root"] == "root" and saved["tracks"][0]["x_library_track"] == "track" and
                  saved["tracks"][0]["parts"][0]["x_library_part"] == "part" and
                  saved["tracks"][0]["parts"][0]["notes"][0]["x_library_note"] == "note" and
                  saved["tracks"][0]["parts"][0]["audioEffects"][0]["x_library_effect"] == "audio" and
                  saved["tracks"][0]["parts"][0]["midiEffects"][0]["x_library_effect"] == "midi" and
                  saved["masterTrack"]["tempo"]["events"][0]["x_library_tempo"] == "tempo",
                  "Library operations lost source extensions")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        restored, _ = await check.save(reopened, "archive-library-reopen")
        v.require(restored == saved, "Library reopen changed extended project")
        await check.close(reopened)
        v.require(source.read_bytes() == original, "Private library operation changed source VPR")
    finally:
        if clip_id is not None:
            await check.library("media_delete", sid, clip_id=clip_id)
        if style_id is not None:
            await check.library("style_delete", sid, style_id=style_id)
        await check.close(sid)


@v.feature("preservation.offline_audio", "preservation", "score_compose", "project_open", "project_audio", "project_save", "vocaloid_features")
async def offline_audio(check):
    import numpy as np

    is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
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
        output = await check.audio(sid, "process_audio", expected_native=not is_v7, action="reverse", path=str(wav),
                                   output_name=check.output("archive-offline-reverse", ".wav"))
        actual, reversed_samples = v.read_audio(output["path"])
        expected_backend = "bridge.pcm_frame_reverse" if is_v7 else "WOR.reverse"
        v.require(output["session_id"] == sid and output["backend"] == expected_backend and
                  samples.shape == reversed_samples.shape and
                  np.allclose(reversed_samples, samples[::-1], atol=2 / 32768, rtol=0),
              "Reverse output differs from the source")
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
