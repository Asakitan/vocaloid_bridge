"""Exercise private clipboard preflight for ambiguous AI track identities."""
import json
from pathlib import Path
import zipfile

import verify_features as v


@v.feature("preservation.clipboard_ambiguity", "preservation", "score_compose", "project_open",
           "project_clipboard", "project_edit", "project_save")
async def clipboard_ambiguity(check):
    seed = await check.call("score_compose", output_name=check.output("clipboard-ambiguity-seed"),
                            title="Clipboard ambiguity", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    original_seed = Path(seed["path"]).read_bytes()
    sequence, members = v.read_vpr(seed["path"])
    sequence["tracks"][0]["x_clipboard_track"] = "source-track"
    sequence["tracks"][0]["parts"][0]["x_clipboard_part"] = "source-part"
    sequence["tracks"][0]["parts"][0]["notes"][0]["x_clipboard_note"] = "source-note"
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("clipboard-ambiguity-source")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original_source = source.read_bytes()
    clips = []
    try:
        src = (await check.call("project_open", path=str(source)))["session_id"]
        try:
            for _ in range(3):
                clips.append((await check.call("project_clipboard", session_id=src, operation="copy",
                                               options={"kind": "tracks", "indices": [0]}))["clipboard_id"])
        finally:
            await check.close(src)
        target = (await check.call("project_open", path=seed["path"]))["session_id"]
        try:
            before = await check.call("project_status", session_id=target)
            attempted = await check.raw("project_clipboard", {"session_id": target, "operation": "paste",
                                                               "options": {"clipboard_id": clips[0]}})
            if not attempted.isError:
                await check.rejected("project_save", "indistinguishable track identities", session_id=target,
                                     output_name=check.output("clipboard-ambiguity-unexpected"))
                raise AssertionError("Ambiguous clipboard paste succeeded but made the target unsaveable")
            text = " ".join(getattr(item, "text", str(item)) for item in attempted.content)
            v.require("indistinguishable track identities" in text, "Wrong clipboard rejection", text)
            v.require(await check.call("project_status", session_id=target) == before,
                      "Rejected ambiguous paste changed the target")
            protected, _ = await check.save(target, "clipboard-ambiguity-protected")
            v.require(len(protected["tracks"]) == 1 and "x_clipboard_track" not in protected["tracks"][0],
                      "Rejected paste left a track or extension in the target")
            cleared = await check.call("project_clipboard", operation="clear", options={"clipboard_id": clips[0]})
            v.require(cleared["cached_assets_retained"] is False,
                      "Failed candidate paste marked clipboard assets as used")
            clips.pop(0)
            await check.call("project_clipboard", session_id=target, operation="paste",
                             options={"clipboard_id": clips[0], "offset_tick": 960})
            saved, _ = await check.save(target, "clipboard-ambiguity-offset")
            v.require(len(saved["tracks"]) == 2 and saved["tracks"][1]["x_clipboard_track"] == "source-track" and
                      saved["tracks"][1]["parts"][0]["x_clipboard_part"] == "source-part" and
                      saved["tracks"][1]["parts"][0]["notes"][0]["x_clipboard_note"] == "source-note",
                      "Unambiguous offset paste lost its metadata")
            await check.edit(target, "undo")
            undone, _ = await check.save(target, "clipboard-ambiguity-undo")
            v.require(len(undone["tracks"]) == 1, "Undo retained pasted track")
            await check.edit(target, "redo")
            redone, path = await check.save(target, "clipboard-ambiguity-redo")
            v.require(redone["tracks"][1]["x_clipboard_track"] == "source-track", "Redo lost pasted metadata")
            reopened = (await check.call("project_open", path=str(path)))["session_id"]
            try:
                reopened_value, _ = await check.save(reopened, "clipboard-ambiguity-reopened")
                v.require(reopened_value["tracks"][1]["x_clipboard_track"] == "source-track",
                          "Reopened track lost pasted metadata")
            finally:
                await check.close(reopened)
        finally:
            await check.close(target)
        cleared = await check.call("project_clipboard", operation="clear", options={"clipboard_id": clips[0]})
        v.require(cleared["cached_assets_retained"] is True, "Successful paste did not retain clipboard assets")
        clips.pop(0)
        equal_target = (await check.call("project_open", path=str(source)))["session_id"]
        try:
            await check.call("project_clipboard", session_id=equal_target, operation="paste",
                             options={"clipboard_id": clips[0]})
            equal, _ = await check.save(equal_target, "clipboard-ambiguity-equal")
            v.require(len(equal["tracks"]) == 2 and all(t["x_clipboard_track"] == "source-track" for t in equal["tracks"]),
                      "Equivalent tracks were rejected or lost extension data")
        finally:
            await check.close(equal_target)
        v.require(Path(seed["path"]).read_bytes() == original_seed and source.read_bytes() == original_source,
                  "Clipboard probe changed a source file")
    finally:
        for clip in clips:
            await check.call("project_clipboard", operation="clear", options={"clipboard_id": clip})


if __name__ == "__main__":
    raise SystemExit(v.main())
