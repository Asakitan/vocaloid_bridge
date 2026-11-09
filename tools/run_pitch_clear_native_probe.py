"""Run the native clear probe against a private synthetic VPR fixture."""
import json
from pathlib import Path
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vocaloid_bridge.native_client import IsolatedProcess

fixture = Path(sys.argv[1]).resolve(strict=True)
if fixture.parent != (ROOT / "output").resolve() or not fixture.name.startswith("feature-") or not fixture.name.endswith("-pitch-transitions-replace.vpr"):
    raise ValueError("Use the synthetic replace fixture from preservation.note_pitch_transitions")
process = IsolatedProcess([r"C:\Program Files\PowerShell\7\pwsh.exe", "-NoProfile", "-File",
                           str(ROOT / "tools/probe_pitch_clear_native.ps1"), "-Fixture", str(fixture)], ROOT)
try:
    result = json.loads(process.read_line(120))
    for case in result["cases"]:
        path = Path(case["save"]["path"])
        with zipfile.ZipFile(path) as archive:
            sequence = json.loads(archive.read("Project/sequence.json"))
        case["serialized_redo"] = sequence["tracks"][0]["parts"][0]["notes"][0].get("directPitches")
    output = ROOT / "artifacts" / f"pitch-clear-native-{uuid.uuid4().hex[:12]}.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
finally:
    process.close()
