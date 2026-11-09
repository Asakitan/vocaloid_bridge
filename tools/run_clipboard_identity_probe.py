"""Run the synthetic clipboard probe on a private Windows desktop."""
import json
import argparse
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vocaloid_bridge.native_client import IsolatedProcess

parser = argparse.ArgumentParser(description=__doc__)
selection = parser.add_mutually_exclusive_group(required=True)
selection.add_argument("--direct", action="store_true")
selection.add_argument("--track-one", action="store_true")
args = parser.parse_args()
mode = "direct" if args.direct else "track-one"
script = ROOT / "tools" / {"direct": "probe_clipboard_direct.ps1", "track-one": "probe_clipboard_track_one.ps1"}[mode]
fixture = ROOT / "output" / "clipboard_probe_synthetic_20261110.vpr"
if not fixture.is_file():
    raise SystemExit("Synthetic fixture missing; create it through the native MCP first.")
process = IsolatedProcess([r"C:\Program Files\PowerShell\7\pwsh.exe", "-NoProfile", "-File", str(script)], ROOT)
try:
    line = process.read_line(120)
    result = json.loads(line)
    result["desktop"] = process.desktop_name
    result["fixture"] = str(fixture)
    output = ROOT / "artifacts" / f"clipboard-{mode}-probe-{uuid.uuid4().hex[:12]}.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
finally:
    process.close()
