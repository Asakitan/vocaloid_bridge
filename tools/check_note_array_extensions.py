"""Probe direct-pitch serialization and edit identity in an isolated native session."""
import json
import zipfile
import verify_features as v


@v.feature("preservation.note_pitch_array_probe", "preservation", "score_compose", "project_edit", "project_save")
async def note_pitch_array_probe(check):
    seed = await check.call("score_compose", output_name=check.output("note-array-seed"),
                            title="Note array probe", bpm=120,
                            notes=[{"start": 0, "duration": 2, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    target = {"track_index": 0, "part_index": 0, "note_index": 0}
    async def save(label):
        sequence, _ = await check.save(sid, "note-array-" + label)
        note = sequence["tracks"][0]["parts"][0]["notes"][0]
        check.evidence(label, {"directPitches": note.get("directPitches"),
                               "phonemePositions": note.get("phonemePositions")})
    await check.edit(sid, "pitch.set", **target, replace=True,
                     points=[{"tick": 100, "value": 60}, {"tick": 300, "value": 62}])
    await save("before")
    await check.edit(sid, "pitch.set", **target, replace=False,
                     points=[{"tick": 100, "value": 61}])
    await save("upsert")
    await check.edit(sid, "pitch.clear", **target, begin_tick=90, end_tick=110)
    await save("clear")
    await check.close(sid)


@v.feature("preservation.note_pitch_transitions", "preservation", "score_compose", "project_edit", "project_save", "project_open", "project_clone")
async def note_pitch_transitions(check):
    seed = await check.call("score_compose", output_name=check.output("pitch-transitions-seed"), title="Pitch transitions", bpm=120,
                            notes=[{"start": 0, "duration": 2, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    scope = {"track_index": 0, "part_index": 0}
    target = {**scope, "note_index": 0}
    async def snapshot(session, label):
        sequence, path = await check.save(session, "pitch-transitions-" + label)
        notes = sequence["tracks"][0]["parts"][0]["notes"]
        check.evidence(label, json.loads(json.dumps([{"pos": n.get("pos"), "duration": n.get("duration"),
                                "directPitches": n.get("directPitches")} for n in notes])))
        return sequence, path
    async def setpoints(points, replace=False):
        return await check.edit(sid, "pitch.set", **target, replace=replace,
                                points=[{"tick": tick, "value": value} for tick, value in points])
    await setpoints([(100, 60), (300, 62)], True)
    await snapshot(sid, "initial")
    await setpoints([(200, 61)])
    await snapshot(sid, "insert")
    await setpoints([(100, 63), (400, 64)], True)
    await snapshot(sid, "replace")
    await check.edit(sid, "pitch.clear", **target, begin_tick=90, end_tick=399)
    await snapshot(sid, "clear_interior")
    await check.edit(sid, "undo")
    await snapshot(sid, "undo_clear")
    await check.edit(sid, "redo")
    await snapshot(sid, "redo_clear")
    await setpoints([(100, 60), (300, 62)], True)
    await check.edit(sid, "note.update", **target, start_tick=100, number=61)
    sequence, source = await snapshot(sid, "note_update")
    clone = (await check.call("project_clone", session_id=sid, title="Pitch clone"))["session_id"]
    await snapshot(clone, "clone")
    await check.close(clone)
    reopened = (await check.call("project_open", path=str(source)))["session_id"]
    await snapshot(reopened, "reopen")
    await check.close(reopened)
    await check.edit(sid, "note.duplicate", **target, start_tick=1200)
    await snapshot(sid, "duplicate")
    await check.edit(sid, "note.remove", **scope, note_index=1)
    await check.edit(sid, "note.split", **target, split_tick=480)
    await snapshot(sid, "split")
    await check.edit(sid, "note.join", **scope, note_indices=[0, 1])
    await snapshot(sid, "join")
    await check.close(sid)
    # Exercise the current archive guard with an independently copied fixture.
    _, members = v.read_vpr(source)
    sequence["tracks"][0]["parts"][0]["notes"][0]["directPitches"][0]["x_probe"] = {"marker": [1, True]}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    fixture = v.ROOT / "output" / check.output("pitch-unknown-field")
    with zipfile.ZipFile(fixture, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = fixture.read_bytes()
    await check.rejected("project_open", "unsupported nested unknown field", path=str(fixture))
    v.require(fixture.read_bytes() == original, "Rejected fixture was modified")
    check.evidence("unknown_guard", {"path": str(fixture), "unchanged": True})


if __name__ == "__main__":
    raise SystemExit(v.main())
