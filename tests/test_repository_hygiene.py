from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.repository_hygiene import TrackedFile, _path_problems


class RepositoryHygieneTests(unittest.TestCase):
    def test_rejects_persistent_data_artifacts_and_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            files = [
                TrackedFile("100644", "data/questflow.db"),
                TrackedFile("100644", "QuestFlow_Mobile.apk"),
                TrackedFile("100644", "mobile/google-services.json"),
                TrackedFile("100644", ".env.production"),
            ]

            problems = _path_problems(root, files)

        self.assertTrue(any("data/questflow.db" in item for item in problems))
        self.assertTrue(any("QuestFlow_Mobile.apk" in item for item in problems))
        self.assertTrue(any("google-services.json" in item for item in problems))
        self.assertTrue(any(".env.production" in item for item in problems))

    def test_allows_source_and_documented_environment_example(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            files = [
                TrackedFile("100644", "core/study.py"),
                TrackedFile("100644", "tests/fixtures/ci/taxonomia_afrfb.json"),
                TrackedFile("100644", ".env.example"),
            ]

            self.assertEqual(_path_problems(root, files), [])

    def test_rejects_symbolic_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            problems = _path_problems(
                Path(temp_dir),
                [TrackedFile("120000", "core-linked")],
            )

        self.assertEqual(problems, ["link simbólico versionado: core-linked"])


if __name__ == "__main__":
    unittest.main()

