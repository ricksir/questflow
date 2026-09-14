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
        quest_ai = self.html.index('id="questAiInsightPanel"')
        metrics = self.html.index('id="metricGrid"')
        self.assertLess(pulse, today)
        self.assertLess(today, quest_ai)
        self.assertLess(quest_ai, metrics)
        self.assertIn('Seu foco agora', self.html)
        self.assertIn('Seu estudo de hoje', self.html)

    def test_next_best_action_opens_recommender(self):
        self.assertIn('Abrir sessão recomendada', self.script)
        self.assertIn("navigate('recommend')", self.script)

    def test_contextual_quest_ai_uses_real_learning_signals(self):
        self.assertIn('id="questAiInsightPanel"', self.html)
        self.assertIn('Quest AI · insight contextual', self.html)
        self.assertIn('function renderQuestAiInsightPanel(data)', self.script)
        self.assertIn('analyticsBuildContext(data)', self.script)
        self.assertIn('Desempenho recente', self.script)
        self.assertIn('Retenção estimada', self.script)
        self.assertIn('Cobertura estudada', self.script)
        self.assertIn("data-quest-ai-study", self.script)
        self.assertIn("data-quest-ai-tutor", self.script)
        self.assertIn("data-quest-ai-analytics", self.script)
        self.assertIn('.quest-ai-insight-grid', self.theme)
        self.assertIn('#recentActivity .data-table-wrap', self.theme)
        self.assertIn('Histórico operacional', self.html)
        self.assertNotIn('QuestFlow Score', self.script)

    def test_recommender_uses_student_facing_next_action_language(self):
        self.assertIn('Próxima melhor ação', self.html)
        self.assertIn('id="recommendTitle">O que estudar agora', self.html)
        self.assertIn('Revisões urgentes vêm primeiro', self.html)
        self.assertIn("function stage4UrgencyLabel", self.script)
        self.assertIn("'Recuperar agora'", self.script)
        self.assertIn("'Revisar agora'", self.script)
        self.assertIn("mastery_gap: 'Domínio'", self.script)
        self.assertIn("forgetting_risk: 'Memória'", self.script)
        self.assertIn('.page[data-page="recommend"] .stage4-recommendations-panel', self.theme)

    def test_visual_layer_respects_keyboard_and_reduced_motion(self):
        self.assertIn(':focus-visible', self.theme)
        self.assertIn('outline: 3px solid var(--focus-ring)', self.theme)
        self.assertIn('@media (prefers-reduced-motion: reduce)', self.theme)
        self.assertIn('animation-duration: .001ms !important', self.theme)
        self.assertIn('transition-duration: .001ms !important', self.theme)

    def test_quest_ai_can_handoff_context_to_tutor_without_auto_generation(self):
        self.assertIn("function openQuestAiInsightInTutor", self.script)
        self.assertIn("Levar insight ao Tutor", self.script)
        self.assertIn("await navigate('tutor')", self.script)
        self.assertIn("field.value = prompt", self.script)
        self.assertIn("field.dispatchEvent(new Event('change'", self.script)
        self.assertIn("Use a questão que eu selecionar como contexto", self.script)
        self.assertIn("Não invente métricas ou fatos", self.script)
        handoff = self.script.split("async function openQuestAiInsightInTutor", 1)[1].split("function renderQuestAiInsightPanel", 1)[0]
        self.assertNotIn("generateTutorAnswer(", handoff)

    def test_tutor_has_contextual_quick_actions(self):
        self.assertIn('data-tutor-quick-prompt', self.html)
        self.assertIn('Explique ultra-fácil', self.html)
        self.assertIn('Por que eu errei?', self.html)
        self.assertIn('Pegadinha da banca', self.html)
        self.assertIn("button.dataset.tutorQuickPrompt", self.script)
        self.assertIn("field.dispatchEvent(new Event('change'", self.script)
        self.assertIn('.tutor-quick-prompts', self.theme)

    def test_mobile_studio_uses_shared_schoolab_visual_language(self):
        self.assertIn('class="page mobile-studio-page"', self.html)
        self.assertIn('.mobile-studio-page {', self.theme)
        self.assertIn('--mobile-blue: var(--qf-sky-500)', self.theme)
        self.assertIn('--mobile-cyan: var(--qf-teal-500)', self.theme)
        self.assertIn('--mobile-violet: var(--qf-gold-500)', self.theme)
        self.assertIn('.mobile-studio-page .mobile-studio-hero', self.theme)
        self.assertIn('.mobile-studio-page .mobile-foundation-metric::before', self.theme)
        self.assertIn('.mobile-studio-page .mobile-cloud-advanced', self.theme)
        self.assertIn('html[data-theme="dark"] .mobile-studio-page .mobile-studio-hero', self.theme)

    def test_question_bank_uses_schoolab_review_hierarchy(self):
        self.assertIn('Curadoria de questões', self.html)
        self.assertIn('Ferramentas avançadas do banco de questões', self.html)
        self.assertIn('Qualidade avançada', self.html)
        self.assertIn('Selecione uma questão para revisar', self.html)
        self.assertIn('.page[data-page="review"] .review-toolbar', self.theme)
        self.assertIn('.page[data-page="review"] .question-list-panel', self.theme)
        self.assertIn('.page[data-page="review"] .virtual-row.is-selected', self.theme)
        self.assertIn('.page[data-page="review"] .question-editor', self.theme)
        self.assertIn('.page[data-page="review"] .question-intelligence-section', self.theme)

    def test_corrections_triage_uses_schoolab_semantics(self):
        self.assertIn('data-page="corrections"', self.html)
        self.assertIn('Correções e Matérias não Estudadas', self.html)
        self.assertIn('.page[data-page="corrections"] .corrections-overview article', self.theme)
        self.assertIn('.page[data-page="corrections"] .corrections-section--editorial', self.theme)
        self.assertIn('.page[data-page="corrections"] .corrections-section--study', self.theme)
        self.assertIn('.not-studied-modal .not-studied-callout', self.theme)
        self.assertIn('.not-studied-modal .not-studied-guidance', self.theme)
        self.assertIn("color: #8b651b !important", self.theme)

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
