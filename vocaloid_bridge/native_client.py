"""A native-engine child process isolated from the interactive desktop."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import msvcrt
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
from typing import Any
import uuid

import win32api
import win32con
import win32event
import win32job
import win32process


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
        self.lines: queue.Queue[bytes | Exception | None] = queue.Queue()
        runtime = workspace / ".runtime"
        runtime.mkdir(parents=True, exist_ok=True)
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
                flags, dict(os.environ), str(workspace), startup,
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


class NativeClient:
    def __init__(self, workspace: Path, install: Path | None = None):
        self.workspace = workspace.resolve()
        self.install = install or Path(os.environ.get("VOCALOID_INSTALL", r"C:\Program Files\VOCALOID6\Editor"))
        self.child: IsolatedProcess | None = None
        self.counter = 0
        self.lock = threading.Lock()
        self.failed = ""
        self.host_snapshot: Path | None = None

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
        return snapshot / host.name

    def request(self, method: str, parameters: dict[str, Any] | None = None, timeout: float = 180) -> dict[str, Any]:
        with self.lock:
            if self.failed:
                raise NativeError(self.failed)
            if self.child is None:
                dotnet = shutil.which("dotnet")
                host = self.workspace / "native/bin/Release/net8.0-windows/VocaloidBridge.Host.dll"
                if dotnet is None or not host.is_file():
                    raise NativeError("Build the native host first: dotnet build native/VocaloidBridge.Host.csproj -c Release.")
                try:
                    snapshot = self._snapshot_host(host)
                    self.child = IsolatedProcess([dotnet, str(snapshot), "--serve", str(self.install), str(self.workspace)], self.workspace)
                except BaseException:
                    self._remove_snapshot()
                    raise
            self.counter += 1
            request = {"id": self.counter, "method": method, "params": parameters or {}}
            try:
                payload = json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
                self.child.stdin.write(payload)
                response = json.loads(self.child.read_line(timeout).decode("utf-8"))
                if response.get("id") != self.counter:
                    raise NativeError("Native RPC response ID did not match the request.")
            except Exception as error:
                self.failed = str(error)
                self.child.close()
                raise
            if "error" in response:
                detail = response["error"]
                raise NativeError(f"{detail.get('type', 'NativeError')}: {detail.get('message', detail)}")
            return response["result"]

    def close(self) -> None:
        with self.lock:
            if self.child is not None:
                self.child.close()
                self.child = None
            self._remove_snapshot()

    def _remove_snapshot(self) -> None:
        if self.host_snapshot is not None:
            snapshot = self.host_snapshot.resolve()
            root = (self.workspace / ".runtime" / "hosts").resolve()
            if snapshot.parent != root or len(snapshot.name) != 32:
                raise NativeError("Private host snapshot path is outside the owned root.")
            shutil.rmtree(snapshot)
            self.host_snapshot = None
