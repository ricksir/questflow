from __future__ import annotations

"""Regras canônicas para os formatos de questão do QuestFlow.

A interface pode mudar o tipo de uma questão depois da importação. Este módulo
centraliza a conversão para impedir estados inconsistentes como
``tipo=certo_errado`` acompanhado de alternativas A-E.
"""

from copy import deepcopy
from typing import Iterable

MULTIPLE_CHOICE = "multipla_escolha"
TRUE_FALSE = "certo_errado"

_TRUE_FALSE_ALIASES = {
    "c": "C",
    "certo": "C",
    "correto": "C",
    "verdadeiro": "C",
    "true": "C",
    "v": "C",
    "e": "E",
    "errado": "E",
    "incorreto": "E",
    "falso": "E",
    "false": "E",
    "f": "E",
}


def normalize_question_type(value: object) -> str:
    text = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    if text in {"certo_errado", "certo/errado", "certo_/_errado", "true_false", "verdadeiro_falso"}:
        return TRUE_FALSE
    return MULTIPLE_CHOICE


def true_false_alternatives() -> list[dict[str, str]]:
    return [
        {"chave": "C", "texto": "Certo"},
        {"chave": "E", "texto": "Errado"},
    ]


def normalize_true_false_answer(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return _TRUE_FALSE_ALIASES.get(text.casefold(), "")


def normalize_alternatives(values: object) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    if not isinstance(values, list):
        return result
    for index, item in enumerate(values):
        if isinstance(item, dict):
            key = str(item.get("chave") or item.get("key") or chr(65 + index)).strip().upper()
            text = str(item.get("texto") or item.get("text") or "").strip()
        else:
            key = chr(65 + index)
            text = str(item).strip()
        if text:
            result.append({"chave": key or chr(65 + index), "texto": text})
    return result


def canonicalize_question_format(
    question_type: object,
    alternatives: object,
    answer: object,
    *,
    reject_invalid_true_false_answer: bool = False,
) -> tuple[str, list[dict[str, str]], str]:
    """Retorna tipo, alternativas e gabarito em um estado coerente.

    Para Certo/Errado, as únicas opções persistidas são C|Certo e E|Errado.
    Um gabarito antigo A-E nunca é reinterpretado silenciosamente como C/E.
    """

    normalized_type = normalize_question_type(question_type)
    if normalized_type == TRUE_FALSE:
        raw_answer = str(answer or "").strip()
        normalized_answer = normalize_true_false_answer(raw_answer)
        if raw_answer and not normalized_answer and reject_invalid_true_false_answer:
            raise ValueError("Para questões de Certo/Errado, o gabarito deve ser C (Certo) ou E (Errado).")
        return TRUE_FALSE, true_false_alternatives(), normalized_answer

    normalized_alternatives = normalize_alternatives(alternatives)
    normalized_answer = str(answer or "").strip().upper()
    return MULTIPLE_CHOICE, normalized_alternatives, normalized_answer


def snapshot_format(question: dict) -> dict:
    """Cópia enxuta do formato anterior para auditoria de conversões manuais."""

    return {
        "tipo": normalize_question_type(question.get("tipo")),
        "alternativas": deepcopy(question.get("alternativas", [])),
        "gabarito": str(question.get("gabarito", "") or ""),
    }
