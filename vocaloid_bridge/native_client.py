"""A native-engine child process isolated from the interactive desktop."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import msvcrt
import os
from pathlib import Path
import queue
import re
import shutil
import stat
import subprocess
import threading
from typing import Any
import uuid

import win32api
import win32con
import win32event
import win32job
import win32process

from .install import SUPPORTED_PRODUCTS, TARGET_FILE, VocaloidInstallation, VocaloidInstallError, discover, host_path, validate_target


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.CreateDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID]
_user32.CreateDesktopW.restype = wintypes.HANDLE
_user32.CloseDesktop.argtypes = [wintypes.HANDLE]
_user32.CloseDesktop.restype = wintypes.BOOL


class NativeError(RuntimeError):
    pass


class IsolatedProcess:
    def __init__(self, arguments: list[str], workspace: Path):
        self.desktop_name = "VocaloidBridge-" + uuid.uuid4().hex
        self.desktop = None
        self.process = None
        self.job = None
        self.pid = None
        self.stdin = None
        self.stdout = None
        self.reader = None
        self.exit_code = None
        self.lines: queue.Queue[bytes | Exception | None] = queue.Queue()
        runtime = workspace / ".runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        self.temp_root = (runtime / "tmp").resolve()
        if self.temp_root.parent != runtime.resolve():
            raise NativeError("Private temporary root is outside the workspace runtime directory.")
        self.temp_directory = self.temp_root / self.desktop_name
        self.temp_directory.mkdir(parents=True, exist_ok=False)
        self.log_path = runtime / (self.desktop_name + ".stderr.log")
        child_input = parent_output = parent_input = child_output = None
        error_log = None
        process_thread = None
        try:
            self.desktop = _user32.CreateDesktopW(self.desktop_name, None, None, 0, 0x00FF, None)
            if not self.desktop:
                raise ctypes.WinError(ctypes.get_last_error())
            child_input, parent_output = os.pipe()
            parent_input, child_output = os.pipe()
            os.set_inheritable(child_input, True)
            os.set_inheritable(child_output, True)
            error_log = self.log_path.open("xb", buffering=0)
            os.set_inheritable(error_log.fileno(), True)
            startup = win32process.STARTUPINFO()
            startup.lpDesktop = "WinSta0\\" + self.desktop_name
            startup.dwFlags = win32con.STARTF_USESTDHANDLES | win32con.STARTF_FORCEOFFFEEDBACK
            startup.hStdInput = msvcrt.get_osfhandle(child_input)
            startup.hStdOutput = msvcrt.get_osfhandle(child_output)
            startup.hStdError = msvcrt.get_osfhandle(error_log.fileno())
            self.job = win32job.CreateJobObject(None, self.desktop_name + "-Job")
            limits = win32job.QueryInformationJobObject(self.job, win32job.JobObjectExtendedLimitInformation)
            limits["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            win32job.SetInformationJobObject(self.job, win32job.JobObjectExtendedLimitInformation, limits)
            flags = win32con.CREATE_NO_WINDOW | win32con.CREATE_SUSPENDED | win32con.CREATE_UNICODE_ENVIRONMENT
            self.process, process_thread, self.pid, _ = win32process.CreateProcess(
                arguments[0], subprocess.list2cmdline(arguments), None, None, True,
                flags, {**os.environ, "TEMP": str(self.temp_directory), "TMP": str(self.temp_directory)}, str(workspace), startup,
            )
            win32job.AssignProcessToJobObject(self.job, self.process)
            win32process.ResumeThread(process_thread)
            self.stdin = os.fdopen(parent_output, "wb", buffering=0)
            parent_output = None
            self.stdout = os.fdopen(parent_input, "rb")
            parent_input = None
            self.reader = threading.Thread(target=self._read, name="vocaloid-native-rpc-reader", daemon=True)
            self.reader.start()
        except BaseException:
            self.close()
            raise
        finally:
            if process_thread is not None:
                win32api.CloseHandle(process_thread)
            for descriptor in (child_input, child_output, parent_input, parent_output):
                if descriptor is not None:
                    os.close(descriptor)
            if error_log is not None:
                error_log.close()

    def _read(self) -> None:
        try:
            while self.stdout is not None:
                line = self.stdout.readline(16 * 1024 * 1024 + 1)
                if not line:
                    break
                if len(line) > 16 * 1024 * 1024 or not line.endswith(b"\n"):
                    raise NativeError("Native RPC returned an oversized or incomplete JSON line.")
                self.lines.put(line)
        except Exception as error:
            self.lines.put(error)
        finally:
            self.lines.put(None)

    def read_line(self, timeout: float) -> bytes:
        try:
            line = self.lines.get(timeout=timeout)
        except queue.Empty as error:
            raise NativeError(f"Native RPC timed out; see {self.log_path}.") from error
        if line is None:
            code = win32process.GetExitCodeProcess(self.process) if self.process is not None else None
            raise NativeError(f"Native engine exited ({code}); see {self.log_path}.")
        if isinstance(line, Exception):
            raise NativeError(str(line)) from line
        return line

    def close(self) -> None:
        if self.stdin is not None:
            self.stdin.close()
            self.stdin = None
        if self.process is not None:
            if win32event.WaitForSingleObject(self.process, 3000) != win32con.WAIT_OBJECT_0:
                win32process.TerminateProcess(self.process, 1)
                win32event.WaitForSingleObject(self.process, 1000)
            if win32event.WaitForSingleObject(self.process, 0) == win32con.WAIT_OBJECT_0:
                self.exit_code = win32process.GetExitCodeProcess(self.process)
            win32api.CloseHandle(self.process)
            self.process = None
        if self.reader is not None:
            self.reader.join(timeout=1)
        if self.stdout is not None:
            self.stdout.close()
            self.stdout = None
        if self.job is not None:
            win32api.CloseHandle(self.job)
            self.job = None
        if self.desktop:
            _user32.CloseDesktop(self.desktop)
            self.desktop = None
        if self.temp_directory.exists():
            target = self.temp_directory.resolve(strict=True)
            if target.parent != self.temp_root or target.name != self.desktop_name or self.temp_directory.is_symlink():
                raise NativeError("Private temporary directory is outside its owned root.")
            shutil.rmtree(target)


class NativeClient:
    def __init__(self, workspace: Path, install: Path | None = None):
        self.workspace = workspace.resolve()
        self._explicit_install = install
        self._installation: VocaloidInstallation | None = None
        self.child: IsolatedProcess | None = None
        self.counter = 0
        self.lock = threading.RLock()
        self.failed = ""
        self.host_snapshot: Path | None = None
        self.generation = 0
        self.cache_namespace: str | None = None

    @property
    def installation(self) -> VocaloidInstallation:
        with self.lock:
            if self.child is not None and self._installation is not None:
                return self._installation
            try:
                return discover(self._explicit_install)
            except VocaloidInstallError as error:
                raise NativeError(str(error)) from error

    @property
    def install(self) -> Path:
        return self.installation.path

    def _running(self) -> bool:
        return self.child is not None and self.child.process is not None and (
            win32event.WaitForSingleObject(self.child.process, 0) == win32con.WAIT_TIMEOUT
        )

    def _release_child(self) -> None:
        child, self.child = self.child, None
        namespace, self.cache_namespace = self.cache_namespace, None
        installation, self._installation = self._installation, None
        try:
            if child is not None:
                child.close()
                if child.exit_code is not None and namespace is not None and installation is not None:
                    self._remove_cache(namespace, installation.product)
        finally:
            self._remove_snapshot()

    @staticmethod
    def _remove_cache(namespace: str, product: str) -> None:
        if not re.fullmatch(r"VocaloidBridge-[0-9a-f]{32}", namespace):
            raise NativeError("Invalid owned native cache namespace.")
        if product not in SUPPORTED_PRODUCTS:
            raise NativeError("Invalid owned native cache product.")
        local = Path(os.environ["LOCALAPPDATA"])
        root = local / product
        for kind in ("VSM", "VSMCaches"):
            base = root / kind
            path = base / namespace
            if not path.exists():
                continue
            if any(parent.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
                   for parent in (root, base)):
                raise NativeError("Owned native cache root contains a reparse point.")
            if path.resolve().parent != base.resolve():
                raise NativeError("Owned native cache escaped its parent.")
            if any(entry.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
                   for entry in (path, *path.rglob("*"))):
                raise NativeError("Owned native cache contains a reparse point.")
            shutil.rmtree(path)

    def runtime(self, operation: str, discard_sessions: bool = False) -> dict[str, Any]:
        """Manage only this MCP server's private VOCALOID process."""
        with self.lock:
            if operation not in {"status", "start", "stop", "restart"}:
                raise NativeError("Unknown runtime operation.")
            running = self._running()
            previous_pid = self.child.pid if self.child is not None else None
            if operation == "status" and not running:
                return {"operation": operation, "running": False, "generation": self.generation,
                        "last_error": self.failed or None, "managed_by_mcp": True}
            if operation in {"stop", "restart"}:
                status = self.request("ping") if running else {}
                sessions = status.get("sessions", 0)
                if sessions and not discard_sessions:
                    raise NativeError("Close or save active projects first, or explicitly set discard_sessions=true.")
                self._release_child()
                self.failed = ""
                if operation == "stop":
                    return {"operation": operation, "running": False, "generation": self.generation,
                            "previous_pid": previous_pid, "discarded_sessions": sessions, "managed_by_mcp": True}
            status = self.request("ping")
            return {**status, "operation": operation, "running": True, "generation": self.generation,
                    "previous_pid": previous_pid, "managed_by_mcp": True}

    def _snapshot_host(self, host: Path) -> Path:
        # A running Windows CLR locks its assembly. Run the exact built artifacts
        # from a private copy so rebuilding never replaces an in-use assembly.
        root = self.workspace / ".runtime" / "hosts"
        root.mkdir(parents=True, exist_ok=True)
        snapshot = root / uuid.uuid4().hex
        snapshot.mkdir()
        self.host_snapshot = snapshot
        for suffix in (".dll", ".deps.json", ".runtimeconfig.json"):
            source = host.with_name("VocaloidBridge.Host" + suffix)
            shutil.copyfile(source, snapshot / source.name)
        shutil.copyfile(host.parent / TARGET_FILE, snapshot / TARGET_FILE)
        return snapshot / host.name

    def request(self, method: str, parameters: dict[str, Any] | None = None, timeout: float = 180) -> dict[str, Any]:
        with self.lock:
            # Encode before touching the process: a local JSON error is not a
            # dispatched native mutation and must not poison a healthy session.
            parameters = parameters or {}
            json.dumps(parameters, ensure_ascii=False, allow_nan=False)
            if self.child is not None and not self._running():
                self.failed = "Native host exited; previous project and object handles have expired."
                self._release_child()
            if self.failed:
                if method not in {"ping", "create", "open", "import_project", "voices", "api_catalog"}:
                    raise NativeError(self.failed + " Create/open a project or use vocaloid_runtime to start a fresh host.")
                self.failed = ""
            if self.child is None:
                dotnet = shutil.which("dotnet")
                if dotnet is None:
                    raise NativeError("The .NET 10 runtime is required; dotnet was not found on PATH.")
                installation = self.installation
                host = host_path(self.workspace, installation)
                try:
                    validate_target(installation, host)
                except VocaloidInstallError as error:
                    raise NativeError(str(error)) from error
                try:
                    snapshot = self._snapshot_host(host)
                    validate_target(installation, snapshot)
                    self._installation = installation
                    self.child = IsolatedProcess([dotnet, str(snapshot), "--serve", str(installation.path), str(self.workspace)], self.workspace)
                    self.generation += 1
                except BaseException:
                    self._installation = None
                    self._remove_snapshot()
                    raise
                status = self._exchange("ping", {}, timeout)
                if method == "ping":
                    return status
            return self._exchange(method, parameters, timeout)

    def _exchange(self, method: str, parameters: dict[str, Any], timeout: float) -> dict[str, Any]:
        self.counter += 1
        payload = json.dumps({"id": self.counter, "method": method, "params": parameters},
                             ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
        try:
            self.child.stdin.write(payload)
            response = json.loads(self.child.read_line(timeout).decode("utf-8"))
            if response.get("id") != self.counter:
                raise NativeError("Native RPC response ID did not match the request.")
        except BaseException as error:
            self.failed = "Native request outcome is unknown; the request was not replayed. " + str(error)
            self._release_child()
            if not isinstance(error, Exception):
                raise
            raise NativeError(self.failed) from error
        if "error" in response:
            detail = response["error"]
            raise NativeError(f"{detail.get('type', 'NativeError')}: {detail.get('message', detail)}")
        result = response["result"]
        if method == "ping":
            installation = self._installation
            if (installation is None or result.get("product") != installation.product
                    or result.get("version") != installation.version
                    or not isinstance(result.get("install"), str)
                    or Path(result["install"]).resolve() != installation.path):
                self.failed = "Native host identity did not match the selected build/installation."
                self._release_child()
                raise NativeError(self.failed)
            namespace = result.get("cache_namespace")
            if not isinstance(namespace, str) or not re.fullmatch(r"VocaloidBridge-[0-9a-f]{32}", namespace):
                self.failed = "Native host did not return a valid owned cache namespace."
                self._release_child()
                raise NativeError(self.failed)
            if self.cache_namespace is not None and namespace != self.cache_namespace:
                self.failed = "Native host cache namespace changed during its lifetime."
                self._release_child()
                raise NativeError(self.failed)
            self.cache_namespace = namespace
        return result

    def close(self) -> None:
        with self.lock:
            self._release_child()
            self.failed = ""

    def _remove_snapshot(self) -> None:
        if self.host_snapshot is not None:
            snapshot = self.host_snapshot.resolve()
            root = (self.workspace / ".runtime" / "hosts").resolve()
            if snapshot.parent != root or len(snapshot.name) != 32:
                raise NativeError("Private host snapshot path is outside the owned root.")
            shutil.rmtree(snapshot)
            self.host_snapshot = None
