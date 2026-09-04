from __future__ import annotations

"""Recomendador multiobjetivo e projeções da Etapa 4.

O módulo é deliberadamente puro: não acessa SQLite e não altera o FSRS. Ele
combina sinais já produzidos pelos motores de aprendizagem e devolve pontuações
explicáveis. A precedência entre classes FSRS continua responsabilidade do
Learning Engine/StudyRepository.
"""

from dataclasses import dataclass
import math
from typing import Mapping

MODEL_VERSION = "qf-multiobjective-2"


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


@dataclass(frozen=True, slots=True)
class RecommendationWeights:
    mastery_gap: float = 0.24
    forgetting_risk: float = 0.22
    coverage_gap: float = 0.16
    board_incidence: float = 0.10
    irt_information: float = 0.10
    exam_urgency: float = 0.08
    uncertainty: float = 0.06
    recency: float = 0.04

    def normalized(self) -> "RecommendationWeights":
        values = [
            max(0.0, self.mastery_gap), max(0.0, self.forgetting_risk),
            max(0.0, self.coverage_gap), max(0.0, self.board_incidence),
            max(0.0, self.irt_information), max(0.0, self.exam_urgency),
            max(0.0, self.uncertainty), max(0.0, self.recency),
        ]
        total = sum(values) or 1.0
        return RecommendationWeights(*(value / total for value in values))


MODE_WEIGHTS: dict[str, RecommendationWeights] = {
    "equilibrado": RecommendationWeights(),
    "diagnostico": RecommendationWeights(
        mastery_gap=0.18, forgetting_risk=0.10, coverage_gap=0.12,
        board_incidence=0.08, irt_information=0.25, exam_urgency=0.05,
        uncertainty=0.17, recency=0.05,
    ),
    "revisao": RecommendationWeights(
        mastery_gap=0.25, forgetting_risk=0.32, coverage_gap=0.08,
        board_incidence=0.07, irt_information=0.08, exam_urgency=0.08,
        uncertainty=0.05, recency=0.07,
    ),
    "edital": RecommendationWeights(
        mastery_gap=0.20, forgetting_risk=0.14, coverage_gap=0.25,
        board_incidence=0.16, irt_information=0.07, exam_urgency=0.10,
        uncertainty=0.05, recency=0.03,
    ),
}


@dataclass(frozen=True, slots=True)
class RecommendationResult:
    score: float
    components: dict[str, float]
    signals: dict[str, float]
    reasons: list[str]
    mode: str
    version: str = MODEL_VERSION


def recommendation_weights(mode: str | None) -> RecommendationWeights:
    key = str(mode or "equilibrado").strip().lower()
    return MODE_WEIGHTS.get(key, MODE_WEIGHTS["equilibrado"]).normalized()


def multiobjective_priority(
    *,
    mastery: float | None,
    mastery_confidence: float,
    retrievability: float | None,
    coverage_gap: float,
    board_incidence: float,
    irt_information: float | None,
    exam_urgency: float,
    days_since_seen: float | None,
    mode: str = "equilibrado",
) -> RecommendationResult:
    """Pontuação 0..100 com decomposição auditável.

    Baixa confiança do KT reduz a força do déficit observado e aumenta o peso
    de incerteza, impedindo falsa precisão em amostras pequenas.
    """
    weights = recommendation_weights(mode)
    confidence = clamp(mastery_confidence)
    if mastery is None:
        mastery_gap = 0.55
        uncertainty = 1.0
    else:
        raw_gap = 1.0 - clamp(mastery)
        # Quando o KT tem evidência fraca, o déficit estimado perde força e a
        # incerteza passa a orientar seleção diagnóstica, evitando falsa precisão.
        mastery_gap = raw_gap * (0.35 + 0.65 * confidence)
        uncertainty = 1.0 - confidence
    forgetting = 0.50 if retrievability is None else 1.0 - clamp(retrievability)
    coverage = clamp(coverage_gap)
    incidence = clamp(board_incidence)
    # Em 2PL a informação pessoal costuma ficar abaixo de 1.2. Saturar evita
    # que itens instáveis dominem a recomendação.
    information = clamp(float(irt_information or 0.0) / 0.85)
    urgency = clamp(exam_urgency)
    if days_since_seen is None:
        recency = 0.65
    else:
        recency = clamp(1.0 - math.exp(-max(0.0, float(days_since_seen)) / 18.0))

    signals = {
        "mastery_gap": mastery_gap,
        "forgetting_risk": forgetting,
        "coverage_gap": coverage,
        "board_incidence": incidence,
        "irt_information": information,
        "exam_urgency": urgency,
        "uncertainty": uncertainty,
        "recency": recency,
    }
    weight_map = {
        "mastery_gap": weights.mastery_gap,
        "forgetting_risk": weights.forgetting_risk,
        "coverage_gap": weights.coverage_gap,
        "board_incidence": weights.board_incidence,
        "irt_information": weights.irt_information,
        "exam_urgency": weights.exam_urgency,
        "uncertainty": weights.uncertainty,
        "recency": weights.recency,
    }
    components = {key: signals[key] * weight_map[key] * 100.0 for key in signals}
    score = clamp(sum(components.values()) / 100.0) * 100.0

    labels = {
        "mastery_gap": "lacuna de domínio KT",
        "forgetting_risk": "risco de esquecimento FSRS",
        "coverage_gap": "cobertura do conteúdo",
        "board_incidence": "incidência observada da banca",
        "irt_information": "valor diagnóstico IRT",
        "exam_urgency": "proximidade da prova",
        "uncertainty": "necessidade de coletar evidência",
        "recency": "tempo sem contato",
    }
    reasons = [
        f"{labels[key]} (+{value:.0f})"
        for key, value in sorted(components.items(), key=lambda item: item[1], reverse=True)
        if value >= 2.0
    ][:4]
    if confidence < 0.34:
        reasons.insert(0, "evidência insuficiente: coletar diagnóstico")
        reasons = reasons[:4]
    if not reasons:
        reasons = ["prioridade equilibrada sem sinal dominante"]
    return RecommendationResult(
        score=round(score, 2),
        components={key: round(value, 2) for key, value in components.items()},
        signals={key: round(value, 4) for key, value in signals.items()},
        reasons=reasons,
        mode=str(mode or "equilibrado").strip().lower(),
    )


