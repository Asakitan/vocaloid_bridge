"""Focused acceptance for clipboard extension transfer on synthetic VPRs."""
import json
import zipfile
import verify_features as v


@v.feature("preservation.clipboard_transfer", "preservation", "score_compose", "project_open",
           "project_clipboard", "project_edit", "project_save")
async def clipboard_transfer(check):
    seed = await check.call("score_compose", output_name=check.output("transfer-seed"),
                            title="Transfer fixture", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0},
                                   {"start": 1, "duration": .5, "pitch": 62, "lyric": "い", "phoneme": "i", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    track = sequence["tracks"][0]; part = track["parts"][0]
    track["x_transfer"] = "track"; part["x_transfer"] = "part"
    for i, note in enumerate(part["notes"]): note["x_transfer"] = "note-" + str(i)
    original_pos = part["pos"]
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("transfer-source")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    plain = (await check.call("project_create", title="Root-only target"))["session_id"]
    target_json, target_seed = await check.save(plain, "transfer-target-seed")
    await check.close(plain)
    _, target_members = v.read_vpr(target_seed)
    target_json["x_target_root"] = "target-root"
    target_json["masterTrack"]["x_target_master"] = "target-master"
    target_members["Project/sequence.json"] = json.dumps(target_json, ensure_ascii=False).encode("utf-8")
    target_members["Project/target-opaque.bin"] = b"target-resource"
    target_source = v.ROOT / "output" / check.output("transfer-root-only-target")
    with zipfile.ZipFile(target_source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in target_members.items(): archive.writestr(name, payload)
    original = source.read_bytes(); clips = []
    try:
        src = (await check.call("project_open", path=str(source)))["session_id"]
        for options in ({"kind": "tracks", "indices": [0]},
                        {"kind": "parts", "indices": [0], "track_index": 0},
                        {"kind": "notes", "indices": [1, 0], "track_index": 0, "part_index": 0}):
            clips.append((await check.call("project_clipboard", session_id=src, operation="copy", options=options))["clipboard_id"])
        await check.close(src)
        target = (await check.call("project_open", path=str(target_source)))["session_id"]
        try:
            await check.call("project_clipboard", session_id=target, operation="paste",
                             options={"clipboard_id": clips[0], "offset_tick": 960})
            saved, _ = await check.save(target, "transfer-paste")
            def verify(value):
                v.require(value["x_target_root"] == "target-root" and
                          value["masterTrack"]["x_target_master"] == "target-master", "Target root/master fields changed")
                copied = value["tracks"][0]; copied_part = copied["parts"][0]
                v.require(copied["x_transfer"] == "track" and copied_part["x_transfer"] == "part", "Parent fields lost")
                v.require(copied_part["pos"] == original_pos + 960, "Part offset changed")
                v.require([n["x_transfer"] for n in copied_part["notes"]] == ["note-0", "note-1"], "Note fields mismatched")
            verify(saved)
            await check.edit(target, "undo")
            undone, _ = await check.save(target, "transfer-undo")
            v.require(not undone.get("tracks", []), "Undo retained pasted track")
            await check.edit(target, "redo")
            redone, _ = await check.save(target, "transfer-redo"); verify(redone)
            await check.call("project_clipboard", session_id=target, operation="paste",
                             options={"clipboard_id": clips[1], "track_index": 0, "offset_tick": 9600})
            await check.call("project_clipboard", session_id=target, operation="paste",
                             options={"clipboard_id": clips[2], "track_index": 0, "part_index": 0, "offset_tick": 3000})
            expanded, path = await check.save(target, "transfer-parts-and-notes")
            parts = expanded["tracks"][0]["parts"]
            v.require(len(parts) == 2 and parts[1]["x_transfer"] == "part" and
                      parts[1]["pos"] == original_pos + 9600, "Transferred part metadata or offset changed")
            v.require([n["x_transfer"] for n in parts[1]["notes"]] == ["note-0", "note-1"], "Transferred part notes mismatched")
            v.require([n["x_transfer"] for n in parts[0]["notes"]] == ["note-0", "note-1", "note-0", "note-1"],
                      "Transferred individual notes mismatched")
            await check.edit(target, "undo"); await check.edit(target, "undo")
            reverted, _ = await check.save(target, "transfer-children-undo"); verify(reverted)
            await check.edit(target, "redo"); await check.edit(target, "redo")
            redone, path = await check.save(target, "transfer-children-redo")
            v.require([n["x_transfer"] for n in redone["tracks"][0]["parts"][0]["notes"]] ==
                      ["note-0", "note-1", "note-0", "note-1"], "Transferred notes lost metadata after redo")
            for clip in clips:
                await check.call("project_clipboard", operation="clear", options={"clipboard_id": clip})
            clips.clear()
            redone, path = await check.save(target, "transfer-clipboard-cleared")
            v.require([p["x_transfer"] for p in redone["tracks"][0]["parts"]] == ["part", "part"],
                      "Transferred data depended on a cleared clipboard")
            _, target_output = v.read_vpr(path)
            v.require(target_output["Project/target-opaque.bin"] == b"target-resource", "Target opaque resource changed")
            reopened = (await check.call("project_open", path=str(path)))["session_id"]
            try:
                reopened_value, _ = await check.save(reopened, "transfer-reopened")
                v.require([p["x_transfer"] for p in reopened_value["tracks"][0]["parts"]] == ["part", "part"],
                          "Transferred parts lost metadata on reopen")
            finally:
                await check.close(reopened)
        finally:
            await check.close(target)
        v.require(source.read_bytes() == original, "Source VPR changed")
    finally:
        for clip in clips:
            await check.call("project_clipboard", operation="clear", options={"clipboard_id": clip})


if __name__ == "__main__":
    raise SystemExit(v.main())
