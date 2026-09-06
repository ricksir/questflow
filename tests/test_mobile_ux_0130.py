from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile" if (ROOT / "mobile").exists() else ROOT.parent / "mobile"


class MobileUx0130Tests(unittest.TestCase):
    def test_offline_saved_state_has_no_indefinite_feedback_spinner(self) -> None:
        source = (MOBILE / "app" / "(tabs)" / "questions.tsx").read_text(encoding="utf-8")
        self.assertIn("setAwaitingFeedback(!offlineOrigin)", source)
        self.assertIn("setAwaitingFeedback(false);", source)
        self.assertIn("Não há conexão em andamento", source)

    def test_struck_option_is_visually_explicit(self) -> None:
        source = (MOBILE / "app" / "(tabs)" / "questions.tsx").read_text(encoding="utf-8")
        for marker in ("ALTERNATIVA ELIMINADA", "optionBadgeStruck", "optionEliminatedLabel", "textDecorationColor: palette.danger"):
            self.assertIn(marker, source)

    def test_offline_session_summary_counts_answered_without_fake_accuracy(self) -> None:
        source = (MOBILE / "app" / "(tabs)" / "questions.tsx").read_text(encoding="utf-8")
        self.assertIn("const pendingResults = Math.max(0, Number(summary.stats.pending_results || 0));", source)
        self.assertIn("const awaitingOnly = accuracy == null", source)
        self.assertIn("questões respondidas nesta sessão", source)
        self.assertIn("Aguardando correção", source)
        self.assertIn("Resultado pendente de sincronização", source)
        self.assertNotIn("{accuracy == null ? '—' : `${Math.round(accuracy * 100)}%`}", source)

    def test_mobile_version_is_0130(self) -> None:
        self.assertIn('"version": "0.16.0"', (MOBILE / "package.json").read_text(encoding="utf-8"))
        self.assertIn("MOBILE_APP_VERSION = '0.16.0'", (MOBILE / "src" / "lib" / "config.ts").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
