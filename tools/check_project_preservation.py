"""Exercise unknown VPR data through a real private native MCP session.

The diagnostic fixture is a copy of a freshly native-saved project with
sentinel-only unknown properties and one benign extra ZIP member.
"""
import json
from pathlib import Path
import zipfile

import verify_features as v


SENTINELS = {
    "root": "root-sentinel", "master": "master-sentinel", "track": "track-sentinel",
    "part": "part-sentinel", "note": "note-sentinel", "master_nested": "loop-sentinel",
    "note_nested": {"marker": "expression-sentinel", "value": [1, True, None]},
}
KEY = "x_bridge_preservation_probe"
NESTED_KEY = "x~nested/name"
EXTRA = "Project/bridge-probe/extra.bin"
EXTRA_BYTES = b"independent-project-resource\x00\x01"
EXTRA_AUDIO = "Project/Audio/opaque-extra.bin"
EXTRA_ROOT = "custom-probe/root.bin"


@v.feature("preservation.array_guard", "preservation", "score_compose", "project_open")
async def array_guard(check):
    """Unknown array-element fields must be rejected, never silently dropped."""
    seed = await check.call("score_compose", output_name=check.output("array-guard-seed"),
                            title="Array guard", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    for label, select in (
        ("effect-parameter", lambda s: s["tracks"][0]["parts"][0]["audioEffects"][0]["parameters"][0]),
        ("language", lambda s: s["tracks"][0]["parts"][0]["aiVoice"]["langIDs"][0]),
    ):
        fixture = json.loads(json.dumps(sequence))
        select(fixture)[KEY] = label
        fixture_members = dict(members)
        fixture_members["Project/sequence.json"] = json.dumps(fixture, ensure_ascii=False).encode("utf-8")
        path = v.ROOT / "output" / check.output("array-guard-" + label)
        with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in fixture_members.items():
                archive.writestr(name, payload)
        original = path.read_bytes()
        await check.rejected("project_open", "unsupported nested unknown field|unsupported language metadata", path=str(path))
        v.require(path.read_bytes() == original, "Rejected array fixture was modified")
        check.evidence("array_guard_" + label, {"path": str(path), "rejected": True})


@v.feature("preservation.controller_array_roundtrip", "preservation", "score_compose", "project_open", "project_edit", "project_save")
async def controller_array_roundtrip(check):
    """Exercise explicit controller identities across edits and native history."""
    seed = await check.call("score_compose", output_name=check.output("controller-seed"),
                            title="Controller array guard", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    await check.edit(sid, "controller.set", track_index=0, part_index=0, type="Dynamics",
                     points=[{"tick": 60, "value": 30}, {"tick": 180, "value": 64}], replace=True)
    sequence, seed_path = await check.save(sid, "controller-native")
    await check.close(sid)
    controllers = sequence["tracks"][0]["parts"][0]["controllers"]
    events = next(c["events"] for c in controllers if c["name"] == "dynamics")
    v.require([(e["pos"], e["value"]) for e in events] == [(60, 30), (180, 64)],
              "Controller serialization differs", events)
    _, members = v.read_vpr(seed_path)
    events[0][KEY] = {"marker": "first", "nested": [True, None]}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("controller-extension-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    async with check.project() as plain_target:
        before = await check.call("project_status", session_id=plain_target)
        await check.rejected("project_merge", "controller extension", session_id=plain_target,
                             path=str(source), include_tracks=True, include_tempo=False)
        v.require(await check.call("project_status", session_id=plain_target) == before,
                  "Guarded controller merge changed target")
        v.require(source.read_bytes() == original, "Guarded controller merge changed source")
    lane = {"track_index": 0, "part_index": 0, "type": "Dynamics"}
    marker = {"marker": "first", "nested": [True, None]}

    async def snapshot(session, label, expected):
        result, path = await check.save(session, "controller-" + label)
        lanes = result["tracks"][0]["parts"][0].get("controllers", [])
        events = next((c["events"] for c in lanes if c["name"] == "dynamics"), [])
        actual = [(e["pos"], e["value"], e.get(KEY)) for e in events]
        v.require(actual == expected, "Controller metadata differs", {"actual": actual, "expected": expected})
        return path

    initial = [(60, 30, marker), (180, 64, None)]
    moved = [(180, 64, None), (240, 40, marker)]
    await snapshot(sid, "initial", initial)
    await check.rejected("project_edit", "destination is ambiguous", session_id=sid,
                         operation="controller.set", options={**lane, "controller_index": 0,
                         "points": [{"tick": 180, "value": 40}]})
    await snapshot(sid, "collision", initial)
    await check.edit(sid, "controller.set", **lane, controller_index=0, points=[{"tick": 240, "value": 40}])
    await snapshot(sid, "moved", moved)
    await check.edit(sid, "undo"); await snapshot(sid, "undo", initial)
    await check.edit(sid, "redo"); await snapshot(sid, "redo", moved)
    clone = (await check.call("project_clone", session_id=sid))["session_id"]
    await check.edit(sid, "controller.remove", **lane, controller_index=1)
    await check.edit(sid, "controller.set", **lane, points=[{"tick": 240, "value": 40}])
    recreated = [(180, 64, None), (240, 40, None)]
    await snapshot(sid, "recreated", recreated)
    await check.edit(sid, "note.update", track_index=0, part_index=0, note_index=0, number=61)
    await check.edit(sid, "undo")
    await snapshot(sid, "empty-controller-unrelated-undo", recreated)
    await check.edit(sid, "undo"); await snapshot(sid, "undo-insert", moved[:1])
    await check.edit(sid, "undo"); await snapshot(sid, "undo-remove", moved)
    await check.edit(sid, "redo"); await check.edit(sid, "redo")
    await check.edit(sid, "controller.set", **lane, replace=True,
                     points=[{"tick": 240, "value": 40}])
    path = await snapshot(sid, "replace", [(240, 40, None)])
    await snapshot(clone, "clone", moved)
    await check.edit(clone, "controller.set", **lane, replace=True,
                     points=[{"tick": 240, "value": 40}])
    await snapshot(clone, "replace-marked", [(240, 40, None)])
    await check.edit(clone, "undo"); await snapshot(clone, "undo-replace", moved)
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    await snapshot(reopened, "reopen", [(240, 40, None)])
    await check.rejected("project_edit", "controller extension mutation", session_id=clone,
                         operation="part.duplicate", options={"track_index": 0, "part_index": 0, "start_tick": 9600})
    v.require(source.read_bytes() == original, "Controller source fixture was modified")
    for session in (reopened, clone, sid): await check.close(session)



@v.feature("preservation.controller_identity_ambiguity", "preservation", "score_compose", "project_open", "project_edit", "project_save")
async def controller_identity_ambiguity(check):
    seed = await check.call("score_compose", output_name=check.output("controller-ambiguous-seed"),
                            title="Controller ambiguity", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    await check.edit(sid, "controller.set", track_index=0, part_index=0, type="Dynamics",
                     points=[{"tick": 60, "value": 30}])
    tracks = (await check.edit(sid, "track.list"))["tracks"]
    await check.edit(sid, "track.duplicate", track_index=0, name=tracks[0]["name"])
    sequence, path = await check.save(sid, "controller-ambiguous-native")
    await check.close(sid)
    _, members = v.read_vpr(path)
    for index, track in enumerate(sequence["tracks"]):
        events = next(c["events"] for c in track["parts"][0]["controllers"] if c["name"] == "dynamics")
        events[0][KEY] = {"track": index}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("controller-ambiguous-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    await check.rejected("project_open", "indistinguishable track identities", path=str(source))
    v.require(source.read_bytes() == original, "Ambiguous controller fixture was modified")


@v.feature("preservation.timesig_array_roundtrip", "preservation", "score_compose", "project_open", "project_edit", "project_save", "project_clone", "project_merge")
async def timesig_array_roundtrip(check):
    seed = await check.call("score_compose", output_name=check.output("timesig-seed"), title="Time signature extensions", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    await check.edit(sid, "time_signature.set", bar=2, numerator=3, denominator=4)
    await check.edit(sid, "time_signature.set", bar=4, numerator=5, denominator=4)
    sequence, seed_path = await check.save(sid, "timesig-native")
    await check.close(sid)
    _, members = v.read_vpr(seed_path)
    for event in sequence["masterTrack"]["timeSig"]["events"]:
        event[KEY] = {"marker": event["bar"], "nested": [True, None]}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("timesig-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    async def assert_events(session, label, expected):
        result, path = await check.save(session, "timesig-" + label)
        actual = [(e["bar"], e["numer"], e["denom"], e.get(KEY)) for e in result["masterTrack"]["timeSig"]["events"]]
        v.require(actual == expected, "Time signature metadata state differs", {"actual": actual, "expected": expected})
        return path

    def marker(bar): return {"marker": bar, "nested": [True, None]}
    initial = [(0, 4, 4, marker(0)), (2, 3, 4, marker(2)), (4, 5, 4, marker(4))]
    moved = [(0, 4, 4, marker(0)), (4, 5, 4, marker(4)), (6, 7, 8, marker(2))]
    await assert_events(sid, "initial", initial)
    await check.rejected("project_edit", "time signature destination is ambiguous", session_id=sid,
                         operation="time_signature.set", options={"time_signature_index": 1, "bar": 4, "numerator": 7, "denominator": 8})
    await assert_events(sid, "collision", initial)
    await check.edit(sid, "time_signature.set", time_signature_index=1, bar=6, numerator=7, denominator=8)
    await assert_events(sid, "move", moved)
    await check.edit(sid, "undo"); await assert_events(sid, "undo", initial)
    await check.edit(sid, "redo"); await assert_events(sid, "redo", moved)
    clone = (await check.call("project_clone", session_id=sid))["session_id"]
    await check.edit(sid, "time_signature.remove", time_signature_index=2)
    await check.edit(sid, "time_signature.set", bar=6, numerator=7, denominator=8)
    recreated = moved[:-1] + [(6, 7, 8, None)]
    await assert_events(sid, "recreated", recreated)
    await check.edit(sid, "undo"); await assert_events(sid, "undo-insert", moved[:-1])
    await check.edit(sid, "undo"); await assert_events(sid, "undo-remove", moved)
    await check.edit(sid, "redo"); await check.edit(sid, "redo")
    path = await assert_events(sid, "redo-recreated", recreated)
    await assert_events(clone, "clone", moved)
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    await assert_events(reopened, "reopen", recreated)
    v.require(source.read_bytes() == original, "Source project changed")
    for session in (reopened, clone, sid): await check.close(session)


@v.feature("preservation.tempo_array_semantics", "preservation", "score_compose", "project_edit", "project_save")
async def tempo_array_semantics(check):
    """Observe serialized tempo transitions without opening user projects."""
    seed = await check.call("score_compose", output_name=check.output("tempo-array-seed"),
                            title="Tempo array semantics", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]

    async def snapshot(label):
        sequence, path = await check.save(sid, "tempo-array-" + label)
        result = [(e["pos"], e["value"]) for e in sequence["masterTrack"]["tempo"]["events"]]
        check.evidence("tempo_" + label, {"path": str(path), "events": result})
        return result

    await check.edit(sid, "tempo.set", start_tick=480, bpm=130)
    await check.edit(sid, "tempo.set", start_tick=960, bpm=140)
    before = await snapshot("before")
    await check.edit(sid, "tempo.set", tempo_index=1, start_tick=1440, bpm=135)
    moved = await snapshot("moved")
    v.require(moved == [(0, 12000), (960, 14000), (1440, 13500)], "Unexpected tempo move")
    await check.edit(sid, "undo")
    v.require(await snapshot("undo_move") == before, "Undo did not restore tempo array")
    await check.edit(sid, "redo")
    v.require(await snapshot("redo_move") == moved, "Redo did not restore tempo array")
    await check.edit(sid, "tempo.remove", tempo_index=2)
    await check.edit(sid, "tempo.set", start_tick=1440, bpm=135)
    v.require(await snapshot("recreated") == moved, "Recreated tempo serialized differently")
    await check.close(sid)


@v.feature("preservation.tempo_array_roundtrip", "preservation", "score_compose", "project_open", "project_edit", "project_save", "project_clone", "project_clipboard", "project_create", "project_merge")
async def tempo_array_roundtrip(check):
    seed = await check.call("score_compose", output_name=check.output("tempo-extension-seed"),
                            title="Tempo extensions", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    await check.edit(sid, "tempo.set", start_tick=480, bpm=130)
    await check.edit(sid, "tempo.set", start_tick=960, bpm=140)
    sequence, seed_path = await check.save(sid, "tempo-extension-native")
    await check.close(sid)
    _, members = v.read_vpr(seed_path)
    events = sequence["masterTrack"]["tempo"]["events"]
    for event in events:
        event[KEY] = {"marker": "event-" + str(event["pos"]), "nested": [True, None]}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("tempo-extension-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]

    async def assert_events(session, label, expected):
        result, path = await check.save(session, "tempo-extension-" + label)
        actual = [(event["pos"], event["value"], event.get(KEY))
                  for event in result["masterTrack"]["tempo"]["events"]]
        v.require(actual == expected, "Tempo metadata state differs", {"actual": actual, "expected": expected})
        check.evidence("tempo_extension_" + label, {"path": str(path), "events": actual})
        return path

    def marker(pos):
        return {"marker": "event-" + str(pos), "nested": [True, None]}
    initial = [(0, 12000, marker(0)), (480, 13000, marker(480)), (960, 14000, marker(960))]
    moved = [(0, 12000, marker(0)), (960, 14000, marker(960)), (1440, 13500, marker(480))]
    await assert_events(sid, "initial", initial)
    await check.rejected("project_edit", "tempo destination is ambiguous", session_id=sid,
                         operation="tempo.set", options={"tempo_index": 1, "start_tick": 960, "bpm": 135})
    await assert_events(sid, "collision", initial)
    await check.edit(sid, "tempo.set", tempo_index=1, start_tick=480, bpm=130)
    await assert_events(sid, "no-op", initial)
    await check.call("project_merge", session_id=sid, path=str(seed_path), include_tracks=False,
                     include_tempo=True, offset_tick=1920)
    merged, _ = await check.save(sid, "tempo-extension-target-merge")
    merged_events = merged["masterTrack"]["tempo"]["events"]
    v.require([e["pos"] for e in merged_events] == [0, 480, 960, 1920, 2400, 2880] and
              [e.get(KEY) for e in merged_events] == [marker(0), marker(480), marker(960), None, None, None],
              "Merge changed target tempo extensions")
    await check.edit(sid, "undo")
    await assert_events(sid, "merge-target-undo", initial)
    plain = (await check.call("project_open", path=str(seed_path)))["session_id"]
    try:
        await check.edit(plain, "tempo.set", start_tick=1920, bpm=90)
        await check.call("project_merge", session_id=plain, path=str(source), include_tracks=False,
                         include_tempo=True, replace_tempo=True)
        await assert_events(plain, "merge-source-replace", initial)
        await check.edit(plain, "undo")
        undone, _ = await check.save(plain, "tempo-extension-source-merge-undo")
        v.require([e["pos"] for e in undone["masterTrack"]["tempo"]["events"]] == [0, 480, 960, 1920] and
                  all(KEY not in e for e in undone["masterTrack"]["tempo"]["events"]),
                  "Source tempo merge undo changed original target")
    finally:
        await check.close(plain)
    clip = (await check.call("project_clipboard", session_id=sid, operation="copy",
                             options={"kind": "tracks", "indices": [0]}))["clipboard_id"]
    try:
        target = (await check.call("project_create", title="Tempo clipboard target"))["session_id"]
        try:
            await check.call("project_clipboard", session_id=target, operation="paste", options={"clipboard_id": clip})
            pasted, _ = await check.save(target, "tempo-clipboard-target")
            v.require(all(KEY not in event for event in pasted["masterTrack"]["tempo"]["events"]),
                      "Track-only clipboard paste incorrectly transferred project tempo metadata")
        finally:
            await check.close(target)
    finally:
        await check.call("project_clipboard", operation="clear", options={"clipboard_id": clip})
    await check.edit(sid, "tempo.set", tempo_index=1, start_tick=1440, bpm=135)
    await assert_events(sid, "moved", moved)
    await check.edit(sid, "undo")
    await assert_events(sid, "undo", initial)
    await check.edit(sid, "redo")
    await assert_events(sid, "redo", moved)
    clone = (await check.call("project_clone", session_id=sid))["session_id"]
    await check.edit(sid, "tempo.remove", tempo_index=2)
    await check.edit(sid, "tempo.set", start_tick=1440, bpm=135)
    recreated = moved[:-1] + [(1440, 13500, None)]
    path = await assert_events(sid, "recreated", recreated)
    await check.edit(sid, "undo")
    await assert_events(sid, "undo-recreate", moved[:-1])
    await check.edit(sid, "undo")
    await assert_events(sid, "undo-remove", moved)
    await check.edit(sid, "redo")
    await check.edit(sid, "redo")
    path = await assert_events(sid, "redo-recreate", recreated)
    await assert_events(clone, "clone", moved)
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    await assert_events(reopened, "reopened", recreated)
    v.require(source.read_bytes() == original, "Source project changed")
    for session in (reopened, clone, sid):
        await check.close(session)


@v.feature("preservation.tempo_only_similar_tracks", "preservation", "score_compose", "project_open", "project_edit", "project_save")
async def tempo_only_similar_tracks(check):
    seed = await check.call("score_compose", output_name=check.output("tempo-similar-seed"),
                            title="Tempo-only metadata", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    await check.edit(sid, "track.duplicate", track_index=0)
    await check.edit(sid, "automation.set", scope="track_volume", track_index=1,
                     points=[{"tick": 0, "value": -120}], replace=True)
    sequence, seed_path = await check.save(sid, "tempo-similar-native")
    await check.close(sid)
    v.require(sequence["tracks"][0]["volume"] != sequence["tracks"][1]["volume"],
              "Fixture does not contain different known track values")
    _, members = v.read_vpr(seed_path)
    sequence["masterTrack"]["tempo"]["events"][0][KEY] = "tempo-only"
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("tempo-similar-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    target = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        await check.edit(target, "tempo.set", tempo_index=0, start_tick=0, bpm=125)
        saved, path = await check.save(target, "tempo-similar-saved")
        v.require(saved["masterTrack"]["tempo"]["events"][0][KEY] == "tempo-only" and
                  saved["tracks"][0]["volume"] != saved["tracks"][1]["volume"],
                  "Tempo-only extension or known track values were lost")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        await check.close(reopened)
    finally:
        await check.close(target)
    v.require(source.read_bytes() == original, "Tempo-only source changed")


def properties(sequence, members):
    track = sequence["tracks"][0]
    part = track["parts"][0]
    note = part["notes"][0]
    return {"root": sequence.get(KEY), "master": sequence["masterTrack"].get(KEY),
            "track": track.get(KEY), "part": part.get(KEY), "note": note.get(KEY),
            "master_nested": sequence["masterTrack"]["loop"].get(NESTED_KEY),
            "note_nested": note["exp"].get(NESTED_KEY),
            "extra": members.get(EXTRA) == EXTRA_BYTES,
            "extra_audio": members.get(EXTRA_AUDIO) == EXTRA_BYTES,
            "extra_root": members.get(EXTRA_ROOT) == EXTRA_BYTES}


@v.feature("preservation.unknown_fields", "preservation", "score_compose", "project_open", "project_edit",
           "project_save", "project_clone")
async def unknown_fields(check):
    seed = await check.call("score_compose", output_name=check.output("preservation-seed"),
                            title="Preservation probe", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    seed_session = seed["native_session"]["session_id"]
    await check.close(seed_session)
    sequence, members = v.read_vpr(seed["path"])
    for obj, value in ((sequence, SENTINELS["root"]), (sequence["masterTrack"], SENTINELS["master"]),
                       (sequence["tracks"][0], SENTINELS["track"]),
                       (sequence["tracks"][0]["parts"][0], SENTINELS["part"]),
                       (sequence["tracks"][0]["parts"][0]["notes"][0], SENTINELS["note"])):
        obj[KEY] = value
    sequence["masterTrack"]["loop"][NESTED_KEY] = SENTINELS["master_nested"]
    sequence["tracks"][0]["parts"][0]["notes"][0]["exp"][NESTED_KEY] = SENTINELS["note_nested"]
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    members[EXTRA] = EXTRA_BYTES
    members[EXTRA_AUDIO] = EXTRA_BYTES
    members[EXTRA_ROOT] = EXTRA_BYTES
    source = v.ROOT / "output" / check.output("preservation-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    original = source.read_bytes()
    identifier = (await check.call("project_open", path=str(source)))['session_id']
    await check.edit(identifier, "note.update", track_index=0, part_index=0, note_index=0,
                     number=61, expression={"Accent": 51})
    saved, path = await check.save(identifier, "preservation-edited")
    _, saved_members = v.read_vpr(path)
    state = properties(saved, saved_members)
    check.evidence("saved_unknown_fields", {"source": str(source), "saved": str(path), "observed": state})
    reopened = (await check.call("project_open", path=str(path)))['session_id']
    actual_note = (await check.edit(reopened, "note.list", track_index=0, part_index=0))["notes"][0]
    v.require(actual_note["number"] == 61, "Known note edit did not persist")
    v.require(actual_note["expression"]["Accent"] == 51 and saved["tracks"][0]["parts"][0]["notes"][0]["exp"]["accent"] == 51,
              "Known expression edit was overwritten by retained unknown data")
    reopened_saved, reopened_path = await check.save(reopened, "preservation-reopened")
    _, reopened_members = v.read_vpr(reopened_path)
    reopened_state = properties(reopened_saved, reopened_members)
    check.evidence("reopened_unknown_fields", {"saved": str(reopened_path), "observed": reopened_state})
    clone = (await check.call("project_clone", session_id=identifier))["session_id"]
    await check.close(identifier)
    clone_saved, clone_path = await check.save(clone, "preservation-clone")
    _, clone_members = v.read_vpr(clone_path)
    clone_state = properties(clone_saved, clone_members)
    check.evidence("clone_unknown_fields", {"saved": str(clone_path), "observed": clone_state})
    v.require(source.read_bytes() == original, "Native editing modified the input VPR")
    expected = {**SENTINELS, "extra": True, "extra_audio": True, "extra_root": True}
    v.require(state == expected and reopened_state == expected and clone_state == expected,
              "Unknown project data did not roundtrip", {"save": state, "reopened": reopened_state, "clone": clone_state})
    await check.close(clone)
    await check.close(reopened)


@v.feature("preservation.identity", "preservation", "score_compose", "project_open", "project_edit", "project_save")
async def identity(check):
    seed = await check.call("score_compose", output_name=check.output("identity-seed"), title="Identity probe", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0},
                                   {"start": 1, "duration": .5, "pitch": 64, "lyric": "い", "phoneme": "i", "lang_id": 0}])
    seed_id = seed["native_session"]["session_id"]
    await check.edit(seed_id, "track.duplicate", track_index=0, name="Other")
    sequence, native_seed = await check.save(seed_id, "identity-native-seed")
    await check.close(seed_id)
    _, members = v.read_vpr(native_seed)
    for track_index, track in enumerate(sequence["tracks"]):
        track[KEY] = f"track-{track_index}"
        for part_index, part in enumerate(track["parts"]):
            part[KEY] = f"part-{track_index}-{part_index}"
            for note_index, note in enumerate(part["notes"]):
                note[KEY] = f"note-{track_index}-{part_index}-{note_index}"
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("identity-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    identifier = (await check.call("project_open", path=str(source)))["session_id"]
    await check.edit(identifier, "track.reorder", track_index=0, to_index=1)
    await check.edit(identifier, "track.update", track_index=1, name="Renamed original")
    await check.edit(identifier, "note.update", track_index=1, part_index=0, note_index=0,
                     start_tick=120, number=61)
    saved, path = await check.save(identifier, "identity-moved")
    moved = saved["tracks"][1]
    require = v.require
    require(saved["tracks"][0].get(KEY) == "track-1" and moved.get(KEY) == "track-0",
            "Reordered track metadata attached to the wrong track")
    require(moved["parts"][0].get(KEY) == "part-0-0" and
            moved["parts"][0]["notes"][0].get(KEY) == "note-0-0-0",
            "Part or moved/edited note metadata was lost")
    await check.edit(identifier, "note.remove", track_index=1, part_index=0, note_index=0)
    await check.edit(identifier, "note.add", track_index=1, part_index=0, start_tick=120,
                     duration_tick=240, number=61, lyric="あ", phonemes="a", lang_id=0)
    replaced, _ = await check.save(identifier, "identity-replacement")
    require(KEY not in replaced["tracks"][1]["parts"][0]["notes"][0],
            "Removed note metadata was attached to a replacement note")
    await check.edit(identifier, "undo")
    await check.edit(identifier, "undo")
    undone, _ = await check.save(identifier, "identity-undo")
    require(undone["tracks"][1]["parts"][0]["notes"][0].get(KEY) == "note-0-0-0",
            "Undo failed to restore original note metadata")
    await check.edit(identifier, "redo")
    await check.edit(identifier, "redo")
    redone, _ = await check.save(identifier, "identity-redo")
    require(KEY not in redone["tracks"][1]["parts"][0]["notes"][0],
            "Redo attached deleted metadata to replacement note")
    check.evidence("identity_outputs", {"source": str(source), "moved": str(path)})
    await check.close(identifier)


@v.feature("preservation.parameter_edits", "preservation", "score_compose", "project_edit", "project_open", "project_save")
async def parameter_edits(check):
    seed = await check.call("score_compose", output_name=check.output("parameter-seed"), title="Preserved parameters", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    sequence[KEY] = "root"
    sequence["masterTrack"]["loop"][KEY] = "loop"
    track = sequence["tracks"][0]
    track[KEY] = "track"
    part = track["parts"][0]
    part[KEY] = "part"
    part["notes"][0][KEY] = "note"
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("parameter-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    scope = {"track_index": 0, "part_index": 0}
    await check.edit(sid, "sequence.update", title="Changed title")
    await check.edit(sid, "tempo.set", start_tick=0, bpm=130)
    await check.edit(sid, "loop.set", start_tick=0, end_tick=1920, enabled=True)
    await check.edit(sid, "tuning.set", value=442)
    await check.edit(sid, "note.batch_update", **scope, note_indices=[0], transpose=2)
    await check.edit(sid, "performance.set", **scope, voice_colors={"S5Air": 25})
    await check.edit(sid, "vibrato.set", **scope, note_index=0, ai_enabled=False)
    saved, path = await check.save(sid, "parameter-preserved")
    v.require(saved[KEY] == "root" and saved["masterTrack"]["loop"][KEY] == "loop", "Root/loop metadata changed")
    part = saved["tracks"][0]["parts"][0]
    v.require(saved["tracks"][0][KEY] == "track" and part[KEY] == "part" and part["notes"][0][KEY] == "note",
              "Parameter edits lost entity metadata")
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    note = (await check.edit(reopened, "note.list", **scope))["notes"][0]
    v.require(note["number"] == 62 and not note["ai_vibrato_enabled"], "Parameter edits were replaced by old data", note)
    v.require((await check.edit(reopened, "tuning.get"))["value"] == 442, "Native tuning changed")
    check.evidence("parameter_preservation", {"source": str(source), "saved": str(path), "note": note})
    await check.close(reopened)
    await check.close(sid)


@v.feature("preservation.duplicates", "preservation", "score_compose", "project_edit", "project_open", "project_save", "project_clone")
async def duplicates(check):
    seed = await check.call("score_compose", output_name=check.output("duplicates-seed"), title="Duplicate metadata", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    track = sequence["tracks"][0]; part = track["parts"][0]; note = part["notes"][0]
    track[KEY] = "track-copy"; part[KEY] = "part-copy"; note[KEY] = "note-copy"
    note["exp"][NESTED_KEY] = {"copy": [1, 2]}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("duplicates-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    identifier = (await check.call("project_open", path=str(source)))["session_id"]
    await check.edit(identifier, "track.duplicate", track_index=0, name=track["name"])
    saved, same_path = await check.save(identifier, "duplicates-same-name")
    def check_track(track):
        v.require(track[KEY] == "track-copy", "Copied track metadata lost")
        v.require(track["parts"][0][KEY] == "part-copy", "Copied part metadata lost")
        v.require(track["parts"][0]["notes"][0][KEY] == "note-copy" and
                  track["parts"][0]["notes"][0]["exp"][NESTED_KEY] == {"copy": [1, 2]}, "Copied note metadata lost")
    v.require(len(saved["tracks"]) == 2 and saved["tracks"][0]["name"] == saved["tracks"][1]["name"],
              "Test requires same-name duplicate tracks")
    for track in saved["tracks"]: check_track(track)
    divergent = json.loads(json.dumps(saved)); divergent["tracks"][1][KEY] = "different-unknown-value"
    _, same_members = v.read_vpr(same_path)
    same_members["Project/sequence.json"] = json.dumps(divergent, ensure_ascii=False).encode("utf-8")
    ambiguous_path = v.ROOT / "output" / check.output("duplicates-ambiguous")
    with zipfile.ZipFile(ambiguous_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in same_members.items(): archive.writestr(name, payload)
    ambiguous_bytes = ambiguous_path.read_bytes()
    await check.rejected("project_open", "indistinguishable|ambiguous", path=str(ambiguous_path))
    v.require(ambiguous_path.read_bytes() == ambiguous_bytes, "Ambiguous open changed the source")
    await check.edit(identifier, "undo")
    undone, _ = await check.save(identifier, "duplicates-undo")
    v.require(len(undone["tracks"]) == 1, "Undo did not remove duplicate")
    check_track(undone["tracks"][0])
    await check.edit(identifier, "redo")
    await check.edit(identifier, "note.duplicate", track_index=0, part_index=0, note_index=0, start_tick=1920)
    await check.edit(identifier, "part.duplicate", track_index=0, part_index=0, start_tick=9600)
    expanded, path = await check.save(identifier, "duplicates-expanded")
    v.require(len(expanded["tracks"]) == 2, "Redo did not restore duplicated track")
    for track in expanded["tracks"]: check_track(track)
    parts = expanded["tracks"][0]["parts"]
    v.require(len(parts) == 2 and all(p[KEY] == "part-copy" for p in parts), "Part duplicate lost metadata")
    v.require(all(len(p["notes"]) == 2 and all(n[KEY] == "note-copy" and n["exp"][NESTED_KEY] == {"copy": [1, 2]}
                                               for n in p["notes"]) for p in parts), "Duplicated notes lost metadata")
    await check.edit(identifier, "undo"); await check.edit(identifier, "undo")
    reverted, _ = await check.save(identifier, "duplicates-children-undo")
    v.require(len(reverted["tracks"][0]["parts"]) == 1 and len(reverted["tracks"][0]["parts"][0]["notes"]) == 1,
              "Child duplicate undo did not restore the source tree")
    await check.edit(identifier, "redo"); await check.edit(identifier, "redo")
    expanded, path = await check.save(identifier, "duplicates-children-redo")
    v.require(len(expanded["tracks"][0]["parts"]) == 2 and
              all(n[KEY] == "note-copy" for p in expanded["tracks"][0]["parts"] for n in p["notes"]),
              "Child duplicate redo lost note metadata")
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    clone = (await check.call("project_clone", session_id=reopened))["session_id"]
    await check.close(reopened); await check.close(identifier)
    cloned, _ = await check.save(clone, "duplicates-clone")
    v.require(len(cloned["tracks"]) == 2 and all(t[KEY] == "track-copy" for t in cloned["tracks"]),
              "Duplicate metadata did not survive source-independent clone")
    v.require(source.read_bytes() == original, "Duplicate operations changed the original VPR")
    await check.close(clone)


@v.feature("preservation.note_split", "preservation", "score_compose", "project_edit", "project_open", "project_save")
async def note_split(check):
    seed = await check.call("score_compose", output_name=check.output("split-seed"), title="Split metadata", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    note = sequence["tracks"][0]["parts"][0]["notes"][0]
    note[KEY] = "split-note"
    note["exp"][NESTED_KEY] = {"split": [1, 2]}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("split-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    identifier = (await check.call("project_open", path=str(source)))["session_id"]
    scope = {"track_index": 0, "part_index": 0}
    await check.edit(identifier, "note.split", **scope, note_index=0, split_tick=240)
    def verify(saved, count):
        notes = saved["tracks"][0]["parts"][0]["notes"]
        v.require(len(notes) == count and all(n.get(KEY) == "split-note" and
                  n["exp"].get(NESTED_KEY) == {"split": [1, 2]} for n in notes), "Split note metadata changed")
    saved, _ = await check.save(identifier, "split-result"); verify(saved, 2)
    await check.edit(identifier, "undo")
    saved, _ = await check.save(identifier, "split-undo"); verify(saved, 1)
    await check.edit(identifier, "redo")
    saved, path = await check.save(identifier, "split-redo"); verify(saved, 2)
    conflict, conflict_members = v.read_vpr(path)
    conflict["tracks"][0]["parts"][0]["notes"][1][KEY] = "different"
    conflict_members["Project/sequence.json"] = json.dumps(conflict, ensure_ascii=False).encode("utf-8")
    conflict_path = v.ROOT / "output" / check.output("join-conflict")
    with zipfile.ZipFile(conflict_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in conflict_members.items(): archive.writestr(name, payload)
    conflict_id = (await check.call("project_open", path=str(conflict_path)))["session_id"]
    await check.rejected("project_edit", "conflicting note join metadata", session_id=conflict_id,
                         operation="note.join", options={**scope, "note_indices": [0, 1]})
    conflict_saved, _ = await check.save(conflict_id, "join-conflict-rollback")
    v.require([n[KEY] for n in conflict_saved["tracks"][0]["parts"][0]["notes"]] == ["split-note", "different"],
              "Join conflict did not roll back both notes and metadata")
    await check.close(conflict_id)
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    saved, _ = await check.save(reopened, "split-reopen"); verify(saved, 2)
    await check.edit(reopened, "note.join", **scope, note_indices=[0, 1])
    saved, _ = await check.save(reopened, "join-result"); verify(saved, 1)
    await check.edit(reopened, "undo")
    saved, _ = await check.save(reopened, "join-undo"); verify(saved, 2)
    await check.edit(reopened, "redo")
    saved, path = await check.save(reopened, "join-redo"); verify(saved, 1)
    joined = (await check.call("project_open", path=str(path)))["session_id"]
    saved, _ = await check.save(joined, "join-reopen"); verify(saved, 1)
    await check.close(joined)
    await check.close(reopened); await check.close(identifier)


@v.feature("preservation.part_split_join", "preservation", "score_compose", "project_edit", "project_open", "project_save")
async def part_split_join(check):
    seed = await check.call("score_compose", output_name=check.output("part-split-seed"), title="Part split", bpm=120,
                            notes=[{"start": i, "duration": 1, "pitch": 60 + i, "lyric": "あ", "phoneme": "a", "lang_id": 0}
                                   for i in (0, 1, 3)])
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    part = sequence["tracks"][0]["parts"][0]; part[KEY] = "part"
    for i, note in enumerate(part["notes"]): note[KEY] = "note-" + str(i)
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("part-split-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    await check.edit(sid, "part.split", track_index=0, part_index=0, split_tick=720)
    def verify(saved, counts):
        parts = saved["tracks"][0]["parts"]
        v.require([len(p["notes"]) for p in parts] == counts and all(p[KEY] == "part" for p in parts), "Part split/join changed metadata")
        v.require([n[KEY] for p in parts for n in p["notes"]] == ["note-0", "note-1", "note-2"], "Part split/join changed note metadata")
    saved, _ = await check.save(sid, "part-split"); verify(saved, [2, 1])
    await check.edit(sid, "undo"); saved, _ = await check.save(sid, "part-split-undo"); verify(saved, [3])
    await check.edit(sid, "redo"); saved, path = await check.save(sid, "part-split-redo"); verify(saved, [2, 1])
    conflict, cm = v.read_vpr(path); conflict["tracks"][0]["parts"][1][KEY] = "different"
    cm["Project/sequence.json"] = json.dumps(conflict, ensure_ascii=False).encode("utf-8")
    cp = v.ROOT / "output" / check.output("part-join-conflict")
    with zipfile.ZipFile(cp, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in cm.items(): archive.writestr(name, payload)
    cid = (await check.call("project_open", path=str(cp)))["session_id"]
    await check.rejected("project_edit", "conflicting part join metadata", session_id=cid,
                         operation="part.join", options={"track_index": 0, "part_indices": [0, 1]})
    saved, _ = await check.save(cid, "part-conflict-rollback")
    v.require([p[KEY] for p in saved["tracks"][0]["parts"]] == ["part", "different"], "Part conflict rollback changed metadata")
    await check.close(cid)
    await check.edit(sid, "part.join", track_index=0, part_indices=[0, 1])
    saved, _ = await check.save(sid, "part-join"); verify(saved, [3])
    await check.edit(sid, "undo"); saved, _ = await check.save(sid, "part-join-undo"); verify(saved, [2, 1])
    await check.edit(sid, "redo"); saved, path = await check.save(sid, "part-join-redo"); verify(saved, [3])
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    saved, _ = await check.save(reopened, "part-join-reopen"); verify(saved, [3])
    await check.close(reopened); await check.close(sid)


@v.feature("preservation.clipboard_old_history", "preservation", "score_compose", "project_open", "project_create",
           "project_clipboard", "project_edit", "project_save")
async def clipboard_old_history(check):
    seed = await check.call("score_compose", output_name=check.output("history-source-seed"), title="History source", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    sequence["tracks"][0][KEY] = "transferred-track"
    sequence["tracks"][0]["parts"][0]["notes"][0][KEY] = "transferred-note"
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("history-source")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    clip = (await check.call("project_clipboard", session_id=sid, operation="copy",
                             options={"kind": "tracks", "indices": [0]}))["clipboard_id"]
    await check.close(sid)
    try:
        async with check.project() as target:
            await check.edit(target, "track.create", name="old")
            await check.edit(target, "track.update", track_index=0, name="old-edited")
            await check.call("project_clipboard", session_id=target, operation="paste",
                             options={"clipboard_id": clip, "offset_tick": 960})
            saved, _ = await check.save(target, "history-paste")
            v.require(len(saved["tracks"]) == 2 and saved["tracks"][1][KEY] == "transferred-track", "Paste lost extension")
            await check.edit(target, "undo")
            saved, _ = await check.save(target, "history-unpaste")
            v.require(len(saved["tracks"]) == 1 and saved["tracks"][0]["name"] == "old-edited", "Undo paste changed old track")
            await check.edit(target, "undo")
            saved, _ = await check.save(target, "history-old-undo")
            v.require(len(saved["tracks"]) == 1 and saved["tracks"][0]["name"] == "old", "Old edit undo failed")
            await check.edit(target, "undo")
            saved, _ = await check.save(target, "history-old-empty")
            v.require(not saved.get("tracks", []), "Old create undo failed")
            await check.edit(target, "redo"); await check.edit(target, "redo"); await check.edit(target, "redo")
            saved, path = await check.save(target, "history-redo-paste")
            v.require(len(saved["tracks"]) == 2 and saved["tracks"][0]["name"] == "old-edited" and
                      saved["tracks"][1][KEY] == "transferred-track" and
                      saved["tracks"][1]["parts"][0]["notes"][0][KEY] == "transferred-note", "History redo lost data")
            reopened = (await check.call("project_open", path=str(path)))["session_id"]
            await check.close(reopened)
            await check.edit(target, "undo"); await check.edit(target, "undo")
            await check.edit(target, "track.update", track_index=0, name="branch")
            status = await check.edit(target, "history.status")
            v.require(not status["can_redo"], "New branch retained redo")
            saved, _ = await check.save(target, "history-branch")
            v.require(len(saved["tracks"]) == 1 and saved["tracks"][0]["name"] == "branch", "Branch changed old state")
    finally:
        await check.call("project_clipboard", operation="clear", options={"clipboard_id": clip})


@v.feature("preservation.native_duplicate_order", "preservation", "score_compose", "project_edit", "project_save", "project_open")
async def native_duplicate_order(check):
    seed = await check.call("score_compose", output_name=check.output("duplicate-order-seed"), title="Native order", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0},
                                   {"start": 1, "duration": .5, "pitch": 64, "lyric": "い", "phoneme": "i", "lang_id": 0}])
    identifier = seed["native_session"]["session_id"]
    original = (await check.edit(identifier, "track.list"))["tracks"][0]
    await check.edit(identifier, "track.update", track_index=0, color=3)
    await check.edit(identifier, "track.duplicate", track_index=0, name=original["name"])
    await check.edit(identifier, "track.update", track_index=1, color=7)
    await check.edit(identifier, "track.reorder", track_index=0, to_index=1)
    await check.edit(identifier, "part.duplicate", track_index=0, part_index=0, start_tick=9600)
    await check.edit(identifier, "note.duplicate", track_index=0, part_index=0, note_index=0, start_tick=1920)
    tracks = (await check.edit(identifier, "track.list"))["tracks"]
    parts = (await check.edit(identifier, "part.list", track_index=0))["parts"]
    notes = (await check.edit(identifier, "note.list", track_index=0, part_index=0))["notes"]
    saved, path = await check.save(identifier, "duplicate-order")
    v.require([(t["name"], t["color"], t["type"]) for t in tracks] ==
              [(t["name"], t["color"], {0: "Midi", 1: "Audio", 2: "MidiAi"}[t["type"]]) for t in saved["tracks"]],
              "Native VPR track order differs from live enumeration")
    v.require([(p["start_tick"], p["duration_tick"]) for p in parts] ==
              [(p["pos"], p["duration"]) for p in saved["tracks"][0]["parts"]],
              "Native VPR part order differs from live enumeration")
    v.require([(n["start_tick"], n["number"]) for n in notes] ==
              [(n["pos"], n["number"]) for n in saved["tracks"][0]["parts"][0]["notes"]],
              "Native VPR note order differs from live enumeration")
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    reopened_tracks = (await check.edit(reopened, "track.list"))["tracks"]
    v.require([(t["name"], t["color"], t["type"]) for t in reopened_tracks] ==
              [(t["name"], t["color"], t["type"]) for t in tracks], "Native reopen changed track order")
    check.evidence("native_duplicate_order", {"vpr": str(path), "tracks": tracks, "parts": parts,
                                              "notes": [(n["start_tick"], n["number"]) for n in notes]})
    await check.close(reopened)
    await check.close(identifier)


if __name__ == "__main__":
    raise SystemExit(v.main())
