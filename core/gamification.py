from __future__ import annotations

"""Gamificação educativa, transparente e não compulsiva.

O módulo não cria caixas-surpresa, moedas compráveis, rankings públicos ou
punições por ausência. A pontuação serve apenas como feedback de progresso.
"""

from dataclasses import dataclass
import math


GAME_ENGINE_VERSION = "qf-learning-game-1"


@dataclass(slots=True)
class Reward:
    xp: int
    level: int
    level_progress: float
    title: str
    rationale: str


def level_from_xp(total_xp: int) -> tuple[int, float]:
    xp = max(0, int(total_xp))
    # Curva sublinear: níveis continuam alcançáveis sem inflar recompensas.
    level = int(math.floor(math.sqrt(xp / 75.0))) + 1
    previous = 75 * (level - 1) ** 2
    next_threshold = 75 * level ** 2
    progress = 0.0 if next_threshold <= previous else (xp - previous) / (next_threshold - previous)
    return max(1, level), max(0.0, min(1.0, progress))


def calculate_reward(
    *,
    correct: bool,
    difficulty: float,
    response_seconds: float,
    streak: int,
    first_attempt: bool,
    total_xp_before: int,
) -> Reward:
    difficulty = max(1.0, min(10.0, float(difficulty or 5.0)))
    response = max(0.0, float(response_seconds or 0.0))
    streak = max(0, int(streak or 0))
    base = 14 if correct else 4
    challenge = int(round((difficulty - 1.0) * (0.85 if correct else 0.25)))
    streak_bonus = min(10, streak // 3) if correct else 0
    first_bonus = 3 if first_attempt and correct else 0
    speed_bonus = 2 if correct and 0 < response <= 20 else 0
    xp = max(1, base + challenge + streak_bonus + first_bonus + speed_bonus)
    total = max(0, int(total_xp_before)) + xp
    level, progress = level_from_xp(total)
    if correct:
        title = "Órbita estabilizada" if streak >= 5 else "Missão cumprida"
        rationale = "Acerto registrado; dificuldade e consistência consideradas."
    else:
        title = "Telemetria recebida"
        rationale = "O erro virou sinal para uma revisão mais próxima."
    return Reward(xp=xp, level=level, level_progress=progress, title=title, rationale=rationale)


__all__ = ["GAME_ENGINE_VERSION", "Reward", "calculate_reward", "level_from_xp"]
