"""Regression for extension-bearing clipboard sources and ordinary targets."""
import json
import zipfile

import verify_features as v


@v.feature("preservation.clipboard_source_guard", "preservation", "score_compose", "project_open",
           "project_clipboard", "project_create", "project_status")
async def clipboard_source_guard(check):
    seed = await check.call("score_compose", output_name=check.output("clipboard-extension-seed"),
                            title="Clipboard extension guard", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    sequence["tracks"][0]["x_clipboard_track"] = {"source": "original"}
    sequence["tracks"][0]["parts"][0]["notes"][0]["x_clipboard_note"] = "original"
    members["Project/bridge-probe/unmapped.bin"] = b"opaque-resource"
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("clipboard-extension-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    original = source.read_bytes()
    clipboard = None
    try:
        sid = (await check.call("project_open", path=str(source)))["session_id"]
        before_cut = await check.call("project_status", session_id=sid)
        await check.rejected("project_clipboard", "opaque archive resources",
                             operation="cut", session_id=sid,
                             options={"kind": "tracks", "indices": [0]})
        v.require(await check.call("project_status", session_id=sid) == before_cut,
                  "Rejected cut modified the source session")
        clipboard = (await check.call("project_clipboard", operation="copy", session_id=sid,
                                      options={"kind": "tracks", "indices": [0]}))["clipboard_id"]
        await check.close(sid)
        async with check.project() as target:
            before = await check.call("project_status", session_id=target)
            await check.rejected("project_clipboard", "project_preservation|identity",
                                 operation="paste", session_id=target,
                                 options={"clipboard_id": clipboard})
            after = await check.call("project_status", session_id=target)
            v.require(before == after, "Rejected clipboard paste changed target session", {"before": before, "after": after})
        v.require(source.read_bytes() == original, "Clipboard operation changed the source VPR")
        check.evidence("clipboard_extension_source", {"source": str(source), "clipboard": clipboard})
    finally:
        if clipboard is not None:
            await check.call("project_clipboard", operation="clear", options={"clipboard_id": clipboard})
