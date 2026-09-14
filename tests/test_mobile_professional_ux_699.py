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

    def test_profile_is_study_only_and_does_not_surface_technical_diagnostics(self):
        profile = (self.root / "mobile" / "app" / "(tabs)" / "profile.tsx").read_text(encoding="utf-8")
        self.assertIn("MEU ESTUDO", profile)
        self.assertIn("Revisões hoje", profile)
        for technical in ("Diagnóstico técnico", "diagnosticsOpen", "Studio local", "Cloud Bridge", "Endpoint", "Cursor", "Saúde da IA", "Telegram", "Entrega de questões"):
            self.assertNotIn(technical, profile)

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
