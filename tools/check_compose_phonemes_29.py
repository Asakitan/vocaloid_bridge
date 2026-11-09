"""Exercise omitted AI phonemes through one private MCP composition case."""
from pathlib import Path
import sys

import verify_features as v


@v.feature("score.compose_phonemes_29", "score", "score_compose", "project_edit", "project_save", "project_open")
async def compose_phonemes(check):
    requested = [
        {"start": 0, "duration": 1, "pitch": 60, "lyric": "い", "lang_id": 0},
        {"start": 1, "duration": 1, "pitch": 62, "lyric": "cat", "lang_id": 1},
        {"start": 2, "duration": 1, "pitch": 64, "lyric": "ni", "lang_id": 4},
        {"start": 3, "duration": 1, "pitch": 65, "lyric": "あ", "phoneme": "a", "lang_id": 0},
    ]
    expected = [("い", "i", 0), ("cat", "kh { t", 1), ("ni", "n i", 4), ("あ", "a", 0)]
    name = check.output("compose-native-phonemes")
    result = await check.call("score_compose", output_name=name, title="AI phonemes", bpm=120, notes=requested)
    sid = result["native_session"]["session_id"]
    try:
        loaded = (await check.edit(sid, "note.list", track_index=0, part_index=0))["notes"]
        v.require([(n["lyric"], n["phonemes"], n["lang_id"]) for n in loaded] == expected,
                  "Native conversion differs from expected notes", loaded)
        sequence, path = await check.save(sid, "compose-native-phonemes-saved")
        saved = sequence["tracks"][0]["parts"][0]["notes"]
        v.require([(n["lyric"], n["phoneme"], n["langID"]) for n in saved] == expected,
                  "Saved notes differ from native conversion", saved)
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        try:
            again = (await check.edit(reopened, "note.list", track_index=0, part_index=0))["notes"]
            v.require([(n["lyric"], n["phonemes"], n["lang_id"]) for n in again] == expected,
                      "Reopened notes differ from native conversion", again)
        finally:
            await check.close(reopened)
        original = Path(result["path"]).read_bytes()
        await check.rejected("score_compose", "already exists", output_name=name,
                             title="Collision", bpm=120, notes=requested)
        v.require(Path(result["path"]).read_bytes() == original, "Existing output was modified")
        for lyric, language in (("hello", 1), ("ni3", 4), ("こんにちは", 0)):
            rejected_name = check.output("compose-rejected")
            await check.rejected("score_compose", "G2PA", output_name=rejected_name, title="Rejected",
                                 bpm=120, notes=[{"start": 0, "duration": 1, "pitch": 60,
                                                 "lyric": lyric, "lang_id": language}])
            v.require(not (v.ROOT / "output" / rejected_name).exists(), "Rejected score was published")
    finally:
        await check.close(sid)


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "score.compose_phonemes_29"])
    raise SystemExit(v.main())
