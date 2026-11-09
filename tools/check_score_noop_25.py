"""Check ordinary AI track no-ops through an isolated native MCP host."""
import sys
import verify_features as v

FIELDS = ("name", "color", "mute", "solo", "bus_no")

@v.feature("score.track_fields_noop_25", "score", "project_create", "project_edit", "project_save", "project_open", "project_status", "project_get", "project_items", "project_set")
async def track_fields_noop(check):
    async with check.project() as seed:
        await check.edit(seed, "track.create", type="MidiAi", name="Noop AI")
        _, source = await check.save(seed, "track-fields-source")
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        track = (await check.edit(sid, "track.list"))["tracks"][0]
        status = await check.call("project_status", session_id=sid)
        history = await check.edit(sid, "history.status")
        v.require(not status["dirty"] and not history["staged"], "Fixture must start clean and unstaged")
        observed = {}
        for field in FIELDS:
            probe = (await check.call("project_open", path=str(source)))["session_id"]
            try:
                before = await check.call("project_status", session_id=probe)
                hist_before = await check.edit(probe, "history.status")
                result = await check.edit(probe, "track.update", track_index=0, **{field: track[field]})
                after = await check.call("project_status", session_id=probe)
                hist_after = await check.edit(probe, "history.status")
                observed[field] = {"before": before, "after": after, "history_before": hist_before, "history_after": hist_after, "result": result}
            finally:
                await check.close(probe)
        check.evidence("individual_clean", observed)
        failures = [field for field, item in observed.items() if item["before"] != item["after"] or item["history_before"] != item["history_after"]]

        recording_probe = (await check.call("project_open", path=str(source)))["session_id"]
        try:
            recording_history = await check.edit(recording_probe, "history.status")
            await check.edit(recording_probe, "track.update", track_index=0, midi_recording=track["midi_recording"])
            recording_after = await check.call("project_status", session_id=recording_probe)
            v.require(recording_after["dirty"] and await check.edit(recording_probe, "history.status") == recording_history,
                      "MIDI recording no longer followed its existing setter path")
        finally:
            await check.close(recording_probe)

        values = {field: track[field] for field in FIELDS}
        await check.edit(sid, "track.update", track_index=0, **values)
        v.require(await check.call("project_status", session_id=sid) == status and await check.edit(sid, "history.status") == history, "Combined no-op changed clean state")
        changed = {"name": "Noop AI changed", "color": (track["color"] + 1) % 16, "mute": not track["mute"], "solo": not track["solo"]}
        await check.edit(sid, "track.update", track_index=0, **changed)
        dirty = await check.call("project_status", session_id=sid)
        dirty_history = await check.edit(sid, "history.status")
        v.require(dirty["dirty"] and not dirty_history["staged"], "Real edit not committed and dirty")
        current = (await check.edit(sid, "track.list"))["tracks"][0]
        await check.edit(sid, "track.update", track_index=0, **{field: current[field] for field in FIELDS})
        v.require(await check.call("project_status", session_id=sid) == dirty and await check.edit(sid, "history.status") == dirty_history, "No-op altered dirty state")
        _, output = await check.save(sid, "track-fields-changed")
        reopened = (await check.call("project_open", path=str(output)))["session_id"]
        try:
            saved = (await check.edit(reopened, "track.list"))["tracks"][0]
            v.require(all(saved[field] == value for field, value in changed.items()), "Real changes did not survive reopen", saved)
        finally:
            await check.close(reopened)
        tempos = (await check.call("project_get", session_id=sid, member="Tempos"))["value"]
        item = (await check.call("project_items", session_id=sid, ref=tempos["$ref"]))["items"][0]
        value = (await check.call("project_get", session_id=sid, ref=item["$ref"], member="Value"))["value"]
        await check.call("project_set", session_id=sid, ref=item["$ref"], member="Value", value=value + 1)
        v.require((await check.edit(sid, "history.status"))["staged"], "Tempo did not stage")
        await check.rejected("project_edit", "pending native edits", session_id=sid, operation="track.update", options={"track_index": 0, **{field: current[field] for field in FIELDS}})
        v.require((await check.edit(sid, "history.status"))["staged"], "No-op consumed pending edit")
        await check.edit(sid, "history.rollback")
    finally:
        await check.close(sid)
    v.require(source.read_bytes() == original, "Source archive changed")
    v.require(not failures, "Same-value fields changed state or history", failures)

if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "score.track_fields_noop_25"])
    raise SystemExit(v.main())
