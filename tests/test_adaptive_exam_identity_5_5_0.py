from __future__ import annotations

import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


class AdaptiveExamIdentity550Tests(unittest.TestCase):
    def test_light_dark_exam_assets_exist_and_are_original_svg(self) -> None:
        assets = BASE / "web" / "assets"
        for mode in ("light", "dark"):
            svg = assets / f"questflow_exam_{mode}.svg"
            self.assertTrue(svg.is_file())
            text = svg.read_text(encoding="utf-8")
            self.assertIn("BANCO DE QUESTÕES", text)
            self.assertIn("Questão de alto nível", text)
            self.assertIn("MAPA DE AULAS", text)
            self.assertIn("DESEMPENHO", text)

    def test_web_switches_identity_with_manual_and_system_theme(self) -> None:
        html = (BASE / "web" / "index.html").read_text(encoding="utf-8")
        css = (BASE / "web" / "styles.css").read_text(encoding="utf-8")
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('theme-art--light', html)
        self.assertIn('theme-art--dark', html)
        self.assertIn('[data-theme="dark"] .theme-art--light', css)
        self.assertIn('html[data-theme="system"] .theme-art--dark', css)
        self.assertIn('resolvedThemeIsDark', js)
        self.assertIn('updateThemeIdentity', js)
        self.assertIn('prefers-color-scheme: dark', js)

    def test_favicon_and_browser_theme_color_follow_resolved_theme(self) -> None:
        html = (BASE / "web" / "index.html").read_text(encoding="utf-8")
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="appFavicon"', html)
        self.assertIn('id="themeColorMeta"', html)
        self.assertIn("art.favicon", js)
        self.assertIn("meta.content", js)

    def test_interface_copy_reinforces_question_bank_identity(self) -> None:
        html = (BASE / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Banco inteligente de questões", html)
        self.assertIn("Curadoria de questões", html)
        self.assertIn("Questões de alto nível", html)


if __name__ == "__main__":
    unittest.main()
