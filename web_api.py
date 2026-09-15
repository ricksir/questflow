from __future__ import annotations

import base64
import io
import copy
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from app_shared import (
    APP_NAME,
    APP_VERSION,
    BASE_DIR,
    CONFIG_PATH,
    DATABASE_PATH,
    MARKDOWN_CACHE_DIR,
    QUESTION_IMAGE_DIR,
    TAXONOMY_PATH,
    TRAIL_GUIDES_PATH,
    load_config,
    save_config,
)
# Core modules are imported lazily by ``_ensure_core``. The former eager
# imports loaded the database, adaptive engine, Telegram flow and extraction
# helpers before pywebview could create its native window. On Windows that made
# the application appear frozen even though the first real query was fast.


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def _safe_int(value: Any, default: int | None = None) -> int | None:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _question_summary(question: dict) -> dict:
    review = question.get("revisao", {}) if isinstance(question.get("revisao"), dict) else {}
    return {
        "uid": str(question.get("database_uid") or question.get("uid") or ""),
        "codigo": str(question.get("codigo_origem") or question.get("source_code") or ""),
        "materia": str(question.get("materia") or question.get("subject") or ""),
        "aula": str(question.get("aula_planilha") or question.get("lesson") or ""),
        "titulo_aula": str(question.get("titulo_aula") or question.get("lesson_title") or ""),
        "assunto": str(question.get("assunto") or question.get("primary_topic") or ""),
        "ano": question.get("ano") or question.get("exam_year") or "",
        "banca": str(question.get("banca") or question.get("board") or ""),
        "arquivo": str(question.get("source_file") or (question.get("fonte", {}).get("arquivo", "") if isinstance(question.get("fonte"), dict) else "")),
        "pagina": question.get("source_page") or (question.get("fonte", {}).get("pagina_inicial") if isinstance(question.get("fonte"), dict) else ""),
        "status": str(review.get("status") or question.get("review_status") or "pendente"),
        "origem": str(question.get("origem_questao") or question.get("origin_type") or "nao_informada"),
        "curadoria": str(question.get("curation_status") or "revisar"),
        "qualidade": float(question.get("quality_score") or 0),
        "dificuldade": str(question.get("difficulty_label") or "sem_dados"),
        "comentario_origem": str(question.get("commentary_source") or "sem_comentario"),
        "enunciado": str(question.get("enunciado") or question.get("statement") or ""),
        "has_image": bool(
            isinstance(question.get("imagem_questao"), dict)
            and str(question.get("imagem_questao", {}).get("path", "")).strip()
        ),
    }