def wilson_interval(correct: int, total: int, *, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de Wilson para uma proporção binomial."""
    n = max(0, int(total))
    if n <= 0:
        return (0.20, 0.80)
    k = max(0, min(n, int(correct)))
    p = k / n
    z2 = z * z
    denominator = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denominator
    half = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n) / denominator
    return clamp(center - half), clamp(center + half)


def blended_projection(
    *,
    correct: int,
    attempts: int,
    mastery: float | None,
    mastery_confidence: float,
    theta_scale: float | None,
) -> dict:
    """Projeção conservadora, sempre acompanhada por intervalo de confiança.

    Não representa chance de aprovação. É uma estimativa de acerto no conteúdo
    disponível, combinando observação, KT e escala pessoal IRT.
    """
    n = max(0, int(attempts))
    observed = (max(0, min(n, int(correct))) / n) if n else 0.50
    kt = observed if mastery is None else clamp(mastery)
    theta = 0.50 if theta_scale is None else clamp(float(theta_scale) / 100.0)
    conf = clamp(mastery_confidence)

    # Quanto maior a amostra, mais a observação manda. KT cresce com confiança;
    # IRT permanece uma correção menor porque é calibração pessoal.
    observation_weight = min(0.58, 0.24 + math.log1p(n) / 18.0)
    kt_weight = 0.18 + 0.20 * conf
    irt_weight = max(0.10, 1.0 - observation_weight - kt_weight)
    total_weight = observation_weight + kt_weight + irt_weight
    estimate = (
        observed * observation_weight + kt * kt_weight + theta * irt_weight
    ) / total_weight

    low, high = wilson_interval(correct, n)
    # Centro do intervalo acompanha parcialmente o modelo combinado; amplitude
    # continua determinada principalmente pela amostra real.
    radius = max(0.06, (high - low) / 2.0)
    if n < 8:
        radius = max(radius, 0.18)
    elif n < 20:
        radius = max(radius, 0.12)
    projected_low = clamp(estimate - radius)
    projected_high = clamp(estimate + radius)
    return {
        "estimate": round(estimate, 4),
        "low": round(projected_low, 4),
        "high": round(projected_high, 4),
        "attempts": n,
        "confidence": "baixa" if n < 10 else ("moderada" if n < 30 else "boa"),
        "method": "observed+KT+personal_IRT",
    }


def diversity_adjusted_value(
    score: float,
    *,
    subject_count: int = 0,
    topic_count: int = 0,
    lesson_count: int = 0,
    board_count: int = 0,
    same_as_last_subject: bool = False,
    same_as_last_topic: bool = False,
) -> float:
    """MMR leve por metadados para evitar repetição excessiva."""
    value = float(score)
    value /= 1.0 + 0.20 * max(0, int(subject_count))
    value -= 8.0 * max(0, int(topic_count))
    value -= 4.0 * max(0, int(lesson_count))
    value -= 2.0 * max(0, int(board_count))
    if same_as_last_subject:
        value -= 13.0
    if same_as_last_topic:
        value -= 16.0
    return value


__all__ = [
    "MODEL_VERSION", "RecommendationWeights", "RecommendationResult",
    "MODE_WEIGHTS", "recommendation_weights", "multiobjective_priority",
    "wilson_interval", "blended_projection", "diversity_adjusted_value",
]
