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
    # The extended point belongs to an independently copied fixture.
    _, members = v.read_vpr(source)
    sequence["tracks"][0]["parts"][0]["notes"][0]["directPitches"][0]["x_probe"] = {"marker": [1, True]}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    fixture = v.ROOT / "output" / check.output("pitch-unknown-field")
    with zipfile.ZipFile(fixture, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = fixture.read_bytes()
    extended = (await check.call("project_open", path=str(fixture)))['session_id']
    try:
        retained, _ = await check.save(extended, "pitch-unknown-retained")
        v.require(retained["tracks"][0]["parts"][0]["notes"][0]["directPitches"][0]["x_probe"] == {"marker": [1, True]},
                  "Extended pitch metadata was not retained")
    finally:
        await check.close(extended)
    v.require(fixture.read_bytes() == original, "Source fixture was modified")
    check.evidence("unknown_retained", {"path": str(fixture), "unchanged": True})


@v.feature("preservation.note_pitch_extension_roundtrip", "preservation", "score_compose", "project_edit", "project_save", "project_open", "project_clone")
async def note_pitch_extension_roundtrip(check):
    """Expected-success regression against the previous guarded host."""
    from check_project_preservation import preserved_edit

    product = (await check.call("vocaloid_features"))["product"]
    seed = await check.call("score_compose", output_name=check.output("pitch-ext-seed"), title="Pitch extension", bpm=120,
                            notes=[{"start": 0, "duration": 2, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    target = {"track_index": 0, "part_index": 0, "note_index": 0}
    await check.edit(sid, "pitch.set", **target, replace=True,
                     points=[{"tick": 100, "value": 60}, {"tick": 300, "value": 62}])
    sequence, source = await check.save(sid, "pitch-ext-source")
    await check.close(sid)
    _, members = v.read_vpr(source)
    points = sequence["tracks"][0]["parts"][0]["notes"][0]["directPitches"]
    v.require(len(points) == 2, "Fixture needs two native points", points)
    points[0]["x_identity"] = {"marker": "first", "nested": [1, True]}
    points[1]["x_identity"] = {"marker": "second"}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    fixture = v.ROOT / "output" / check.output("pitch-ext-input")
    with zipfile.ZipFile(fixture, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    check.evidence("extended_fixture", str(fixture))
    source_bytes = fixture.read_bytes()
    sid = (await check.call("project_open", path=str(fixture)))["session_id"]

    async def snapshot(label):
        data, _ = await check.save(sid, "pitch-ext-" + label)
        found = data["tracks"][0]["parts"][0]["notes"][0].get("directPitches", [])
        check.evidence(label, found)
        return found

    initial = await snapshot("initial")
    v.require(initial == points, "Open/save changed extended points", initial)
    history = await check.edit(sid, "history.status")
    clipboard = await check.call("project_clipboard", session_id=sid, operation="copy",
                                options={"kind": "notes", "indices": [0], "track_index": 0, "part_index": 0})
    v.require(await check.edit(sid, "history.status") == history, "Copy changed source history")
    before_paste, _ = await check.save(sid, "pitch-copy-before")
    await check.call("project_clipboard", session_id=sid, operation="paste",
                     options={"clipboard_id": clipboard["clipboard_id"], "track_index": 0,
                              "part_index": 0, "offset_tick": 3000})
    pasted, pasted_path = await check.save(sid, "pitch-copy-pasted")
    copied_notes = pasted["tracks"][0]["parts"][0]["notes"]
    v.require(len(copied_notes) == 2 and all(note["directPitches"] == initial for note in copied_notes),
              "Clipboard paste lost pitch point identity")
    await check.edit(sid, "undo")
    undone, _ = await check.save(sid, "pitch-copy-undo")
    v.require(undone == before_paste, "Pitch clipboard undo differs")
    await check.edit(sid, "redo")
    redone, _ = await check.save(sid, "pitch-copy-redo")
    v.require(redone == pasted, "Pitch clipboard redo differs")
    reopened = (await check.call("project_open", path=str(pasted_path)))["session_id"]
    restored, _ = await check.save(reopened, "pitch-copy-reopen")
    v.require(restored == pasted, "Pitch clipboard reopen differs")
    await check.close(reopened)
    await check.edit(sid, "undo")
    if product == "VOCALOID7":
        await check.rejected("project_library", "VOCALOID7.*media|VOCALOID7.*VMM|not supported",
                             session_id=sid, operation="media_capture",
                             options={"track_index": 0, "part_index": 0, "name": "pitch metadata"})
        check.evidence("media_scope", {"product": product, "supported": False})
    else:
        clip = (await check.library("media_capture", sid, track_index=0, part_index=0,
                                    name="Pitch metadata " + check.run_id))["clip"]
        try:
            async with check.project() as media_target:
                await check.edit(media_target, "track.create", type="MidiAi", name="Pitch media")
                await check.library("media_import", media_target, clip_id=clip["clip_id"], track_index=0, position_tick=0)
                imported, _ = await check.save(media_target, "pitch-media-import")
                v.require(imported["tracks"][0]["parts"][0]["notes"][0]["directPitches"] == initial,
                          "Media transfer lost pitch metadata")
        finally:
            await check.library("media_delete", sid, clip_id=clip["clip_id"])
    async with check.project() as destination:
        before, _ = await check.save(destination, "pitch-merge-before")
        await check.call("project_merge", session_id=destination,
                         path=str(fixture), include_tracks=True, include_tempo=False)
        merged, merged_path = await check.save(destination, "pitch-merge-after")
        v.require(merged["tracks"][-1]["parts"][0]["notes"][0]["directPitches"] == initial,
                  "Merge lost direct pitch metadata")
        await check.edit(destination, "undo")
        undone, _ = await check.save(destination, "pitch-merge-undo")
        v.require(undone == before, "Pitch merge undo differs")
        await check.edit(destination, "redo")
        redone, _ = await check.save(destination, "pitch-merge-redo")
        v.require(redone == merged, "Pitch merge redo differs")
        reopened = (await check.call("project_open", path=str(merged_path)))["session_id"]
        restored, _ = await check.save(reopened, "pitch-merge-reopen")
        v.require(restored == merged, "Pitch merge reopen differs")
        await check.close(reopened)
    _, split = await preserved_edit(check, sid, "note.split", **target, split_tick=480)
    split_notes = split["tracks"][0]["parts"][0]["notes"]
    v.require(len(split_notes) == 2, "Note split did not produce two notes")
    for note in split_notes:
        retained = [{**point, "pos": point["pos"] + note["pos"]}
                    for point in note["directPitches"] if "x_identity" in point]
        generated = [point for point in note["directPitches"] if "x_identity" not in point]
        v.require(retained == initial and generated == [{"pos": 1440, "value": "ZeroPitch"}],
                  "Note split lost point identity or marked a generated sentinel", note["directPitches"])
    await check.edit(sid, "note.split", **target, split_tick=480)
    _, joined = await preserved_edit(check, sid, "note.join", track_index=0, part_index=0, note_indices=[0, 1])
    joined_points = joined["tracks"][0]["parts"][0]["notes"][0]["directPitches"]
    v.require([point for point in joined_points if "x_identity" in point] == initial and
              all(point["value"] == "ZeroPitch" for point in joined_points if "x_identity" not in point),
              "Note join lost retained direct pitch metadata", joined_points)
    await check.edit(sid, "undo")
    _, distant = await preserved_edit(check, sid, "time.insert", start_tick=20000, duration_tick=480, include_tempo=False)
    v.require(distant["tracks"][0]["parts"][0]["notes"][0]["directPitches"] == initial,
              "Distant timeline insertion changed direct pitch metadata")
    await check.rejected("project_edit", "distinct ticks", session_id=sid, operation="pitch.set",
                         options={**target, "points": [{"tick": 100, "value": 60}, {"tick": 100, "value": 61}]})
    v.require(await snapshot("rejected_operations") == initial, "Rejected operation changed extension state")
    await check.edit(sid, "note.update", **target, start_tick=100, number=61)
    v.require(await snapshot("note_update") == initial, "Note update changed direct pitch metadata")
    await check.edit(sid, "undo")
    v.require(await snapshot("undo_note_update") == initial, "Undo note update changed direct pitch metadata")
    clone = (await check.call("project_clone", session_id=sid, title="Pitch metadata clone"))["session_id"]
    clone_sequence, clone_path = await check.save(clone, "pitch-ext-clone")
    v.require(clone_sequence["tracks"][0]["parts"][0]["notes"][0]["directPitches"] == initial,
              "Clone changed direct pitch metadata")
    await check.close(clone)
    reopened = (await check.call("project_open", path=str(clone_path)))["session_id"]
    reopened_sequence, _ = await check.save(reopened, "pitch-ext-reopened")
    v.require(reopened_sequence["tracks"][0]["parts"][0]["notes"][0]["directPitches"] == initial,
              "Reopen changed direct pitch metadata")
    await check.close(reopened)
    await check.edit(sid, "pitch.set", **target, replace=False,
                     points=[{"tick": 100, "value": 61}, {"tick": 200, "value": 60}])
    upsert = await snapshot("upsert")
    by_tick = {item["pos"]: item for item in upsert}
    v.require(set(by_tick) == {100, 200, 300} and
              by_tick[100].get("x_identity") == points[0]["x_identity"] and
              "x_identity" not in by_tick[200] and
              by_tick[300].get("x_identity") == points[1]["x_identity"],
              "Upsert changed point metadata identity", upsert)
    await check.edit(sid, "undo")
    v.require(await snapshot("undo_upsert") == initial, "Undo did not restore upsert metadata")
    await check.edit(sid, "redo")
    v.require(await snapshot("redo_upsert") == upsert, "Redo did not restore upsert metadata")
    await check.edit(sid, "undo")
    await check.edit(sid, "pitch.clear", **target, begin_tick=90, end_tick=110)
    cleared = await snapshot("cleared")
    v.require(len(cleared) == 1 and cleared[0].get("x_identity") == {"marker": "second"},
              "Clear retained wrong point metadata", cleared)
    await check.edit(sid, "undo")
    v.require(await snapshot("undo") == initial, "Undo did not restore point metadata")
    await check.edit(sid, "redo")
    v.require(await snapshot("redo") == cleared, "Redo did not restore clear metadata")
    await check.edit(sid, "undo")
    await check.edit(sid, "pitch.set", **target, replace=True,
                     points=[{"tick": 100, "value": 60}, {"tick": 300, "value": 62}])
    replaced = await snapshot("replace")
    v.require(all("x_identity" not in item for item in replaced), "Replace retained old metadata", replaced)
    await check.edit(sid, "undo")
    v.require(await snapshot("undo_replace") == initial, "Undo did not restore replace metadata")
    await check.edit(sid, "redo")
    v.require(await snapshot("redo_replace") == replaced, "Redo did not restore replacement")
    await check.close(sid)
    v.require(fixture.read_bytes() == source_bytes, "Source archive changed")


@v.feature("preservation.note_pitch_extension_duplicate_tick", "preservation", "score_compose", "project_edit", "project_save", "project_open")
async def note_pitch_extension_duplicate_tick(check):
    seed = await check.call("score_compose", output_name=check.output("pitch-duplicate-seed"), title="Duplicate pitch", bpm=120,
                            notes=[{"start": 0, "duration": 2, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    target = {"track_index": 0, "part_index": 0, "note_index": 0}
    await check.edit(sid, "pitch.set", **target, replace=True, points=[{"tick": 100, "value": 60}])
    sequence, source = await check.save(sid, "pitch-duplicate-source")
    await check.close(sid)
    # The extension-free sibling remains a normal supported project.
    plain = (await check.call("project_open", path=str(source)))["session_id"]
    await check.close(plain)
    _, members = v.read_vpr(source)
    points = sequence["tracks"][0]["parts"][0]["notes"][0]["directPitches"]
    points[0]["x_identity"] = "first"
    duplicate = dict(points[0]); duplicate["x_identity"] = "second"
    points.append(duplicate)
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    fixture = v.ROOT / "output" / check.output("pitch-duplicate-input")
    with zipfile.ZipFile(fixture, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    original = fixture.read_bytes()
    await check.rejected("project_open", "duplicate position", path=str(fixture))
    v.require(fixture.read_bytes() == original, "Duplicate fixture changed")


@v.feature("preservation.note_pitch_mixed_controller_guard", "preservation", "score_compose", "project_edit", "project_save", "project_open")
async def note_pitch_mixed_controller_guard(check):
    seed = await check.call("score_compose", output_name=check.output("pitch-mixed-seed"), title="Mixed extensions", bpm=120,
                            notes=[{"start": 0, "duration": 2, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    note = {"track_index": 0, "part_index": 0, "note_index": 0}
    lane = {"track_index": 0, "part_index": 0, "type": "Dynamics"}
    await check.edit(sid, "pitch.set", **note, points=[{"tick": 100, "value": 60}])
    await check.edit(sid, "controller.set", **lane, points=[{"tick": 60, "value": 30}], replace=True)
    seq, path = await check.save(sid, "pitch-mixed-native")
    await check.close(sid)
    _, members = v.read_vpr(path)
    part = seq["tracks"][0]["parts"][0]
    part["notes"][0]["directPitches"][0]["x_pitch"] = "note-event"
    controller = next(item for item in part["controllers"] if item["name"].lower() == "dynamics")
    controller["events"][0]["x_controller"] = "controller-event"
    members["Project/sequence.json"] = json.dumps(seq, ensure_ascii=False).encode("utf-8")
    fixture = v.ROOT / "output" / check.output("pitch-mixed-input")
    with zipfile.ZipFile(fixture, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items(): archive.writestr(name, data)
    original = fixture.read_bytes()
    sid = (await check.call("project_open", path=str(fixture)))["session_id"]
    try:
        before, _ = await check.save(sid, "pitch-mixed-before")
        history = await check.edit(sid, "history.status")
        await check.rejected("project_edit", "controller extension", session_id=sid, operation="pitch.set",
                             options={**note, "points": [{"tick": 100, "value": 61}]})
        await check.rejected("project_edit", "direct pitch extension", session_id=sid, operation="controller.set",
                             options={**lane, "points": [{"tick": 60, "value": 31}]})
        after, _ = await check.save(sid, "pitch-mixed-after")
        v.require(after == before and await check.edit(sid, "history.status") == history and
                  fixture.read_bytes() == original, "Mixed extension guard changed source or history")
        mixed = after["tracks"][0]["parts"][0]
        v.require(mixed["notes"][0]["directPitches"][0]["x_pitch"] == "note-event" and
                  next(item for item in mixed["controllers"] if item["name"].lower() == "dynamics")["events"][0]["x_controller"] == "controller-event",
                  "Mixed extension save lost metadata")
    finally:
        await check.close(sid)


@v.feature("preservation.note_pitch_copy_roundtrip", "preservation", "score_compose", "project_edit", "project_save", "project_open")
async def note_pitch_copy_roundtrip(check):
    seed = await check.call("score_compose", output_name=check.output("pitch-copy-seed"), title="Pitch copy",
                            bpm=120, notes=[{"start": i, "duration": 0.6, "pitch": pitch,
                            "lyric": "あ", "phoneme": "a", "lang_id": 0} for i, pitch in enumerate((60, 64))])
    sid = seed["native_session"]["session_id"]
    scope = {"track_index": 0, "part_index": 0}
    for index in range(2):
        await check.edit(sid, "pitch.set", **scope, note_index=index, replace=True,
                         points=[{"tick": 100, "value": 60 + index}, {"tick": 200, "value": 62 + index}])
    sequence, source = await check.save(sid, "pitch-copy-native")
    await check.close(sid)
    notes = sequence["tracks"][0]["parts"][0]["notes"]
    v.require(len(notes) == 2, "Expected two source notes")
    for ni, note in enumerate(notes):
        for pi, point in enumerate(note["directPitches"]):
            point["x_identity"] = {"note": ni, "point": pi, "nested": [ni, pi, True]}
    expected = [json.loads(json.dumps(n["directPitches"])) for n in notes]
    _, members = v.read_vpr(source)
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    fixture = v.ROOT / "output" / check.output("pitch-copy-extended")
    with zipfile.ZipFile(fixture, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = fixture.read_bytes()

    def canonical(points):
        return sorted(points, key=lambda item: item["pos"])
    def check_parts(data, operation, copied):
        parts = data["tracks"][0]["parts"]
        v.require(len(parts) == (2 if copied and operation == "part.duplicate" else 1), "Unexpected part count", parts)
        source_notes = parts[0]["notes"]
        v.require(len(source_notes) == (3 if copied and operation == "note.duplicate" else 2), "Unexpected source note count")
        for index in range(2):
            v.require(canonical(source_notes[index]["directPitches"]) == canonical(expected[index]), "Source points changed")
        if copied and operation == "note.duplicate":
            v.require(canonical(source_notes[2]["directPitches"]) == canonical(expected[0]), "Copied note metadata differs")
        if copied and operation == "part.duplicate":
            v.require(len(parts[1]["notes"]) == 2, "Copied part note count differs")
            for index in range(2):
                v.require(canonical(parts[1]["notes"][index]["directPitches"]) == canonical(expected[index]), "Copied part metadata differs")

    for operation in ("note.duplicate", "part.duplicate"):
        sid = (await check.call("project_open", path=str(fixture)))["session_id"]
        try:
            options = {**scope, "start_tick": 1200 if operation == "note.duplicate" else 9600}
            if operation == "note.duplicate": options["note_index"] = 0
            await check.edit(sid, operation, **options)
            result, saved = await check.save(sid, "pitch-copy-" + operation.replace(".", "-"))
            check_parts(result, operation, True)
            await check.edit(sid, "undo")
            undone, _ = await check.save(sid, "pitch-copy-undo")
            check_parts(undone, operation, False)
            await check.edit(sid, "redo")
            redone, saved = await check.save(sid, "pitch-copy-redo")
            check_parts(redone, operation, True)
            reopened = (await check.call("project_open", path=str(saved)))["session_id"]
            try:
                roundtrip, _ = await check.save(reopened, "pitch-copy-reopened")
                check_parts(roundtrip, operation, True)
            finally:
                await check.close(reopened)
        finally:
            await check.close(sid)
        v.require(fixture.read_bytes() == original, "Copy modified source archive")
    check.evidence("copy_fixture", {"path": str(fixture), "source_unchanged": True})


@v.feature("preservation.note_pitch_track_copy_roundtrip", "preservation", "score_compose", "project_edit", "project_save", "project_open")
async def note_pitch_track_copy_roundtrip(check):
    seed = await check.call("score_compose", output_name=check.output("pitch-copy-seed"), title="Pitch copy",
                            bpm=120, notes=[{"start": i, "duration": 0.6, "pitch": pitch,
                            "lyric": "あ", "phoneme": "a", "lang_id": 0} for i, pitch in enumerate((60, 64))])
    sid = seed["native_session"]["session_id"]
    scope = {"track_index": 0, "part_index": 0}
    for index in range(2):
        await check.edit(sid, "pitch.set", **scope, note_index=index, replace=True,
                         points=[{"tick": 100, "value": 60 + index}, {"tick": 200, "value": 62 + index}])
    sequence, source = await check.save(sid, "pitch-copy-native")
    await check.close(sid)
    notes = sequence["tracks"][0]["parts"][0]["notes"]
    v.require(len(notes) == 2, "Expected two source notes")
    for ni, note in enumerate(notes):
        for pi, point in enumerate(note["directPitches"]):
            point["x_identity"] = {"note": ni, "point": pi, "nested": [ni, pi, True]}
    expected = [json.loads(json.dumps(n["directPitches"])) for n in notes]
    _, members = v.read_vpr(source)
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    fixture = v.ROOT / "output" / check.output("pitch-copy-extended")
    with zipfile.ZipFile(fixture, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = fixture.read_bytes()

    def canonical(points):
        return sorted(points, key=lambda item: item["pos"])
    def check_parts(data, operation, copied):
        tracks = data["tracks"]
        v.require(len(tracks) == (2 if copied else 1), "Unexpected track count")
        parts = tracks[0]["parts"]
        if copied:
            copied_notes = tracks[1]["parts"][0]["notes"]
            v.require(len(copied_notes) == 2, "Copied track note count differs")
            for index in range(2):
                v.require(canonical(copied_notes[index]["directPitches"]) == canonical(expected[index]), "Copied track metadata differs")
        v.require(len(parts) == (2 if copied and operation == "part.duplicate" else 1), "Unexpected part count", parts)
        source_notes = parts[0]["notes"]
        v.require(len(source_notes) == (3 if copied and operation == "note.duplicate" else 2), "Unexpected source note count")
        for index in range(2):
            v.require(canonical(source_notes[index]["directPitches"]) == canonical(expected[index]), "Source points changed")
        if copied and operation == "note.duplicate":
            v.require(canonical(source_notes[2]["directPitches"]) == canonical(expected[0]), "Copied note metadata differs")
        if copied and operation == "part.duplicate":
            v.require(len(parts[1]["notes"]) == 2, "Copied part note count differs")
            for index in range(2):
                v.require(canonical(parts[1]["notes"][index]["directPitches"]) == canonical(expected[index]), "Copied part metadata differs")

    for operation in ("track.duplicate",):
        sid = (await check.call("project_open", path=str(fixture)))["session_id"]
        try:
            options = {"track_index": 0}
            if operation == "note.duplicate": options["note_index"] = 0
            await check.edit(sid, operation, **options)
            result, saved = await check.save(sid, "pitch-copy-" + operation.replace(".", "-"))
            check_parts(result, operation, True)
            await check.edit(sid, "undo")
            undone, _ = await check.save(sid, "pitch-copy-undo")
            check_parts(undone, operation, False)
            await check.edit(sid, "redo")
            redone, saved = await check.save(sid, "pitch-copy-redo")
            check_parts(redone, operation, True)
            reopened = (await check.call("project_open", path=str(saved)))["session_id"]
            try:
                roundtrip, _ = await check.save(reopened, "pitch-copy-reopened")
                check_parts(roundtrip, operation, True)
            finally:
                await check.close(reopened)
        finally:
            await check.close(sid)
        v.require(fixture.read_bytes() == original, "Copy modified source archive")
    check.evidence("copy_fixture", {"path": str(fixture), "source_unchanged": True})


async def pitch_identity_lifecycle(check, operation, options):
    seed = await check.call("score_compose", output_name=check.output("identity-seed"), title="Identity", bpm=120,
        notes=[{"start": i, "duration": 0.6, "pitch": pitch, "lyric": "あ", "phoneme": "a", "lang_id": 0} for i, pitch in enumerate((60, 64))])
    sid = seed["native_session"]["session_id"]
    for i in range(2):
        await check.edit(sid, "pitch.set", track_index=0, part_index=0, note_index=i, replace=True,
                         points=[{"tick": 100, "value": 60+i}])
    await check.edit(sid, "track.update", track_index=0, name="Original")
    await check.edit(sid, "track.duplicate", track_index=0, name="Other")
    sequence, source = await check.save(sid, "identity-native")
    await check.close(sid)
    for ti, track in enumerate(sequence["tracks"]):
        for ni, note in enumerate(track["parts"][0]["notes"]):
            note["directPitches"][0]["x_identity"] = {"track": ti, "note": ni}
    _, members = v.read_vpr(source)
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    fixture = v.ROOT / "output" / check.output("identity-extended")
    with zipfile.ZipFile(fixture, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = fixture.read_bytes()
    def verify(data, changed):
        tracks = data["tracks"]
        expected_order = [1, 0] if changed and operation == "track.reorder" else [0, 1]
        v.require(len(tracks) == 2, "Unexpected track count")
        cross_move = operation == "part.move" and options.get("to_track_index") == 1
        for track, ti in zip(tracks, expected_order):
            if cross_move and changed:
                expected_parts = [] if ti == 0 else [1, 0]
            else:
                expected_parts = [ti]
            parts = track.get("parts", [])
            v.require(len(parts) == len(expected_parts), "Unexpected part count", parts)
            for part, origin in zip(parts, expected_parts):
                v.require(len(part["notes"]) == 2, "Unexpected note count")
                for ni, note in enumerate(part["notes"]):
                    v.require(note["directPitches"][0]["x_identity"] == {"track": origin, "note": ni}, "Marker attached to wrong note")
        return data
    sid = (await check.call("project_open", path=str(fixture)))["session_id"]
    try:
        before, _ = await check.save(sid, "identity-before")
        verify(before, False)
        await check.edit(sid, operation, **options)
        after, _ = await check.save(sid, "identity-after")
        verify(after, True)
        v.require(after != before, "Edit did not change the sequence")
        await check.edit(sid, "undo")
        undone, _ = await check.save(sid, "identity-undo")
        verify(undone, False)
        v.require(undone == before, "Undo differs from initial sequence")
        await check.rejected("project_edit", "range|index|track", session_id=sid, operation=operation,
                             options={**options, "track_index": 999})
        rejected, _ = await check.save(sid, "identity-rejected")
        v.require(rejected == before, "Rejected operation changed sequence")
        if operation == "part.move" and options.get("to_track_index") == 1:
            await check.rejected("project_edit", "range|index|track", session_id=sid, operation=operation,
                                 options={**options, "to_track_index": 999})
            await check.rejected("project_edit", "overlap|occupied|move|failed|range", session_id=sid, operation=operation,
                                 options={**options, "start_tick": 0})
            rejected_target, _ = await check.save(sid, "identity-target-rejected")
            v.require(rejected_target == before, "Rejected target changed sequence")
        await check.edit(sid, "redo")
        redone, saved = await check.save(sid, "identity-redo")
        verify(redone, True)
        v.require(redone == after, "Redo differs from edited sequence")
        reopened = (await check.call("project_open", path=str(saved)))["session_id"]
        try:
            reopened_data, _ = await check.save(reopened, "identity-reopened")
            verify(reopened_data, True)
            v.require(reopened_data == after, "Reopened sequence differs")
        finally:
            await check.close(reopened)
    finally:
        await check.close(sid)
    v.require(fixture.read_bytes() == original, "Source fixture changed")


@v.feature("preservation.note_pitch_track_update", "preservation", "score_compose", "project_edit", "project_save", "project_open")
async def note_pitch_track_update(check):
    await pitch_identity_lifecycle(check, "track.update", {"track_index": 0, "name": "Changed"})


@v.feature("preservation.note_pitch_track_reorder", "preservation", "score_compose", "project_edit", "project_save", "project_open")
async def note_pitch_track_reorder(check):
    await pitch_identity_lifecycle(check, "track.reorder", {"track_index": 0, "to_index": 1})


@v.feature("preservation.note_pitch_part_update", "preservation", "score_compose", "project_edit", "project_save", "project_open")
async def note_pitch_part_update(check):
    await pitch_identity_lifecycle(check, "part.update", {"track_index": 0, "part_index": 0, "name": "Changed part"})


@v.feature("preservation.note_pitch_part_move", "preservation", "score_compose", "project_edit", "project_save", "project_open")
async def note_pitch_part_move(check):
    await pitch_identity_lifecycle(check, "part.move", {"track_index": 0, "part_index": 0, "start_tick": 9600})


@v.feature("preservation.note_pitch_part_move_cross_track", "preservation", "score_compose", "project_edit", "project_save", "project_open")
async def note_pitch_part_move_cross_track(check):
    await pitch_identity_lifecycle(check, "part.move", {"track_index": 0, "part_index": 0, "to_track_index": 1, "start_tick": 9600})


@v.feature("preservation.note_pitch_copy_ambiguous_signature", "preservation", "score_compose", "project_edit", "project_save", "project_open")
async def note_pitch_copy_ambiguous_signature(check):
    seed = await check.call("score_compose", output_name=check.output("pitch-copy-ambiguous-seed"),
                            title="Ambiguous pitch copy", bpm=120,
                            notes=[{"start": 0, "duration": 0.6, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    await check.edit(sid, "pitch.set", track_index=0, part_index=0, note_index=0,
                     points=[{"tick": 100, "value": 60}])
    sequence, path = await check.save(sid, "pitch-copy-ambiguous-native")
    await check.close(sid)
    notes = sequence["tracks"][0]["parts"][0]["notes"]
    notes[0]["directPitches"][0]["x_identity"] = "first"
    duplicate = json.loads(json.dumps(notes[0]))
    duplicate["directPitches"][0]["x_identity"] = "second"
    notes.append(duplicate)
    _, members = v.read_vpr(path)
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    fixture = v.ROOT / "output" / check.output("pitch-copy-ambiguous")
    with zipfile.ZipFile(fixture, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = fixture.read_bytes()
    try:
        sid = (await check.call("project_open", path=str(fixture)))["session_id"]
    except v.ToolFailure as error:
        v.require("project_preservation" in str(error).lower(), "Unexpected open error", str(error))
        check.evidence("rejected_at_open", str(error))
    else:
        try:
            before, _ = await check.save(sid, "pitch-copy-ambiguous-before")
            history = await check.edit(sid, "history.status")
            await check.rejected("project_edit", "ambiguous|correspondence", session_id=sid,
                                 operation="part.duplicate", options={"track_index": 0, "part_index": 0, "start_tick": 9600})
            after, _ = await check.save(sid, "pitch-copy-ambiguous-after")
            v.require(before == after and history == await check.edit(sid, "history.status"), "Ambiguous copy changed state")
            check.evidence("rejected_at_copy", True)
        finally:
            await check.close(sid)
    v.require(fixture.read_bytes() == original, "Ambiguous fixture changed")



async def pitch_delete_lifecycle(check, operation, options):
    seed = await check.call("score_compose", output_name=check.output("delete-seed"), title="Delete", bpm=120,
        notes=[{"start": i, "duration": 0.6, "pitch": pitch, "lyric": "あ", "phoneme": "a", "lang_id": 0} for i, pitch in enumerate((60, 64))])
    sid = seed["native_session"]["session_id"]
    for i in range(2):
        await check.edit(sid, "pitch.set", track_index=0, part_index=0, note_index=i, replace=True,
                         points=[{"tick": 100, "value": 60+i}])
    await check.edit(sid, "track.duplicate", track_index=0, name="Survivor")
    sequence, source = await check.save(sid, "delete-native")
    await check.close(sid)
    for ti, track in enumerate(sequence["tracks"]):
        for ni, note in enumerate(track["parts"][0]["notes"]):
            note["directPitches"][0]["x_identity"] = {"track": ti, "note": ni, "nested": [ti, ni]}
    _, members = v.read_vpr(source)
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    fixture = v.ROOT / "output" / check.output("delete-extended")
    with zipfile.ZipFile(fixture, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = fixture.read_bytes()
    def markers(data):
        return [note["directPitches"][0]["x_identity"] for track in data["tracks"]
                for part in track.get("parts", []) for note in part.get("notes", [])]
    initial = [{"track": ti, "note": ni, "nested": [ti, ni]} for ti in range(2) for ni in range(2)]
    remaining = initial[1:] if operation == "note.remove" else initial[2:]
    sid = (await check.call("project_open", path=str(fixture)))["session_id"]
    try:
        before, _ = await check.save(sid, "delete-before")
        v.require(markers(before) == initial, "Initial pitch identities differ")
        await check.edit(sid, operation, **options)
        after, saved = await check.save(sid, "delete-after")
        v.require(markers(after) == remaining, "Deletion changed surviving markers")
        await check.edit(sid, "undo")
        undone, _ = await check.save(sid, "delete-undo")
        v.require(undone == before, "Undo differs from initial state")
        await check.edit(sid, "redo")
        redone, saved = await check.save(sid, "delete-redo")
        v.require(redone == after, "Redo differs from deleted state")
        reopened = (await check.call("project_open", path=str(saved)))["session_id"]
        try:
            reopened_data, _ = await check.save(reopened, "delete-reopened")
            v.require(reopened_data == after, "Reopened state differs")
        finally:
            await check.close(reopened)
        await check.edit(sid, "undo")
        await check.edit(sid, "track.update", track_index=1, name="Branch")
        branched, _ = await check.save(sid, "delete-branch")
        v.require(markers(branched) == initial, "Branch changed restored markers")
        await check.rejected("project_edit", "redo|history|failed", session_id=sid, operation="redo", options={})
    finally:
        await check.close(sid)
    v.require(fixture.read_bytes() == original, "Source fixture changed")


@v.feature("preservation.note_pitch_delete_note", "preservation", "score_compose", "project_edit", "project_save", "project_open")
async def note_pitch_delete_note(check):
    await pitch_delete_lifecycle(check, "note.remove", {"track_index": 0, "part_index": 0, "note_index": 0})


@v.feature("preservation.note_pitch_delete_clear", "preservation", "score_compose", "project_edit", "project_save", "project_open")
async def note_pitch_delete_clear(check):
    await pitch_delete_lifecycle(check, "note.clear", {"track_index": 0, "part_index": 0})


@v.feature("preservation.note_pitch_delete_part", "preservation", "score_compose", "project_edit", "project_save", "project_open")
async def note_pitch_delete_part(check):
    await pitch_delete_lifecycle(check, "part.remove", {"track_index": 0, "part_index": 0})


@v.feature("preservation.note_pitch_delete_track", "preservation", "score_compose", "project_edit", "project_save", "project_open")
async def note_pitch_delete_track(check):
    await pitch_delete_lifecycle(check, "track.remove", {"track_index": 0})


if __name__ == "__main__":
    raise SystemExit(v.main())
