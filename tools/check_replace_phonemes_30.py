"""One focused MCP case for replaced AI-note phonemes and source identity."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import zipfile

import verify_features as v


@v.feature("score.replace_phonemes_30", "score", "score_compose", "score_replace_notes", "project_open",
           "project_edit", "project_save")
async def replace_phonemes(check):
    seed = await check.call("score_compose", output_name=check.output("replace-phonemes-source"),
                            title="Replacement source", bpm=123, notes=[
        {"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0,
         "velocity": 70, "raw": {"exp": {"accent": 37}}},
        {"start": 1, "duration": .5, "pitch": 62, "lyric": "Ooh", "phoneme": "u:", "lang_id": 1,
         "velocity": 90, "raw": {"exp": {"accent": 41}}},
        {"start": 2, "duration": .5, "pitch": 64, "lyric": "ni", "phoneme": "n i", "lang_id": 4,
         "velocity": 80, "raw": {"exp": {"accent": 45}}},
    ])
    await check.close(seed["native_session"]["session_id"])
    source = Path(seed["path"])
    original = source.read_bytes()
    sequence, members = v.read_vpr(source)
    source_notes = sequence["tracks"][0]["parts"][0]["notes"]

    def note(start, pitch, lyric, language, index=None):
        result = {"start": start, "duration": .5, "pitch": pitch, "lyric": lyric, "lang_id": language}
        if index is not None:
            result["source"] = {"index": index, "expected": deepcopy(source_notes[index])}
        return result

    result = await check.call("score_replace_notes", path=str(source), output_name=check.output("replace-phonemes"),
                              notes=[note(2, 67, "あ", 0, 0), note(0, 64, "cat", 1, 1),
                                     note(3, 69, "hao", 4, 2), note(1, 65, "い", 0)])
    v.require(set(result) == {"path", "summary"}, "File-only result contract changed", result)
    changed, _ = v.read_vpr(result["path"])
    actual = changed["tracks"][0]["parts"][0]["notes"]
    expected = [(0, 64, "cat", "kh { t", 1, 90, 41), (480, 65, "い", "i", 0, 64, 50),
                (960, 67, "あ", "a", 0, 70, 37), (1440, 69, "hao", "x AU", 4, 80, 45)]
    v.require([(n["pos"], n["number"], n["lyric"], n["phoneme"], n["langID"], n["velocity"], n["exp"]["accent"])
               for n in actual] == expected, "Replaced notes lost identity or phonemes", actual)
    restored = deepcopy(changed)
    restored["tracks"][0]["parts"][0]["notes"] = deepcopy(source_notes)
    v.require(restored == sequence, "Non-note project data changed")
    for output_index, source_index in ((0, 1), (2, 0), (3, 2)):
        retained = deepcopy(source_notes[source_index])
        retained.update({key: actual[output_index][key] for key in ("pos", "number", "lyric", "phoneme")})
        v.require(actual[output_index] == retained, "Selected source note lost its other fields", output_index)
    sid = (await check.call("project_open", path=result["path"]))["session_id"]
    try:
        saved, path = await check.save(sid, "replace-phonemes-saved")
    finally:
        await check.close(sid)
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    try:
        loaded = (await check.edit(reopened, "note.list", track_index=0, part_index=0))["notes"]
        v.require([(n["start_tick"], n["number"], n["lyric"], n["phonemes"], n["lang_id"],
                    n["velocity"], n["expression"]["Accent"]) for n in loaded] == expected,
                  "Native save/reopen changed replaced notes", loaded)
    finally:
        await check.close(reopened)

    rejected = check.output("replace-phonemes-rejected")
    await check.rejected("score_replace_notes", "G2PA", path=str(source), output_name=rejected,
                         notes=[note(0, 60, "ni3", 4)])
    v.require(not (v.ROOT / "output" / rejected).exists(), "Rejected edit published a target")
    old = source_notes[0]
    sidecar = {"Format": "vocaloid-bridge-phoneme-validity", "Version": 1, "Notes": [{
        "TrackIndex": 0, "PartIndex": 0, "NoteIndex": 0,
        "Note": {"IsValid": False, "Position": old["pos"], "Duration": old["duration"],
                 "Number": old["number"], "Lyric": old["lyric"], "Phonemes": old["phoneme"], "LanguageId": old["langID"]}}]}
    side_source = v.ROOT / "output" / check.output("replace-phonemes-sidecar-source")
    with zipfile.ZipFile(side_source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
        archive.writestr("vocaloid_bridge/phoneme-validity-v1.json", json.dumps(sidecar).encode("utf-8"))
    rejected = check.output("replace-phonemes-sidecar-rejected")
    await check.rejected("score_replace_notes", "phoneme.validity", path=str(side_source), output_name=rejected,
                         notes=[note(0, 60, "い", 0, 0)])
    v.require(not (v.ROOT / "output" / rejected).exists() and source.read_bytes() == original,
              "Rejected sidecar edit or conversion changed the source/target")


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "score.replace_phonemes_30"])
    raise SystemExit(v.main())
