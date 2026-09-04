from __future__ import annotations

"""Motor adaptativo local do QuestFlow.

O módulo combina um estado de memória inspirado em modelos DSR/FSRS com um
classificador logístico incremental. Ele não depende de serviços externos nem
substitui uma implementação oficial completa do FSRS; foi desenhado para ser
interpretável, testável e seguro para migração de bancos existentes.
"""

from dataclasses import dataclass, asdict
import json
import math
from typing import Iterable, Mapping

MODEL_VERSION = "qf-adaptive-1"
DEFAULT_DECAY = 0.1542
DEFAULT_TARGET_RETENTION = 0.88


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def sigmoid(value: float) -> float:
    value = clamp(value, -35.0, 35.0)
    return 1.0 / (1.0 + math.exp(-value))


def forgetting_curve(
    elapsed_days: float,
    stability_days: float,
    *,
    decay: float = DEFAULT_DECAY,
) -> float:
    """Probabilidade aproximada de recordação.

    A forma é compatível com a curva de esquecimento usada pela família FSRS:
    R(S)=0,9 por construção. Valores inválidos são normalizados para manter o
    motor numericamente estável.
    """

    elapsed = max(0.0, float(elapsed_days))
    stability = max(0.05, float(stability_days))
    exponent = max(0.05, float(decay))
    factor = math.pow(0.9, -1.0 / exponent) - 1.0
    return clamp(math.pow(1.0 + factor * elapsed / stability, -exponent), 0.0, 1.0)


def interval_for_retention(
    stability_days: float,
    target_retention: float = DEFAULT_TARGET_RETENTION,
    *,
    decay: float = DEFAULT_DECAY,
) -> float:
    """Intervalo em dias no qual a curva alcança a retenção desejada."""

    stability = max(0.05, float(stability_days))
    retention = clamp(target_retention, 0.70, 0.97)
    exponent = max(0.05, float(decay))
    factor = math.pow(0.9, -1.0 / exponent) - 1.0
    interval = stability * (math.pow(retention, -1.0 / exponent) - 1.0) / factor
    return clamp(interval, 0.04, 3650.0)


@dataclass(slots=True)
class MemoryState:
    difficulty: float = 5.0
    stability_days: float = 1.0
    retrievability: float = 0.9
    response_time_ema: float = 0.0
    review_count: int = 0

    @classmethod
    def from_mapping(cls, data: Mapping[str, object] | None) -> "MemoryState":
        data = data or {}
        return cls(
            difficulty=clamp(float(data.get("difficulty", 5.0) or 5.0), 1.0, 10.0),
            stability_days=clamp(float(data.get("stability_days", 1.0) or 1.0), 0.05, 3650.0),
            retrievability=clamp(float(data.get("retrievability", 0.9) or 0.9), 0.0, 1.0),
            response_time_ema=max(0.0, float(data.get("response_time_ema", 0.0) or 0.0)),
            review_count=max(0, int(data.get("review_count", 0) or 0)),
        )

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def update_memory_state(
    state: MemoryState,
    *,
    correct: bool,
    elapsed_days: float,
    response_seconds: float | None = None,
    target_retention: float = DEFAULT_TARGET_RETENTION,
) -> tuple[MemoryState, float]:
    """Atualiza dificuldade/estabilidade e devolve o próximo intervalo.

    A atualização é deliberadamente conservadora: respostas corretas aumentam
    a estabilidade de forma decrescente; erros reduzem a estabilidade e elevam
    a dificuldade. Tempo de resposta é usado apenas como sinal suave.
    """

    elapsed = max(0.0, float(elapsed_days))
    recall = forgetting_curve(elapsed, state.stability_days)
    response = max(0.0, float(response_seconds or 0.0))
    if state.response_time_ema <= 0.0:
        response_ema = response
    elif response > 0.0:
        response_ema = 0.82 * state.response_time_ema + 0.18 * response
    else:
        response_ema = state.response_time_ema

    # Respostas muito lentas reduzem levemente a qualidade do acerto sem nunca
    # convertê-lo em erro. A escala logarítmica evita penalidades exageradas.
    speed_penalty = clamp(math.log1p(response) / math.log(301.0), 0.0, 1.0) if response else 0.0
    if correct:
        difficulty = state.difficulty - 0.28 * (1.0 - speed_penalty * 0.45)
        difficulty += 0.10 * (recall - target_retention)
        growth = 1.0 + (11.0 - difficulty) / 10.0 * (0.45 + 2.4 * (1.0 - recall))
        growth *= 1.0 - 0.12 * speed_penalty
        stability = state.stability_days * max(1.06, growth)
    else:
        difficulty = state.difficulty + 0.85 + 0.20 * (1.0 - recall)
        lapse_factor = 0.28 + 0.035 * (10.0 - difficulty)
        stability = max(0.18, state.stability_days * clamp(lapse_factor, 0.18, 0.55))

    next_state = MemoryState(
        difficulty=clamp(difficulty, 1.0, 10.0),
        stability_days=clamp(stability, 0.05, 3650.0),
        retrievability=1.0 if correct else 0.20,
        response_time_ema=response_ema,
        review_count=state.review_count + 1,
    )
    interval = interval_for_retention(next_state.stability_days, target_retention)
    if not correct:
        interval = min(interval, 0.25)  # nova tentativa em até seis horas
    return next_state, interval


