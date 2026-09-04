from __future__ import annotations

"""Integração oficial do QuestFlow com Py-FSRS 6.

A partir da série 5.6 o QuestFlow trata Py-FSRS como scheduler principal. O
motor DSR local permanece apenas como fallback de continuidade caso a instalação
esteja danificada; o instalador exige ``fsrs[optimizer]`` para a operação normal.

Toda a API externa fica isolada aqui para facilitar futuras migrações de versão.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import importlib
import json
from typing import Any, Iterable, Mapping, Sequence


FSRS_ADAPTER_VERSION = "qf-fsrs6-adapter-2"
FSRS_REQUIRED_VERSION = "==6.3.2"
DEFAULT_LEARNING_STEPS_MINUTES = (1, 10)
DEFAULT_RELEARNING_STEPS_MINUTES = (10,)
DEFAULT_MAXIMUM_INTERVAL = 36500


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _aware_utc(value: datetime | None) -> datetime:
    result = value or _utc_now()
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def fsrs_available() -> bool:
    try:
        module = importlib.import_module("fsrs")
        return all(hasattr(module, name) for name in ("Scheduler", "Card", "Rating", "ReviewLog"))
    except Exception:
        return False


def optimizer_available() -> bool:
    try:
        module = importlib.import_module("fsrs")
        optimizer = getattr(module, "Optimizer", None)
        return optimizer is not None
    except Exception:
        return False


def fsrs_version() -> str:
    try:
        module = importlib.import_module("fsrs")
        return str(getattr(module, "__version__", "fsrs"))
    except Exception:
        return "indisponivel"


def _normalize_parameters(parameters: Sequence[float] | None) -> tuple[float, ...] | None:
    if not parameters:
        return None
    try:
        values = tuple(float(item) for item in parameters)
    except (TypeError, ValueError):
        return None
    # FSRS-6 usa 21 parâmetros. Não passamos um vetor incompleto ao scheduler.
    return values if len(values) == 21 else None


def _steps(values: Iterable[int | float] | None, fallback: tuple[int, ...]) -> tuple[timedelta, ...]:
    source = tuple(values or fallback)
    result: list[timedelta] = []
    for value in source:
        try:
            minutes = max(0.0, float(value))
        except (TypeError, ValueError):
            continue
        if minutes > 0:
            result.append(timedelta(minutes=minutes))
    return tuple(result)


def build_scheduler(
    *,
    parameters: Sequence[float] | None = None,
    desired_retention: float = 0.90,
    learning_steps_minutes: Iterable[int | float] | None = None,
    relearning_steps_minutes: Iterable[int | float] | None = None,
    maximum_interval: int = DEFAULT_MAXIMUM_INTERVAL,
    enable_fuzzing: bool = True,
):
    """Cria um ``fsrs.Scheduler`` usando apenas a API pública do Py-FSRS."""

    fsrs = importlib.import_module("fsrs")
    Scheduler = getattr(fsrs, "Scheduler")
    kwargs: dict[str, Any] = {
        "desired_retention": max(0.70, min(0.97, float(desired_retention))),
        "learning_steps": _steps(learning_steps_minutes, DEFAULT_LEARNING_STEPS_MINUTES),
        "relearning_steps": _steps(relearning_steps_minutes, DEFAULT_RELEARNING_STEPS_MINUTES),
        "maximum_interval": max(1, int(maximum_interval or DEFAULT_MAXIMUM_INTERVAL)),
        "enable_fuzzing": bool(enable_fuzzing),
    }
    normalized = _normalize_parameters(parameters)
    if normalized is not None:
        kwargs["parameters"] = normalized
    try:
        return Scheduler(**kwargs)
    except TypeError:
        # Compatibilidade defensiva com wrappers/fakes antigos; a instalação
        # oficial 6.x recebe todos os argumentos acima.
        return Scheduler(desired_retention=kwargs["desired_retention"])


def rating_from_answer(
    *,
    correct: bool,
    response_seconds: float = 0.0,
    prior_accuracy: float = 0.0,
    prior_attempts: int | None = None,
    confidence: str = "",
) -> int:
    """Mapeia o quiz para Again/Hard/Good/Easy (1..4).

    A resposta objetiva continua sendo a evidência principal. A autopercepção é
    apenas um sinal auxiliar: um acerto por chute/dúvida não recebe a mesma nota
    de um acerto recuperado com segurança.
    """

    if not correct:
        return 1
    confidence_norm = str(confidence or "").strip().casefold()
    if confidence_norm in {"chutei", "chute", "duvida", "dúvida", "incerto"}:
        return 2
    response = max(0.0, float(response_seconds or 0.0))
    accuracy = max(0.0, min(1.0, float(prior_accuracy or 0.0)))
    # Sem histórico não é baixa performance. A suavização Bayesiana inicial de
    # 0,50 continua útil para modelos preditivos, mas não deve rebaixar uma
    # primeira resposta correta para Hard.
    history_exists = prior_attempts is None or max(0, int(prior_attempts)) > 0
    if response >= 90 or (history_exists and accuracy < 0.55):
        return 2
    if confidence_norm in {"sabia", "seguro", "facil", "fácil"} and 0 < response <= 15 and accuracy >= 0.80:
        return 4
    if 0 < response <= 12 and accuracy >= 0.88:
        return 4
    return 3


@dataclass(slots=True)
class FSRSResult:
    card_json: str
    review_log_json: str
    due_at: str
    stability: float
    difficulty: float
    retrievability: float
    rating: int
    scheduler_state: str
    scheduler_version: str


@dataclass(slots=True)
class FSRSOptimizationResult:
    parameters: tuple[float, ...]
    desired_retention: float | None
    review_count: int
    scheduler_version: str


def _serialized(value: Any) -> str:
    if hasattr(value, "to_json"):
        serialized = value.to_json()
        if isinstance(serialized, str):
            return serialized
        return json.dumps(serialized, ensure_ascii=False, default=str)
    return json.dumps(getattr(value, "__dict__", {"value": str(value)}), ensure_ascii=False, default=str)


def _state_name(card: Any) -> str:
    state = getattr(card, "state", None)
    name = getattr(state, "name", None)
    if name:
        return str(name).strip().lower()
    value = str(state or "").strip().lower()
    for candidate in ("learning", "review", "relearning"):
        if candidate in value:
            return candidate
    return value or "review"


def review_with_fsrs(
    card_json: str | None,
    *,
    correct: bool,
    response_seconds: float,
    prior_accuracy: float,
    prior_attempts: int | None = None,
    desired_retention: float,
    now: datetime | None = None,
    confidence: str = "",
    parameters: Sequence[float] | None = None,
    learning_steps_minutes: Iterable[int | float] | None = None,
    relearning_steps_minutes: Iterable[int | float] | None = None,
    maximum_interval: int = DEFAULT_MAXIMUM_INTERVAL,
    enable_fuzzing: bool = True,
    due_cap: datetime | None = None,
) -> FSRSResult | None:
    """Executa uma revisão real com Py-FSRS 6, quando a dependência está íntegra."""

    try:
        fsrs = importlib.import_module("fsrs")
        Card = getattr(fsrs, "Card")
        Rating = getattr(fsrs, "Rating")
        scheduler = build_scheduler(
            parameters=parameters,
            desired_retention=desired_retention,
            learning_steps_minutes=learning_steps_minutes,
            relearning_steps_minutes=relearning_steps_minutes,
            maximum_interval=maximum_interval,
            enable_fuzzing=enable_fuzzing,
        )

        if card_json:
            try:
                card = Card.from_json(card_json)
            except Exception:
                card = Card()
        else:
            card = Card()

        rating_value = rating_from_answer(
            correct=correct,
            response_seconds=response_seconds,
            prior_accuracy=prior_accuracy,
            prior_attempts=prior_attempts,
            confidence=confidence,
        )
        rating = Rating(rating_value)
        review_time = _aware_utc(now)
        review_duration_ms = int(max(0.0, float(response_seconds or 0.0)) * 1000) or None
        try:
            card, review_log = scheduler.review_card(
                card,
                rating,
                review_datetime=review_time,
                review_duration=review_duration_ms,
            )
        except TypeError:
            # Compatibilidade apenas com wrappers/fakes legados usados na suíte;
            # Py-FSRS 6.3.2 aceita review_duration oficialmente.
            card, review_log = scheduler.review_card(card, rating, review_datetime=review_time)

        due = _aware_utc(getattr(card, "due", review_time))
        if due_cap is not None:
            cap = _aware_utc(due_cap)
            if due > cap:
                due = cap
                # Card.due é gravável no Py-FSRS; se alguma versão futura mudar,
                # o due serializado pode divergir, mas o banco continua respeitando o cap.
                try:
                    card.due = cap
                except Exception:
                    pass

        stability = float(getattr(card, "stability", 1.0) or 1.0)
        difficulty = float(getattr(card, "difficulty", 5.0) or 5.0)
        retrievability = float(scheduler.get_card_retrievability(card, current_datetime=review_time))
        return FSRSResult(
            card_json=_serialized(card),
            review_log_json=_serialized(review_log),
            due_at=due.replace(microsecond=0).isoformat(),
            stability=max(0.01, stability),
            difficulty=max(1.0, min(10.0, difficulty)),
            retrievability=max(0.0, min(1.0, retrievability)),
            rating=rating_value,
            scheduler_state=_state_name(card),
            scheduler_version=fsrs_version(),
        )
    except Exception:
        return None


def current_retrievability(
    card_json: str | None,
    *,
    desired_retention: float = 0.90,
    parameters: Sequence[float] | None = None,
    now: datetime | None = None,
) -> float | None:
    if not card_json:
        return None
    try:
        fsrs = importlib.import_module("fsrs")
        Card = getattr(fsrs, "Card")
        scheduler = build_scheduler(parameters=parameters, desired_retention=desired_retention)
        card = Card.from_json(card_json)
        return max(0.0, min(1.0, float(scheduler.get_card_retrievability(card, current_datetime=_aware_utc(now)))))
    except Exception:
        return None


def batch_retrievability(
    cards: Mapping[str, str | None],
    *,
    desired_retention: float = 0.90,
    parameters: Sequence[float] | None = None,
    now: datetime | None = None,
) -> dict[str, float]:
    """Calcula retrievability FSRS de vários cartões com um único Scheduler.

    A seleção de ciclos pode avaliar centenas/milhares de questões; construir um
    Scheduler por questão desperdiçaria CPU. Este caminho mantém o cálculo
    oficial do Py-FSRS e desserializa apenas os cartões existentes.
    """

    if not cards:
        return {}
    try:
        fsrs = importlib.import_module("fsrs")
        Card = getattr(fsrs, "Card")
        scheduler = build_scheduler(parameters=parameters, desired_retention=desired_retention)
        current = _aware_utc(now)
        output: dict[str, float] = {}
        for key, raw in cards.items():
            if not str(raw or "").strip():
                continue
            try:
                card = Card.from_json(str(raw))
                value = float(scheduler.get_card_retrievability(card, current_datetime=current))
                output[str(key)] = max(0.0, min(1.0, value))
            except Exception:
                continue
        return output
    except Exception:
        return {}



def optimize_review_logs(
    review_logs_json: Iterable[str],
    *,
    optimize_retention: bool = True,
) -> FSRSOptimizationResult | None:
    """Otimiza os 21 parâmetros FSRS a partir de ReviewLogs reais do usuário."""

    try:
        fsrs = importlib.import_module("fsrs")
        ReviewLog = getattr(fsrs, "ReviewLog")
        Optimizer = getattr(fsrs, "Optimizer")
        logs = []
        for raw in review_logs_json:
            if not str(raw or "").strip():
                continue
            try:
                logs.append(ReviewLog.from_json(str(raw)))
            except Exception:
                continue
        if not logs:
            return None
        optimizer = Optimizer(logs)
        parameters = tuple(float(value) for value in optimizer.compute_optimal_parameters())
        if len(parameters) != 21:
            return None
        retention: float | None = None
        if optimize_retention:
            try:
                retention = float(optimizer.compute_optimal_retention(parameters))
                retention = max(0.70, min(0.97, retention))
            except Exception:
                retention = None
        return FSRSOptimizationResult(
            parameters=parameters,
            desired_retention=retention,
            review_count=len(logs),
            scheduler_version=fsrs_version(),
        )
    except Exception:
        return None


__all__ = [
    "DEFAULT_LEARNING_STEPS_MINUTES",
    "DEFAULT_MAXIMUM_INTERVAL",
    "DEFAULT_RELEARNING_STEPS_MINUTES",
    "FSRS_ADAPTER_VERSION",
    "FSRS_REQUIRED_VERSION",
    "FSRSOptimizationResult",
    "FSRSResult",
    "batch_retrievability",
    "build_scheduler",
    "current_retrievability",
    "fsrs_available",
    "fsrs_version",
    "optimizer_available",
    "optimize_review_logs",
    "rating_from_answer",
    "review_with_fsrs",
]
