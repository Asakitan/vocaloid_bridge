"""Locate installed VOCALOID editors and choose the newest usable one.

The native host is compiled against one core assembly (``VOCALOID6.dll`` or
``VOCALOID7.dll``).  At runtime the Python side selects the newest installed
editor that contains a managed core assembly, passes that directory to the host
and verifies the host was built for the same product.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable

_PRODUCT = re.compile(r"^VOCALOID(\d+)$", re.IGNORECASE)
_CORE = re.compile(r"^VOCALOID(\d+)\.dll$", re.IGNORECASE)
_UNINSTALL_KEYS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
)
TARGET_FILE = "vocaloid-target.txt"
FRAMEWORK = "net10.0-windows"
SUPPORTED_PRODUCTS = {"VOCALOID6", "VOCALOID7"}


class VocaloidInstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class VocaloidInstallation:
    path: Path
    product: str
    core: Path
    version: str
    source: str

    @property
    def major(self) -> int:
        match = _PRODUCT.fullmatch(self.product)
        return int(match.group(1)) if match else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "product": self.product,
            "core_assembly": self.core.stem,
            "core_path": str(self.core),
            "version": self.version,
            "source": self.source,
        }


def _file_version(path: Path) -> str:
    try:
        import win32api

        info = win32api.GetFileVersionInfo(str(path), "\\")
        ms = int(info["FileVersionMS"])
        ls = int(info["FileVersionLS"])
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception as error:
        raise VocaloidInstallError(f"Cannot read the core assembly file version: {path}: {error}") from error


def _version_key(version: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+(?:\.\d+){0,3}", version):
        raise VocaloidInstallError(f"Invalid VOCALOID file version: {version!r}")
    parts = tuple(int(piece) for piece in version.split("."))
    return parts + (0,) * (4 - len(parts))


def _candidate_root(value: str | os.PathLike[str]) -> Path | None:
    path = Path(os.path.expandvars(str(value)).strip('"')).expanduser()
    try:
        path = path.resolve()
    except OSError:
        path = path.absolute()
    if path.is_file():
        path = path.parent
    if path.is_dir() and any(_CORE.fullmatch(item.name) for item in path.iterdir() if item.is_file()):
        return path
    editor = path / "Editor"
    return editor if editor.is_dir() else None


def _installation(editor: Path, source: str) -> VocaloidInstallation | None:
    cores = sorted(
        (item for item in editor.iterdir() if item.is_file() and _CORE.fullmatch(item.name)),
        key=lambda item: int(_CORE.fullmatch(item.name).group(1)),  # type: ignore[union-attr]
        reverse=True,
    )
    if not cores:
        return None
    if len(cores) != 1:
        raise VocaloidInstallError(f"Ambiguous VOCALOID core assemblies under: {editor}")
    core = cores[0]
    product = core.stem.upper()
    version = _file_version(core)
    major = int(_PRODUCT.fullmatch(product).group(1))
    if _version_key(version)[0] != major:
        raise VocaloidInstallError(f"Core product/version mismatch: {core} ({version})")
    return VocaloidInstallation(editor, product, core, version, source)


def _registry_roots() -> Iterable[tuple[str, str, str]]:
    try:
        import winreg
    except ImportError:
        return
    for hive_name, hive in (("HKLM", winreg.HKEY_LOCAL_MACHINE), ("HKCU", winreg.HKEY_CURRENT_USER)):
        for relative in _UNINSTALL_KEYS:
            try:
                key = winreg.OpenKey(hive, relative)
            except OSError:
                continue
            with key:
                index = 0
                while True:
                    try:
                        name = winreg.EnumKey(key, index)
                    except OSError:
                        break
                    index += 1
                    try:
                        with winreg.OpenKey(key, name) as entry:
                            display = winreg.QueryValueEx(entry, "DisplayName")[0]
                            if not isinstance(display, str) or not re.search(r"\bVOCALOID\s*\d+\b", display, re.IGNORECASE):
                                continue
                            if "editor" not in display.lower():
                                continue
                            try:
                                location = winreg.QueryValueEx(entry, "InstallLocation")[0]
                            except OSError:
                                location = ""
                            if not location:
                                try:
                                    location = winreg.QueryValueEx(entry, "DisplayIcon")[0]
                                    location = re.sub(r",\s*-?\d+$", "", location).strip('"')
                                except OSError:
                                    continue
                            try:
                                version = winreg.QueryValueEx(entry, "DisplayVersion")[0]
                            except OSError:
                                version = ""
                    except OSError:
                        continue
                    if isinstance(location, str) and location.strip():
                        yield f"{hive_name}:{relative}\\{name}", location, str(version)


def discover(explicit: str | os.PathLike[str] | None = None) -> VocaloidInstallation:
    """Return the newest usable editor installation.

    Precedence: explicit argument, ``VOCALOID_INSTALL``, registry entries and
    ``Program Files``/``ProgramW6432`` directory scans.  The highest product
    major wins; the file version breaks ties.
    """
    candidates: list[VocaloidInstallation] = []
    seen: set[Path] = set()

    def add(value: str | os.PathLike[str], source: str, required: bool = False) -> None:
        editor = _candidate_root(value)
        if editor is None:
            if required:
                raise VocaloidInstallError(f"VOCALOID editor directory is missing or invalid: {value}")
            return
        if editor in seen:
            return
        seen.add(editor)
        found = _installation(editor, source)
        if found is None:
            if required:
                raise VocaloidInstallError(f"No managed VOCALOID core assembly under: {editor}")
            return
        candidates.append(found)

    chosen = explicit if explicit is not None else os.environ.get("VOCALOID_INSTALL")
    if chosen is not None:
        if not str(chosen).strip():
            raise VocaloidInstallError("An explicit VOCALOID installation override cannot be empty.")
        add(chosen, "VOCALOID_INSTALL" if explicit is None else "argument", required=True)
        return _supported(candidates[0])

    for source, location, _ in _registry_roots():
        add(location, source)

    roots = {os.environ.get("ProgramW6432"), os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")}
    for raw_root in roots:
        if not raw_root:
            continue
        root = Path(raw_root)
        if not root.is_dir():
            continue
        for product_dir in sorted(root.glob("VOCALOID*")):
            if _PRODUCT.fullmatch(product_dir.name):
                add(product_dir, "directory scan")

    if not candidates:
        raise VocaloidInstallError(
            "No VOCALOID editor installation with a managed core assembly was found. "
            "Install VOCALOID6 or VOCALOID7, or set VOCALOID_INSTALL to the Editor directory."
        )
    candidates.sort(key=lambda item: (_version_key(item.version), str(item.path).casefold()), reverse=True)
    return _supported(candidates[0])


def _supported(installation: VocaloidInstallation) -> VocaloidInstallation:
    if installation.product not in SUPPORTED_PRODUCTS:
        raise VocaloidInstallError(
            f"Unsupported installed product {installation.product} ({installation.version}) at {installation.path}. "
            "Only VOCALOID6 and VOCALOID7 are supported; no automatic downgrade is performed. "
            "Select a supported installation explicitly with VOCALOID_INSTALL or setup.ps1 -Install."
        )
    return installation


def host_path(workspace: Path, installation: VocaloidInstallation) -> Path:
    return Path(workspace) / "native" / "bin" / "Release" / installation.product / FRAMEWORK / "VocaloidBridge.Host.dll"


def built_target(host: Path) -> dict[str, str]:
    path = host.parent / TARGET_FILE
    result: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return result
    for line in lines:
        key, separator, value = line.partition("=")
        if separator:
            if key.strip() in result:
                return {}
            result[key.strip()] = value.strip()
    return result


def _marker(installation: VocaloidInstallation, host: Path) -> dict[str, str]:
    return {
        "product": installation.product,
        "assembly": installation.core.stem,
        "install": str(installation.path),
        "version": installation.version,
        "framework": FRAMEWORK,
        "host_sha256": hashlib.sha256(host.read_bytes()).hexdigest(),
    }


def validate_target(installation: VocaloidInstallation, host: Path) -> None:
    command = f"pwsh -NoProfile -File tools/setup.ps1 -Install '{installation.path}'"
    try:
        if host.name != "VocaloidBridge.Host.dll":
            raise ValueError("unexpected host assembly filename")
        for suffix in (".dll", ".deps.json", ".runtimeconfig.json"):
            if not host.with_suffix(suffix).is_file():
                raise ValueError(f"missing host artifact: {host.with_suffix(suffix)}")
        target = built_target(host)
        expected = _marker(installation, host)
        for key, value in expected.items():
            actual = target.get(key)
            if key == "install" and actual:
                matches = Path(actual).resolve() == installation.path.resolve()
            else:
                matches = actual == value
            if not matches:
                raise ValueError(f"build marker mismatch for {key}: {actual!r} != {value!r}")
    except (OSError, ValueError) as error:
        raise VocaloidInstallError(f"No matching native build for {installation.product}: {error}. Run: {command}") from error


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover or validate the VOCALOID installation used by build and runtime.")
    parser.add_argument("--install")
    parser.add_argument("--product", choices=sorted(SUPPORTED_PRODUCTS))
    parser.add_argument("--host", type=Path)
    parser.add_argument("--write-target", action="store_true")
    arguments = parser.parse_args()
    try:
        installation = discover(arguments.install)
        if arguments.product and arguments.product != installation.product:
            raise VocaloidInstallError(f"Requested {arguments.product}, but {installation.path} contains {installation.product}.")
        if arguments.write_target:
            if arguments.host is None or not arguments.product or not arguments.install:
                raise VocaloidInstallError("Writing a target marker requires --host, --product and --install.")
            marker = _marker(installation, arguments.host)
            destination = arguments.host.parent / TARGET_FILE
            temporary = destination.with_suffix(".tmp")
            temporary.write_text("".join(f"{key}={value}\n" for key, value in marker.items()), encoding="utf-8")
            temporary.replace(destination)
        print(json.dumps(installation.to_dict()))
    except (VocaloidInstallError, OSError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
