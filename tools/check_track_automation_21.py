"""Track unknown volume and pan event fields through native automation edits."""
import json
import sys
import zipfile

import verify_features as v
from check_project_preservation import preserved_edit

KEY = "x_track_automation_21"


@v.feature("preservation.track_volume_extensions", "preservation", "project_create", "project_edit", "project_save", "project_open", "project_clone")
async def track_volume_extensions(check):
    await track_automation_extensions(check, "track_volume", "volume")


@v.feature("preservation.track_pan_extensions", "preservation", "project_create", "project_edit", "project_save", "project_open", "project_clone")
async def track_pan_extensions(check):
    await track_automation_extensions(check, "track_pan", "panpot")


async def track_automation_extensions(check, scope, prop):
    async with check.project() as seed:
        await check.edit(seed, "track.create", type="MidiAi", name="Synthetic AI")
        spec = await check.edit(seed, "automation.list", scope=scope, track_index=0)
        default, minimum, maximum = spec["default_value"], spec["minimum"], spec["maximum"]
        await check.edit(seed, "automation.set", scope=scope, track_index=0, replace=True,
                         points=[{"tick": 0, "value": default}, {"tick": 480, "value": minimum},
                                 {"tick": 960, "value": maximum}])
        sequence, source_seed = await check.save(seed, "master-volume-seed")
    _, members = v.read_vpr(source_seed)
    for event in sequence["tracks"][0][prop]["events"]:
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
                for event in project["tracks"][0][prop]["events"]]

    sid = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        before, _ = await check.save(sid, "master-volume-before")
        initial = [(0, default, marker(0)), (480, minimum, marker(480)), (960, maximum, marker(960))]
        v.require(events(before) == initial, "Master volume input metadata differs", events(before))
        tempo_before = before["masterTrack"]["tempo"]["events"]
        v.require(tempo_before[0][KEY] == {"owner": "tempo"}, "Mixed tempo metadata is absent")
        await check.edit(sid, "automation.set", scope=scope, track_index=0,
                         points=[{"tick": 480, "value": default}, {"tick": 720, "value": minimum}])
        upsert, _ = await check.save(sid, "master-volume-upsert")
        upsert_expected = [(0, default, marker(0)), (480, default, marker(480)),
                           (720, minimum, None), (960, maximum, marker(960))]
        v.require(events(upsert) == upsert_expected, "Master volume upsert metadata differs", events(upsert))
        await check.edit(sid, "automation.set", scope=scope, track_index=0, replace=True,
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
        await check.edit(sid, "automation.remove", scope=scope, track_index=0, event_index=1)
        await check.edit(sid, "automation.set", scope=scope, track_index=0, points=[{"tick": 480, "value": maximum}])
        recreated, _ = await check.save(sid, "master-volume-recreated")
        v.require(events(recreated) == [(0, default, marker(0)), (480, maximum, None), (1200, minimum, None)],
                  "Recreated event inherited deleted metadata", events(recreated))
        await check.edit(sid, "undo")
        await check.edit(sid, "undo")
        restored, _ = await check.save(sid, "master-volume-remove-undo")
        v.require(events(restored) == replace_expected, "Master volume remove history lost fields", events(restored))
        _, shifted = await preserved_edit(check, sid, "time.insert",
            start_tick=100, duration_tick=200, include_tempo=False)
        boundary_value = round(default + (maximum - default) * 100 / 480)
        expected_shifted = sorted([(tick + (200 if tick > 100 else 0), value, metadata)
                                   for tick, value, metadata in replace_expected] +
                                  [(100, boundary_value, None), (300, boundary_value, None)])
        v.require(events(shifted) == expected_shifted,
                  "Timeline insertion lost automation identity", events(shifted))
        v.require(shifted["masterTrack"]["tempo"]["events"] == tempo_before,
                  "Timeline insertion changed excluded tempo metadata")
        _, duplicated = await preserved_edit(check, sid, "track.duplicate", track_index=0)
        v.require(len(duplicated["tracks"]) == 2 and
                  duplicated["tracks"][1][prop] == duplicated["tracks"][0][prop],
                  "Track duplication lost automation metadata")
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
    async with check.project() as target:
        target_before, _ = await check.save(target, "track-automation-merge-before")
        await check.call("project_merge", session_id=target,
                         path=str(source), include_tracks=True, include_tempo=False)
        merged, merged_path = await check.save(target, "track-automation-merge")
        v.require(events(merged) == initial and merged["masterTrack"]["tempo"] == target_before["masterTrack"]["tempo"],
                  "Track merge lost automation metadata or changed excluded tempo")
        await check.edit(target, "undo")
        undone, _ = await check.save(target, "track-automation-merge-undo")
        v.require(undone == target_before, "Track automation merge undo differs")
        await check.edit(target, "redo")
        redone, _ = await check.save(target, "track-automation-merge-redo")
        v.require(redone == merged, "Track automation merge redo differs")
        reopened = (await check.call("project_open", path=str(merged_path)))["session_id"]
        restored, _ = await check.save(reopened, "track-automation-merge-reopen")
        v.require(restored == merged, "Track automation merge reopen differs")
        await check.close(reopened)
    v.require(source.read_bytes() == original, "Track automation source archive changed")
    ambiguous = json.loads(json.dumps(sequence))
    same_track = json.loads(json.dumps(ambiguous["tracks"][0]))
    same_track[prop]["events"][0][KEY] = {"different": True}
    ambiguous["tracks"].append(same_track)
    members["Project/sequence.json"] = json.dumps(ambiguous, ensure_ascii=False).encode("utf-8")
    invalid_ambiguous = v.ROOT / "output" / check.output("track-automation-ambiguous")
    with zipfile.ZipFile(invalid_ambiguous, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    ambiguous_original = invalid_ambiguous.read_bytes()
    await check.rejected("project_open", "ambiguous|indistinguishable|project_preservation", path=str(invalid_ambiguous))
    v.require(invalid_ambiguous.read_bytes() == ambiguous_original, "Rejected ambiguous archive changed")
    distinguishable = json.loads(json.dumps(ambiguous))
    distinguishable["tracks"][1][prop]["events"][0]["value"] = minimum
    members["Project/sequence.json"] = json.dumps(distinguishable, ensure_ascii=False).encode("utf-8")
    collision_source = v.ROOT / "output" / check.output("track-automation-collision-source")
    with zipfile.ZipFile(collision_source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    collision_original = collision_source.read_bytes()
    collision_sid = (await check.call("project_open", path=str(collision_source)))["session_id"]
    try:
        collision_before, _ = await check.save(collision_sid, "track-automation-collision-before")
        v.require(collision_before["tracks"][0][prop]["events"][0]["value"] == default and
                  collision_before["tracks"][1][prop]["events"][0]["value"] == minimum and
                  collision_before["tracks"][0][prop]["events"][0][KEY] !=
                  collision_before["tracks"][1][prop]["events"][0][KEY],
                  "Collision fixture lost distinct known values or opaque identities")
        collision_history = await check.edit(collision_sid, "history.status")
        collision_status = await check.call("project_status", session_id=collision_sid)
        await check.rejected("project_edit", "ambiguous|indistinguishable|project_preservation",
                             session_id=collision_sid, operation="automation.set",
                             options={"scope": scope, "track_index": 1,
                                      "points": [{"tick": 0, "value": default}]})
        v.require(await check.edit(collision_sid, "history.status") == collision_history and
                  await check.call("project_status", session_id=collision_sid) == collision_status,
                  "Rejected automation identity collision changed history or dirty state")
        collision_after, _ = await check.save(collision_sid, "track-automation-collision-after")
        v.require(collision_after == collision_before and collision_source.read_bytes() == collision_original,
                  "Rejected automation identity collision changed saved data or source")
        check.evidence("automation_identity_collision", {"scope": scope, "rejected_before_mutation": True,
                                                        "source": str(collision_source)})
    finally:
        await check.close(collision_sid)
    duplicate = json.loads(json.dumps(sequence))
    duplicate["tracks"][0][prop]["events"].append(
        json.loads(json.dumps(duplicate["tracks"][0][prop]["events"][1])))
    members["Project/sequence.json"] = json.dumps(duplicate, ensure_ascii=False).encode("utf-8")
    invalid = v.ROOT / "output" / check.output("master-volume-duplicate-tick")
    with zipfile.ZipFile(invalid, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    invalid_original = invalid.read_bytes()
    await check.rejected("project_open", "duplicate|project_preservation", path=str(invalid))
    v.require(invalid.read_bytes() == invalid_original, "Rejected duplicate event changed source")


@v.feature("preservation.track_volume_identity", "preservation", "project_create", "project_edit", "project_save", "project_open")
async def track_volume_identity(check):
    await track_automation_identity(check, "track_volume", "volume")


@v.feature("preservation.track_pan_identity", "preservation", "project_create", "project_edit", "project_save", "project_open")
async def track_pan_identity(check):
    await track_automation_identity(check, "track_pan", "panpot")


async def track_automation_identity(check, scope, prop):
    async with check.project() as seed:
        for name in ("AI A", "AI B"):
            await check.edit(seed, "track.create", type="MidiAi", name=name)
        _, seed_path = await check.save(seed, "track-identity-seed")
    sequence, members = v.read_vpr(seed_path)
    for index, track in enumerate(sequence["tracks"]):
        track[prop]["events"][0][KEY] = {"track": index}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("track-identity-source")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    original = source.read_bytes()

    def owners(project):
        return [(track["name"], track[prop]["events"][0].get(KEY)) for track in project["tracks"]]

    sid = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        initial = [("AI A", {"track": 0}), ("AI B", {"track": 1})]
        renamed = [("AI A renamed", {"track": 0}), initial[1]]
        reordered = [renamed[1], renamed[0]]
        await check.edit(sid, "track.update", track_index=0, name="AI A renamed", color=6, mute=True)
        changed, _ = await check.save(sid, "track-identity-update")
        v.require(owners(changed) == renamed and changed["tracks"][0]["color"] == 6 and changed["tracks"][0]["isMuted"],
                  "Track update lost owner metadata", owners(changed))
        await check.edit(sid, "track.reorder", track_index=1, to_index=0)
        moved, _ = await check.save(sid, "track-identity-reorder")
        v.require(owners(moved) == reordered, "Track reorder lost owner metadata", owners(moved))
        await check.edit(sid, "undo")
        undone, _ = await check.save(sid, "track-identity-reorder-undo")
        v.require(owners(undone) == renamed, "Reorder undo lost owner metadata", owners(undone))
        await check.edit(sid, "undo")
        undone_update, _ = await check.save(sid, "track-identity-update-undo")
        v.require(owners(undone_update) == initial, "Update undo lost owner metadata", owners(undone_update))
        await check.edit(sid, "redo")
        await check.edit(sid, "redo")
        redone, path = await check.save(sid, "track-identity-redo")
        v.require(owners(redone) == reordered, "Redo lost owner metadata", owners(redone))
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        try:
            reopened_json, _ = await check.save(reopened, "track-identity-reopened")
            v.require(owners(reopened_json) == reordered, "Reopen lost owner metadata", owners(reopened_json))
        finally:
            await check.close(reopened)
    finally:
        await check.close(sid)
    v.require(source.read_bytes() == original, "Track identity source changed")


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "preservation.track_volume_extensions", "--case", "preservation.track_pan_extensions", "--case", "preservation.track_volume_identity", "--case", "preservation.track_pan_identity"])
    raise SystemExit(v.main())
