"""Focused synthetic acceptance for archive-aware project merge."""
import json
import zipfile
import verify_features as v


@v.feature("preservation.merge_transfer", "preservation", "score_compose", "project_open",
           "project_merge", "project_edit", "project_save")
async def merge_transfer(check):
    seed = await check.call("score_compose", output_name=check.output("merge-seed"), title="Merge fixture", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0},
                                   {"start": 1, "duration": .5, "pitch": 62, "lyric": "い", "phoneme": "i", "lang_id": 0}])
    seed_id = seed["native_session"]["session_id"]
    await check.edit(seed_id, "tempo.set", start_tick=1920, bpm=95)
    sequence, seed_path = await check.save(seed_id, "merge-source-tempo")
    await check.close(seed_id)
    _, members = v.read_vpr(seed_path)
    track = sequence["tracks"][0]; part = track["parts"][0]; position = part["pos"]
    track["x_merge"] = "track"; part["x_merge"] = "part"
    for i, note in enumerate(part["notes"]): note["x_merge"] = "note-" + str(i)
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("merge-source")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    for extended_target in (False, True):
        target = (await check.call("project_open", path=str(source)))["session_id"] if extended_target else (await check.call("project_create", title="Merge target"))["session_id"]
        try:
            await check.call("project_merge", session_id=target, path=str(source), offset_tick=960,
                             include_tracks=True, include_tempo=False)
            def verify(value):
                v.require(len(value["tracks"]) == (2 if extended_target else 1), "Merged track count changed")
                imported = value["tracks"][-1]; copied_part = imported["parts"][0]
                v.require(imported["x_merge"] == "track" and copied_part["x_merge"] == "part", "Parent extension lost")
                v.require(copied_part["pos"] == position + 960, "Merge offset changed")
                v.require([n["x_merge"] for n in copied_part["notes"]] == ["note-0", "note-1"], "Note extensions mismatched")
            saved, _ = await check.save(target, "merge-transfer"); verify(saved)
            await check.edit(target, "undo")
            undone, _ = await check.save(target, "merge-undo")
            v.require(len(undone.get("tracks", [])) == (1 if extended_target else 0), "Merge undo failed")
            await check.edit(target, "redo")
            redone, _ = await check.save(target, "merge-redo"); verify(redone)
        finally:
            await check.close(target)
    target = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        before = await check.edit(target, "tempo.list")
        await check.call("project_merge", session_id=target, path=str(source), offset_tick=0,
                         include_tracks=False, include_tempo=True, replace_tempo=True)
        after = await check.edit(target, "tempo.list")
        v.require(after["tempos"] == before["tempos"], "Tempo-only merge changed the source map", after)
        saved, _ = await check.save(target, "merge-tempo-only")
        v.require(saved["tracks"][0]["x_merge"] == "track", "Tempo merge lost target metadata")
    finally:
        await check.close(target)
    guarded = json.loads(json.dumps(sequence)); guarded["x_merge_root"] = {"value": None}
    guarded["masterTrack"]["x_merge_master"] = [1, "master"]
    guarded_members = dict(members)
    guarded_members["Project/sequence.json"] = json.dumps(guarded, ensure_ascii=False).encode("utf-8")
    guarded_path = v.ROOT / "output" / check.output("merge-guarded-source")
    with zipfile.ZipFile(guarded_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in guarded_members.items(): archive.writestr(name, payload)
    guarded_original = guarded_path.read_bytes()
    target_sequence = json.loads(json.dumps(sequence))
    target_sequence["x_existing_root"] = "target"
    target_sequence["masterTrack"]["x_existing_master"] = "target-master"
    target_members = dict(members)
    target_members["Project/sequence.json"] = json.dumps(target_sequence, ensure_ascii=False).encode("utf-8")
    target_path = v.ROOT / "output" / check.output("merge-global-target")
    with zipfile.ZipFile(target_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in target_members.items(): archive.writestr(name, payload)
    root_only_sequence = json.loads(json.dumps(target_sequence))
    root_only_track = root_only_sequence["tracks"][0]
    root_only_track.pop("x_merge")
    root_only_part = root_only_track["parts"][0]
    root_only_part.pop("x_merge")
    for note in root_only_part["notes"]: note.pop("x_merge")
    root_only_members = dict(members)
    root_only_members["Project/sequence.json"] = json.dumps(root_only_sequence, ensure_ascii=False).encode("utf-8")
    root_only_path = v.ROOT / "output" / check.output("merge-root-only-target")
    with zipfile.ZipFile(root_only_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in root_only_members.items(): archive.writestr(name, payload)
    for target_kind in ("plain", "entities", "root_only"):
        target = ((await check.call("project_create", title="Global merge target"))["session_id"]
                  if target_kind == "plain" else
                  (await check.call("project_open", path=str(target_path if target_kind == "entities" else root_only_path)))["session_id"])
        try:
            await check.edit(target, "tempo.set", start_tick=1920, bpm=90)
            if target_kind == "root_only":
                before = await check.call("project_status", session_id=target)
                await check.rejected("project_merge", "indistinguishable track identities", session_id=target,
                                     path=str(guarded_path), include_tracks=True, include_tempo=False)
                v.require(await check.call("project_status", session_id=target) == before,
                          "Ambiguous track merge changed the target before rejection")
                protected, _ = await check.save(target, "merge-ambiguous-protected")
                v.require(len(protected["tracks"]) == 1 and "x_merge_root" not in protected,
                          "Ambiguous track merge left imported data in the target")
            await check.call("project_merge", session_id=target, path=str(guarded_path),
                             include_tracks=True, offset_tick=960 if target_kind == "root_only" else 0)
            saved, _ = await check.save(target, "merge-global")
            v.require(saved["x_merge_root"] == {"value": None} and saved["masterTrack"]["x_merge_master"] == [1, "master"], "Global extensions lost")
            if target_kind != "plain":
                v.require(saved["x_existing_root"] == "target" and saved["masterTrack"]["x_existing_master"] == "target-master", "Target global extensions lost")
            await check.edit(target, "undo")
            undone, _ = await check.save(target, "merge-global-undo")
            v.require("x_merge_root" not in undone and "x_merge_master" not in undone["masterTrack"], "Global merge undo failed")
            if target_kind != "plain":
                v.require(undone["x_existing_root"] == "target" and undone["masterTrack"]["x_existing_master"] == "target-master", "Target global extensions lost on undo")
            await check.edit(target, "undo")
            old_history, _ = await check.save(target, "merge-global-old-undo")
            if target_kind != "plain":
                v.require(old_history["x_existing_root"] == "target" and
                          old_history["masterTrack"]["x_existing_master"] == "target-master",
                          "Target global fields lost in pre-upgrade history")
            await check.edit(target, "redo")
            await check.edit(target, "redo")
            redone, _ = await check.save(target, "merge-global-redo")
            v.require(redone["x_merge_root"] == {"value": None} and redone["masterTrack"]["x_merge_master"] == [1, "master"], "Global merge redo failed")
        finally:
            await check.close(target)
    conflicting = json.loads(json.dumps(guarded)); conflicting["x_merge_root"] = "conflict"
    conflicting_members = dict(members)
    conflicting_members["Project/sequence.json"] = json.dumps(conflicting, ensure_ascii=False).encode("utf-8")
    conflicting_path = v.ROOT / "output" / check.output("merge-conflict")
    with zipfile.ZipFile(conflicting_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in conflicting_members.items(): archive.writestr(name, payload)
    conflicting_original = conflicting_path.read_bytes()
    target = (await check.call("project_open", path=str(guarded_path)))["session_id"]
    try:
        await check.call("project_merge", session_id=target, path=str(guarded_path), offset_tick=9600,
                         include_tracks=True, include_tempo=False)
        equal, _ = await check.save(target, "merge-global-equal")
        v.require(equal["x_merge_root"] == {"value": None} and
                  equal["masterTrack"]["x_merge_master"] == [1, "master"] and len(equal["tracks"]) == 2,
                  "Equal global extensions or imported track changed")
        await check.edit(target, "undo")
        before = await check.call("project_status", session_id=target)
        await check.rejected("project_merge", "extension conflicts", session_id=target, path=str(conflicting_path), include_tracks=True)
        v.require(await check.call("project_status", session_id=target) == before, "Rejected merge modified the target")
        saved, _ = await check.save(target, "merge-conflict-target")
        v.require(saved["x_merge_root"] == {"value": None}, "Conflict changed target extension")
    finally:
        await check.close(target)
    v.require(guarded_path.read_bytes() == guarded_original, "Rejected merge changed its source")
    v.require(conflicting_path.read_bytes() == conflicting_original, "Rejected merge changed the conflicting input")

    nested = json.loads(json.dumps(guarded))
    nested["version"]["x_nested_version"] = "version-extension"
    nested["masterTrack"]["loop"]["x_nested_merge"] = {"value": 17}
    nested_members = dict(members)
    nested_members["Project/sequence.json"] = json.dumps(nested, ensure_ascii=False).encode("utf-8")
    nested_path = v.ROOT / "output" / check.output("merge-nested-source")
    with zipfile.ZipFile(nested_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in nested_members.items(): archive.writestr(name, payload)
    nested_original = nested_path.read_bytes()
    target = (await check.call("project_open", path=str(guarded_path)))["session_id"]
    try:
        await check.call("project_merge", session_id=target, path=str(nested_path), offset_tick=9600,
                         include_tracks=True, include_tempo=False)
        nested_saved, nested_saved_path = await check.save(target, "merge-nested-added")
        v.require(nested_saved["version"]["x_nested_version"] == "version-extension" and
                  nested_saved["masterTrack"]["loop"]["x_nested_merge"] == {"value": 17},
                  "New nested global extension lost")
        await check.edit(target, "undo")
        nested_undo, _ = await check.save(target, "merge-nested-undo")
        v.require("x_nested_version" not in nested_undo["version"] and
                  "x_nested_merge" not in nested_undo["masterTrack"]["loop"],
                  "Nested global merge undo failed")
        await check.edit(target, "redo")
        nested_redo, nested_saved_path = await check.save(target, "merge-nested-redo")
        v.require(nested_redo["version"]["x_nested_version"] == "version-extension" and
                  nested_redo["masterTrack"]["loop"]["x_nested_merge"] == {"value": 17},
                  "Nested global merge redo failed")
        reopened = (await check.call("project_open", path=str(nested_saved_path)))["session_id"]
        try:
            reopened_json, _ = await check.save(reopened, "merge-nested-reopened")
            v.require(reopened_json["version"]["x_nested_version"] == "version-extension" and
                      reopened_json["masterTrack"]["loop"]["x_nested_merge"] == {"value": 17},
                      "Nested global extensions lost on reopen")
        finally:
            await check.close(reopened)
    finally:
        await check.close(target)
    target = (await check.call("project_open", path=str(nested_path)))["session_id"]
    try:
        await check.call("project_merge", session_id=target, path=str(nested_path), offset_tick=9600,
                         include_tracks=True, include_tempo=False)
        equal_nested, _ = await check.save(target, "merge-nested-equal")
        v.require(equal_nested["masterTrack"]["loop"]["x_nested_merge"] == {"value": 17},
                  "Equal nested extension changed")
    finally:
        await check.close(target)
    v.require(nested_path.read_bytes() == nested_original, "Nested source file changed")

    empty = (await check.call("project_create", title="Empty global source"))["session_id"]
    empty_json, empty_path = await check.save(empty, "merge-empty-global-seed")
    await check.close(empty)
    _, empty_members = v.read_vpr(empty_path)
    empty_json["x_empty_global"] = "only-metadata"
    empty_members["Project/sequence.json"] = json.dumps(empty_json, ensure_ascii=False).encode("utf-8")
    empty_source = v.ROOT / "output" / check.output("merge-empty-global-source")
    with zipfile.ZipFile(empty_source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in empty_members.items(): archive.writestr(name, payload)
    target = (await check.call("project_create", title="Empty global target"))["session_id"]
    try:
        before = await check.call("project_status", session_id=target)
        await check.rejected("project_merge", "requires a native history entry", session_id=target,
                             path=str(empty_source), include_tracks=True, include_tempo=False)
        v.require(await check.call("project_status", session_id=target) == before,
                  "Rejected metadata-only merge changed target status")
        empty_saved, _ = await check.save(target, "merge-empty-global-target")
        v.require("x_empty_global" not in empty_saved, "Rejected metadata-only merge changed global data")
    finally:
        await check.close(target)
    v.require(source.read_bytes() == original, "Source VPR changed")


if __name__ == "__main__":
    raise SystemExit(v.main())
