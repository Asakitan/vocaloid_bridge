"""Maintained MCP coverage for the explicit synthetic MIDI event stream."""
import json
import zipfile

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

    async with check.project(score=True) as seed:
        await check.edit(seed, "part.resize", track_index=0, part_index=0, duration_tick=3840)
        await check.edit(seed, "pitch.set", track_index=0, part_index=0, note_index=0,
                         points=[{"tick": 0, "value": 60}, {"tick": 100, "value": 61}])
        await check.edit(seed, "controller.set", track_index=0, part_index=0, type="Dynamics",
                         points=[{"tick": 0, "value": 64}])
        await check.edit(seed, "automation.set", scope="track_volume", track_index=0,
                         points=[{"tick": 480, "value": 0}])
        sequence, seed_path = await check.save(seed, "midi-extension-seed")
    _, members = v.read_vpr(seed_path)
    marker = "x_midi_recording_probe"
    track = sequence["tracks"][0]
    part = track["parts"][0]
    note = part["notes"][0]
    sequence[marker], track[marker], part[marker], note[marker] = "root", "track", "part", "note"
    note["directPitches"][0][marker] = "pitch"
    next(lane for lane in part["controllers"] if lane["name"].lower() == "dynamics")["events"][0][marker] = "controller"
    next(point for point in track["volume"]["events"] if point["pos"] == 480)[marker] = "automation"
    resource = "Project/bridge-probe/midi-recording.bin"
    members[resource] = b"midi-recording-extension\x00\x01"
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("midi-extension-source")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        await check.edit(sid, "track.update", track_index=0, midi_recording=True)
        before, _ = await check.save(sid, "midi-extension-before")
        before_notes = (await check.edit(sid, "note.list", track_index=0, part_index=0))["notes"]
        before_history = await check.edit(sid, "history.status")
        duplicate_scope = {"mode": "synthetic", "track_index": 0, "part_index": 0, "start_tick": 0,
                           "lyric": "あ", "phonemes": "a", "lang_id": 0}
        await check.call("project_midi", session_id=sid, operation="start", options=duplicate_scope)
        await check.call("project_midi", session_id=sid, operation="synthetic_events", options={"events": [
            {"elapsed_ms": 0, "channel": 0, "number": before_notes[0]["number"],
             "velocity": before_notes[0]["velocity"], "on": True},
            {"elapsed_ms": 300, "channel": 0, "number": before_notes[0]["number"], "velocity": 0, "on": False}]})
        await check.rejected("project_midi", "ambiguous|overlap|identity", session_id=sid,
                             operation="stop", options={"end_ms": 300})
        await check.call("project_midi", session_id=sid, operation="cancel", options={})
        v.require((await check.edit(sid, "note.list", track_index=0, part_index=0))["notes"] == before_notes
                  and await check.edit(sid, "history.status") == before_history,
                  "Rejected ambiguous MIDI note changed the project or history")
        scope = {"mode": "synthetic", "track_index": 0, "part_index": 0, "start_tick": 1440,
                 "lyric": "あ", "phonemes": "a", "lang_id": 0}
        await check.call("project_midi", session_id=sid, operation="start", options=scope)
        await check.call("project_midi", session_id=sid, operation="synthetic_events", options={"events": [
            {"elapsed_ms": 100, "channel": 0, "number": 72, "velocity": 91, "on": True},
            {"elapsed_ms": 300, "channel": 0, "number": 72, "velocity": 0, "on": False}]})
        stopped = await check.call("project_midi", session_id=sid, operation="stop", options={"end_ms": 300})
        v.require(stopped["result"]["inserted"] == 1, "Extended-project MIDI note was not inserted")
        after_notes = (await check.edit(sid, "note.list", track_index=0, part_index=0))["notes"]
        v.require(len(after_notes) == len(before_notes) + 1, "MIDI recording lost existing notes")
        saved, path = await check.save(sid, "midi-extension-recorded")
        v.require(saved[marker] == "root" and saved["tracks"][0][marker] == "track"
                  and saved["tracks"][0]["parts"][0][marker] == "part"
                  and saved["tracks"][0]["parts"][0]["notes"][0] == before["tracks"][0]["parts"][0]["notes"][0]
                  and saved["tracks"][0]["parts"][0]["controllers"] == before["tracks"][0]["parts"][0]["controllers"]
                  and saved["tracks"][0]["volume"] == before["tracks"][0]["volume"]
                  and v.read_vpr(path)[1][resource] == members[resource],
                  "MIDI recording changed existing extended entities or resources")
        await check.edit(sid, "undo")
        undone, undo_path = await check.save(sid, "midi-extension-undo")
        v.require(undone == before and v.read_vpr(undo_path)[1][resource] == members[resource],
                  "MIDI recording undo did not restore extension data")
        await check.edit(sid, "redo")
        redone, redo_path = await check.save(sid, "midi-extension-redo")
        v.require(redone == saved and v.read_vpr(redo_path)[1][resource] == members[resource],
                  "MIDI recording redo did not restore extension data")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        try:
            v.require((await check.edit(reopened, "note.list", track_index=0, part_index=0))["notes"] == after_notes,
                      "Extended MIDI recording changed after reopen")
        finally:
            await check.close(reopened)
        check.evidence("midi_extended", {"source": str(source), "saved": str(path), "undo": str(undo_path),
                                          "redo": str(redo_path), "hardware_opened": False})
    finally:
        await check.close(sid)
    v.require(source.read_bytes() == original, "MIDI recording modified its source project")
