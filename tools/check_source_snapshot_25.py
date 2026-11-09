"""Exercise file-edit source consistency with a forced independent writer."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vocaloid_bridge import projects
import pywintypes
import win32con
import win32file

ARTIFACTS = (ROOT / "artifacts").resolve()


def checked_fixture(path: str, name: str) -> Path:
    result = Path(path).resolve(strict=True)
    if (result.name != name or result.parent.parent != ARTIFACTS
            or not result.parent.name.startswith("source-snapshot-25-")):
        raise ValueError("child paths must be this probe's synthetic artifacts")
    return result


def replace_child(source: str, candidate: str) -> None:
    target = checked_fixture(source, "source.vpr")
    replacement = checked_fixture(candidate, "replacement.vpr")
    if target.parent != replacement.parent:
        raise ValueError("child paths must share the synthetic fixture directory")
    try:
        os.replace(replacement, target)
        outcome = {"replaced": True}
    except OSError as error:
        outcome = {"replaced": False, "winerror": error.winerror, "message": str(error)}
    print(json.dumps(outcome))


def write_child(source: str) -> None:
    target = checked_fixture(source, "source.vpr")
    try:
        with target.open("r+b") as stream:
            first = stream.read(1)
            stream.seek(0)
            stream.write(first)
        outcome = {"opened_for_write": True}
    except OSError as error:
        outcome = {"opened_for_write": False, "winerror": error.winerror}
    print(json.dumps(outcome))


def writer_child(source: str) -> None:
    target = checked_fixture(source, "writer-source.vpr")
    handle = win32file.CreateFile(str(target), win32con.GENERIC_WRITE,
                                 win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
                                 None, win32con.OPEN_EXISTING, 0, None)
    try:
        print("ready", flush=True)
        sys.stdin.readline()
    finally:
        handle.Close()


def make_vpr(path: Path, marker: str) -> None:
    sequence = {"title": marker, "masterTrack": {"tempo": {"events": [{"pos": 0, "value": 12000}]}}}
    with zipfile.ZipFile(path, "x") as archive:
        archive.writestr("Project/sequence.json", json.dumps(sequence))
        archive.writestr("opaque-resource.bin", marker.encode("ascii"))
        archive.comment = marker.encode("ascii")


def contents(path: Path) -> tuple[str, str, str]:
    with zipfile.ZipFile(path) as archive:
        return (json.loads(archive.read("Project/sequence.json"))["title"],
                archive.read("opaque-resource.bin").decode("ascii"),
                archive.comment.decode("ascii"))


def main() -> int:
    ARTIFACTS.mkdir(exist_ok=True)
    fixture = Path(tempfile.mkdtemp(prefix="source-snapshot-25-", dir=ARTIFACTS))
    source = fixture / "source.vpr"
    replacement = fixture / "replacement.vpr"
    writer_source = fixture / "writer-source.vpr"
    for path, marker in ((source, "A"), (replacement, "B"), (writer_source, "A")):
        make_vpr(path, marker)
    store = projects.ProjectStore(fixture)
    original_tempo = projects._tempo_events
    observed = {}

    def inject(data, events):
        writer = subprocess.run([sys.executable, __file__, "--write", str(source)],
                                capture_output=True, text=True, timeout=15, check=True)
        observed["in_place"] = json.loads(writer.stdout)
        child = subprocess.run([sys.executable, __file__, "--replace", str(source), str(replacement)],
                               capture_output=True, text=True, timeout=15, check=True)
        observed.update(json.loads(child.stdout))
        original_tempo(data, events)

    projects._tempo_events = inject
    try:
        edited = store.set_tempo(str(source), "race-output.vpr", [{"start": 0, "bpm": 135}])
    finally:
        projects._tempo_events = original_tempo
    output_contents = contents(Path(edited["path"]))
    source_contents = contents(source)
    after_release = None
    if replacement.exists():
        child = subprocess.run([sys.executable, __file__, "--replace", str(source), str(replacement)],
                               capture_output=True, text=True, timeout=15, check=True)
        after_release = json.loads(child.stdout)

    writer = subprocess.Popen([sys.executable, __file__, "--writer", str(writer_source)],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    writer_blocked = False
    writer_error = None
    try:
        if writer.stdout.readline().strip() != "ready":
            raise RuntimeError("writer child did not become ready")
        try:
            store.set_tempo(str(writer_source), "writer-output.vpr", [{"start": 0, "bpm": 135}])
        except pywintypes.error as error:
            writer_blocked = error.args[0] == 32
            writer_error = str(error)
    finally:
        stdout, stderr = writer.communicate(input="done\n", timeout=15)
        if writer.returncode:
            raise RuntimeError(f"writer child failed: {stdout} {stderr}")

    writer_output_exists = (fixture / "output" / "writer-output.vpr").exists()
    validation_released = False
    try:
        store.set_tempo(str(writer_source), "invalid-output.vpr", [])
    except ValueError:
        handle = win32file.CreateFile(str(writer_source), win32con.GENERIC_WRITE,
                                     win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
                                     None, win32con.OPEN_EXISTING, 0, None)
        handle.Close()
        validation_released = not (fixture / "output" / "invalid-output.vpr").exists()

    good = (observed.get("replaced") is False and observed.get("in_place", {}).get("opened_for_write") is False
            and output_contents == ("A", "A", "A")
            and source_contents == ("A", "A", "A") and after_release == {"replaced": True}
            and writer_blocked and not writer_output_exists and validation_released)
    receipt = {"fixture": str(fixture), "race_result": observed, "output_contents": output_contents,
               "source_before_release_check": source_contents, "replace_after_release": after_release,
               "preexisting_writer_blocked": writer_blocked, "preexisting_writer_error": writer_error,
               "preexisting_writer_output_exists": writer_output_exists,
               "validation_failure_released_handle": validation_released, "passed": good}
    (fixture / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if good else 1


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--replace":
        replace_child(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 3 and sys.argv[1] == "--writer":
        writer_child(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "--write":
        write_child(sys.argv[2])
    else:
        raise SystemExit(main())
