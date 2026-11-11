"""Focused discovery/build-marker/lifecycle checks; never launch a native host."""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vocaloid_bridge import install
from vocaloid_bridge import native_client


class SelectionChecks(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(TemporaryDirectory(prefix="selection-", dir=Path(__file__).parent)))
        self.programs = self.root / "programs"
        self.programs.mkdir()
        self.stack.enter_context(patch.dict(install.os.environ, {"ProgramFiles": str(self.programs)}, clear=True))
        self.registry = self.stack.enter_context(patch.object(install, "_registry_roots", return_value=[]))
        self.versions: dict[Path, str] = {}
        self.stack.enter_context(patch.object(install, "_file_version", side_effect=lambda path: self.versions[path]))
        self.launch = self.stack.enter_context(patch.object(native_client, "IsolatedProcess", side_effect=AssertionError("Native launch forbidden")))

    def editor(self, name: str, product: str, version: str) -> install.VocaloidInstallation:
        directory = self.root / name
        directory.mkdir(parents=True)
        core = directory / (product + ".dll")
        core.write_bytes(b"fixture core")
        self.versions[core] = version
        return install.VocaloidInstallation(directory, product, core, version, "argument")

    def artifacts(self, installation: install.VocaloidInstallation) -> Path:
        host = install.host_path(self.root, installation)
        host.parent.mkdir(parents=True, exist_ok=True)
        for suffix in (".dll", ".deps.json", ".runtimeconfig.json"):
            host.with_suffix(suffix).write_bytes(b"fixture artifact")
        self.marker(installation, host)
        return host

    def marker(self, installation: install.VocaloidInstallation, host: Path, **changes: str) -> None:
        fields = {**install._marker(installation, host), **changes}
        (host.parent / install.TARGET_FILE).write_text("".join(f"{key}={value}\n" for key, value in fields.items()), encoding="utf-8")

    def test_custom_registry_numeric_and_override(self) -> None:
        older = self.editor("custom-nine", "VOCALOID7", "7.9.0.0")
        newer = self.editor("custom-ten", "VOCALOID7", "7.10.0.0")
        self.registry.return_value = [("registry", str(older.path), "99.0"), ("registry", str(newer.path), "1.0")]
        self.assertEqual(install.discover().path, newer.path)
        install.os.environ["VOCALOID_INSTALL"] = str(older.path)
        self.assertEqual(install.discover().path, older.path)
        self.assertEqual(install.discover(newer.path).path, newer.path)
        with self.assertRaises(install.VocaloidInstallError):
            install.discover(self.root / "missing")

    def test_program_files_and_future_rejection(self) -> None:
        supported = self.editor("programs/VOCALOID7/Editor", "VOCALOID7", "7.0.0.1")
        self.assertEqual(install.discover().path, supported.path)
        future = self.editor("programs/VOCALOID8/Editor", "VOCALOID8", "8.0.0.0")
        with self.assertRaisesRegex(install.VocaloidInstallError, "Unsupported installed product VOCALOID8"):
            install.discover()
        self.assertEqual(install.discover(supported.path).path, supported.path)
        with self.assertRaises(install.VocaloidInstallError):
            install.discover(future.path)

    def test_marker_requires_exact_build_identity(self) -> None:
        installation = self.editor("v7", "VOCALOID7", "7.0.0.1")
        host = self.artifacts(installation)
        install.validate_target(installation, host)
        for field, value in {"assembly": "VOCALOID6", "product": "VOCALOID6", "install": str(self.root), "version": "7.1.0.0", "framework": "net8.0-windows", "host_sha256": "stale"}.items():
            with self.subTest(field=field):
                self.marker(installation, host, **{field: value})
                with self.assertRaisesRegex(install.VocaloidInstallError, "setup.ps1"):
                    install.validate_target(installation, host)
        (host.parent / install.TARGET_FILE).unlink()
        with self.assertRaises(install.VocaloidInstallError):
            install.validate_target(installation, host)
        self.marker(installation, host)
        host.write_bytes(b"replaced DLL")
        with self.assertRaises(install.VocaloidInstallError):
            install.validate_target(installation, host)

    def test_missing_build_never_launches_old_dll(self) -> None:
        installation = self.editor("programs/VOCALOID7/Editor", "VOCALOID7", "7.0.0.1")
        legacy = self.root / "native/bin/Release/net10.0-windows/VocaloidBridge.Host.dll"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"old DLL")
        client = native_client.NativeClient(self.root)
        with patch.object(native_client.shutil, "which", return_value="dotnet"):
            with self.assertRaisesRegex(native_client.NativeError, "setup.ps1"):
                client.request("ping")
        self.launch.assert_not_called()
        self.assertEqual(client.installation.path, installation.path)

    def test_refresh_only_between_hosts(self) -> None:
        first = self.editor("v6", "VOCALOID6", "6.13.3.1")
        second = self.editor("v7", "VOCALOID7", "7.0.0.1")
        self.artifacts(first)
        self.artifacts(second)
        namespace = "VocaloidBridge-" + "a" * 32
        with patch.object(native_client, "discover", return_value=first) as discover:
            client = native_client.NativeClient(self.root)
            discover.assert_not_called()
            self.launch.side_effect = lambda *args: Mock(process=object(), exit_code=0)
            with patch.object(native_client.shutil, "which", return_value="dotnet"), patch.object(client, "_running", side_effect=lambda: client.child is not None), patch.object(client, "_exchange", return_value={"sessions": 0}), patch.object(client, "_remove_cache") as cleanup:
                client.request("ping")
                self.assertEqual(client.installation, first)
                client.cache_namespace = namespace
                discover.return_value = second
                client.request("ping")
                self.assertEqual(discover.call_count, 1)
                self.assertEqual(client.installation, first)
                client.runtime("restart")
                cleanup.assert_called_once_with(namespace, "VOCALOID6")
                self.assertEqual(client.installation, second)
                self.assertEqual(discover.call_count, 2)
                self.assertEqual(self.launch.call_count, 2)
                client.close()
                self.assertIsNone(client._installation)

    def test_cache_cleanup_is_product_and_namespace_scoped(self) -> None:
        namespace = "VocaloidBridge-" + "b" * 32
        other = "VocaloidBridge-" + "c" * 32
        install.os.environ["LOCALAPPDATA"] = str(self.root)
        for product in ("VOCALOID6", "VOCALOID7", "VOCALOID8"):
            for kind in ("VSM", "VSMCaches"):
                for name in (namespace, other):
                    (self.root / product / kind / name).mkdir(parents=True)
        native_client.NativeClient._remove_cache(namespace, "VOCALOID6")
        for product in ("VOCALOID6", "VOCALOID7", "VOCALOID8"):
            for kind in ("VSM", "VSMCaches"):
                self.assertEqual((self.root / product / kind / namespace).exists(), product != "VOCALOID6")
                self.assertTrue((self.root / product / kind / other).is_dir())


if __name__ == "__main__":
    unittest.main(verbosity=2)