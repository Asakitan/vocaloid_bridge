"""Read direct-pitch item identities and observer events in a private desktop."""
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vocaloid_bridge.native_client import IsolatedProcess

fixture = Path(sys.argv[1]).resolve(strict=True)
if fixture.parent != (ROOT / "output").resolve() or not fixture.name.startswith("feature-") or not fixture.name.endswith("-pitch-ext-input.vpr"):
    raise ValueError("Use the synthetic extended fixture from preservation.note_pitch_extension_roundtrip")
original = fixture.read_bytes()
process = IsolatedProcess([r"C:\Program Files\PowerShell\7\pwsh.exe", "-NoProfile", "-File",
                           str(ROOT / "tools/probe_pitch_copy_extended_native.ps1"), "-Fixture", str(fixture)], ROOT)
try:
    result = json.loads(process.read_line(120))
    if fixture.read_bytes() != original:
        raise AssertionError("Source fixture changed")
    for operation, case in result["cases"].items():
        before, pending, after, undo, redo = (case[k] for k in ("before", "pending", "after", "undo", "redo"))
        def points(note):
            items = note["items"]
            keys = [(p["tick"], p["value"]) for p in items]
            if len({x[0] for x in keys}) != len(keys):
                raise AssertionError("Duplicate native pitch position")
            return sorted(keys)
        source = points(before[0]["notes"][0])
        if len(source) != 2:
            raise AssertionError("Expected two fixture points")
        for snapshot in (pending, after, redo):
            notes = [note for part in snapshot for note in part["notes"]]
            if len(notes) != 2 or any(points(note) != source for note in notes):
                raise AssertionError(f"{operation}: source or copy differs")
        if len(undo) != 1 or len(undo[0]["notes"]) != 1 or points(undo[0]["notes"][0]) != source:
            raise AssertionError(f"{operation}: undo differs")
    result["source_archive_unchanged"] = True
    output = ROOT / "artifacts" / f"pitch-copy-extended-native-{uuid.uuid4().hex[:12]}.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
finally:
    process.close()
