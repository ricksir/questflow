from __future__ import annotations

"""Learning analytics do QuestFlow.

Este módulo concentra cálculos puros usados pelo dashboard e pelo motor de
prioridade por matéria. Mantê-los fora da camada de UI facilita calibração,
testes e futuras trocas de pesos sem alterar consultas ou componentes visuais.
"""

from dataclasses import dataclass
from math import exp, log
from typing import Iterable, Sequence


DASHBOARD_ANALYTICS_VERSION = "qf-learning-analytics-1"
DEFAULT_RECENT_WINDOW = 30
DEFAULT_PERFORMANCE_TARGET = 0.80
DEFAULT_COVERAGE_TARGET = 0.90


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def weighted_recent_accuracy(outcomes: Sequence[int | bool], *, decay: float = 0.94) -> float | None:
    """Média recente com maior peso para tentativas mais novas.

    ``outcomes`` deve vir em ordem cronológica (antiga -> nova). O decaimento
    exponencial impede que respostas muito antigas tenham o mesmo peso da
    evidência atual, sem descartar completamente o histórico recente.
    """
    if not outcomes:
        return None
    decay = clamp(decay, 0.50, 0.999)
    weighted = total = 0.0
    count = len(outcomes)
    for index, value in enumerate(outcomes):
        age = count - index - 1
        weight = decay ** age
        weighted += (1.0 if bool(value) else 0.0) * weight
        total += weight
    return weighted / total if total else None


def trend_delta(recent_outcomes: Sequence[int | bool], previous_outcomes: Sequence[int | bool]) -> float | None:
    """Diferença em pontos percentuais entre duas janelas comparáveis."""
    if not recent_outcomes or not previous_outcomes:
        return None
    recent = sum(bool(x) for x in recent_outcomes) / len(recent_outcomes)
    previous = sum(bool(x) for x in previous_outcomes) / len(previous_outcomes)
    return (recent - previous) * 100.0


def recency_risk(days_since_review: float | None, *, half_life_days: float = 10.0) -> float:
    """Converte dias sem revisão em risco 0..1.

    Sem histórico, o risco é máximo para uma matéria já estudada; a camada que
    chama esta função pode reduzir o peso para matérias fora do escopo estudado.
    """
    if days_since_review is None:
        return 1.0
    days = max(0.0, float(days_since_review))
    half_life = max(1.0, float(half_life_days))
    return clamp(1.0 - exp(-log(2.0) * days / half_life))


@dataclass(slots=True)
class PriorityResult:
    score: float
    label: str
    tone: str
    components: dict[str, float]
    reasons: list[str]


def subject_priority(
    *,
    retention: float | None,
    recent_accuracy: float | None,
    coverage: float | None,
    days_since_review: float | None,
    exam_urgency: float = 0.0,
    due_count: int = 0,
    attempts: int = 0,
    studied: bool = True,
    hard_ratio: float = 0.0,
    learning_gap_ratio: float = 0.0,
    performance_target: float = DEFAULT_PERFORMANCE_TARGET,
) -> PriorityResult:
    """Índice explicável de prioridade por matéria (0..100).

    Pesos seguem o plano aprovado: risco de esquecimento, desempenho atual,
    cobertura, recência e proximidade da prova. Sinais metacognitivos não criam
    uma sexta dimensão opaca; eles refinam o déficit de desempenho atual.
    """
    target = clamp(performance_target, 0.55, 0.98)

    # Retenção desconhecida não é tratada como fracasso. Se já há respostas,
    # usamos o desempenho como proxy conservadora; em cold start usamos 0,50.
    effective_retention = retention
    if effective_retention is None:
        effective_retention = recent_accuracy if recent_accuracy is not None else 0.50
    retention_risk = 1.0 - clamp(effective_retention)

    if recent_accuracy is None:
        performance_deficit = 0.45 if studied else 0.20
    else:
        performance_deficit = clamp((target - clamp(recent_accuracy)) / target)
        # Acertos percebidos como difíceis ou com lacuna declarada são evidência
        # menos confortável que o percentual bruto sugere.
        meta_penalty = 0.12 * clamp(hard_ratio) + 0.20 * clamp(learning_gap_ratio)
        performance_deficit = clamp(performance_deficit + meta_penalty)

    if coverage is None:
        coverage_gap = 0.55 if studied else 0.25
    else:
        coverage_gap = 1.0 - clamp(coverage)

    recency = recency_risk(days_since_review)
    if not studied and attempts == 0:
        recency *= 0.35

    # Vencidas aumentam o risco de retenção, mas sem permitir que volume bruto
    # domine sozinho o ranking.
    due_pressure = clamp(int(due_count) / 20.0)
    retention_risk = clamp(retention_risk * 0.80 + due_pressure * 0.20)

    components = {
        "retention": retention_risk * 35.0,
        "performance": performance_deficit * 25.0,
        "coverage": coverage_gap * 20.0,
        "recency": recency * 10.0,
        "exam": clamp(exam_urgency) * 10.0,
    }
    score = clamp(sum(components.values()) / 100.0) * 100.0

    if score >= 40:
        label, tone = "Alta", "danger"
    elif score >= 20:
        label, tone = "Média", "warning"
    else:
        label, tone = "Baixa", "success"

    reasons: list[str] = []
    ranked = sorted(components.items(), key=lambda item: item[1], reverse=True)
    label_map = {
        "retention": "risco de esquecimento",
        "performance": "desempenho recente",
        "coverage": "cobertura ainda incompleta",
        "recency": "tempo sem revisar",
        "exam": "proximidade da prova",
    }
    for key, value in ranked:
        if value >= 4.0:
            reasons.append(f"{label_map[key]} (+{value:.0f})")
        if len(reasons) >= 3:
            break
    if not reasons:
        reasons.append("estado geral estável")

    return PriorityResult(
        score=round(score, 1),
        label=label,
        tone=tone,
        components={key: round(value, 2) for key, value in components.items()},
        reasons=reasons,
    )


def exam_urgency(days_to_exam: int | None) -> float:
    if days_to_exam is None:
        return 0.0
    days = max(0, int(days_to_exam))
    if days <= 7:
        return 1.0
    if days >= 180:
        return 0.0
    return clamp((180.0 - days) / 173.0)


def sample_confidence(attempts: int) -> str:
    count = max(0, int(attempts))
    if count == 0:
        return "sem_amostra"
    if count < 10:
        return "baixa"
    if count < 30:
        return "moderada"
    return "boa"


__all__ = [
    "DASHBOARD_ANALYTICS_VERSION",
    "DEFAULT_COVERAGE_TARGET",
    "DEFAULT_PERFORMANCE_TARGET",
    "DEFAULT_RECENT_WINDOW",
    "PriorityResult",
    "clamp",
    "exam_urgency",
    "recency_risk",
    "sample_confidence",
    "subject_priority",
    "trend_delta",
    "weighted_recent_accuracy",
]
