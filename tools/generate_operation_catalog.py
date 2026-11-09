"""Generate/check the shipped operation index against native dispatch and docs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = {
    "score": ("ScoreOperations.cs", "project_edit", "score-operations.md", "score_edit"),
    "audio": ("AudioOperations.cs", "project_audio", "audio-operations.md", "audio_op"),
    "library": ("LibraryOperations.cs", "project_library", "library-operations.md", "library_op"),
    "clipboard": ("ProjectClipboard.cs", "project_clipboard", "native-protocol.md", "clipboard"),
    "midi": ("MidiRecordingOperations.cs", "project_midi", "midi-recording.md", "midi_recording"),
}
DESTINATION = ROOT / "vocaloid_bridge" / "operations.json"


def generate() -> dict:
    result = {"schema_version": 1, "verification": "Discovery only; use vocaloid_features for acceptance evidence.", "domains": {}}
    for domain, (source_name, tool, doc_name, rpc) in DOMAINS.items():
        source = (ROOT / "native" / source_name).read_text(encoding="utf-8-sig")
        if domain == "midi":
            names = set(re.findall(r'if \(operation (?:==|!=) "([a-z][a-z0-9_]*)"\)', source))
        else:
            start = source.index("operation switch")
            switch = source[start:source.index("};", start)]
            names = set(re.findall(r'"([a-z][a-z0-9_.]*)"\s*(?:or|=>)', switch))
            if domain == "clipboard":
                names.update(re.findall(r'if \(operation == "([a-z]+)"\)', source[:start]))
        document = (ROOT / "docs" / doc_name).read_text(encoding="utf-8-sig")
        rows = [line for line in document.splitlines() if line.startswith("|")]
        result["domains"][domain] = {
            "tool": tool, "rpc": rpc, "documentation": "docs/" + doc_name,
            "operations": [
                {"operation": name, "contract_rows": [row for row in rows if "`" + name + "`" in row]}
                for name in sorted(names)
            ],
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    expected = generate()
    if arguments.check:
        actual = json.loads(DESTINATION.read_text(encoding="utf-8"))
        if actual != expected:
            raise SystemExit("Operation index differs from native dispatch/docs; regenerate it.")
    else:
        DESTINATION.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Operation index: " + ", ".join(f"{name}={len(data['operations'])}" for name, data in expected["domains"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
