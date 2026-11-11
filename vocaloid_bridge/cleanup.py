"""Delete bridge-owned temporary files that are older than a fixed age.

The bridge writes test output, probe audio and native session scratch data under
the workspace. Originals live outside ``output``, so a periodic sweep keeps the
workspace bounded:

* ``output/**`` files older than the age limit
* ``.runtime/mcp-temp/**`` (Python TEMP/TMP for the server) older than the limit
* orphaned ``.runtime/tmp/VocaloidBridge-<guid>/`` scratch trees older than the limit
* ``.runtime/VocaloidBridge-<guid>.stderr.log`` files older than the limit

Nothing else under ``.runtime`` is touched. Reparse points, files still held
open by a live process and paths outside the owned roots are retained and
reported. Deletion is best effort: one failure never aborts the sweep, and the
MCP server never fails to start because of cleanup.
"""

from __future__ import annotations

from datetime import datetime, timezone
import fnmatch
import json
import os
from pathlib import Path
import re
import stat
import threading
import time
from typing import Any, Iterable
import uuid

DEFAULT_MAX_AGE_SECONDS = 60 * 60
MIN_MAX_AGE_SECONDS = 60
MAX_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
DEFAULT_INTERVAL_SECONDS = 10 * 60
REPORT_FORMAT = "vocaloid-bridge-temp-cleanup"
REPORT_VERSION = 1
REPORT_DIRECTORY = Path(".runtime") / "temp-cleanup"
REPORT_FILE = "last-report.json"
DRY_RUN_FILE = "last-dry-run.json"
LOCK_FILE = "sweep.lock"
STALE_LOCK_SECONDS = 10 * 60
SAMPLE_LIMIT = 100
RETENTION_SAMPLE_LIMIT = 50
LOG_NAME = re.compile(r"VocaloidBridge-[0-9a-f]{32}\.stderr\.log\Z")
NAMESPACE_NAME = re.compile(r"VocaloidBridge-[0-9a-f]{32}\Z")
_REPARSE_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_started = False
_started_lock = threading.Lock()


def enabled() -> bool:
    """Return whether automatic cleanup is allowed in this process."""
    return os.environ.get("VOCALOID_TEMP_CLEANUP", "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


def resolve_max_age(max_age_seconds: float | int | None = None) -> int:
    """Resolve and validate the age limit, defaulting to one hour."""
    if max_age_seconds is None:
        raw = os.environ.get("VOCALOID_TEMP_MAX_AGE_SECONDS", "").strip()
        if raw:
            try:
                max_age_seconds = float(raw)
            except ValueError:
                max_age_seconds = DEFAULT_MAX_AGE_SECONDS
        else:
            max_age_seconds = DEFAULT_MAX_AGE_SECONDS
    if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, (int, float)):
        raise TypeError("max_age_seconds must be a number")
    if not MIN_MAX_AGE_SECONDS <= max_age_seconds <= MAX_MAX_AGE_SECONDS:
        raise ValueError(
            f"max_age_seconds must be between {MIN_MAX_AGE_SECONDS} and {MAX_MAX_AGE_SECONDS}"
        )
    return int(max_age_seconds)


def interval_seconds() -> int:
    """Return the background sweep interval; zero means sweep once at startup."""
    raw = os.environ.get("VOCALOID_TEMP_CLEANUP_INTERVAL_SECONDS", "").strip()
    if not raw:
        return DEFAULT_INTERVAL_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_INTERVAL_SECONDS
    if value <= 0:
        return 0
    return max(MIN_MAX_AGE_SECONDS, value)


