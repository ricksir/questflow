from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import installer


class InstallerTests(unittest.TestCase):
    def test_pip_command_preserves_cache_and_disables_version_check(self) -> None:
        command = installer.pip_install_command()
        self.assertNotIn("--no-cache-dir", command)
        self.assertIn("--disable-pip-version-check", command)
        self.assertIn("--no-input", command)
        self.assertNotIn("--upgrade", command)

    def test_requirements_hash_changes_with_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "requirements.txt"
            path.write_text("A==1\n", encoding="utf-8")
            first = installer.requirements_hash(path)
            path.write_text("A==2\n", encoding="utf-8")
            second = installer.requirements_hash(path)
        self.assertNotEqual(first, second)

    def test_marker_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            marker = Path(temp_name) / "marker.json"
            state = installer.DependencyState("abc", "3.14.5", "C:/Python/python.exe")
            installer.write_marker(state, marker)
            payload = installer.read_marker(marker)
        self.assertEqual(payload["schema"], installer.MARKER_SCHEMA)
        self.assertEqual(payload["requirements_hash"], "abc")

    def test_marker_requires_all_fields(self) -> None:
        state = installer.DependencyState("abc", "3.14.5", "C:/Python/python.exe")
        valid = {
            "schema": installer.MARKER_SCHEMA,
            "requirements_hash": "abc",
            "python_version": "3.14.5",
            "python_executable": "C:/Python/python.exe",
            "lock_verified": True,
        }
        self.assertTrue(installer.marker_matches(state, valid))
        missing_lock = dict(valid)
        missing_lock.pop("lock_verified")
        self.assertFalse(installer.marker_matches(state, missing_lock))
        invalid = dict(valid)
        invalid["python_version"] = "3.13.0"
        self.assertFalse(installer.marker_matches(state, invalid))

    def test_prepare_skips_install_when_ready(self) -> None:
        with mock.patch.object(installer, "dependencies_are_ready", return_value=(True, "")), mock.patch.object(
            installer, "install_dependencies"
        ) as install_mock:
            result = installer.prepare_dependencies(force=False)
        self.assertEqual(result, 0)
        install_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
