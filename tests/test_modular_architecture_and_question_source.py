from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from app_shared import TAXONOMY_PATH
from core.architecture import DomainEvent, SelectiveEventStore
from core.modules.question_catalog import ApiDasQuestoesAdapter, normalize_api_question
from core.storage import QuestFlowDatabase
from web_api import QuestFlowWebApi
from web_server import QuestFlowLocalServer


class _FakeResponse:
    def __init__(self, payload: object, headers: dict[str, str] | None = None) -> None:
        self._payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._payload


class ModularArchitectureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "questflow.sqlite"
        self.api = QuestFlowWebApi(
            self.db_path,
            config={},
            config_path=self.root / "config.json",
            taxonomy_path=TAXONOMY_PATH,
        )
        self.api.bootstrap()

    def tearDown(self) -> None:
        self.api.shutdown()
        self.temp.cleanup()

    def test_modular_kernel_has_extensible_modules_and_complete_table_ownership(self) -> None:
        envelope = self.api.get_engine_architecture()
        self.assertTrue(envelope["ok"])
        architecture = envelope["architecture"]
        self.assertEqual(architecture["schema"], "questflow.architecture.v3")
        self.assertEqual(architecture["architecture"], "modular_monolith_hexagonal")
        self.assertTrue(architecture["database"]["table_ownership_explicit"])
        self.assertEqual(architecture["database"]["unknown_tables"], [])
        self.assertGreater(architecture["modules"]["module_count"], 6)
        self.assertTrue(architecture["modules"]["extensible"])
        self.assertTrue(architecture["domain_engines"]["extensible"])
        self.assertNotIn("exactly_six", architecture["principles"])

    def test_selective_event_store_rejects_editorial_aggregate(self) -> None:
        store = SelectiveEventStore(QuestFlowDatabase(self.db_path))
        created = store.append("attempt", "attempt-1", "attempt.recorded", {"correct": True})
        self.assertEqual(created["version"], 1)
        self.assertEqual(store.read("attempt", "attempt-1")[0]["payload"], {"correct": True})
        with self.assertRaises(ValueError):
            store.append("question", "question-1", "question.updated", {})

    def test_internal_event_is_durable_and_captured_by_existing_sync_outbox(self) -> None:
        assert self.api.architecture_kernel is not None
        event = self.api.architecture_kernel.events.publish(DomainEvent(
            event_type="learning.projection.requested",
            module="learning",
            aggregate_type="projection",
            aggregate_id="learning.analytics",
            payload={"reason": "test"},
        ))
        with QuestFlowDatabase(self.db_path).connect() as connection:
            row = connection.execute(
                "SELECT dispatch_status,payload_json FROM qf_internal_events WHERE event_id=?",
                (event.event_id,),
            ).fetchone()
            outbox = connection.execute(
                "SELECT operation FROM qf_sync_outbox WHERE table_name='qf_internal_events' AND row_key LIKE ?",
                (f'%{event.event_id}%',),
            ).fetchone()
        self.assertEqual(row["dispatch_status"], "dispatched")
        self.assertEqual(json.loads(row["payload_json"]), {"reason": "test"})
        self.assertIsNotNone(outbox)
        self.assertEqual(outbox["operation"], "upsert")

        # Um efeito real entre módulos: mudança editorial reconstrói a projeção
        # de analytics pertencente ao módulo learning.
        self.api.architecture_kernel.events.publish(DomainEvent(
            event_type="editorial.question.changed",
            module="editorial_bank",
            aggregate_type="question",
            aggregate_id="question-1",
            payload={"question_uid": "question-1"},
        ))
        with QuestFlowDatabase(self.db_path).connect() as connection:
            checkpoint = connection.execute(
                "SELECT status FROM qf_projection_checkpoints WHERE projection_name='learning.analytics'"
            ).fetchone()
        self.assertEqual(checkpoint["status"], "ready")

    def test_studio_v1_contract_dispatches_versioned_use_cases(self) -> None:
        contract = self.api.get_studio_contract_v1()
        self.assertTrue(contract["ok"])
        self.assertEqual(contract["contract"], "questflow.studio.v1")
        operation_names = {item["name"] for item in contract["operations"]}
        self.assertIn("questions.list", operation_names)
        result = self.api.dispatch_studio_v1("questions.list", {"limit": 10})
        self.assertTrue(result["ok"])
        self.assertEqual(result["contract"], "questflow.studio.v1")
        self.assertEqual(result["module"], "editorial_bank")
        self.assertEqual(result["data"]["meta"]["provider"], "local")

    def test_http_studio_v1_requires_session_token_and_serves_typed_modules(self) -> None:
        server = QuestFlowLocalServer(
            self.api,
            Path(__file__).resolve().parents[1] / "web",
            preferred_port=0,
        )
        server.start()
        try:
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(f"{server.base_url}/api/v1/studio/contract", timeout=5)
            self.assertEqual(denied.exception.code, 401)
            denied.exception.close()

            request = urllib.request.Request(
                f"{server.base_url}/api/v1/studio/contract",
                headers={"X-QuestFlow-Token": server.token},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["contract"], "questflow.studio.v1")

            with urllib.request.urlopen(f"{server.base_url}/modules/bootstrap.js", timeout=5) as response:
                frontend = response.read().decode("utf-8")
            self.assertIn("typed-route-modules-v1", frontend)
        finally:
            server.stop()

    def test_fsrs_kt_irt_and_analytics_are_declared_rebuildable(self) -> None:
        architecture = self.api.get_engine_architecture()["architecture"]
        names = {item["projection_name"] for item in architecture["projections"]["items"]}
        self.assertEqual(names, {"learner.fsrs_kt_irt", "learning.analytics"})
        result = self.api.rebuild_learning_projections("learning.analytics")
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["name"], "learning.analytics")

    def test_external_api_key_is_kept_out_of_config_and_protected_by_dpapi(self) -> None:
        result = self.api.save_question_source_settings({
            "provider": "api_das_questoes",
            "api_key": "chave-super-secreta",
            "base_url": "https://api.apidasquestoes.com.br/api/v1",
            "timeout_seconds": 15,
        })
        self.assertTrue(result["ok"])
        self.assertTrue(result["settings"]["api_das_questoes"]["api_key_configured"])
        config_text = (self.root / "config.json").read_text(encoding="utf-8")
        self.assertNotIn("chave-super-secreta", config_text)
        envelope_text = (self.root / "api_das_questoes_credentials.dat").read_text(encoding="utf-8")
        self.assertNotIn("chave-super-secreta", envelope_text)
        self.assertEqual(json.loads(envelope_text)["protection"], "windows-dpapi")