def sweep(
    workspace: str | Path,
    max_age_seconds: float | int | None = None,
    apply: bool = True,
    keep: Iterable[str] = (),
    now: float | None = None,
) -> dict[str, Any]:
    """Remove owned temporary files older than the age limit.

    ``apply=False`` projects the same selection without touching the disk and
    writes the dry-run receipt instead of the applied one. ``keep`` entries are
    glob patterns matched against both the workspace-relative path and the file
    name, case-insensitively.
    """
    if not isinstance(apply, bool):
        raise TypeError("apply must be a bool")
    workspace = Path(workspace).resolve(strict=True)
    age = resolve_max_age(max_age_seconds)
    started = time.time() if now is None else float(now)
    cutoff = started - age
    patterns = tuple(str(pattern) for pattern in keep if str(pattern).strip())
    report: dict[str, Any] = {
        "format": REPORT_FORMAT,
        "version": REPORT_VERSION,
        "workspace": str(workspace),
        "mode": "apply" if apply else "dry-run",
        "max_age_seconds": age,
        "cutoff_unix": cutoff,
        "started": _timestamp(started),
        "started_unix": started,
        "roots": [],
    }
    state = _state()
    lock: tuple[int, Path] | None = None
    if apply:
        lock = _acquire_lock(workspace)
        if lock is None:
            report.update(
                skipped="another sweep holds the lock",
                finished=_timestamp(time.time()),
                scanned=0,
                candidate_files=0,
                candidate_bytes=0,
                removed_files=0,
                removed_directories=0,
                bytes_removed=0,
                retained=0,
                failures=[],
                removed_samples=[],
                retained_samples=[],
            )
            report["report"] = str(_write_report(workspace, report, apply))
            return report
    try:
        runtime = workspace / ".runtime"
        output = workspace / "output"
        mcp_temp = runtime / "mcp-temp"
        if _owned_directory(workspace, output):
            report["roots"].append("output")
            _remove_tree(output, workspace, cutoff, state, patterns, apply)
        if _owned_directory(workspace, mcp_temp):
            report["roots"].append(".runtime/mcp-temp")
            _remove_tree(mcp_temp, workspace, cutoff, state, patterns, apply)
        if _owned_directory(workspace, runtime / "tmp"):
            report["roots"].append(".runtime/tmp")
            _sweep_native_temp(runtime / "tmp", workspace, cutoff, state, patterns, apply)
        if _owned_directory(workspace, runtime):
            report["roots"].append(".runtime scratch logs")
            _sweep_runtime_logs(runtime, workspace, cutoff, state, patterns, apply)
    except Exception as error:  # noqa: BLE001 - housekeeping must not escape
        state["failures"].append({"path": ".", "error": f"{type(error).__name__}: {error}"})
    finally:
        if lock is not None:
            _release_lock(lock)
    report["finished"] = _timestamp(time.time())
    report["finished_unix"] = time.time()
    report["duration_seconds"] = round(report["finished_unix"] - started, 3)
    report.update(state)
    report["retained"] = len(state["retained_samples"]) + state["retained_overflow"]
    report["report"] = str(_write_report(workspace, report, apply))
    return report


def summary(workspace: str | Path) -> dict[str, Any]:
    """Return the last applied sweep receipt for status reporting."""
    path = Path(workspace) / REPORT_DIRECTORY / REPORT_FILE
    try:
        age: int | None = resolve_max_age()
    except (TypeError, ValueError):
        age = DEFAULT_MAX_AGE_SECONDS
    result: dict[str, Any] = {
        "enabled": enabled(),
        "interval_seconds": interval_seconds(),
        "max_age_seconds": age,
        "report": None,
    }
    if not path.is_file():
        return result
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        result.update(report=str(path), error="receipt is unreadable")
        return result
    if data.get("format") != REPORT_FORMAT:
        result.update(report=str(path), error="receipt has an unexpected format")
        return result
    result.update(
        report=str(path),
        finished=data.get("finished"),
        removed_files=data.get("removed_files"),
        removed_directories=data.get("removed_directories"),
        bytes_removed=data.get("bytes_removed"),
        retained=data.get("retained"),
        failures=len(data.get("failures") or []),
    )
    return result


def start_background_sweep(workspace: str | Path, interval: int | None = None) -> threading.Thread | None:
    """Start the process-wide cleanup thread once; returns None when disabled."""
    global _started
    if not enabled():
        return None
    with _started_lock:
        if _started:
            return None
        _started = True
    delay = interval_seconds() if interval is None else max(0, int(interval))

    def run() -> None:
        while True:
            try:
                sweep(workspace, apply=True)
            except Exception:  # noqa: BLE001 - never break the MCP server
                pass
            if delay <= 0:
                return
            time.sleep(delay)

    thread = threading.Thread(target=run, name="vocaloid-temp-cleanup", daemon=True)
    thread.start()
    return thread


def _state() -> dict[str, Any]:
    return {
        "scanned": 0,
        "candidate_files": 0,
        "candidate_bytes": 0,
        "removed_files": 0,
        "removed_directories": 0,
        "bytes_removed": 0,
        "retained": 0,
        "retained_overflow": 0,
        "failures": [],
        "removed_samples": [],
        "retained_samples": [],
    }


def _timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat(timespec="seconds")


def _relative(workspace: Path, path: Path) -> str:
    try:
        return path.relative_to(workspace).as_posix()
    except ValueError:
        return str(path)


def _reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_ATTRIBUTE)


def _kept(workspace: Path, path: Path, patterns: tuple[str, ...]) -> bool:
    if not patterns:
        return False
    relative = _relative(workspace, path).lower()
    name = path.name.lower()
    for pattern in patterns:
        candidate = pattern.replace("\\", "/").lower()
        if fnmatch.fnmatchcase(relative, candidate) or fnmatch.fnmatchcase(name, candidate):
            return True
    return False


