"""Report or apply the workspace temporary-file sweep.

The MCP server also runs this sweep in a background thread, so this entry point
is for inspection and for machines that keep old files for longer:

    .venv/Scripts/python.exe tools/clean_temp_output.py
    .venv/Scripts/python.exe tools/clean_temp_output.py --apply
    .venv/Scripts/python.exe tools/clean_temp_output.py --max-age-minutes 30 --keep "*.vpr" --apply
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vocaloid_bridge.cleanup import DEFAULT_MAX_AGE_SECONDS, sweep


def human(report: dict) -> str:
    mode = report.get("mode", "apply")
    if report.get("skipped"):
        return f"{mode}: skipped ({report['skipped']})"
    if mode == "apply":
        headline = (
            f"removed {report['removed_files']} files / "
            f"{report['removed_directories']} directories / {report['bytes_removed']} bytes"
        )
    else:
        headline = (
            f"would remove {report['candidate_files']} files / "
            f"{report['candidate_bytes']} bytes"
        )
    lines = [
        f"{mode}: {headline}",
        f"scanned {report['scanned']} files older than {report['max_age_seconds']} seconds; "
        f"retained {report['retained']}; failures {len(report.get('failures') or [])}",
        f"receipt: {report.get('report')}",
    ]
    shown = report["removed_files"] if mode == "apply" else report["candidate_files"]
    for item in (report.get("removed_samples") or [])[:10]:
        lines.append(f"  {item['path']} ({item['bytes']} bytes)")
    if shown > 10:
        lines.append(f"  ... {shown - 10} more")
    for item in (report.get("failures") or [])[:10]:
        lines.append(f"  FAILED {item['path']}: {item['error']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Delete candidates; default is a dry run.")
    parser.add_argument(
        "--max-age-minutes", type=float, default=DEFAULT_MAX_AGE_SECONDS / 60,
        help="Age limit in minutes (default: 60).",
    )
    parser.add_argument(
        "--keep", action="append", default=[], metavar="GLOB",
        help="Keep matching workspace-relative paths or file names; repeatable.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full JSON receipt.")
    arguments = parser.parse_args()
    report = sweep(
        ROOT,
        max_age_seconds=arguments.max_age_minutes * 60,
        apply=arguments.apply,
        keep=arguments.keep,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2) if arguments.json else human(report))
    return 0 if not report.get("failures") else 1


if __name__ == "__main__":
    raise SystemExit(main())
