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
        self.assertIn("questions.create", operation_names)
        self.assertIn("questions.update", operation_names)
        self.assertIn("questions.delete", operation_names)
        self.assertIn("questions.annul", operation_names)
        self.assertIn("questions.image.remove", operation_names)
        self.assertIn("taxonomy.subjects.list", operation_names)
        self.assertIn("taxonomy.classification.options", operation_names)
        create_contract = next(item for item in contract["operations"] if item["name"] == "questions.create")
        update_contract = next(item for item in contract["operations"] if item["name"] == "questions.update")
        delete_contract = next(item for item in contract["operations"] if item["name"] == "questions.delete")
        annul_contract = next(item for item in contract["operations"] if item["name"] == "questions.annul")
        remove_image_contract = next(item for item in contract["operations"] if item["name"] == "questions.image.remove")
        subjects_contract = next(item for item in contract["operations"] if item["name"] == "taxonomy.subjects.list")
        classification_options_contract = next(item for item in contract["operations"] if item["name"] == "taxonomy.classification.options")
        self.assertTrue(create_contract["mutating"])
        self.assertTrue(update_contract["mutating"])
        self.assertTrue(delete_contract["mutating"])
        self.assertTrue(annul_contract["mutating"])
        self.assertTrue(remove_image_contract["mutating"])
        self.assertFalse(subjects_contract["mutating"])
        self.assertFalse(classification_options_contract["mutating"])
        result = self.api.dispatch_studio_v1("questions.list", {"limit": 10})
        self.assertTrue(result["ok"])
        self.assertEqual(result["contract"], "questflow.studio.v1")
        self.assertEqual(result["module"], "editorial_bank")
        self.assertEqual(result["data"]["meta"]["provider"], "local")

    def test_subject_listing_is_available_in_studio_v1_and_legacy_facade(self) -> None:
        studio = self.api.dispatch_studio_v1("taxonomy.subjects.list", {})
        legacy = self.api.list_materias()

        self.assertTrue(studio["ok"])
        self.assertEqual(studio["operation"], "taxonomy.subjects.list")
        self.assertEqual(studio["module"], "editorial_bank")
        self.assertIsInstance(studio["data"]["items"], list)
        self.assertEqual(studio["data"]["count"], len(studio["data"]["items"]))

        self.assertTrue(legacy["ok"])
        self.assertEqual(legacy["items"], studio["data"]["items"])
        self.assertEqual(legacy["count"], studio["data"]["count"])

    def test_classification_options_are_available_in_studio_v1_and_legacy_facade(self) -> None:
        studio = self.api.dispatch_studio_v1(
            "taxonomy.classification.options",
            {"subject": "", "lesson": ""},
        )
        legacy = self.api.get_bank_classification_options("", "")

        self.assertTrue(studio["ok"])
        self.assertEqual(studio["operation"], "taxonomy.classification.options")
        self.assertEqual(studio["module"], "editorial_bank")
        self.assertIn("subjects", studio["data"])
        self.assertIn("lessons", studio["data"])
        self.assertIn("tasks", studio["data"])

        self.assertTrue(legacy["ok"])
        self.assertEqual(legacy["subjects"], studio["data"]["subjects"])
        self.assertEqual(legacy["bank_subjects"], studio["data"]["bank_subjects"])
        self.assertEqual(legacy["lessons"], studio["data"]["lessons"])
        self.assertEqual(legacy["bank_lessons"], studio["data"]["bank_lessons"])
        self.assertEqual(legacy["tasks"], studio["data"]["tasks"])

    def test_manual_question_creation_is_available_in_studio_v1_and_legacy_facade(self) -> None:
        studio = self.api.dispatch_studio_v1("questions.create", {})
        self.assertTrue(studio["ok"])
        self.assertEqual(studio["operation"], "questions.create")
        self.assertEqual(studio["module"], "editorial_bank")
        studio_uid = str(studio["data"]["uid"])
        self.assertTrue(studio_uid)
        self.assertEqual(studio["data"]["question"]["database_uid"], studio_uid)

        legacy = self.api.create_manual_question()
        self.assertTrue(legacy["ok"])
        legacy_uid = str(legacy["uid"])
        self.assertTrue(legacy_uid)
        self.assertEqual(legacy["question"]["database_uid"], legacy_uid)
        self.assertNotEqual(studio_uid, legacy_uid)

    def test_question_save_is_available_in_studio_v1_and_legacy_facade(self) -> None:
        created = self.api.create_manual_question()
        self.assertTrue(created["ok"])
        uid = str(created["uid"])
        original = dict(self.api.get_question(uid)["question"])

        studio_payload = dict(original)
        studio_payload["enunciado"] = "Enunciado salvo pelo Studio v1"
        studio = self.api.dispatch_studio_v1(
            "questions.update",
            {"uid": uid, "question": studio_payload, "approve": False},
        )
        self.assertTrue(studio["ok"])
        self.assertEqual(studio["operation"], "questions.update")
        self.assertEqual(studio["data"]["question"]["enunciado"], "Enunciado salvo pelo Studio v1")
        self.assertIn("stats", studio["data"])
        self.assertIn("code_change", studio["data"])
        self.assertIn("curation", studio["data"])

        legacy_payload = dict(studio["data"]["question"])
        legacy_payload["enunciado"] = "Enunciado salvo pela fachada legada"
        legacy = self.api.save_question(uid, legacy_payload, True)
        self.assertTrue(legacy["ok"])
        self.assertEqual(legacy["question"]["enunciado"], "Enunciado salvo pela fachada legada")
        self.assertEqual(legacy["question"]["revisao"]["status"], "aprovado")

        persisted = self.api.get_question(uid)
        self.assertTrue(persisted["ok"])
        self.assertEqual(persisted["question"]["enunciado"], "Enunciado salvo pela fachada legada")
        self.assertEqual(persisted["question"]["revisao"]["status"], "aprovado")

    def test_question_lifecycle_is_available_in_studio_v1_and_legacy_facades(self) -> None:
        studio_annulled = self.api.create_manual_question()
        self.assertTrue(studio_annulled["ok"])
        studio_annul_uid = str(studio_annulled["uid"])
        annul = self.api.dispatch_studio_v1(
            "questions.annul",
            {"uid": studio_annul_uid, "reason": "Anulada no teste Studio v1"},
        )
        self.assertTrue(annul["ok"])
        self.assertEqual(annul["operation"], "questions.annul")
        self.assertIn("stats", annul["data"])
        self.assertFalse(self.api.get_question(studio_annul_uid)["ok"])

        studio_deleted = self.api.create_manual_question()
        self.assertTrue(studio_deleted["ok"])
        studio_delete_uid = str(studio_deleted["uid"])
        deleted = self.api.dispatch_studio_v1("questions.delete", {"uid": studio_delete_uid})
        self.assertTrue(deleted["ok"])
        self.assertEqual(deleted["operation"], "questions.delete")
        self.assertIn("stats", deleted["data"])
        self.assertFalse(self.api.get_question(studio_delete_uid)["ok"])

        legacy_annulled = self.api.create_manual_question()
        self.assertTrue(legacy_annulled["ok"])
        legacy_annul_uid = str(legacy_annulled["uid"])
        legacy_annul = self.api.annul_question(legacy_annul_uid, "Anulada pela fachada legada")
        self.assertTrue(legacy_annul["ok"])
        self.assertFalse(self.api.get_question(legacy_annul_uid)["ok"])

        legacy_deleted = self.api.create_manual_question()
        self.assertTrue(legacy_deleted["ok"])
        legacy_delete_uid = str(legacy_deleted["uid"])
        legacy_delete = self.api.delete_question(legacy_delete_uid)
        self.assertTrue(legacy_delete["ok"])
        self.assertFalse(self.api.get_question(legacy_delete_uid)["ok"])

    def test_question_image_removal_is_available_in_studio_v1_and_legacy_facade(self) -> None:
        assert self.api.commands is not None and self.api.queries is not None

        studio_created = self.api.create_manual_question()
        self.assertTrue(studio_created["ok"])
        studio_uid = str(studio_created["uid"])
        studio_question = dict(self.api.queries.get(studio_uid) or {})
        studio_question["imagem_questao"] = {
            "path": str(self.root / "external-studio-image.png"),
            "origem": "manual",
        }
        self.api.commands.update(studio_uid, studio_question)
        self.assertIn("imagem_questao", self.api.queries.get(studio_uid) or {})

        studio = self.api.dispatch_studio_v1("questions.image.remove", {"uid": studio_uid})
        self.assertTrue(studio["ok"])
        self.assertEqual(studio["operation"], "questions.image.remove")
        self.assertNotIn("imagem_questao", self.api.queries.get(studio_uid) or {})

        legacy_created = self.api.create_manual_question()
        self.assertTrue(legacy_created["ok"])
        legacy_uid = str(legacy_created["uid"])
        legacy_question = dict(self.api.queries.get(legacy_uid) or {})
        legacy_question["imagem_questao"] = {
            "path": str(self.root / "external-legacy-image.png"),
            "origem": "manual",
        }
        self.api.commands.update(legacy_uid, legacy_question)
        legacy = self.api.remove_image(legacy_uid)
        self.assertTrue(legacy["ok"])
        self.assertNotIn("imagem_questao", self.api.queries.get(legacy_uid) or {})

    def test_question_detail_is_equivalent_between_studio_v1_and_legacy_facade(self) -> None:
        created = self.api.create_manual_question()
        self.assertTrue(created["ok"])
        uid = str(created["uid"])

        studio = self.api.dispatch_studio_v1("questions.get", {"uid": uid})
        legacy = self.api.get_question(uid)

        self.assertTrue(studio["ok"])
        self.assertTrue(legacy["ok"])
        self.assertEqual(studio["data"]["question"], legacy["question"])
        self.assertEqual(studio["data"]["image"], legacy["image"])
        self.assertEqual(studio["data"]["question"]["database_uid"], uid)
        self.assertIn("historico_codigos", studio["data"]["question"])

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

            questions_request = urllib.request.Request(
                f"{server.base_url}/api/v1/studio/questions?search=&status=todos&offset=0&limit=10",
                headers={"X-QuestFlow-Token": server.token},
            )
            with urllib.request.urlopen(questions_request, timeout=5) as response:
                questions_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(questions_payload["ok"])
            self.assertEqual(questions_payload["contract"], "questflow.studio.v1")
            self.assertEqual(questions_payload["operation"], "questions.list")
            self.assertEqual(questions_payload["module"], "editorial_bank")
            self.assertIn("items", questions_payload["data"])

            subjects_request = urllib.request.Request(
                f"{server.base_url}/api/v1/studio/taxonomy/subjects",
                headers={"X-QuestFlow-Token": server.token},
            )
            with urllib.request.urlopen(subjects_request, timeout=5) as response:
                subjects_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(subjects_payload["ok"])
            self.assertEqual(subjects_payload["contract"], "questflow.studio.v1")
            self.assertEqual(subjects_payload["operation"], "taxonomy.subjects.list")
            self.assertEqual(subjects_payload["module"], "editorial_bank")
            self.assertIsInstance(subjects_payload["data"]["items"], list)

            classification_request = urllib.request.Request(
                f"{server.base_url}/api/v1/studio/taxonomy/classification-options?subject=&lesson=",
                headers={"X-QuestFlow-Token": server.token},
            )
            with urllib.request.urlopen(classification_request, timeout=5) as response:
                classification_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(classification_payload["ok"])
            self.assertEqual(classification_payload["contract"], "questflow.studio.v1")
            self.assertEqual(classification_payload["operation"], "taxonomy.classification.options")
            self.assertEqual(classification_payload["module"], "editorial_bank")
            self.assertIn("subjects", classification_payload["data"])
            self.assertIn("lessons", classification_payload["data"])
            self.assertIn("tasks", classification_payload["data"])

            created = self.api.create_manual_question()
            self.assertTrue(created["ok"])
            uid = str(created["uid"])
            detail_request = urllib.request.Request(
                f"{server.base_url}/api/v1/studio/questions/{urllib.parse.quote(uid, safe='')}",
                headers={"X-QuestFlow-Token": server.token},
            )
            with urllib.request.urlopen(detail_request, timeout=5) as response:
                detail_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(detail_payload["ok"])
            self.assertEqual(detail_payload["contract"], "questflow.studio.v1")
            self.assertEqual(detail_payload["operation"], "questions.get")
            self.assertEqual(detail_payload["data"]["question"]["database_uid"], uid)
            self.assertIn("historico_codigos", detail_payload["data"]["question"])
            self.assertIn("image", detail_payload["data"])

            create_request = urllib.request.Request(
                f"{server.base_url}/api/v1/studio/questions",
                data=b"{}",
                headers={
                    "X-QuestFlow-Token": server.token,
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(create_request, timeout=5) as response:
                create_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(create_payload["ok"])
            self.assertEqual(create_payload["contract"], "questflow.studio.v1")
            self.assertEqual(create_payload["operation"], "questions.create")
            self.assertTrue(create_payload["data"]["uid"])
            self.assertEqual(
                create_payload["data"]["question"]["database_uid"],
                create_payload["data"]["uid"],
            )

            created_uid = str(create_payload["data"]["uid"])
            update_question = dict(create_payload["data"]["question"])
            update_question["enunciado"] = "Atualização HTTP Studio v1"
            update_request = urllib.request.Request(
                f"{server.base_url}/api/v1/studio/questions/{urllib.parse.quote(created_uid, safe='')}",
                data=json.dumps({
                    "question": update_question,
                    "approve": False,
                }, ensure_ascii=False).encode("utf-8"),
                headers={
                    "X-QuestFlow-Token": server.token,
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(update_request, timeout=5) as response:
                update_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(update_payload["ok"])
            self.assertEqual(update_payload["contract"], "questflow.studio.v1")
            self.assertEqual(update_payload["operation"], "questions.update")
            self.assertEqual(update_payload["data"]["question"]["database_uid"], created_uid)
            self.assertEqual(update_payload["data"]["question"]["enunciado"], "Atualização HTTP Studio v1")
            self.assertIn("stats", update_payload["data"])
            self.assertIn("curation", update_payload["data"])

            annul_request = urllib.request.Request(
                f"{server.base_url}/api/v1/studio/questions/{urllib.parse.quote(created_uid, safe='')}/annul",
                data=json.dumps({"reason": "Anulada via HTTP Studio v1"}, ensure_ascii=False).encode("utf-8"),
                headers={
                    "X-QuestFlow-Token": server.token,
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(annul_request, timeout=5) as response:
                annul_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(annul_payload["ok"])
            self.assertEqual(annul_payload["operation"], "questions.annul")
            self.assertIn("stats", annul_payload["data"])
            self.assertFalse(self.api.get_question(created_uid)["ok"])

            delete_create_request = urllib.request.Request(
                f"{server.base_url}/api/v1/studio/questions",
                data=b"{}",
                headers={
                    "X-QuestFlow-Token": server.token,
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(delete_create_request, timeout=5) as response:
                delete_create_payload = json.loads(response.read().decode("utf-8"))
            delete_uid = str(delete_create_payload["data"]["uid"])
            delete_request = urllib.request.Request(
                f"{server.base_url}/api/v1/studio/questions/{urllib.parse.quote(delete_uid, safe='')}/delete",
                data=b"{}",
                headers={
                    "X-QuestFlow-Token": server.token,
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(delete_request, timeout=5) as response:
                delete_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(delete_payload["ok"])
            self.assertEqual(delete_payload["operation"], "questions.delete")
            self.assertIn("stats", delete_payload["data"])
            self.assertFalse(self.api.get_question(delete_uid)["ok"])

            image_created = self.api.create_manual_question()
            self.assertTrue(image_created["ok"])
            image_uid = str(image_created["uid"])
            assert self.api.commands is not None and self.api.queries is not None
            image_question = dict(self.api.queries.get(image_uid) or {})
            image_question["imagem_questao"] = {
                "path": str(self.root / "external-http-image.png"),
                "origem": "manual",
            }
            self.api.commands.update(image_uid, image_question)
            remove_image_request = urllib.request.Request(
                f"{server.base_url}/api/v1/studio/questions/{urllib.parse.quote(image_uid, safe='')}/image/remove",
                data=b"{}",
                headers={
                    "X-QuestFlow-Token": server.token,
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(remove_image_request, timeout=5) as response:
                remove_image_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(remove_image_payload["ok"])
            self.assertEqual(remove_image_payload["operation"], "questions.image.remove")
            self.assertNotIn("imagem_questao", self.api.queries.get(image_uid) or {})

            with urllib.request.urlopen(f"{server.base_url}/modules/bootstrap.js", timeout=5) as response:
                frontend = response.read().decode("utf-8")
            self.assertIn("typed-route-modules-v1", frontend)
        finally:
            server.stop()

    def test_review_core_editorial_actions_use_studio_v1_with_legacy_fallback(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("async studioGet(path, fallbackMethod = '', fallbackArgs = [])", script)
        self.assertIn("/api/v1/studio/", script)

        list_start = script.index("async function loadQuestions()")
        list_end = script.index("async function ensureMatterOptions", list_start)
        load_questions = script[list_start:list_end]
        self.assertIn("bridge.studioGet(", load_questions)
        self.assertIn("'list_questions'", load_questions)
        self.assertNotIn("bridge.call('list_questions'", load_questions)

        subjects_start = script.index("async function ensureMatterOptions")
        subjects_end = script.index("async function selectQuestion", subjects_start)
        subject_options = script[subjects_start:subjects_end]
        self.assertIn("bridge.studioGet('taxonomy/subjects', 'list_materias')", subject_options)
        self.assertNotIn("bridge.call('list_materias'", subject_options)

        detail_start = script.index("async function selectQuestion")
        detail_end = script.index("const metadataFields", detail_start)
        select_question = script[detail_start:detail_end]
        self.assertIn("bridge.studioGet(", select_question)
        self.assertIn("'get_question'", select_question)
        self.assertIn("encodeURIComponent(uid)", select_question)
        self.assertNotIn("bridge.call('get_question'", select_question)

        create_start = script.index("async function createQuestion()")
        create_end = script.index("async function deleteQuestion()", create_start)
        create_question = script[create_start:create_end]
        self.assertIn("bridge.studioPost('questions'", create_question)
        self.assertIn("'create_manual_question'", create_question)
        self.assertNotIn("bridge.call('create_manual_question'", create_question)
        self.assertIn("async studioPost(path, payload = {}, fallbackMethod = '', fallbackArgs = [])", script)

        save_start = script.index("async function saveCurrentQuestion")
        save_end = script.index("function clearQuestionEditor", save_start)
        save_question = script[save_start:save_end]
        self.assertIn("bridge.studioPost(", save_question)
        self.assertIn("encodeURIComponent(state.currentUid)", save_question)
        self.assertIn("'save_question'", save_question)
        self.assertNotIn("bridge.call('save_question'", save_question)

        delete_start = script.index("async function deleteQuestion()")
        delete_end = script.index("async function annulQuestion()", delete_start)
        delete_question = script[delete_start:delete_end]
        self.assertIn("bridge.studioPost(", delete_question)
        self.assertIn("/delete", delete_question)
        self.assertIn("'delete_question'", delete_question)
        self.assertNotIn("bridge.call('delete_question'", delete_question)

        annul_start = script.index("async function annulQuestion()")
        annul_end = script.index("async function attachImage()", annul_start)
        annul_question = script[annul_start:annul_end]
        self.assertIn("bridge.studioPost(", annul_question)
        self.assertIn("/annul", annul_question)
        self.assertIn("'annul_question'", annul_question)
        self.assertNotIn("bridge.call('annul_question'", annul_question)

        remove_image_start = script.index("async function removeImage()")
        remove_image_end = script.index("async function rereadQuestion()", remove_image_start)
        remove_image = script[remove_image_start:remove_image_end]
        self.assertIn("bridge.studioPost(", remove_image)
        self.assertIn("/image/remove", remove_image)
        self.assertIn("'remove_image'", remove_image)
        self.assertNotIn("bridge.call('remove_image'", remove_image)

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
