"""File-level note identity and phoneme-sidecar regression via private MCP."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import zipfile

import verify_features as v

KEY = "x_file_note_26"
SIDE = "vocaloid_bridge/phoneme-validity-v1.json"
RESOURCE = "Project/synthetic-note-26.bin"


async def fixture(check):
    notes = [
        {"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0, "velocity": 70},
        {"start": 1, "duration": .5, "pitch": 62, "lyric": "あ", "phoneme": "a", "lang_id": 0, "velocity": 90},
    ]
    seed = await check.call("score_compose", output_name=check.output("note-identity-seed"),
                            title="File note identity", bpm=120, notes=notes)
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    old = sequence["tracks"][0]["parts"][0]["notes"]
    v.require(len(old) == 2 and all(not note.get("directPitches") for note in old), "Unexpected source note data", old)
    for note, name in zip(old, ("A", "B")):
        note[KEY] = {"owner": name}
        note["exp"][KEY] = {"owner": name}
    sequence["x_root_26"] = {"keep": True}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    members[RESOURCE] = b"source-note-26"
    source = v.ROOT / "output" / check.output("note-identity-source")
    write_archive(source, members)
    return source, sequence, members, source.read_bytes()


def write_archive(path, members):
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


def request(start, pitch, source=None, raw=None):
    result = {"start": start, "duration": .5, "pitch": pitch, "lyric": "あ", "phoneme": "a"}
    if source is not None:
        result["source"] = source
    if raw is not None:
        result["raw"] = raw
    return result


def selector(notes, index):
    return {"index": index, "expected": deepcopy(notes[index])}


def summary(sequence):
    return [(n["pos"], n["number"], n.get(KEY), n["velocity"], n["langID"],
             n["exp"].get(KEY)) for n in sequence["tracks"][0]["parts"][0]["notes"]]


def source_sidecar(check, members, sequence):
    note = sequence["tracks"][0]["parts"][0]["notes"][0]
    validity = {"Format": "vocaloid-bridge-phoneme-validity", "Version": 1, "Notes": [{
        "TrackIndex": 0, "PartIndex": 0, "NoteIndex": 0,
        "Note": {"IsValid": False, "Position": note["pos"], "Duration": note["duration"],
                 "Number": note["number"], "Lyric": note["lyric"],
                 "Phonemes": note["phoneme"], "LanguageId": note["langID"]}}]}
    changed = dict(members)
    changed[SIDE] = json.dumps(validity).encode("utf-8")
    path = v.ROOT / "output" / check.output("note-sidecar-source")
    write_archive(path, changed)
    return path, path.read_bytes()


@v.feature("preservation.file_notes_identity_26", "preservation",
           "score_compose", "score_replace_notes", "score_inspect", "project_open", "project_save")
async def file_notes_identity(check):
    source, sequence, members, original = await fixture(check)
    old = sequence["tracks"][0]["parts"][0]["notes"]
    inspected = [await check.call("score_inspect", path=str(source), pointer=f"/tracks/0/parts/0/notes/{index}") for index in range(len(old))]
    v.require(inspected == old, "Source snapshot via tool differs", inspected)
    outputs = [
        request(2, 67, selector(old, 0), {"exp": {"accent": 37, KEY: {"added": 1}}}),
        request(0, 64, selector(old, 1)),
        request(1, 65),
    ]
    edited = await check.call("score_replace_notes", path=str(source), output_name=check.output("note-identity-edited"),
                              notes=outputs)
    path = Path(edited["path"])
    result, copied = v.read_vpr(path)
    expected = [(0, 64, {"owner": "B"}, 90, 0, {"owner": "B"}),
                (480, 65, None, 64, 0, None),
                (960, 67, {"owner": "A"}, 70, 0, {"owner": "A", "added": 1})]
    actual = summary(result)
    check.evidence("actual_note_identity", actual)
    v.require(actual == expected, "Selected note fields or new-note defaults do not follow the identity contract", actual)
    v.require(result["tracks"][0]["parts"][0]["notes"][2]["exp"]["accent"] == 37,
              "Raw nested edit did not merge")
    v.require(copied[RESOURCE] == b"source-note-26" and result["x_root_26"] == {"keep": True},
              "Unrelated archive data changed")
    sid = (await check.call("project_open", path=str(path)))["session_id"]
    try:
        native, saved = await check.save(sid, "note-identity-native")
        v.require(summary(native) == expected, "Native save changed note identities", summary(native))
    finally:
        await check.close(sid)
    sid = (await check.call("project_open", path=str(saved)))["session_id"]
    try:
        reopened, _ = await check.save(sid, "note-identity-reopened")
        v.require(summary(reopened) == expected, "Native reopen changed note identities", summary(reopened))
    finally:
        await check.close(sid)

    retained_phoneme = request(0, 60, selector(old, 0))
    retained_phoneme.pop("phoneme")
    retained = await check.call("score_replace_notes", path=str(source), output_name=check.output("note-phoneme-retained"),
                                notes=[retained_phoneme])
    retained_data, _ = v.read_vpr(retained["path"])
    v.require(retained_data["tracks"][0]["parts"][0]["notes"][0]["phoneme"] == "a",
              "Unchanged selected note lost its original phoneme")
    retained_sid = (await check.call("project_open", path=retained["path"]))["session_id"]
    await check.close(retained_sid)

    no_source = await check.call("score_replace_notes", path=str(source), output_name=check.output("note-new-only"),
                                 notes=[request(0, 60), request(1, 62)])
    fresh, _ = v.read_vpr(no_source["path"])
    v.require([(n.get(KEY), n["velocity"]) for n in fresh["tracks"][0]["parts"][0]["notes"]] == [(None, 64), (None, 64)],
              "New notes inherited source identity", summary(fresh))

    stale = selector(old, 0)
    stale["expected"]["isProtected"] = 0  # JSON false and JSON zero are distinct snapshots.
    cases = [
        ("duplicate", [request(0, 60, selector(old, 0)), request(1, 62, selector(old, 0))]),
        ("stale", [request(0, 60, stale)]),
        ("out-of-range", [request(0, 60, {"index": 2, "expected": {}})]),
        ("bad-shape", [request(0, 60, {"index": 0})]),
    ]
    for label, selected in cases:
        output = check.output("note-invalid-" + label)
        await check.rejected("score_replace_notes", "source|selector|identity", path=str(source),
                             output_name=output, notes=selected)
        v.require(not (v.ROOT / "output" / output).exists(), "Invalid selection produced output", label)

    side_source, side_original = source_sidecar(check, members, sequence)
    side_notes = [request(0, 60, selector(old, 0)), request(1, 62, selector(old, 1))]
    side_copy = await check.call("score_replace_notes", path=str(side_source), output_name=check.output("note-sidecar-kept"),
                                 notes=side_notes)
    side_sequence, side_members = v.read_vpr(side_copy["path"])
    v.require(SIDE in side_members and summary(side_sequence) == summary(sequence),
              "Unchanged sidecar source identity changed")
    output = check.output("note-sidecar-new-rejected")
    await check.rejected("score_replace_notes", "phoneme.validity|identity", path=str(side_source),
                         output_name=output, notes=[request(0, 60), request(1, 62, selector(old, 1))])
    v.require(not (v.ROOT / "output" / output).exists() and side_source.read_bytes() == side_original,
              "Sidecar identity conflict changed files")
    # Only the guard predicate is called on these in-memory examples; no
    # extension-bearing project is edited or opened.
    from vocaloid_bridge.projects import _guard_note_replacement
    examples = (
        {"tracks": [{"volume": {"events": [{"pos": 0, "value": 0, "x_extra": 1}]}}]},
        {"tracks": [{"parts": [{"controllers": [{"events": [{"pos": 0, "value": 0, "x_extra": 1}]}]}]}]},
        {"tracks": [{"parts": [{"notes": [{"directPitches": [{"pos": 0, "value": 0, "x_extra": 1}]}]}]}]},
    )
    for example in examples:
        try:
            _guard_note_replacement(example)
        except ValueError:
            pass
        else:
            raise AssertionError("Existing extension boundary not detected")

    v.require(source.read_bytes() == original, "Note edit changed source archive")


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "preservation.file_notes_identity_26"])
    raise SystemExit(v.main())