def _retain(state: dict[str, Any], workspace: Path, path: Path, reason: str) -> None:
    if len(state["retained_samples"]) < RETENTION_SAMPLE_LIMIT:
        state["retained_samples"].append({"path": _relative(workspace, path), "reason": reason})
    else:
        state["retained_overflow"] += 1


def _fail(state: dict[str, Any], workspace: Path, path: Path, error: BaseException | str) -> None:
    state["failures"].append({
        "path": _relative(workspace, path),
        "error": error if isinstance(error, str) else f"{type(error).__name__}: {error}",
    })


def _remove_file(
    path: Path,
    size: int,
    workspace: Path,
    state: dict[str, Any],
    busy_reason: str | None = None,
    apply: bool = True,
) -> bool:
    if not apply:
        if len(state["removed_samples"]) < SAMPLE_LIMIT:
            state["removed_samples"].append({"path": _relative(workspace, path), "bytes": size})
        return True
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    except PermissionError as error:
        if busy_reason is not None:
            _retain(state, workspace, path, busy_reason)
            return False
        try:
            os.chmod(path, stat.S_IWRITE)
            path.unlink()
        except OSError as retry:
            _fail(state, workspace, path, retry)
            return False
    except OSError as error:
        _fail(state, workspace, path, error)
        return False
    state["removed_files"] += 1
    state["bytes_removed"] += size
    if len(state["removed_samples"]) < SAMPLE_LIMIT:
        state["removed_samples"].append({"path": _relative(workspace, path), "bytes": size})
    return True


def _candidates(
    root: Path,
    workspace: Path,
    cutoff: float,
    state: dict[str, Any],
) -> tuple[list[tuple[Path, int]], list[Path]]:
    files: list[tuple[Path, int]] = []
    directories: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as error:
            _fail(state, workspace, current, error)
            continue
        for entry in entries:
            path = Path(entry.path)
            try:
                info = entry.stat(follow_symlinks=False)
            except FileNotFoundError:
                continue
            except OSError as error:
                _fail(state, workspace, path, error)
                continue
            if _reparse(info):
                _retain(state, workspace, path, "reparse point")
                continue
            if entry.is_dir(follow_symlinks=False):
                directories.append(path)
                stack.append(path)
                continue
            if not entry.is_file(follow_symlinks=False):
                _retain(state, workspace, path, "not a regular file")
                continue
            state["scanned"] += 1
            if info.st_mtime >= cutoff:
                _retain(state, workspace, path, "newer than cutoff")
                continue
            files.append((path, info.st_size))
    return files, directories


def _remove_tree(
    root: Path,
    workspace: Path,
    cutoff: float,
    state: dict[str, Any],
    patterns: tuple[str, ...],
    apply: bool,
) -> None:
    files, directories = _candidates(root, workspace, cutoff, state)
    for path, size in files:
        if _kept(workspace, path, patterns):
            _retain(state, workspace, path, "kept by pattern")
            continue
        state["candidate_files"] += 1
        state["candidate_bytes"] += size
        _remove_file(path, size, workspace, state, apply=apply)
    if apply:
        _prune(directories, cutoff, state)


def _prune(directories: list[Path], cutoff: float, state: dict[str, Any]) -> None:
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        try:
            info = directory.stat()
            if _reparse(info) or info.st_mtime >= cutoff:
                continue
            if any(directory.iterdir()):
                continue
            directory.rmdir()
        except FileNotFoundError:
            continue
        except OSError:
            continue
        state["removed_directories"] += 1


