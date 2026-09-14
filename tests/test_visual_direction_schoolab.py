import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SchoolabAprovaCheckmateUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        cls.script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        cls.theme = (ROOT / "web" / "questflow-schoolab.css").read_text(encoding="utf-8")
        cls.version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()

    def test_reference_theme_is_loaded_after_legacy_styles(self):
        legacy = self.html.index('questflow622.css')
        theme = self.html.index('questflow-schoolab.css')
        self.assertLess(legacy, theme)
        self.assertIn('#fbfaf6', self.theme.lower())
        self.assertIn('#f3b54a', self.theme.lower())
        self.assertIn('#21b89a', self.theme.lower())
        self.assertIn('#1d223b', self.theme.lower())

    def test_dashboard_is_action_first(self):
        pulse = self.html.index('id="learningPulsePanel"')
        today = self.html.index('id="todayPanel"')
        metrics = self.html.index('id="metricGrid"')
        self.assertLess(pulse, today)
        self.assertLess(today, metrics)
        self.assertIn('Seu foco agora', self.html)
        self.assertIn('Seu estudo de hoje', self.html)

    def test_next_best_action_opens_recommender(self):
        self.assertIn('Abrir sessão recomendada', self.script)
        self.assertIn("navigate('recommend')", self.script)

    def test_checkmate_analytics_bento_is_decision_first(self):
        self.assertIn('Analytics de estudo', self.html)
        self.assertIn('Seu aprendizado em números', self.html)
        trend = self.script.index('data-analytics-info="trend"')
        insights = self.script.index('data-analytics-info="insights"', trend)
        compare = self.script.index('data-analytics-info="compare"', insights)
        summary = self.script.index('data-analytics-info="summary"', compare)
        self.assertLess(trend, insights)
        self.assertLess(insights, compare)
        self.assertLess(compare, summary)
        self.assertIn('analytics-card__kicker', self.script)
        self.assertIn('--chart-accent-1: var(--qf-gold-500)', self.theme)
        self.assertIn('#visualAnalyticsPanel .analytics-hero-card', self.theme)
        self.assertIn('Horizonte de revisões', self.script)
        self.assertIn('analytics-memory-horizon', self.script)
        self.assertIn('.analytics-memory-horizon', self.theme)

    def test_visual_work_does_not_bump_release(self):
        self.assertEqual(self.version, '6.24.0')


if __name__ == "__main__":
    unittest.main()
