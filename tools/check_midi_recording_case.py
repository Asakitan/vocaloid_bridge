"""Maintained MCP coverage for the explicit synthetic MIDI event stream."""
import verify_features as v


@v.feature("midi.recording.synthetic", "midi_recording", "project_midi", "project_edit", "project_save", "project_open")
async def synthetic_recording(check):
    listing = await check.call("project_midi", operation="devices", options={})
    v.require(listing["native"] and isinstance(listing["result"]["devices"], list), "Invalid MIDI device listing")
    async with check.project(score=True) as sid:
        await check.edit(sid, "note.clear", track_index=0, part_index=0)
        await check.edit(sid, "track.update", track_index=0, midi_recording=True)
        await check.save(sid, "midi-armed")
        scope = {"mode": "synthetic", "track_index": 0, "part_index": 0, "start_tick": 0,
                 "lyric": "あ", "phonemes": "a", "lang_id": 0}

        async def midi(operation, **options):
            result = await check.call("project_midi", session_id=sid, operation=operation, options=options)
            v.require(result["native"] and result["operation"] == operation, "Invalid MIDI operation envelope", result)
            return result["result"]

        await midi("start", **scope)
        v.require((await midi("status"))["active"], "Recording did not start")
        await check.rejected("project_close", "pending MIDI recording", session_id=sid, discard_changes=False)
        await check.rejected("project_library", "recording", session_id=sid, operation="style_list", options={})
        await midi("synthetic_events", events=[
            {"elapsed_ms": 100, "channel": 0, "number": 60, "velocity": 91, "on": True},
            {"elapsed_ms": 600, "channel": 0, "number": 60, "velocity": 0, "on": False}])
        stopped = await midi("stop", end_ms=600)
        v.require(stopped["inserted"] == 1, "Recorded note was not inserted", stopped)
        notes = (await check.edit(sid, "note.list", track_index=0, part_index=0))["notes"]
        v.require([(n["start_tick"], n["duration_tick"], n["number"], n["velocity"]) for n in notes]
                  == [(96, 480, 60, 91)], "Recorded note timing or velocity differs", notes)
        _, path = await check.save(sid, "midi-recorded")
        await midi("start", **scope)
        v.require((await midi("cancel"))["cancelled"], "Recording did not cancel")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        try:
            actual = (await check.edit(reopened, "note.list", track_index=0, part_index=0))["notes"]
            v.require(actual == notes, "Recorded note changed after reopen", actual)
        finally:
            await check.close(reopened)
        check.evidence("midi_synthetic", {"hardware_opened": False, "stopped": stopped, "saved": str(path)})
