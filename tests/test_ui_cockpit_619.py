import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class QuestFlowCockpit619Tests(unittest.TestCase):
    def test_studio_exposes_learning_pulse(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn('id="learningPulsePanel"', html)
        self.assertIn("renderLearningPulsePanel(data)", script)
        self.assertIn(".slice(0, 4)", script)
        self.assertIn("const priorityFocus", script)
        self.assertIn("const visibleFocus = focusSubjects.slice(0, 4)", script)
        self.assertIn("hiddenFocusCount", script)
        self.assertIn("data-pulse-all", script)
        self.assertIn("openFocusSubjectsModal(context)", script)
        self.assertIn("focusSubjectSearch", script)
        self.assertIn("focusPriorityFilter", script)
        self.assertIn("focusSubjects.length", script)
        self.assertNotIn("${context.highPriority + context.mediumPriority} em foco", script)
        self.assertIn("learning-pulse-grid", styles)

    def test_mobile_uses_shared_pulse_components(self):
        ui = (ROOT / "mobile" / "src" / "components" / "ui.tsx").read_text(encoding="utf-8")
        today = (ROOT / "mobile" / "app" / "(tabs)" / "today.tsx").read_text(encoding="utf-8")
        progress = (ROOT / "mobile" / "app" / "(tabs)" / "progress.tsx").read_text(encoding="utf-8")
        self.assertIn("export function StatRing", ui)
        self.assertIn("export function MicroBars", ui)
        self.assertIn("<StatRing", today)
        self.assertIn("<MicroBars", progress)

    def test_mobile_release_and_brand_tokens_are_consistent(self):
        app = json.loads((ROOT / "mobile" / "app.json").read_text(encoding="utf-8"))
        package = json.loads((ROOT / "mobile" / "package.json").read_text(encoding="utf-8"))
        palette = (ROOT / "mobile" / "src" / "components" / "ui.tsx").read_text(encoding="utf-8")
        self.assertEqual(app["expo"]["version"], "0.15.6")
        self.assertEqual(package["version"], "0.15.6")
        self.assertEqual(app["expo"]["primaryColor"], "#FF7A18")
        self.assertIn("primary: '#FF7A18'", palette)


if __name__ == "__main__":
    unittest.main()
