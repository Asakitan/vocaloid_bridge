"""Necessary MCP history and native post-mutation rollback checks for lyrics."""
import json
import sys
import verify_features as v

sys.path.insert(0, str(v.ROOT))
from vocaloid_bridge.native_client import IsolatedProcess
from vocaloid_bridge.install import discover, host_path, validate_target


@v.feature("library.lyrics_transactions_31", "library", "score_compose", "project_library", "project_edit", "project_save")
async def lyrics_transactions(check):
    seed = await check.call("score_compose", output_name=check.output("lyric-tx-seed"), title="Lyric transactions",
                            bpm=120, notes=[{"start": n, "duration": .5, "pitch": 60 + n, "lyric": "あ",
                                            "phoneme": "a", "lang_id": 0} for n in range(2)])
    sid = seed["native_session"]["session_id"]
    scope = {"track_index": 0, "part_index": 0}
    try:
        for operation, values in (("lyrics_apply", {"lyrics": "い", "note_index": 0}),
                                  ("phonemes_apply", {"phonemes": "i", "note_index": 1}),
                                  ("lyrics_reset", {}), ("phonemes_reset", {})):
            before = await check.edit(sid, "note.list", **scope)
            await check.library(operation, sid, **scope, language_id=0, **values)
            after = await check.edit(sid, "note.list", **scope)
            if before != after:
                await check.edit(sid, "undo")
                v.require(await check.edit(sid, "note.list", **scope) == before, "Lyric transaction was not one undo step", operation)
                await check.edit(sid, "redo")
                v.require(await check.edit(sid, "note.list", **scope) == after, "Lyric redo failed", operation)
        before = await check.edit(sid, "note.list", **scope)
        await check.rejected("project_library", "G2PA", session_id=sid, operation="lyrics_apply",
                             options={**scope, "note_index": 0, "language_id": 4, "lyrics": "ni3"})
        v.require(await check.edit(sid, "note.list", **scope) == before, "Rejected lyrics changed notes")
        await check.save(sid, "lyric-tx-saved")
    finally:
        await check.close(sid)
    root = check.directory / "lyric-rollback-private"
    root.mkdir()
    installation = discover()
    host = host_path(v.ROOT, installation)
    validate_target(installation, host)
    product = (await check.call("vocaloid_features"))["product"]
    v.require(installation.product == product, "Rollback probe selected a different VOCALOID product")
    process = IsolatedProcess([r"C:\Program Files\PowerShell\7\pwsh.exe", "-NoProfile", "-File",
                               str(v.ROOT / "tools/check_lyrics_rollback_31.ps1"), "-Root", str(root), "-Source", seed["path"],
                               "-Install", str(installation.path), "-Product", product, "-HostPath", str(host)], v.ROOT)
    try:
        observed = json.loads(process.read_line(60))
    finally:
        process.close()
    check.evidence("native_post_mutation_rollback", observed)
    v.require(observed["product"] == product and observed["core_assembly"] == product
              and observed["staged_change_observed"] and observed["lyric_change_observed"] and observed["restored"]
              and observed["track_change_observed"] and observed["track_restored"],
              "Native lyric or track rollback did not restore prior state", observed)


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "library.lyrics_transactions_31"])
    raise SystemExit(v.main())
