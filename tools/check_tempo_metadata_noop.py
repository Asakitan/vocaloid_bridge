"""Native identical-map merge with tempo/time-signature extension history."""
import json
import sys
import zipfile

import verify_features as v


@v.feature("preservation.tempo_collision_native_probe", "preservation", "project_create", "project_edit",
           "project_save", "project_merge")
async def tempo_collision_native_probe(check):
    async with check.project() as source:
        await check.edit(source, "tempo.set", start_tick=0, bpm=110)
        await check.edit(source, "tempo.set", start_tick=480, bpm=130)
        _, source_path = await check.save(source, "tempo-collision-native-source")
    original = source_path.read_bytes()
    async with check.project() as target:
        await check.edit(target, "tempo.set", start_tick=480, bpm=90)
        await check.edit(target, "tempo.set", start_tick=960, bpm=80)
        before = (await check.edit(target, "tempo.list"))["tempos"]
        await check.call("project_merge", session_id=target, path=str(source_path), include_tracks=False,
                         include_tempo=True, replace_tempo=False, offset_tick=480)
        after = (await check.edit(target, "tempo.list"))["tempos"]
        saved, _ = await check.save(target, "tempo-collision-native-after")
        await check.edit(target, "undo")
        undone = (await check.edit(target, "tempo.list"))["tempos"]
        await check.edit(target, "redo")
        redone = (await check.edit(target, "tempo.list"))["tempos"]
        check.evidence("native_collision", {"before": before, "after": after, "undo": undone, "redo": redone,
                                            "saved_events": saved["masterTrack"]["tempo"]["events"]})
        v.require(undone == before and redone == after, "Native collision history changed maps")
    v.require(source_path.read_bytes() == original, "Native collision probe changed source bytes")


@v.feature("preservation.tempo_same_collision_native_probe", "preservation", "project_create", "project_edit",
           "project_save", "project_merge")
async def tempo_same_collision_native_probe(check):
    async with check.project() as source:
        await check.edit(source, "tempo.set", start_tick=0, bpm=110)
        await check.edit(source, "tempo.set", start_tick=480, bpm=130)
        _, source_path = await check.save(source, "tempo-same-collision-source")
    async with check.project() as target:
        await check.edit(target, "tempo.set", start_tick=480, bpm=110)
        await check.edit(target, "tempo.set", start_tick=960, bpm=130)
        await check.edit(target, "tempo.set", start_tick=1440, bpm=70)
        before = (await check.edit(target, "tempo.list"))["tempos"]
        await check.call("project_merge", session_id=target, path=str(source_path), include_tracks=False,
                         include_tempo=True, replace_tempo=False, offset_tick=480)
        after = (await check.edit(target, "tempo.list"))["tempos"]
        await check.edit(target, "undo")
        undone = (await check.edit(target, "tempo.list"))["tempos"]
        await check.edit(target, "redo")
        redone = (await check.edit(target, "tempo.list"))["tempos"]
        check.evidence("same_collision", {"before": before, "after": after, "undo": undone, "redo": redone})
        v.require(after == before and redone == before, "Same-value collision changed the final map")


@v.feature("preservation.tempo_collision_extensions", "preservation", "project_create", "project_edit",
           "project_save", "project_open", "project_merge")