FEATURE_NAMES = (
    "bias",
    "log_stability",
    "elapsed_ratio",
    "difficulty",
    "historical_accuracy",
    "log_response_time",
    "is_new",
    "autoapproved",
)

DEFAULT_WEIGHTS = {
    "bias": 0.55,
    "log_stability": 0.34,
    "elapsed_ratio": -1.20,
    "difficulty": -0.62,
    "historical_accuracy": 1.05,
    "log_response_time": -0.20,
    "is_new": -0.45,
    "autoapproved": -0.08,
}


@dataclass(slots=True)
class OnlineRecallModel:
    weights: dict[str, float]
    samples: int = 0
    learning_rate: float = 0.035
    l2: float = 0.0008
    version: str = MODEL_VERSION

    @classmethod
    def default(cls) -> "OnlineRecallModel":
        return cls(weights=dict(DEFAULT_WEIGHTS))

    @classmethod
    def from_json(cls, raw: str | None) -> "OnlineRecallModel":
        if not raw:
            return cls.default()
        try:
            payload = json.loads(raw)
            weights = dict(DEFAULT_WEIGHTS)
            for name, value in dict(payload.get("weights", {})).items():
                if name in FEATURE_NAMES:
                    weights[name] = clamp(float(value), -8.0, 8.0)
            return cls(
                weights=weights,
                samples=max(0, int(payload.get("samples", 0) or 0)),
                learning_rate=clamp(float(payload.get("learning_rate", 0.035) or 0.035), 0.001, 0.2),
                l2=clamp(float(payload.get("l2", 0.0008) or 0.0008), 0.0, 0.05),
                version=str(payload.get("version", MODEL_VERSION) or MODEL_VERSION),
            )
        except Exception:
            return cls.default()

    def to_json(self) -> str:
        return json.dumps(
            {
                "weights": self.weights,
                "samples": self.samples,
                "learning_rate": self.learning_rate,
                "l2": self.l2,
                "version": self.version,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    @staticmethod
    def features(
        *,
        state: MemoryState,
        elapsed_days: float,
        historical_accuracy: float,
        response_seconds: float,
        is_new: bool,
        autoapproved: bool,
    ) -> dict[str, float]:
        stability = max(0.05, state.stability_days)
        return {
            "bias": 1.0,
            "log_stability": clamp(math.log1p(stability) / 5.0, 0.0, 1.5),
            "elapsed_ratio": clamp(float(elapsed_days) / stability, 0.0, 6.0) / 3.0,
            "difficulty": (clamp(state.difficulty, 1.0, 10.0) - 5.5) / 4.5,
            "historical_accuracy": clamp(historical_accuracy, 0.0, 1.0) - 0.5,
            "log_response_time": clamp(math.log1p(max(0.0, response_seconds)) / math.log(601.0), 0.0, 1.5),
            "is_new": 1.0 if is_new else 0.0,
            "autoapproved": 1.0 if autoapproved else 0.0,
        }

    def predict(self, features: Mapping[str, float]) -> float:
        linear = sum(self.weights.get(name, 0.0) * float(features.get(name, 0.0)) for name in FEATURE_NAMES)
        return clamp(sigmoid(linear), 0.01, 0.99)

    def update(self, features: Mapping[str, float], outcome: bool) -> float:
        prediction = self.predict(features)
        error = (1.0 if outcome else 0.0) - prediction
        # Redução suave da taxa conforme o histórico cresce.
        rate = self.learning_rate / math.sqrt(1.0 + self.samples / 200.0)
        for name in FEATURE_NAMES:
            value = float(features.get(name, 0.0))
            regularizer = 0.0 if name == "bias" else self.l2 * self.weights.get(name, 0.0)
            updated = self.weights.get(name, 0.0) + rate * (error * value - regularizer)
            self.weights[name] = clamp(updated, -8.0, 8.0)
        self.samples += 1
        return prediction


def adaptive_priority_score(
    *,
    predicted_recall: float,
    retrievability: float,
    overdue_days: float,
    is_new: bool,
    sent_count: int,
    coverage_gap: float = 0.0,
    correction_priority: bool = False,
    review_status: str = "",
) -> float:
    """Pontuação interpretável para escolher a próxima questão."""

    recall_risk = 1.0 - clamp(predicted_recall, 0.0, 1.0)
    memory_risk = 1.0 - clamp(retrievability, 0.0, 1.0)
    uncertainty = 1.0 - abs(clamp(predicted_recall, 0.0, 1.0) - 0.5) * 2.0
    status_bonus = 8.0 if review_status.strip().lower() == "aprovado" else 0.0
    return (
        (240.0 if correction_priority else 0.0)
        + recall_risk * 115.0
        + memory_risk * 62.0
        + uncertainty * 18.0
        + min(max(0.0, overdue_days), 60.0) * 2.2
        + (46.0 if is_new else 0.0)
        + 24.0 / math.sqrt(1.0 + max(0, int(sent_count)))
        + clamp(coverage_gap, 0.0, 1.0) * 34.0
        + status_bonus
    )