def _sweep_native_temp(
    root: Path,
    workspace: Path,
    cutoff: float,
    state: dict[str, Any],
    patterns: tuple[str, ...],
    apply: bool,
) -> None:
    runtime = root.parent
    try:
        entries = list(os.scandir(root))
    except OSError as error:
        _fail(state, workspace, root, error)
        return
    for entry in entries:
        path = Path(entry.path)
        try:
            info = entry.stat(follow_symlinks=False)
        except FileNotFoundError:
            continue
        except OSError as error:
            _fail(state, workspace, path, error)
            continue
        if _reparse(info):
            _retain(state, workspace, path, "reparse point")
            continue
        if entry.is_file(follow_symlinks=False):
            state["scanned"] += 1
            if info.st_mtime >= cutoff:
                _retain(state, workspace, path, "newer than cutoff")
                continue
            if _kept(workspace, path, patterns):
                _retain(state, workspace, path, "kept by pattern")
                continue
            state["candidate_files"] += 1
            state["candidate_bytes"] += info.st_size
            _remove_file(path, info.st_size, workspace, state, apply=apply)
            continue
        if not entry.is_dir(follow_symlinks=False):
            _retain(state, workspace, path, "not a regular file")
            continue
        if not NAMESPACE_NAME.fullmatch(path.name):
            _retain(state, workspace, path, "not a bridge scratch namespace")
            continue
        if _kept(workspace, path, patterns):
            _retain(state, workspace, path, "kept by pattern")
            continue
        log = runtime / (path.name + ".stderr.log")
        if log.exists():
            try:
                log_info = log.stat()
            except OSError as error:
                _fail(state, workspace, log, error)
                _retain(state, workspace, path, "scratch log state is unknown")
                continue
            if log_info.st_mtime >= cutoff:
                _retain(state, workspace, path, "scratch log is newer than cutoff")
                continue
            state["candidate_files"] += 1
            state["candidate_bytes"] += log_info.st_size
            if not apply:
                if len(state["removed_samples"]) < SAMPLE_LIMIT:
                    state["removed_samples"].append(
                        {"path": _relative(workspace, log), "bytes": log_info.st_size}
                    )
            else:
                try:
                    log.unlink()
                except PermissionError:
                    _retain(state, workspace, path, "scratch log is held by a live process")
                    continue
                except OSError as error:
                    _fail(state, workspace, log, error)
                    _retain(state, workspace, path, "scratch log could not be removed")
                    continue
                state["removed_files"] += 1
                state["bytes_removed"] += log_info.st_size
                if len(state["removed_samples"]) < SAMPLE_LIMIT:
                    state["removed_samples"].append(
                        {"path": _relative(workspace, log), "bytes": log_info.st_size}
                    )
        elif info.st_mtime >= cutoff:
            _retain(state, workspace, path, "newer than cutoff")
            continue
        _remove_tree(path, workspace, cutoff, state, patterns, apply)
        # The dead scratch log proves the owner is gone; the namespace root is
        # bridge-owned even when its directory timestamp is recent.
        try:
            if apply and not any(path.iterdir()):
                path.rmdir()
                state["removed_directories"] += 1
        except OSError:
            pass


def _sweep_runtime_logs(
    runtime: Path,
    workspace: Path,
    cutoff: float,
    state: dict[str, Any],
    patterns: tuple[str, ...],
    apply: bool,
) -> None:
    try:
        entries = list(os.scandir(runtime))
    except OSError as error:
        _fail(state, workspace, runtime, error)
        return
    for entry in entries:
        if not LOG_NAME.fullmatch(entry.name):
            continue
        path = Path(entry.path)
        if (runtime / "tmp" / path.name[:-len(".stderr.log")]).is_dir():
            # The matching scratch namespace is handled with the log as its liveness probe.
            continue
        try:
            info = entry.stat(follow_symlinks=False)
        except FileNotFoundError:
            continue
        except OSError as error:
            _fail(state, workspace, path, error)
            continue
        state["scanned"] += 1
        if _reparse(info):
            _retain(state, workspace, path, "reparse point")
            continue
        if info.st_mtime >= cutoff:
            _retain(state, workspace, path, "newer than cutoff")
            continue
        if _kept(workspace, path, patterns):
            _retain(state, workspace, path, "kept by pattern")
            continue
        state["candidate_files"] += 1
        state["candidate_bytes"] += info.st_size
        _remove_file(path, info.st_size, workspace, state,
                     busy_reason="held by a live process", apply=apply)


def _owned_directory(workspace: Path, path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return False
    if not stat.S_ISDIR(info.st_mode) or _reparse(info):
        return False
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return False
    return resolved == path and resolved != workspace and resolved.is_relative_to(workspace)


def _acquire_lock(workspace: Path) -> tuple[int, Path] | None:
    directory = workspace / REPORT_DIRECTORY
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    path = directory / LOCK_FILE
    for attempt in (0, 1):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = time.time() - path.stat().st_mtime
            except OSError:
                age = 0.0
            if attempt or age < STALE_LOCK_SECONDS:
                return None
            try:
                path.unlink()
            except OSError:
                return None
            continue
        except OSError:
            return None
        try:
            os.write(descriptor, f"{os.getpid()} {time.time()}\n".encode("ascii"))
        except OSError:
            pass
        return descriptor, path
    return None


def _release_lock(lock: tuple[int, Path]) -> None:
    descriptor, path = lock
    try:
        os.close(descriptor)
    except OSError:
        pass
    try:
        path.unlink()
    except OSError:
        pass


def _write_report(workspace: Path, report: dict[str, Any], apply: bool) -> Path:
    directory = workspace / REPORT_DIRECTORY
    path = directory / (REPORT_FILE if apply else DRY_RUN_FILE)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / f"{path.name}.{uuid.uuid4().hex[:8]}.tmp"
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        return path
    return path
