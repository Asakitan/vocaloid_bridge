"""Exercise the built native library slice on its existing private desktop."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid
import zipfile

import win32gui


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vocaloid_bridge.native_client import NativeClient


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(fixture: Path) -> dict:
    fixture = fixture.resolve(strict=True)
    original = fixture.read_bytes()
    foreground = win32gui.GetForegroundWindow()
    client = NativeClient(ROOT)
    sessions: set[str] = set()
    operations: list[str] = []
    report: dict = {"fixture": str(fixture), "operations": operations, "native": True}
    run_id = uuid.uuid4().hex[:12]
    report_path = ROOT / ".runtime" / f"library-check-{run_id}.json"
    report["report"] = str(report_path)

    def library(operation: str, session_id: str | None = None, **options):
        response = client.request("library_op", {
            "session_id": session_id, "operation": operation, "options": options,
        })
        require(response.get("native") is True, f"{operation}: nonnative response")
        require(response.get("operation") == operation, f"{operation}: wrong operation")
        require(response.get("session_id") == session_id, f"{operation}: wrong session")
        operations.append(operation)
        return response["result"]

    def score(session_id: str, operation: str, **options):
        return client.request("score_edit", {
            "session_id": session_id, "operation": operation, "options": options,
        })["result"]

    try:
        languages = library("languages")
        require({item["language_id"] for item in languages} == {0, 1, 2, 3, 4}, "Native language catalog mismatch")
        require(library("lyrics_can_convert", language_id=1, lyrics="a", is_ai=True)["can_convert"],
                "Native English G2PA cannot convert 'a'")
        styles = library("style_list")["styles"]
        media = library("media_list")["clips"]
        report["style_count"] = len(styles)
        report["initial_media_count"] = len(media)
        require(bool(styles), "Installed native style catalog is empty")

        opened = client.request("open", {"path": str(fixture)})
        session_id = opened["session_id"]
        sessions.add(session_id)
        part = next(part for part in score(session_id, "part.list")["parts"]
                    if score(session_id, "note.list", track_index=part["track_index"],
                             part_index=part["part_index"])["notes"])
        scope = {"track_index": part["track_index"], "part_index": part["part_index"]}
        candidates = library("lyrics_candidates", session_id, **scope, note_index=0, language_id=1, lyrics="a")
        require(bool(candidates["candidates"]), "Native G2PA returned no candidates")
        applied = library("lyrics_apply", session_id, **scope, note_index=0, language_id=1, lyrics="a")
        require(bool(applied["notes"][0]["phonemes"]), "Native lyric application produced no phonemes")
        phonemes = applied["notes"][0]["phonemes"]
        protected = library("phonemes_apply", session_id, **scope, note_index=0,
                            language_id=1, phonemes=phonemes, protect=True)
        require(protected["notes"][0]["protected"], "Native phoneme protection was not set")
        library("phonemes_apply", session_id, **scope, note_index=0,
                language_id=1, phonemes=phonemes, protect=False)
        library("lyrics_reset", session_id, **scope, language_id=1)
        library("phonemes_reset", session_id, **scope, language_id=1)

        style = next((item for item in styles if item["audio_effect_count"] > 0), styles[0])
        detail = library("style_get", style_id=style["style_id"])
        require(detail["style_id"] == style["style_id"], "Native style lookup changed identity")
        styled = library("style_apply", session_id, **scope, style_id=style["style_id"])
        require(styled["scope"] == "complete" and styled["audio_effects_applied"], "Full native style was not applied")
        require(styled["audio_effect_count"] == style["audio_effect_count"], "Native style audio count mismatch")

        captured = library("media_capture", session_id, **scope, name=f"Library probe {run_id}")
        clip = captured["clip"]
        require(clip["writable"] and Path(clip["path"]).is_file(), "Private native clip file was not saved")
        require(Path(clip["path"]).resolve().is_relative_to((ROOT / ".runtime" / "library" / "media").resolve()),
                "Captured clip escaped the private media directory")
        clip_id = clip["clip_id"]
        updated = library("media_update", session_id, clip_id=clip_id,
                          name=f"Library probe verified {run_id}", add_genres=[f"probe-{run_id}"])["clip"]
        require(updated["name"] == f"Library probe verified {run_id}", "Native clip property edit did not persist")
        require(updated["tempo"] == clip["tempo"] and updated["key"] == clip["key"],
            "Native clip edit changed omitted tempo or key")
        require(set(clip["genres"]).issubset(updated["genres"]) and set(clip["types"]).issubset(updated["types"]),
            "Native clip edit removed existing tags")
        require(any(item["clip_id"] == clip_id for item in library("media_list", query=run_id)["clips"]),
                "Native media search cannot find the private clip")
        require(library("media_get", clip_id=clip_id)["part"]["notes"] > 0, "Saved native clip lost its notes")
        imported = library("media_import", session_id, clip_id=clip_id,
                           track_index=scope["track_index"], position_tick=15360)
        require(len(imported["notes"]) == clip["part"]["notes"], "Native media import lost notes")

        saved = client.request("save", {"session_id": session_id, "output_name": f"library-check-{run_id}.vpr"})
        output = Path(saved["path"])
        with zipfile.ZipFile(output) as archive:
            sequence = json.loads(archive.read("Project/sequence.json"))
            require(bool(sequence.get("tracks")), "Saved VPR contains no tracks")
        reopened = client.request("open", {"path": str(output)})
        sessions.add(reopened["session_id"])
        require(len(score(reopened["session_id"], "part.list")["parts"]) >= 2,
                "Native VPR reopen did not retain the imported part")
        deleted = library("media_delete", session_id, clip_id=clip_id)
        require(deleted["deleted"] and not Path(clip["path"]).is_file(), "Native private media deletion did not remove its file")
        require(all(item["clip_id"] != clip_id for item in library("media_list")["clips"]),
            "Deleted private media remains in the native catalog")
        report["output"] = str(output)
        report["clip_id"] = clip_id
        report["clip_path"] = clip["path"]
        report["private_clip_deleted"] = True
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        for session_id in sessions:
            try:
                client.request("close", {"session_id": session_id, "discard": True})
            except Exception as error:
                report.setdefault("cleanup_errors", []).append(str(error))
        client.close()
        report["fixture_unchanged"] = fixture.read_bytes() == original
        report["foreground_unchanged"] = win32gui.GetForegroundWindow() == foreground
        if not report["fixture_unchanged"] or not report["foreground_unchanged"] or report.get("cleanup_errors"):
            report["status"] = "failed"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    require(report["fixture_unchanged"], "The original fixture was modified")
    require(report["foreground_unchanged"], "The foreground window changed during native library verification")
    require(not report.get("cleanup_errors"), "Native session cleanup failed")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "artifacts" / "fixtures" / "editor-note.vpr")
    args = parser.parse_args()
    print(json.dumps(run(args.fixture), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())