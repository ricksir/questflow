from __future__ import annotations

import unittest
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]


class ArchitectureRefactorTests(unittest.TestCase):
    def test_app_is_only_composition_root(self) -> None:
        app_lines = (BASE / "app.py").read_text(encoding="utf-8").splitlines()
        self.assertLess(len(app_lines), 180)
        content = "\n".join(app_lines)
        self.assertIn("QuestFlowWebApi", content)
        self.assertIn("run_chrome", content)
        self.assertNotIn("webview.create_window", content)
        self.assertNotIn("edgechromium", content)
        self.assertIn("QuestFlowApp", content)  # fallback clássico preservado

    def test_web_ui_is_split_from_business_logic(self) -> None:
        self.assertTrue((BASE / "web_api.py").exists())
        self.assertTrue((BASE / "web" / "index.html").exists())
        self.assertTrue((BASE / "web" / "styles.css").exists())
        self.assertTrue((BASE / "web" / "app.js").exists())
        api_content = (BASE / "web_api.py").read_text(encoding="utf-8")
        self.assertIn("QuestionQueryService", api_content)
        self.assertIn("QuestionCommandService", api_content)
        self.assertIn("StudyRepository", api_content)

    def test_classic_ui_remains_available(self) -> None:
        self.assertTrue((BASE / "app_classic.py").exists())
        required = {
            "shell_mixin.py",
            "dashboard_mixin.py",
            "import_mixin.py",
            "review_layout_mixin.py",
            "review_enrichment_mixin.py",
            "deep_analysis_mixin.py",
            "question_editor_mixin.py",
            "flow_mixin.py",
            "settings_export_mixin.py",
            "corrections_coverage_mixin.py",
        }
        actual = {path.name for path in (BASE / "ui").glob("*_mixin.py")}
        self.assertTrue(required.issubset(actual))
        for filename in required:
            count = len((BASE / "ui" / filename).read_text(encoding="utf-8").splitlines())
            self.assertLess(count, 1000, filename)

    def test_views_do_not_call_database_directly(self) -> None:
        violations = []
        for path in (BASE / "ui").glob("*.py"):
            if "self.database." in path.read_text(encoding="utf-8"):
                violations.append(path.name)
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