class ApiDasQuestoesAdapterTests(unittest.TestCase):
    SAMPLE = {
        "id": 321,
        "externalId": "9981",
        "enunciado": "<p>Qual é a <strong>resposta</strong>?</p><img src='https://img/q.png' alt='gráfico'>",
        "nomeProva": "Prova exemplo",
        "ano": 2025,
        "dificuldade": "MEDIA",
        "nivel": "SUPERIOR",
        "resposta": "B",
        "materia": {"id": 1, "label": "Direito"},
        "topico": {"id": 2, "label": "Constitucional"},
        "banca": {"id": 3, "label": "FGV"},
        "instituicao": {"id": 4, "label": "SEFAZ"},
        "options": [
            {"key": "A", "text": "<p>Primeira</p>"},
            {"key": "B", "text": "<em>Segunda</em>"},
        ],
    }

    def test_normalizer_preserves_current_shape_and_marks_external_read_only(self) -> None:
        question = normalize_api_question(self.SAMPLE)
        self.assertEqual(question["database_uid"], "api_das_questoes:321")
        self.assertEqual(question["codigo_origem"], "Q9981")
        self.assertEqual(question["materia"], "Direito")
        self.assertEqual(question["assunto"], "Constitucional")
        self.assertEqual(question["gabarito"], "B")
        self.assertEqual(question["alternativas"][1], {"chave": "B", "texto": "Segunda"})
        self.assertIn("Qual é a resposta?", question["enunciado"])
        self.assertTrue(question["external_read_only"])
        self.assertTrue(question["imagem_questao"]["remote"])

    def test_adapter_uses_server_side_key_filters_and_quota_headers(self) -> None:
        requests: list[object] = []

        def transport(request, _timeout):
            requests.append(request)
            return _FakeResponse(
                {"content": [self.SAMPLE], "totalElements": 1, "page": 0, "size": 20, "totalPages": 1},
                {"X-RateLimit-Remaining": "119", "X-Plano": "teste"},
            )

        adapter = ApiDasQuestoesAdapter(api_key="segredo", transport=transport)
        total, items, meta = adapter.page(search="constituição", limit=20, filters={"ano": 2025})
        request = requests[0]
        query = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
        self.assertEqual(request.get_header("X-api-key"), "segredo")
        self.assertEqual(query["q"], ["constituição"])
        self.assertEqual(query["ano"], ["2025"])
        self.assertEqual(total, 1)
        self.assertEqual(items[0]["uid"], "api_das_questoes:321")
        self.assertEqual(meta["quota"]["remaining"], "119")
        self.assertEqual(meta["quota"]["plan"], "teste")

    def test_public_subject_labels_are_normalized_for_the_internal_port(self) -> None:
        def transport(_request, _timeout):
            return _FakeResponse([{"id": 4, "label": "Direito Administrativo", "topics": []}])

        adapter = ApiDasQuestoesAdapter(api_key="", transport=transport)
        self.assertEqual(adapter.subjects()[0]["nome"], "Direito Administrativo")

    def test_adapter_aggregates_official_pages_for_the_existing_virtual_list(self) -> None:
        requested_pages: list[int] = []

        def transport(request, _timeout):
            page = int(urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)["page"][0])
            requested_pages.append(page)
            count = 100 if page == 0 else 50
            rows = [{**self.SAMPLE, "id": page * 100 + index + 1} for index in range(count)]
            return _FakeResponse({
                "content": rows,
                "totalElements": 150,
                "page": page,
                "size": 100,
                "totalPages": 2,
                "last": page == 1,
            })

        adapter = ApiDasQuestoesAdapter(api_key="segredo", transport=transport)
        total, items, meta = adapter.page(limit=150)
        self.assertEqual(requested_pages, [0, 1])
        self.assertEqual(total, 150)
        self.assertEqual(len(items), 150)
        self.assertEqual(meta["fetched_pages"], 2)


if __name__ == "__main__":
    unittest.main()
