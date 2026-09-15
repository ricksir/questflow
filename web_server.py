from __future__ import annotations

"""Servidor local de alto desempenho para a interface do QuestFlow.

A interface responsiva não depende mais da injeção da ponte JavaScript do
pywebview. O navegador e o núcleo Python se comunicam por HTTP/JSON somente em
127.0.0.1, com token aleatório por sessão. Isso isola o motor visual do trabalho
pesado de banco, OCR e Telegram e impede que a janela do Windows pare de
responder enquanto o núcleo é preparado.
"""

import ipaddress
import json
import logging
import mimetypes
import secrets
import socket
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from app_shared import APP_VERSION
from urllib.parse import parse_qs, unquote, urlparse

LOGGER = logging.getLogger("questflow.local_server")

ALLOWED_API_METHODS = frozenset(
    {
        "poll_events",
        "bootstrap_shell",
        "start_bootstrap_load",
        "start_dashboard_load",
        "bootstrap",
        "get_dashboard",
        "list_materias",
        "list_questions",
        "get_bank_classification_options",
        "update_question_classification",
        "organize_bank_lesson_group",
        "get_question",
        "create_manual_question",
        "save_question",
        "delete_question",
        "annul_question",
        "attach_image",
        "remove_image",
        "choose_import_files",
        "start_import",
        "start_reread",
        "poll_task",
        "get_flow",
        "save_flow_settings",
        "test_telegram_connection",
        "flow_action",
        "list_corrections",
        "correction_action",
        "get_coverage",
        "get_course_catalog_settings",
        "preflight_course_catalog",
        "apply_course_catalog",
        "sync_study_coverage",
        "choose_trail_guide_files",
        "import_trail_guides",
        "save_settings",
        "test_ai_provider",
        "save_ai_provider_settings",
        "get_ai_provider_settings",
        "get_ai_privacy_settings",
        "save_ai_privacy_settings",
        "get_ai_privacy_preview",
        "get_ai_telemetry",
        "get_update_monitor_status",
        "save_update_monitor_settings",
        "defer_update_monitor",
        "start_update_monitor_check",
        "get_network_settings",
        "detect_network_proxy",
        "save_network_settings",
        "test_network_connection",
        "get_cloud_sync_settings",
        "save_cloud_sync_settings",
        "test_cloud_sync_connection",
        "get_cloud_sync_activation_preview",
        "activate_cloud_sync_safely",
        "prepare_cloud_sync",
        "sync_cloud_now",
        "get_cloud_sync_status",
        "get_cloud_sync_pending",
        "get_database_health",
        "get_runtime_watchdog_status",
        "run_runtime_watchdog_check",
        "restart_runtime_service",
        "save_runtime_watchdog_settings",
        "request_close",
        "get_mobile_access",
        "get_mobile_foundation_status",
        "get_learning_analytics_v2",
        "get_adaptive_session_observability",
        "explain_adaptive_question",
        "get_mobile_cloud_bridge_settings",
        "save_mobile_cloud_bridge_settings",
        "test_mobile_cloud_bridge",
        "sync_mobile_cloud_bridge_now",
        "get_mobile_cloud_bridge_status",
        "create_mobile_pairing",
        "disconnect_mobile_device",
        "forget_mobile_device",
        "revoke_mobile_device",
        "export_data",
        "import_database",
        "launch_classic",
        "get_today_dashboard",
        "get_exam_project_dashboard",
        "save_exam_project",
        "set_active_exam_project",
        "parse_edital_text",
        "add_edital_version",
        "relink_exam_project",
        "scan_question_currency",
        "set_question_currency",
        "get_bank_intelligence",
        "refresh_bank_intelligence",
        "get_curation_attention",
        "complete_curation_review",
        "get_question_intelligence",
        "resolve_duplicate_candidate",
        "get_ai_commentary_brief",
        "get_semantic_index_summary",
        "get_question_knowledge_graph",
        "get_rag_context",
        "start_semantic_rebuild",
        "start_ai_commentary_assist",
        "start_google_commentary_research",
        "get_learning_model",
        "get_counterfactual_learning_plan",
        "get_evidence_collection_plan",
        "start_evidence_collection",
        "get_scaffolding_benchmark",
        "start_learner_model_rebuild",
        "get_engine_architecture",
        "dispatch_studio_v1",
        "get_studio_contract_v1",
        "get_question_source_settings",
        "save_question_source_settings",
        "test_question_source",
        "rebuild_learning_projections",
        "get_tutor_workspace",
        "start_tutor_scaffolding",
        "advance_tutor_scaffolding",
        "get_tutor_scaffolding",
        "diagnose_question_error",
        "start_tutor_assist",
        "get_ai_audit",
        "get_ai_interaction",
        "save_ai_interaction_text",
        "review_ai_interaction",
        "get_recommendation_dashboard",
        "start_adaptive_simulation",
        "get_adaptive_simulation",
        "submit_adaptive_simulation_answer",
        "abandon_adaptive_simulation",
        "get_stage5_workspace",
        "create_legislation_version",
        "resolve_legislation_version",
        "generate_controlled_question",
        "get_generation_draft",
        "review_generation_draft",
        "publish_generation_draft",
        "run_multimodal_grounding_benchmark",
        "run_retrieval_calibration",
        "apply_retrieval_calibration",
        "rollback_retrieval_calibration",
        "save_retrieval_regression_baseline",
        "get_retrieval_regression_status",
        "get_retrieval_health_service",
        "get_retrieval_health_snapshot",
        "start_retrieval_evaluation",
        "get_retrieval_evaluation_job",
        "get_retrieval_observability",
        "record_retrieval_observability",
        "suggest_gold_question_expansion",
        "export_retrieval_observability_report",
        "get_retrieval_quality_gate",
        "reevaluate_retrieval_quality_gate",
        "promote_retrieval_release",
        "override_retrieval_quality_gate",
        "rollback_retrieval_release_gate",
        "export_retrieval_quality_gate_report",
        "add_gold_question",
        "run_gold_regression",
        "get_gold_dashboard",
    }
)


class QuestFlowThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR can bind a second listener to a port that is
    # already occupied. A local control plane must have exactly one owner;
    # the caller already falls back to an ephemeral port when binding fails.
    allow_reuse_address = False
    request_queue_size = 64


class QuestFlowLocalServer:
    def __init__(
        self,
        api: Any,
        web_root: str | Path,
        *,
        bind_host: str = "127.0.0.1",
        preferred_port: int = 53155,
    ) -> None:
        self.api = api
        self.web_root = Path(web_root).resolve()
        self.bind_host = str(bind_host or "127.0.0.1")
        self.preferred_port = max(0, min(65535, int(preferred_port or 0)))
        self.token = secrets.token_urlsafe(32)
        self._httpd: QuestFlowThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._stopped = threading.Event()
        self._last_heartbeat = time.monotonic()
        self._heartbeat_count = 0
        self._heartbeat_lock = threading.Lock()

    @property
    def port(self) -> int:
        if self._httpd is None:
            return 0
        return int(self._httpd.server_address[1])

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/index.html?qf_token={self.token}"

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def mobile_urls(self) -> list[str]:
        if self.bind_host == "127.0.0.1":
            return []
        return [f"{base}/index.html?qf_token={self.token}" for base in self.mobile_api_urls()]

    @staticmethod
    def _usable_lan_ipv4(value: str) -> bool:
        try:
            address = ipaddress.ip_address(str(value or ""))
        except ValueError:
            return False
        return bool(
            address.version == 4
            and not address.is_loopback
            and not address.is_link_local
            and not address.is_multicast
            and not address.is_unspecified
            and address.is_private
        )

    @staticmethod
    def _default_route_ipv4() -> str:
        """Return the IPv4 selected by the OS default route without sending data.

        UDP connect() only asks the routing table which local interface would be
        used. This makes the result follow Wi-Fi/Ethernet changes even when the
        network itself has no Internet access.
        """
        for host in ("1.1.1.1", "8.8.8.8", "192.0.2.1"):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.connect((host, 80))
                candidate = str(sock.getsockname()[0] or "")
                if QuestFlowLocalServer._usable_lan_ipv4(candidate):
                    return candidate
            except OSError:
                pass
            finally:
                sock.close()
        return ""

    def mobile_network_info(self) -> dict[str, Any]:
        """Detect current LAN addresses and rank the active route first.

        No address is cached: every call reflects the network currently selected
        by Windows. Virtual/secondary adapters are retained only as fallbacks.
        """
        if self.bind_host == "127.0.0.1":
            return {"preferred_ip": "", "addresses": [], "api_urls": [], "detected_at": time.time()}

        addresses: set[str] = set()
        preferred = self._default_route_ipv4()
        if preferred:
            addresses.add(preferred)
        try:
            for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                candidate = str(item[4][0] or "")
                if self._usable_lan_ipv4(candidate):
                    addresses.add(candidate)
        except OSError:
            pass

        ordered = sorted(addresses, key=lambda item: (0 if item == preferred else 1, ipaddress.ip_address(item)))
        return {
            "preferred_ip": preferred or (ordered[0] if ordered else ""),
            "addresses": ordered,
            "api_urls": [f"http://{address}:{self.port}" for address in ordered],
            "detected_at": time.time(),
        }

    def mobile_api_urls(self) -> list[str]:
        """Return fresh LAN API URLs, active/default-route address first."""
        return list(self.mobile_network_info().get("api_urls") or [])

    @property
    def last_heartbeat_age(self) -> float:
        with self._heartbeat_lock:
            return max(0.0, time.monotonic() - self._last_heartbeat)

    @property
    def heartbeat_count(self) -> int:
        with self._heartbeat_lock:
            return self._heartbeat_count

    def touch_heartbeat(self) -> None:
        with self._heartbeat_lock:
            self._last_heartbeat = time.monotonic()
            self._heartbeat_count += 1

    def runtime_health(self) -> dict[str, Any]:
        thread_alive = bool(self._thread and self._thread.is_alive())
        age = self.last_heartbeat_age
        count = self.heartbeat_count
        if not thread_alive:
            return {"ok": False, "state": "failed", "thread_alive": False, "heartbeat_age_seconds": round(age, 2), "heartbeat_count": count}
        # Before the first browser heartbeat the HTTP service itself may already
        # be healthy; after the UI connected, a long silence is surfaced as a
        # diagnostic signal but is not auto-restarted by the supervisor.
        if count > 0 and age > 25.0:
            return {"ok": False, "state": "degraded", "thread_alive": True, "heartbeat_age_seconds": round(age, 2), "heartbeat_count": count, "error": "Interface sem heartbeat recente."}
        return {"ok": True, "state": "healthy", "thread_alive": True, "heartbeat_age_seconds": round(age, 2), "heartbeat_count": count, "port": self.port}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = f"QuestFlowLocal/{APP_VERSION}"
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt: str, *args: Any) -> None:
                LOGGER.debug("%s - %s", self.address_string(), fmt % args)

            def parse_request(self) -> bool:
                """Tolerate harmless method prefixes injected by security filters.

                Some antivirus/browser protection modules have been observed to
                rewrite a loopback request line from ``GET`` to ``{{GET``. The
                standard library then returns an HTML 501 page before our API
                handler runs. Normalize only a small, explicit set of methods
                and only when the extra prefix is punctuation; all other input
                keeps the standard parser behavior.
                """
                parsed = super().parse_request()
                if not parsed:
                    return False
                command = str(getattr(self, "command", ""))
                normalized = command.lstrip("{}[]()<>\"'")
                if normalized in {"GET", "POST", "DELETE", "HEAD", "OPTIONS"} and normalized != command:
                    LOGGER.warning("Método HTTP normalizado no loopback: %r -> %s", command, normalized)
                    self.command = normalized
                return True

            def send_error(
                self,
                code: int,
                message: str | None = None,
                explain: str | None = None,
            ) -> None:
                # API callers must always receive JSON, never the generic HTML
                # error page generated by BaseHTTPRequestHandler.
                if str(getattr(self, "path", "")).startswith("/api/"):
                    try:
                        default_message = HTTPStatus(code).phrase
                    except ValueError:
                        default_message = "Falha HTTP."
                    self._send_json(
                        code,
                        {"ok": False, "error": message or default_message},
                    )
                    return
                super().send_error(code, message, explain)

            def _send_bytes(
                self,
                status: int,
                payload: bytes,
                content_type: str,
                *,
                cache_control: str = "no-store",
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", cache_control)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; img-src 'self' data: blob: https:; style-src 'self' 'unsafe-inline'; "
                    "script-src 'self'; connect-src 'self'; font-src 'self' data:; object-src 'none'; "
                    "base-uri 'none'; frame-ancestors 'none'",
                )
                self.end_headers()
                self.wfile.write(payload)

            def _send_json(self, status: int, value: Any) -> None:
                payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self._send_bytes(status, payload, "application/json; charset=utf-8")

            def _authorized(self) -> bool:
                supplied = self.headers.get("X-QuestFlow-Token", "")
                return secrets.compare_digest(supplied, owner.token)

            def _static_path(self, request_path: str) -> Path | None:
                clean = unquote(request_path).split("?", 1)[0].lstrip("/") or "index.html"
                candidate = (owner.web_root / clean).resolve()
                try:
                    candidate.relative_to(owner.web_root)
                except ValueError:
                    return None
                return candidate

            def _send_health(self) -> None:
                if not self._authorized():
                    self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Sessão inválida."})
                    return
                owner.touch_heartbeat()
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "transport": "http-json",
                        "api": "questflow.local.v1",
                        "server_time": time.time(),
                    },
                )

            def _studio_v1_result(self, operation: str, payload: dict[str, Any] | None = None) -> None:
                if not self._authorized():
                    self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Sessão inválida."})
                    return
                owner.touch_heartbeat()
                result = owner.api.dispatch_studio_v1(operation, payload or {})
                status = int(result.get("status") or (HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST))
                self._send_json(status, result)

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path.startswith("/api/v1/mobile/"):
                    status, payload = owner.api.mobile_http_request(
                        "GET", parsed.path, self.headers, {}, parse_qs(parsed.query, keep_blank_values=True)
                    )
                    self._send_json(status, payload)
                    return
                if parsed.path.startswith("/api/v1/studio/"):
                    if parsed.path == "/api/v1/studio/contract":
                        if not self._authorized():
                            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Sessão inválida."})
                            return
                        self._send_json(HTTPStatus.OK, owner.api.get_studio_contract_v1())
                        return
                    if parsed.path == "/api/v1/studio/architecture":
                        self._studio_v1_result("system.architecture")
                        return
                    if parsed.path == "/api/v1/studio/projections":
                        self._studio_v1_result("system.projections.status")
                        return
                    if parsed.path == "/api/v1/studio/question-source":
                        self._studio_v1_result("questions.source.settings")
                        return
                    if parsed.path == "/api/v1/studio/taxonomy/subjects":
                        self._studio_v1_result("taxonomy.subjects.list")
                        return
                    if parsed.path == "/api/v1/studio/taxonomy/classification-options":
                        query = parse_qs(parsed.query, keep_blank_values=True)
                        self._studio_v1_result("taxonomy.classification.options", {
                            "subject": (query.get("subject") or [""])[0],
                            "lesson": (query.get("lesson") or [""])[0],
                        })
                        return
                    if parsed.path == "/api/v1/studio/questions":
                        query = parse_qs(parsed.query, keep_blank_values=True)
                        payload = {
                            "search": (query.get("search") or [""])[0],
                            "status": (query.get("status") or ["todos"])[0],
                            "subject": (query.get("subject") or [""])[0],
                            "lesson": (query.get("lesson") or [""])[0],
                            "offset": (query.get("offset") or [0])[0],
                            "limit": (query.get("limit") or [100])[0],
                        }
                        self._studio_v1_result("questions.list", payload)
                        return
                    prefix = "/api/v1/studio/questions/"
                    if parsed.path.startswith(prefix):
                        self._studio_v1_result("questions.get", {"uid": unquote(parsed.path[len(prefix):])})
                        return
                    self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Rota Studio v1 não encontrada."})
                    return
                if parsed.path == "/api/health":
                    self._send_health()
                    return

                path = self._static_path(parsed.path)
                if path is None or not path.is_file():
                    self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Arquivo não encontrado."})
                    return
                try:
                    payload = path.read_bytes()
                except OSError as error:
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(error)})
                    return
                mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                if mime.startswith("text/") or mime in {"application/javascript", "application/json"}:
                    mime += "; charset=utf-8"
                # The server uses a random loopback port each launch. Browser
                # disk-cache entries from a previous port cannot be reused and
                # only accumulate stale JS/CSS/profile data. Serving local files
                # with no-store is faster and prevents UI/core version mismatch.
                self._send_bytes(HTTPStatus.OK, payload, mime, cache_control="no-store")

            def _read_post_body(self) -> bytes:
                if self.headers.get("Transfer-Encoding"):
                    self.close_connection = True
                    raise ValueError("Transfer-Encoding não é aceito pela API local.")
                try:
                    length = int(self.headers.get("Content-Length", "0") or 0)
                except ValueError as error:
                    self.close_connection = True
                    raise ValueError("Content-Length inválido.") from error
                if length < 0 or length > 16 * 1024 * 1024:
                    self.close_connection = True
                    raise ValueError("Requisição inválida ou muito grande.")
                return self.rfile.read(length) if length else b""

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                # Always consume the request body before returning. Versions
                # anteriores respondiam ao heartbeat sem ler ``{}``; em uma
                # conexão HTTP/1.1 persistente, esses bytes sobravam e viravam
                # o prefixo da próxima linha, produzindo ``{{GET`` e erro 501.
                try:
                    body = self._read_post_body()
                except ValueError as error:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(error)})
                    return

                if parsed.path.startswith("/api/v1/mobile/"):
                    try:
                        request_body = json.loads(body.decode("utf-8")) if body else {}
                        if not isinstance(request_body, dict):
                            raise ValueError("Corpo JSON inválido.")
                    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
                        self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(error)})
                        return
                    status, payload = owner.api.mobile_http_request(
                        "POST", parsed.path, self.headers, request_body, parse_qs(parsed.query, keep_blank_values=True)
                    )
                    self._send_json(status, payload)
                    return

                if parsed.path.startswith("/api/v1/studio/"):
                    if not body:
                        request_body: dict[str, Any] = {}
                    else:
                        try:
                            request_body = json.loads(body.decode("utf-8"))
                            if not isinstance(request_body, dict):
                                raise ValueError("Corpo JSON inválido.")
                        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
                            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(error)})
                            return
                    if parsed.path == "/api/v1/studio/questions":
                        self._studio_v1_result("questions.create", request_body)
                        return
                    question_prefix = "/api/v1/studio/questions/"
                    if parsed.path.startswith(question_prefix):
                        question_suffix = parsed.path[len(question_prefix):]
                        if question_suffix.endswith("/delete"):
                            request_body["uid"] = unquote(question_suffix[:-len("/delete")])
                            self._studio_v1_result("questions.delete", request_body)
                            return
                        if question_suffix.endswith("/annul"):
                            request_body["uid"] = unquote(question_suffix[:-len("/annul")])
                            self._studio_v1_result("questions.annul", request_body)
                            return
                        if question_suffix.endswith("/image/remove"):
                            request_body["uid"] = unquote(question_suffix[:-len("/image/remove")])
                            self._studio_v1_result("questions.image.remove", request_body)
                            return
                        if question_suffix.endswith("/classification"):
                            request_body["uid"] = unquote(question_suffix[:-len("/classification")])
                            self._studio_v1_result("questions.classification.update", request_body)
                            return
                        request_body["uid"] = unquote(question_suffix)
                        self._studio_v1_result("questions.update", request_body)
                        return
                    if parsed.path == "/api/v1/studio/taxonomy/lesson-group/organize":
                        self._studio_v1_result("taxonomy.lesson_group.organize", request_body)
                        return
                    if parsed.path == "/api/v1/studio/question-source":
                        self._studio_v1_result("questions.source.save", request_body)
                        return
                    if parsed.path == "/api/v1/studio/question-source/test":
                        self._studio_v1_result("questions.source.test", request_body)
                        return
                    if parsed.path == "/api/v1/studio/projections/rebuild":
                        self._studio_v1_result("system.projections.rebuild", request_body)
                        return
                    prefix = "/api/v1/studio/use-cases/"
                    if parsed.path.startswith(prefix):
                        operation = unquote(parsed.path[len(prefix):]).replace("/", ".")
                        self._studio_v1_result(operation, request_body)
                        return
                    self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Rota Studio v1 não encontrada."})
                    return

                if not self._authorized():
                    self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Sessão inválida."})
                    return
                owner.touch_heartbeat()

                if parsed.path == "/api/health":
                    self._send_health()
                    return
                if parsed.path == "/api/heartbeat":
                    self._send_json(HTTPStatus.OK, {"ok": True})
                    return
                if parsed.path != "/api/call":
                    self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Rota não encontrada."})
                    return
                if not body:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Requisição inválida."})
                    return

                try:
                    request = json.loads(body.decode("utf-8"))
                    method_name = str(request.get("method", ""))
                    args = request.get("args", [])
                    if method_name not in ALLOWED_API_METHODS:
                        raise ValueError("Método não permitido.")
                    if not isinstance(args, list):
                        raise ValueError("Argumentos inválidos.")
                    method = getattr(owner.api, method_name, None)
                    if not callable(method):
                        raise AttributeError(f"Recurso interno indisponível: {method_name}")
                    result = method(*args)
                    self._send_json(HTTPStatus.OK, {"ok": True, "result": result})
                except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError, AttributeError) as error:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(error)})
                except Exception as error:  # pragma: no cover - erro é registrado e devolvido à UI
                    LOGGER.exception("Falha no método da API local")
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(error)})

            def do_DELETE(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if not parsed.path.startswith("/api/v1/mobile/"):
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "Método não permitido."})
                    return
                status, payload = owner.api.mobile_http_request(
                    "DELETE", parsed.path, self.headers, {}, parse_qs(parsed.query, keep_blank_values=True)
                )
                self._send_json(status, payload)

            def do_HEAD(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path.startswith("/api/"):
                    self.send_error(HTTPStatus.METHOD_NOT_ALLOWED, "Método não permitido.")
                    return
                path = self._static_path(parsed.path)
                if path is None or not path.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND, "Arquivo não encontrado.")
                    return
                mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                if mime.startswith("text/") or mime in {"application/javascript", "application/json"}:
                    mime += "; charset=utf-8"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(path.stat().st_size))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()

            def do_OPTIONS(self) -> None:  # noqa: N802
                self.send_response(HTTPStatus.NO_CONTENT)
                self.send_header("Allow", "GET, POST, DELETE, HEAD, OPTIONS")
                self.send_header("Content-Length", "0")
                self.end_headers()

        try:
            self._httpd = QuestFlowThreadingHTTPServer((self.bind_host, self.preferred_port), Handler)
        except OSError:
            # A stable port keeps Chrome localStorage/preferences on one origin.
            # If another process already owns it, transparently fall back to an
            # ephemeral port instead of preventing QuestFlow from opening.
            self._httpd = QuestFlowThreadingHTTPServer((self.bind_host, 0), Handler)

        def serve() -> None:
            self._started.set()
            try:
                assert self._httpd is not None
                self._httpd.serve_forever(poll_interval=0.2)
            finally:
                self._stopped.set()

        self._thread = threading.Thread(target=serve, daemon=True, name="questflow-local-http")
        self._thread.start()
        if not self._started.wait(timeout=5.0):
            raise RuntimeError("O servidor local do QuestFlow não iniciou.")

    def stop(self) -> None:
        httpd = self._httpd
        self._httpd = None
        if httpd is not None:
            try:
                httpd.shutdown()
            finally:
                httpd.server_close()
        thread = self._thread
        self._thread = None
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=3.0)


__all__ = ["ALLOWED_API_METHODS", "QuestFlowLocalServer"]
