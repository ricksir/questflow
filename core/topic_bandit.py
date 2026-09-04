from __future__ import annotations

"""Política contextual leve para equilibrar matérias e assuntos.

Não usa recompensa aleatória nem mecânicas de aposta. O objetivo é explorar
conteúdos pouco vistos e reforçar conteúdos com maior risco de erro, mantendo
rotação e diversidade.
"""

from dataclasses import dataclass
import math
import random
from typing import Iterable


BANDIT_VERSION = "qf-topic-ucb-1"


@dataclass(slots=True)
class TopicState:
    subject: str
    topic: str
    correct: int = 0
    wrong: int = 0
    exposures: int = 0
    last_seen_days: float = 999.0

    @property
    def attempts(self) -> int:
        return max(0, self.correct + self.wrong)

    @property
    def mastery(self) -> float:
        # Prior Beta(2,2): evita conclusões extremas com poucas respostas.
        return (self.correct + 2.0) / (self.attempts + 4.0)

    @property
    def uncertainty(self) -> float:
        return 1.0 / math.sqrt(self.attempts + 1.0)


def topic_priority(
    state: TopicState,
    *,
    total_exposures: int,
    coverage_gap: float = 0.0,
    predicted_recall: float = 0.5,
) -> float:
    """Pontuação UCB interpretável para um assunto."""

    exposures = max(0, int(state.exposures))
    total = max(1, int(total_exposures))
    exploration = math.sqrt(2.0 * math.log(total + 1.0) / (exposures + 1.0))
    weakness = 1.0 - state.mastery
    memory_risk = 1.0 - max(0.0, min(1.0, float(predicted_recall)))
    recency = 1.0 - math.exp(-max(0.0, state.last_seen_days) / 21.0)
    return (
        weakness * 52.0
        + memory_risk * 46.0
        + exploration * 22.0
        + recency * 18.0
        + max(0.0, min(1.0, coverage_gap)) * 34.0
    )


def rank_topics(
    states: Iterable[TopicState],
    *,
    total_exposures: int,
    seed: int,
) -> list[tuple[float, TopicState]]:
    rng = random.Random(int(seed))
    ranked = [
        (topic_priority(item, total_exposures=total_exposures) + rng.random() * 0.05, item)
        for item in states
    ]
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ranked


__all__ = ["BANDIT_VERSION", "TopicState", "topic_priority", "rank_topics"]
