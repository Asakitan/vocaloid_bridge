"""Exercise note edits while controller-event extensions are tracked."""
import json
import sys
import zipfile

import verify_features as v

KEY = "x_controller_notes_22"


@v.feature("preservation.controller_note_edits_22", "preservation", "score_compose", "project_edit",
           "project_open", "project_save", "project_clone", "project_merge")
async def controller_note_edits(check):
    seed = await check.call(
        "score_compose", output_name=check.output("controller-notes-seed"), title="Controller notes", bpm=120,
        notes=[{"start": i, "duration": .5, "pitch": pitch, "lyric": "あ", "phoneme": "a", "lang_id": 0}
               for i, pitch in enumerate((60, 64))])
    sid = seed["native_session"]["session_id"]
    try:
        await check.edit(sid, "controller.set", track_index=0, part_index=0, type="Dynamics", replace=True,
                         points=[{"tick": 60, "value": 30}, {"tick": 180, "value": 64}])
        await check.edit(sid, "track.duplicate", track_index=0, name="Second AI")
        sequence, path = await check.save(sid, "controller-notes-native")
    finally:
        await check.close(sid)
    _, members = v.read_vpr(path)
    for index, track in enumerate(sequence["tracks"]):
        part = track["parts"][0]
        part["notes"][0]["x_note22"] = {"track": index}
        lane = next(lane for lane in part["controllers"] if lane["name"] == "dynamics")
        for event in lane["events"]:
            event[KEY] = {"track": index, "tick": event["pos"], "nested": [True, None]}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("controller-notes-extended")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    original = source.read_bytes()

    def controllers(project):
        return [next(lane["events"] for lane in track["parts"][0]["controllers"]
                     if lane["name"] == "dynamics") for track in project["tracks"]]

    sid = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        before, _ = await check.save(sid, "controller-notes-before")
        original_lanes = controllers(before)
        history = await check.edit(sid, "history.status")
        await check.rejected("project_edit", "controller extension", session_id=sid, operation="time.insert",
                             options={"start_tick": 10000, "duration_tick": 480, "include_tempo": False})
        v.require(await check.edit(sid, "history.status") == history, "Rejected time edit changed history")
        states = [before]
        edits = [
            ("note.update", {"track_index": 0, "part_index": 0, "note_index": 0, "number": 61}),
            ("note.add", {"track_index": 0, "part_index": 0, "start_tick": 1200, "duration_tick": 240,
                          "number": 67, "lyric": "あ", "phonemes": "a", "lang_id": 0}),
            ("note.batch_update", {"track_index": 0, "part_index": 0, "note_indices": [0, 1], "transpose": 1}),
            ("note.update", {"track_index": 1, "part_index": 0, "note_index": 1, "number": 65}),
        ]
        for index, (operation, options) in enumerate(edits):
            await check.edit(sid, operation, **options)
            snapshot, _ = await check.save(sid, f"controller-notes-step-{index}")
            v.require(controllers(snapshot) == original_lanes, "Note edit changed controller metadata", operation)
            v.require(snapshot["tracks"][0]["parts"][0]["notes"][0]["x_note22"] == {"track": 0} and
                      snapshot["tracks"][1]["parts"][0]["notes"][0]["x_note22"] == {"track": 1},
                      "Note edit changed unknown note metadata", operation)
            states.append(snapshot)
        v.require([n["number"] for n in states[-1]["tracks"][0]["parts"][0]["notes"]] == [62, 65, 67] and
                  [n["number"] for n in states[-1]["tracks"][1]["parts"][0]["notes"]] == [60, 65],
                  "Requested note edits did not persist")
        status = await check.call("project_status", session_id=sid)
        history = await check.edit(sid, "history.status")
        await check.rejected("project_edit", "transpose|range", session_id=sid, operation="note.batch_update",
                             options={"track_index": 0, "part_index": 0, "note_indices": [0], "transpose": 127})
        v.require(await check.call("project_status", session_id=sid) == status and
                  await check.edit(sid, "history.status") == history, "Invalid note edit changed state")
        for index in range(len(edits) - 1, -1, -1):
            await check.edit(sid, "undo")
            undone, _ = await check.save(sid, f"controller-notes-undo-{index}")
            v.require(undone == states[index], "Undo lost controller or note state", index)
        for index in range(len(edits)):
            await check.edit(sid, "redo")
            redone, saved = await check.save(sid, f"controller-notes-redo-{index}")
            v.require(redone == states[index + 1], "Redo lost controller or note state", index)
        clone = (await check.call("project_clone", session_id=sid))["session_id"]
        try:
            cloned, _ = await check.save(clone, "controller-notes-clone")
            v.require(cloned == states[-1], "Clone lost controller or note state")
        finally:
            await check.close(clone)
        reopened = (await check.call("project_open", path=str(saved)))["session_id"]
        try:
            actual, _ = await check.save(reopened, "controller-notes-reopened")
            v.require(actual == states[-1], "Reopen lost controller or note state")
        finally:
            await check.close(reopened)
        await check.edit(sid, "undo")
        await check.edit(sid, "note.update", track_index=1, part_index=0, note_index=0, number=62)
        branched, _ = await check.save(sid, "controller-notes-branch")
        v.require(controllers(branched) == original_lanes and not (await check.edit(sid, "history.status"))["can_redo"],
                  "History branch changed controller metadata or retained redo")
    finally:
        await check.close(sid)
    async with check.project() as target:
        target_before = await check.call("project_status", session_id=target)
        await check.rejected("project_merge", "controller extension", session_id=target, path=str(source),
                             include_tracks=True, include_tempo=False)
        v.require(await check.call("project_status", session_id=target) == target_before,
                  "Guarded controller source merge changed target")
    v.require(source.read_bytes() == original, "Controller note edits changed source archive")


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "preservation.controller_note_edits_22"])
    raise SystemExit(v.main())
