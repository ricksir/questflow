from __future__ import annotations

import unittest
from pathlib import Path


class MobileProfessionalUX699Tests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]

    def test_android_bottom_navigation_respects_safe_area(self):
        layout = (self.root / "mobile" / "app" / "(tabs)" / "_layout.tsx").read_text(encoding="utf-8")
        root_layout = (self.root / "mobile" / "app" / "_layout.tsx").read_text(encoding="utf-8")
        self.assertIn("useSafeAreaInsets", layout)
        self.assertIn("Math.max(insets.bottom, Platform.OS === 'android' ? 28 : 10)", layout)
        self.assertIn("paddingBottom: bottom", layout)
        self.assertIn("SafeAreaProvider", root_layout)

    def test_today_uses_performance_visual_instead_of_telegram_controls(self):
        today = (self.root / "mobile" / "app" / "(tabs)" / "today.tsx").read_text(encoding="utf-8")
        self.assertIn("Seu desempenho", today)
        self.assertIn("Acerto por matéria", today)
        self.assertIn("splitCorrect", today)
        self.assertIn('slice(0, 3)', today)
        self.assertIn("Ver progresso completo", today)
        self.assertNotIn("ReviewQueuePreview", today)
        self.assertNotIn("TrendLineChart", today)
        self.assertNotIn("Últimas respostas", today)
        self.assertNotIn("Retomar questões no Telegram", today)
        self.assertNotIn("Pausar questões no Telegram", today)

    def test_running_question_explains_selection_without_technical_noise(self):
        questions = (self.root / "mobile" / "app" / "(tabs)" / "questions.tsx").read_text(encoding="utf-8")
        self.assertIn("POR QUE ESTA QUESTÃO?", questions)
        self.assertIn("current.selection?.reason", questions)
        self.assertIn("selectionReasonLabel(current.selection.reason)", questions)
        self.assertIn("transferReasonLabel(current.selection.transfer_reason)", questions)
        self.assertIn("Você errou esta questão antes", questions)
        self.assertIn("chegou ao momento de revisão", questions)
        self.assertIn("QuestFlow explica", questions)
        self.assertIn("current.selection.topic_transfer", questions)
        self.assertNotIn("Estratégia:", questions)
        self.assertNotIn("Plano ", questions)

    def test_result_coach_uses_correctness_and_confidence_without_fake_metrics(self):
        questions = (self.root / "mobile" / "app" / "(tabs)" / "questions.tsx").read_text(encoding="utf-8")
        self.assertIn("function resultCoach", questions)
        self.assertIn("ERRO DE ALTA CONFIANÇA", questions)
        self.assertIn("ACERTO FRÁGIL", questions)
        self.assertIn("DOMÍNIO CONSISTENTE", questions)
        self.assertIn("RESULTADO PROVISÓRIO", questions)
        self.assertEqual(questions.count("RESULTADO PROVISÓRIO"), 1)
        self.assertNotIn("Feedback provisório disponível.", questions)
        self.assertIn("feedback.is_correct && confidence === 'high'", questions)
        self.assertIn("!feedback.is_correct && confidence === 'high'", questions)
        self.assertIn("coach ? (", questions)
        self.assertNotIn("QuestFlow Score", questions)

    def test_profile_is_study_only_and_does_not_surface_technical_diagnostics(self):
        profile = (self.root / "mobile" / "app" / "(tabs)" / "profile.tsx").read_text(encoding="utf-8")
        self.assertIn("MEU ESTUDO", profile)
        self.assertIn("Revisões hoje", profile)
        for technical in ("Diagnóstico técnico", "diagnosticsOpen", "Studio local", "Cloud Bridge", "Endpoint", "Cursor", "Saúde da IA", "Telegram", "Entrega de questões", "Contrato de dados"):
            self.assertNotIn(technical, profile)

    def test_shared_mobile_actions_keep_accessible_touch_targets(self):
        ui = (self.root / "mobile" / "src" / "components" / "ui.tsx").read_text(encoding="utf-8")
        self.assertIn('accessibilityState={{ disabled: Boolean(disabled) }}', ui)
        self.assertIn("stateAction: { minHeight: 44", ui)
        self.assertIn("button: { borderRadius: 16, minHeight: 50", ui)
        self.assertIn("flexWrap: 'wrap'", ui)
        self.assertIn("screenHeaderCopy: { flex: 1, minWidth: 210", ui)

    def test_progress_priority_cards_expose_expand_state(self):
        progress = (self.root / "mobile" / "app" / "(tabs)" / "progress.tsx").read_text(encoding="utf-8")
        self.assertIn('accessibilityRole="button"', progress)
        self.assertIn('accessibilityState={{ expanded: open }}', progress)
        self.assertIn('accessibilityHint={open ?', progress)
        self.assertIn("rankBadgeText: { color: palette.primaryDeep", progress)

    def test_studio_has_dedicated_mobile_navigation_and_page(self):
        html = (self.root / "web" / "index.html").read_text(encoding="utf-8")
        js = (self.root / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-route="mobile"', html)
        self.assertIn('data-page="mobile"', html)
        self.assertIn("QuestFlow Mobile", html)
        self.assertIn("Conectar novo aparelho", html)
        self.assertIn("mobile: 'QuestFlow Mobile'", js)
        self.assertIn("route === 'mobile'", js)

    def test_mobile_lan_control_moved_to_mobile_page(self):
        html = (self.root / "web" / "index.html").read_text(encoding="utf-8")
        mobile_pos = html.index('data-page="mobile"')
        settings_pos = html.index('data-page="settings"')
        lan_pos = html.index('id="mobileLanEnabled"')
        self.assertGreater(lan_pos, mobile_pos)
        self.assertLess(lan_pos, settings_pos)
        self.assertEqual(html.count('id="mobileLanEnabled"'), 1)


if __name__ == "__main__":
    unittest.main()
