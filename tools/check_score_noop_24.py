"""Verify a same-name track update preserves clean state through real MCP."""
import sys

import verify_features as v


@v.feature("score.track_name_noop_24", "score", "project_create", "project_edit", "project_save",
           "project_open", "project_status", "project_get", "project_items", "project_set")
async def track_name_noop(check):
    async with check.project() as seed:
        await check.edit(seed, "track.create", type="MidiAi", name="Noop AI")
        _, source = await check.save(seed, "track-noop-source")
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        status = await check.call("project_status", session_id=sid)
        history = await check.edit(sid, "history.status")
        v.require(not status["dirty"], "Reopened project is not clean")
        result = await check.edit(sid, "track.update", track_index=0, name="Noop AI")
        v.require(result["name"] == "Noop AI" and await check.call("project_status", session_id=sid) == status and
                  await check.edit(sid, "history.status") == history, "Same-name update changed state or history")
        await check.edit(sid, "track.update", track_index=0, name="Noop AI changed")
        dirty = await check.call("project_status", session_id=sid)
        dirty_history = await check.edit(sid, "history.status")
        v.require(dirty["dirty"], "Changed name did not mark project dirty")
        await check.edit(sid, "track.update", track_index=0, name="Noop AI changed")
        v.require(await check.call("project_status", session_id=sid) == dirty and
                  await check.edit(sid, "history.status") == dirty_history, "No-op altered an already dirty project")
        saved, output = await check.save(sid, "track-noop-changed")
        v.require(saved["tracks"][0]["name"] == "Noop AI changed", "Changed name was not saved")
        reopened = (await check.call("project_open", path=str(output)))["session_id"]
        try:
            v.require((await check.edit(reopened, "track.list"))["tracks"][0]["name"] == "Noop AI changed",
                      "Changed name did not survive reopen")
        finally:
            await check.close(reopened)

        tempos = (await check.call("project_get", session_id=sid, member="Tempos"))["value"]
        item = (await check.call("project_items", session_id=sid, ref=tempos["$ref"]))["items"][0]
        value = (await check.call("project_get", session_id=sid, ref=item["$ref"], member="Value"))["value"]
        await check.call("project_set", session_id=sid, ref=item["$ref"], member="Value", value=value + 1)
        v.require((await check.edit(sid, "history.status"))["staged"], "Native tempo change did not stage")
        await check.rejected("project_edit", "pending native edits", session_id=sid, operation="track.update",
                             options={"track_index": 0, "name": "Noop AI changed"})
        v.require((await check.edit(sid, "history.status"))["staged"], "No-op consumed pending native edits")
        await check.edit(sid, "history.rollback")
    finally:
        await check.close(sid)
    v.require(source.read_bytes() == original, "Track no-op changed source archive")


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "score.track_name_noop_24"])
    raise SystemExit(v.main())