class QuestFlowWebApi:
    """Bridge between the responsive web UI and the existing QuestFlow core.

    The business rules remain in ``core``. This class only validates data crossing
    the JavaScript/Python boundary and orchestrates long-running jobs.
    """

    def __init__(
        self,
        database_path: str | Path = DATABASE_PATH,
        *,
        config: dict | None = None,
        config_path: str | Path = CONFIG_PATH,
        taxonomy_path: str | Path = TAXONOMY_PATH,
        trail_guides_path: str | Path | None = None,
    ) -> None:
        self._startup_started_at = time.perf_counter()
        self._startup_log_path = Path(database_path).parent / "startup_performance.log"
        self._log_startup("bridge_created")
        self.window = None
        self.mobile_server_info: dict[str, Any] = {"enabled": False, "urls": [], "restart_required": False}
        self.database_path = Path(database_path)
        self.taxonomy_path = Path(taxonomy_path)
        self.trail_guides_path = Path(trail_guides_path) if trail_guides_path else self.database_path.parent / TRAIL_GUIDES_PATH.name
        self.config_path = Path(config_path)
        self.config = dict(config) if config is not None else load_config()
        legacy_telegram_token_present = bool(str(self.config.get("telegram_bot_token") or "").strip())
        # 6.4.1: keep the Telegram token in memory for Flow, but migrate/remove
        # any legacy clear-text copy from config.json and hydrate the protected
        # Windows-DPAPI value when available.
        try:
            from core.telegram_secrets import hydrate_and_migrate
            hydrate_and_migrate(self.config, self.config_path)
        except Exception:
            pass
        if legacy_telegram_token_present:
            # Persist immediately so an old clear-text token is removed even if
            # the user closes the application without opening Settings.
            try:
                disk_config = dict(self.config)
                disk_config.pop("telegram_bot_token", None)
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                self.config_path.write_text(json.dumps(disk_config, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass
        self.taxonomy = None
        self.database = None
        self.queries = None
        self.commands = None
        self.study = None
        self.flow = None
        self.cloud_sync = None
        self.cloud_sync_service = None
        self.engines = None
        self.architecture_kernel = None
        self.question_catalog = None
        self.use_cases = None
        self.retrieval_health = None
        self.mobile_foundation = None
        self.mobile_cloud_bridge = None
        self.mobile_cloud_bridge_service = None
        self._core_lock = threading.RLock()
        self._coverage_sync_lock = threading.Lock()
        self._core_ready = threading.Event()
        self._core_started = False
        self._core_error: BaseException | None = None
        self.flow_events: list[dict] = []
        self._flow_events_lock = threading.RLock()
        self._flow_event_base_cursor = 0
        # HTTP/JSON requests, SQLite reads and network operations can progress
        # independently. Keep a bounded pool sized from the actual machine so
        # low-end computers are not saturated and stronger CPUs are used.
        cpu_count = max(2, int(os.cpu_count() or 4))
        self.executor = ThreadPoolExecutor(
            max_workers=min(12, max(4, cpu_count + 2)),
            thread_name_prefix="questflow-worker",
        )
        from core.background_runtime import BackgroundRuntime
        self.background_runtime = BackgroundRuntime(
            max_concurrency=max(2, min(12, int(self.config.get("runtime_io_max_concurrency", 4) or 4)))
        )
        self._runtime_server = None
        self.runtime_supervisor = None
        self._watchdog_last_db_full_check = 0.0
        self._watchdog_db_quick_check = "não executado"
        self.tasks: dict[str, dict] = {}
        self.task_lock = threading.RLock()
        self._active_task_by_kind: dict[str, str] = {}
        self._task_history_limit = max(64, min(1000, int(self.config.get("runtime_task_history_limit", 160) or 160)))
        self._shutdown = False
        self._close_requested = threading.Event()
        self._shutdown_report: dict[str, Any] = {}
        self._services_thread: threading.Thread | None = None
        self._watchdog_flow_expected = False
        self._initial_dashboard_ready = threading.Event()
        self._dashboard_cache_path = self.database_path.parent / "dashboard_cache.json"
        self._dashboard_cache_lock = threading.RLock()
        self._dashboard_cache = self._load_dashboard_cache()
        self._log_startup("bridge_ready")

    def _ensure_core(self, timeout: float = 90.0) -> None:
        """Initialize all heavy services once, outside the native UI thread.

        The first background task becomes the initializer. Concurrent calls
        wait on an event instead of constructing duplicate repositories or
        racing schema migrations. Direct API calls from tests and the classic
        compatibility paths remain supported.
        """
        if self._core_ready.is_set():
            if self._core_error is not None:
                raise RuntimeError(f"Falha ao inicializar o núcleo: {self._core_error}") from self._core_error
            return

        initializer = False
        with self._core_lock:
            if not self._core_started:
                self._core_started = True
                initializer = True

        if initializer:
            self._log_startup("core_init_started")
            try:
                from core.flow import CyclicStudyEngine
                from core.question_services import QuestionCommandService, QuestionQueryService
                from core.spreadsheet_taxonomy import SpreadsheetTaxonomy
                from core.storage import QuestFlowDatabase
                from core.study import StudyRepository

                try:
                    taxonomy = SpreadsheetTaxonomy.load(self.taxonomy_path)
                except Exception as error:
                    taxonomy = None
                    self._log_startup("taxonomy_unavailable", str(error))

                database = QuestFlowDatabase(self.database_path)
                queries = QuestionQueryService(database)
                commands = QuestionCommandService(database)
                study = StudyRepository(database)
                study.set_learning_preferences(
                    target_retention=float(self.config.get("flow_target_retention", 0.88) or 0.88),
                    retention_mode=str(self.config.get("flow_target_retention_mode", "optimized") or "optimized"),
                    exam_date=str(self.config.get("flow_exam_date", "") or ""),
                    daily_minutes=int(self.config.get("flow_daily_study_minutes", 45) or 45),
                    maximum_interval_days=int(self.config.get("flow_fsrs_max_interval_days", 365) or 365),
                    relearning_minutes=int(self.config.get("flow_relearning_minutes", 10) or 10),
                    studied_only=bool(self.config.get("flow_studied_only", True)),
                    early_review_enabled=bool(self.config.get("flow_early_review_enabled", False)),
                )
                if taxonomy is not None:
                    study.refresh_studied_scope(taxonomy.tasks)
                flow = CyclicStudyEngine(
                    database,
                    study,
                    lambda: dict(self.config),
                    self._on_flow_event,
                )
                from core.cloud_sync import CloudSyncEngine
                cloud_sync = CloudSyncEngine(
                    self.database_path,
                    config=self.config,
                    config_path=self.config_path,
                    reset_callback=study.reset_progress,
                )
                from core.engines import EngineRegistry
                engines = EngineRegistry.build(database=database, queries=queries, commands=commands, study=study)
                engines.ai.api = self
                from core.architecture import ArchitectureKernel
                architecture_kernel = ArchitectureKernel(database, engines=engines, study=study)
                from core.modules.question_catalog import QuestionCatalogService
                question_catalog = QuestionCatalogService(
                    queries,
                    config=self.config,
                    config_path=self.config_path,
                )
                from core.application import StudioUseCaseDispatcher
                use_cases = StudioUseCaseDispatcher(
                    catalog=question_catalog,
                    architecture=architecture_kernel,
                    persist_config=self._persist_config,
                    present_question=self._present_question_detail,
                    create_question=self._create_manual_question_record,
                    save_question=self._save_question_record,
                    delete_question=self._delete_question_record,
                    annul_question=self._annul_question_record,
                    remove_image=self._remove_image_record,
                    list_subjects=self._list_materias_data,
                )
                # 6.11.0: Observabilidade/Quality Gates saem do AI Engine e passam
                # a um serviço de controle dedicado com worker serial e Snapshot Store.
                from core.retrieval_health_service import RetrievalHealthService
                retrieval_health = RetrievalHealthService(
                    knowledge=engines.knowledge,
                    governance=engines.governance,
                    editorial=engines.editorial,
                    calibration_store=engines.knowledge.retrieval_calibration_store,
                    root=engines.knowledge.retrieval_calibration_store.root,
                )
                from core.mobile_foundation import MobileFoundationService
                mobile_foundation = MobileFoundationService(
                    database,
                    study,
                    control_plane_path=self.database_path.parent / "mobile_control_plane.sqlite",
                )
                mobile_foundation.projection_scheduler = lambda: self.executor.submit(
                    mobile_foundation.process_pending_attempt_projections
                )
                # Retoma projeções que possam ter ficado pendentes após um
                # encerramento inesperado, sem atrasar a inicialização da UI.
                mobile_foundation.schedule_projection_drain()
                # O Mobile cria seu log imutável depois do kernel; instale agora
                # os capturadores seletivos de eventos de aprendizagem.
                architecture_kernel.event_store.install_capture_triggers()
                from core.mobile_cloud_bridge import MobileCloudBridgeEngine
                mobile_cloud_bridge = MobileCloudBridgeEngine(
                    mobile_foundation,
                    config=self.config,
                    config_path=self.config_path,
                )
                mobile_foundation.cloud_bridge_provider = mobile_cloud_bridge.client_projection
                def _wake_mobile_cloud_bridge() -> None:
                    if self.mobile_cloud_bridge_service is not None:
                        self.mobile_cloud_bridge_service.wake()
                        return
                    if mobile_cloud_bridge.enabled():
                        threading.Thread(
                            target=mobile_cloud_bridge.publish,
                            daemon=True,
                            name="questflow-mobile-cloud-pairing-publish",
                        ).start()
                mobile_foundation.pairing_completed_callback = _wake_mobile_cloud_bridge
                # O Banco Editorial 6.5 cria as tabelas de Projeto/Edital durante
                # o registro dos motores. Reinstale apenas os triggers locais
                # para que esses novos dados também entrem na outbox Turso.
                cloud_sync.initialize_local()

                with self._core_lock:
                    self.taxonomy = taxonomy
                    self.database = database
                    self.queries = queries
                    self.commands = commands
                    self.study = study
                    self.flow = flow
                    self.cloud_sync = cloud_sync
                    self.engines = engines
                    self.architecture_kernel = architecture_kernel
                    self.question_catalog = question_catalog
                    self.use_cases = use_cases
                    self.retrieval_health = retrieval_health
                    self.mobile_foundation = mobile_foundation
                    self.mobile_cloud_bridge = mobile_cloud_bridge
                self._log_startup("core_ready")
            except BaseException as error:
                self._core_error = error
                self._log_startup("core_error", str(error))
            finally:
                self._core_ready.set()
        elif not self._core_ready.wait(timeout=max(1.0, float(timeout))):
            raise TimeoutError("O núcleo do QuestFlow ainda está sendo preparado.")

        if self._core_error is not None:
            raise RuntimeError(f"Falha ao inicializar o núcleo: {self._core_error}") from self._core_error

    def _start_core_background(self) -> None:
        if self._core_ready.is_set() or self._core_started:
            return

        def initialize() -> None:
            try:
                self._ensure_core()
            except Exception as error:
                self._on_flow_event("error", message=str(error))

        threading.Thread(
            target=initialize,
            daemon=True,
            name="questflow-core-init",
        ).start()

    # -------------------------- lifecycle and bridge -----------------------
    def set_window(self, window: Any) -> None:
        self.window = window

    def set_mobile_server_info(self, info: dict[str, Any]) -> None:
        self.mobile_server_info = dict(info or {})

    def _refresh_mobile_server_info(self) -> dict[str, Any]:
        info = dict(self.mobile_server_info or {})
        runtime = getattr(self, "_runtime_server", None)
        if runtime is not None and bool(info.get("enabled", False)):
            try:
                network = runtime.mobile_network_info()
                api_urls = list(network.get("api_urls") or [])
                info.update({
                    "api_urls": api_urls,
                    "urls": [f"{base}/index.html?qf_token={runtime.token}" for base in api_urls],
                    "preferred_ip": str(network.get("preferred_ip") or ""),
                    "addresses": list(network.get("addresses") or []),
                    "network_detected_at": network.get("detected_at"),
                    "network_dynamic": True,
                })
                self.mobile_server_info = info
            except Exception:
                pass
        return info

    def get_mobile_cloud_bridge_settings(self) -> dict:
        self._ensure_core()
        if self.mobile_cloud_bridge is None:
            return {"ok": False, "error": "Mobile Cloud Bridge indisponível."}
        return {
            "ok": True,
            "settings": _jsonable(self.mobile_cloud_bridge.settings()),
            "status": _jsonable(self.mobile_cloud_bridge.safe_status()),
        }

    def save_mobile_cloud_bridge_settings(self, payload: dict) -> dict:
        from core.mobile_cloud_bridge import clear_bridge_key, save_bridge_key
        payload = dict(payload or {})
        enabled = bool(payload.get("mobile_cloud_bridge_enabled", self.config.get("mobile_cloud_bridge_enabled", False)))
        url = str(payload.get("mobile_cloud_bridge_url", self.config.get("mobile_cloud_bridge_url", "")) or "").strip().rstrip("/")
        interval = max(15, min(900, int(payload.get("mobile_cloud_bridge_interval_seconds", self.config.get("mobile_cloud_bridge_interval_seconds", 30)) or 30)))
        pack_size = max(8, min(100, int(payload.get("mobile_cloud_bridge_pack_size", self.config.get("mobile_cloud_bridge_pack_size", 40)) or 40)))
        self.config.update({
            "mobile_cloud_bridge_enabled": enabled,
            "mobile_cloud_bridge_url": url,
            "mobile_cloud_bridge_interval_seconds": interval,
            "mobile_cloud_bridge_pack_size": pack_size,
        })
        if bool(payload.get("mobile_cloud_bridge_clear_key")):
            clear_bridge_key(self.config_path)
        key = str(payload.get("mobile_cloud_bridge_key", "") or "").strip()
        if key:
            try:
                save_bridge_key(self.config_path, key)
            except Exception as error:
                return {"ok": False, "error": f"Não foi possível proteger a chave do Mobile Cloud Bridge: {error}"}
        self._persist_config()
        if self.mobile_cloud_bridge is not None:
            self.mobile_cloud_bridge.config = self.config
            try:
                from core.mobile_cloud_bridge import MobileCloudBridgeService
                if enabled:
                    if self.mobile_cloud_bridge_service is None:
                        self.mobile_cloud_bridge_service = MobileCloudBridgeService(self.mobile_cloud_bridge)
                        self.mobile_cloud_bridge_service.start()
                    else:
                        self.mobile_cloud_bridge_service.wake()
                elif self.mobile_cloud_bridge_service is not None:
                    self.mobile_cloud_bridge_service.stop(flush=False, timeout=2.0)
                    self.mobile_cloud_bridge_service = None
            except Exception as error:
                self._log_startup("mobile_cloud_bridge_reconfigure_error", str(error))
        return self.get_mobile_cloud_bridge_settings()

    def test_mobile_cloud_bridge(self) -> dict:
        self._ensure_core()
        if self.mobile_cloud_bridge is None:
            return {"ok": False, "error": "Mobile Cloud Bridge indisponível."}
        try:
            return {"ok": True, "result": _jsonable(self.mobile_cloud_bridge.test_remote()), "status": _jsonable(self.mobile_cloud_bridge.safe_status())}
        except Exception as error:
            return {"ok": False, "error": str(error), "status": _jsonable(self.mobile_cloud_bridge.safe_status())}

    def sync_mobile_cloud_bridge_now(self) -> dict:
        self._ensure_core()
        if self.mobile_cloud_bridge is None:
            return {"ok": False, "error": "Mobile Cloud Bridge indisponível."}
        return _jsonable(self.mobile_cloud_bridge.sync_once())

    def get_mobile_cloud_bridge_status(self) -> dict:
        self._ensure_core()
        if self.mobile_cloud_bridge is None:
            return {"ok": False, "error": "Mobile Cloud Bridge indisponível."}
        return {"ok": True, "status": _jsonable(self.mobile_cloud_bridge.safe_status())}

    def get_mobile_access(self) -> dict:
        payload = {"ok": True, **_jsonable(self._refresh_mobile_server_info())}
        try:
            self._ensure_core()
            if self.mobile_foundation is not None:
                payload["foundation"] = _jsonable(self.mobile_foundation.status())
        except Exception as error:
            payload["foundation"] = {"ok": False, "error": str(error)}
        return payload

    def get_mobile_foundation_status(self) -> dict:
        self._ensure_core()
        if self.mobile_foundation is None:
            return {"ok": False, "error": "Fundação mobile indisponível."}
        return _jsonable(self.mobile_foundation.status())

    def get_learning_analytics_v2(self, exam_project_id: str = "", range_value: str = "all", grain: str = "attempt") -> dict:
        """Shared, source-backed analytics projection for Studio and Mobile."""
        self._ensure_core()
        if self.mobile_foundation is None:
            return {"ok": False, "error": "Fundação mobile indisponível."}
        try:
            return {
                "ok": True,
                "analytics": _jsonable(
                    self.mobile_foundation.analytics_projection(
                        str(exam_project_id or ""),
                        range_value=str(range_value or "all"),
                        grain=str(grain or "attempt"),
                    )
                ),
            }
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def get_adaptive_session_observability(self, limit: int = 12) -> dict:
        """Explicabilidade pedagógica do orquestrador, exclusiva do Studio."""
        self._ensure_core()
        if self.mobile_foundation is None:
            return {"ok": False, "error": "Fundação mobile indisponível."}
        service = self.mobile_foundation.adaptive_sessions
        return {
            "ok": True,
            "recent_decisions": _jsonable(service.recent_decisions(limit=max(1, min(50, int(limit or 12))))),
            "evaluation": _jsonable(service.evaluation_readiness()),
        }

    def explain_adaptive_question(self, question_uid: str, session_id: str = "") -> dict:
        self._ensure_core()
        if self.mobile_foundation is None:
            return {"ok": False, "error": "Fundação mobile indisponível."}
        try:
            return {"ok": True, "explanation": _jsonable(self.mobile_foundation.adaptive_sessions.explain_question(question_uid, session_id=session_id))}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def create_mobile_pairing(self) -> dict:
        self._ensure_core()
        if self.mobile_foundation is None:
            return {"ok": False, "error": "Fundação mobile indisponível."}
        pairing = _jsonable(self.mobile_foundation.create_pairing())
        server_info = self._refresh_mobile_server_info()
        api_urls = [str(item).rstrip("/") for item in list(server_info.get("api_urls") or []) if str(item).strip()]
        api_base_url = str(api_urls[0] if api_urls else "")
        pairing_uri = f"questflow://pair?api=v1&token={quote(str(pairing.get('pairing_token') or ''))}"
        for api_url in api_urls:
            pairing_uri += f"&server={quote(api_url, safe='')}"
        cloud_bridge = self.mobile_cloud_bridge.client_projection() if self.mobile_cloud_bridge is not None else {}
        cloud_url = str(cloud_bridge.get("base_url") or "").strip().rstrip("/") if cloud_bridge.get("enabled") else ""
        if cloud_url:
            pairing_uri += f"&cloud={quote(cloud_url, safe='')}"
        pairing["cloud_bridge"] = cloud_bridge
        pairing["cloud_base_url"] = cloud_url
        pairing["api_base_url"] = api_base_url
        pairing["api_base_urls"] = api_urls
        pairing["preferred_ip"] = str(server_info.get("preferred_ip") or "")
        pairing["network_dynamic"] = True
        pairing["requires_manual_server"] = not bool(api_base_url)
        pairing["pairing_uri"] = pairing_uri
        pairing["qr_data_uri"] = ""
        try:
            import qrcode

            image = qrcode.make(pairing_uri)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            pairing["qr_data_uri"] = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
        except Exception:
            # O token textual continua sendo um fallback seguro e de curta duração.
            pass
        return {"ok": True, "pairing": pairing}

    def disconnect_mobile_device(self, device_id: str) -> dict:
        self._ensure_core()
        if self.mobile_foundation is None:
            return {"ok": False, "error": "Fundação mobile indisponível."}
        return _jsonable(self.mobile_foundation.disconnect_device(str(device_id or "")))

    def forget_mobile_device(self, device_id: str) -> dict:
        self._ensure_core()
        if self.mobile_foundation is None:
            return {"ok": False, "error": "Fundação mobile indisponível."}
        return _jsonable(self.mobile_foundation.forget_device(str(device_id or "")))

    def revoke_mobile_device(self, device_id: str) -> dict:
        # Compatibilidade com clientes/JS da 6.9.4; a UI nova usa "desconectar".
        return self.disconnect_mobile_device(device_id)

    def mobile_http_request(
        self,
        method: str,
        path: str,
        headers: Any,
        body: dict | None = None,
        query: dict[str, list[str]] | None = None,
    ) -> tuple[int, dict]:
        self._ensure_core()
        if self.mobile_foundation is None:
            return 503, {"ok": False, "error": "Fundação mobile indisponível."}
        return self.mobile_foundation.http_request(
            method=str(method or "GET"), path=str(path or ""), headers=headers, body=body or {}, query=query or {}
        )

    def attach_local_server(self, server: Any) -> None:
        """Attach the loopback server so the watchdog can observe transport health."""
        self._runtime_server = server

    def _watchdog_database_health(self) -> dict:
        started = time.perf_counter()
        try:
            connection = sqlite3.connect(self.database_path, timeout=1.5)
            try:
                connection.execute("SELECT 1").fetchone()
                try:
                    migration_rows = connection.execute(
                        "SELECT component, MAX(version) FROM schema_migrations GROUP BY component"
                    ).fetchall()
                    schema_versions = {str(row[0]): int(row[1] or 0) for row in migration_rows}
                except sqlite3.Error:
                    schema_versions = {}
                now = time.monotonic()
                if now - self._watchdog_last_db_full_check >= 300.0:
                    row = connection.execute("PRAGMA quick_check(1)").fetchone()
                    self._watchdog_db_quick_check = str(row[0] if row else "desconhecido")
                    self._watchdog_last_db_full_check = now
            finally:
                connection.close()
            latency = round((time.perf_counter() - started) * 1000.0, 2)
            quick_ok = str(self._watchdog_db_quick_check).casefold() in {"ok", "não executado"}
            return {
                "ok": quick_ok and latency < 1500.0,
                "state": "healthy" if quick_ok and latency < 500.0 else "degraded",
                "latency_ms": latency,
                "quick_check": self._watchdog_db_quick_check,
                "database_exists": self.database_path.exists(),
                "schema_versions": schema_versions,
                "wal_mb": round(Path(str(self.database_path) + "-wal").stat().st_size / 1048576, 2) if Path(str(self.database_path) + "-wal").exists() else 0.0,
            }
        except Exception as error:
            return {"ok": False, "state": "failed", "error": str(error)}

    def _watchdog_http_health(self) -> dict:
        server = self._runtime_server
        if server is None:
            return {"ok": False, "state": "initializing", "error": "Servidor local ainda não anexado."}
        try:
            return dict(server.runtime_health())
        except Exception as error:
            return {"ok": False, "state": "degraded", "error": str(error)}

    def _watchdog_task_health(self) -> dict:
        now = datetime.now(timezone.utc)
        stalled_limit = max(30.0, float(self.config.get("watchdog_task_stall_seconds", 240) or 240))
        running: list[dict[str, Any]] = []
        stalled: list[dict[str, Any]] = []
        with self.task_lock:
            items = [copy.deepcopy(item) for item in self.tasks.values() if item.get("status") in {"queued", "running"}]
        for item in items:
            stamp = str(item.get("updated_at") or item.get("created_at") or "")
            try:
                age = max(0.0, (now - datetime.fromisoformat(stamp)).total_seconds()) if stamp else 0.0
            except Exception:
                age = 0.0
            compact = {"id": item.get("id"), "kind": item.get("kind"), "status": item.get("status"), "age_seconds": round(age, 1), "message": item.get("message", "")}
            running.append(compact)
            if age > stalled_limit:
                stalled.append(compact)
        return {
            "ok": not stalled,
            "state": "healthy" if not stalled else "degraded",
            "active": len(running),
            "stalled": stalled[:10],
            "history_limit": self._task_history_limit,
        }

    def _watchdog_engine_health(self) -> dict:
        if self.engines is None:
            return {"ok": True, "state": "initializing", "engine_count": 0}
        architecture = self.engines.architecture()
        # O watchdog verifica disponibilidade, não uma contagem arquitetural fixa.
        # Extensões registradas passam a participar automaticamente do health check.
        count = int(architecture.get("engine_count", 0) or 0)
        ok = bool(architecture.get("all_ready")) and count > 0
        return {
            "ok": ok,
            "state": "healthy" if ok else "degraded",
            "engine_count": architecture.get("engine_count", 0),
            "all_ready": architecture.get("all_ready", False),
        }

    def _ensure_runtime_supervisor(self) -> None:
        if self.runtime_supervisor is not None:
            return
        from core.runtime_supervisor import RuntimeSupervisor, ServiceSpec
        supervisor = RuntimeSupervisor(
            config=self.config,
            journal_path=self.database_path.parent / "runtime_watchdog.jsonl",
            interval_seconds=float(self.config.get("watchdog_interval_seconds", 5) or 5),
        )
        supervisor.register(ServiceSpec(
            name="local_http", label="Servidor local e interface", health_check=self._watchdog_http_health,
            critical=True, failure_threshold=2,
        ))
        supervisor.register(ServiceSpec(
            name="sqlite", label="SQLite local", health_check=self._watchdog_database_health,
            critical=True, failure_threshold=2,
        ))
        supervisor.register(ServiceSpec(
            name="async_runtime", label="Runtime assíncrono", health_check=self.background_runtime.health,
            recover=self.background_runtime.restart, critical=False, failure_threshold=2, recovery_cooldown=20.0,
        ))
        supervisor.register(ServiceSpec(
            name="task_runtime", label="Fila de tarefas", health_check=self._watchdog_task_health,
            critical=False, failure_threshold=2,
        ))
        supervisor.register(ServiceSpec(
            name="domain_modules", label="Módulos de domínio QuestFlow", health_check=self._watchdog_engine_health,
            critical=True, failure_threshold=2,
        ))
        supervisor.register(ServiceSpec(
            name="retrieval_health", label="Observabilidade e Quality Gates",
            health_check=lambda: self.retrieval_health.health() if self.retrieval_health is not None else {"ok": False, "state": "initializing"},
            critical=False, failure_threshold=2,
        ))
        supervisor.register(ServiceSpec(
            name="cloud_sync", label="Cloud Sync / Turso",
            health_check=lambda: self.cloud_sync_service.health() if self.cloud_sync_service is not None else {"ok": True, "state": "disabled"},
            recover=lambda: self.cloud_sync_service.restart() if self.cloud_sync_service is not None else {"ok": False, "error": "Cloud Sync não iniciado."},
            enabled=lambda: bool(self.cloud_sync is not None and self.cloud_sync.auto_sync_allowed()),
            failure_threshold=2, recovery_cooldown=30.0,
        ))
        supervisor.register(ServiceSpec(
            name="telegram", label="Telegram e agendador",
            health_check=lambda: self.flow.runtime_health() if self.flow is not None else {"ok": False, "state": "initializing"},
            recover=lambda: self.flow.recover_runtime() if self.flow is not None else {"ok": False},
            enabled=lambda: bool(self._watchdog_flow_expected and str(self.config.get("telegram_bot_token", "")).strip() and str(self.config.get("telegram_chat_id", "")).strip()),
            failure_threshold=2, recovery_cooldown=30.0,
        ))
        self.runtime_supervisor = supervisor
        supervisor.start()

    def get_runtime_watchdog_status(self) -> dict:
        self._ensure_runtime_supervisor()
        from core.compatibility import compatibility_report
        from core.rate_limiter import rate_limit_status
        return {
            "ok": True,
            "watchdog": _jsonable(self.runtime_supervisor.snapshot() if self.runtime_supervisor is not None else {}),
            "compatibility": _jsonable(compatibility_report()),
            "rate_limits": _jsonable(rate_limit_status()),
        }

    def run_runtime_watchdog_check(self) -> dict:
        self._ensure_runtime_supervisor()
        assert self.runtime_supervisor is not None
        return {"ok": True, "watchdog": _jsonable(self.runtime_supervisor.check_once(auto_recover=False))}

    def restart_runtime_service(self, name: str) -> dict:
        self._ensure_runtime_supervisor()
        assert self.runtime_supervisor is not None
        return _jsonable(self.runtime_supervisor.restart_service(str(name or ""), manual=True))

    def save_runtime_watchdog_settings(self, payload: dict | None = None) -> dict:
        data = dict(payload or {})
        previous_io_concurrency = int(self.config.get("runtime_io_max_concurrency", 4) or 4)
        self.config["watchdog_enabled"] = bool(data.get("enabled", self.config.get("watchdog_enabled", True)))
        self.config["watchdog_auto_recover"] = bool(data.get("auto_recover", self.config.get("watchdog_auto_recover", True)))
        self.config["watchdog_interval_seconds"] = max(2, min(60, int(data.get("interval_seconds", self.config.get("watchdog_interval_seconds", 5)) or 5)))
        self.config["watchdog_task_stall_seconds"] = max(30, min(3600, int(data.get("task_stall_seconds", self.config.get("watchdog_task_stall_seconds", 240)) or 240)))
        self.config["runtime_io_max_concurrency"] = max(2, min(12, int(data.get("io_max_concurrency", self.config.get("runtime_io_max_concurrency", 4)) or 4)))
        self.config["runtime_task_history_limit"] = max(64, min(1000, int(data.get("task_history_limit", self.config.get("runtime_task_history_limit", 160)) or 160)))
        self.config["ai_rate_limit_per_minute"] = max(1, min(600, int(data.get("ai_rate_limit_per_minute", self.config.get("ai_rate_limit_per_minute", 30)) or 30)))
        self.config["cloud_rate_limit_per_minute"] = max(10, min(1200, int(data.get("cloud_rate_limit_per_minute", self.config.get("cloud_rate_limit_per_minute", 120)) or 120)))
        self._task_history_limit = int(self.config["runtime_task_history_limit"])
        if int(self.config["runtime_io_max_concurrency"]) != previous_io_concurrency:
            try:
                self.background_runtime.reconfigure(max_concurrency=int(self.config["runtime_io_max_concurrency"]))
            except Exception as error:
                self._on_flow_event("runtime_reconfigure_error", message=str(error))
        self._persist_config()
        if self.runtime_supervisor is not None:
            self.runtime_supervisor.interval_seconds = float(self.config["watchdog_interval_seconds"])
            if self.config["watchdog_enabled"]:
                self.runtime_supervisor.start()
                self.runtime_supervisor.wake()
            else:
                self.runtime_supervisor.stop(timeout=2.0)
        result = self.get_runtime_watchdog_status()
        result["settings"] = {
            "watchdog_enabled": self.config["watchdog_enabled"],
            "watchdog_auto_recover": self.config["watchdog_auto_recover"],
            "watchdog_interval_seconds": self.config["watchdog_interval_seconds"],
            "watchdog_task_stall_seconds": self.config["watchdog_task_stall_seconds"],
            "runtime_io_max_concurrency": self.config["runtime_io_max_concurrency"],
            "runtime_task_history_limit": self.config["runtime_task_history_limit"],
            "ai_rate_limit_per_minute": self.config["ai_rate_limit_per_minute"],
            "cloud_rate_limit_per_minute": self.config["cloud_rate_limit_per_minute"],
        }
        return result

    def start_services(self) -> None:
        """Start optional services without ever blocking the WebView message loop.

        pywebview invokes this hook when the native window loop is ready. Any
        database or network work performed synchronously here can make Windows
        label the application as "Não está respondendo". The hook therefore
        only schedules a daemon worker and returns immediately.
        """
        if self._services_thread and self._services_thread.is_alive():
            return

        def worker() -> None:
            self._log_startup("service_worker_started")
            try:
                self._ensure_core()
            except Exception as error:
                self._on_flow_event("error", message=str(error))
                self._log_startup("service_core_error", str(error))
                return
            # Give the first dashboard snapshot priority over Telegram
            # maintenance, which can open transactions and perform network I/O.
            self._initial_dashboard_ready.wait(timeout=20.0)
            if self._shutdown:
                return
            if self.cloud_sync is not None and self.cloud_sync.auto_sync_allowed():
                try:
                    from core.cloud_sync import CloudSyncService
                    self.cloud_sync_service = CloudSyncService(self.cloud_sync)
                    self.cloud_sync_service.start()
                    self._log_startup("cloud_sync_started")
                except Exception as error:
                    self._log_startup("cloud_sync_error", str(error))
            if self.mobile_cloud_bridge is not None and bool(self.config.get("mobile_cloud_bridge_enabled", False)):
                try:
                    from core.mobile_cloud_bridge import MobileCloudBridgeService
                    self.mobile_cloud_bridge_service = MobileCloudBridgeService(self.mobile_cloud_bridge)
                    self.mobile_cloud_bridge_service.start()
                    self._log_startup("mobile_cloud_bridge_started")
                except Exception as error:
                    self._log_startup("mobile_cloud_bridge_error", str(error))
            if self.config.get("telegram_bot_token") and self.config.get("telegram_chat_id"):
                try:
                    if self.flow is not None:
                        self._watchdog_flow_expected = True
                        self.flow.start(start_listener=True)
                    self._log_startup("telegram_services_started")
                except Exception as error:
                    self._on_flow_event("error", message=str(error))
                    self._log_startup("telegram_services_error", str(error))
            try:
                self._ensure_runtime_supervisor()
                self._log_startup("runtime_watchdog_started")
            except Exception as error:
                self._log_startup("runtime_watchdog_error", str(error))

        self._services_thread = threading.Thread(
            target=worker,
            daemon=True,
            name="questflow-deferred-services",
        )
        self._services_thread.start()

    def _log_startup(self, stage: str, detail: str = "") -> None:
        try:
            elapsed = time.perf_counter() - self._startup_started_at
            self._startup_log_path.parent.mkdir(parents=True, exist_ok=True)
            # Controle de histórico: startup_performance.log não cresce sem
            # limite. Mantemos apenas o arquivo atual + uma geração anterior.
            if self._startup_log_path.exists() and self._startup_log_path.stat().st_size >= 2 * 1024 * 1024:
                rotated = self._startup_log_path.with_suffix(self._startup_log_path.suffix + ".1")
                rotated.unlink(missing_ok=True)
                self._startup_log_path.replace(rotated)
            with self._startup_log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"{_utc_now()} | {elapsed:8.3f}s | {stage} | {detail}\n")
        except Exception:
            pass

    def _load_dashboard_cache(self) -> dict:
        try:
            payload = json.loads(self._dashboard_cache_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("schema") == "questflow.dashboard.cache.v1":
                data = payload.get("data")
                return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def _save_dashboard_cache(self, payload: dict) -> None:
        serializable = _jsonable(payload)
        with self._dashboard_cache_lock:
            self._dashboard_cache = dict(serializable)
            try:
                self._dashboard_cache_path.parent.mkdir(parents=True, exist_ok=True)
                temp = self._dashboard_cache_path.with_suffix(".tmp")
                temp.write_text(
                    json.dumps(
                        {
                            "schema": "questflow.dashboard.cache.v1",
                            "saved_at": _utc_now(),
                            "data": serializable,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    encoding="utf-8",
                )
                temp.replace(self._dashboard_cache_path)
            except OSError:
                pass

    def _cached_dashboard(self) -> dict:
        with self._dashboard_cache_lock:
            return copy.deepcopy(self._dashboard_cache)

    @property
    def close_requested(self) -> bool:
        return self._close_requested.is_set()

    def request_close(self) -> dict:
        """Ask the desktop runtime to perform a controlled application shutdown.

        The HTTP handler returns immediately so the UI can show a closing state. The
        desktop runtime then invokes :meth:`shutdown` from the main process thread
        before terminating the Chrome app window.
        """
        self._close_requested.set()
        return {"ok": True, "message": "Fechamento seguro solicitado."}

    def _finalize_database_safely(self, *, reason: str, cloud_result: Any = None) -> dict[str, Any]:
        report: dict[str, Any] = {
            "reason": str(reason or "runtime"),
            "closed_at": _utc_now(),
            "quick_check": "não executado",
            "checkpoint": "não executado",
            "cloud_flush": _jsonable(cloud_result),
            "pending_cloud": None,
            "clean": False,
        }
        try:
            if self.cloud_sync is not None:
                cloud_status = self.cloud_sync.safe_status()
                report["pending_cloud"] = cloud_status.get("pending")
                report["cloud_status"] = _jsonable(cloud_status)
        except Exception as error:
            report["cloud_status_error"] = str(error)

        if not self.database_path.exists():
            report["quick_check"] = "banco ausente"
            report["error"] = "O arquivo do banco local não foi encontrado durante o fechamento."
        else:
            try:
                connection = sqlite3.connect(self.database_path, timeout=6.0)
                try:
                    connection.execute("PRAGMA busy_timeout=6000")
                    try:
                        checkpoint = connection.execute("PRAGMA wal_checkpoint(FULL)").fetchone()
                        report["checkpoint"] = list(checkpoint) if checkpoint is not None else "ok"
                    except sqlite3.Error as error:
                        report["checkpoint"] = f"aviso: {error}"
                    row = connection.execute("PRAGMA quick_check").fetchone()
                    report["quick_check"] = str(row[0] if row else "sem resultado")
                    try:
                        connection.execute("PRAGMA optimize")
                    except sqlite3.Error:
                        pass
                    if report["quick_check"].lower() == "ok":
                        try:
                            truncate = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                            report["checkpoint_truncate"] = list(truncate) if truncate is not None else "ok"
                        except sqlite3.Error as error:
                            report["checkpoint_truncate"] = f"aviso: {error}"
                finally:
                    connection.close()
            except sqlite3.Error as error:
                report["error"] = str(error)

        report["clean"] = report.get("quick_check", "").lower() == "ok"
        try:
            path = self.database_path.parent / "last_clean_shutdown.json"
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(path)
        except OSError:
            pass
        self._shutdown_report = report
        return report

    def shutdown(self, reason: str = "runtime", *_args: Any) -> dict:
        if self._shutdown:
            return {"ok": True, "report": _jsonable(self._shutdown_report)}
        self._shutdown = True
        self._close_requested.set()
        self._initial_dashboard_ready.set()
        cloud_result = None
        try:
            if self.runtime_supervisor is not None:
                self.runtime_supervisor.stop(timeout=3.0)
        except Exception:
            pass
        self._watchdog_flow_expected = False
        try:
            if self.flow is not None:
                self.flow.stop()
        except Exception:
            pass
        try:
            if self.mobile_cloud_bridge_service is not None:
                self.mobile_cloud_bridge_service.stop(flush=True, timeout=8.0)
        except Exception:
            pass
        try:
            if self.cloud_sync_service is not None:
                cloud_result = self.cloud_sync_service.stop(flush=True, timeout=10.0)
        except Exception as error:
            cloud_result = {"ok": False, "error": str(error)}
        service_thread = self._services_thread
        if service_thread and service_thread.is_alive() and service_thread is not threading.current_thread():
            service_thread.join(timeout=5.0)
        try:
            if self.retrieval_health is not None:
                self.retrieval_health.shutdown(wait=False)
        except Exception:
            pass
        try:
            # Cancel work that has not started. Running SQLite transactions keep their
            # own rollback guarantees; the bounded checkpoint below waits for normal
            # writers without turning shutdown into an indefinite hang.
            self.executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            self.executor.shutdown(wait=False)
        except Exception:
            pass
        try:
            self.background_runtime.shutdown(timeout=3.0)
        except Exception:
            pass
        report = self._finalize_database_safely(reason=reason, cloud_result=cloud_result)
        return {"ok": True, "report": _jsonable(report)}

    def _on_flow_event(self, event: str, payload: dict | None = None, **extra: Any) -> None:
        merged = dict(payload or {})
        merged.update(extra)
        item = {"event": event, "at": _utc_now(), **_jsonable(merged)}
        with self._flow_events_lock:
            self.flow_events.append(item)
            overflow = max(0, len(self.flow_events) - 200)
            if overflow:
                del self.flow_events[:overflow]
                self._flow_event_base_cursor += overflow

    def poll_events(self, after: int = 0) -> dict:
        requested = max(0, int(after or 0))
        with self._flow_events_lock:
            base = self._flow_event_base_cursor
            cursor = base + len(self.flow_events)
            start = max(0, requested - base)
            if start > len(self.flow_events):
                start = len(self.flow_events)
            items = copy.deepcopy(self.flow_events[start:])
        return {"items": items, "cursor": cursor}

    # -------------------------- bootstrap/dashboard ------------------------
    def bootstrap_shell(self) -> dict:
        """Return only already-loaded metadata; never touch study tables.

        This payload lets the browser paint a usable shell immediately while
        counters and adaptive metrics are calculated in a worker thread.
        """
        cached = self._cached_dashboard()
        return _jsonable(
            {
                "app": {"name": APP_NAME, "version": APP_VERSION},
                "stats": cached.get("question_stats", {}),
                "config": self._public_config(),
                "taxonomy": {
                    "loaded": bool(self._core_ready.is_set() and self.taxonomy is not None),
                    "name": self.taxonomy.source_name if self.taxonomy else "",
                    "materias": list(self.taxonomy.materias) if self.taxonomy else [],
                    "task_count": len(self.taxonomy.tasks) if self.taxonomy else 0,
                },
                "flow": cached.get("flow") or self._flow_status(),
                "pending_reviews": cached.get("pending_reviews", 0),
                "cached_dashboard": bool(cached),
                "dashboard_preview": cached,
                "deferred": True,
            }
        )

    def start_bootstrap_load(self) -> dict:
        return self._start_task(
            "bootstrap",
            lambda task_id: self._bootstrap_worker(task_id),
            coalesce=True,
        )

    def _bootstrap_worker(self, task_id: str) -> dict:
        self._update_task(task_id, progress=0.15, message="Lendo contadores do banco…")
        payload = self.bootstrap()
        self._update_task(task_id, progress=0.95, message="Finalizando dados iniciais…")
        return payload

    def start_dashboard_load(self) -> dict:
        return self._start_task(
            "dashboard",
            lambda task_id: self._dashboard_worker(task_id),
            coalesce=True,
        )

    def _dashboard_worker(self, task_id: str) -> dict:
        started = time.perf_counter()
        self._update_task(task_id, progress=0.03, message="Preparando núcleo local…")
        try:
            self._ensure_core()
            assert self.queries is not None and self.study is not None
            self._update_task(task_id, progress=0.10, message="Lendo banco de questões…")
            question_stats = self.queries.stats()
            bank_intelligence = self.queries.bank_intelligence_summary()
            self._update_task(task_id, progress=0.25, message="Calculando progresso de estudo…")
            study_stats = self.study.stats()
            self._update_task(task_id, progress=0.48, message="Atualizando motor adaptativo…")
            adaptive = self.study.adaptive_dashboard()
            self._update_task(task_id, progress=0.66, message="Calculando calibração…")
            calibration = self.study.calibration_report()
            self._update_task(task_id, progress=0.74, message="Atualizando modelo do aluno…")
            learner_sync = self.study.ensure_learner_model_current()
            learner_model = self.study.learner_model_dashboard()
            learner_model["sync"] = learner_sync
            self._update_task(task_id, progress=0.82, message="Organizando prioridades…")
            subjects = self.study.subject_stats(limit=12)
            activity_summary = self.study.activity_summary()
            self._update_task(task_id, progress=0.90, message="Lendo atividade recente…")
            recent = self.study.recent_deliveries(limit=12)
            pending_reviews = self.study.pending_review_count()
            if self.mobile_foundation is not None:
                pending_reviews += self.mobile_foundation.pending_study_backlog_count()
            payload = _jsonable(
                {
                    "question_stats": question_stats,
                    "bank_intelligence": bank_intelligence,
                    "study_stats": study_stats,
                    "adaptive": adaptive,
                    "calibration": calibration,
                    "learner_model": learner_model,
                    "subjects": subjects,
                    "activity_summary": activity_summary,
                    "recent": recent,
                    "flow": self._flow_status(),
                    "pending_reviews": pending_reviews,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                }
            )
            self._save_dashboard_cache(payload)
            self._log_startup("dashboard_ready", f"{payload.get('elapsed_seconds', 0)}s")
            return payload
        finally:
            self._initial_dashboard_ready.set()

    def bootstrap(self) -> dict:
        self._ensure_core()
        assert self.queries is not None and self.study is not None
        stats = self.queries.stats()
        return _jsonable(
            {
                "app": {"name": APP_NAME, "version": APP_VERSION},
                "stats": stats,
                "config": self._public_config(),
                "taxonomy": {
                    "loaded": self.taxonomy is not None,
                    "name": self.taxonomy.source_name if self.taxonomy else "",
                    "materias": list(self.taxonomy.materias) if self.taxonomy else [],
                    "task_count": len(self.taxonomy.tasks) if self.taxonomy else 0,
                },
                "flow": self._flow_status(),
                "pending_reviews": self.study.pending_review_count() + (self.mobile_foundation.pending_study_backlog_count() if self.mobile_foundation is not None else 0),
            }
        )

    def _public_config(self) -> dict:
        payload = dict(self.config)
        token = str(payload.get("telegram_bot_token", ""))
        payload["telegram_bot_token_masked"] = (
            f"{token[:5]}…{token[-4:]}" if len(token) > 12 else ("configurado" if token else "")
        )
        payload.pop("telegram_bot_token", None)
        try:
            from core.network import credential_path_for_config, load_proxy_credentials
            _proxy_user, proxy_password = load_proxy_credentials(credential_path_for_config(self.config_path))
            payload["network_proxy_password_configured"] = bool(proxy_password)
        except Exception:
            payload["network_proxy_password_configured"] = False
        try:
            from core.cloud_sync import load_turso_token
            payload["cloud_turso_token_configured"] = bool(load_turso_token(self.config_path))
        except Exception:
            payload["cloud_turso_token_configured"] = False
        return payload

    def _persist_config(self) -> None:
        # Runtime config contains secrets hydrated for local services. Persist a
        # sanitized copy only; Telegram/API/Turso/proxy secrets live in DPAPI.
        public_disk = dict(self.config)
        public_disk.pop("telegram_bot_token", None)
        if self.config_path.resolve() == CONFIG_PATH.resolve():
            save_config(public_disk)
            return
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(public_disk, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_dashboard(self) -> dict:
        """Compatibility endpoint.

        The responsive UI uses ``start_dashboard_load`` so this method is not
        awaited on the native UI thread during startup.
        """
        task_id = "dashboard-sync"
        return self._dashboard_worker(task_id)

    # -------------------- Projeto de Concurso/Edital 6.5 -----------------
    def get_today_dashboard(self, project_id: str = "") -> dict:
        self._ensure_core()
        assert self.engines is not None
        return {"ok": True, "today": _jsonable(self.engines.learning.today_dashboard(str(project_id or "")))}

    def get_exam_project_dashboard(self, project_id: str = "") -> dict:
        self._ensure_core()
        assert self.engines is not None
        return {"ok": True, "dashboard": _jsonable(self.engines.editorial.exam_project_dashboard(str(project_id or "")))}

    def save_exam_project(self, payload: dict | None = None) -> dict:
        self._ensure_core()
        assert self.engines is not None and self.study is not None
        try:
            item = self.engines.editorial.upsert_exam_project(payload or {})
            if bool(item.get("active")) and str(item.get("exam_date") or ""):
                self.study.set_learning_preferences(exam_date=str(item.get("exam_date") or ""))
                self.config["flow_exam_date"] = str(item.get("exam_date") or "")
                self._persist_config()
            dashboard = self.engines.editorial.exam_project_dashboard(str(item.get("id") or ""))
        except (ValueError, TypeError) as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "project": _jsonable(item), "dashboard": _jsonable(dashboard)}

    def set_active_exam_project(self, project_id: str) -> dict:
        self._ensure_core()
        assert self.engines is not None and self.study is not None
        try:
            dashboard = self.engines.editorial.set_active_exam_project(str(project_id or ""))
            project = dashboard.get("project") or {}
            self.study.set_learning_preferences(exam_date=str(project.get("exam_date") or ""))
            self.config["flow_exam_date"] = str(project.get("exam_date") or "")
            self._persist_config()
        except (ValueError, TypeError) as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "dashboard": _jsonable(dashboard), "today": _jsonable(self.engines.learning.today_dashboard(str(project_id or "")))}

    def parse_edital_text(self, text: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        items = self.engines.editorial.parse_syllabus_text(str(text or ""))
        return {"ok": True, "items": _jsonable(items), "count": len(items)}

    def add_edital_version(self, project_id: str, payload: dict | None = None) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            dashboard = self.engines.editorial.add_exam_version(str(project_id or ""), payload or {})
        except (ValueError, TypeError) as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "dashboard": _jsonable(dashboard), "today": _jsonable(self.engines.learning.today_dashboard(str(project_id or "")))}

    def relink_exam_project(self, project_id: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            result = self.engines.editorial.auto_link_exam_project(str(project_id or ""))
            dashboard = self.engines.editorial.exam_project_dashboard(str(project_id or ""))
        except (ValueError, TypeError) as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "result": _jsonable(result), "dashboard": _jsonable(dashboard)}

    def scan_question_currency(self, project_id: str = "") -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            result = self.engines.editorial.scan_question_currency(str(project_id or ""))
        except (ValueError, TypeError) as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "result": _jsonable(result)}

    def set_question_currency(self, uid: str, status: str, reason: str = "", reference_date: str = "") -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            item = self.engines.editorial.set_question_currency(str(uid or ""), str(status or ""), reason=str(reason or ""), reference_date=str(reference_date or ""))
        except (ValueError, TypeError) as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "currency": _jsonable(item)}

    def _list_materias_data(self) -> dict:
        """Return subjects from both the spreadsheet taxonomy and the active bank.

        The initial shell is intentionally lightweight and may be painted before
        the taxonomy worker is ready.  This endpoint guarantees that the editor
        can still populate its selector as soon as a question is opened.
        """
        self._ensure_core()
        assert self.queries is not None
        values: list[str] = []
        if self.taxonomy is not None:
            values.extend(str(item).strip() for item in self.taxonomy.materias)
        if self.question_catalog is not None and self.question_catalog.provider_id() != "local":
            try:
                values.extend(str(item.get("nome") or "").strip() for item in self.question_catalog.subjects())
            except Exception:
                # A taxonomia local continua disponível quando a fonte externa
                # está temporariamente offline.
                values.extend(self.queries.subjects())
        else:
            values.extend(self.queries.subjects())
        unique = sorted(
            {item for item in values if item},
            key=lambda item: item.casefold(),
        )
        return {"ok": True, "items": unique, "count": len(unique)}

    def list_materias(self) -> dict:
        result = self.dispatch_studio_v1("taxonomy.subjects.list", {})
        if not result.get("ok"):
            return result
        return {"ok": True, **_jsonable(result.get("data") or {})}

    def get_bank_classification_options(self, subject: str = "", lesson: str = "") -> dict:
        """Return bank/taxonomy facets used by the correction workspace."""
        self._ensure_core()
        assert self.queries is not None
        selected_subject = _clean_text(subject)
        selected_lesson = _clean_text(lesson)
        bank_subjects = sorted({item for item in self.queries.subjects() if item}, key=str.casefold)
        subjects = list(bank_subjects)
        if self.taxonomy is not None:
            subjects.extend(str(item).strip() for item in self.taxonomy.materias)
        subjects = sorted({item for item in subjects if item}, key=str.casefold)

        bank_lessons = sorted({item for item in self.queries.lessons(selected_subject) if item}, key=str.casefold)
        lessons = list(bank_lessons)
        task_options: list[dict] = []
        for index, raw in enumerate(self.taxonomy.tasks if self.taxonomy else []):
            task = dict(raw)
            matter = _clean_text(task.get("materia"))
            task_lesson = _clean_text(task.get("aula"))
            if selected_subject and matter.casefold() != selected_subject.casefold():
                continue
            if task_lesson:
                lessons.append(task_lesson)
            if selected_lesson and task_lesson.casefold() != selected_lesson.casefold():
                continue
            row_number = int(task.get("row", 0) or 0) or index + 1
            task_id = f"{task.get('trilha', '')}:{row_number}"
            segments = [str(item).strip() for item in task.get("segmentos", []) if str(item).strip()]
            content = " até ".join(segments[:2]) if segments else _clean_text(task.get("descricao"))
            task_options.append(
                {
                    "task_id": task_id,
                    "trilha": _clean_text(task.get("trilha")),
                    "tarefa": _clean_text(task.get("tarefa")),
                    "materia": matter,
                    "aula": task_lesson,
                    "conteudo": content,
                    "descricao": _clean_text(task.get("descricao")),
                    "estudado": bool(task.get("estudado")),
                }
            )
        lessons = sorted({item for item in lessons if item}, key=str.casefold)
        task_options.sort(
            key=lambda item: (
                item.get("materia", "").casefold(),
                item.get("aula", "").casefold(),
                item.get("trilha", "").casefold(),
                item.get("tarefa", "").casefold(),
            )
        )
        return {
            "ok": True,
            "subjects": subjects,
            "bank_subjects": bank_subjects,
            "lessons": lessons,
            "bank_lessons": bank_lessons,
            "tasks": _jsonable(task_options),
        }

    def update_question_classification(self, uid: str, payload: dict) -> dict:
        """Correct subject/lesson and optionally bind the question to an exact spreadsheet task.

        This method intentionally keeps the stable question UID and study history.  Only
        classification metadata changes, so answers, Telegram history and adaptive state
        remain linked to the same question.
        """
        self._ensure_core()
        assert self.queries is not None and self.commands is not None and self.study is not None
        current = self.queries.get(uid)
        if not current:
            return {"ok": False, "error": "Questão não encontrada."}
        if not isinstance(payload, dict):
            return {"ok": False, "error": "Dados de classificação inválidos."}

        requested_subject = _clean_text(payload.get("materia"))
        requested_lesson = _clean_text(payload.get("aula"))
        task_id = _clean_text(payload.get("task_id"))
        selected_task: dict | None = None
        if task_id:
            for index, raw in enumerate(self.taxonomy.tasks if self.taxonomy else []):
                task = dict(raw)
                row_number = int(task.get("row", 0) or 0) or index + 1
                candidate_id = f"{task.get('trilha', '')}:{row_number}"
                if candidate_id == task_id:
                    selected_task = task
                    break
            if selected_task is None:
                return {"ok": False, "error": "O conteúdo selecionado não existe mais na planilha atual. Sincronize e tente novamente."}
            requested_subject = _clean_text(selected_task.get("materia")) or requested_subject
            requested_lesson = _clean_text(selected_task.get("aula")) or requested_lesson

        if not requested_subject:
            return {"ok": False, "error": "Selecione a matéria correta da questão."}

        old_subject = _clean_text(current.get("materia"))
        old_lesson = _clean_text(current.get("aula_planilha"))
        question = copy.deepcopy(current)
        question["materia"] = requested_subject
        question["aula_planilha"] = requested_lesson
        if old_subject.casefold() != requested_subject.casefold() or old_lesson.casefold() != requested_lesson.casefold():
            question.pop("titulo_aula", None)
        primary = _clean_text(question.get("assunto"))
        question["trilha_assuntos"] = [item for item in (requested_subject, requested_lesson, primary) if item]

        history = question.get("historico_classificacao")
        if not isinstance(history, list):
            history = []
        if old_subject != requested_subject or old_lesson != requested_lesson or task_id:
            history.append(
                {
                    "alterado_em": _utc_now(),
                    "origem": "correcao_banco_web",
                    "materia_anterior": old_subject,
                    "aula_anterior": old_lesson,
                    "materia_nova": requested_subject,
                    "aula_nova": requested_lesson,
                    "task_id": task_id,
                }
            )
            question["historico_classificacao"] = history[-100:]

        classification = question.get("classificacao_planilha")
        if not isinstance(classification, dict):
            classification = {}
        if old_subject.casefold() != requested_subject.casefold() or old_lesson.casefold() != requested_lesson.casefold():
            classification.pop("titulo_aula", None)
        classification.update(
            {
                "status": "classificado" if requested_subject else "revisar",
                "confianca": 1.0 if requested_subject else 0.5,
                "metodo": "correcao_manual_banco",
                "fonte": self.taxonomy.source_name if self.taxonomy else "Correção manual",
            }
        )
        if selected_task is not None:
            reference = _clean_text(selected_task.get("descricao"))
            segments = [str(item).strip() for item in selected_task.get("segmentos", []) if str(item).strip()]
            content = " até ".join(segments[:2]) if segments else reference
            classification["referencia"] = reference or content
            classification["contexto_task_id"] = task_id
            question["contexto_importacao_estudos"] = {
                "task_id": task_id,
                "trilha": _clean_text(selected_task.get("trilha")),
                "tarefa": _clean_text(selected_task.get("tarefa")),
                "materia": requested_subject,
                "aula": requested_lesson,
                "conteudo": content,
                "referencia": reference or content,
                "corrigido_manualmente": True,
            }
        else:
            # A reference from the old import must never drag a moved question
            # back to the previous spreadsheet task during coverage calculation.
            classification.pop("referencia", None)
            classification.pop("contexto_task_id", None)
            question.pop("contexto_importacao_estudos", None)
        question["classificacao_planilha"] = classification

        try:
            self.commands.update(uid, question, change_source="correcao_banco_web")
        except (ValueError, sqlite3.IntegrityError) as error:
            return {"ok": False, "error": str(error)}
        try:
            from core.architecture import DomainEvent

            assert self.architecture_kernel is not None
            self.architecture_kernel.events.publish(DomainEvent(
                event_type="editorial.question.changed",
                module="editorial_bank",
                aggregate_type="question",
                aggregate_id=str(uid),
                payload={
                    "question_uid": str(uid),
                    "approved": bool(approve),
                    "code_changed": bool((code_change or {}).get("code_changed")),
                },
            ))
        except Exception:
            # A escrita editorial já foi confirmada; uma falha de projeção fica
            # registrada no barramento para retry e não corrompe a edição.
            pass

        refreshed = self.queries.get(uid) or question
        assignment = None
        try:
            coverage = self.study.studied_content_coverage(self.taxonomy.tasks if self.taxonomy else [])
            code = _clean_text(refreshed.get("codigo_origem"))
            assignment = next(
                (
                    {
                        "task_id": item.get("task_id"),
                        "trilha": item.get("trilha"),
                        "tarefa": item.get("tarefa"),
                        "materia": item.get("subject"),
                        "aula": item.get("lesson"),
                        "conteudo": item.get("content"),
                    }
                    for item in coverage.get("items", [])
                    if code and code in (item.get("question_codes") or [])
                ),
                None,
            )
        except Exception:
            assignment = None
        return {
            "ok": True,
            "question": _jsonable(refreshed),
            "stats": self.queries.stats(),
            "coverage_assignment": _jsonable(assignment),
        }

    def organize_bank_lesson_group(self, payload: dict) -> dict:
        """Normalize every question in a subject/lesson group and save its canonical title."""
        self._ensure_core()
        assert self.commands is not None and self.queries is not None and self.study is not None
        if not isinstance(payload, dict):
            return {"ok": False, "error": "Dados de organização inválidos."}
        try:
            result = self.commands.organize_lesson_group(
                _clean_text(payload.get("source_matter")),
                _clean_text(payload.get("source_lesson")),
                _clean_text(payload.get("materia")),
                _clean_text(payload.get("aula")),
                _clean_text(payload.get("titulo_aula")),
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            return {"ok": False, "error": str(error)}
        try:
            self.study.rebuild_subject_analytics_daily()
        except Exception:
            pass
        return {
            "ok": True,
            "group": _jsonable(result),
            "stats": self.queries.stats(),
        }

    # -------------------------- modelo de aprendizagem 6.0 ----------------
    def get_learning_model(self) -> dict:
        self._ensure_core()
        assert self.engines is not None
        return {"ok": True, "model": _jsonable(self.engines.learner.dashboard())}

    def get_counterfactual_learning_plan(self, target_mastery: float = 0.80, limit: int = 6) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            plan = self.engines.learner.counterfactual_plan(
                target_mastery=float(target_mastery or 0.80), limit=int(limit or 6)
            )
        except (TypeError, ValueError) as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "plan": _jsonable(plan)}

    def get_evidence_collection_plan(self, concept_key: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            plan = self.engines.learner.evidence_collection_plan(str(concept_key or ""), candidate_limit=12)
        except (ValueError, TypeError) as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "plan": _jsonable(plan)}

    def start_evidence_collection(self, concept_key: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            simulation = self.engines.learning.start_evidence_collection(str(concept_key or ""))
        except (ValueError, TypeError) as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "simulation": _jsonable(simulation)}

    def get_scaffolding_benchmark(self) -> dict:
        self._ensure_core()
        assert self.engines is not None
        return {"ok": True, "benchmark": _jsonable(self.engines.learner.scaffolding_benchmark())}

    def start_learner_model_rebuild(self) -> dict:
        self._ensure_core()
        return self._start_task("learner_model_rebuild", self._learner_model_rebuild_worker, coalesce=True)

    def _learner_model_rebuild_worker(self, task_id: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        self._update_task(task_id, progress=0.08, message="Reconstruindo domínio por conceito…")
        result = self.engines.learner.rebuild()
        self._update_task(task_id, progress=0.94, message="Validando habilidade e informação dos itens…")
        return _jsonable(result)

    # -------------------------- arquitetura e tutor IA 6.1 ----------------
    def get_engine_architecture(self) -> dict:
        self._ensure_core()
        assert self.engines is not None and self.architecture_kernel is not None
        architecture = self.architecture_kernel.architecture()
        architecture["domain_engines"] = self.engines.architecture()
        architecture["services"] = []
        if self.retrieval_health is not None:
            architecture["services"].append(_jsonable(self.retrieval_health.status()))
        architecture["principles"] = list(architecture.get("principles") or []) + [
            "retrieval_cqrs", "metrics_snapshot_store", "dedicated_evaluator_worker",
            "single_snapshot_quality_gate",
        ]
        return {"ok": True, "architecture": _jsonable(architecture)}

    def dispatch_studio_v1(self, operation: str, payload: dict | None = None) -> dict:
        """Despacha um caso de uso do contrato ``questflow.studio.v1``."""
        self._ensure_core()
        if self.use_cases is None:
            return {"ok": False, "error": "Application layer indisponível.", "code": "unavailable"}
        try:
            return _jsonable(self.use_cases.dispatch(str(operation or ""), payload or {}))
        except Exception as error:
            try:
                from core.application import UseCaseError
                if isinstance(error, UseCaseError):
                    return {"ok": False, "error": str(error), "code": error.code, "status": error.status}
            except Exception:
                pass
            return {"ok": False, "error": str(error), "code": "internal_error", "status": 500}

    def get_studio_contract_v1(self) -> dict:
        self._ensure_core()
        if self.use_cases is None:
            return {"ok": False, "error": "Application layer indisponível."}
        return {"ok": True, **_jsonable(self.use_cases.catalog_contract())}

    def get_question_source_settings(self) -> dict:
        result = self.dispatch_studio_v1("questions.source.settings", {})
        return {"ok": True, "settings": result.get("data", {})} if result.get("ok") else result

    def save_question_source_settings(self, payload: dict | None = None) -> dict:
        result = self.dispatch_studio_v1("questions.source.save", payload or {})
        return {"ok": True, "settings": result.get("data", {})} if result.get("ok") else result

    def test_question_source(self, provider: str = "") -> dict:
        result = self.dispatch_studio_v1("questions.source.test", {"provider": provider})
        return {"ok": True, "result": result.get("data", {})} if result.get("ok") else result

    def rebuild_learning_projections(self, name: str = "") -> dict:
        return self.dispatch_studio_v1("system.projections.rebuild", {"name": name})

    def get_tutor_workspace(self, uid: str = "") -> dict:
        self._ensure_core()
        assert self.engines is not None
        workspace = self.engines.ai.workspace(str(uid or ""))
        selected = workspace.get("selected") if isinstance(workspace, dict) else None
        if isinstance(selected, dict) and selected.get("uid") and self.queries is not None:
            try:
                question = self.queries.get(str(selected.get("uid")))
                if question:
                    selected["image"] = self._image_data(question)
            except Exception:
                selected["image"] = None
        return {"ok": True, "workspace": _jsonable(workspace)}

    def start_tutor_scaffolding(self, uid: str, user_prompt: str = "", representation: str = "texto", media_notes: str = "", online: bool = False) -> dict:
        self._ensure_core()
        assert self.engines is not None
        if not str(uid or "").strip():
            return {"ok": False, "error": "Selecione uma questão para iniciar a escada de pistas."}
        return self._start_task(
            "tutor_scaffold",
            lambda task_id: self._tutor_scaffold_start_worker(task_id, str(uid), str(user_prompt or ""), str(representation or "texto"), str(media_notes or ""), bool(online)),
        )

    def _tutor_scaffold_start_worker(self, task_id: str, uid: str, user_prompt: str, representation: str, media_notes: str, online: bool) -> dict:
        self._ensure_core()
        assert self.engines is not None
        self._update_task(task_id, progress=0.10, message="Criando sessão de scaffolding…")
        self._update_task(task_id, progress=0.28, message="Montando primeira pista sem revelar o gabarito…")
        result = self.engines.ai.start_scaffolding(uid, user_prompt=user_prompt, representation=representation, media_notes=media_notes, online=online)
        self._update_task(task_id, progress=0.95, message="Registrando o nível de ajuda no Learner Model…")
        return _jsonable(result)

    def advance_tutor_scaffolding(self, session_id: str, action: str = "next", online: bool | None = None) -> dict:
        self._ensure_core()
        assert self.engines is not None
        if not str(session_id or "").strip():
            return {"ok": False, "error": "Sessão de scaffolding não informada."}
        return self._start_task(
            "tutor_scaffold",
            lambda task_id: self._tutor_scaffold_advance_worker(task_id, str(session_id), str(action or "next"), online),
        )

    def _tutor_scaffold_advance_worker(self, task_id: str, session_id: str, action: str, online: bool | None) -> dict:
        self._ensure_core()
        assert self.engines is not None
        self._update_task(task_id, progress=0.12, message="Atualizando o nível de ajuda…")
        result = self.engines.ai.advance_scaffolding(session_id, action=action, online=online)
        self._update_task(task_id, progress=0.95, message="Atualizando o sinal de independência no Learner Model…")
        return _jsonable(result)

    def get_tutor_scaffolding(self, session_id: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            return _jsonable(self.engines.ai.scaffolding_state(str(session_id)))
        except ValueError as error:
            return {"ok": False, "error": str(error)}

    def diagnose_question_error(self, uid: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            diagnosis = self.engines.ai.diagnose_error(str(uid), persist=True)
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "diagnosis": _jsonable(diagnosis)}

    def start_tutor_assist(self, uid: str, mode: str = "professor", user_prompt: str = "", online: bool = False) -> dict:
        self._ensure_core()
        assert self.engines is not None
        if not str(uid or "").strip():
            return {"ok": False, "error": "Selecione uma questão para o Tutor IA."}
        return self._start_task(
            "tutor_ai",
            lambda task_id: self._tutor_assist_worker(task_id, str(uid), str(mode or "professor"), str(user_prompt or ""), bool(online)),
        )

    def _tutor_assist_worker(self, task_id: str, uid: str, mode: str, user_prompt: str, online: bool) -> dict:
        self._ensure_core()
        assert self.engines is not None
        self._update_task(task_id, progress=0.08, message="Montando contexto do aluno (FSRS + KT + IRT)…")
        # O pacote e o diagnóstico são montados dentro do AI Engine para manter a
        # API sem regra pedagógica. A avaliação ocorre em motor separado.
        self._update_task(task_id, progress=0.18, message="Recuperando evidências no Knowledge Engine…")
        if online:
            self._update_task(task_id, progress=0.26, message="Consultando IA online; a janela do Google pode ser exibida…")
        result = self.engines.ai.generate_tutor(uid, mode=mode, user_prompt=user_prompt, online=online)
        self._update_task(task_id, progress=0.94, message="Avaliando fundamentação e registrando auditoria…")
        return _jsonable(result)

    # -------------------------- recomendador / simulado 6.2 --------------
    def get_recommendation_dashboard(self, mode: str = "equilibrado") -> dict:
        self._ensure_core()
        assert self.engines is not None
        return {"ok": True, "dashboard": _jsonable(self.engines.learning.recommendation_dashboard(mode=str(mode or "equilibrado")))}

    def start_adaptive_simulation(self, payload: dict | None = None) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            result = self.engines.learning.start_simulation(payload or {})
        except (ValueError, TypeError) as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "simulation": _jsonable(result)}

    def get_adaptive_simulation(self, session_id: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            result = self.engines.learning.simulation(str(session_id or ""))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "simulation": _jsonable(result)}

    def submit_adaptive_simulation_answer(
        self,
        session_id: str,
        selected_index: int,
        response_seconds: float | None = None,
        confidence: str = "",
        perceived_difficulty: str = "",
        learning_gap: bool | None = None,
    ) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            result = self.engines.learning.submit_simulation_answer(
                str(session_id or ""), int(selected_index),
                response_seconds=response_seconds, confidence=str(confidence or ""),
                perceived_difficulty=str(perceived_difficulty or ""), learning_gap=learning_gap,
            )
        except (ValueError, TypeError) as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "simulation": _jsonable(result)}

    def abandon_adaptive_simulation(self, session_id: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            result = self.engines.learning.abandon_simulation(str(session_id or ""))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "simulation": _jsonable(result)}

    # -------------------------- etapa 5 / geração controlada 6.3 ---------
    def get_stage5_workspace(self, uid: str = "") -> dict:
        self._ensure_core()
        assert self.engines is not None
        return {"ok": True, "workspace": _jsonable(self.engines.ai.generation_workspace(str(uid or "")))}

    def create_legislation_version(self, payload: dict | None = None) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            item = self.engines.editorial.upsert_legislation(payload or {})
        except (ValueError, TypeError) as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "version": _jsonable(item), "summary": _jsonable(self.engines.editorial.legislation_summary())}

    def resolve_legislation_version(self, canonical_key: str, reference_date: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        item = self.engines.editorial.resolve_legislation(str(canonical_key or ""), str(reference_date or ""))
        return {"ok": True, "version": _jsonable(item) if item else None}

    def generate_controlled_question(self, payload: dict | None = None) -> dict:
        self._ensure_core()
        assert self.engines is not None
        payload = payload or {}
        try:
            result = self.engines.ai.generate_controlled_question(
                seed_uid=str(payload.get("seed_uid") or ""),
                source_chunk_ids=list(payload.get("source_chunk_ids") or []),
                question_type=str(payload.get("question_type") or "multipla_escolha"),
                board_style=str(payload.get("board_style") or ""),
                subject=str(payload.get("subject") or ""),
                topic=str(payload.get("topic") or ""),
                exam_date=str(payload.get("exam_date") or ""),
            )
        except (ValueError, TypeError) as error:
            return {"ok": False, "error": str(error)}
        return _jsonable(result)

    def get_generation_draft(self, draft_id: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            item = self.engines.governance.generation_draft(str(draft_id or ""))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "draft": _jsonable(item)}

    def review_generation_draft(self, draft_id: str, decision: str, note: str = "") -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            item = self.engines.governance.review_generation_draft(str(draft_id or ""), decision=str(decision or ""), note=str(note or ""))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "draft": _jsonable(item)}

    def publish_generation_draft(self, draft_id: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            result = self.engines.ai.publish_generation_draft(str(draft_id or ""))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, **_jsonable(result)}

    def run_multimodal_grounding_benchmark(self, limit: int = 30) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            benchmark = self.engines.ai.run_multimodal_grounding_benchmark(limit=max(1, min(100, int(limit or 30))))
        except (ValueError, TypeError) as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "benchmark": _jsonable(benchmark)}

    def run_retrieval_calibration(self, limit: int = 30) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            result = self.engines.ai.run_retrieval_calibration(limit=max(1, min(100, int(limit or 30))))
        except (ValueError, TypeError) as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "calibration": _jsonable(result)}

    def apply_retrieval_calibration(self, profile_id: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            result = self.engines.ai.apply_retrieval_calibration(str(profile_id or ""))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "result": _jsonable(result)}

    def rollback_retrieval_calibration(self) -> dict:
        self._ensure_core()
        assert self.engines is not None
        return {"ok": True, "result": _jsonable(self.engines.ai.rollback_retrieval_calibration())}

    def save_retrieval_regression_baseline(self, limit: int = 30) -> dict:
        self._ensure_core()
        assert self.engines is not None
        return {"ok": True, "baseline": _jsonable(self.engines.ai.save_retrieval_regression_baseline(limit=max(1,min(100,int(limit or 30)))))}

    def get_retrieval_regression_status(self, limit: int = 30) -> dict:
        self._ensure_core()
        assert self.engines is not None
        return {"ok": True, "status": _jsonable(self.engines.ai.get_retrieval_regression_status(limit=max(1,min(100,int(limit or 30)))))}

    def _retrieval_health_service(self):
        self._ensure_core()
        if self.retrieval_health is None:
            raise RuntimeError("Serviço de observabilidade de retrieval indisponível.")
        return self.retrieval_health

    def get_retrieval_health_service(self) -> dict:
        try:
            return {"ok": True, "service": _jsonable(self._retrieval_health_service().status())}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def get_retrieval_health_snapshot(self) -> dict:
        try:
            service = self._retrieval_health_service()
            return {"ok": True, "snapshot": _jsonable(service.combined_snapshot(release=APP_VERSION))}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def start_retrieval_evaluation(self, limit: int = 30, source: str = "manual") -> dict:
        try:
            service = self._retrieval_health_service()
            job = service.start_evaluation(
                release=APP_VERSION, limit=max(1, min(100, int(limit or 30))),
                source=str(source or "manual"),
            )
            return {"ok": True, "job": _jsonable(job)}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def get_retrieval_evaluation_job(self, job_id: str = "") -> dict:
        try:
            return {"ok": True, "job": _jsonable(self._retrieval_health_service().job(str(job_id or "")))}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def get_retrieval_observability(self, limit: int = 30) -> dict:
        try:
            return {"ok": True, "observability": _jsonable(self._retrieval_health_service().read_observability(release=APP_VERSION))}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def record_retrieval_observability(self, limit: int = 30) -> dict:
        """Alias compatível: agora agenda o Evaluator Worker em vez de executar inline."""
        return self.start_retrieval_evaluation(limit=limit, source="observability")

    def suggest_gold_question_expansion(self, limit: int = 12) -> dict:
        try:
            result = self._retrieval_health_service().suggest_gold_expansion(limit=max(1, min(30, int(limit or 12))))
            return {"ok": True, "suggestions": _jsonable(result)}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def export_retrieval_observability_report(self, format: str = "json", limit: int = 30) -> dict:
        try:
            report = self._retrieval_health_service().export_observability(
                release=APP_VERSION, format=str(format or "json"), limit=max(1, min(100, int(limit or 30)))
            )
            return {"ok": True, "report": _jsonable(report)}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def get_retrieval_quality_gate(self, limit: int = 30) -> dict:
        try:
            gate = self._retrieval_health_service().read_quality_gate(release=APP_VERSION)
            return {"ok": True, "gate": _jsonable(gate)}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def reevaluate_retrieval_quality_gate(self, limit: int = 30) -> dict:
        """Alias compatível: agenda avaliação única que atualiza Observabilidade + Gate."""
        return self.start_retrieval_evaluation(limit=limit, source="quality_gate")

    def promote_retrieval_release(self, limit: int = 30, reason: str = "human_release_promotion") -> dict:
        try:
            result = self._retrieval_health_service().promote(
                release=APP_VERSION, reason=str(reason or "human_release_promotion")
            )
            return {"ok": True, "result": _jsonable(result)}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def override_retrieval_quality_gate(self, reason: str, limit: int = 30) -> dict:
        try:
            result = self._retrieval_health_service().override(release=APP_VERSION, reason=str(reason or ""))
            return {"ok": True, "result": _jsonable(result)}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def rollback_retrieval_release_gate(self) -> dict:
        try:
            return {"ok": True, "result": _jsonable(self._retrieval_health_service().rollback())}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def export_retrieval_quality_gate_report(self, format: str = "json", limit: int = 30) -> dict:
        try:
            report = self._retrieval_health_service().export_quality_gate(
                release=APP_VERSION, format=str(format or "json"), limit=max(1, min(100, int(limit or 30)))
            )
            return {"ok": True, "report": _jsonable(report)}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def add_gold_question(self, uid: str, label: str = "", notes: str = "") -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            item = self.engines.ai.add_gold_question(str(uid or ""), label=str(label or ""), notes=str(notes or ""))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "gold": _jsonable(item), "summary": _jsonable(self.engines.governance.gold_dashboard())}

    def run_gold_regression(self, limit: int = 50) -> dict:
        self._ensure_core()
        assert self.engines is not None
        return {"ok": True, "result": _jsonable(self.engines.ai.run_gold_regression(limit=max(1, min(200, int(limit or 50))))),
                "summary": _jsonable(self.engines.governance.gold_dashboard())}

    def get_gold_dashboard(self) -> dict:
        self._ensure_core()
        assert self.engines is not None
        return {"ok": True, "summary": _jsonable(self.engines.governance.gold_dashboard()),
                "items": _jsonable(self.engines.governance.gold_questions(active_only=True))}

    def get_ai_audit(self, limit: int = 20) -> dict:
        self._ensure_core()
        assert self.engines is not None
        return {
            "ok": True,
            "summary": _jsonable(self.engines.governance.dashboard()),
            "items": _jsonable(self.engines.governance.recent_audit(limit=max(1, min(100, int(limit or 20))))),
        }

    def get_ai_interaction(self, interaction_id: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            item = self.engines.governance.interaction(str(interaction_id))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "interaction": _jsonable(item)}

    def save_ai_interaction_text(self, interaction_id: str, response_text: str, note: str = "") -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            before = self.engines.governance.interaction(str(interaction_id))
            if str(before.get("interaction_type") or "") != "tutor":
                return {"ok": False, "error": "Somente rascunhos do Tutor IA podem ser editados nesta tela."}
            item = self.engines.governance.edit_interaction_response(
                str(interaction_id), response_text=str(response_text or ""), note=str(note or "")
            )
            question = self.engines.editorial.question(str(item.get("question_uid") or ""))
            sources = item.get("sources") if isinstance(item.get("sources"), list) else []
            diagnosis = item.get("diagnosis") if isinstance(item.get("diagnosis"), dict) else {}
            evaluation = self.engines.governance.evaluate(
                str(interaction_id),
                response_text=str(item.get("display_response_text") or ""),
                mode=str(item.get("tutor_mode") or "professor"),
                official_answer=str(question.get("gabarito") or ""),
                source_texts=[str(src.get("content") or "") for src in sources if isinstance(src, dict)],
                diagnosis=diagnosis,
                sources=sources,
                question_context={
                    "reference_date": str((question.get("contexto_temporal") or {}).get("data_prova") or "")
                    if isinstance(question.get("contexto_temporal"), dict) else ""
                },
            )
            item = self.engines.governance.interaction(str(interaction_id))
            item["evaluation"] = evaluation
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "interaction": _jsonable(item)}

    def review_ai_interaction(self, interaction_id: str, decision: str, note: str = "") -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            result = self.engines.governance.review_interaction(str(interaction_id), decision=str(decision), note=str(note or ""))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "review": _jsonable(result)}

    # -------------------------- inteligência e curadoria do banco ---------
    def get_bank_intelligence(self) -> dict:
        self._ensure_core()
        assert self.engines is not None
        return {"ok": True, "summary": _jsonable(self.engines.editorial.summary())}

    def refresh_bank_intelligence(self) -> dict:
        self._ensure_core()
        assert self.engines is not None
        return _jsonable(self.engines.editorial.refresh_summary())

    def get_curation_attention(self, kind: str = "curation", limit: int = 100) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            result = self.engines.editorial.attention(str(kind), limit=int(limit or 100))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, **_jsonable(result)}

    def complete_curation_review(self, uid: str, reviewer: str = "") -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            result = self.engines.editorial.complete_review(str(uid), reviewer=str(reviewer or ""))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return _jsonable(result)

    def get_question_intelligence(self, uid: str, scan_duplicates: bool = True) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            intelligence = self.engines.editorial.intelligence(str(uid), scan_duplicates=bool(scan_duplicates))
            intelligence["learning_model"] = self.engines.learner.question_state(str(uid))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "intelligence": _jsonable(intelligence)}

    def resolve_duplicate_candidate(self, candidate_id: str, duplicate: bool = False) -> dict:
        self._ensure_core()
        assert self.engines is not None
        ok = self.engines.editorial.resolve_duplicate(str(candidate_id), duplicate=bool(duplicate))
        return {"ok": bool(ok), "status": "confirmado" if duplicate else "descartado"}

    def get_ai_commentary_brief(self, uid: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            brief = self.engines.ai.editorial_commentary_brief(str(uid))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "brief": _jsonable(brief)}

    def get_semantic_index_summary(self) -> dict:
        self._ensure_core()
        assert self.engines is not None
        return {"ok": True, "summary": _jsonable(self.engines.knowledge.summary())}

    def get_question_knowledge_graph(self, uid: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            graph = self.engines.knowledge.graph(str(uid))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "graph": _jsonable(graph)}

    def get_rag_context(self, uid: str, query: str = "", limit: int = 8) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            result = self.engines.knowledge.retrieve(str(uid), str(query or ""), limit=max(1, min(20, int(limit or 8))))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "retrieval": _jsonable(result)}

    def start_semantic_rebuild(self) -> dict:
        self._ensure_core()
        return self._start_task("semantic_rebuild", self._semantic_rebuild_worker, coalesce=True)

    def _semantic_rebuild_worker(self, task_id: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        self._update_task(task_id, progress=0.08, message="Reconstruindo assinaturas semânticas, grafo e chunks RAG…")
        result = self.engines.knowledge.rebuild()
        self._update_task(task_id, progress=0.96, message="Validando cobertura do índice híbrido…")
        return _jsonable(result)

    def start_ai_commentary_assist(self, uid: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            self.engines.editorial.question(str(uid))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return self._start_task(
            "ai_commentary",
            lambda task_id: self._ai_commentary_worker(task_id, str(uid)),
        )

    def _ai_commentary_worker(self, task_id: str, uid: str) -> dict:
        self._ensure_core()
        assert self.engines is not None
        self._update_task(task_id, progress=0.06, message="Preparando contexto auditável no AI Engine…")
        self._update_task(task_id, progress=0.16, message="Recuperando evidências no Knowledge Engine…")
        self._update_task(task_id, progress=0.24, message="Consultando IA online e preservando rastreabilidade…")
        result = self.engines.ai.generate_editorial_commentary(uid, online=True)
        self._update_task(task_id, progress=0.90, message="Avaliando fundamentação no Governance Engine…")
        self._update_task(task_id, progress=1.0, message="Rascunho auditado pronto para conferência humana.")
        return _jsonable(result)

    def start_google_commentary_research(self, uid: str, question_draft: dict | None = None) -> dict:
        self._ensure_core()
        assert self.engines is not None
        try:
            self.engines.editorial.question(str(uid))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return self._start_task(
            "google_commentary_research",
            lambda task_id: self._google_commentary_research_worker(task_id, str(uid), question_draft if isinstance(question_draft, dict) else {}),
        )

    def _google_commentary_research_worker(self, task_id: str, uid: str, question_draft: dict | None = None) -> dict:
        self._ensure_core()
        assert self.engines is not None
        self._update_task(task_id, progress=0.05, message="Preparando a questão e aplicando a política de privacidade…")
        self._update_task(task_id, progress=0.16, message="Abrindo o Google Modo IA em segundo plano…")
        self._update_task(task_id, progress=0.34, message="Pesquisando pelo código e pelo enunciado quando necessário…")
        result = self.engines.ai.research_google_commentary(
            uid,
            question_override=question_draft if isinstance(question_draft, dict) else None,
            progress_callback=lambda progress, message: self._update_task(
                task_id, progress=progress, message=message
            ),
        )
        self._update_task(task_id, progress=0.88, message="Avaliando a explicação e registrando as fontes…")
        self._update_task(task_id, progress=1.0, message="Pesquisa concluída. A explicação está pronta para revisão humana.")
        return _jsonable(result)

    # -------------------------- question review ----------------------------
    def list_questions(
        self,
        search: str = "",
        status: str = "todos",
        offset: int = 0,
        limit: int = 500,
        subject: str = "",
        lesson: str = "",
    ) -> dict:
        result = self.dispatch_studio_v1(
            "questions.list",
            {
                "search": search,
                "status": status,
                "offset": offset,
                "limit": limit,
                "subject": subject,
                "lesson": lesson,
            },
        )
        if not result.get("ok"):
            return result
        return _jsonable(result.get("data") or {"total": 0, "items": []})

    def _present_question_detail(self, uid: str, raw_question: dict) -> dict:
        question = dict(raw_question or {})
        if not question:
            return {"question": {}, "image": None}
        question.setdefault("database_uid", str(uid))
        if not question.get("external_read_only") and self.queries is not None:
            try:
                question["historico_codigos"] = self.queries.code_history(uid, limit=50)
            except Exception:
                question.setdefault("historico_codigos", [])
        # Compatibilidade com bases anteriores: uma questão marcada como
        # Certo/Errado nunca deve voltar para a interface exibindo A-E. A
        # normalização aqui é de apresentação; ao salvar, _merge_question
        # persiste o formato canônico e registra a conversão no histórico.
        try:
            from core.question_types import TRUE_FALSE, canonicalize_question_format, normalize_question_type

            if normalize_question_type(question.get("tipo")) == TRUE_FALSE:
                qtype, alternatives, answer = canonicalize_question_format(
                    TRUE_FALSE, question.get("alternativas", []), question.get("gabarito", "")
                )
                question["tipo"] = qtype
                question["alternativas"] = alternatives
                question["gabarito"] = answer
        except Exception:
            pass
        if question.get("external_read_only"):
            info = question.get("imagem_questao") if isinstance(question.get("imagem_questao"), dict) else {}
            remote_src = str(info.get("path") or "").strip()
            image = {
                "src": remote_src,
                "name": "Imagem da APIdasQuestões",
                "meta": _jsonable(info),
            } if remote_src.lower().startswith("https://") else None
        else:
            image = self._image_data(question)
        return {"question": _jsonable(question), "image": image}

    def get_question(self, uid: str) -> dict:
        result = self.dispatch_studio_v1("questions.get", {"uid": uid})
        if not result.get("ok"):
            return result
        detail = dict(result.get("data") or {})
        if not isinstance(detail.get("question"), dict) or not detail.get("question"):
            return {"ok": False, "error": "Questão não encontrada."}
        return {"ok": True, **_jsonable(detail)}

    def _create_manual_question_record(self) -> dict:
        self._ensure_core()
        assert self.commands is not None and self.queries is not None
        uid = self.commands.create_manual(self.taxonomy)
        question = self.queries.get(uid)
        return {"uid": uid, "question": _jsonable(question)}

    def create_manual_question(self) -> dict:
        result = self.dispatch_studio_v1("questions.create", {})
        if not result.get("ok"):
            return result
        return {"ok": True, **_jsonable(result.get("data") or {})}

    def _save_question_record(self, uid: str, payload: dict, approve: bool = False) -> dict:
        self._ensure_core()
        assert self.commands is not None and self.queries is not None and self.study is not None
        current = self.queries.get(uid)
        if not current:
            return {"ok": False, "error": "Questão não encontrada."}
        if not isinstance(payload, dict):
            return {"ok": False, "error": "Dados inválidos."}
        try:
            updated = self._merge_question(current, payload, approve=bool(approve))
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        try:
            code_change = self.commands.update(uid, updated, change_source="interface_web")
        except (ValueError, sqlite3.IntegrityError) as error:
            return {"ok": False, "error": str(error)}
        try:
            self.study.rebuild_subject_analytics_daily()
        except Exception:
            pass
        if approve:
            try:
                self.study.resolve_review_requests_for_question(uid)
            except Exception:
                pass
        refreshed = self.queries.get(uid)
        if refreshed:
            try:
                refreshed["historico_codigos"] = self.queries.code_history(uid, limit=50)
            except Exception:
                refreshed.setdefault("historico_codigos", [])
        curation_state = None
        if refreshed:
            try:
                from core.bank_intelligence import curation_readiness
                curation_state = curation_readiness(refreshed)
            except Exception:
                curation_state = None
        return {
            "ok": True,
            "question": _jsonable(refreshed),
            "stats": self.queries.stats(),
            "code_change": _jsonable(code_change),
            "curation": _jsonable(curation_state),
        }

    def save_question(self, uid: str, payload: dict, approve: bool = False) -> dict:
        result = self.dispatch_studio_v1(
            "questions.update",
            {"uid": uid, "question": payload, "approve": bool(approve)},
        )
        if not result.get("ok"):
            return result
        return {"ok": True, **_jsonable(result.get("data") or {})}

    def _merge_question(self, current: dict, payload: dict, *, approve: bool) -> dict:
        question = copy.deepcopy(current)
        # O tipo da questão governa também alternativas e gabarito. Antes da 5.5.6
        # era possível salvar tipo=certo_errado mantendo A-E no JSON, o que fazia
        # o editor e o Telegram continuarem com aparência de múltipla escolha.
        from core.question_types import (
            TRUE_FALSE,
            canonicalize_question_format,
            normalize_question_type,
            snapshot_format,
        )

        previous_type = normalize_question_type(question.get("tipo", "multipla_escolha"))
        requested_type = normalize_question_type(payload.get("tipo", question.get("tipo", "multipla_escolha")))
        raw_answer = payload.get("gabarito", question.get("gabarito", ""))
        alternatives_raw = payload.get("alternativas", question.get("alternativas", []))
        question_type, alternatives, answer = canonicalize_question_format(
            requested_type,
            alternatives_raw,
            raw_answer,
            reject_invalid_true_false_answer=requested_type == TRUE_FALSE and previous_type == TRUE_FALSE and bool(str(raw_answer or "").strip()),
        )
        if question_type != previous_type:
            history = question.get("historico_formato")
            if not isinstance(history, list):
                history = []
            old_format = snapshot_format(current)
            old_format.update({
                "alterado_em": _utc_now(),
                "origem": "editor_completo_web",
                "tipo_novo": question_type,
            })
            history.append(old_format)
            question["historico_formato"] = history[-50:]

        keys = [item["chave"] for item in alternatives]
        if question_type != TRUE_FALSE and answer and answer not in keys:
            raise ValueError("O gabarito não corresponde a nenhuma alternativa.")
        year = _safe_int(payload.get("ano", question.get("ano")))
        if year is not None and not 1800 <= year <= 2200:
            raise ValueError("O ano deve ter quatro dígitos válidos.")
        topics_raw = payload.get("assuntos", question.get("assuntos", []))
        if isinstance(topics_raw, str):
            topics = [part.strip() for part in topics_raw.split("|") if part.strip()]
        elif isinstance(topics_raw, list):
            topics = [str(part).strip() for part in topics_raw if str(part).strip()]
        else:
            topics = []
        primary = str(payload.get("assunto", question.get("assunto", ""))).strip()
        if primary and primary not in topics:
            topics.insert(0, primary)
        old_matter = str(question.get("materia", "") or "").strip()
        old_lesson = str(question.get("aula_planilha", "") or "").strip()
        matter = str(payload.get("materia", old_matter)).strip()
        lesson = str(payload.get("aula_planilha", old_lesson)).strip()
        classification_changed = matter.casefold() != old_matter.casefold() or lesson.casefold() != old_lesson.casefold()
        code = str(payload.get("codigo_origem", question.get("codigo_origem", ""))).strip()
        if not code:
            raise ValueError("O código da questão não pode ficar vazio.")
        if len(code) > 240 or any(ord(char) < 32 for char in code):
            raise ValueError("O código da questão é inválido.")

        from core.bank_intelligence import normalize_origin_type, split_pipe
        provenance = question.setdefault("proveniencia", {})
        origin_type = normalize_origin_type(payload.get("origem_questao", provenance.get("tipo", question.get("origem_questao", ""))))
        provenance["tipo"] = origin_type
        provenance["fonte_primaria"] = str(payload.get("fonte_primaria", provenance.get("fonte_primaria", ""))).strip()
        if "origem_verificada" in payload:
            provenance["verificada"] = bool(payload.get("origem_verificada"))
        question["origem_questao"] = origin_type
        question["tags"] = split_pipe(payload.get("tags", question.get("tags", [])))
        question["referencias_legais"] = split_pipe(payload.get("referencias_legais", question.get("referencias_legais", [])))
        comment_meta = question.setdefault("comentario_meta", {})
        explanation_text = str(payload.get("explicacao", question.get("explicacao", ""))).strip()
        requested_comment_source = str(payload.get("origem_comentario", comment_meta.get("origem", ""))).strip()
        # Uma explicação existente nunca pode continuar classificada como "sem comentário".
        # Esse estado contraditório fazia o contador da Curadoria permanecer parado
        # mesmo depois de o usuário escrever e salvar uma explicação.
        if explanation_text:
            comment_meta["origem"] = requested_comment_source if requested_comment_source and requested_comment_source != "sem_comentario" else "manual_nao_classificado"
        else:
            comment_meta["origem"] = "sem_comentario"
        curation = question.setdefault("curadoria", {})
        curation["responsavel"] = str(payload.get("curadoria_responsavel", curation.get("responsavel", ""))).strip()
        curation["notas"] = str(payload.get("curadoria_notas", curation.get("notas", ""))).strip()
        editable = {
            "codigo_origem": code,
            "materia": matter,
            "aula_planilha": lesson,
            "assunto": primary,
            "assuntos": topics,
            "trilha_assuntos": [item for item in (matter, lesson, primary) if item],
            "banca": str(payload.get("banca", question.get("banca", ""))).strip(),
            "ano": year,
            "orgao": str(payload.get("orgao", question.get("orgao", ""))).strip(),
            "prova": str(payload.get("prova", question.get("prova", ""))).strip(),
            "cargo": str(payload.get("cargo", question.get("cargo", ""))).strip(),
            "area": str(payload.get("area", question.get("area", ""))).strip(),
            "especialidade": str(payload.get("especialidade", question.get("especialidade", ""))).strip(),
            "turno": str(payload.get("turno", question.get("turno", ""))).strip(),
            "tipo": question_type,
            "gabarito": answer,
            "enunciado": str(payload.get("enunciado", question.get("enunciado", ""))).strip(),
            "alternativas": alternatives,
            "explicacao": str(payload.get("explicacao", question.get("explicacao", ""))).strip(),
            "origem_questao": origin_type,
            "fonte_primaria": provenance.get("fonte_primaria", ""),
            "origem_verificada": bool(provenance.get("verificada", False)),
            "tags": question.get("tags", []),
            "referencias_legais": question.get("referencias_legais", []),
            "origem_comentario": comment_meta.get("origem", ""),
            "curadoria_responsavel": curation.get("responsavel", ""),
            "curadoria_notas": curation.get("notas", ""),
        }
        question.update(editable)
        classification = question.setdefault("classificacao_planilha", {})
        if classification_changed:
            classification.pop("referencia", None)
            classification.pop("contexto_task_id", None)
            question.pop("contexto_importacao_estudos", None)
            history = question.get("historico_classificacao")
            if not isinstance(history, list):
                history = []
            history.append(
                {
                    "alterado_em": _utc_now(),
                    "origem": "editor_completo_web",
                    "materia_anterior": old_matter,
                    "aula_anterior": old_lesson,
                    "materia_nova": matter,
                    "aula_nova": lesson,
                }
            )
            question["historico_classificacao"] = history[-100:]
        classification.update(
            {
                "status": "classificado" if matter and primary else "revisar",
                "confianca": 1.0 if matter and primary else 0.5,
                "metodo": "revisao_manual_web",
                "fonte": self.taxonomy.source_name if self.taxonomy else "Edição manual",
            }
        )
        correct_index = keys.index(answer) if answer in keys else None
        question["telegram"] = {
            "modo": "quiz",
            "pergunta": question["enunciado"],
            "opcoes": [item["texto"] for item in alternatives],
            "indice_correto": correct_index,
        }
        review = question.setdefault("revisao", {})
        if approve:
            review.update({"status": "aprovado", "confianca": 1.0, "alertas": []})
        else:
            review.setdefault("status", "pendente")
        return question

    def _delete_question_record(self, uid: str) -> dict:
        self._ensure_core()
        assert self.commands is not None and self.queries is not None and self.study is not None
        if not self.queries.get(uid):
            return {"ok": False, "error": "Questão não encontrada."}
        self.commands.delete(uid)
        try:
            self.study.rebuild_subject_analytics_daily()
        except Exception:
            pass
        return {"ok": True, "stats": self.queries.stats()}

    def delete_question(self, uid: str) -> dict:
        result = self.dispatch_studio_v1("questions.delete", {"uid": uid})
        if not result.get("ok"):
            return result
        return {"ok": True, **_jsonable(result.get("data") or {})}

    def _annul_question_record(self, uid: str, reason: str = "Questão anulada pela banca") -> dict:
        self._ensure_core()
        assert self.commands is not None and self.queries is not None
        archived = self.commands.archive(uid, kind="anulada", reason=str(reason or "").strip())
        return {"ok": bool(archived), "stats": self.queries.stats()}

    def annul_question(self, uid: str, reason: str = "Questão anulada pela banca") -> dict:
        result = self.dispatch_studio_v1("questions.annul", {"uid": uid, "reason": reason})
        if not result.get("ok"):
            return result
        return {"ok": True, **_jsonable(result.get("data") or {})}

    def attach_image(self, uid: str) -> dict:
        self._ensure_core()
        assert self.commands is not None and self.queries is not None
        question = self.queries.get(uid)
        if not question:
            return {"ok": False, "error": "Questão não encontrada."}
        paths = self._dialog_open(
            multiple=False,
            file_types=("Imagens (*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff)", "Todos os arquivos (*.*)"),
        )
        if not paths:
            return {"ok": False, "cancelled": True}
        source = Path(paths[0])
        target = QUESTION_IMAGE_DIR / f"manual_{uid}{source.suffix.lower() or '.png'}"
        shutil.copy2(source, target)
        question["imagem_questao"] = {
            "path": str(target),
            "origem": "manual",
            "recorte_automatico": False,
            "precisa_revisao": False,
        }
        self.commands.update(uid, question)
        return {"ok": True, "image": self._image_data(question)}

    def _remove_image_record(self, uid: str) -> dict:
        self._ensure_core()
        assert self.commands is not None and self.queries is not None
        question = self.queries.get(uid)
        if not question:
            return {"ok": False, "error": "Questão não encontrada."}
        info = question.pop("imagem_questao", None)
        if isinstance(info, dict):
            path = Path(str(info.get("path", "")))
            try:
                if path.exists() and QUESTION_IMAGE_DIR in path.parents:
                    path.unlink()
            except Exception:
                pass
        self.commands.update(uid, question)
        return {"ok": True}

    def remove_image(self, uid: str) -> dict:
        result = self.dispatch_studio_v1("questions.image.remove", {"uid": uid})
        if not result.get("ok"):
            return result
        return {"ok": True, **_jsonable(result.get("data") or {})}

    def _image_data(self, question: dict) -> dict | None:
        info = question.get("imagem_questao", {}) if isinstance(question.get("imagem_questao"), dict) else {}
        path_text = str(info.get("path", "")).strip()
        if not path_text:
            return None
        path = Path(path_text)
        if not path.exists() or not path.is_file():
            return None
        try:
            mime = mimetypes.guess_type(path.name)[0] or "image/png"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return {"src": f"data:{mime};base64,{encoded}", "name": path.name, "meta": _jsonable(info)}
        except Exception:
            return None

    # -------------------------- import and async tasks ---------------------
    def choose_import_files(self, pdf_only: bool = False) -> dict:
        file_types = (
            ("PDF com questões (*.pdf)", "Todos os arquivos (*.*)")
            if bool(pdf_only)
            else (
                "PDF e imagens (*.pdf;*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff)",
                "Todos os arquivos (*.*)",
            )
        )
        paths = self._dialog_open(multiple=True, file_types=file_types)
        if pdf_only:
            paths = [path for path in paths if Path(path).suffix.casefold() == ".pdf"]
        return {"paths": paths}

    def _resolve_study_import_context(self, context: dict | None) -> dict | None:
        """Resolve uma importação contextual contra a cobertura atual.

        Desde a 5.5.6 a unidade preferencial é ``trilha + matéria + aula``.
        Isso permite importar um único PDF de uma aula que apareceu em várias
        linhas do CICLO_REG sem forçar todas as questões para uma parte específica.
        O ``task_id`` individual continua aceito para compatibilidade.
        """
        if not context:
            return None
        if not isinstance(context, dict):
            raise ValueError("Contexto de importação inválido.")
        self._ensure_core()
        assert self.study is not None
        tasks = self.taxonomy.tasks if self.taxonomy else []

        group_id = _clean_text(context.get("group_id"))
        if group_id:
            analysis = self.study.studied_lesson_group_coverage(tasks)
            row = next((dict(item) for item in analysis.get("items", []) if str(item.get("group_id", "")) == group_id), None)
            if row is None:
                raise ValueError("A aula estudada selecionada não está mais disponível. Sincronize a planilha e tente novamente.")
            parts = [str(value).strip() for value in row.get("content_parts", []) if str(value).strip()]
            return {
                "group_id": group_id,
                "task_ids": [str(value) for value in row.get("task_ids", []) if str(value)],
                "trilha": _clean_text(row.get("trilha")),
                "tarefas": [str(value) for value in row.get("tarefas", []) if str(value)],
                "materia": _clean_text(row.get("subject")),
                "aula": _clean_text(row.get("lesson")),
                "conteudo": _clean_text(row.get("content")),
                "conteudos": parts,
                "descricao": _clean_text(row.get("description")),
                "questoes_planilha": int(row.get("questions_done", 0) or 0),
                "questoes_banco_antes": int(row.get("bank_question_count", 0) or 0),
                "faltam_antes": row.get("missing_question_count"),
                "missing_exact": bool(row.get("missing_exact")),
                "needs_attention": bool(row.get("needs_attention")),
                "task_count": int(row.get("task_count", len(row.get("task_ids", []))) or 0),
            }

        task_id = _clean_text(context.get("task_id"))
        if not task_id:
            raise ValueError("O conteúdo estudado não possui identificador para importação contextual.")
        analysis = self.study.studied_content_coverage(tasks)
        row = next((dict(item) for item in analysis.get("items", []) if str(item.get("task_id", "")) == task_id), None)
        if row is None:
            raise ValueError("O conteúdo estudado selecionado não está mais disponível. Sincronize a planilha e tente novamente.")
        description = _clean_text(row.get("description"))
        content = _clean_text(row.get("content")) or description
        return {
            "task_id": task_id,
            "trilha": _clean_text(row.get("trilha")),
            "tarefa": _clean_text(row.get("tarefa")),
            "materia": _clean_text(row.get("subject")),
            "aula": _clean_text(row.get("lesson")),
            "conteudo": content,
            "descricao": description or content,
            "questoes_planilha": int(row.get("questions_done", 0) or 0),
            "questoes_banco_antes": int(row.get("bank_question_count", 0) or 0),
            "faltam_antes": row.get("missing_question_count"),
            "needs_attention": bool(row.get("needs_attention")),
        }

    def _apply_study_import_context(self, result: dict, context: dict | None) -> dict:
        """Vincula o lote à aula estudada escolhida pelo usuário.

        Código, enunciado, alternativas, gabarito, banca e assuntos finos continuam
        vindo do extrator. Matéria e aula são autoritativas. Quando o contexto é um
        grupo, nenhuma parte isolada da aula recebe uma referência falsa.
        """
        if not context:
            return result
        matter = _clean_text(context.get("materia"))
        lesson = _clean_text(context.get("aula"))
        content = _clean_text(context.get("conteudo"))
        reference = _clean_text(context.get("descricao")) or content
        trail = _clean_text(context.get("trilha"))
        task = _clean_text(context.get("tarefa"))
        group_id = _clean_text(context.get("group_id"))
        task_ids = [str(value) for value in context.get("task_ids", []) if str(value)] if isinstance(context.get("task_ids"), list) else []
        is_group = bool(group_id)
        source_name = str(getattr(self.taxonomy, "source_name", "") or "Planilha de estudos")
        for question in result.get("questions", []):
            if not isinstance(question, dict):
                continue
            previous_matter = _clean_text(question.get("materia"))
            previous_lesson = _clean_text(question.get("aula_planilha"))
            if previous_matter and previous_matter != matter:
                question.setdefault("materia_origem", previous_matter)
            if previous_lesson and previous_lesson != lesson:
                question.setdefault("aula_origem", previous_lesson)
            question["materia"] = matter or previous_matter
            question["aula_planilha"] = lesson or previous_lesson

            primary = _clean_text(question.get("assunto"))
            topics = question.get("assuntos", [])
            if isinstance(topics, str):
                topics = [part.strip() for part in topics.split("|") if part.strip()]
            elif not isinstance(topics, list):
                topics = []
            topics = [_clean_text(item) for item in topics if _clean_text(item)]
            if not primary and not is_group:
                primary = content
                question["assunto"] = primary
            if primary and primary not in topics:
                topics.insert(0, primary)
            # Em um grupo de aula, não adicionamos a descrição concatenada de todas
            # as partes como se fosse um assunto de cada questão.
            if not is_group and content and content.casefold() not in {item.casefold() for item in topics}:
                topics.append(content)
            question["assuntos"] = topics
            question["trilha_assuntos"] = [item for item in [matter, lesson, primary] if item]

            classification = question.get("classificacao_planilha")
            if not isinstance(classification, dict):
                classification = {}
            if is_group:
                classification.pop("referencia", None)
                classification.pop("contexto_task_id", None)
                classification.update(
                    {
                        "status": "classificado",
                        "confianca": 1.0,
                        "metodo": "importacao_contextual_aula",
                        "fonte": source_name,
                        "contexto_group_id": group_id,
                        "contexto_task_ids": task_ids,
                    }
                )
            else:
                classification.update(
                    {
                        "status": "classificado",
                        "confianca": 1.0,
                        "metodo": "importacao_contextual_estudo",
                        "referencia": reference,
                        "fonte": source_name,
                        "contexto_task_id": str(context.get("task_id", "")),
                    }
                )
            question["classificacao_planilha"] = classification
            if is_group:
                question["contexto_importacao_estudos"] = {
                    "group_id": group_id,
                    "task_ids": task_ids,
                    "trilha": trail,
                    "materia": matter,
                    "aula": lesson,
                    "conteudos": list(context.get("conteudos", []) or []),
                }
            else:
                question["contexto_importacao_estudos"] = {
                    "task_id": str(context.get("task_id", "")),
                    "trilha": trail,
                    "tarefa": task,
                    "materia": matter,
                    "aula": lesson,
                    "conteudo": content,
                    "referencia": reference,
                }
        result["study_import_context"] = dict(context)
        taxonomy_meta = result.get("taxonomy")
        if not isinstance(taxonomy_meta, dict):
            taxonomy_meta = {}
        taxonomy_meta["contextual_study_import"] = {
            "group_id": group_id,
            "task_id": str(context.get("task_id", "")),
            "materia": matter,
            "aula": lesson,
            "referencia": "" if is_group else reference,
        }
        result["taxonomy"] = taxonomy_meta
        return result

    def start_import(self, paths: list[str], import_context: dict | None = None) -> dict:
        valid = [str(Path(path)) for path in paths if Path(path).exists()]
        if not valid:
            return {"ok": False, "error": "Nenhum arquivo válido foi selecionado."}
        resolved_context = self._resolve_study_import_context(import_context)
        return self._start_task(
            "import",
            lambda task_id: self._import_worker(task_id, valid, resolved_context),
        )

    def _import_worker(self, task_id: str, paths: list[str], import_context: dict | None = None) -> dict:
        # OCR/PDF libraries are intentionally imported only when an import is
        # requested. Loading OpenCV, PyMuPDF and OCR helpers during normal app
        # startup added several seconds on some Windows installations.
        self._ensure_core()
        assert self.commands is not None and self.study is not None
        from core.extractor import ExtractorConfig, extract_pdf

        total = len(paths)
        inserted = duplicates = repaired = extracted = 0
        reports: list[dict] = []
        config = ExtractorConfig(
            dpi=int(self.config.get("dpi", 180) or 180),
            languages=str(self.config.get("languages", "por+eng")),
            tesseract_cmd=str(self.config.get("tesseract_cmd", "")),
        )
        for index, path_text in enumerate(paths):
            path = Path(path_text)

            def progress(value: float, message: str, *, _index=index, _path=path) -> None:
                overall = (_index + max(0.0, min(1.0, float(value)))) / max(1, total)
                self._update_task(task_id, progress=overall, message=f"{_path.name}: {message}")

            try:
                result = extract_pdf(
                    path,
                    config=config,
                    progress=progress,
                    taxonomy=self.taxonomy,
                    asset_dir=QUESTION_IMAGE_DIR,
                    markdown_cache_dir=MARKDOWN_CACHE_DIR,
                )
                result = self._apply_study_import_context(result, import_context)
                result.setdefault("source_path", str(path.resolve()))
                count = len(result.get("questions", []))
                if count == 0:
                    raise ValueError(
                        "Nenhuma questão foi reconhecida. O arquivo é válido, mas o layout ainda não pôde ser identificado."
                    )
                imported = self.commands.import_extraction(result)
                extracted += count
                inserted += int(imported.get("inserted", 0))
                duplicates += int(imported.get("duplicates", 0))
                repaired += int(imported.get("repaired", 0))
                reports.append({"file": path.name, "ok": True, "extracted": count, **_jsonable(imported)})
            except Exception as error:
                reports.append({"file": path.name, "ok": False, "error": str(error)})
            self._update_task(
                task_id,
                progress=(index + 1) / max(1, total),
                message=f"Concluído {index + 1}/{total}",
            )
        try:
            self.study.sync_questions()
        except Exception:
            pass
        coverage_after = None
        if import_context:
            try:
                tasks = self.taxonomy.tasks if self.taxonomy else []
                if import_context.get("group_id"):
                    refreshed = self.study.studied_lesson_group_coverage(tasks)
                    coverage_after = next(
                        (item for item in refreshed.get("items", []) if str(item.get("group_id", "")) == str(import_context.get("group_id", ""))),
                        None,
                    )
                else:
                    refreshed = self.study.studied_content_coverage(tasks)
                    coverage_after = next(
                        (item for item in refreshed.get("items", []) if str(item.get("task_id", "")) == str(import_context.get("task_id", ""))),
                        None,
                    )
            except Exception:
                coverage_after = None
        return {
            "files": total,
            "extracted": extracted,
            "inserted": inserted,
            "duplicates": duplicates,
            "repaired": repaired,
            "reports": reports,
            "import_context": _jsonable(import_context),
            "coverage_after": _jsonable(coverage_after),
        }

    def start_reread(self, uid: str) -> dict:
        self._ensure_core()
        assert self.queries is not None
        question = self.queries.get(uid)
        if not question:
            return {"ok": False, "error": "Questão não encontrada."}
        source = question.get("fonte", {}) if isinstance(question.get("fonte"), dict) else {}
        path_text = str(source.get("caminho_arquivo", "")).strip()
        if not path_text or not Path(path_text).exists():
            chosen = self._dialog_open(
                multiple=False,
                file_types=(
                    "PDF e imagens (*.pdf;*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff)",
                    "Todos os arquivos (*.*)",
                ),
            )
            if not chosen:
                return {"ok": False, "cancelled": True}
            path_text = chosen[0]
        return self._start_task(
            "reread",
            lambda task_id: self._reread_worker(task_id, uid, question, Path(path_text)),
        )

    @staticmethod
    def _find_candidate(current: dict, candidates: list[dict]) -> dict | None:
        code = _clean_text(current.get("codigo_origem", "")).upper()
        if code:
            for item in candidates:
                if _clean_text(item.get("codigo_origem", "")).upper() == code:
                    return item
        statement = _clean_text(current.get("enunciado", "")).casefold()
        if not statement:
            return candidates[0] if len(candidates) == 1 else None
        current_tokens = set(re.findall(r"[\wÀ-ÿ]{4,}", statement))
        best: tuple[float, dict] | None = None
        for item in candidates:
            other = _clean_text(item.get("enunciado", "")).casefold()
            tokens = set(re.findall(r"[\wÀ-ÿ]{4,}", other))
            if not tokens:
                continue
            score = len(current_tokens & tokens) / max(1, len(current_tokens | tokens))
            if best is None or score > best[0]:
                best = (score, item)
        return best[1] if best and best[0] >= 0.42 else None

    def _reread_worker(self, task_id: str, uid: str, current: dict, source: Path) -> dict:
        self._ensure_core()
        assert self.commands is not None and self.queries is not None
        from core.extractor import ExtractorConfig, deep_repair_question, extract_pdf

        config = ExtractorConfig(
            dpi=max(260, int(self.config.get("deep_analysis_dpi", 300) or 300)),
            languages=str(self.config.get("languages", "por+eng")),
            tesseract_cmd=str(self.config.get("tesseract_cmd", "")),
        )

        def progress(value: float, message: str) -> None:
            self._update_task(task_id, progress=value, message=message)

        extraction = extract_pdf(
            source,
            config=config,
            progress=progress,
            taxonomy=self.taxonomy,
            asset_dir=QUESTION_IMAGE_DIR,
            markdown_cache_dir=MARKDOWN_CACHE_DIR,
            force_markdown_ocr=True,
        )
        candidate = self._find_candidate(current, list(extraction.get("questions", [])))
        if not candidate:
            raise RuntimeError("A questão não foi localizada com segurança no arquivo selecionado.")
        refreshed = copy.deepcopy(candidate)
        refreshed["id"] = current.get("id", refreshed.get("id"))
        refreshed["codigo_origem"] = current.get("codigo_origem", refreshed.get("codigo_origem"))
        refreshed["fingerprint"] = current.get("fingerprint", refreshed.get("fingerprint"))
        refreshed["database_uid"] = uid
        refreshed.setdefault("fonte", {})["caminho_arquivo"] = str(source.resolve())
        old_classification = current.get("classificacao_planilha", {})
        if isinstance(old_classification, dict) and old_classification.get("metodo") in {
            "revisao_manual",
            "revisao_manual_web",
        }:
            for key in ("materia", "aula_planilha", "assunto", "assuntos", "trilha_assuntos"):
                refreshed[key] = current.get(key, refreshed.get(key))
            refreshed["classificacao_planilha"] = old_classification
        old_image = current.get("imagem_questao", {})
        if isinstance(old_image, dict) and old_image.get("origem") == "manual":
            refreshed["imagem_questao"] = old_image
        if str(current.get("explicacao", "")).strip():
            refreshed["explicacao"] = current.get("explicacao", "")
        refreshed = deep_repair_question(
            refreshed,
            self.taxonomy,
            allow_auto_approve=True,
            method="web_ui_markdown_ocr_apurado",
        )
        self.commands.update(uid, refreshed)
        return {"uid": uid, "question": _jsonable(self.queries.get(uid))}

    def _prune_tasks_locked(self) -> None:
        """Keep the task registry bounded during long-running desktop sessions."""
        if len(self.tasks) <= self._task_history_limit:
            return
        protected = set(self._active_task_by_kind.values())
        removable = [
            task_id
            for task_id, item in self.tasks.items()
            if task_id not in protected and item.get("status") in {"done", "error", "missing"}
        ]
        excess = max(0, len(self.tasks) - self._task_history_limit)
        for task_id in removable[:excess]:
            self.tasks.pop(task_id, None)

    def _start_task(
        self,
        kind: str,
        worker: Callable[[str], dict],
        *,
        coalesce: bool = False,
    ) -> dict:
        task_id = uuid.uuid4().hex
        with self.task_lock:
            if coalesce:
                active_id = self._active_task_by_kind.get(kind)
                active = self.tasks.get(active_id or "")
                if active and active.get("status") in {"queued", "running"}:
                    return {"ok": True, "task_id": active_id, "reused": True}
            self._prune_tasks_locked()
            self.tasks[task_id] = {
                "id": task_id,
                "kind": kind,
                "status": "queued",
                "progress": 0.0,
                "message": "Preparando...",
                "created_at": _utc_now(),
            }
            if coalesce:
                self._active_task_by_kind[kind] = task_id

        def runner() -> None:
            started_monotonic = time.monotonic()
            self._update_task(task_id, status="running", started_at=_utc_now())
            try:
                result = worker(task_id)
                self._update_task(task_id, status="done", progress=1.0, message="Concluído", result=result, finished_at=_utc_now(), duration_seconds=round(time.monotonic()-started_monotonic, 3))
            except Exception as error:
                self._update_task(
                    task_id,
                    status="error",
                    message=str(error),
                    error=str(error),
                    traceback=traceback.format_exc(),
                    finished_at=_utc_now(),
                    duration_seconds=round(time.monotonic()-started_monotonic, 3),
                )
            finally:
                with self.task_lock:
                    if self._active_task_by_kind.get(kind) == task_id:
                        self._active_task_by_kind.pop(kind, None)
                    self._prune_tasks_locked()

        io_kinds = {"tutor_ai", "ai_commentary", "google_commentary_research", "update-monitor", "send_cycle"}
        if kind in io_kinds:
            try:
                self.background_runtime.run_blocking(runner)
            except Exception:
                self.executor.submit(runner)
        else:
            self.executor.submit(runner)
        return {"ok": True, "task_id": task_id}

    def _update_task(self, task_id: str, **values: Any) -> None:
        with self.task_lock:
            item = self.tasks.get(task_id)
            if item is not None:
                item.update(_jsonable(values))
                item["updated_at"] = _utc_now()

    def poll_task(self, task_id: str) -> dict:
        with self.task_lock:
            item = copy.deepcopy(self.tasks.get(task_id))
        return item or {"status": "missing", "error": "Tarefa não encontrada."}

    # -------------------------- flow / Telegram ----------------------------
    def _flow_status(self) -> dict:
        if self.flow is None:
            return {
                "running": False,
                "listening": False,
                "paused": False,
                "next_run": None,
                "initializing": not self._core_ready.is_set(),
            }
        next_run = self.flow.next_run
        return {
            "running": self.flow.running,
            "listening": self.flow.listening,
            "paused": self.flow.paused,
            "telegram_questions_paused": bool(self.config.get("telegram_questions_paused", False)),
            "next_run": next_run.isoformat() if next_run else None,
        }

    def get_flow(self) -> dict:
        self._ensure_core()
        assert self.study is not None
        return _jsonable(
            {
                "status": self._flow_status(),
                "settings": self._public_config(),
                "stats": self.study.stats(),
                "recent": self.study.recent_deliveries(limit=100),
                "failed": self.study.failed_deliveries(limit=50, due_only=False),
                "adaptive": self.study.adaptive_dashboard(),
                "optimizer": self.study.fsrs_optimizer_status(),
                "learning": self.study.learning_preferences(),
            }
        )

    def test_telegram_connection(self, token: str = "", chat_id: str = "") -> dict:
        """Validate the Telegram bot token without exposing the saved secret."""
        candidate_token = str(token or self.config.get("telegram_bot_token", "")).strip()
        candidate_chat = str(chat_id or self.config.get("telegram_chat_id", "")).strip()
        if not candidate_token:
            return {"ok": False, "error": "Informe o token do bot do Telegram."}
        try:
            from core.telegram import get_me

            result = get_me(candidate_token, timeout=15)
            bot = result.get("result", {}) if isinstance(result, dict) else {}
            return {
                "ok": True,
                "bot_name": bot.get("first_name") or bot.get("username") or "Bot conectado",
                "username": bot.get("username") or "",
                "chat_id": candidate_chat,
                "chat_configured": bool(candidate_chat),
            }
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def save_flow_settings(self, payload: dict) -> dict:
        allowed = {
            key
            for key in self.config
            if key.startswith("flow_") or key in {"telegram_bot_token", "telegram_chat_id"}
        }
        data = dict(payload or {})
        token_update = str(data.get("telegram_bot_token") or "").strip()
        if token_update:
            try:
                from core.telegram_secrets import save_telegram_token
                save_telegram_token(self.config_path, token_update)
                self.config["telegram_bot_token"] = token_update
            except Exception as error:
                return {"ok": False, "error": f"Não foi possível proteger o token do Telegram: {error}"}
        for key, value in data.items():
            if key not in allowed or key == "telegram_bot_token":
                continue
            self.config[key] = value
        self._persist_config()
        self._ensure_core()
        if self.study is not None:
            self.study.set_learning_preferences(
                target_retention=float(self.config.get("flow_target_retention", 0.88) or 0.88),
                retention_mode=str(self.config.get("flow_target_retention_mode", "optimized") or "optimized"),
                exam_date=str(self.config.get("flow_exam_date", "") or ""),
                daily_minutes=int(self.config.get("flow_daily_study_minutes", 45) or 45),
                maximum_interval_days=int(self.config.get("flow_fsrs_max_interval_days", 365) or 365),
                relearning_minutes=int(self.config.get("flow_relearning_minutes", 10) or 10),
                studied_only=bool(self.config.get("flow_studied_only", True)),
                early_review_enabled=bool(self.config.get("flow_early_review_enabled", False)),
            )
        return {"ok": True, "settings": self._public_config(), "optimizer": self.study.fsrs_optimizer_status() if self.study else {}}

    def flow_action(self, action: str) -> dict:
        self._ensure_core()
        assert self.flow is not None and self.study is not None
        action = str(action or "").lower()
        try:
            if action == "start":
                self._watchdog_flow_expected = True
                self.flow.start(start_listener=True)
            elif action == "pause":
                self.flow.pause()
            elif action == "resume":
                self.flow.resume()
            elif action == "pause_questions":
                self.config["telegram_questions_paused"] = True
                self._persist_config()
            elif action == "resume_questions":
                self.config["telegram_questions_paused"] = False
                self._persist_config()
            elif action == "stop":
                self._watchdog_flow_expected = False
                self.flow.stop()
            elif action == "retry_all":
                self.flow.retry_all_failed(requested_via="web_ui")
            elif action == "send_now":
                return self._start_task("send_cycle", lambda _task_id: self.flow.send_cycle_now())
            elif action == "optimize_fsrs":
                return self._start_task("optimize_fsrs", lambda _task_id: self.study.optimize_fsrs(force=True))
            elif action == "reset":
                if self.flow.sending:
                    return {
                        "ok": False,
                        "error": "Há um ciclo enviando questões neste momento. Aguarde o envio terminar e tente reiniciar novamente.",
                    }
                # Reinício protegido: pause o ciclo, crie backup consistente e
                # somente então zere o aprendizado. O listener pode continuar
                # com seu offset preservado, mas nenhuma fila antiga será
                # reaplicada depois da operação.
                was_paused = self.flow.paused
                self.flow.pause()
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                backup_dir = self.database_path.parent / "backups"
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_path = backup_dir / f"QuestFlow-pre-reset-{timestamp}.sqlite"
                assert self.database is not None
                try:
                    self.database.backup(backup_path)
                    cloud_generation = None
                    if self.cloud_sync is not None:
                        cloud_generation = self.cloud_sync.begin_global_reset()
                    reset_info = self.study.reset_progress()
                    self.study.sync_questions()
                    self.study.set_runtime("unanswered_policy_version", "3.0.14")
                    self.study.set_runtime("unanswered_resend_activated_at", _utc_now())
                    self.study.set_runtime("schedule_activated_at", datetime.now().isoformat(timespec="seconds"))
                    with self._dashboard_cache_lock:
                        self._dashboard_cache = {}
                    try:
                        self._dashboard_cache_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                except Exception:
                    # O banco ativo permanece transacional; o backup pré-reset
                    # ainda existe para restauração manual em caso de falha.
                    raise
                finally:
                    if not was_paused:
                        self.flow.resume()
                return {
                    "ok": True,
                    "status": self._flow_status(),
                    "backup_path": str(backup_path),
                    "reset": _jsonable(reset_info),
                    "cloud_generation": cloud_generation,
                }
            else:
                return {"ok": False, "error": "Ação desconhecida."}
        except Exception as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "status": self._flow_status()}

    # -------------------------- corrections / coverage --------------------
    def list_corrections(self, status: str = "ativas") -> dict:
        self._ensure_core()
        assert self.study is not None
        editorial = [
            dict(
                item,
                item_type="correction",
                type_label="Correção da questão",
                created_at=str(item.get("requested_at") or item.get("updated_at") or ""),
                question_code=str(item.get("source_code") or ""),
                materia=str(item.get("subject") or ""),
                assunto=str(item.get("primary_topic") or ""),
            )
            for item in self.study.list_review_requests(status=status, limit=2000)
        ]
        study_backlog: list[dict] = []
        if self.mobile_foundation is not None and status in {"ativas", "todas"}:
            backlog_status = "pending" if status == "ativas" else "all"
            study_backlog = self.mobile_foundation.list_study_backlog_for_studio(status=backlog_status, limit=2000)
        items = editorial + study_backlog
        items.sort(key=lambda item: str(item.get("updated_at") or item.get("requested_at") or item.get("created_at") or ""), reverse=True)
        return {
            "items": _jsonable(items),
            "corrections": _jsonable(editorial),
            "not_studied": _jsonable(study_backlog),
            "summary": {
                "editorial": len(editorial),
                "not_studied": len(study_backlog),
                "total": len(items),
            },
        }

    def correction_action(self, request_id: str, action: str) -> dict:
        self._ensure_core()
        assert self.study is not None
        try:
            raw_id = str(request_id or "")
            if raw_id.startswith("not_studied:"):
                if self.mobile_foundation is None:
                    return {"ok": False, "error": "Serviço Mobile não disponível."}
                backlog_id = raw_id.split(":", 1)[1]
                return _jsonable(self.mobile_foundation.studio_study_backlog_action(backlog_id, action))
            if action == "open":
                self.study.mark_review_opened(raw_id)
            elif action == "resolve":
                self.study.resolve_review_request(raw_id)
            elif action == "delete":
                self.study.delete_review_request(raw_id)
            else:
                return {"ok": False, "error": "Ação desconhecida."}
        except Exception as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True}

    def get_coverage(self) -> dict:
        self._ensure_core()
        assert self.study is not None
        tasks = self.taxonomy.tasks if self.taxonomy else []
        analysis = self.study.studied_lesson_group_coverage(tasks)
        labels = {
            "faltam_questoes": "Sem cobertura: adicionar questões",
            "cobertura_parcial": "Cobertura parcial",
            "sem_questoes": "Conteúdo estudado sem questão",
            "coberto": "Coberto",
            "coberto_sem_meta": "Há questões cadastradas",
        }
        items: list[dict] = []
        for raw in analysis.get("items", []):
            item = dict(raw)
            status = str(item.get("status", ""))
            missing = item.get("missing_question_count")
            if missing is None:
                missing_display = "A definir" if item.get("needs_attention") else "—"
            else:
                amount = max(0, int(missing or 0))
                missing_display = str(amount) if item.get("missing_exact", False) or amount == 0 else f"≥ {amount}"
            item.update(
                {
                    "materia": item.get("subject", ""),
                    "aula": item.get("lesson", ""),
                    "conteudo": item.get("content", ""),
                    "questoes_planilha": item.get("questions_done", 0),
                    "questoes_banco": item.get("bank_question_count", 0),
                    "faltam_adicionar": missing,
                    "faltam_display": missing_display,
                    "acertos_planilha": item.get("correct_answers", 0),
                    "desempenho_planilha": item.get("performance", 0),
                    "ch_efetiva": item.get("effective_time", ""),
                    "situacao": labels.get(status, status),
                    "status_code": status,
                }
            )
            items.append(item)
        source = self.taxonomy.payload.get("source", {}) if self.taxonomy else {}
        generated_at = self.taxonomy.payload.get("generated_at", "") if self.taxonomy else ""
        from core.trail_guides import ensure_registry, guide_status_for_tasks

        guide_registry = ensure_registry(self.trail_guides_path)
        guide_status = guide_status_for_tasks(tasks, guide_registry)
        return {
            "items": _jsonable(items),
            "summary": _jsonable(analysis.get("summary", {})),
            "source": _jsonable(source),
            "generated_at": str(generated_at or ""),
            "guide_status": _jsonable(guide_status),
        }

    def get_course_catalog_settings(self) -> dict:
        """Return the active spreadsheet/catalog status for the Web Studio settings page."""
        self._ensure_core()
        from core.course_catalog import CourseCatalogService, MERGE_STRATEGY

        payload = dict(self.taxonomy.payload) if self.taxonomy is not None else {}
        source = dict(payload.get("source", {}) or {})
        logic = dict(payload.get("spreadsheet_logic", {}) or {})
        catalog = dict(payload.get("course_catalog", {}) or {})
        tasks = [dict(item) for item in payload.get("tarefas_referencia", [])]

        trails: list[int] = []
        for task in tasks:
            match = re.search(r"(\d+)", str(task.get("trilha") or ""))
            if match:
                trails.append(int(match.group(1)))
        unique_trails = sorted(set(trails))
        if unique_trails:
            trail_range = f"Trilhas {unique_trails[0]:02d} a {unique_trails[-1]:02d}"
        else:
            trail_range = "Faixa de trilhas não identificada"

        service = CourseCatalogService(self.database, self.taxonomy_path, self.config_path)
        imports = service.recent_imports(1)
        last_import = imports[0] if imports else {}
        last_sync = str(last_import.get("imported_at") or payload.get("generated_at") or "")
        url = str(self.config.get("taxonomy_spreadsheet_url") or source.get("url") or "").strip()
        sheets = [str(logic.get("mapa_sheet") or ""), str(logic.get("ciclo_sheet") or "")]
        return _jsonable({
            "ok": True,
            "url": url,
            "source": source,
            "source_title": str(source.get("title") or "Planilha configurada"),
            "trail_range": trail_range,
            "trail_count": len(unique_trails),
            "lesson_count": len(tasks),
            "last_sync": last_sync,
            "catalog_version": str(catalog.get("version") or self.config.get("course_catalog_version") or "snapshot legado"),
            "merge_strategy": MERGE_STRATEGY,
            "sheets": [item for item in sheets if item],
        })

    def preflight_course_catalog(self, url: str) -> dict:
        """Read the proposed Google Sheet and compare it without changing DB/config."""
        self._ensure_core()
        from core.spreadsheet_taxonomy import build_taxonomy_from_xlsx, download_public_spreadsheet
        from core.course_catalog import CourseCatalogService

        requested_url = str(url or "").strip()
        if not requested_url:
            return {"ok": False, "error": "Informe o link da nova planilha."}
        try:
            with tempfile.TemporaryDirectory(prefix="questflow-catalog-web-preflight-") as temp_dir:
                xlsx = download_public_spreadsheet(requested_url, Path(temp_dir) / "trilhas.xlsx")
                payload = build_taxonomy_from_xlsx(xlsx, source_url=requested_url)
            current_payload = dict(self.taxonomy.payload) if self.taxonomy is not None else {}
            service = CourseCatalogService(self.database, self.taxonomy_path, self.config_path)
            report = service.preflight(payload, current_payload)
            return {"ok": True, "ready": bool(report.get("ok")), "preflight": _jsonable(report)}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def apply_course_catalog(self, url: str, resolutions: dict | None = None) -> dict:
        """Apply a previously reviewed catalog source using the safe merge service."""
        self._ensure_core()
        from core.spreadsheet_taxonomy import SpreadsheetTaxonomy, build_taxonomy_from_xlsx, download_public_spreadsheet
        from core.course_catalog import CourseCatalogService

        requested_url = str(url or "").strip()
        if not requested_url:
            return {"ok": False, "error": "Informe o link da nova planilha."}
        try:
            with self._coverage_sync_lock:
                with tempfile.TemporaryDirectory(prefix="questflow-catalog-web-merge-") as temp_dir:
                    xlsx = download_public_spreadsheet(requested_url, Path(temp_dir) / "trilhas.xlsx")
                    payload = build_taxonomy_from_xlsx(xlsx, source_url=requested_url)
                current_payload = dict(self.taxonomy.payload) if self.taxonomy is not None else {}
                service = CourseCatalogService(self.database, self.taxonomy_path, self.config_path)
                result = service.apply(payload, current_payload, new_url=requested_url, resolutions=dict(resolutions or {}))
                taxonomy = SpreadsheetTaxonomy(dict(result.get("payload") or payload), self.taxonomy_path)
                with self._core_lock:
                    self.taxonomy = taxonomy
                self.config["taxonomy_spreadsheet_url"] = requested_url
                self.config["course_catalog_version"] = str(result.get("catalog_version") or "")
                self.config["course_catalog_last_import_id"] = str(result.get("import_id") or "")
                if self.study is not None:
                    self.study.refresh_studied_scope(taxonomy.tasks)
            response = {k: v for k, v in result.items() if k != "payload"}
            response.update({"ok": True, "message": "Planilha atualizada com mesclagem segura; o progresso pessoal foi preservado."})
            return _jsonable(response)
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def sync_study_coverage(self) -> dict:
        """Refresh CICLO_REG from Google Sheets and return studied-content gaps."""
        self._ensure_core()
        with self._coverage_sync_lock:
            try:
                from core.spreadsheet_taxonomy import (
                    SpreadsheetTaxonomy,
                    build_taxonomy_from_xlsx,
                    download_public_spreadsheet,
                )
                from core.course_catalog import CourseCatalogService

                url = str(
                    self.config.get(
                        "taxonomy_spreadsheet_url",
                        "https://docs.google.com/spreadsheets/d/1lT6I_8fgNiBSt7wlfGH7eXfubkupbAsH03gkxJ7jBd4/edit?usp=sharing",
                    )
                    or ""
                ).strip()
                if not url:
                    raise ValueError("O endereço da planilha de estudos não está configurado.")
                with tempfile.TemporaryDirectory(prefix="questflow-estudos-") as temp_dir:
                    xlsx = download_public_spreadsheet(url, Path(temp_dir) / "ciclo_reg.xlsx")
                    payload = build_taxonomy_from_xlsx(xlsx, source_url=url)
                current_payload = dict(self.taxonomy.payload) if self.taxonomy is not None else {}
                service = CourseCatalogService(self.database, self.taxonomy_path, self.config_path)
                preflight = service.preflight(payload, current_payload)
                if not preflight.get("ok"):
                    raise ValueError("A nova versão da planilha possui correspondências incertas; use o Studio para revisar antes de aplicar.")
                merged = service.apply(payload, current_payload, new_url=url)
                taxonomy = SpreadsheetTaxonomy(dict(merged.get("payload") or payload), self.taxonomy_path)
                with self._core_lock:
                    self.taxonomy = taxonomy
                if self.study is not None:
                    self.study.refresh_studied_scope(taxonomy.tasks)
                result = self.get_coverage()
                result.update(
                    {
                        "ok": True,
                        "synced": True,
                        "catalog_merge": _jsonable({k: v for k, v in merged.items() if k != "payload"}),
                        "message": "Planilha sincronizada com mesclagem segura; progresso pessoal preservado.",
                    }
                )
                return result
            except Exception as error:
                # Keep the last valid snapshot usable when Google/proxy is temporarily unavailable.
                result = self.get_coverage()
                result.update(
                    {
                        "ok": False,
                        "synced": False,
                        "error": str(error),
                        "message": "Não foi possível atualizar o Google Sheets; exibindo o último snapshot local disponível.",
                    }
                )
                return result

    def choose_trail_guide_files(self) -> dict:
        paths = self._dialog_open(
            multiple=True,
            file_types=("PDFs explicativos das trilhas (*.pdf)", "Todos os arquivos (*.*)"),
        )
        return {"paths": paths}

    def import_trail_guides(self, paths: list[str]) -> dict:
        valid = [str(Path(path)) for path in (paths or []) if Path(path).exists()]
        if not valid:
            return {"ok": False, "error": "Nenhum PDF válido de trilha foi selecionado."}
        try:
            from core.trail_guides import import_guide_pdfs, guide_status_for_tasks

            imported = import_guide_pdfs(valid, self.trail_guides_path)
            tasks = self.taxonomy.tasks if self.taxonomy else []
            imported["status"] = guide_status_for_tasks(tasks, imported.get("registry", {}))
            if imported.get("imported"):
                labels = ", ".join(
                    f"Trilha {int(item.get('trail', 0)):02d}" for item in imported["imported"]
                )
                imported["message"] = f"Explicação incorporada: {labels}."
            return _jsonable(imported)
        except Exception as error:
            return {"ok": False, "error": str(error)}

    # -------------------------- settings/export ----------------------------
    def save_settings(self, payload: dict) -> dict:
        protected = {"window_geometry"}
        for key, value in (payload or {}).items():
            if key in self.config and key not in protected and not key.startswith("network_"):
                self.config[key] = value
        self._persist_config()
        return {"ok": True, "config": self._public_config()}

    def get_ai_provider_settings(self) -> dict:
        from core.ai_providers import public_settings
        return {"ok": True, "settings": _jsonable(public_settings(self.config, self.config_path))}

    def save_ai_provider_settings(self, payload: dict) -> dict:
        from core.ai_providers import PROVIDER_META, public_settings, save_keys
        data = dict(payload or {})
        active = str(data.get("active_provider") or self.config.get("ai_active_provider") or "local")
        if active not in PROVIDER_META:
            return {"ok": False, "error": "Provedor de IA inválido."}
        self.config["ai_active_provider"] = active
        for pid in ("openai", "gemini", "anthropic"):
            model = str(data.get(f"{pid}_model") or "").strip()
            if model or f"{pid}_model" in data:
                self.config[f"ai_{pid}_model"] = model
            for side in ("input", "output"):
                key = f"{pid}_{side}_cost"
                if key in data:
                    try:
                        self.config[f"ai_cost_{pid}_{side}_per_million"] = max(0.0, float(data.get(key) or 0))
                    except Exception:
                        return {"ok": False, "error": f"Preço inválido para {pid}/{side}."}
        updates = {pid: str(data.get(f"{pid}_api_key") or "") for pid in ("openai","gemini","anthropic") if str(data.get(f"{pid}_api_key") or "")}
        clear = [pid for pid in ("openai","gemini","anthropic") if bool(data.get(f"clear_{pid}_key"))]
        try:
            if updates or clear:
                save_keys(self.config_path, updates, clear=clear)
        except Exception as error:
            return {"ok": False, "error": f"Não foi possível proteger a chave da API: {error}"}
        self._persist_config()
        return {"ok": True, "settings": _jsonable(public_settings(self.config, self.config_path))}

    def test_ai_provider(self, provider: str = "") -> dict:
        from core.ai_providers import generate, public_settings
        pid = str(provider or self.config.get("ai_active_provider") or "local")
        if pid == "local":
            return {"ok": True, "provider": "QuestFlow local", "detail": "RAG local disponível; nenhuma chave externa necessária."}
        if pid == "google_ai_mode":
            return {"ok": True, "provider": "Google Modo IA", "detail": "Integração por navegador disponível. O uso efetivo ocorre ao gerar uma orientação."}
        try:
            result = generate(pid, "Responda apenas: OK", config=self.config, config_path=self.config_path)
            return {"ok": bool(result.get("text")), "provider": result.get("provider"), "model": result.get("model"), "detail": str(result.get("text") or "")[:160], "settings": public_settings(self.config, self.config_path)}
        except Exception as error:
            return {"ok": False, "error": str(error), "settings": public_settings(self.config, self.config_path)}

    def get_ai_privacy_settings(self) -> dict:
        from core.ai_safety import privacy_settings
        return {"ok": True, "settings": _jsonable(privacy_settings(self.config))}

    def save_ai_privacy_settings(self, payload: dict) -> dict:
        from core.ai_safety import privacy_settings
        data = dict(payload or {})
        mode = str(data.get("mode") or self.config.get("ai_privacy_mode") or "balanced")
        if mode not in {"private", "balanced", "custom"}:
            return {"ok": False, "error": "Modo de privacidade inválido."}
        self.config["ai_privacy_mode"] = mode
        for key in (
            "share_taxonomy", "share_statement", "share_alternatives", "share_official_answer", "share_rag",
            "share_binary_media", "share_learner_summary", "share_user_prompt", "share_personal_notes", "confirm_before_external",
        ):
            if key in data:
                self.config[key] = bool(data.get(key))
        self._persist_config()
        return {"ok": True, "settings": _jsonable(privacy_settings(self.config))}

    def get_ai_privacy_preview(self, uid: str, mode: str = "professor", user_prompt: str = "") -> dict:
        self._ensure_core()
        return _jsonable(self.engines.ai.privacy_preview(str(uid), mode=str(mode or "professor"), user_prompt=str(user_prompt or "")))

    def get_ai_telemetry(self, days: int = 30) -> dict:
        self._ensure_core()
        return {"ok": True, "telemetry": _jsonable(self.engines.governance.provider_telemetry(days=max(1, min(365, int(days or 30)))))}

    # -------------------------- update monitor ---------------------------
    def _update_monitor(self):
        from core.update_monitor import UpdateMonitor
        return UpdateMonitor(
            config=self.config,
            state_path=self.database_path.parent / "update_monitor_state.json",
        )

    def get_update_monitor_status(self) -> dict:
        return _jsonable(self._update_monitor().status())

    def save_update_monitor_settings(self, payload: dict) -> dict:
        data = dict(payload or {})
        if "enabled" in data:
            self.config["update_monitor_enabled"] = bool(data.get("enabled"))
        raw_days = data.get("days")
        if isinstance(raw_days, (list, tuple)) and len(raw_days) >= 2:
            try:
                days = sorted({max(1, min(28, int(x))) for x in raw_days})
                if len(days) >= 2:
                    self.config["update_monitor_days"] = days[:2]
            except Exception:
                return {"ok": False, "error": "Dias inválidos. Use dois dias entre 1 e 28."}
        self._persist_config()
        return _jsonable(self._update_monitor().status())

    def defer_update_monitor(self, action: str = "snooze") -> dict:
        return _jsonable(self._update_monitor().defer(action))

    def start_update_monitor_check(self) -> dict:
        monitor = self._update_monitor()

        def worker(task_id: str) -> dict:
            def progress(value: float, message: str) -> None:
                self._update_task(task_id, progress=value, message=message)
            return _jsonable(monitor.run(progress=progress))

        return self._start_task("update-monitor", worker, coalesce=True)

    def get_network_settings(self) -> dict:
        from core.network import NetworkManager

        manager = NetworkManager(self.config, config_path=self.config_path)
        return {"ok": True, "settings": _jsonable(manager.settings())}

    def detect_network_proxy(self) -> dict:
        from core.network import NetworkManager, detect_system_proxy

        detected = detect_system_proxy()
        manager = NetworkManager(self.config, config_path=self.config_path)
        try:
            effective = manager.resolve("https://www.google.com/", refresh=True).public()
        except Exception as error:
            effective = {"enabled": False, "source": "error", "detail": str(error)}
        return {"ok": True, "detected": _jsonable(detected), "effective": _jsonable(effective)}

    def save_network_settings(self, payload: dict) -> dict:
        from core.network import (
            DEFAULT_BYPASS,
            NetworkManager,
            clear_proxy_credentials,
            credential_path_for_config,
            save_proxy_credentials,
        )

        payload = dict(payload or {})
        mode = str(payload.get("network_mode", self.config.get("network_mode", "auto")) or "auto").strip().lower()
        if mode not in {"auto", "system", "manual", "pac", "direct"}:
            return {"ok": False, "error": "Modo de proxy inválido."}
        auth = str(payload.get("network_proxy_auth", self.config.get("network_proxy_auth", "none")) or "none").strip().lower()
        if auth not in {"none", "basic", "windows"}:
            return {"ok": False, "error": "Modo de autenticação do proxy inválido."}
        host = str(payload.get("network_proxy_host", self.config.get("network_proxy_host", "")) or "").strip()
        port_text = str(payload.get("network_proxy_port", self.config.get("network_proxy_port", "")) or "").strip()
        if mode == "manual":
            if not host:
                return {"ok": False, "error": "Informe o servidor do proxy manual."}
            try:
                port = int(port_text)
            except (TypeError, ValueError):
                return {"ok": False, "error": "Informe uma porta de proxy válida."}
            if not 1 <= port <= 65535:
                return {"ok": False, "error": "A porta do proxy deve ficar entre 1 e 65535."}
            port_text = str(port)
        pac_url = str(payload.get("network_pac_url", self.config.get("network_pac_url", "")) or "").strip()
        if mode == "pac" and not pac_url:
            return {"ok": False, "error": "Informe a URL do arquivo PAC."}
        if pac_url and not pac_url.lower().startswith(("http://", "https://", "file://")):
            return {"ok": False, "error": "A URL do PAC deve começar por http://, https:// ou file://."}

        bypass = str(payload.get("network_proxy_bypass", self.config.get("network_proxy_bypass", DEFAULT_BYPASS)) or DEFAULT_BYPASS).strip()
        rules = [item.strip() for item in bypass.replace(",", ";").split(";") if item.strip()]
        for mandatory in ("localhost", "127.0.0.1", "::1"):
            if mandatory not in rules:
                rules.append(mandatory)
        bypass = ";".join(rules)
        username = str(payload.get("network_proxy_username", self.config.get("network_proxy_username", "")) or "").strip()

        self.config.update({
            "network_mode": mode,
            "network_proxy_host": host,
            "network_proxy_port": port_text,
            "network_pac_url": pac_url,
            "network_proxy_bypass": bypass,
            "network_proxy_auth": auth,
            "network_proxy_username": username,
        })
        credential_path = credential_path_for_config(self.config_path)
        if bool(payload.get("network_clear_password")):
            clear_proxy_credentials(credential_path)
        else:
            password = str(payload.get("network_proxy_password", "") or "")
            if password:
                try:
                    save_proxy_credentials(username, password, credential_path)
                except Exception as error:
                    return {"ok": False, "error": f"Não foi possível proteger a senha do proxy no Windows: {error}"}
        self._persist_config()
        manager = NetworkManager(self.config, config_path=self.config_path)
        return {"ok": True, "settings": _jsonable(manager.settings()), "config": self._public_config()}

    def test_network_connection(self) -> dict:
        from core.network import test_network

        try:
            return _jsonable(test_network(self.config, config_path=self.config_path, timeout=10))
        except Exception as error:
            return {"ok": False, "error": str(error), "tests": []}

    def get_database_health(self) -> dict:
        self._ensure_core()
        assert self.cloud_sync is not None
        try:
            return {"ok": True, "health": _jsonable(self.cloud_sync.health_snapshot())}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def get_cloud_sync_settings(self) -> dict:
        self._ensure_core()
        assert self.cloud_sync is not None
        return {"ok": True, "settings": _jsonable(self.cloud_sync.settings()), "status": _jsonable(self.cloud_sync.safe_status())}

    def save_cloud_sync_settings(self, payload: dict) -> dict:
        from core.cloud_sync import clear_turso_token, save_turso_token
        self._ensure_core()
        assert self.cloud_sync is not None
        payload = dict(payload or {})
        previous_url = str(self.config.get("cloud_turso_url", "") or "").strip()
        previous_token_configured = bool(self.cloud_sync.settings().get("cloud_turso_token_configured"))
        url = str(payload.get("cloud_turso_url", previous_url) or "").strip()
        requested_enabled = bool(payload.get("cloud_sync_enabled", self.config.get("cloud_sync_enabled", False)))
        interval = max(10, min(900, int(payload.get("cloud_sync_interval_seconds", self.config.get("cloud_sync_interval_seconds", 30)) or 30)))
        clear_token = bool(payload.get("cloud_clear_token"))
        token = str(payload.get("cloud_turso_token", "") or "").strip()
        token_changed = clear_token or bool(token)
        endpoint_changed = url != previous_url

        activation_required = bool(self.config.get("cloud_sync_safe_activation_required", True))
        activation_completed = self.cloud_sync.activation_completed()
        if activation_required and requested_enabled and not activation_completed:
            requested_enabled = False

        self.config.update({
            "cloud_sync_enabled": requested_enabled,
            "cloud_turso_url": url,
            "cloud_device_name": str(payload.get("cloud_device_name", self.config.get("cloud_device_name", "")) or "").strip(),
            "cloud_sync_interval_seconds": interval,
            "cloud_sync_on_start": bool(payload.get("cloud_sync_on_start", True)),
            "cloud_sync_on_shutdown": bool(payload.get("cloud_sync_on_shutdown", True)),
            "cloud_sync_safe_activation_required": activation_required,
            "cloud_sync_retry_base_seconds": max(2, min(120, int(payload.get("cloud_sync_retry_base_seconds", self.config.get("cloud_sync_retry_base_seconds", 5)) or 5))),
            "cloud_sync_retry_max_seconds": max(10, min(3600, int(payload.get("cloud_sync_retry_max_seconds", self.config.get("cloud_sync_retry_max_seconds", 300)) or 300))),
            "mobile_lan_enabled": bool(payload.get("mobile_lan_enabled", self.config.get("mobile_lan_enabled", False))),
        })
        if clear_token:
            clear_turso_token(self.config_path)
        if token:
            try:
                save_turso_token(self.config_path, token)
            except Exception as error:
                return {"ok": False, "error": f"Não foi possível proteger o token do Turso: {error}"}

        self.cloud_sync.config = self.config
        if activation_required and (endpoint_changed or token_changed) and (activation_completed or previous_token_configured):
            self.cloud_sync.invalidate_activation("URL ou credencial do Turso foi alterada; uma nova validação segura é necessária.")
            self.config["cloud_sync_enabled"] = False

        self._persist_config()
        try:
            from core.cloud_sync import CloudSyncService
            if self.cloud_sync.auto_sync_allowed():
                if self.cloud_sync_service is None:
                    self.cloud_sync_service = CloudSyncService(self.cloud_sync)
                    self.cloud_sync_service.start()
                else:
                    self.cloud_sync_service.wake()
            elif self.cloud_sync_service is not None:
                self.cloud_sync_service.stop(flush=False, timeout=2.0)
                self.cloud_sync_service = None
        except Exception as error:
            self._log_startup("cloud_sync_reconfigure_error", str(error))
        result = self.get_cloud_sync_settings()
        if activation_required and bool(payload.get("cloud_sync_enabled")) and not self.cloud_sync.activation_completed():
            result["activation_required"] = True
            result["message"] = "Configuração salva. Use Ativação segura antes da primeira escrita no Turso."
        return result

    def get_cloud_sync_activation_preview(self) -> dict:
        self._ensure_core()
        assert self.cloud_sync is not None
        preview = self.cloud_sync.activation_preview()
        return {"ok": bool(preview.get("ok")), "preview": _jsonable(preview)}

    def activate_cloud_sync_safely(self, source: str = "merge", confirm_remote_differences: bool = False) -> dict:
        self._ensure_core()
        assert self.cloud_sync is not None
        result = self.cloud_sync.activate_safely(
            source=str(source or "merge"),
            confirm_remote_differences=bool(confirm_remote_differences),
        )
        completed = bool(result.get("completed") or (result.get("activation") or {}).get("completed"))
        if result.get("ok") and completed:
            self.config["cloud_sync_enabled"] = True
            self.cloud_sync.config = self.config
            self._persist_config()
            try:
                from core.cloud_sync import CloudSyncService
                if self.cloud_sync_service is None:
                    self.cloud_sync_service = CloudSyncService(self.cloud_sync)
                    self.cloud_sync_service.start()
                else:
                    self.cloud_sync_service.wake()
            except Exception as error:
                self._log_startup("cloud_sync_activation_service_error", str(error))
        else:
            # Enquanto a ativação protegida estiver apenas avançando em blocos, o
            # sincronismo automático permanece desligado. O mesmo vale para falhas:
            # escritas remotas já confirmadas são seguras para retentativa.
            self.config["cloud_sync_enabled"] = False
            self.cloud_sync.config = self.config
            self._persist_config()
        return _jsonable(result)

    def test_cloud_sync_connection(self) -> dict:
        self._ensure_core()
        assert self.cloud_sync is not None
        try:
            result = self.cloud_sync.test_remote()
            return {"ok": True, "result": _jsonable(result), "status": _jsonable(self.cloud_sync.safe_status())}
        except Exception as error:
            return {"ok": False, "error": str(error), "status": _jsonable(self.cloud_sync.safe_status())}

    def prepare_cloud_sync(self, source: str = "merge") -> dict:
        """Legacy entry point kept for compatibility; delegates to safe activation."""
        return self.activate_cloud_sync_safely(source=source, confirm_remote_differences=False)

    def sync_cloud_now(self) -> dict:
        self._ensure_core()
        assert self.cloud_sync is not None
        if bool(self.config.get("cloud_sync_safe_activation_required", True)) and not self.cloud_sync.activation_completed():
            return {
                "ok": False, "activation_required": True,
                "error": "Conclua a ativação segura do Cloud Sync antes da primeira sincronização.",
                "status": _jsonable(self.cloud_sync.safe_status()),
            }
        result = self.cloud_sync.sync_until_idle(max_rounds=8, max_seconds=45.0)
        if self.study is not None:
            try:
                self.study.rebuild_subject_analytics_daily()
            except Exception:
                pass
        return _jsonable(result)

    def get_cloud_sync_status(self) -> dict:
        self._ensure_core()
        assert self.cloud_sync is not None
        try:
            return {"ok": True, "status": _jsonable(self.cloud_sync.safe_status())}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def get_cloud_sync_pending(self, limit: int = 60) -> dict:
        self._ensure_core()
        assert self.cloud_sync is not None
        try:
            return {"ok": True, "queue": _jsonable(self.cloud_sync.pending_details(limit=max(1, min(200, int(limit or 60)))))}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def export_data(self, kind: str, approved_only: bool = False) -> dict:
        self._ensure_core()
        assert self.queries is not None and self.commands is not None
        from core.exporter import export_csv, export_json, export_questflow_bank

        questions = self.queries.all(approved_only=bool(approved_only))
        kind = str(kind or "json").lower()
        if kind == "sqlite":
            path = self._dialog_save("QuestFlow-backup.sqlite", "SQLite (*.sqlite)")
            if not path:
                return {"ok": False, "cancelled": True}
            output = self.commands.backup(path)
        elif kind == "csv":
            path = self._dialog_save("QuestFlow-questoes.csv", "CSV (*.csv)")
            if not path:
                return {"ok": False, "cancelled": True}
            output = export_csv(questions, path)
        elif kind == "questflow":
            path = self._dialog_save("QuestFlow-base-de-questoes.json", "JSON (*.json)")
            if not path:
                return {"ok": False, "cancelled": True}
            output = export_questflow_bank(questions, path)
        else:
            path = self._dialog_save("QuestFlow-export.json", "JSON (*.json)")
            if not path:
                return {"ok": False, "cancelled": True}
            output = export_json(questions, path)
        return {"ok": True, "path": str(output), "count": len(questions)}

    def import_database(self) -> dict:
        paths = self._dialog_open(
            multiple=False,
            file_types=("Bancos QuestFlow (*.sqlite;*.db;*.json;*.qflow;*.qflowpkg)", "Todos os arquivos (*.*)"),
        )
        if not paths:
            return {"ok": False, "cancelled": True}
        try:
            self._ensure_core()
            assert self.commands is not None and self.study is not None
            result = self.commands.import_database(paths[0])
            self.study.sync_questions()
            return {"ok": True, "result": _jsonable(result)}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def launch_classic(self) -> dict:
        try:
            subprocess.Popen([sys.executable, str(BASE_DIR / "app_classic.py")], cwd=BASE_DIR)
            return {"ok": True}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    # -------------------------- dialogs ------------------------------------
    @staticmethod
    def _tk_file_types(file_types: tuple[str, ...]) -> list[tuple[str, str]]:
        converted: list[tuple[str, str]] = []
        for item in file_types:
            match = re.match(r"^(.*?)\s*\((.*?)\)\s*$", str(item))
            if match:
                label = match.group(1).strip() or "Arquivos"
                patterns = match.group(2).replace(";", " ").strip()
            else:
                label = str(item).strip() or "Arquivos"
                patterns = "*.*"
            converted.append((label, patterns))
        return converted or [("Todos os arquivos", "*.*")]

    def _tk_dialog_open(self, *, multiple: bool, file_types: tuple[str, ...]) -> list[str]:
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            try:
                root.attributes("-topmost", True)
                root.update_idletasks()
                options = {"title": "Selecionar arquivo", "filetypes": self._tk_file_types(file_types)}
                if multiple:
                    result = filedialog.askopenfilenames(parent=root, **options)
                    return [str(path) for path in result]
                result = filedialog.askopenfilename(parent=root, **options)
                return [str(result)] if result else []
            finally:
                root.destroy()
        except Exception:
            return []

    def _dialog_open(self, *, multiple: bool, file_types: tuple[str, ...]) -> list[str]:
        if self.window is not None:
            try:
                import webview

                result = self.window.create_file_dialog(
                    webview.OPEN_DIALOG,
                    allow_multiple=multiple,
                    file_types=file_types,
                )
                if result:
                    if isinstance(result, (str, Path)):
                        return [str(result)]
                    return [str(path) for path in result]
            except Exception:
                pass
        return self._tk_dialog_open(multiple=multiple, file_types=file_types)

    def _dialog_save(self, filename: str, file_type: str) -> str:
        if self.window is not None:
            try:
                import webview

                result = self.window.create_file_dialog(
                    webview.SAVE_DIALOG,
                    save_filename=filename,
                    file_types=(file_type, "Todos os arquivos (*.*)"),
                )
                if result:
                    if isinstance(result, (tuple, list)):
                        return str(result[0]) if result else ""
                    return str(result)
            except Exception:
                pass
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            try:
                root.attributes("-topmost", True)
                root.update_idletasks()
                result = filedialog.asksaveasfilename(
                    parent=root,
                    title="Salvar arquivo",
                    initialfile=filename,
                    filetypes=self._tk_file_types((file_type, "Todos os arquivos (*.*)")),
                )
                return str(result or "")
            finally:
                root.destroy()
        except Exception:
            return ""
