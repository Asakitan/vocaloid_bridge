"""Exercise JSON Patch validity provenance on an isolated ordinary AI project."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import zipfile

import verify_features as v

SIDE = "vocaloid_bridge/phoneme-validity-v1.json"
KEY = "x_patch_owner_27"


async def fixture(check):
    seed = await check.call("score_compose", output_name=check.output("patch-validity-seed"), title="Patch validity",
                            bpm=120, notes=[{"start": 0, "duration": 1, "pitch": 60,
                                             "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    try:
        await check.edit(sid, "track.duplicate", track_index=0, name="Second")
        await check.edit(sid, "note.update", track_index=0, part_index=0, note_index=0,
                         phonemes="a", is_valid_phonemes=False)
        sequence, path = await check.save(sid, "patch-validity-native-source")
    finally:
        await check.close(sid)
    _, members = v.read_vpr(path)
    v.require(SIDE in members and len(sequence["tracks"]) == 2, "Missing expected sidecar or tracks")
    for track, marker in zip(sequence["tracks"], ("A", "B")):
        track[KEY] = marker
        part = track["parts"][0]
        v.require(all(not n.get("directPitches") for n in part["notes"]), "Unexpected pitch extension")
        part["notes"][0][KEY] = marker
    side = json.loads(members[SIDE])
    v.require(len(side["Notes"]) == 1 and side["Notes"][0]["TrackIndex"] == 0, "Unexpected sidecar", side)
    side["x_sidecar_root_27"] = {"keep": True}
    side["Notes"][0]["x_sidecar_entry_27"] = {"keep": "A"}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    members[SIDE] = json.dumps(side, ensure_ascii=False).encode("utf-8")
    members["Project/probe-patch-resource.bin"] = b"patch-sidecar-27"
    source = v.ROOT / "output" / check.output("patch-validity-source")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return source, source.read_bytes(), sequence, members


async def apply(check, source, label, operations):
    result = await check.call("score_patch", path=str(source), output_name=check.output(label), operations=operations)
    data, members = v.read_vpr(result["path"])
    v.require(members["Project/probe-patch-resource.bin"] == b"patch-sidecar-27", "Opaque resource changed")
    side = json.loads(members[SIDE])
    v.require(side["x_sidecar_root_27"] == {"keep": True}, "Unknown sidecar root field changed")
    return Path(result["path"]), data, side, members


def flags(side):
    return [(e["TrackIndex"], e["PartIndex"], e["NoteIndex"], e["Note"]["Position"],
             e.get("x_sidecar_entry_27")) for e in side["Notes"]]


async def native_roundtrip(check, path, expected):
    sid = (await check.call("project_open", path=str(path)))["session_id"]
    try:
        actual = []
        for index in range(len(expected)):
            notes = (await check.edit(sid, "note.list", track_index=index, part_index=0))["notes"]
            actual.append([(n["start_tick"], n["is_valid_phonemes"], n["number"], n["duration_tick"]) for n in notes])
        v.require(actual == expected, "Native opened wrong validity identities", actual)
        _, saved = await check.save(sid, "patch-validity-saved")
    finally:
        await check.close(sid)
    sid = (await check.call("project_open", path=str(saved)))["session_id"]
    try:
        actual = []
        for index in range(len(expected)):
            notes = (await check.edit(sid, "note.list", track_index=index, part_index=0))["notes"]
            actual.append([(n["start_tick"], n["is_valid_phonemes"], n["number"], n["duration_tick"]) for n in notes])
        v.require(actual == expected, "Native reopened wrong validity identities", actual)
    finally:
        await check.close(sid)


@v.feature("preservation.patch_sidecar_identity_27", "preservation",
           "score_compose", "score_patch", "project_edit", "project_open", "project_save")
async def patch_sidecar_identity(check):
    source, original, sequence, source_members = await fixture(check)
    notes = "/tracks/0/parts/0/notes"
    path, copied, side, _ = await apply(check, source, "patch-copy-invalid", [
        {"op": "copy", "from": notes + "/0", "path": notes + "/-"},
        {"op": "replace", "path": notes + "/1/pos", "value": 960},
    ])
    check.evidence("copied_sidecar", side)
    v.require(flags(side) == [(0, 0, 0, 0, {"keep": "A"}), (0, 0, 1, 960, {"keep": "A"})],
              "Copied invalid note did not carry its validity", flags(side))
    await native_roundtrip(check, path, [[(0, False, 60, 480), (960, False, 60, 480)], [(0, True, 60, 480)]])

    path, moved, side, _ = await apply(check, source, "patch-move-track", [
        {"op": "move", "from": "/tracks/1", "path": "/tracks/0"}])
    v.require([track[KEY] for track in moved["tracks"]] == ["B", "A"] and
              flags(side) == [(1, 0, 0, 0, {"keep": "A"})], "Moved track lost sidecar owner", flags(side))
    await native_roundtrip(check, path, [[(0, True, 60, 480)], [(0, False, 60, 480)]])

    path, duplicated, side, _ = await apply(check, source, "patch-copy-track", [
        {"op": "copy", "from": "/tracks/0", "path": "/tracks/-"}])
    v.require([track[KEY] for track in duplicated["tracks"]] == ["A", "B", "A"] and
              flags(side) == [(0, 0, 0, 0, {"keep": "A"}), (2, 0, 0, 0, {"keep": "A"})],
              "Copied track lost invalid flag", flags(side))
    await native_roundtrip(check, path, [[(0, False, 60, 480)], [(0, True, 60, 480)], [(0, False, 60, 480)]])

    path, adjusted, side, _ = await apply(check, source, "patch-adjust-invalid", [
        {"op": "replace", "path": notes + "/0/pos", "value": 120},
        {"op": "replace", "path": notes + "/0/duration", "value": 240},
        {"op": "replace", "path": notes + "/0/number", "value": 61},
    ])
    item = side["Notes"][0]["Note"]
    v.require(flags(side) == [(0, 0, 0, 120, {"keep": "A"})] and
              item["Duration"] == 240 and item["Number"] == 61,
              "Edited invalid note identity did not follow its musical fields", side)
    await native_roundtrip(check, path, [[(120, False, 61, 240)], [(0, True, 60, 480)]])

    path, deleted, side, _ = await apply(check, source, "patch-delete-invalid", [
        {"op": "remove", "path": notes + "/0"}])
    v.require(not side["Notes"] and not deleted["tracks"][0]["parts"][0]["notes"],
              "Deleted note retained sidecar identity", side)
    await native_roundtrip(check, path, [[], [(0, True, 60, 480)]])

    second = deepcopy(sequence["tracks"][1]["parts"][0]["notes"][0])
    path, replaced, side, _ = await apply(check, source, "patch-replace-identical", [
        {"op": "replace", "path": notes + "/0", "value": second}])
    v.require(not side["Notes"] and replaced["tracks"][0]["parts"][0]["notes"][0][KEY] == "B",
              "Replaced note inherited prior validity", side)
    await native_roundtrip(check, path, [[(0, True, 60, 480)], [(0, True, 60, 480)]])

    path, stable, side, stable_members = await apply(check, source, "patch-identity-stable", [
        {"op": "move", "from": "/tracks/1", "path": "/tracks/0"},
        {"op": "move", "from": "/tracks/0", "path": "/tracks/1"},
        {"op": "test", "path": "/tracks/0/parts/0/notes/0/lyric", "value": "あ"},
        {"op": "replace", "path": "/tracks/0/parts/0/notes/0/velocity", "value": 72},
        {"op": "replace", "path": "/title", "value": "Patched title"},
    ])
    v.require(stable_members[SIDE] == source_members[SIDE] and stable["title"] == "Patched title",
              "Unchanged validity sidecar was rewritten or title lost")
    await native_roundtrip(check, path, [[(0, False, 60, 480)], [(0, True, 60, 480)]])

    for label, operations in [
        ("lyric", [{"op": "replace", "path": notes + "/0/lyric", "value": "い"}]),
        ("failed-test", [{"op": "replace", "path": "/title", "value": "not persisted"},
                         {"op": "test", "path": "/title", "value": "wrong"}]),
    ]:
        output = check.output("patch-invalid-" + label)
        await check.rejected("score_patch", "phoneme.validity|identity|test|conflict", path=str(source),
                             output_name=output, operations=operations)
        v.require(not (v.ROOT / "output" / output).exists(), "Rejected patch produced output", label)
    v.require(source.read_bytes() == original, "Patch changed source archive")


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "preservation.patch_sidecar_identity_27"])
    raise SystemExit(v.main())
