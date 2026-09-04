from __future__ import annotations

import hashlib
import tempfile
import time
import unittest
from pathlib import Path

from app_shared import TAXONOMY_PATH
from core.storage import QuestFlowDatabase
from web_api import QuestFlowWebApi


class StartupResponsivenessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "questions.sqlite"
        database = QuestFlowDatabase(self.db_path)
        questions = []
        for index in range(25):
            code = f"QFAST{index:03d}"
            questions.append(
                {
                    "id": code,
                    "codigo_origem": code,
                    "fingerprint": hashlib.sha256(code.encode()).hexdigest(),
                    "materia": "AUDITORIA" if index % 2 else "DIREITO TRIBUTÁRIO",
                    "aula_planilha": f"Aula {index % 5:02d}",
                    "assunto": "TESTE DE DESEMPENHO",
                    "assuntos": ["TESTE DE DESEMPENHO"],
                    "banca": "FGV",
                    "ano": 2026,
                    "orgao": "SEFAZ",
                    "tipo": "multipla_escolha",
                    "enunciado": f"Questão sintética {index}",
                    "alternativas": [
                        {"chave": "A", "texto": "A"},
                        {"chave": "B", "texto": "B"},
                    ],
                    "gabarito": "A",
                    "revisao": {"status": "aprovado", "alertas": []},
                }
            )
        database.import_extraction({"source_file": "startup.pdf", "questions": questions})
        self.api = QuestFlowWebApi(
            self.db_path,
            config={"flow_target_retention": 0.88},
            config_path=self.root / "config.json",
            taxonomy_path=TAXONOMY_PATH,
        )

    def tearDown(self) -> None:
        self.api.shutdown()
        self.temp.cleanup()

    def test_shell_bootstrap_does_not_scan_study_tables(self) -> None:
        self.assertFalse(self.api._core_ready.is_set())
        started = time.perf_counter()
        payload = self.api.bootstrap_shell()
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 0.2)
        self.assertTrue(payload["deferred"])
        self.assertEqual(payload["stats"], {})
        self.assertFalse(self.api._core_ready.is_set())

    def test_dashboard_runs_as_background_task(self) -> None:
        started = time.perf_counter()
        task = self.api.start_dashboard_load()
        self.assertLess(time.perf_counter() - started, 0.2)
        self.assertTrue(task["ok"])
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = self.api.poll_task(task["task_id"])
            if status["status"] == "done":
                self.assertEqual(status["result"]["question_stats"]["total"], 25)
                return
            if status["status"] == "error":
                self.fail(status.get("error"))
            time.sleep(0.02)
        self.fail("dashboard task did not finish")

    def test_start_services_returns_immediately(self) -> None:
        started = time.perf_counter()
        self.api.start_services()
        self.assertLess(time.perf_counter() - started, 0.2)

    def test_question_list_uses_real_sql_pagination(self) -> None:
        first = self.api.list_questions(offset=0, limit=10)
        second = self.api.list_questions(offset=10, limit=10)
        self.assertEqual(first["total"], 25)
        self.assertEqual(second["total"], 25)
        self.assertEqual(len(first["items"]), 10)
        self.assertEqual(len(second["items"]), 10)
        self.assertTrue({item["uid"] for item in first["items"]}.isdisjoint({item["uid"] for item in second["items"]}))


if __name__ == "__main__":
    unittest.main()
