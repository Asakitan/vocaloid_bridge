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


if __name__ == "__main__":
    raise SystemExit(v.main())
