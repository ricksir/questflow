from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MobileOfflineResults6170Tests(unittest.TestCase):
    def test_release_versions(self):
        self.assertEqual((ROOT / "VERSION.txt").read_text(encoding="utf-8").strip(), "6.24.0")
        self.assertIn('version = "6.24.0"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        app = json.loads((ROOT / "mobile" / "app.json").read_text(encoding="utf-8"))
        package = json.loads((ROOT / "mobile" / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(app["expo"]["version"], "0.16.0")
        self.assertEqual(package["version"], "0.16.0")

    def test_dev_client_chrome_is_hidden_without_disabling_background_refresh(self):
        app = json.loads((ROOT / "mobile" / "app.json").read_text(encoding="utf-8"))
        plugins = app["expo"]["plugins"]
        dev_client = next(item for item in plugins if isinstance(item, list) and item and item[0] == "expo-dev-client")
        options = dev_client[1]
        self.assertFalse(options["toolsButton"])
        self.assertFalse(options["showMenuAtLaunch"])
        self.assertTrue(options["skipOnboarding"])
        self.assertEqual(options["launchMode"], "most-recent")

        guard = (ROOT / "mobile" / "src" / "lib" / "devUi.ts").read_text(encoding="utf-8")
        self.assertIn("DevLoadingView", guard)
        self.assertIn("showMessage = () => undefined", guard)
        self.assertIn("hideMenu", guard)
        self.assertNotIn("FastRefresh.disable", guard)
        layout = (ROOT / "mobile" / "app" / "_layout.tsx").read_text(encoding="utf-8")
        self.assertIn("suppressDevelopmentChrome();", layout)

    def test_offline_attempts_are_persistent_and_legacy_pending_results_are_recoverable(self):
        db = (ROOT / "mobile" / "src" / "lib" / "db.ts").read_text(encoding="utf-8")
        self.assertIn("answered_offline INTEGER NOT NULL DEFAULT 0", db)
        self.assertIn("legacy_pending_result", db)
        self.assertIn("listOfflineAttemptsAwaitingFeedback", db)
        self.assertIn("offlineAttemptHistoryInfo", db)
        self.assertIn("listOfflineAttemptHistory", db)
        self.assertIn("answered_offline=1 AND selected_index IS NOT NULL", db)

    def test_sync_resolves_every_pending_offline_feedback_not_only_current_question(self):
        sync = (ROOT / "mobile" / "src" / "lib" / "sync.ts").read_text(encoding="utf-8")
        self.assertIn("listOfflineAttemptsAwaitingFeedback(50)", sync)
        self.assertIn("for (const attempt of pendingFeedback)", sync)
        self.assertIn("api.feedback(attempt.attempt_id)", sync)
        self.assertIn("saveFeedback(attempt.attempt_id, result)", sync)
        self.assertIn("feedbackResolved", sync)

    def test_questions_screen_exposes_human_readable_offline_results_area(self):
        screen = (ROOT / "mobile" / "app" / "(tabs)" / "questions.tsx").read_text(encoding="utf-8")
        for expected in (
            "Respondidas offline",
            "Ver resultado e explicação",
            "Sua resposta",
            "Gabarito",
            "Aguardando",
            "Sincronizar resultados",
        ):
            self.assertIn(expected, screen)
        self.assertIn("markAttemptAnsweredOffline", screen)
        self.assertIn("offlineAttemptHistoryInfo", screen)

    def test_offline_reserve_still_contains_no_answer_key_and_no_parallel_learning_engine(self):
        offline_test = (ROOT / "tests" / "test_mobile_offline_pack_6160.py").read_text(encoding="utf-8")
        self.assertIn('self.assertNotIn("answer", question)', offline_test)
        self.assertIn('self.assertNotIn("correct_index", question)', offline_test)
        source = "\n".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for p in (ROOT / "mobile").rglob("*.ts*")
            if "node_modules" not in p.parts
        )
        self.assertNotIn("StudyRepository", source)
        self.assertNotIn("AdaptiveSessionOrchestrator", source)


if __name__ == "__main__":
    unittest.main()
