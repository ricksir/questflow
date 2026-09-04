from __future__ import annotations

"""Métricas de calibração para o modelo adaptativo.

O modelo não deve ser otimizado automaticamente apenas porque sua acurácia
subiu. Estas métricas verificam se probabilidades previstas correspondem à
frequência real de acertos.
"""

from dataclasses import dataclass, asdict
import math
from typing import Iterable


def _clamp_probability(value: float) -> float:
    return max(1e-6, min(1.0 - 1e-6, float(value)))


def brier_score(predictions: Iterable[float], outcomes: Iterable[bool | int]) -> float:
    pairs = [(float(p), 1.0 if bool(y) else 0.0) for p, y in zip(predictions, outcomes)]
    if not pairs:
        return 0.0
    return sum((max(0.0, min(1.0, p)) - y) ** 2 for p, y in pairs) / len(pairs)


def log_loss(predictions: Iterable[float], outcomes: Iterable[bool | int]) -> float:
    pairs = [(_clamp_probability(p), 1.0 if bool(y) else 0.0) for p, y in zip(predictions, outcomes)]
    if not pairs:
        return 0.0
    return -sum(y * math.log(p) + (1.0 - y) * math.log(1.0 - p) for p, y in pairs) / len(pairs)


@dataclass(slots=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_prediction: float
    observed_accuracy: float

    @property
    def gap(self) -> float:
        return abs(self.mean_prediction - self.observed_accuracy)


@dataclass(slots=True)
class CalibrationReport:
    samples: int
    brier: float
    log_loss: float
    expected_calibration_error: float
    bins: list[CalibrationBin]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["bins"] = [asdict(item) | {"gap": item.gap} for item in self.bins]
        return payload


def calibration_report(
    predictions: Iterable[float],
    outcomes: Iterable[bool | int],
    *,
    bin_count: int = 10,
) -> CalibrationReport:
    pairs = [
        (max(0.0, min(1.0, float(p))), 1.0 if bool(y) else 0.0)
        for p, y in zip(predictions, outcomes)
    ]
    if not pairs:
        return CalibrationReport(0, 0.0, 0.0, 0.0, [])
    count = max(2, min(20, int(bin_count)))
    bins: list[CalibrationBin] = []
    for index in range(count):
        lower = index / count
        upper = (index + 1) / count
        selected = [
            pair for pair in pairs
            if lower <= pair[0] < upper or (index == count - 1 and pair[0] == 1.0)
        ]
        if not selected:
            continue
        mean_prediction = sum(item[0] for item in selected) / len(selected)
        observed = sum(item[1] for item in selected) / len(selected)
        bins.append(CalibrationBin(lower, upper, len(selected), mean_prediction, observed))
    total = len(pairs)
    ece = sum(item.gap * item.count / total for item in bins)
    predictions_list = [item[0] for item in pairs]
    outcomes_list = [item[1] for item in pairs]
    return CalibrationReport(
        samples=total,
        brier=brier_score(predictions_list, outcomes_list),
        log_loss=log_loss(predictions_list, outcomes_list),
        expected_calibration_error=ece,
        bins=bins,
    )
