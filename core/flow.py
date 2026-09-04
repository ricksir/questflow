from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from .storage import QuestFlowDatabase
from .study import SelectionFilters, StudyRepository
from .telegram import (
    answer_callback_query,
    get_updates,
    TelegramError,
    classify_exception,
    send_message,
    send_quiz_with_retry,
    send_study_menu,
    send_answer_feedback,
    send_explanation_card,
)

EventCallback = Callable[[str, dict], None]
ConfigProvider = Callable[[], dict]


class CyclicStudyEngine:
    """Agenda o ciclo diário, envia quizzes e captura respostas/comandos do Telegram."""

    def __init__(
        self,
        database: QuestFlowDatabase,
        study: StudyRepository,
        config_provider: ConfigProvider,
        callback: EventCallback | None = None,
    ) -> None:
        self.database = database
        self.study = study
        self.config_provider = config_provider
        self.callback = callback or (lambda _event, _payload: None)
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._send_lock = threading.Lock()
        self._scheduler_thread: threading.Thread | None = None
        self._listener_thread: threading.Thread | None = None
        self._next_run: datetime | None = None
        saved_offset = self.study.get_runtime("telegram_update_offset", "")
        try:
            self._update_offset: int | None = int(saved_offset) if saved_offset else None
        except (TypeError, ValueError):
            self._update_offset = None
        self._last_retry_sweep: datetime | None = None
        self._last_unanswered_sweep: datetime | None = None
        self._last_outbox_sweep: datetime | None = None
        self._last_callback_sweep: datetime | None = None
        self._session_started_at: datetime = datetime.now()
        self._unanswered_sent_this_session = 0
        self._failed_retry_sent_this_session = 0
        self._last_relearning_sweep: datetime | None = None
        self._last_optimizer_sweep: datetime | None = None
        self._optimizer_thread: threading.Thread | None = None
        self._scheduler_heartbeat = 0.0
        self._listener_heartbeat = 0.0
        self._scheduler_restarts = 0
        self._listener_restarts = 0
        self._relearning_sent_today = 0
        self._relearning_day = datetime.now().date()

    @property
    def running(self) -> bool:
        return bool(self._scheduler_thread and self._scheduler_thread.is_alive())

    @property
    def listening(self) -> bool:
        return bool(self._listener_thread and self._listener_thread.is_alive())

    def runtime_health(self) -> dict:
        now = time.monotonic()
        scheduler_age = max(0.0, now - self._scheduler_heartbeat) if self._scheduler_heartbeat else None
        listener_age = max(0.0, now - self._listener_heartbeat) if self._listener_heartbeat else None
        configured = self.config_provider()
        token_ready = bool(str(configured.get("telegram_bot_token", "")).strip() and str(configured.get("telegram_chat_id", "")).strip())
        scheduler_ok = self.running and (scheduler_age is None or scheduler_age < 8.0)
        listener_ok = (not token_ready) or (self.listening and (listener_age is None or listener_age < 45.0))
        return {
            "ok": bool(scheduler_ok and listener_ok),
            "state": "healthy" if scheduler_ok and listener_ok else "degraded",
            "scheduler": {"alive": self.running, "heartbeat_age_seconds": round(scheduler_age, 2) if scheduler_age is not None else None, "restarts": self._scheduler_restarts},
            "listener": {"enabled": token_ready, "alive": self.listening, "heartbeat_age_seconds": round(listener_age, 2) if listener_age is not None else None, "restarts": self._listener_restarts},
            "paused": self.paused,
            "sending": self.sending,
        }

    def recover_runtime(self) -> dict:
        config = self.config_provider()
        token_ready = bool(str(config.get("telegram_bot_token", "")).strip() and str(config.get("telegram_chat_id", "")).strip())
        recovered: list[str] = []
        if not self.running:
            self._scheduler_restarts += 1
            self.start(start_listener=False)
            recovered.append("scheduler")
        if token_ready and not self.listening:
            self._listener_restarts += 1
            self.start_listener()
            recovered.append("listener")
        return {"ok": True, "recovered": recovered, "health": self.runtime_health()}

    @property
    def paused(self) -> bool:
        return self._pause.is_set()

    @property
    def sending(self) -> bool:
        """Indica se há um ciclo enviando questões neste instante."""
        return self._send_lock.locked()

    @property
    def next_run(self) -> datetime | None:
        return self._next_run

    def _emit(self, event: str, **payload) -> None:
        try:
            self.callback(event, payload)
        except Exception:
            pass

    @staticmethod
    def _weekdays(config: dict) -> set[int]:
        try:
            result = {int(item) for item in config.get("flow_weekdays", range(7))}
            return {item for item in result if 0 <= item <= 6} or set(range(7))
        except Exception:
            return set(range(7))

    @staticmethod
    def _daily_hour_minute(config: dict) -> tuple[int, int]:
        value = str(config.get("flow_daily_time", "19:00") or "19:00").strip()
        try:
            hour_text, minute_text = value.split(":", 1)
            hour, minute = int(hour_text), int(minute_text)
            if not 0 <= hour <= 23 or not 0 <= minute <= 59:
                raise ValueError
            return hour, minute
        except (ValueError, TypeError):
            return 19, 0

    def _scheduled_for_date(self, config: dict, day: datetime) -> datetime:
        hour, minute = self._daily_hour_minute(config)
        return day.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def _latest_due_occurrence(self, config: dict, now: datetime) -> datetime | None:
        weekdays = self._weekdays(config)
        activation_text = self.study.get_runtime("schedule_activated_at")
        try:
            activation = datetime.fromisoformat(activation_text) if activation_text else now
        except ValueError:
            activation = now
        activation_date = activation.date()
        for offset in range(0, 8):
            day = now - timedelta(days=offset)
            if day.date() < activation_date:
                break
            if day.weekday() not in weekdays:
                continue
            scheduled = self._scheduled_for_date(config, day)
            if scheduled <= now:
                return scheduled
        return None

    def _next_occurrence(self, config: dict, now: datetime) -> datetime:
        weekdays = self._weekdays(config)
        for offset in range(0, 15):
            day = now + timedelta(days=offset)
            if day.weekday() not in weekdays:
                continue
            scheduled = self._scheduled_for_date(config, day)
            if scheduled > now and not self.study.daily_cycle_done(scheduled.date().isoformat()):
                return scheduled
        return self._scheduled_for_date(config, now + timedelta(days=1))

    def _schedule_signature(self, config: dict) -> str:
        days = ",".join(str(item) for item in sorted(self._weekdays(config)))
        hour, minute = self._daily_hour_minute(config)
        return f"{hour:02d}:{minute:02d}|{days}"

    def _ensure_schedule_activation(self, config: dict, now: datetime) -> None:
        signature = self._schedule_signature(config)
        if self.study.get_runtime("schedule_signature") != signature:
            self.study.set_runtime("schedule_signature", signature)
            self.study.set_runtime("schedule_activated_at", now.isoformat(timespec="seconds"))
            self.study.set_runtime("last_pre_reminder_date", "")
            self.study.set_runtime("last_missed_notice_date", "")
            self.study.set_runtime("last_skipped_date", "")

    def start(self, start_listener: bool = True) -> None:
        if not self.running:
            self._stop.clear()
            self._pause.clear()
            config = self.config_provider()
            now = datetime.now()
            self._session_started_at = now
            self._unanswered_sent_this_session = 0
            self._failed_retry_sent_this_session = 0
            self._ensure_schedule_activation(config, now)
            self._next_run = self._next_occurrence(config, now)
            self._scheduler_thread = threading.Thread(
                target=self._scheduler_loop,
                daemon=True,
                name="questflow-daily-scheduler",
            )
            self._scheduler_thread.start()
            self._emit("engine_started", next_run=self._next_run.isoformat(timespec="minutes"))
        if start_listener:
            self.start_listener()

    def start_listener(self) -> None:
        if self.listening:
            return
        self._stop.clear()
        self._listener_thread = threading.Thread(
            target=self._listener_loop,
            daemon=True,
            name="questflow-telegram-listener",
        )
        self._listener_thread.start()
        self._emit("listener_started")

    def pause(self) -> None:
        self._pause.set()
        self._emit("engine_paused")

    def resume(self) -> None:
        self._pause.clear()
        self._next_run = self._next_occurrence(self.config_provider(), datetime.now())
        self._emit("engine_resumed", next_run=self._next_run.isoformat(timespec="minutes"))

    def stop(self) -> None:
        self._stop.set()
        self._emit("engine_stopped")

    @staticmethod
    def _retry_time(minutes: int) -> str:
        value = datetime.now(timezone.utc) + timedelta(minutes=max(1, int(minutes)))
        return value.replace(microsecond=0).isoformat()

    def retry_delivery_now(self, delivery_id: str, *, requested_via: str = "programa") -> None:
        threading.Thread(
            target=lambda: self._retry_delivery(delivery_id, requested_via=requested_via),
            daemon=True,
            name=f"questflow-retry-{delivery_id[:8]}",
        ).start()

    def retry_all_failed(self, *, requested_via: str = "programa") -> None:
        def worker() -> None:
            rows = self.study.failed_deliveries(200, due_only=False)
            self._emit("retry_batch_started", count=len(rows))
            for index, row in enumerate(rows, start=1):
                if self._stop.is_set():
                    break
                self._retry_delivery(str(row["id"]), requested_via=requested_via, index=index, total=len(rows))
            self._emit("retry_batch_finished", count=len(rows))

        threading.Thread(target=worker, daemon=True, name="questflow-retry-all").start()

    def _retry_delivery(
        self,
        delivery_id: str,
        *,
        requested_via: str,
        index: int | None = None,
        total: int | None = None,
    ) -> dict:
        if not self._send_lock.acquire(blocking=False):
            self._emit("retry_skipped", delivery_id=delivery_id, reason="Existe outro envio em andamento.")
            return {"sent": False, "busy": True}
        try:
            row = self.study.get_delivery(delivery_id)
            if not row:
                self._emit("retry_failed", delivery_id=delivery_id, error="Registro de envio não encontrado.")
                return {"sent": False}
            if row.get("resolved_by_delivery_id") or row.get("status") in {"enviado", "reenviado"}:
                return {"sent": True, "already_resolved": True}
            config = self.config_provider()
            token = str(config.get("telegram_bot_token", "")).strip()
            chat_id = str(row.get("chat_id") or config.get("telegram_chat_id", "")).strip()
            if not token or not chat_id:
                raise ValueError("Token do bot ou Chat ID não configurado.")
            question = row["question"]
            attempt_count = self.study.mark_retry_started(delivery_id)
            max_attempts = max(1, min(8, int(config.get("flow_question_retry_attempts", 3) or 3)))

            def progress(attempt: int, error: TelegramError, delay: float) -> None:
                self._emit(
                    "retry_wait",
                    delivery_id=delivery_id,
                    code=question.get("codigo_origem", ""),
                    attempt=attempt,
                    delay=round(delay, 1),
                    error=str(error),
                    index=index,
                    total=total,
                )

            try:
                result = send_quiz_with_retry(
                    token,
                    chat_id,
                    question,
                    timeout=35,
                    attempts=max_attempts,
                    progress=progress,
                    show_question_card=bool(config.get("flow_question_card_enabled", True)),
                    native_explanation=bool(config.get("flow_native_quiz_explanation", False)),
                )
                delivery = self.study.record_delivery(
                    str(row["question_uid"]),
                    chat_id,
                    result,
                    str(row.get("cycle_id") or f"retry-{uuid.uuid4()}"),
                    parent_delivery_id=delivery_id,
                    attempt_count=attempt_count,
                )
                self._emit(
                    "retry_sent",
                    delivery_id=delivery_id,
                    new_delivery_id=delivery.get("delivery_id"),
                    code=question.get("codigo_origem", ""),
                    requested_via=requested_via,
                    index=index,
                    total=total,
                )
                return {"sent": True, "delivery": delivery}
            except Exception as error:
                parsed = classify_exception(error)
                retry_minutes = max(1, min(1440, int(config.get("flow_retry_minutes", 10) or 10)))
                next_retry = self._retry_time(retry_minutes) if parsed.retryable else None
                self.study.restore_retry_error(
                    delivery_id,
                    str(parsed),
                    category=parsed.category,
                    retryable=parsed.retryable,
                    next_retry_at=next_retry,
                )
                self._emit(
                    "retry_failed",
                    delivery_id=delivery_id,
                    code=question.get("codigo_origem", ""),
                    error=str(parsed),
                    category=parsed.category,
                    retryable=parsed.retryable,
                    next_retry_at=next_retry,
                    index=index,
                    total=total,
                )
                return {"sent": False, "error": str(parsed)}
        finally:
            self._send_lock.release()

    def _retry_due_deliveries(self, config: dict, now: datetime) -> None:
        if self._last_retry_sweep and now < self._last_retry_sweep + timedelta(seconds=60):
            return
        self._last_retry_sweep = now
        if not bool(config.get("flow_auto_retry_failed", True)):
            return
        try:
            startup_grace = max(0, min(120, int(config.get("flow_background_startup_grace_minutes", 5))))
            session_cap = max(0, min(20, int(config.get("flow_failed_retry_session_cap", 5) or 5)))
            batch_limit = max(1, min(3, int(config.get("flow_failed_retry_batch_limit", 1) or 1)))
        except (TypeError, ValueError):
            startup_grace, session_cap, batch_limit = 5, 5, 1
        if now < self._session_started_at + timedelta(minutes=startup_grace):
            return
        remaining = session_cap - self._failed_retry_sent_this_session
        if remaining <= 0:
            return
        for row in self.study.failed_deliveries(min(batch_limit, remaining), due_only=True):
            if self._stop.is_set() or self._pause.is_set():
                break
            result = self._retry_delivery(str(row["id"]), requested_via="reenvio_automatico")
            if result.get("sent") and not result.get("already_resolved"):
                self._failed_retry_sent_this_session += 1

    def _retry_pending_outbox(self, config: dict, now: datetime) -> None:
        if self._last_outbox_sweep and now < self._last_outbox_sweep + timedelta(seconds=30):
            return
        self._last_outbox_sweep = now
        token = str(config.get("telegram_bot_token", "")).strip()
        if not token:
            return
        retry_minutes = max(1, min(1440, int(config.get("flow_retry_minutes", 10) or 10)))
        for item in self.study.pending_outbox_messages(20, due_only=True):
            try:
                send_message(token, str(item.get("chat_id", "")), str(item.get("text", "")))
                self.study.mark_outbox_sent(str(item["id"]))
                self._emit("outbox_sent", kind=item.get("kind", "mensagem"))
            except Exception as error:
                self.study.mark_outbox_error(str(item["id"]), str(error), retry_minutes=retry_minutes)
                self._emit("outbox_error", error=str(error), kind=item.get("kind", "mensagem"))

    def _process_review_callback(self, callback: dict, config: dict) -> dict:
        token = str(config.get("telegram_bot_token", "")).strip()
        callback_id = str(callback.get("id", "") or "")
        message = callback.get("message") or {}
        chat_id = str((message.get("chat") or {}).get("id", config.get("telegram_chat_id", "")))
        data = str(callback.get("data", "") or "")
        if not data.startswith("qf:review:"):
            return {}
        question_uid = data.split(":", 2)[2].strip()
        user = callback.get("from") or {}
        username = str(user.get("username") or " ".join(
            part for part in [str(user.get("first_name", "")).strip(), str(user.get("last_name", "")).strip()] if part
        )).strip()
        request = self.study.create_review_request(
            question_uid,
            chat_id=chat_id,
            user_id=str(user.get("id", "")),
            username=username,
            message_id=message.get("message_id") if isinstance(message.get("message_id"), int) else None,
        )
        if token and callback_id:
            try:
                answer_callback_query(token, callback_id, "Questão guardada para correção no QuestFlow.")
            except Exception:
                pass
        code = str(request.get("source_code", "") or "questão")
        outbox_id = self.study.enqueue_outbox_message(
            chat_id,
            (
                f"🛠 {code} foi encaminhada para a aba Correções Telegram do QuestFlow.\n"
                "Se o computador estava desligado, a solicitação foi sincronizada agora."
            ),
            kind="confirmacao_correcao",
        )
        if token:
            try:
                send_message(token, chat_id, (
                    f"🛠 {code} foi encaminhada para a aba Correções Telegram do QuestFlow.\n"
                    "Se o computador estava desligado, a solicitação foi sincronizada agora."
                ))
                self.study.mark_outbox_sent(outbox_id)
            except Exception as error:
                retry_minutes = max(1, min(1440, int(config.get("flow_retry_minutes", 10) or 10)))
                self.study.mark_outbox_error(outbox_id, str(error), retry_minutes=retry_minutes)
        self._emit("review_requested", request=request)
        return request

    def _retry_pending_callbacks(self, config: dict, now: datetime) -> None:
        if self._last_callback_sweep and now < self._last_callback_sweep + timedelta(seconds=20):
            return
        self._last_callback_sweep = now
        retry_minutes = max(1, min(1440, int(config.get("flow_retry_minutes", 10) or 10)))
        for item in self.study.pending_callback_updates(20, due_only=True):
            payload = item.get("payload") or {}
            try:
                data = str(payload.get("data", ""))
                if data.startswith("qf:review:"):
                    self._process_review_callback(payload, config)
                elif data.startswith("qf:m:"):
                    parts = data.split(":")
                    if len(parts) == 5:
                        attempt_id, kind, code = parts[2], parts[3], parts[4]
                        confidence = {"s": "sabia", "d": "duvida", "g": "chutei"}.get(code) if kind == "c" else None
                        error_type = {"n": "nao_sabia", "c": "confundi", "d": "desatencao"}.get(code) if kind == "e" else None
                        perceived_difficulty = {"e": "facil", "m": "media", "h": "dificil"}.get(code) if kind == "d" else None
                        learning_gap = True if kind == "g" and code == "y" else None
                        self.study.record_attempt_meta(
                            attempt_id, confidence=confidence, error_type=error_type,
                            perceived_difficulty=perceived_difficulty, learning_gap=learning_gap,
                        )
                self.study.mark_callback_processed(str(item["id"]))
                self._emit("callback_recovered", callback_data=item.get("callback_data", ""))
            except Exception as error:
                self.study.mark_callback_error(str(item["id"]), str(error), retry_minutes=retry_minutes)
                self._emit("callback_recovery_error", error=str(error))

    def _resend_unanswered_delivery(self, row: dict, config: dict) -> dict:
        if not self._send_lock.acquire(blocking=False):
            return {"sent": False, "busy": True}
        try:
            token = str(config.get("telegram_bot_token", "")).strip()
            chat_id = str(row.get("chat_id") or config.get("telegram_chat_id", "")).strip()
            if not token or not chat_id:
                return {"sent": False, "missing_config": True}
            self.study.mark_unanswered_check(str(row["id"]))
            question = row["question"]
            max_attempts = max(1, min(8, int(config.get("flow_question_retry_attempts", 3) or 3)))
            try:
                send_message(
                    token,
                    chat_id,
                    "⏳ Esta questão ficou sem resposta. Estou enviando novamente para você concluir quando puder.",
                )
            except Exception:
                pass
            result = send_quiz_with_retry(
                token,
                chat_id,
                question,
                timeout=35,
                attempts=max_attempts,
                show_question_card=bool(config.get("flow_question_card_enabled", True)),
                native_explanation=bool(config.get("flow_native_quiz_explanation", False)),
            )
            count = int(row.get("unanswered_resend_count") or 0) + 1
            delivery = self.study.record_delivery(
                str(row["question_uid"]),
                chat_id,
                result,
                str(row.get("cycle_id") or f"unanswered-{uuid.uuid4()}"),
                parent_delivery_id=str(row["id"]),
                attempt_count=int(result.get("_attempt_count", 1) or 1),
                resend_reason="sem_resposta",
                unanswered_resend_count=count,
            )
            self._emit(
                "unanswered_resent",
                code=question.get("codigo_origem", ""),
                resend_count=count,
                delivery=delivery,
            )
            return {"sent": True, "delivery": delivery}
        except Exception as error:
            self._emit(
                "unanswered_resend_error",
                code=(row.get("question") or {}).get("codigo_origem", ""),
                error=str(error),
            )
            return {"sent": False, "error": str(error)}
        finally:
            self._send_lock.release()

    def _resend_due_unanswered(self, config: dict, now: datetime) -> None:
        if self._last_unanswered_sweep and now < self._last_unanswered_sweep + timedelta(minutes=5):
            return
        self._last_unanswered_sweep = now
        if not bool(config.get("flow_unanswered_resend_enabled", True)):
            return
        try:
            wait_hours = max(0.25, min(720.0, float(config.get("flow_unanswered_resend_hours", 24) or 24)))
            max_resends = max(0, min(10, int(config.get("flow_unanswered_max_resends", 2) or 2)))
            startup_grace = max(0, min(120, int(config.get("flow_background_startup_grace_minutes", 5))))
            batch_limit = max(1, min(5, int(config.get("flow_unanswered_batch_limit", 1) or 1)))
            daily_cap = max(0, min(20, int(config.get("flow_unanswered_daily_cap", 3) or 3)))
            session_cap = max(0, min(20, int(config.get("flow_unanswered_session_cap", 3) or 3)))
        except (TypeError, ValueError):
            wait_hours, max_resends = 24.0, 2
            startup_grace, batch_limit, daily_cap, session_cap = 5, 1, 3, 3
        if max_resends <= 0 or daily_cap <= 0 or session_cap <= 0:
            return
        if now < self._session_started_at + timedelta(minutes=startup_grace):
            return

        # Migração de segurança: não despeja no Telegram o estoque antigo de questões sem resposta.
        policy_version = self.study.get_runtime("unanswered_policy_version", "")
        if policy_version != "3.0.14":
            activated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            self.study.set_runtime("unanswered_policy_version", "3.0.14")
            self.study.set_runtime("unanswered_resend_activated_at", activated_at)
            self.study.set_runtime("unanswered_resend_daily_date", now.date().isoformat())
            self.study.set_runtime("unanswered_resend_daily_count", "0")
            self._emit(
                "unanswered_backlog_quarantined",
                message="O estoque antigo de questões sem resposta foi bloqueado para evitar envio em massa.",
            )
            return

        activation = self.study.get_runtime("unanswered_resend_activated_at", "")
        daily_date = self.study.get_runtime("unanswered_resend_daily_date", "")
        try:
            daily_count = int(self.study.get_runtime("unanswered_resend_daily_count", "0") or 0)
        except (TypeError, ValueError):
            daily_count = 0
        today = now.date().isoformat()
        if daily_date != today:
            daily_count = 0
            self.study.set_runtime("unanswered_resend_daily_date", today)
            self.study.set_runtime("unanswered_resend_daily_count", "0")

        remaining = min(
            batch_limit,
            daily_cap - daily_count,
            session_cap - self._unanswered_sent_this_session,
        )
        if remaining <= 0:
            return
        rows = self.study.unanswered_deliveries_due(
            wait_hours=wait_hours,
            max_resends=max_resends,
            limit=remaining,
            min_sent_at=activation or None,
        )
        for row in rows:
            if self._stop.is_set():
                break
            result = self._resend_unanswered_delivery(row, config)
            if result.get("sent"):
                daily_count += 1
                self._unanswered_sent_this_session += 1
                self.study.set_runtime("unanswered_resend_daily_count", str(daily_count))

    def _send_pre_reminder(self, config: dict, scheduled: datetime, now: datetime) -> None:
        if not bool(config.get("flow_send_pre_reminder", True)):
            return
        try:
            reminder_minutes = max(1, min(180, int(config.get("flow_reminder_minutes", 15))))
        except (TypeError, ValueError):
            reminder_minutes = 15
        reminder_at = scheduled - timedelta(minutes=reminder_minutes)
        date_key = scheduled.date().isoformat()
        if not reminder_at <= now < scheduled:
            return
        if self.study.get_runtime("last_pre_reminder_date") == date_key:
            return
        token = str(config.get("telegram_bot_token", "")).strip()
        chat_id = str(config.get("telegram_chat_id", "")).strip()
        if not token or not chat_id:
            return
        attempt_key = f"pre_reminder_attempt_{date_key}"
        last_attempt_text = self.study.get_runtime(attempt_key)
        try:
            last_attempt = datetime.fromisoformat(last_attempt_text) if last_attempt_text else None
        except ValueError:
            last_attempt = None
        if last_attempt is not None and now < last_attempt + timedelta(seconds=60):
            return
        self.study.set_runtime(attempt_key, now.isoformat(timespec="seconds"))
        count = max(1, int(config.get("flow_questions_per_cycle", 20) or 20))
        try:
            send_message(
                token,
                chat_id,
                (
                    f"⏰ Seu ciclo inteligente de {count} questões começa às {scheduled:%H:%M}.\n"
                    "A seleção vai alternar matérias e assuntos da sua trilha de Auditor, "
                    "priorizando erros, revisões vencidas e conteúdos pouco vistos."
                ),
            )
            self.study.set_runtime("last_pre_reminder_date", date_key)
            self._emit("pre_reminder_sent", scheduled_for=scheduled.isoformat(timespec="minutes"))
        except Exception as error:
            self._emit("reminder_error", error=str(error))

    def _send_missed_notice(self, config: dict, scheduled: datetime) -> None:
        date_key = scheduled.date().isoformat()
        if self.study.get_runtime("last_missed_notice_date") == date_key:
            return
        token = str(config.get("telegram_bot_token", "")).strip()
        chat_id = str(config.get("telegram_chat_id", "")).strip()
        if not token or not chat_id:
            return
        try:
            send_message(
                token,
                chat_id,
                (
                    f"⚠️ O ciclo previsto para {scheduled:%d/%m às %H:%M} não foi enviado no horário.\n"
                    "O computador ou o QuestFlow pode ter ficado desligado/sem conexão. "
                    "Vou tentar enviar agora como ciclo de recuperação."
                ),
            )
            self.study.set_runtime("last_missed_notice_date", date_key)
            self._emit("missed_notice_sent", scheduled_for=scheduled.isoformat(timespec="minutes"))
        except Exception as error:
            self._emit("reminder_error", error=str(error))

    def _run_relearning_sweep(self, config: dict, now: datetime) -> None:
        if not bool(config.get("flow_enabled", False)) or not bool(config.get("flow_relearning_enabled", True)) or self._pause.is_set():
            return
        try:
            grace = max(0, min(120, int(config.get("flow_background_startup_grace_minutes", 5) or 5)))
        except (TypeError, ValueError):
            grace = 5
        if now < self._session_started_at + timedelta(minutes=grace):
            return
        if self._last_relearning_sweep and now < self._last_relearning_sweep + timedelta(seconds=45):
            return
        self._last_relearning_sweep = now
        if self._relearning_day != now.date():
            self._relearning_day = now.date(); self._relearning_sent_today = 0
        cap = max(0, min(30, int(config.get("flow_relearning_daily_cap", 6) or 6)))
        if cap and self._relearning_sent_today >= cap:
            return
        if self._send_lock.locked() or not self.study.relearning_due_questions(limit=1):
            return
        self._relearning_sent_today += 1
        threading.Thread(
            target=lambda: self.send_cycle(manual=False, limit_override=1, cycle_kind="relearning", requested_via="fsrs_relearning"),
            daemon=True, name="questflow-relearning",
        ).start()

    def _run_optimizer_sweep(self, config: dict, now: datetime) -> None:
        if not bool(config.get("flow_fsrs_auto_optimize", True)):
            return
        if self._last_optimizer_sweep and now < self._last_optimizer_sweep + timedelta(minutes=10):
            return
        self._last_optimizer_sweep = now
        if self._optimizer_thread and self._optimizer_thread.is_alive():
            return
        if not self.study.should_optimize_fsrs():
            return
        def _work():
            result = self.study.optimize_fsrs(force=False)
            self._emit("fsrs_optimized" if result.get("ok") else "fsrs_optimizer_status", **result)
        self._optimizer_thread = threading.Thread(target=_work, daemon=True, name="questflow-fsrs-optimizer")
        self._optimizer_thread.start()

    def _scheduler_loop(self) -> None:
        while not self._stop.is_set():
            self._scheduler_heartbeat = time.monotonic()
            config = self.config_provider()
            now = datetime.now()
            # Manutenção funciona mesmo com o ciclo diário desativado ou pausado.
            self._retry_pending_callbacks(config, now)
            self._retry_pending_outbox(config, now)
            questions_paused = bool(config.get("telegram_questions_paused", False))
            if not questions_paused:
                self._retry_due_deliveries(config, now)
                self._resend_due_unanswered(config, now)
                self._run_relearning_sweep(config, now)
            self._run_optimizer_sweep(config, now)
            if not bool(config.get("flow_enabled", False)):
                self._stop.wait(1)
                continue
            if self._pause.is_set():
                self._stop.wait(1)
                continue

            retry_run: datetime | None = None
            self._ensure_schedule_activation(config, now)
            latest_due = self._latest_due_occurrence(config, now)
            next_occurrence = self._next_occurrence(config, now)
            self._next_run = next_occurrence

            # Aviso prévio do ciclo de hoje, quando o aplicativo está disponível.
            today_scheduled = self._scheduled_for_date(config, now)
            if now.weekday() in self._weekdays(config) and not self.study.daily_cycle_done(now.date().isoformat()):
                self._send_pre_reminder(config, today_scheduled, now)

            if latest_due is not None:
                date_key = latest_due.date().isoformat()
                already_done = self.study.daily_cycle_done(date_key)
                skipped = self.study.get_runtime("last_skipped_date") == date_key
                if not already_done and not skipped and now >= latest_due:
                    is_missed = now > latest_due + timedelta(minutes=2)
                    catch_up = bool(config.get("flow_catch_up_missed", True))
                    if is_missed and not catch_up and latest_due.date() < now.date():
                        self.study.set_runtime("last_skipped_date", date_key)
                    else:
                        try:
                            startup_grace = max(
                                0,
                                min(120, int(config.get("flow_background_startup_grace_minutes", 5))),
                            )
                        except (TypeError, ValueError):
                            startup_grace = 5
                        if is_missed and now < self._session_started_at + timedelta(minutes=startup_grace):
                            retry_run = self._session_started_at + timedelta(minutes=startup_grace)
                            self._next_run = min(next_occurrence, retry_run)
                            self._stop.wait(1)
                            continue
                        try:
                            retry_minutes = max(1, min(1440, int(config.get("flow_retry_minutes", 10))))
                        except (TypeError, ValueError):
                            retry_minutes = 10
                        last_attempt_text = self.study.get_runtime(f"last_attempt_{date_key}")
                        try:
                            last_attempt = datetime.fromisoformat(last_attempt_text) if last_attempt_text else None
                        except ValueError:
                            last_attempt = None
                        can_retry = last_attempt is None or now >= last_attempt + timedelta(minutes=retry_minutes)
                        if can_retry:
                            if is_missed:
                                self._send_missed_notice(config, latest_due)
                            self.study.set_runtime(f"last_attempt_{date_key}", now.isoformat(timespec="seconds"))
                            try:
                                result = self.send_cycle(
                                    manual=False,
                                    cycle_kind="recuperacao" if is_missed else "diario",
                                    scheduled_for=latest_due,
                                    requested_via="agendador",
                                )
                                if result.get("sent", 0) <= 0:
                                    retry_run = datetime.now() + timedelta(minutes=retry_minutes)
                                    self._emit(
                                        "cycle_retry_pending",
                                        retry_minutes=retry_minutes,
                                        at=retry_run.isoformat(timespec="minutes"),
                                    )
                            except Exception as error:
                                retry_run = datetime.now() + timedelta(minutes=retry_minutes)
                                self._emit("cycle_error", error=str(error))

            next_scheduled = self._next_occurrence(config, datetime.now())
            self._next_run = min(next_scheduled, retry_run) if retry_run else next_scheduled
            self._stop.wait(1)

    def send_cycle_now(
        self,
        limit_override: int | None = None,
        *,
        cycle_kind: str = "extra",
        requested_via: str = "programa",
    ) -> None:
        threading.Thread(
            target=lambda: self.send_cycle(
                manual=True,
                limit_override=limit_override,
                cycle_kind=cycle_kind,
                requested_via=requested_via,
            ),
            daemon=True,
            name="questflow-manual-cycle",
        ).start()

    def send_cycle(
        self,
        manual: bool,
        limit_override: int | None = None,
        *,
        cycle_kind: str = "extra",
        scheduled_for: datetime | None = None,
        requested_via: str = "programa",
    ) -> dict:
        if not self._send_lock.acquire(blocking=False):
            self._emit("cycle_skipped", reason="Já existe um ciclo de envio em andamento.")
            return {"sent": 0, "errors": 0, "busy": True}
        cycle_id = str(uuid.uuid4())
        sent = errors = 0
        try:
            config = self.config_provider()
            if bool(config.get("telegram_questions_paused", False)):
                self._emit("cycle_skipped", reason="Envio de questões pelo Telegram pausado pelo usuário.")
                return {"sent": 0, "errors": 0, "paused": True, "reason": "telegram_questions_paused"}
            token = str(config.get("telegram_bot_token", "")).strip()
            chat_id = str(config.get("telegram_chat_id", "")).strip()
            if not token or not chat_id:
                raise ValueError("Informe o token do bot e o Chat ID nas configurações.")
            try:
                limit = int(limit_override or config.get("flow_questions_per_cycle", 20))
            except (TypeError, ValueError):
                limit = 20
            limit = max(1, min(limit, 50))
            if limit_override is None and bool(config.get("flow_dynamic_cycle_size", True)):
                limit = self.study.recommended_cycle_size(limit)
            subjects = config.get("flow_subjects", [])
            if isinstance(subjects, str):
                subjects = [item.strip() for item in subjects.split("|") if item.strip()]
            filters = SelectionFilters(
                subjects=list(subjects or []),
                topic=str(config.get("flow_topic", "") or ""),
                approved_only=bool(config.get("flow_approved_only", True)),
                strategy=str(config.get("flow_strategy", "auditor_inteligente") or "auditor_inteligente"),
                recycle_when_empty=bool(config.get("flow_recycle_when_empty", True)),
            )
            if cycle_kind == "relearning":
                questions = self.study.relearning_due_questions(limit=limit)
            else:
                questions = self.study.select_questions(filters, limit)
            scheduled_date = scheduled_for.date().isoformat() if scheduled_for else None
            self.study.begin_cycle(
                cycle_id,
                cycle_kind,
                len(questions),
                scheduled_for=scheduled_for.isoformat(timespec="minutes") if scheduled_for else None,
                scheduled_date=scheduled_date,
                requested_via=requested_via,
            )
            self._emit(
                "cycle_started",
                cycle_id=cycle_id,
                count=len(questions),
                manual=manual,
                cycle_kind=cycle_kind,
                requested_via=requested_via,
            )
            if not questions:
                self.study.finish_cycle(cycle_id, 0, 0, "vazio", "Nenhuma questão corresponde aos filtros.")
                send_study_menu(
                    token,
                    chat_id,
                    "Não encontrei questões prontas para este ciclo. Revise os filtros ou aprove mais questões no banco.",
                    extra_count=int(config.get("flow_extra_questions_count", 5) or 5),
                    cycle_count=int(config.get("flow_questions_per_cycle", 20) or 20),
                    paused=self.paused,
                )
                self._emit("cycle_empty", cycle_id=cycle_id)
                return {"cycle_id": cycle_id, "sent": 0, "errors": 0}

            kind_label = {
                "diario": "ciclo diário",
                "recuperacao": "ciclo de recuperação",
                "extra": "bloco extra",
                "novo_ciclo": "novo ciclo solicitado",
                "unica": "questão avulsa",
                "relearning": "recuperação pós-erro FSRS",
            }.get(cycle_kind, "ciclo")
            send_message(
                token,
                chat_id,
                (
                    f"🎯 Iniciando {kind_label}: {len(questions)} questão(ões).\n"
                    "FSRS 6 ativo: revisões vencidas têm precedência real, com relearning pós-erro, "
                    "rotação ponderada entre matérias/aulas/assuntos e somente conteúdos estudados."
                ),
            )

            try:
                delay = max(0, int(config.get("flow_delay_seconds", 5)))
            except (TypeError, ValueError):
                delay = 5
            selected_subjects: set[str] = set()
            for index, question in enumerate(questions, start=1):
                if self._stop.is_set() or (self._pause.is_set() and not manual):
                    break
                uid = str(question.get("database_uid", ""))
                try:
                    max_attempts = max(1, min(8, int(config.get("flow_question_retry_attempts", 3) or 3)))

                    def retry_progress(attempt: int, retry_error: TelegramError, retry_delay: float) -> None:
                        self._emit(
                            "question_retry_wait",
                            cycle_id=cycle_id,
                            index=index,
                            total=len(questions),
                            question_uid=uid,
                            code=question.get("codigo_origem", ""),
                            attempt=attempt,
                            delay=round(retry_delay, 1),
                            error=str(retry_error),
                        )

                    result = send_quiz_with_retry(
                        token,
                        chat_id,
                        question,
                        timeout=35,
                        attempts=max_attempts,
                        progress=retry_progress,
                        position=index,
                        total=len(questions),
                        show_question_card=bool(config.get("flow_question_card_enabled", True)),
                        native_explanation=bool(config.get("flow_native_quiz_explanation", False)),
                    )
                    delivery = self.study.record_delivery(uid, chat_id, result, cycle_id, attempt_count=int(result.get("_attempt_count", 1) or 1))
                    sent += 1
                    selected_subjects.add(str(question.get("materia", "") or ""))
                    self._emit(
                        "question_sent",
                        cycle_id=cycle_id,
                        index=index,
                        total=len(questions),
                        question_uid=uid,
                        code=question.get("codigo_origem", ""),
                        subject=question.get("materia", ""),
                        topic=question.get("assunto", ""),
                        delivery=delivery,
                    )
                except Exception as error:
                    errors += 1
                    parsed = classify_exception(error)
                    retry_minutes = max(1, min(1440, int(config.get("flow_retry_minutes", 10) or 10)))
                    next_retry = self._retry_time(retry_minutes) if parsed.retryable and bool(config.get("flow_auto_retry_failed", True)) else None
                    delivery_id = self.study.record_delivery_error(
                        uid,
                        chat_id,
                        str(parsed),
                        cycle_id,
                        category=parsed.category,
                        retryable=parsed.retryable,
                        next_retry_at=next_retry,
                        attempt_count=max_attempts,
                    )
                    self._emit(
                        "question_error",
                        cycle_id=cycle_id,
                        delivery_id=delivery_id,
                        index=index,
                        question_uid=uid,
                        code=question.get("codigo_origem", ""),
                        error=str(parsed),
                        category=parsed.category,
                        retryable=parsed.retryable,
                        next_retry_at=next_retry,
                    )
                if index < len(questions) and delay:
                    for _ in range(delay * 10):
                        if self._stop.is_set():
                            break
                        time.sleep(0.1)

            status = "concluido" if sent == len(questions) and errors == 0 else ("parcial" if sent else "falhou")
            self.study.finish_cycle(cycle_id, sent, errors, status)
            try:
                stats = self.study.stats()
            except Exception:
                stats = {"correct": 0, "wrong": 0, "accuracy": 0.0}
            extra_count = max(1, min(20, int(config.get("flow_extra_questions_count", 5) or 5)))
            cycle_count = max(1, min(50, int(config.get("flow_questions_per_cycle", 20) or 20)))
            if bool(config.get("flow_send_completion_menu", True)):
                try:
                    send_study_menu(
                        token,
                        chat_id,
                        (
                            f"✅ {kind_label.capitalize()} concluído: {sent} enviada(s) e {errors} erro(s) de envio.\n"
                            f"Estatísticas acumuladas: {stats['correct']} acertos, {stats['wrong']} erros "
                            f"e {stats['accuracy']:.1f}% de aproveitamento.\n\n"
                            "Use os botões abaixo para continuar estudando quando quiser."
                        ),
                        extra_count=extra_count,
                        cycle_count=cycle_count,
                        paused=self.paused,
                    )
                except Exception as menu_error:
                    self._emit("menu_error", error=str(menu_error))
            self._emit(
                "cycle_finished",
                cycle_id=cycle_id,
                sent=sent,
                errors=errors,
                cycle_kind=cycle_kind,
                subjects=sorted(item for item in selected_subjects if item),
            )
            return {"cycle_id": cycle_id, "sent": sent, "errors": errors, "status": status}
        except Exception as error:
            try:
                self.study.finish_cycle(cycle_id, sent, errors, "falhou", str(error))
            except Exception:
                pass
            raise
        finally:
            self._send_lock.release()

    def _command_allowed(self, message: dict, config: dict) -> bool:
        target = str(config.get("telegram_chat_id", "")).strip()
        chat = str((message.get("chat") or {}).get("id", ""))
        return not target or chat == target

    def _stats_message(self) -> str:
        stats = self.study.stats()
        lines = [
            "📊 Seu desempenho no QuestFlow",
            f"Questões disponíveis: {stats['questions']}",
            f"Envios: {stats['sent']} · Respostas: {stats['attempts']}",
            f"Acertos: {stats['correct']} · Erros: {stats['wrong']}",
            f"Aproveitamento: {stats['accuracy']:.1f}%",
            f"Questões devidas agora: {stats['due']}",
        ]
        weak = self.study.subject_stats(5)
        if weak:
            lines.append("\nPrioridades por matéria:")
            for item in weak:
                label = str(item.get("priority_label") or "")
                score = float(item.get("priority_score") or 0.0)
                if label == "Aguardando estudo":
                    lines.append(f"• {item['subject']}: aguardando estudo na trilha")
                    continue
                retention = item.get("retention")
                recent = item.get("recent_accuracy")
                metrics = [f"prioridade {score:.0f}/100 ({label})"]
                if retention is not None:
                    metrics.append(f"retenção {float(retention):.0f}%")
                if recent is not None:
                    metrics.append(f"recente {float(recent):.0f}%")
                if int(item.get("due_count") or 0):
                    metrics.append(f"{int(item.get('due_count') or 0)} vencidas")
                lines.append(f"• {item['subject']}: " + " · ".join(metrics))
        return "\n".join(lines)

    @staticmethod
    def _optional_count(text: str, default: int, maximum: int = 50) -> int:
        pieces = text.split()
        if len(pieces) < 2:
            return default
        try:
            return max(1, min(maximum, int(pieces[1])))
        except ValueError:
            return default

    def _send_menu(self, token: str, chat_id: str, config: dict, text: str = "Escolha como deseja continuar:") -> None:
        send_study_menu(
            token,
            chat_id,
            text,
            extra_count=int(config.get("flow_extra_questions_count", 5) or 5),
            cycle_count=int(config.get("flow_questions_per_cycle", 20) or 20),
            paused=self.paused,
        )

    def _handle_message(self, message: dict, config: dict) -> None:
        text_original = str(message.get("text", "") or "").strip()
        text = text_original.lower()
        if not text.startswith("/") or not self._command_allowed(message, config):
            return
        token = str(config.get("telegram_bot_token", "")).strip()
        chat_id = str((message.get("chat") or {}).get("id", config.get("telegram_chat_id", "")))
        command = text.split()[0].split("@")[0]
        if command in {"/status", "/desempenho"}:
            self._send_menu(token, chat_id, config, self._stats_message())
        elif command == "/proxima":
            send_message(token, chat_id, "Preparando uma questão...")
            self.send_cycle_now(1, cycle_kind="unica", requested_via="telegram")
        elif command == "/mais":
            default = max(1, int(config.get("flow_extra_questions_count", 5) or 5))
            count = self._optional_count(text, default, 20)
            send_message(token, chat_id, f"Preparando mais {count} questões...")
            self.send_cycle_now(count, cycle_kind="extra", requested_via="telegram")
        elif command == "/ciclo":
            default = max(1, int(config.get("flow_questions_per_cycle", 20) or 20))
            count = self._optional_count(text, default, 50)
            send_message(token, chat_id, f"Preparando um novo ciclo de {count} questões...")
            self.send_cycle_now(count, cycle_kind="novo_ciclo", requested_via="telegram")
        elif command == "/pausar":
            self.pause()
            self._send_menu(token, chat_id, config, "Fluxo automático pausado. Suas estatísticas continuam salvas.")
        elif command == "/retomar":
            self.resume()
            self._send_menu(token, chat_id, config, "Fluxo automático retomado.")
        elif command == "/menu":
            self._send_menu(token, chat_id, config)
        elif command in {"/ajuda", "/start"}:
            self._send_menu(
                token,
                chat_id,
                config,
                (
                    "QuestFlow Studio — comandos disponíveis:\n"
                    "/proxima — envia 1 questão\n"
                    "/mais [quantidade] — envia um bloco extra\n"
                    "/ciclo [quantidade] — inicia outro ciclo\n"
                    "/desempenho — mostra suas estatísticas\n"
                    "/pausar e /retomar — controlam o ciclo diário\n"
                    "/menu — mostra os botões de estudo"
                ),
            )

    def _callback_allowed(self, callback: dict, config: dict) -> bool:
        message = callback.get("message") or {}
        return self._command_allowed(message, config)

    def _handle_callback_query(self, callback: dict, config: dict) -> None:
        token = str(config.get("telegram_bot_token", "")).strip()
        callback_id = str(callback.get("id", "") or "")
        if not token or not callback_id:
            return
        if not self._callback_allowed(callback, config):
            try:
                answer_callback_query(token, callback_id, "Este botão pertence a outro chat.")
            except Exception:
                pass
            return
        message = callback.get("message") or {}
        chat_id = str((message.get("chat") or {}).get("id", config.get("telegram_chat_id", "")))
        data = str(callback.get("data", "") or "")

        if data.startswith("qf:m:"):
            parts = data.split(":")
            # qf:m:<attempt_uuid>:c:<s|d|g> ou :e:<n|c|d>
            if len(parts) >= 6:
                attempt_id, kind, code = parts[2], parts[3], parts[4]
            elif len(parts) == 5:
                attempt_id, kind, code = parts[2], parts[3], parts[4]
            else:
                attempt_id = kind = code = ""
            confidence = {"s": "sabia", "d": "duvida", "g": "chutei"}.get(code) if kind == "c" else None
            error_type = {"n": "nao_sabia", "c": "confundi", "d": "desatencao"}.get(code) if kind == "e" else None
            perceived_difficulty = {"e": "facil", "m": "media", "h": "dificil"}.get(code) if kind == "d" else None
            learning_gap = True if kind == "g" and code == "y" else None
            result = self.study.record_attempt_meta(
                attempt_id, confidence=confidence, error_type=error_type,
                perceived_difficulty=perceived_difficulty, learning_gap=learning_gap,
            )
            try:
                label = "Registrado ✓" if result.get("ok") else str(result.get("error", "Não foi possível registrar"))[:120]
                answer_callback_query(token, callback_id, label)
            except Exception:
                pass
            self._emit("attempt_meta_updated", **result)
            return

        if data.startswith("qf:explain:"):
            question_uid = data.split(":", 2)[2].strip()
            question = self.database.get_question(question_uid)
            if not question:
                try:
                    answer_callback_query(token, callback_id, "Questão não encontrada no banco.", show_alert=True)
                except Exception:
                    pass
                return
            poll = message.get("poll") if isinstance(message.get("poll"), dict) else {}
            poll_id = str(poll.get("id", "") or "")
            callback_user = callback.get("from") or {}
            user_id = str(callback_user.get("id", "") or "")
            if poll_id and user_id and not self.study.user_answered_poll(poll_id, user_id):
                try:
                    answer_callback_query(
                        token,
                        callback_id,
                        "Responda ao quiz antes de abrir a explicação.",
                        show_alert=True,
                    )
                except Exception:
                    pass
                return
            try:
                answer_callback_query(token, callback_id, "Abrindo a explicação completa…")
            except Exception:
                pass
            try:
                send_explanation_card(
                    token,
                    chat_id,
                    question,
                    reply_to_message_id=message.get("message_id") if isinstance(message.get("message_id"), int) else None,
                )
            except Exception as error:
                try:
                    answer_callback_query(token, callback_id, f"Não foi possível abrir: {str(error)[:120]}", show_alert=True)
                except Exception:
                    pass
                self._emit("explanation_error", error=str(error), question_uid=question_uid)
            return

        if data.startswith("qf:review:"):
            try:
                self._process_review_callback(callback, config)
            except Exception as error:
                try:
                    answer_callback_query(token, callback_id, f"Não foi possível guardar: {str(error)[:120]}")
                except Exception:
                    pass
                self._emit("review_request_error", error=str(error), question_uid=data.split(":", 2)[-1])
            return

        try:
            answer_callback_query(token, callback_id, "Comando recebido")
        except Exception:
            pass
        if data.startswith("qf:more:"):
            try:
                count = max(1, min(20, int(data.rsplit(":", 1)[1])))
            except ValueError:
                count = 5
            send_message(token, chat_id, f"Preparando mais {count} questões...")
            self.send_cycle_now(count, cycle_kind="extra", requested_via="botao_telegram")
        elif data.startswith("qf:cycle:"):
            try:
                count = max(1, min(50, int(data.rsplit(":", 1)[1])))
            except ValueError:
                count = 20
            send_message(token, chat_id, f"Preparando um novo ciclo de {count} questões...")
            self.send_cycle_now(count, cycle_kind="novo_ciclo", requested_via="botao_telegram")
        elif data == "qf:stats":
            self._send_menu(token, chat_id, config, self._stats_message())
        elif data == "qf:pause":
            self.pause()
            self._send_menu(token, chat_id, config, "Fluxo automático pausado.")
        elif data == "qf:resume":
            self.resume()
            self._send_menu(token, chat_id, config, "Fluxo automático retomado.")

    def _listener_loop(self) -> None:
        self._emit("listener_status", status="Conectando ao Telegram...")
        while not self._stop.is_set():
            self._listener_heartbeat = time.monotonic()
            config = self.config_provider()
            token = str(config.get("telegram_bot_token", "")).strip()
            if not token:
                self._emit("listener_error", error="Token do bot não configurado.")
                self._stop.wait(5)
                continue
            try:
                updates = get_updates(
                    token,
                    offset=self._update_offset,
                    timeout=25,
                    allowed_updates=["poll_answer", "message", "callback_query"],
                )
                self._listener_heartbeat = time.monotonic()
                self._emit("listener_status", status="Respostas e botões do Telegram ativos")
                for update in updates:
                    update_id = update.get("update_id")
                    inbox_id = ""
                    try:
                        if "poll_answer" in update:
                            answer = self.study.record_poll_answer(update["poll_answer"])
                            if answer:
                                self._emit("answer_received", **answer)
                                mode = str(config.get("flow_explanation_mode", "automatico") or "automatico")
                                if not answer.get("feedback_already_sent") and mode != "somente_botao":
                                    try:
                                        feedback = send_answer_feedback(token, answer, mode=mode)
                                        message_id = None
                                        messages = feedback.get("messages", []) if isinstance(feedback, dict) else []
                                        if messages:
                                            message_id = ((messages[-1].get("result") or {}).get("message_id")
                                                          if isinstance(messages[-1], dict) else None)
                                        self.study.mark_attempt_feedback_sent(str(answer.get("attempt_id", "")), message_id)
                                        self._emit("answer_feedback_sent", question_uid=answer.get("question_uid"), mode=mode)
                                    except Exception as feedback_error:
                                        self._emit("answer_feedback_error", error=str(feedback_error), question_uid=answer.get("question_uid"))
                        elif "callback_query" in update:
                            callback = update["callback_query"]
                            callback_data = str(callback.get("data", ""))
                            if isinstance(update_id, int) and (callback_data.startswith("qf:review:") or callback_data.startswith("qf:m:")):
                                inbox_id = self.study.enqueue_callback_update(update_id, callback)
                            self._handle_callback_query(callback, config)
                            if inbox_id:
                                self.study.mark_callback_processed(inbox_id)
                        elif "message" in update:
                            self._handle_message(update["message"], config)
                        if isinstance(update_id, int):
                            self._update_offset = update_id + 1
                            self.study.set_runtime("telegram_update_offset", str(self._update_offset))
                    except Exception as update_error:
                        if inbox_id:
                            retry_minutes = max(1, min(1440, int(config.get("flow_retry_minutes", 10) or 10)))
                            self.study.mark_callback_error(inbox_id, str(update_error), retry_minutes=retry_minutes)
                        self._emit("listener_update_error", error=str(update_error), update_id=update_id)
            except Exception as error:
                self._emit("listener_error", error=str(error))
                for _ in range(5):
                    if self._stop.wait(1):
                        break
