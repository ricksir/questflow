from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest import mock

import app_shared
import installer
from core.compatibility import CONTROLLED_PYTHON, compatibility_report
from core.production_hardening import (
    BackupPolicy,
    apply_retention_policy,
    create_backup,
    extract_update_zip,
    generate_sbom,
    parse_lock,
    restore_backup,
    sqlite_quick_check,
    test_restore as perform_restore_test,
    verify_backup,
    verify_lock_integrity,
)


class ProductionHardening673Tests(unittest.TestCase):
    def test_release_version(self) -> None:
        self.assertEqual(app_shared.APP_VERSION, "6.23.2")

    def test_lock_is_exact_and_sha256_verified(self) -> None:
        report = verify_lock_integrity()
        self.assertTrue(report["ok"], report)
        self.assertGreaterEqual(report["exact_entries"], 7)
        self.assertTrue(all("==" in item["entry"] for item in report["entries"]))
        self.assertEqual(report["sha256"], report["expected_sha256"])

    def test_installer_uses_verified_lock(self) -> None:
        self.assertEqual(installer.requirements_path().name, "requirements.lock")
        ok, detail = installer.verify_dependency_lock()
        self.assertTrue(ok, detail)
        command = installer.pip_install_command()
        self.assertIn("requirements.lock", " ".join(command))

    def test_lock_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            lock = root / "requirements.lock"
            digest = root / "requirements.lock.sha256"
            lock.write_text("demo==1.0\n", encoding="utf-8")
            digest.write_text(hashlib.sha256(lock.read_bytes()).hexdigest() + "\n", encoding="utf-8")
            self.assertTrue(verify_lock_integrity(lock, digest)["ok"])
            lock.write_text("demo==1.1\n", encoding="utf-8")
            self.assertFalse(verify_lock_integrity(lock, digest)["ok"])

    def test_sbom_contains_locked_components(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            output = Path(temp_name) / "sbom.json"
            payload = generate_sbom(output)
            self.assertEqual(payload["bomFormat"], "CycloneDX")
            self.assertEqual(payload["metadata"]["component"]["version"], "6.23.2")
            self.assertGreaterEqual(len(payload["components"]), 7)
            self.assertTrue(output.exists())

    def test_backup_verify_and_restore_test(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data = root / "data"
            backups = root / "backups"
            data.mkdir()
            db = data / "questflow_questions.sqlite"
            with closing(sqlite3.connect(db)) as connection:
                connection.execute("CREATE TABLE demo(id INTEGER PRIMARY KEY, value TEXT)")
                connection.execute("INSERT INTO demo(value) VALUES('ok')")
                connection.commit()
            (data / "config.json").write_text('{"ok":true}\n', encoding="utf-8")

            result = create_backup(data_dir=data, backup_root=backups, label="test")
            self.assertTrue(result.quick_check_ok)
            verified = verify_backup(result.path)
            self.assertTrue(verified["ok"], verified)
            restored = perform_restore_test(result.path)
            self.assertTrue(restored["ok"], restored)

            destination = root / "restored"
            direct = restore_backup(result.path, destination)
            self.assertTrue(direct["ok"])
            self.assertTrue((destination / "config.json").exists())
            self.assertTrue(sqlite_quick_check(destination / "questflow_questions.sqlite")["ok"])

    def test_corrupt_backup_hash_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data = root / "data"
            backups = root / "backups"
            data.mkdir()
            (data / "config.json").write_text("{}", encoding="utf-8")
            result = create_backup(data_dir=data, backup_root=backups, label="tamper")
            manifest = Path(result.path) / "manifest.json"
            manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            self.assertFalse(verify_backup(result.path)["ok"])

    def test_zip_slip_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            package = root / "bad.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("../escape.txt", "blocked")
            with self.assertRaises(ValueError):
                extract_update_zip(package, root / "out")

    def test_retention_policy_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            # Unknown/nonstandard directories are intentionally retained.
            unknown = root / "manual-copy"
            unknown.mkdir()
            (unknown / "manifest.json").write_text("{}", encoding="utf-8")
            report = apply_retention_policy(root, BackupPolicy(daily=1, weekly=1, monthly=1))
            self.assertTrue(report["ok"])
            self.assertTrue(unknown.exists())

    def test_python_314_is_controlled_not_silent_validation(self) -> None:
        self.assertEqual(CONTROLLED_PYTHON, (3, 14))
        with mock.patch("core.compatibility.sys.version_info", (3, 14, 1, "final", 0)):
            report = compatibility_report()
        self.assertTrue(report["python"]["controlled"])
        self.assertFalse(report["python"]["validated"])
        self.assertEqual(report["status"], "compatível_experimental")


if __name__ == "__main__":
    unittest.main()
