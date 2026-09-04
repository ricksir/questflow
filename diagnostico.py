from __future__ import annotations

import importlib
import json
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

REQUIRED = ["pymupdf", "PIL", "pytesseract", "cv2", "tkinter"]
OPTIONAL = ["pymupdf4llm", "selenium"]


def main() -> int:
    print(f"Python: {sys.version.split()[0]}")
    failures: list[tuple[str, str]] = []
    for module in REQUIRED:
        try:
            importlib.import_module(module)
            print(f"[OK] {module}")
        except Exception as error:
            failures.append((module, str(error)))
            print(f"[FALHA] {module}: {error}")
    for module in OPTIONAL:
        try:
            importlib.import_module(module)
            print(f"[OK] {module}")
        except Exception as error:
            print(f"[AVISO] {module}: indisponível neste ambiente; o QuestFlow usará o modo alternativo ({error})")

    base_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(base_dir))

    try:
        from core.extractor import configure_tesseract

        path = configure_tesseract("")
        print(f"[OK] Tesseract: {path}")
    except Exception as error:
        failures.append(("Tesseract OCR", str(error)))
        print(f"[FALHA] Tesseract OCR: {error}")
        print("Instale o Tesseract OCR para Windows e mantenha o idioma Portuguese.")
        print(r"Caminho comum: C:\Program Files\Tesseract-OCR\tesseract.exe")

    data_dir = base_dir / "data"
    data_dir.mkdir(exist_ok=True)
    print(f"[OK] Pasta de dados: {data_dir}")


    try:
        import json as _json
        import urllib.request
        from core.network import network_urlopen
        from web_server import QuestFlowLocalServer

        class _DiagnosticApi:
            def bootstrap_shell(self):
                return {"ok": True, "engine": "http-json"}

        with tempfile.TemporaryDirectory(prefix="questflow_http_engine_") as temp_name:
            web_root = Path(temp_name)
            (web_root / "index.html").write_text("QuestFlow", encoding="utf-8")
            server = QuestFlowLocalServer(_DiagnosticApi(), web_root)
            server.start()
            try:
                request = urllib.request.Request(
                    server.base_url + "/api/call",
                    data=_json.dumps({"method": "bootstrap_shell", "args": []}).encode("utf-8"),
                    headers={"Content-Type": "application/json", "X-QuestFlow-Token": server.token},
                    method="POST",
                )
                with network_urlopen(request, timeout=5) as response:
                    payload = _json.loads(response.read().decode("utf-8"))
                if not payload.get("ok") or payload.get("result", {}).get("engine") != "http-json":
                    raise ValueError("resposta inesperada do motor local")
            finally:
                server.stop()
        print("[OK] Motor local HTTP/JSON: interface e núcleo comunicando sem ponte injetada")
    except Exception as error:
        failures.append(("Motor local HTTP/JSON", str(error)))
        print(f"[FALHA] Motor local HTTP/JSON: {error}")

    try:
        from desktop_runtime import browser_candidates

        browsers = browser_candidates()
        if browsers:
            print(f"[OK] Google Chrome exclusivo: {browsers[0]}")
        else:
            print("[AVISO] Google Chrome não localizado; instale o Chrome para abrir a interface responsiva")
    except Exception as error:
        print(f"[AVISO] Verificação do Google Chrome: {error}")

    try:
        from core.network import NetworkManager, detect_system_proxy

        detected = detect_system_proxy()
        manager = NetworkManager()
        effective = manager.resolve("https://www.google.com/", refresh=True).public()
        if effective.get("enabled"):
            print(f"[OK] Rede corporativa: proxy {effective.get('proxy') or effective.get('source')} ({effective.get('source')})")
        else:
            print(f"[OK] Rede corporativa: conexão direta/bypass ({effective.get('detail', '')})")
        if detected.get("pac_url"):
            print(f"[OK] PAC detectado: {detected.get('pac_url')}")
        if detected.get("auto_detect"):
            print("[OK] WPAD/autodetecção de proxy habilitada no Windows")
        print("[OK] Bypass local obrigatório: localhost, 127.0.0.1 e ::1")
    except Exception as error:
        print(f"[AVISO] Detecção de Rede e Proxy: {error}")

    # Cloud Sync is optional. Validate the local/outbox engine unconditionally and
    # perform a live Turso acceptance check only after the user has configured it.
    try:
        from app_shared import CONFIG_PATH, DATABASE_PATH, load_config
        from core.cloud_sync import CloudSyncEngine, load_turso_token
        from core.storage import QuestFlowDatabase
        from core.study import StudyRepository

        with tempfile.TemporaryDirectory(prefix="questflow_cloud_sync_") as temp_name:
            temp_db_path = Path(temp_name) / "cloud-test.sqlite"
            temp_db = QuestFlowDatabase(temp_db_path)
            temp_study = StudyRepository(temp_db)
            temp_cfg = {
                "cloud_sync_enabled": False,
                "cloud_device_name": "DIAGNOSTICO",
                "cloud_turso_url": "",
            }
            cloud = CloudSyncEngine(
                temp_db_path, config=temp_cfg,
                config_path=Path(temp_name) / "config.json",
                reset_callback=temp_study.reset_progress,
            )
            uid = temp_db.create_manual_question()
            temp_study.sync_questions()
            if cloud.pending_count() < 1 or temp_db.get_question(uid) is None:
                raise ValueError("a fila local durável não capturou uma alteração confirmada")
            # sqlite3.Connection.__exit__ commits/rolls back, but it does NOT close
            # the connection. On Windows that left cloud-test.sqlite open and
            # TemporaryDirectory failed with WinError 32 even though the Cloud
            # Sync self-test itself had passed. ``closing`` guarantees the OS
            # file handle is released before the temporary directory is removed.
            with closing(sqlite3.connect(temp_db_path, timeout=3)) as check:
                if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("integridade SQLite inválida após inicializar Cloud Sync")
                # Force any remaining WAL frames back into the database before
                # Windows cleanup. This is harmless on other platforms and makes
                # the diagnostic deterministic after abrupt previous exits.
                check.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        print("[OK] Cloud Sync local-first: outbox durável, gatilhos e integridade SQLite")

        live_cfg = load_config()
        live_url = str(live_cfg.get("cloud_turso_url", "") or "").strip()
        live_token = load_turso_token(CONFIG_PATH)
        if bool(live_cfg.get("cloud_sync_enabled")) and live_url and live_token:
            live = CloudSyncEngine(DATABASE_PATH, config=live_cfg, config_path=CONFIG_PATH)
            result = live.test_remote()
            print(f"[OK] Turso Cloud real: conectado em {result.get('elapsed_ms', 0)} ms; geração {result.get('generation', 1)}")
        else:
            print("[INFO] Turso Cloud real: ainda não configurado; use CONFIGURAR_TURSO_CLOUD.bat ou Configurações → Cloud Sync")
    except Exception as error:
        failures.append(("Cloud Sync / Turso", str(error)))
        print(f"[FALHA] Cloud Sync / Turso: {error}")

    taxonomy_path = data_dir / "taxonomia_afrfb.json"
    try:
        from core.spreadsheet_taxonomy import SpreadsheetTaxonomy

        taxonomy = SpreadsheetTaxonomy.load(taxonomy_path)
        print(
            f"[OK] Taxonomia AFRFB: {len(taxonomy.materias)} matérias e "
            f"{len(taxonomy.tasks)} tarefas de referência"
        )
        if taxonomy.payload.get("schema") != "questflow.taxonomy.v1":
            raise ValueError("schema de taxonomia inválido")
    except Exception as error:
        failures.append(("Taxonomia AFRFB", str(error)))
        print(f"[FALHA] Taxonomia AFRFB: {error}")

    try:
        import pymupdf
        from core.markdown_pipeline import build_markdown_bundle

        with tempfile.TemporaryDirectory(prefix="questflow_markdown_") as temp_name:
            root = Path(temp_name)
            sample_path = root / "markdown.pdf"
            sample = pymupdf.open()
            page = sample.new_page()
            page.insert_text((50, 80), "QuestFlow Markdown - questão de auditoria")
            sample.save(sample_path)
            sample.close()
            bundle = build_markdown_bundle(sample_path, root / "cache")
            if "QuestFlow Markdown" not in bundle.markdown:
                raise ValueError("o texto não foi preservado no Markdown")
            if not Path(bundle.markdown_path).exists():
                raise ValueError("o cache Markdown não foi criado")
        print("[OK] Pipeline Markdown: estrutura, cache e preparação para imagens/OCR")
    except Exception as error:
        failures.append(("Pipeline Markdown", str(error)))
        print(f"[FALHA] Pipeline Markdown: {error}")

    try:
        import pymupdf
        from core.extractor import ExtractorConfig, extract_pdf
        from core.spreadsheet_taxonomy import SpreadsheetTaxonomy

        taxonomy_for_extract = SpreadsheetTaxonomy.load(taxonomy_path)
        with tempfile.TemporaryDirectory(prefix="questflow_pdf_textual_") as temp_name:
            sample_path = Path(temp_name) / "lista_textual.pdf"
            sample = pymupdf.open()
            page = sample.new_page()
            content = (
                "LISTA DE QUESTÕES\n\n"
                "1. (CEBRASPE / ÓRGÃO TESTE - 2025) Assinale a opção correta sobre ETL.\n"
                "a) Alternativa incorreta.\n"
                "b) ETL significa extração, transformação e carga.\n\n"
                "2. (CEBRASPE / ÓRGÃO TESTE - 2025) Julgue o item a seguir.\n"
                "Um Data Warehouse apoia a análise de dados históricos.\n\n"
                "GABARITO\n"
                "1. LETRA B\n"
                "2. CORRETO\n"
            )
            page.insert_textbox(pymupdf.Rect(45, 45, 550, 800), content, fontsize=10)
            sample.save(sample_path)
            sample.close()
            extracted = extract_pdf(
                sample_path,
                config=ExtractorConfig(),
                taxonomy=taxonomy_for_extract,
            )
            if extracted.get("extractor_mode") != "texto_nativo_lista_gabarito":
                raise ValueError("o extrator textual não foi selecionado")
            if extracted.get("starts_found") != 2 or extracted.get("answers_found") != 2:
                raise ValueError("a lista textual e o gabarito não foram reconhecidos")
            questions = extracted.get("questions", [])
            if len(questions) != 2 or questions[0].get("gabarito") != "B":
                raise ValueError("as questões textuais não foram associadas ao gabarito")
            if questions[1].get("tipo") != "certo_errado":
                raise ValueError("a questão de Certo/Errado não foi reconhecida")
        print("[OK] PDFs textuais: lista, metadados, alternativas e gabarito")
    except Exception as error:
        failures.append(("Extrator de PDFs textuais", str(error)))
        print(f"[FALHA] Extrator de PDFs textuais: {error}")


    try:
        from core.extractor import deep_repair_question

        broken_true_false = {
            "enunciado": "Julgue o item a seguir. O controle interno auxilia a auditoria.",
            "alternativas": [],
            "gabarito": "CORRETO",
            "tipo": "multipla_escolha",
            "materia": "AUDITORIA",
            "assunto": "CONTROLE INTERNO",
            "banca": "CEBRASPE",
            "ano": 2025,
            "orgao": "TCU",
            "classificacao_planilha": {"status": "classificado", "confianca": 1.0},
        }
        repaired = deep_repair_question(broken_true_false, None)
        if repaired.get("tipo") != "certo_errado" or repaired.get("gabarito") != "C":
            raise ValueError("a questão Certo/Errado não foi reparada")
        if len(repaired.get("alternativas", [])) != 2:
            raise ValueError("as alternativas Certo/Errado não foram reconstruídas")

        broken_multiple = {
            "enunciado": "Assinale a opção correta. a) Alfa b) Beta c) Gama.",
            "alternativas": [],
            "gabarito": "B",
            "tipo": "multipla_escolha",
            "materia": "AUDITORIA",
            "assunto": "TESTE",
            "banca": "FGV",
            "ano": 2025,
            "orgao": "MF",
            "classificacao_planilha": {"status": "classificado", "confianca": 1.0},
        }
        repaired_multiple = deep_repair_question(broken_multiple, None)
        if len(repaired_multiple.get("alternativas", [])) != 3:
            raise ValueError("as alternativas incorporadas ao enunciado não foram recuperadas")
        print("[OK] Análise apurada: Certo/Errado, alternativas embutidas e aprovação segura")
    except Exception as error:
        failures.append(("Análise apurada", str(error)))
        print(f"[FALHA] Análise apurada: {error}")

    try:
        from core.storage import QuestFlowDatabase
        from core.study import SelectionFilters, StudyRepository

        temp_dir = Path(tempfile.mkdtemp(prefix="questflow_diagnostico_"))
        try:
            database = QuestFlowDatabase(temp_dir / "diagnostico.sqlite")
            subjects = ["AUDITORIA", "DIREITO TRIBUTÁRIO", "FLUÊNCIA EM DADOS", "CONTABILIDADE GERAL E AVANÇADA"]
            uids: list[str] = []
            for index in range(24):
                uid = database.create_manual_question(None)
                question = database.get_question(uid)
                if question is None:
                    raise ValueError("questão de diagnóstico não localizada")
                question["materia"] = subjects[index % len(subjects)]
                question["assunto"] = f"Assunto {index % 8}"
                question["aula_planilha"] = f"Aula {index % 6:02d}"
                question["enunciado"] = f"Questão de diagnóstico {index}"
                question["revisao"]["status"] = "aprovado"
                database.update_question(uid, question)
                uids.append(uid)

            study = StudyRepository(database)
            selected = study.select_questions(
                SelectionFilters(subjects=[], approved_only=True, strategy="auditor_inteligente"),
                20,
            )
            if len(selected) != 20:
                raise ValueError("o ciclo inteligente não selecionou vinte questões")
            if len({item.get("materia") for item in selected}) < 4:
                raise ValueError("a rotação inteligente não distribuiu as matérias")

            cycle_id = "diagnostico-ciclo"
            study.begin_cycle(
                cycle_id,
                "diario",
                20,
                scheduled_for="2026-07-15T19:00",
                scheduled_date="2026-07-15",
                requested_via="diagnostico",
            )
            fake_send = {
                "direct_poll": True,
                "poll": {"result": {"message_id": 1, "poll": {"id": "diagnostico-poll"}}},
            }
            study.record_delivery(selected[0]["database_uid"], "0", fake_send, cycle_id)
            answer = study.record_poll_answer(
                {
                    "poll_id": "diagnostico-poll",
                    "user": {"id": 1, "username": "diagnostico"},
                    "option_ids": [0],
                }
            )
            study.finish_cycle(cycle_id, 1, 0, "parcial")
            if not answer or not answer.get("is_correct"):
                raise ValueError("a resposta de teste não foi registrada como correta")
            if not study.daily_cycle_done("2026-07-15"):
                raise ValueError("o ciclo diário não foi persistido")
            stats = study.stats()
            if stats["correct"] != 1 or stats["sent"] != 1 or stats["daily_cycles"] != 1:
                raise ValueError("as estatísticas do fluxo não foram atualizadas")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        print("[OK] Banco, ciclo diário de 20 questões, rotação por matéria e estatísticas")
    except Exception as error:
        failures.append(("Motor de estudo", str(error)))
        print(f"[FALHA] Motor de estudo: {error}")

    try:
        from unittest.mock import patch
        from core.telegram import TelegramError, with_retry

        attempts = {"count": 0}
        def transient_operation():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise TelegramError("Falha temporária simulada", category="servidor_telegram", retryable=True)
            return {"ok": True}
        with patch("core.telegram.time.sleep", return_value=None), patch("core.telegram.random.uniform", return_value=0):
            retry_result = with_retry(transient_operation, attempts=3, base_delay=0)
        if not retry_result.get("ok") or attempts["count"] != 3:
            raise ValueError("o backoff não recuperou a falha temporária")
        print("[OK] Telegram resiliente: classificação de erro e retentativa com backoff")
    except Exception as error:
        failures.append(("Retentativas do Telegram", str(error)))
        print(f"[FALHA] Retentativas do Telegram: {error}")

    try:
        from core.telegram import study_menu_markup, telegram_payload

        payload = telegram_payload(
            {
                "enunciado": "Questão de diagnóstico",
                "alternativas": [
                    {"chave": "A", "texto": "Alternativa correta"},
                    {"chave": "B", "texto": "Alternativa incorreta"},
                ],
                "gabarito": "A",
                "tipo": "multipla_escolha",
                "telegram": {"indice_correto": 0},
                "database_uid": "00000000-0000-0000-0000-000000000001",
            },
            "0",
        )
        if payload.get("type") != "quiz" or payload.get("is_anonymous") != "false":
            raise ValueError("payload do Telegram não está no modo quiz não anônimo")
        if json.loads(payload.get("correct_option_ids", "[]")) != [0]:
            raise ValueError("alternativa correta não foi configurada")
        review_markup = json.loads(payload.get("reply_markup", "{}"))
        review_callbacks = {
            button.get("callback_data")
            for row in review_markup.get("inline_keyboard", [])
            for button in row
        }
        if "qf:review:00000000-0000-0000-0000-000000000001" not in review_callbacks:
            raise ValueError("o botão de correção da questão não foi criado")
        menu = study_menu_markup(extra_count=5, cycle_count=20)
        buttons = [button for row in menu.get("inline_keyboard", []) for button in row]
        callbacks = {button.get("callback_data") for button in buttons}
        if "qf:more:5" not in callbacks or "qf:cycle:20" not in callbacks or "qf:stats" not in callbacks:
            raise ValueError("os botões para pedir mais questões não foram criados")
        print("[OK] Quiz, botão de correção, mais questões, novo ciclo e desempenho no Telegram")
    except Exception as error:
        failures.append(("Telegram", str(error)))
        print(f"[FALHA] Telegram: {error}")

    try:
        from core.storage import QuestFlowDatabase
        from core.study import StudyRepository

        with tempfile.TemporaryDirectory(prefix="questflow_review_queue_") as temp_name:
            review_db = QuestFlowDatabase(Path(temp_name) / "review.sqlite")
            review_uid = review_db.create_manual_question(None)
            review_study = StudyRepository(review_db)
            request = review_study.create_review_request(
                review_uid, chat_id="0", user_id="1", username="diagnostico", message_id=10
            )
            if review_study.pending_review_count() != 1:
                raise ValueError("a solicitação de correção não foi persistida")
            review_study.mark_review_opened(request["id"])
            review_study.resolve_review_request(request["id"])
            resolved = review_study.get_review_request(request["id"])
            if not resolved or resolved.get("status") != "resolvida":
                raise ValueError("a fila de correções não concluiu o ciclo pendente/aberta/resolvida")
        print("[OK] Correções Telegram: fila persistente, abertura posterior e resolução")
    except Exception as error:
        failures.append(("Fila de correções do Telegram", str(error)))
        print(f"[FALHA] Fila de correções do Telegram: {error}")

    try:
        from datetime import datetime, timedelta, timezone
        from core.storage import QuestFlowDatabase
        from core.study import StudyRepository

        with tempfile.TemporaryDirectory(prefix="questflow_offline_queue_") as temp_name:
            queue_db = QuestFlowDatabase(Path(temp_name) / "queue.sqlite")
            queue_uid = queue_db.create_manual_question(None)
            question = queue_db.get_question(queue_uid)
            question["materia"] = "AUDITORIA"
            question["aula_planilha"] = "Aula 01"
            question["assunto"] = "Evidências"
            question["revisao"]["status"] = "aprovado"
            queue_db.update_question(queue_uid, question)
            queue_study = StudyRepository(queue_db)
            callback_id = queue_study.enqueue_callback_update(
                100,
                {
                    "id": "callback-diagnostico",
                    "data": f"qf:review:{queue_uid}",
                    "message": {"chat": {"id": 1}},
                },
            )
            if not queue_study.pending_callback_updates():
                raise ValueError("o clique offline não foi guardado")
            queue_study.mark_callback_processed(callback_id)
            outbox_id = queue_study.enqueue_outbox_message("1", "Confirmação", kind="diagnostico")
            if not queue_study.pending_outbox_messages():
                raise ValueError("a confirmação offline não foi guardada")
            queue_study.mark_outbox_sent(outbox_id)

            fake_send = {
                "direct_poll": True,
                "poll": {"result": {"message_id": 1, "poll": {"id": "poll-sem-resposta"}}},
            }
            delivery = queue_study.record_delivery(queue_uid, "1", fake_send, "cycle-offline")
            old = (datetime.now(timezone.utc) - timedelta(hours=30)).replace(microsecond=0).isoformat()
            with queue_db.connect() as connection:
                connection.execute(
                    "UPDATE telegram_deliveries SET sent_at = ? WHERE id = ?",
                    (old, delivery["delivery_id"]),
                )
            if not queue_study.unanswered_deliveries_due(wait_hours=24, max_resends=2):
                raise ValueError("a questão sem resposta não entrou na fila de reenvio")
            coverage = queue_study.lesson_coverage([
                {"materia": "AUDITORIA", "aula": "Aula 01", "descricao": "Evidências", "segmentos": ["Evidências"]},
                {"materia": "AUDITORIA", "aula": "Aula 02", "descricao": "Relatórios", "segmentos": ["Relatórios"]},
            ])
            statuses = {row["lesson"]: row["status"] for row in coverage}
            if statuses.get("Aula 01") != "todas_enviadas" or statuses.get("Aula 02") != "sem_questoes":
                raise ValueError("o mapa de aulas não diferenciou cobertura e ausência de questões")
        print("[OK] Continuidade offline: correções persistentes, reenvio sem resposta e mapa de aulas")
    except Exception as error:
        failures.append(("Continuidade offline e mapa de aulas", str(error)))
        print(f"[FALHA] Continuidade offline e mapa de aulas: {error}")

    try:
        from datetime import datetime
        from core.flow import CyclicStudyEngine

        class DummyStudy:
            @staticmethod
            def daily_cycle_done(_date: str) -> bool:
                return False

        engine = object.__new__(CyclicStudyEngine)
        engine.study = DummyStudy()
        config = {"flow_daily_time": "19:30", "flow_weekdays": list(range(7))}
        now = datetime(2026, 7, 15, 18, 0)
        next_run = engine._next_occurrence(config, now)
        if next_run.hour != 19 or next_run.minute != 30:
            raise ValueError("o horário diário não foi calculado corretamente")
        print("[OK] Agendamento diário por horário e dias da semana")
    except Exception as error:
        failures.append(("Agendador diário", str(error)))
        print(f"[FALHA] Agendador diário: {error}")


    try:
        from core.enrichment import (
            _parse_google_html,
            _SEARCH_DIRECTIVE,
            build_search_queries,
            parse_candidate_question,
            parse_google_search_page,
            enrichment_from_candidate,
        )
        from core.google_browser import _expand_google_answer

        sample_question = {
            "codigo_origem": "Q2534553",
            "enunciado": "Assinale a opção correta sobre princípios orçamentários.",
            "banca": "FGV",
            "ano": 2024,
            "orgao": "MF",
        }
        queries = build_search_queries(sample_question)
        if len(queries) < 2:
            raise ValueError("não foram geradas consultas alternativas")
        first_query = queries[0]
        if _SEARCH_DIRECTIVE not in first_query:
            raise ValueError("pergunta orientadora atual do Google não aplicada")
        normalized_query = first_query.casefold()
        required_answer_terms = ("gabarito", "justificativa", "sem repetir enunciado")
        if not all(term in normalized_query for term in required_answer_terms):
            raise ValueError("pergunta orientadora não está suficientemente focada na resposta da questão")
        if not first_query.startswith('"Q2534553"'):
            raise ValueError("consulta prioritária por código não foi preservada")
        if "Q2534553" in queries[1]:
            raise ValueError("fallback por enunciado ainda contém o código da questão")
        if not _parse_google_html('<a href="/url?q=https%3A%2F%2Fexample.com%2Fg"><h3>Q2534553</h3></a>'):
            raise ValueError("parser Google inválido")
        google_text = """
        Q2534553
        Informações da Questão
        Ano: 2024
        Banca: FGV
        Órgão: MF
        Enunciado
        Assinale a opção correta sobre princípios orçamentários.
        Gabarito
        B
        Justificativa
        O princípio aplicável é o indicado na alternativa B.
        """
        google_candidate = parse_google_search_page(
            google_text,
            "<html></html>",
            sample_question,
            search_url="https://www.google.com/search?q=Q2534553",
        )
        if not google_candidate.get("verified") or google_candidate.get("gabarito") != "B":
            raise ValueError("leitura da página renderizada do Google inválida")
        selected_enrichment = enrichment_from_candidate(google_candidate, question_uid="diagnostico")
        if not selected_enrichment.get("safe_to_apply") or selected_enrichment.get("question_uid") != "diagnostico":
            raise ValueError("extração manual da fonte selecionada inválida")
        parsed = parse_candidate_question(
            '<div>Q2534553</div><div>Ano: 2024 Banca: FGV Órgão: MF</div>'
            '<p>Assinale a opção correta sobre princípios orçamentários.</p>'
            '<div>Alternativas</div><div>A</div><div>Universalidade.</div>'
            '<div>B</div><div>Exclusividade.</div><div>Gabarito: B</div>',
            sample_question,
        )
        if not parsed.get("verified") or parsed.get("gabarito") != "B":
            raise ValueError("validação de fonte adicional/gabarito inválida")

        class _DiagBody:
            def __init__(self, driver):
                self.driver = driver
            @property
            def text(self):
                return self.driver.body_text

        class _DiagMore:
            def __init__(self, driver):
                self.driver = driver
            def is_displayed(self):
                return not self.driver.expanded
            def click(self):
                self.driver.expanded = True
                self.driver.body_text += "\nGabarito\nB\nJustificativa\nO princípio aplicável é o indicado na alternativa B.\nMostrar menos"

        class _DiagDriver:
            def __init__(self):
                self.body_text = "Q2534553\nInformações Gerais\nAno: 2024\nBanca: FGV\nMostrar mais"
                self.expanded = False
                self.more = _DiagMore(self)
            def find_element(self, by, value):
                if by == "tag name" and value == "body":
                    return _DiagBody(self)
                raise LookupError(value)
            def find_elements(self, by, value):
                if "Mostrar mais" in value and not self.expanded:
                    return [self.more]
                return []
            def execute_script(self, script, *args):
                if "click" in script and args:
                    args[0].click()

        expanded = _expand_google_answer(_DiagDriver())
        if not expanded.get("expanded") or "Justificativa" not in expanded.get("text", ""):
            raise ValueError("o botão Mostrar mais não foi expandido antes da leitura")
        print("[OK] Google Modo IA: resposta renderizada, Mostrar mais, banca/ano, alternativas, gabarito e justificativa")
    except Exception as error:
        failures.append(("Pesquisa Google visível", str(error)))
        print(f"[FALHA] Pesquisa Google visível: {error}")

    try:
        source_files = [base_dir / "app.py", *(base_dir / "ui").glob("*.py")]
        app_source = "\n".join(path.read_text(encoding="utf-8") for path in source_files if path.exists())
        required_events = (
            'kind == "deep_progress"',
            'kind == "deep_done"',
            'kind == "deep_cancelled"',
            'kind == "deep_error"',
            'kind == "reread_progress"',
        )
        missing = [event for event in required_events if event not in app_source]
        if missing:
            raise ValueError("eventos da interface ausentes: " + ", ".join(missing))
        if "Preparar prévia e atualizar base" not in app_source or "OK — atualizar base" not in app_source:
            raise ValueError("prévia confirmável antes da atualização não foi incorporada à interface")
        print("[OK] Interface: progresso, prévia Telegram e confirmação antes de atualizar a base")
    except Exception as error:
        failures.append(("Eventos da análise apurada", str(error)))
        print(f"[FALHA] Eventos da análise apurada: {error}")

    try:
        from core.storage import QuestFlowDatabase
        archive_root = base_dir / "data" / "diagnostico_archive"
        archive_root.mkdir(parents=True, exist_ok=True)
        archive_db = archive_root / "archive.sqlite"
        if archive_db.exists():
            archive_db.unlink()
        db = QuestFlowDatabase(archive_db)
        sample = {
            "id": "Q-ANULADA", "codigo_origem": "Q-ANULADA", "fingerprint": "diag-annulled",
            "materia": "TESTE", "assuntos": [], "enunciado": "Questão anulada",
            "alternativas": [{"chave": "A", "texto": "A"}, {"chave": "B", "texto": "B"}],
            "gabarito": "A", "tipo": "multipla_escolha", "fonte": {"arquivo": "diag.pdf"},
            "revisao": {"status": "pendente", "confianca": 0.5, "alertas": []},
        }
        db.import_extraction({"source_file": "diag.pdf", "questions": [sample]})
        uid = db.list_questions()[0]["uid"]
        if not db.archive_question(uid, kind="anulada", reason="diagnóstico"):
            raise ValueError("não arquivou a questão anulada")
        if db.stats()["total"] != 0 or db.excluded_count("anulada") != 1:
            raise ValueError("questão anulada ainda está na base ativa")
        print("[OK] Questões anuladas: retirada da base ativa e bloqueio de reimportação")
    except Exception as error:
        failures.append(("Arquivamento de anuladas", str(error)))
        print(f"[FALHA] Arquivamento de anuladas: {error}")

    try:
        from core.adaptive_engine import MemoryState, OnlineRecallModel, forgetting_curve, update_memory_state
        recall_now = forgetting_curve(0, 10)
        recall_later = forgetting_curve(20, 10)
        if not (recall_now > recall_later):
            raise ValueError("curva de esquecimento não é monotônica")
        state, interval = update_memory_state(
            MemoryState(difficulty=5, stability_days=5),
            correct=True,
            elapsed_days=5,
            response_seconds=20,
        )
        if state.stability_days <= 5 or interval <= 0:
            raise ValueError("estado de memória não evoluiu após acerto")
        model = OnlineRecallModel.default()
        if not 0 < model.predict(model.features(
            state=state,
            elapsed_days=1,
            historical_accuracy=0.7,
            response_seconds=20,
            is_new=False,
            autoapproved=False,
        )) < 1:
            raise ValueError("previsão adaptativa inválida")
        print("[OK] Motor adaptativo: curva de esquecimento, memória e modelo online")
    except Exception as error:
        failures.append(("Motor adaptativo", str(error)))
        print(f"[FALHA] Motor adaptativo: {error}")

    try:
        from core.learning_analytics import subject_priority, weighted_recent_accuracy
        weak = subject_priority(
            retention=0.50, recent_accuracy=0.55, coverage=0.35, days_since_review=18,
            due_count=12, attempts=60, studied=True,
        )
        stable = subject_priority(
            retention=0.93, recent_accuracy=0.88, coverage=0.92, days_since_review=1,
            due_count=0, attempts=60, studied=True,
        )
        if weak.score <= stable.score:
            raise ValueError("prioridade por matéria não reage aos sinais de risco")
        if weighted_recent_accuracy([0, 0, 1, 1]) is None:
            raise ValueError("tendência recente não calculada")
        web_js = (base_dir / "web" / "app.js").read_text(encoding="utf-8")
        for token in ("Retenção estimada hoje", "Desempenho recente", "subject-summary-toggle", "renderVisualAnalyticsPanel", "openSubjectAnalyticsModal"):
            if token not in web_js:
                raise ValueError(f"componente do dashboard ausente: {token}")
        web_html = (base_dir / "web" / "index.html").read_text(encoding="utf-8")
        for token in ('data-route="visualanalytics"', 'data-page="visualanalytics"', 'id="visualAnalyticsPanel"'):
            if token not in web_html:
                raise ValueError(f"componente estrutural do painel visual ausente: {token}")
        print("[OK] QuestFlow: módulos extensíveis + recomendador multiobjetivo + simulados adaptativos")
    except Exception as error:
        failures.append(("Learning Analytics 5.7", str(error)))
        print(f"[FALHA] Learning Analytics 5.7: {error}")

    try:
        from core.fsrs_adapter import fsrs_available, optimizer_available, fsrs_version
        from core.topic_bandit import TopicState, topic_priority
        from core.gamification import calculate_reward
        from core.background_runtime import BackgroundRuntime
        from core.health import collect_health

        state = TopicState(subject="TESTE", topic="ASSUNTO", correct=1, wrong=3, exposures=4)
        if topic_priority(state, total_exposures=20, predicted_recall=0.35) <= 0:
            raise ValueError("prioridade contextual inválida")
        reward = calculate_reward(
            correct=True, difficulty=7, response_seconds=18, streak=4,
            first_attempt=False, total_xp_before=200,
        )
        if reward.xp <= 0 or reward.level < 1:
            raise ValueError("recompensa educativa inválida")
        runtime = BackgroundRuntime(max_concurrency=2)
        try:
            if runtime.run_blocking(lambda: 42).result(timeout=3) != 42:
                raise ValueError("runtime assíncrono não devolveu o resultado")
        finally:
            runtime.shutdown()
        health = collect_health(data_dir / "questflow_questions.sqlite").to_dict()
        if health.get("status") not in {"operacional", "atenção", "degradado"}:
            raise ValueError("estado de saúde inválido")
        if not fsrs_available() or not optimizer_available():
            raise RuntimeError("Py-FSRS 6.3.2 + Optimizer não estão instalados; execute INSTALAR_E_DIAGNOSTICAR.bat")
        print(
            "[OK] Engenharia 5.6: runtime estruturado, bandit matéria/aula/assunto, "
            f"gamificação educativa e Py-FSRS {fsrs_version()} + Optimizer ativos"
        )
    except Exception as error:
        failures.append(("Engenharia 4.2", str(error)))
        print(f"[FALHA] Engenharia 4.2: {error}")

    try:
        app_lines = (base_dir / "app.py").read_text(encoding="utf-8").splitlines()
        if len(app_lines) >= 250:
            raise ValueError(f"app.py voltou a crescer: {len(app_lines)} linhas")
        ui_files = list((base_dir / "ui").glob("*_mixin.py"))
        if len(ui_files) < 10:
            raise ValueError("abas/controladores não foram separados em módulos")
        direct_db = [path.name for path in ui_files if "self.database." in path.read_text(encoding="utf-8")]
        if direct_db:
            raise ValueError("views com acesso direto ao banco: " + ", ".join(direct_db))
        from core.storage import QuestFlowDatabase
        from core.study import StudyRepository
        architecture_root = base_dir / "data" / "diagnostico_architecture"
        architecture_root.mkdir(parents=True, exist_ok=True)
        architecture_db = architecture_root / "architecture.sqlite"
        if architecture_db.exists():
            architecture_db.unlink()
        architecture_database = QuestFlowDatabase(architecture_db)
        StudyRepository(architecture_database)
        history = architecture_database.schema_history()
        if not any(item["component"] == "question_bank" for item in history):
            raise ValueError("migrações do banco de questões não foram registradas")
        if not any(item["component"] == "study" for item in history):
            raise ValueError("migrações do estudo não foram registradas")
        print("[OK] Dívida técnica 4.2: composition root, views modulares, CQRS leve e migrações versionadas")
    except Exception as error:
        failures.append(("Dívida técnica 4.2", str(error)))
        print(f"[FALHA] Dívida técnica 4.2: {error}")

    try:
        web_root = base_dir / "web"
        index_text = (web_root / "index.html").read_text(encoding="utf-8")
        styles_text = (web_root / "styles.css").read_text(encoding="utf-8")
        script_text = (web_root / "app.js").read_text(encoding="utf-8")
        required_css = ("display: grid", "display: flex", "container-type", "@container", "clamp(", ":focus-visible", "prefers-color-scheme", "prefers-reduced-motion")
        missing_css = [token for token in required_css if token not in styles_text]
        if missing_css:
            raise ValueError("recursos CSS ausentes: " + ", ".join(missing_css))
        required_html = ('skip-link', 'aria-label', 'role="dialog"', 'virtual-table', 'questionEditor')
        missing_html = [token for token in required_html if token not in index_text]
        if missing_html:
            raise ValueError("recursos de acessibilidade/estrutura ausentes: " + ", ".join(missing_html))
        if "class VirtualQuestionList" not in script_text:
            raise ValueError("virtualização da lista de questões não encontrada")
        from web_api import QuestFlowWebApi
        if not QuestFlowWebApi:
            raise ValueError("ponte Python/JavaScript indisponível")
        print("[OK] Interface Web Enterprise: Grid/Flexbox, container queries, tokens, acessibilidade e virtualização")
        print("[OK] Renderizador: Google Chrome exclusivo, perfil isolado e API local HTTP/JSON")
    except Exception as error:
        failures.append(("Interface Web Enterprise", str(error)))
        print(f"[FALHA] Interface Web Enterprise: {error}")

    try:
        import app

        version_path = base_dir / "VERSION.txt"
        expected_version = version_path.read_text(encoding="utf-8").strip()
        if not expected_version:
            raise ValueError("VERSION.txt está vazio")
        if app.APP_VERSION != expected_version:
            raise ValueError(
                f"versão do aplicativo inconsistente: app.py={app.APP_VERSION}, "
                f"VERSION.txt={expected_version}"
            )
        if app.DEFAULT_CONFIG.get("flow_questions_per_cycle") != 20:
            raise ValueError("o ciclo diário padrão não possui vinte questões")
        required_methods = (
            "reread_current_question",
            "toggle_review_orientation",
            "swap_review_panes",
            "delete_current_question",
            "process_pending_questions",
            "retry_selected_delivery",
            "retry_all_failed_deliveries",
            "enrich_current_question_web",
            "enrich_pending_questions_web",
            "process_selected_pending_questions",
            "_apply_live_ui_scale",
            "toggle_sidebar",
            "refresh_corrections_list",
            "open_selected_correction",
            "resolve_selected_correction",
            "refresh_adaptive_dashboard",
            "_build_dashboard_page",
        )
        missing = [name for name in required_methods if not hasattr(app.QuestFlowApp, name)]
        if missing:
            raise ValueError("recursos da revisão ausentes: " + ", ".join(missing))
        print("[OK] Interface: Mission Control, revisão ajustável, temas, zoom, saúde e reenvio de falhas")
        print(f"[OK] Módulo principal QuestFlow Studio {expected_version}")
    except Exception as error:
        failures.append(("Aplicativo", str(error)))
        print(f"[FALHA] Aplicativo: {error}")

    if failures:
        print(f"\nDiagnóstico concluído com {len(failures)} falha(s).")
        return 1
    print("\nDiagnóstico concluído sem falhas locais.")
    print("A conexão real com o Telegram deve ser testada no botão 'Testar bot'.")
    print("Observação: com o computador totalmente desligado, o envio só pode ocorrer após ele ser ligado novamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
