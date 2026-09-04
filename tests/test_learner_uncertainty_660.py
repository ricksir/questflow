from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.learner_model import (
    counterfactual_practice_plan,
    evidence_status,
    predict_success_selective,
)
from core.schema_migrations import migration_history
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from core.engines.registry import EngineRegistry
from core.question_services import QuestionCommandService, QuestionQueryService
from web_server import ALLOWED_API_METHODS


class LearnerUncertainty660Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="qf-660-")
        self.db = QuestFlowDatabase(Path(self.tmp.name) / "q.sqlite")
        self.study = StudyRepository(self.db)
        self.uid = self.db.create_manual_question(None)
        q = self.db.get_question(self.uid); assert q
        q.update({
            "codigo_origem": "Q660-1", "id": "Q660-1",
            "materia": "DIREITO TRIBUTÁRIO", "aula_planilha": "Aula 03",
            "assunto": "Suspensão da exigibilidade", "assuntos": ["Suspensão da exigibilidade"],
            "enunciado": "Questão de teste sobre suspensão da exigibilidade.",
            "alternativas": [{"chave":"A","texto":"Certa"},{"chave":"B","texto":"Errada"}],
            "gabarito":"A", "telegram":{"indice_correto":0},
            "revisao":{"status":"aprovado","confianca":1.0,"alertas":[]},
        })
        self.db.update_question(self.uid, q)
        self.study.sync_questions()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_evidence_status_abstains_when_sample_is_small(self) -> None:
        low = evidence_status(confidence=.18, exposures=1, standard_error=2.2)
        high = evidence_status(confidence=.82, exposures=12, standard_error=.55)
        self.assertTrue(low["abstain"])
        self.assertEqual(low["status"], "evidencia_insuficiente")
        self.assertFalse(high["abstain"])
        self.assertEqual(high["status"], "estimativa_confiavel")

    def test_selective_prediction_reports_interval_and_abstention(self) -> None:
        early = predict_success_selective(
            mastery=None, mastery_confidence_value=0, retrievability=None, fsrs_reviews=0,
            theta=None, difficulty=None, discrimination=None, ability_standard_error=None,
            ability_attempts=0, item_attempts=0, historical_accuracy=.5, history_attempts=0,
        )
        mature = predict_success_selective(
            mastery=.76, mastery_confidence_value=.82, retrievability=.78, fsrs_reviews=8,
            theta=.4, difficulty=.1, discrimination=1.15, ability_standard_error=.55,
            ability_attempts=30, item_attempts=8, historical_accuracy=.74, history_attempts=20,
        )
        self.assertTrue(early.abstain)
        self.assertLess(early.confidence, .38)
        self.assertFalse(mature.abstain)
        self.assertGreater(mature.confidence, .60)
        self.assertLess(mature.interval_low, mature.probability)
        self.assertGreater(mature.interval_high, mature.probability)

    def test_counterfactual_plan_prioritizes_diagnosis_before_false_precision(self) -> None:
        weak = counterfactual_practice_plan(mastery=.42, confidence=.15, exposures=1, target_mastery=.80)
        informed = counterfactual_practice_plan(mastery=.42, confidence=.80, exposures=9, target_mastery=.80)
        self.assertEqual(weak["action"], "coletar_evidencia")
        self.assertGreaterEqual(weak["diagnostic_questions_first"], 2)
        self.assertEqual(informed["action"], "consolidar")
        self.assertIsNotNone(informed["estimated_successful_practices"])

    def test_migration_10_and_live_attempts_populate_selective_calibration(self) -> None:
        # O primeiro contato deve ser abstido; após várias respostas o modelo
        # começa a aceitar previsões e a calibração seletiva passa a ter amostra.
        pattern = [0, 1, 0, 0, 1, 0, 0, 0, 1, 0]
        for idx in pattern:
            self.study.record_local_practice_attempt(self.uid, idx, source="test_660")
        with self.db.connect() as connection:
            versions = [int(row["version"]) for row in migration_history(connection) if row["component"] == "study"]
            rows = connection.execute(
                "SELECT learner_predicted_probability,learner_prediction_confidence,learner_prediction_status FROM telegram_attempts ORDER BY answered_at,id"
            ).fetchall()
        self.assertEqual(max(versions), 12)
        self.assertEqual(len(rows), len(pattern))
        self.assertTrue(all(row["learner_predicted_probability"] is not None for row in rows))
        statuses = [str(row["learner_prediction_status"]) for row in rows]
        self.assertIn("evidencia_insuficiente", statuses)
        self.assertTrue(any(status != "evidencia_insuficiente" for status in statuses))
        report = self.study.calibration_report(source="learner")
        self.assertEqual(report["samples"], len(pattern))
        self.assertGreater(report["accepted_samples"], 0)
        self.assertIn("brier", report["selective"])
        self.assertIn("expected_calibration_error", report["selective"])

    def test_dashboard_exposes_abstention_calibration_and_counterfactual_plan(self) -> None:
        for idx in [1, 0, 1, 0]:
            self.study.record_local_practice_attempt(self.uid, idx, source="test_660_dashboard")
        model = self.study.learner_model_dashboard()
        self.assertEqual(model["version"], "qf-learner-2")
        self.assertIn("abstained_concepts", model)
        self.assertIn("calibration", model)
        self.assertIn("counterfactual_plan", model)
        self.assertIn("decision_rule", model)
        state = self.study.question_learning_state(self.uid)
        self.assertIn("evidence", state)

    def test_historical_engines_remain_available_and_registry_is_extensible(self) -> None:
        queries = QuestionQueryService(self.db)
        commands = QuestionCommandService(self.db)
        engines = EngineRegistry.build(database=self.db, queries=queries, commands=commands, study=self.study)
        architecture = engines.architecture()
        self.assertGreaterEqual(architecture["engine_count"], 6)
        self.assertTrue(architecture["extensible"])
        learner = next(item for item in architecture["engines"] if item["id"] == "learner_model")
        self.assertEqual(learner["version"], "qf-learner-engine-4")
        self.assertIn("selective_prediction", architecture["principles"])
        self.assertIn("get_counterfactual_learning_plan", ALLOWED_API_METHODS)


if __name__ == "__main__":
    unittest.main()
