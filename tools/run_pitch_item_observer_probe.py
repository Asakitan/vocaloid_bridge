"""Read direct-pitch item identities and observer events in a private desktop."""
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vocaloid_bridge.native_client import IsolatedProcess

fixture = Path(sys.argv[1]).resolve(strict=True)
if fixture.parent != (ROOT / "output").resolve() or not fixture.name.startswith("feature-") or not fixture.name.endswith("-pitch-transitions-replace.vpr"):
    raise ValueError("Use the synthetic replace fixture from preservation.note_pitch_transitions")
process = IsolatedProcess([r"C:\Program Files\PowerShell\7\pwsh.exe", "-NoProfile", "-File",
                           str(ROOT / "tools/probe_pitch_item_observer.ps1"), "-Fixture", str(fixture)], ROOT)
try:
    result = json.loads(process.read_line(120))
    output = ROOT / "artifacts" / f"pitch-item-observer-{uuid.uuid4().hex[:12]}.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
finally:
    process.close()