async def tempo_collision_extensions(check):
    async with check.project() as source:
        await check.edit(source, "tempo.set", start_tick=0, bpm=110)
        await check.edit(source, "tempo.set", start_tick=480, bpm=130)
        source_json, plain_source = await check.save(source, "tempo-collision-source")
    _, source_members = v.read_vpr(plain_source)
    for event in source_json["masterTrack"]["tempo"]["events"]:
        event["x_origin"] = {"project": "source", "original_tick": event["pos"]}
    source_members["Project/sequence.json"] = json.dumps(source_json, ensure_ascii=False).encode("utf-8")
    extended_source = v.ROOT / "output" / check.output("tempo-collision-source-extended")
    with zipfile.ZipFile(extended_source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in source_members.items(): archive.writestr(name, payload)
    async with check.project() as seed:
        await check.edit(seed, "tempo.set", start_tick=480, bpm=90)
        await check.edit(seed, "tempo.set", start_tick=960, bpm=80)
        target_json, target_seed = await check.save(seed, "tempo-collision-target")
    _, target_members = v.read_vpr(target_seed)
    target_json["x_target_root"] = "preserved"
    for event in target_json["masterTrack"]["tempo"]["events"]:
        event["x_origin"] = {"project": "target", "original_tick": event["pos"]}
    target_members["Project/sequence.json"] = json.dumps(target_json, ensure_ascii=False).encode("utf-8")
    extended_target = v.ROOT / "output" / check.output("tempo-collision-target-extended")
    with zipfile.ZipFile(extended_target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in target_members.items(): archive.writestr(name, payload)
    originals = {p: p.read_bytes() for p in (extended_source, plain_source, extended_target)}

    def events(sequence):
        return [(e["pos"], e["value"], e.get("x_origin")) for e in sequence["masterTrack"]["tempo"]["events"]]

    async def snapshot(sid, name):
        sequence, path = await check.save(sid, "tempo-collision-" + name)
        v.require(sequence["x_target_root"] == "preserved", "Tempo collision lost target root metadata")
        return events(sequence), path

    target = (await check.call("project_open", path=str(extended_target)))["session_id"]
    try:
        await check.edit(target, "tempo.set", start_tick=1440, bpm=70)
        before, _ = await snapshot(target, "before")
        await check.call("project_merge", session_id=target, path=str(extended_source), include_tracks=False,
                         include_tempo=True, replace_tempo=False, offset_tick=480)
        actual, _ = await snapshot(target, "source-overwrite")
        expected = [(0, 12000, {"project": "target", "original_tick": 0}),
                    (480, 11000, {"project": "source", "original_tick": 0}),
                    (960, 13000, {"project": "source", "original_tick": 480}),
                    (1440, 7000, None)]
        v.require(actual == expected, "Colliding tempo did not take source value and fields", actual)
        await check.edit(target, "undo")
        undone, _ = await snapshot(target, "undo")
        v.require(undone == before, "Collision undo did not restore target metadata", undone)
        await check.edit(target, "undo")
        older, _ = await snapshot(target, "older-undo")
        v.require(older == before[:-1], "Collision merge damaged earlier history", older)
        await check.edit(target, "redo")
        await check.edit(target, "redo")
        redone, redone_path = await snapshot(target, "redo")
        v.require(redone == expected, "Collision redo did not restore source metadata", redone)
        reopened = (await check.call("project_open", path=str(redone_path)))["session_id"]
        try:
            reopened_events, _ = await snapshot(reopened, "reopened")
            v.require(reopened_events == expected, "Collision reopen differs", reopened_events)
        finally:
            await check.close(reopened)
    finally:
        await check.close(target)

    target = (await check.call("project_open", path=str(extended_target)))["session_id"]
    try:
        before, _ = await snapshot(target, "plain-before")
        await check.call("project_merge", session_id=target, path=str(plain_source), include_tracks=False,
                         include_tempo=True, replace_tempo=False, offset_tick=480)
        plain, _ = await snapshot(target, "plain-overwrite")
        expected = [(0, 12000, {"project": "target", "original_tick": 0}), (480, 11000, None), (960, 13000, None)]
        v.require(plain == expected, "Plain source collision retained target event fields", plain)
        await check.edit(target, "undo")
        undone, _ = await snapshot(target, "plain-undo")
        v.require(undone == before, "Plain source collision undo differs", undone)
    finally:
        await check.close(target)

    target = (await check.call("project_open", path=str(extended_target)))["session_id"]
    try:
        before, _ = await snapshot(target, "zero-before")
        await check.call("project_merge", session_id=target, path=str(extended_source), include_tracks=False,
                         include_tempo=True, replace_tempo=False, offset_tick=0)
        at_zero, _ = await snapshot(target, "zero-overwrite")
        expected = [(0, 11000, {"project": "source", "original_tick": 0}),
                    (480, 13000, {"project": "source", "original_tick": 480}),
                    (960, 8000, {"project": "target", "original_tick": 960})]
        v.require(at_zero == expected, "Tick-zero collision did not follow native overwrite", at_zero)
        await check.edit(target, "undo")
        undone, _ = await snapshot(target, "zero-undo")
        v.require(undone == before, "Tick-zero collision undo differs", undone)
    finally:
        await check.close(target)

    # The source must replace extension metadata even if native tempo values
    # already match; undo must restore the previous metadata separately.
    target = (await check.call("project_open", path=str(extended_target)))["session_id"]
    try:
        await check.edit(target, "tempo.set", tempo_index=1, start_tick=480, bpm=110)
        await check.edit(target, "tempo.set", tempo_index=2, start_tick=960, bpm=130)
        before, _ = await snapshot(target, "same-value-before")
        await check.call("project_merge", session_id=target, path=str(extended_source), include_tracks=False,
                         include_tempo=True, replace_tempo=False, offset_tick=480)
        same_value, _ = await snapshot(target, "same-value-overwrite")
        expected = [(0, 12000, {"project": "target", "original_tick": 0}),
                    (480, 11000, {"project": "source", "original_tick": 0}),
                    (960, 13000, {"project": "source", "original_tick": 480})]
        v.require(same_value == expected, "Same-value collision did not replace target metadata", same_value)
        await check.edit(target, "undo")
        undone, _ = await snapshot(target, "same-value-undo")
        v.require(undone == before, "Same-value collision undo differs", undone)
    finally:
        await check.close(target)
    v.require(all(path.read_bytes() == data for path, data in originals.items()), "Collision merge changed a source archive")


@v.feature("preservation.identical_map_extension_merge", "preservation", "project_create", "project_edit",
           "project_save", "project_open", "project_merge")
async def identical_map_extension_merge(check):
    async with check.project() as seed:
        source_json, seed_path = await check.save(seed, "identical-map-seed")
    _, members = v.read_vpr(seed_path)
    source_json["masterTrack"]["tempo"]["events"][0]["x_marker"] = {"type": "tempo", "values": [1, None]}
    source_json["masterTrack"]["timeSig"]["events"][0]["x_marker"] = {"type": "meter", "values": [2, True]}
    members["Project/sequence.json"] = json.dumps(source_json, ensure_ascii=False).encode("utf-8")
    source_path = v.ROOT / "output" / check.output("identical-map-source")
    with zipfile.ZipFile(source_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    original = source_path.read_bytes()
    async with check.project() as target:
        await check.edit(target, "track.create", type="MidiAi", name="Earlier history")
        before, _ = await check.save(target, "identical-map-before")
        await check.call("project_merge", session_id=target, path=str(source_path), include_tracks=False,
                         include_tempo=True, replace_tempo=True)
        merged, merged_path = await check.save(target, "identical-map-merged")
        for key in ("tempo", "timeSig"):
            v.require(merged["masterTrack"][key]["events"] == source_json["masterTrack"][key]["events"],
                      "Identical native map merge lost extension fields", merged["masterTrack"][key])
        v.require(merged.get("tracks", []) == before.get("tracks", []), "Map merge changed tracks")
        await check.edit(target, "undo")
        undone, _ = await check.save(target, "identical-map-undo")
        for key in ("tempo", "timeSig"):
            v.require(undone["masterTrack"][key]["events"] == before["masterTrack"][key]["events"],
                      "Map extension merge undo differs", undone["masterTrack"][key])
        await check.edit(target, "undo")
        older, _ = await check.save(target, "identical-map-older-undo")
        v.require(older.get("tracks", []) == [], "Map merge lost earlier native history")
        await check.edit(target, "redo")
        await check.edit(target, "redo")
        redone, redone_path = await check.save(target, "identical-map-redo")
        for key in ("tempo", "timeSig"):
            v.require(redone["masterTrack"][key]["events"] == merged["masterTrack"][key]["events"],
                      "Map extension merge redo differs", redone["masterTrack"][key])
        reopened = (await check.call("project_open", path=str(redone_path)))['session_id']
        try:
            reopened_json, _ = await check.save(reopened, "identical-map-reopened")
            for key in ("tempo", "timeSig"):
                v.require(reopened_json["masterTrack"][key]["events"] == merged["masterTrack"][key]["events"],
                          "Reopened identical map lost extension fields", reopened_json["masterTrack"][key])
        finally:
            await check.close(reopened)
    v.require(source_path.read_bytes() == original, "Merge changed source bytes")


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "preservation.identical_map_extension_merge"])
    raise SystemExit(v.main())
