"""Native rendering and MIDI exports for extension-bearing AI projects."""
import json
import zipfile

import verify_features as v


@v.feature("preservation.output", "preservation", "score_compose", "project_open", "project_edit",
           "project_render_part", "project_export_midi", "project_audio", "project_save")
async def archive_output(check):
    seed = await check.call("score_compose", output_name=check.output("archive-output-seed"), title="Extended output", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0},
                                   {"start": 1, "duration": .5, "pitch": 64, "lyric": "い", "phoneme": "i", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    sequence["x_output"] = "root"
    sequence["tracks"][0]["x_output"] = "track"
    sequence["tracks"][0]["parts"][0]["x_output"] = "part"
    sequence["tracks"][0]["parts"][0]["notes"][0]["x_output"] = "note"
    sequence["masterTrack"]["tempo"]["events"][0]["x_output"] = "tempo"
    sequence["masterTrack"]["timeSig"]["events"][0]["x_output"] = "meter"
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    members["Extras/output-test.bin"] = b"opaque-output-resource"
    source = v.ROOT / "output" / check.output("archive-output-source")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        await check.edit(sid, "note.update", track_index=0, part_index=0, note_index=0, number=61)
        before = await check.call("project_status", session_id=sid)
        history = await check.edit(sid, "history.status")
        exported = await check.call("project_export_midi", session_id=sid, output_name=check.output("archive-output", ".mid"))
        v.require(exported["native"] and exported["session_id"] == sid, "MIDI output changed session identity", exported)
        v.require([item[0] for item in v.midi_snapshot(exported["path"])["notes"]] == [61, 64], "MIDI output omitted live edits")
        render = await check.call("project_render_part", session_id=sid, track_index=0, part_index=0,
                                  output_name=check.output("archive-output-part", ".wav"))
        v.require(render["native"] and render["session_id"] == sid, "Rendered output changed session identity", render)
        v.read_audio(render["path"])
        options = {"sample_rate": 44100, "channels": 2, "bits_per_sample": 16, "timeout_seconds": 90}
        mix = await check.audio(sid, "mixdown", output_name=check.output("archive-output-mix", ".wav"), **options)
        v.require(mix["native"] and mix["session_id"] == sid, "Mix output changed session identity", mix)
        v.read_audio(mix["path"])
        stems = await check.audio(sid, "mixdown_stems", output_prefix=check.output("archive-output-stem", ""), **options)
        v.require(stems["native"] and stems["session_id"] == sid and len(stems["stems"]) == 1 and
                  stems["stems"][0]["session_id"] == sid, "Stem output changed session identity", stems)
        v.read_audio(stems["stems"][0]["path"])
        await check.rejected("project_render_part", "track|range|exist", session_id=sid, track_index=99,
                             output_name=check.output("archive-output-invalid", ".wav"))
        v.require(await check.call("project_status", session_id=sid) == before and
                  await check.edit(sid, "history.status") == history, "Output changed source status or history")
        await check.edit(sid, "undo")
        undone, _ = await check.save(sid, "archive-output-undo")
        v.require(undone["tracks"][0]["parts"][0]["notes"][0]["number"] == 60, "Output damaged undo")
        await check.edit(sid, "redo")
        saved, path = await check.save(sid, "archive-output-redo")
        v.require(saved["x_output"] == "root" and saved["tracks"][0]["x_output"] == "track" and
                  saved["tracks"][0]["parts"][0]["x_output"] == "part" and
                  saved["tracks"][0]["parts"][0]["notes"][0]["x_output"] == "note" and
                  saved["tracks"][0]["parts"][0]["notes"][0]["number"] == 61 and
                  saved["masterTrack"]["tempo"]["events"][0]["x_output"] == "tempo" and
                  saved["masterTrack"]["timeSig"]["events"][0]["x_output"] == "meter" and
                  v.read_vpr(path)[1]["Extras/output-test.bin"] == b"opaque-output-resource",
                  "Output or history lost retained project data")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        await check.close(reopened)
        v.require(source.read_bytes() == original, "Output modified original project")
    finally:
        await check.close(sid)


if __name__ == "__main__":
    raise SystemExit(v.main())
