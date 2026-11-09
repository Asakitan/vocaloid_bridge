"""Remove only bridge VSM cache namespaces whose recorded processes have ended."""
import argparse
from datetime import timezone
import json
import os
from pathlib import Path
import re
import shutil
import stat
import time
import uuid

import win32api
import win32process

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"VocaloidBridge-[0-9a-f]{32}\Z")


def ended(pid, observed_before):
    try:
        handle = win32api.OpenProcess(0x1000, False, pid)
    except Exception as error:
        return getattr(error, "winerror", None) == 87
    try:
        if win32process.GetExitCodeProcess(handle) != 259:
            return True
        created = win32process.GetProcessTimes(handle)["CreationTime"]
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return created.timestamp() > observed_before
    finally:
        handle.Close()


def run(apply, keep):
    records = {}
    for receipt in (ROOT / "artifacts").glob("feature-acceptance-*/summary.json"):
        data = json.loads(receipt.read_text(encoding="utf-8"))
        for result in data.get("results", []):
            for call in result.get("calls", []):
                value = call.get("result")
                if call.get("tool") == "vocaloid_status" and isinstance(value, dict):
                    name, pid = value.get("cache_namespace"), value.get("pid")
                    if isinstance(name, str) and PATTERN.fullmatch(name) and isinstance(pid, int):
                        records.setdefault(name, []).append((pid, receipt.stat().st_mtime, str(receipt)))
    report = {"applied": apply, "removed": [], "retained": [], "bytes_removed": 0}
    base = Path(os.environ["LOCALAPPDATA"]) / "VOCALOID6"
    for kind in ("VSM", "VSMCaches"):
        parent = (base / kind).resolve()
        if not parent.is_dir():
            continue
        for path in parent.iterdir():
            if not path.is_dir() or not PATTERN.fullmatch(path.name):
                continue
            evidence = records.get(path.name, [])
            if path.name in keep or not evidence or not all(ended(pid, stamp) for pid, stamp, _ in evidence):
                report["retained"].append({"path": str(path), "reason": "active, unknown or explicitly preserved"})
                continue
            target = path.resolve(strict=True)
            if target.parent != parent or path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise RuntimeError("Cache cleanup target escaped the exact owned namespace parent")
            size = 0
            linked = False
            for directory, dirs, files in os.walk(target, followlinks=False):
                for name in (*dirs, *files):
                    child = Path(directory) / name
                    info = child.lstat()
                    if info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                        linked = True
                    elif child.is_file():
                        size += info.st_size
            if linked:
                report["retained"].append({"path": str(path), "reason": "reparse point"})
                continue
            if apply:
                # Recheck process identity immediately before recursive deletion.
                if not all(ended(pid, stamp) for pid, stamp, _ in evidence):
                    report["retained"].append({"path": str(path), "reason": "process state changed"})
                    continue
                shutil.rmtree(target)
                if target.exists():
                    raise RuntimeError("Owned namespace remained after cleanup")
            report["removed"].append({"path": str(path), "bytes": size, "receipts": sorted({row[2] for row in evidence})})
            report["bytes_removed"] += size
    destination = ROOT / "artifacts" / ("cleanup-31-" + uuid.uuid4().hex[:12])
    destination.mkdir()
    report["finished_unix"] = time.time()
    (destination / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"receipt": str(destination / "manifest.json"), "directories": len(report["removed"]),
                      "bytes_removed": report["bytes_removed"], "retained": len(report["retained"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--keep", action="append", default=[])
    args = parser.parse_args()
    run(args.apply, set(args.keep))
