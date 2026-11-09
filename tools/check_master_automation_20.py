"""Track unknown master-volume event fields through native automation edits."""
import json
import sys
import zipfile

import verify_features as v

KEY = "x_master_volume_20"


@v.feature("preservation.master_volume_extensions", "preservation", "project_create", "project_edit",
           "project_save", "project_open", "project_clone")
async def master_volume_extensions(check):
    async with check.project() as seed:
        await check.edit(seed, "track.create", type="MidiAi", name="Synthetic AI")
        spec = await check.edit(seed, "automation.list", scope="master_volume")
        default, minimum, maximum = spec["default_value"], spec["minimum"], spec["maximum"]
        await check.edit(seed, "automation.set", scope="master_volume", replace=True,
                         points=[{"tick": 0, "value": default}, {"tick": 480, "value": minimum},
                                 {"tick": 960, "value": maximum}])
        sequence, source_seed = await check.save(seed, "master-volume-seed")
    _, members = v.read_vpr(source_seed)
    for event in sequence["masterTrack"]["volume"]["events"]:
        event[KEY] = {"original_tick": event["pos"], "nested": [True, None]}
    sequence["masterTrack"]["tempo"]["events"][0][KEY] = {"owner": "tempo"}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("master-volume-extended")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    original = source.read_bytes()

    def marker(tick):
        return {"original_tick": tick, "nested": [True, None]}

    def events(project):
        return [(event["pos"], event["value"], event.get(KEY))
                for event in project["masterTrack"]["volume"]["events"]]

    sid = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        before, _ = await check.save(sid, "master-volume-before")
        initial = [(0, default, marker(0)), (480, minimum, marker(480)), (960, maximum, marker(960))]
        v.require(events(before) == initial, "Master volume input metadata differs", events(before))
        tempo_before = before["masterTrack"]["tempo"]["events"]
        v.require(tempo_before[0][KEY] == {"owner": "tempo"}, "Mixed tempo metadata is absent")
        await check.edit(sid, "automation.set", scope="master_volume",
                         points=[{"tick": 480, "value": default}, {"tick": 720, "value": minimum}])
        upsert, _ = await check.save(sid, "master-volume-upsert")
        upsert_expected = [(0, default, marker(0)), (480, default, marker(480)),
                           (720, minimum, None), (960, maximum, marker(960))]
        v.require(events(upsert) == upsert_expected, "Master volume upsert metadata differs", events(upsert))
        await check.edit(sid, "automation.set", scope="master_volume", replace=True,
                         points=[{"tick": 480, "value": maximum}, {"tick": 1200, "value": minimum}])
        replaced, _ = await check.save(sid, "master-volume-replaced")
        v.require(replaced["masterTrack"]["tempo"]["events"] == tempo_before,
                  "Master volume edit changed tempo extension")
        replace_expected = [(0, default, marker(0)), (480, maximum, marker(480)), (1200, minimum, None)]
        v.require(events(replaced) == replace_expected, "Master volume replace metadata differs", events(replaced))
        await check.edit(sid, "undo")
        undone, _ = await check.save(sid, "master-volume-replace-undo")
        v.require(events(undone) == upsert_expected, "Master volume undo differs", events(undone))
        await check.edit(sid, "redo")
        redone, _ = await check.save(sid, "master-volume-replace-redo")
        v.require(events(redone) == replace_expected, "Master volume redo differs", events(redone))
        await check.edit(sid, "automation.remove", scope="master_volume", event_index=1)
        await check.edit(sid, "automation.set", scope="master_volume", points=[{"tick": 480, "value": maximum}])
        recreated, _ = await check.save(sid, "master-volume-recreated")
        v.require(events(recreated) == [(0, default, marker(0)), (480, maximum, None), (1200, minimum, None)],
                  "Recreated event inherited deleted metadata", events(recreated))
        await check.edit(sid, "undo")
        await check.edit(sid, "undo")
        restored, _ = await check.save(sid, "master-volume-remove-undo")
        v.require(events(restored) == replace_expected, "Master volume remove history lost fields", events(restored))
        before_history = await check.edit(sid, "history.status")
        await check.rejected("project_edit", "project_preservation", session_id=sid, operation="time.insert",
                             options={"start_tick": 100, "duration_tick": 200, "include_tempo": False})
        after_guard, _ = await check.save(sid, "master-volume-time-guard")
        v.require(events(after_guard) == replace_expected and await check.edit(sid, "history.status") == before_history,
                  "Rejected master-volume timeline edit changed state")
        clone = (await check.call("project_clone", session_id=sid))["session_id"]
        try:
            cloned, clone_path = await check.save(clone, "master-volume-clone")
            v.require(events(cloned) == replace_expected, "Clone lost master volume fields", events(cloned))
            reopened = (await check.call("project_open", path=str(clone_path)))["session_id"]
            try:
                reopened_json, _ = await check.save(reopened, "master-volume-reopened")
                v.require(events(reopened_json) == replace_expected, "Reopen lost master volume fields", events(reopened_json))
                v.require(reopened_json["masterTrack"]["tempo"]["events"] == tempo_before,
                          "Reopen lost mixed tempo extension")
            finally:
                await check.close(reopened)
        finally:
            await check.close(clone)
    finally:
        await check.close(sid)
    v.require(source.read_bytes() == original, "Master volume source archive changed")
    duplicate = json.loads(json.dumps(sequence))
    duplicate["masterTrack"]["volume"]["events"].append(
        json.loads(json.dumps(duplicate["masterTrack"]["volume"]["events"][1])))
    members["Project/sequence.json"] = json.dumps(duplicate, ensure_ascii=False).encode("utf-8")
    invalid = v.ROOT / "output" / check.output("master-volume-duplicate-tick")
    with zipfile.ZipFile(invalid, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    invalid_original = invalid.read_bytes()
    await check.rejected("project_open", "duplicate|project_preservation", path=str(invalid))
    v.require(invalid.read_bytes() == invalid_original, "Rejected duplicate event changed source")
    mixed = json.loads(json.dumps(sequence))
    mixed["tracks"][0]["volume"]["events"][0][KEY] = "track-volume-mixed"
    members["Project/sequence.json"] = json.dumps(mixed, ensure_ascii=False).encode("utf-8")
    mixed_path = v.ROOT / "output" / check.output("master-and-track-volume")
    with zipfile.ZipFile(mixed_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    mixed_original = mixed_path.read_bytes()
    sid = (await check.call("project_open", path=str(mixed_path)))["session_id"]
    try:
        before, _ = await check.save(sid, "master-track-before")
        bounds = await check.edit(sid, "automation.list", scope="track_volume", track_index=0)
        await check.edit(sid, "automation.set", scope="track_volume", track_index=0,
                         points=[{"tick": 0, "value": bounds["maximum"]}])
        after, _ = await check.save(sid, "master-track-after")
        v.require(after["tracks"][0]["volume"]["events"][0][KEY] == "track-volume-mixed" and
                  events(after) == events(before), "Mixed track edit lost master or track fields")
        await check.edit(sid, "undo")
        undone, _ = await check.save(sid, "master-track-undo")
        v.require(undone == before, "Mixed master/track undo differs")
        await check.edit(sid, "redo")
        redone, _ = await check.save(sid, "master-track-redo")
        v.require(redone == after, "Mixed master/track redo differs")
    finally:
        await check.close(sid)
    v.require(mixed_path.read_bytes() == mixed_original, "Mixed volume source archive changed")


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "preservation.master_volume_extensions"])
    raise SystemExit(v.main())
