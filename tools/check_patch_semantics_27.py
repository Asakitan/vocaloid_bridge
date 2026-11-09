"""Focused in-memory JSON Patch validity provenance semantics."""
from copy import deepcopy
import json
import jsonpatch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vocaloid_bridge.projects import _EDITOR_AI_NOTE, _patch_validity, _patch_touches_note_tree


def fixture():
    notes = []
    for position, name in ((0, "A"), (480, "B"), (0, "C")):
        note = deepcopy(_EDITOR_AI_NOTE)
        note.update(pos=position, duration=240, number=60, lyric="あ", phoneme="a", langID=0, marker=name)
        notes.append(note)
    data = {"tracks": [{"parts": [{"notes": notes[:2]}]}, {"parts": [{"notes": notes[2:]}]}], "metadata": {}}
    def entry(t, n, label):
        item = data["tracks"][t]["parts"][0]["notes"][n]
        return {"TrackIndex": t, "PartIndex": 0, "NoteIndex": n, "marker": label,
                "Note": {"IsValid": False, "Position": item["pos"], "Duration": item["duration"],
                         "Number": item["number"], "Lyric": item["lyric"],
                         "Phonemes": item["phoneme"], "LanguageId": item["langID"]}}
    metadata = {"Format": "vocaloid-bridge-phoneme-validity", "Version": 1,
                "x_root": {"keep": [1, True]}, "Notes": [entry(0, 0, "A"), entry(0, 1, "B")]}
    return data, json.dumps(metadata, ensure_ascii=False).encode("utf-8")


def run(data, payload, ops):
    result, side = _patch_validity(data, payload, ops)
    return result, json.loads(side)


def flags(side):
    return sorted((e["TrackIndex"], e["PartIndex"], e["NoteIndex"], e["Note"]["Position"], e["marker"])
                  for e in side["Notes"])


def main():
    data, payload = fixture()
    original = deepcopy(data)
    base = "/tracks/0/parts/0/notes"
    result, side = run(data, payload, [
        {"op": "copy", "from": base + "/0", "path": base + "/-"},
        {"op": "replace", "path": base + "/2/pos", "value": 960},
        {"op": "copy", "from": base + "/2", "path": base + "/-"},
        {"op": "replace", "path": base + "/3/pos", "value": 1440},
    ])
    assert flags(side) == [(0, 0, 0, 0, "A"), (0, 0, 1, 480, "B"),
                           (0, 0, 2, 960, "A"), (0, 0, 3, 1440, "A")]
    assert result["tracks"][0]["parts"][0]["notes"][3]["marker"] == "A"

    result, side = run(data, payload, [{"op": "copy", "from": "/tracks/0", "path": "/tracks/-"}])
    assert flags(side) == [(0, 0, 0, 0, "A"), (0, 0, 1, 480, "B"),
                           (2, 0, 0, 0, "A"), (2, 0, 1, 480, "B")]

    result, side = run(data, payload, [
        {"op": "move", "from": base + "/0", "path": "/tracks/1/parts/0/notes/-"},
        {"op": "replace", "path": "/tracks/1/parts/0/notes/1/pos", "value": 960},
    ])
    assert flags(side) == [(0, 0, 0, 480, "B"), (1, 0, 1, 960, "A")]

    result, side = run(data, payload, [
        {"op": "copy", "from": base + "/0", "path": "/temporary"},
        {"op": "copy", "from": "/temporary", "path": base + "/-"},
        {"op": "replace", "path": base + "/2/pos", "value": 960},
        {"op": "remove", "path": "/temporary"},
    ])
    assert flags(side) == [(0, 0, 0, 0, "A"), (0, 0, 1, 480, "B"), (0, 0, 2, 960, "A")]

    result, side = run(data, payload, [{"op": "copy", "from": "", "path": ""}])
    assert result == data and flags(side) == [(0, 0, 0, 0, "A"), (0, 0, 1, 480, "B")]

    result, side = run(data, payload, [
        {"op": "add", "path": "/metadata/a~1b~0", "value": {"0": "ok"}},
        {"op": "test", "path": "/metadata/a~1b~0/0", "value": "ok"},
        {"op": "add", "path": base + "/0", "value": deepcopy(data["tracks"][1]["parts"][0]["notes"][0])},
    ])
    assert result["metadata"]["a/b~"]["0"] == "ok"
    assert flags(side) == [(0, 0, 1, 0, "A"), (0, 0, 2, 480, "B")]

    for path, expected in (("", True), ("/tracks/0/parts/0/notes/0", True),
                           ("/tracks/0/name", False), ("/tracks~10", False),
                           ("/metadata/a~1b~0", False)):
        assert _patch_touches_note_tree(path) is expected
    for ops in ([{"op": "replace", "path": base + "/0/lyric", "value": "い"}],
                [{"op": "replace", "path": "/metadata", "value": {}},
                 {"op": "test", "path": "/metadata", "value": {"bad": 1}}]):
        try:
            _patch_validity(data, payload, ops)
        except (ValueError, jsonpatch.JsonPatchTestFailed):
            pass
        else:
            raise AssertionError("Expected patch rejection")
    bad = json.loads(payload)
    bad["Notes"][0]["Note"]["Position"] = False
    try:
        _patch_validity(data, json.dumps(bad).encode(), [])
    except ValueError:
        pass
    else:
        raise AssertionError("JSON boolean was accepted as an integer identity field")
    for extension in ("direct_pitch", "controller", "track_volume"):
        guarded = deepcopy(data)
        track = guarded["tracks"][0]
        part = track["parts"][0]
        if extension == "direct_pitch":
            part["notes"][0]["directPitches"] = [{"pos": 0, "value": 0, "x_extra": 1}]
        elif extension == "controller":
            part["controllers"] = [{"events": [{"pos": 0, "value": 0, "x_extra": 1}]}]
        else:
            track["volume"] = {"events": [{"pos": 0, "value": 0, "x_extra": 1}]}
        before = deepcopy(guarded)
        try:
            _patch_validity(guarded, None, [{"op": "replace", "path": base + "/0/velocity", "value": 72}])
        except ValueError as error:
            assert "guarded" in str(error)
        else:
            raise AssertionError("Extended note patch passed the in-memory guard")
        assert guarded == before
    assert data == original
    print("PASS: tracked moves, copies, chains, root copy, insertion, escaped keys, guards and rejection")


if __name__ == "__main__":
    main()
