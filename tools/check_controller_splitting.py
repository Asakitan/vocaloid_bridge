"""Controller identity through native AI split, join and duplicate."""
import json
import zipfile

import verify_features as v

KEY = "x_controller_split"


def lanes(sequence):
    return [[(e["pos"], e["value"], e.get(KEY))
             for e in next((c["events"] for c in p.get("controllers", []) if c["name"] == "dynamics"), [])]
            for p in sequence["tracks"][0]["parts"]]


@v.feature("preservation.controller_split_generated_probe", "preservation", "score_compose", "project_edit", "project_save")
async def controller_split_generated_probe(check):
    seed = await check.call("score_compose", output_name=check.output("controller-generated-seed"),
                            title="Controller generated boundary", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    try:
        await check.edit(sid, "controller.set", track_index=0, part_index=0, type="Dynamics", replace=True,
                         points=[{"tick": 180, "value": 64}, {"tick": 240, "value": 40}])
        await check.edit(sid, "part.split", track_index=0, part_index=0, split_tick=480)
        saved, _ = await check.save(sid, "controller-generated-split")
        split = lanes(saved)
        await check.edit(sid, "part.join", track_index=0, part_indices=[0, 1])
        joined, _ = await check.save(sid, "controller-generated-join")
        check.evidence("controller_generated_native", {"split": split, "join": lanes(joined)})
    finally:
        await check.close(sid)


@v.feature("preservation.controller_split_boundary", "preservation", "score_compose", "project_open",
           "project_edit", "project_save", "project_clone")
async def controller_split_boundary(check):
    seed = await check.call("score_compose", output_name=check.output("controller-boundary-seed"),
                            title="Controller boundary", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    seed_id = seed["native_session"]["session_id"]
    await check.edit(seed_id, "controller.set", track_index=0, part_index=0, type="Dynamics", replace=True,
                     points=[{"tick": 60, "value": 30}, {"tick": 480, "value": 40}, {"tick": 720, "value": 50}])
    original_json, original_path = await check.save(seed_id, "controller-boundary-native")
    await check.edit(seed_id, "part.split", track_index=0, part_index=0, split_tick=480)
    plain_split, _ = await check.save(seed_id, "controller-boundary-plain-split")
    await check.edit(seed_id, "part.join", track_index=0, part_indices=[0, 1])
    plain_join, _ = await check.save(seed_id, "controller-boundary-plain-join")
    await check.close(seed_id)
    _, members = v.read_vpr(original_path)
    plain_lanes, joined_lanes = lanes(plain_split), lanes(plain_join)

    def fixture(label, mark_controllers):
        seq = json.loads(json.dumps(original_json))
        part = seq["tracks"][0]["parts"][0]
        if mark_controllers:
            events = next(c["events"] for c in part["controllers"] if c["name"] == "dynamics")
            for index, event in enumerate(events): event[KEY] = {"event": index}
        else:
            part["x_other_extension"] = "part"
        archive_members = dict(members)
        archive_members["Project/sequence.json"] = json.dumps(seq, ensure_ascii=False).encode("utf-8")
        path = v.ROOT / "output" / check.output(label)
        with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in archive_members.items(): archive.writestr(name, payload)
        return path

    other = fixture("controller-ordinary-with-part-extension", False)
    sid = (await check.call("project_open", path=str(other)))["session_id"]
    try:
        await check.edit(sid, "part.split", track_index=0, part_index=0, split_tick=480)
        saved, _ = await check.save(sid, "controller-ordinary-split")
        v.require(lanes(saved) == plain_lanes, "Unextended controller split changed native semantics")
        await check.edit(sid, "part.join", track_index=0, part_indices=[0, 1])
        saved, _ = await check.save(sid, "controller-ordinary-join")
        v.require(lanes(saved) == joined_lanes and saved["tracks"][0]["parts"][0]["x_other_extension"] == "part",
                  "Unextended controller join changed native semantics")
    finally:
        await check.close(sid)

    source = fixture("controller-boundary-extended", True)
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        name = (await check.edit(sid, "track.list"))["tracks"][0]["name"]
        await check.edit(sid, "track.duplicate", track_index=0, name=name)
        saved, _ = await check.save(sid, "controller-boundary-track-copy")
        v.require(lanes(saved) == [[(60, 30, {"event": 0}), (480, 40, {"event": 1}), (720, 50, {"event": 2})]] and
                  saved["tracks"][1]["parts"][0]["controllers"] == saved["tracks"][0]["parts"][0]["controllers"],
                  "Track duplicate lost controller extensions")
        await check.edit(sid, "undo")
        await check.edit(sid, "part.split", track_index=0, part_index=0, split_tick=480)
        expected_split = [[(60, 30, {"event": 0})], [(0, 40, {"event": 1}), (240, 50, {"event": 2})]]
        saved, _ = await check.save(sid, "controller-boundary-split")
        v.require(lanes(saved) == expected_split, "Boundary event metadata changed", lanes(saved))
        await check.edit(sid, "part.join", track_index=0, part_indices=[0, 1])
        expected_join = [[(60, 30, {"event": 0}), (480, 40, {"event": 1}), (720, 50, {"event": 2})]]
        saved, _ = await check.save(sid, "controller-boundary-join")
        v.require(lanes(saved) == expected_join, "Joined controller metadata changed", lanes(saved))
        await check.edit(sid, "undo")
        saved, _ = await check.save(sid, "controller-boundary-undo")
        v.require(lanes(saved) == expected_split, "Undo join lost controller metadata")
        await check.edit(sid, "redo")
        saved, path = await check.save(sid, "controller-boundary-redo")
        v.require(lanes(saved) == expected_join, "Redo join lost controller metadata")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        try:
            saved, _ = await check.save(reopened, "controller-boundary-reopened")
            v.require(lanes(saved) == expected_join, "Reopen lost controller metadata")
        finally:
            await check.close(reopened)
        await check.edit(sid, "part.duplicate", track_index=0, part_index=0, start_tick=240)
        await check.edit(sid, "controller.set", track_index=0, part_index=1, type="Dynamics", controller_index=1,
                         points=[{"tick": 240, "value": 40}])
        before, _ = await check.save(sid, "controller-overlap-before")
        status = await check.call("project_status", session_id=sid)
        history = await check.edit(sid, "history.status")
        await check.rejected("project_edit", "overlap|controller|join", session_id=sid,
                             operation="part.join", options={"track_index": 0, "part_indices": [0, 1]})
        v.require(await check.call("project_status", session_id=sid) == status and
                  await check.edit(sid, "history.status") == history, "Rejected overlap changed source state")
        after, _ = await check.save(sid, "controller-overlap-after")
        v.require(after == before, "Rejected overlap changed controller archive")
        v.require(source.read_bytes() == original, "Controller split changed source VPR")
    finally:
        await check.close(sid)


if __name__ == "__main__":
    raise SystemExit(v.main())
