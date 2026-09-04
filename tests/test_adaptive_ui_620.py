import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AdaptiveUi620Tests(unittest.TestCase):
    def test_studio_navigation_is_grouped_and_reports_route_state(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        for label in ("Planejamento", "Banco de questões", "Aprendizagem e IA", "Rotina e sincronização", "Sistema"):
            self.assertIn(f'<p class="nav-section-label">{label}</p>', html)
        self.assertIn('id="routeProgress"', html)
        self.assertIn('id="pageStateAnnouncer"', html)

    def test_dom_runtime_is_container_aware_and_accessible(self):
        source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        for marker in (
            "function installDomRuntime()",
            "function measurePageLayout(page)",
            "page.inert = !active",
            "page.setAttribute('aria-hidden'",
            "document.documentElement.dataset.currentRoute",
            "questflow:route-ready",
            "Promise.allSettled(tasks)",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("document.documentElement.dataset.route = route", source)

    def test_each_page_uses_a_bounded_grid_track(self):
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("grid-template-columns: minmax(0, 1fr);", styles)
        self.assertIn('.page--tutor[data-layout="wide"] .tutor-layout', styles)
        self.assertIn('.page--tutor[data-layout="standard"] .tutor-workspace-panel', styles)
        self.assertIn('.page--recommend[data-layout="standard"] .stage4-grid', styles)
        self.assertIn('.page[data-layout="compact"] .settings-grid', styles)

    def test_mobile_exposes_shared_screen_and_state_components(self):
        ui = (ROOT / "mobile" / "src" / "components" / "ui.tsx").read_text(encoding="utf-8")
        self.assertIn("export function ScreenHeader", ui)
        self.assertIn("export function StatePanel", ui)
        for relative in (
            "app/(tabs)/today.tsx",
            "app/(tabs)/progress.tsx",
            "app/(tabs)/questions.tsx",
            "app/(tabs)/profile.tsx",
            "app/pair.tsx",
        ):
            source = (ROOT / "mobile" / relative).read_text(encoding="utf-8")
            self.assertIn("StatePanel", source)


if __name__ == "__main__":
    unittest.main()
