"""Native external-bus versus offline mix-rate probe; does not build the host."""
import json
import sys
import time
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vocaloid_bridge.native_client import NativeClient

FIXTURE = ROOT / "output/background-demo-07ca3af496-score.vpr"

def guard_probe():
    run = uuid.uuid4().hex[:12]
    results = []
    client = NativeClient(ROOT)
    try:
        for rate in (48000, 96000):
            sid = client.request("open", {"path": str(FIXTURE.resolve(strict=True))})["session_id"]
            try:
                updated = client.request("score_edit", {"session_id": sid, "operation": "sequence.update", "options": {"sample_rate": rate}})["result"]
                start = time.monotonic()
                try:
                    client.request("render_part", {"session_id": sid, "track_index": 0, "part_index": 0, "output_name": f"routing-guard-{run}-{rate}.wav"})
                    result = {"status": "unexpected_success"}
                except Exception as error:
                    result = {"status": "rejected", "error": str(error), "elapsed_seconds": round(time.monotonic() - start, 3)}
                results.append({"rate": rate, "readback": updated["sample_rate"], "render": result})
            finally:
                client.request("close", {"session_id": sid, "discard": True})
    finally:
        client.close()
        path = ROOT / "artifacts" / f"audio-routing-guard-{run}.json"
        path.write_text(json.dumps({"fixture": str(FIXTURE), "results": results}, indent=2), encoding="utf-8")
        print("receipt:", path, json.dumps(results), flush=True)
    return int(any(r["readback"] != r["rate"] or r["render"]["status"] != "rejected" or r["render"]["elapsed_seconds"] > 5 or "44100" not in r["render"]["error"] for r in results))

def main():
    run = uuid.uuid4().hex[:12]
    results = []
    client = NativeClient(ROOT)
    try:
        for bus in (0, 1):
                sid = None
                case = {"sequence_rate": 44100, "bus": bus, "mixes": {}}
                results.append(case)
                try:
                    sid = client.request("open", {"path": str(FIXTURE.resolve(strict=True))})["session_id"]
                    def edit(operation, **options):
                        return client.request("score_edit", {"session_id": sid, "operation": operation, "options": options})["result"]
                    case["sequence"] = edit("sequence.update", sample_rate=44100)
                    case["track"] = edit("track.update", track_index=0, bus_no=bus)
                    for operation, rate in [("render_part", 44100), ("mixdown", 44100), ("mixdown", 48000), ("mixdown", 96000)]:
                        try:
                            filename = f"routing-{run}-{rate}-{bus}-{operation}.wav"
                            if operation == "render_part":
                                result = client.request(operation, {"session_id": sid, "track_index": 0, "part_index": 0, "output_name": filename})
                            else:
                                result = client.request("audio_op", {"session_id": sid, "operation": operation, "options": {"sample_rate": rate, "output_name": filename}})
                            pcm, actual_rate = sf.read(result["path"], dtype="float32", always_2d=True)
                            rms = float(np.sqrt(np.mean(pcm.astype(np.float64) ** 2)))
                            detail = {"status": "passed" if rms > 1e-6 and actual_rate == rate else "failed", "path": result["path"], "sample_rate": actual_rate, "frames": len(pcm), "rms": rms}
                        except Exception as exc:
                            detail = {"status": "failed", "error": str(exc)}
                        if operation == "render_part":
                            case[operation] = detail
                            if detail["status"] != "passed":
                                break
                        else:
                            case["mixes"][str(rate)] = detail
                except Exception as exc:
                    case["setup_error"] = str(exc)
                finally:
                    if sid:
                        client.request("close", {"session_id": sid, "discard": True})
                print(json.dumps(case, ensure_ascii=False), flush=True)
    finally:
        client.close()
        comparisons = {}
        if len(results) == 2:
            for rate in ("44100", "48000", "96000"):
                first = results[0]["mixes"].get(rate, {})
                second = results[1]["mixes"].get(rate, {})
                if first.get("status") == second.get("status") == "passed":
                    a, ar = sf.read(first["path"], dtype="float32", always_2d=True)
                    b, br = sf.read(second["path"], dtype="float32", always_2d=True)
                    comparisons[rate] = {"sample_rates": [ar, br], "shapes_equal": a.shape == b.shape,
                                         "max_absolute_difference": float(np.max(np.abs(a - b))) if a.shape == b.shape else None}
        path = ROOT / "artifacts" / f"audio-routing-{run}.json"
        path.write_text(json.dumps({"fixture": str(FIXTURE), "results": results, "comparisons": comparisons}, indent=2), encoding="utf-8")
        print("receipt:", path, flush=True)
    return int(any(c.get("setup_error") or c.get("render_part", {}).get("status") != "passed" or len(c["mixes"]) != 3 or any(m["status"] != "passed" for m in c["mixes"].values()) for c in results))

if __name__ == "__main__":
    sys.exit(guard_probe() if sys.argv[1:] == ["--guard"] else main())
