import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8')
JS = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
SERVER = (ROOT / 'web_server.py').read_text(encoding='utf-8')

class RoadmapUiAudit683Hotfix1(unittest.TestCase):
    def test_global_rag_tools_are_top_level(self):
        strip = re.search(r'<div class="roadmap-tools-strip.*?</div>\s*</div>', HTML, re.S)
        self.assertIsNotNone(strip)
        block = strip.group(0)
        for control in ('openGroundingBenchmark','openRetrievalCalibration','openRetrievalObservability'):
            self.assertIn(f'id="{control}"', block)

    def test_contextual_tools_visible_but_disabled_without_question(self):
        for control in ('showAiBrief','showKnowledgeGraph','showHybridEvidence'):
            self.assertRegex(HTML, rf'id="{control}"[^>]*disabled')
            self.assertIn(control, JS)
        self.assertIn("'#showHybridEvidence'", JS)
        self.assertIn('element.disabled = !active', JS)

    def test_roadmap_buttons_have_handlers(self):
        bindings = {
            'openGroundingBenchmark': 'openGroundingBenchmark',
            'openRetrievalCalibration': 'openRetrievalCalibration',
            'openRetrievalObservability': 'openRetrievalObservability',
            'showAiBrief': 'showAiCommentaryBrief',
            'showKnowledgeGraph': 'showKnowledgeGraph',
            'showHybridEvidence': 'showHybridEvidence',
            'researchGoogleCommentary': 'researchCommentaryOnGoogle',
        }
        for control, handler in bindings.items():
            self.assertIn(f"$('#{control}')", JS)
            self.assertIn(handler, JS)

    def test_backend_methods_are_http_allowed(self):
        methods = (
            'run_multimodal_grounding_benchmark',
            'run_retrieval_calibration',
            'apply_retrieval_calibration',
            'rollback_retrieval_calibration',
            'save_retrieval_regression_baseline',
            'get_retrieval_regression_status',
            'get_retrieval_observability',
            'record_retrieval_observability',
            'suggest_gold_question_expansion',
            'export_retrieval_observability_report',
            'start_google_commentary_research',
            'get_evidence_collection_plan',
            'start_evidence_collection',
            'restart_runtime_service',
        )
        for method in methods:
            self.assertIn(f'"{method}"', SERVER)

    def test_conditional_actions_do_not_disappear(self):
        self.assertIn('id="applyRecommendedRetrieval" disabled', JS)
        self.assertIn('id="startEvidencePractice" disabled', JS)

    def test_every_static_html_button_id_is_referenced_by_js(self):
        ids = re.findall(r'<button\b[^>]*\bid="([^"]+)"', HTML, re.I)
        missing = [button_id for button_id in ids if button_id not in JS]
        self.assertEqual(missing, [], f'Botões sem referência JS: {missing}')

if __name__ == '__main__':
    unittest.main()
