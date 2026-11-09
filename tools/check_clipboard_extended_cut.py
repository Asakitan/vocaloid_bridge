"""Extended-data clipboard cut and history against private AI fixtures."""
import json
import zipfile
import verify_features as v


@v.feature("preservation.clipboard_cut", "preservation", "score_compose", "project_open",
           "project_clipboard", "project_edit", "project_save")
async def clipboard_cut(check):
    seed = await check.call("score_compose", output_name=check.output("extended-cut-seed"),
                            title="Extended cut", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0},
                                   {"start": 1, "duration": .5, "pitch": 62, "lyric": "い", "phoneme": "i", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    track = sequence["tracks"][0]; part = track["parts"][0]
    track["x_cut"] = "track"; part["x_cut"] = "part"
    for i, note in enumerate(part["notes"]): note["x_cut"] = f"note-{i}"
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    path = v.ROOT / "output" / check.output("extended-cut-input")
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items(): archive.writestr(name, data)
    original = path.read_bytes(); clips = []
    try:
        source = (await check.call("project_open", path=str(path)))["session_id"]
        clip = (await check.call("project_clipboard", session_id=source, operation="cut",
                                 options={"kind": "notes", "track_index": 0, "part_index": 0, "indices": [1]}))["clipboard_id"]
        clips.append(clip)
        cut, _ = await check.save(source, "extended-cut-note")
        v.require([n["x_cut"] for n in cut["tracks"][0]["parts"][0]["notes"]] == ["note-0"],
                  "Cut removed the wrong note metadata")
        await check.edit(source, "undo")
        restored, _ = await check.save(source, "extended-cut-undo")
        v.require([n["x_cut"] for n in restored["tracks"][0]["parts"][0]["notes"]] == ["note-0", "note-1"],
                  "Cut undo lost original note metadata")
        await check.edit(source, "redo")
        redone, _ = await check.save(source, "extended-cut-redo")
        v.require([n["x_cut"] for n in redone["tracks"][0]["parts"][0]["notes"]] == ["note-0"],
                  "Cut redo changed remaining metadata")
        await check.close(source)
        async with check.project(score=True) as target:
            await check.call("project_clipboard", session_id=target, operation="paste",
                             options={"clipboard_id": clip, "track_index": 0, "part_index": 0, "offset_tick": 1920})
            await check.call("project_clipboard", operation="clear", options={"clipboard_id": clip}); clips.remove(clip)
            saved, target_path = await check.save(target, "extended-cut-paste")
            notes = saved["tracks"][0]["parts"][0]["notes"]
            v.require(sum(n.get("x_cut") == "note-1" for n in notes) == 1,
                      "Pasted cut note lost its original metadata")
            opened = (await check.call("project_open", path=str(target_path)))["session_id"]
            try:
                reopened, _ = await check.save(opened, "extended-cut-reopen")
                v.require(sum(n.get("x_cut") == "note-1" for n in reopened["tracks"][0]["parts"][0]["notes"]) == 1,
                          "Cut note metadata was not retained on reopen")
            finally:
                await check.close(opened)
        source = (await check.call("project_open", path=str(path)))["session_id"]
        clip = (await check.call("project_clipboard", session_id=source, operation="cut",
                                 options={"kind": "tracks", "indices": [0]}))["clipboard_id"]
        clips.append(clip)
        cut, _ = await check.save(source, "extended-cut-track")
        v.require(not cut.get("tracks", []), "Cut track remained present")
        await check.edit(source, "undo")
        restored, _ = await check.save(source, "extended-track-undo")
        v.require(restored["tracks"][0]["x_cut"] == "track" and
                  restored["tracks"][0]["parts"][0]["x_cut"] == "part", "Track cut undo lost metadata")
        await check.close(source)
        async with check.project() as target:
            await check.call("project_clipboard", session_id=target, operation="paste", options={"clipboard_id": clip})
            saved, _ = await check.save(target, "extended-cut-track-paste")
            v.require(saved["tracks"][0]["x_cut"] == "track" and
                      [n["x_cut"] for n in saved["tracks"][0]["parts"][0]["notes"]] == ["note-0", "note-1"],
                      "Pasted cut track lost metadata")
        await check.call("project_clipboard", operation="clear", options={"clipboard_id": clip}); clips.remove(clip)
        source = (await check.call("project_open", path=str(path)))["session_id"]
        clip = (await check.call("project_clipboard", session_id=source, operation="cut",
                                 options={"kind": "parts", "track_index": 0, "indices": [0]}))["clipboard_id"]
        clips.append(clip)
        cut, _ = await check.save(source, "extended-cut-part")
        v.require(not cut["tracks"][0].get("parts", []), "Cut part remained present")
        await check.edit(source, "undo")
        restored, _ = await check.save(source, "extended-part-undo")
        v.require(restored["tracks"][0]["parts"][0]["x_cut"] == "part", "Part cut undo lost metadata")
        await check.close(source)
        async with check.project(score=True) as target:
            await check.call("project_clipboard", session_id=target, operation="paste",
                             options={"clipboard_id": clip, "track_index": 0, "offset_tick": 9600})
            saved, _ = await check.save(target, "extended-cut-part-paste")
            copied = saved["tracks"][0]["parts"][1]
            v.require(copied["x_cut"] == "part" and copied["pos"] == 9600 and
                      [n["x_cut"] for n in copied["notes"]] == ["note-0", "note-1"],
                      "Pasted cut part lost metadata or position")
        v.require(path.read_bytes() == original, "Cut altered the original file")
    finally:
        for clip in clips:
            await check.call("project_clipboard", operation="clear", options={"clipboard_id": clip})
