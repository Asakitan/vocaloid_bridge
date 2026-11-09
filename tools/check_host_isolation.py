"""Regression for simultaneous native clients retaining their own audio caches."""
from __future__ import annotations

import json
import argparse
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vocaloid_bridge.native_client import NativeClient


def main() -> None:
    run_id = uuid.uuid4().hex[:12]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-fixture", type=Path, required=True)
    source = parser.parse_args().audio_fixture.resolve(strict=True)
    report = {"run_id": run_id, "source": str(source), "steps": []}
    a, b = NativeClient(ROOT), NativeClient(ROOT)
    sid = None
    try:
        sid = a.request("create", {"title": "Concurrent cache probe", "bpm": 120, "sample_rate": 44100})["session_id"]
        imported = a.request("audio_op", {"session_id": sid, "operation": "import_audio", "options": {"path": str(source)}})
        report["imported"] = imported
        saved = a.request("save", {"session_id": sid, "output_name": "cache-" + run_id + ".vpr"})
        report["saved"] = saved
        report["peer"] = b.request("ping")
        b.close()
        report["steps"].append("peer_closed")
        result = a.request("audio_op", {"session_id": sid, "operation": "export_audio", "options": {
            "track_index": imported["track_index"], "part_index": imported["part_index"],
            "output_name": "cache-" + run_id + ".wav", "original": False,
        }})
        report["exported"] = result
        assert Path(result["path"]).stat().st_size > 44
        report["passed"] = True
    except Exception as error:
        report["error"] = str(error)
        report["passed"] = False
        raise
    finally:
        if sid is not None:
            a.request("close", {"session_id": sid, "discard": True})
        a.close()
        b.close()
        destination = ROOT / "artifacts" / ("host-isolation-" + run_id + ".json")
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(destination)


if __name__ == "__main__":
    main()
