import tempfile, unittest
from pathlib import Path
from web_api import QuestFlowWebApi
from web_server import ALLOWED_API_METHODS

class AiProviderUi640Tests(unittest.TestCase):
    def test_provider_api_is_exposed(self):
        self.assertTrue({'get_ai_provider_settings','save_ai_provider_settings','test_ai_provider'} <= set(ALLOWED_API_METHODS))
    def test_default_provider_is_privacy_first_local_rag(self):
        with tempfile.TemporaryDirectory() as d:
            api=QuestFlowWebApi(database_path=Path(d)/'q.db', config_path=Path(d)/'config.json')
            data=api.get_ai_provider_settings()
            self.assertTrue(data['ok'])
            self.assertEqual(data['settings']['active_provider'],'local')
            self.assertTrue(any(p['id']=='openai' for p in data['settings']['providers']))
            self.assertTrue(any(p['id']=='gemini' for p in data['settings']['providers']))
            self.assertTrue(any(p['id']=='anthropic' for p in data['settings']['providers']))
    def test_ui_removed_static_pipeline_and_added_actionable_curation(self):
        html=(Path(__file__).parents[1]/'web'/'index.html').read_text(encoding='utf-8')
        self.assertNotIn('Esteira recomendada', html)
        self.assertIn('O que merece sua atenção agora', html)
        self.assertIn('Provedores de IA', html)
        self.assertIn('tutorQuestionSelect', html)
