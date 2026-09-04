from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .spreadsheet_taxonomy import SpreadsheetTaxonomy
from .markdown_pipeline import MarkdownBundle, build_markdown_bundle

import cv2
import pymupdf
import numpy as np
import pytesseract
from PIL import Image

ProgressCallback = Callable[[float, str], None]


class ExtractionCancelled(RuntimeError):
    pass


@dataclass(slots=True)
class ExtractorConfig:
    dpi: int = 180
    languages: str = "por+eng"
    platform: str = "QConcursos"
    tesseract_cmd: str = ""


@dataclass(slots=True)
class PageAnalysis:
    index: int
    image: Image.Image
    width: int
    height: int
    offset: int
    lines: list[dict]
    horizontal_rules: list[int]
    option_circles: list[tuple[int, int, int]]


def configure_tesseract(explicit_path: str = "") -> str:
    candidates = [
        explicit_path,
        os.environ.get("TESSERACT_CMD", ""),
        shutil.which("tesseract") or "",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return str(candidate)
    raise FileNotFoundError(
        "Tesseract OCR não foi encontrado. Instale-o ou informe o caminho nas Configurações."
    )


def _check_cancel(cancel_event) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise ExtractionCancelled("Extração cancelada pelo usuário.")


def _progress(callback: ProgressCallback | None, value: float, message: str) -> None:
    if callback:
        callback(max(0.0, min(1.0, value)), message)


def _render_page(page: pymupdf.Page, dpi: int) -> Image.Image:
    pix = page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def _ocr_lines(image: Image.Image, languages: str) -> list[dict]:
    data = pytesseract.image_to_data(
        image,
        lang=languages,
        config="--psm 6",
        output_type=pytesseract.Output.DICT,
    )
    grouped: dict[tuple[int, int, int], list[dict]] = {}
    count = len(data.get("text", []))
    for i in range(count):
        text = str(data["text"][i]).strip()
        try:
            confidence = float(data["conf"][i])
        except (ValueError, TypeError):
            confidence = -1.0
        if not text or confidence < 0:
            continue
        key = (
            int(data["block_num"][i]),
            int(data["par_num"][i]),
            int(data["line_num"][i]),
        )
        grouped.setdefault(key, []).append(
            {
                "x": int(data["left"][i]),
                "y": int(data["top"][i]),
                "w": int(data["width"][i]),
                "h": int(data["height"][i]),
                "text": text,
                "confidence": confidence,
            }
        )

    lines: list[dict] = []
    for words in grouped.values():
        words.sort(key=lambda item: item["x"])
        text = " ".join(item["text"] for item in words).strip()
        if not text:
            continue
        y = min(item["y"] for item in words)
        x = min(item["x"] for item in words)
        bottom = max(item["y"] + item["h"] for item in words)
        lines.append(
            {
                "y": y,
                "x": x,
                "h": bottom - y,
                "text": text,
                "words": words,
            }
        )
    lines.sort(key=lambda item: (item["y"], item["x"]))
    return lines


def _detect_horizontal_rules(image: Image.Image) -> list[int]:
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    binary = cv2.threshold(gray, 248, 255, cv2.THRESH_BINARY_INV)[1]
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(80, image.width // 3), 1)
    )
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    counts = (horizontal > 0).sum(axis=1)
    rows = np.where(counts > image.width * 0.45)[0]
    groups: list[list[int]] = []
    for row in rows:
        y = int(row)
        if not groups or y - groups[-1][-1] > 2:
            groups.append([y])
        else:
            groups[-1].append(y)
    return [round(sum(group) / len(group)) for group in groups]


def _ring_quality(gray: np.ndarray, x: int, y: int, radius: int) -> float:
    best = 0.0
    for measured_radius in range(max(5, radius - 3), radius + 2):
        hits = 0
        total = 72
        for sample in range(total):
            angle = 2 * math.pi * sample / total
            xx = int(round(x + measured_radius * math.cos(angle)))
            yy = int(round(y + measured_radius * math.sin(angle)))
            if (
                0 <= yy < gray.shape[0]
                and 0 <= xx < gray.shape[1]
                and gray[yy, xx] < 185
            ):
                hits += 1
        best = max(best, hits / total)
    return best


def _detect_option_circles(image: Image.Image, dpi: int) -> list[tuple[int, int, int]]:
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    left_limit = min(gray.shape[1], int(210 * dpi / 180))
    crop = cv2.medianBlur(gray[:, :left_limit], 5)
    circles = cv2.HoughCircles(
        crop,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(25, int(35 * dpi / 180)),
        param1=80,
        param2=17,
        minRadius=max(6, int(8 * dpi / 180)),
        maxRadius=max(12, int(18 * dpi / 180)),
    )
    accepted: list[tuple[int, int, int]] = []
    if circles is not None:
        for x, y, radius in np.round(circles[0]).astype(int):
            if not (
                int(105 * dpi / 180) <= x <= int(150 * dpi / 180)
                and radius >= int(12 * dpi / 180)
            ):
                continue
            if _ring_quality(gray, int(x), int(y), int(radius)) >= 0.55:
                accepted.append((int(x), int(y), int(radius)))

    accepted.sort(key=lambda item: item[1])
    deduplicated: list[tuple[int, int, int]] = []
    for circle in accepted:
        if not deduplicated or abs(circle[1] - deduplicated[-1][1]) > int(
            13 * dpi / 180
        ):
            deduplicated.append(circle)
        elif circle[2] > deduplicated[-1][2]:
            deduplicated[-1] = circle
    return deduplicated


def _clean_text(text: str) -> str:
    text = text.replace("\x0c", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([,.;:?!])", r"\1", text)


def _clean_option(text: str) -> str:
    text = _clean_text(text)
    text = re.sub(
        r"^(?:[©®@]+|[O0][.)]|\([O0A-E]\)|[A-E][.)])\s*", "", text
    )
    return text.strip(" -")


def _normalize_board(board: str) -> str:
    board = _clean_text(board)
    return re.sub(r"\s*/\s*", " / ", board)


def _parse_metadata(lines: Iterable[dict]) -> tuple[int | None, str, str, str, str]:
    raw = _clean_text(" ".join(line["text"] for line in lines))
    year: int | None = None
    board = agency = exam = ""

    match = re.search(r"Ano\s*:\s*(\d{4})", raw, re.I)
    if match:
        year = int(match.group(1))

    # In browser-printed PDFs the labels that share one visual row can be emitted
    # in a slightly different Y order (e.g. Órgão before Banca).  Parse each field
    # independently and stop at the next metadata label instead of assuming one
    # fixed sequence.
    boundary = r"(?=\s+(?:Ano|Banca|Órgão|Orgao|Prova(?:s)?)\s*:|$)"
    match = re.search(r"Banca\s*:\s*(.*?)" + boundary, raw, re.I)
    if match:
        board = _normalize_board(match.group(1))
    match = re.search(r"(?:Órgão|Orgao)\s*:\s*(.*?)" + boundary, raw, re.I)
    if match:
        agency = _clean_text(match.group(1))
    match = re.search(r"Prova(?:s)?\s*:\s*(.*?)" + boundary, raw, re.I)
    if match:
        exam = _clean_text(match.group(1))
    return year, board, agency, exam, raw


def _classification(category: str) -> tuple[str, list[str], list[str]]:
    """Extract the source discipline/topic hierarchy before spreadsheet mapping."""
    category = _clean_text(category)
    if ">" in category:
        matter, rest = category.split(">", 1)
    else:
        matter, rest = "", category
    matter = _clean_text(matter)
    parts = [
        _clean_text(part)
        for part in re.split(r"\s*,\s*", rest)
        if _clean_text(part)
    ]
    if parts and matter and parts[0].lower() == matter.lower():
        parts = parts[1:]
    subjects: list[str] = []
    for part in parts:
        if part.lower() not in {item.lower() for item in subjects}:
            subjects.append(part)
    if not matter and subjects:
        matter = subjects.pop(0)
    return matter, subjects, [item for item in [matter, *subjects] if item]


def _derive_exam_fields(exam: str) -> tuple[str, str, str, str]:
    role = area = specialty = shift = ""
    match = re.search(r"(?:Área|Area)\s*[:\-]\s*([^\-]+)", exam, re.I)
    if match:
        area = _clean_text(match.group(1))
    match = re.search(r"Especialidade\s*:\s*([^\-]+)", exam, re.I)
    if match:
        specialty = _clean_text(match.group(1))
    if re.search(r"\bManhã\b", exam, re.I):
        shift = "Manhã"
    elif re.search(r"\bTarde\b", exam, re.I):
        shift = "Tarde"
    parts = [_clean_text(part) for part in exam.split(" - ") if _clean_text(part)]
    if len(parts) >= 4:
        role = parts[-1]
    return role, area, specialty, shift


def _fingerprint(question: dict) -> str:
    pieces = [question.get("materia", ""), question.get("enunciado", "")]
    pieces.extend(item.get("texto", "") for item in question.get("alternativas", []))
    normalized = unicodedata.normalize("NFKD", "|".join(pieces))
    normalized = normalized.encode("ascii", "ignore").decode().lower()
    normalized = re.sub(r"\W+", "", normalized)
    return hashlib.sha256(normalized.encode()).hexdigest()


def _header_identity(previous_lines: list[dict], inferred_number: int) -> tuple[int, str]:
    text = " ".join(line["text"] for line in previous_lines)
    candidates = list(re.finditer(r"(?:Q|O|0)\s*(\d{5,8})\b", text, re.I))
    source_code = f"Q{candidates[-1].group(1)}" if candidates else ""

    number: int | None = None
    for line in reversed(previous_lines):
        text_line = line["text"]
        match = re.match(r"^\s*(\d{1,3})\b", text_line)
        if match and (
            re.search(r"(?:Q|O|0)\s*\d{5,8}\b", text_line, re.I)
            or re.search(r">", text_line)
        ):
            number = int(match.group(1))
            break
    if number is None:
        number = inferred_number
    if not source_code:
        source_code = f"QFLOW-{number:04d}"
    return number, source_code


def _answer_key(
    page_image: Image.Image,
    marker_y: int,
    dpi: int,
    languages: str = "por+eng",
) -> tuple[dict[int, str], str]:
    """Read the compact answer table at the end of QConcursos PDFs.

    The answer table uses small, thin glyphs. A whitelist-only OCR pass can merge
    whole lines, so we combine normal, thresholded and restricted OCR results.
    """
    crop = page_image.crop(
        (
            int(30 * dpi / 180),
            max(0, marker_y - int(12 * dpi / 180)),
            page_image.width - int(20 * dpi / 180),
            page_image.height - int(20 * dpi / 180),
        )
    )
    gray = cv2.cvtColor(np.array(crop), cv2.COLOR_RGB2GRAY)
    enlarged = cv2.resize(gray, None, fx=1.6, fy=1.6, interpolation=cv2.INTER_CUBIC)
    thresholded = cv2.threshold(enlarged, 210, 255, cv2.THRESH_BINARY)[1]

    passes = [
        pytesseract.image_to_string(crop, lang=languages, config="--psm 6"),
        pytesseract.image_to_string(
            Image.fromarray(thresholded), lang=languages, config="--psm 6"
        ),
        pytesseract.image_to_string(
            Image.fromarray(thresholded),
            lang="eng",
            config="--psm 6 -c tessedit_char_whitelist=0123456789:ABCDE",
        ),
    ]
    answers: dict[int, str] = {}
    normalized_passes: list[str] = []
    for raw in passes:
        normalized = (
            raw.upper()
            .replace("€", "C")
            .replace("©", "C")
            .replace("Ç", "C")
            .replace("¢", "C")
            .replace("|", "I")
        )
        normalized_passes.append(_clean_text(normalized))
        for number, value in re.findall(
            r"(?<!\d)(\d{1,3})\s*[:;,.\-]?\s*"
            r"(?:LETRA\s*)?(CORRETO|CERTO|VERDADEIRO|ERRADO|INCORRETO|FALSO|ANULADA|[A-H])"
            r"(?=\s|$|\d)",
            normalized,
        ):
            answers.setdefault(int(number), _normalize_answer_value(value))

    return answers, " || ".join(normalized_passes)




def _align_answers_to_questions(
    raw_answers: dict[int, str], starts: list[dict]
) -> dict[int, str]:
    """Align an answer table to visible question numbers.

    Most PDFs use the same numbering in the question header and answer table. Some
    QConcursos exports preserve the original caderno numbering in the answer box,
    while the displayed questions are renumbered in a larger combined list. In that
    case, a consecutive answer sequence is associated by visual order.
    """
    question_numbers = [int(item["number"]) for item in starts]
    direct = {
        number: raw_answers[number]
        for number in question_numbers
        if number in raw_answers
    }
    if len(direct) == len(question_numbers):
        return direct

    sorted_keys = sorted(number for number in raw_answers if 0 < number < 500)
    runs: list[list[int]] = []
    for number in sorted_keys:
        if not runs or number != runs[-1][-1] + 1:
            runs.append([number])
        else:
            runs[-1].append(number)
    runs.sort(key=lambda run: (len(run), -run[0]), reverse=True)
    if runs and len(runs[0]) >= len(question_numbers):
        run = runs[0][: len(question_numbers)]
        return {
            question_number: raw_answers[answer_number]
            for question_number, answer_number in zip(question_numbers, run)
        }

    # Preserve any direct matches when the answer key is incomplete, so the review
    # screen can clearly flag only the missing entries.
    return direct


def _word_text_right_of(line: dict, x_cut: int) -> str:
    words = [word["text"] for word in line.get("words", []) if word["x"] >= x_cut]
    if words:
        return " ".join(words)
    if line["x"] >= x_cut:
        return line["text"]
    return ""



_TRUE_FALSE_HINT_RE = re.compile(
    r"\b(?:julgue|certo\s+ou\s+errado|verdadeiro\s+ou\s+falso|item\s+(?:a\s+seguir|subsequente)|assinale\s+certo|assinale\s+errado)\b",
    re.I,
)
_INLINE_OPTION_RE = re.compile(
    r"(?is)(?:^|\n|\s{2,})(?:\(([A-H])\)|([A-H])\s*[.)-])\s+"
)


def _normalize_answer_value(value: object) -> str:
    raw = _clean_text(str(value or "")).upper()
    raw_ascii = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    raw_ascii = re.sub(r"\b(?:LETRA|ALTERNATIVA|OPCAO|RESPOSTA|GABARITO)\b", " ", raw_ascii)
    raw_ascii = _clean_text(raw_ascii)
    if re.search(r"\b(?:CORRETO|CERTO|VERDADEIRO|V)\b", raw_ascii):
        return "C"
    if re.search(r"\b(?:ERRADO|INCORRETO|FALSO|F)\b", raw_ascii):
        return "E"
    if re.search(r"\bANULAD[AO]\b", raw_ascii):
        return "ANULADA"
    match = re.search(r"\b([A-H])\b", raw_ascii)
    return match.group(1) if match else raw_ascii[:12]


def _extract_options_from_text(value: str) -> tuple[str, list[dict]]:
    text = str(value or "").replace("\r", "\n")
    matches = list(_INLINE_OPTION_RE.finditer(text))
    # PDFs textuais e OCRs às vezes juntam várias alternativas na mesma linha.
    # Use a leitura compacta sempre que ela encontrar mais marcadores do que a
    # versão orientada por quebras de linha.
    compact_pattern = re.compile(r"(?i)(?<![A-Za-z0-9])(?:\(([A-H])\)|([A-H])\s*[.)])\s*")
    compact_matches = list(compact_pattern.finditer(text))
    if len(compact_matches) > len(matches):
        matches = compact_matches
    if len(matches) < 2:
        return _clean_text(text), []
    statement = _clean_text(text[: matches[0].start()])
    alternatives: list[dict] = []
    seen: set[str] = set()
    for index, match in enumerate(matches[:8]):
        key = (match.group(1) or match.group(2) or "").upper()
        if not key or key in seen:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        option_text = _clean_option(text[match.end() : end])
        if option_text:
            alternatives.append({"chave": key, "texto": option_text})
            seen.add(key)
    return statement, alternatives


def _core_question_complete(question: dict) -> bool:
    statement = _clean_text(str(question.get("enunciado", "")))
    alternatives = list(question.get("alternativas", []))
    answer = str(question.get("gabarito", "")).upper()
    keys = [str(item.get("chave", "")).upper() for item in alternatives]
    if len(statement) < 18:
        return False
    if not 2 <= len(alternatives) <= 12:
        return False
    if len(set(keys)) != len(keys) or any(not key for key in keys):
        return False
    if any(len(_clean_text(str(item.get("texto", "")))) < 1 for item in alternatives):
        return False
    if answer not in keys:
        return False
    visual = question.get("contexto_visual", {}) if isinstance(question.get("contexto_visual"), dict) else {}
    if visual.get("necessario"):
        image_info = question.get("imagem_questao", {}) if isinstance(question.get("imagem_questao"), dict) else {}
        image_path = str(image_info.get("path", "")).strip()
        if not image_path or not Path(image_path).exists():
            return False
    return True


def deep_repair_question(
    question: dict,
    taxonomy: SpreadsheetTaxonomy | None = None,
    *,
    allow_auto_approve: bool = True,
    method: str = "analise_apurada",
) -> dict:
    """Repara questões incompletas e normaliza Certo/Errado e múltipla escolha.

    A aprovação automática só ocorre quando enunciado, alternativas, gabarito e
    eventual imagem obrigatória estão coerentes entre si.
    """
    repaired = json.loads(json.dumps(question, ensure_ascii=False))
    statement = _clean_text(str(repaired.get("enunciado", "")))
    answer = _normalize_answer_value(repaired.get("gabarito", ""))
    repaired["gabarito"] = answer

    alternatives: list[dict] = []
    for index, item in enumerate(repaired.get("alternativas", []) or []):
        if isinstance(item, dict):
            key = _clean_text(str(item.get("chave", ""))).upper()
            text_value = _clean_option(str(item.get("texto", "")))
        else:
            key = chr(65 + index)
            text_value = _clean_option(str(item))
        if key and text_value:
            alternatives.append({"chave": key, "texto": text_value})

    # Algumas extrações colocam as alternativas junto com o enunciado.
    parsed_statement, parsed_alternatives = _extract_options_from_text(statement)
    if len(alternatives) < 2 and len(parsed_alternatives) >= 2:
        statement = parsed_statement
        alternatives = parsed_alternatives

    # Também tenta os textos brutos preservados pelo extrator.
    raw_sources = []
    ocr = repaired.get("ocr", {}) if isinstance(repaired.get("ocr"), dict) else {}
    for key in ("texto_bruto", "bloco_bruto", "conteudo_bruto", "metadados_brutos"):
        if ocr.get(key):
            raw_sources.append(str(ocr.get(key)))
    if len(alternatives) < 2 and raw_sources:
        raw_statement, raw_alternatives = _extract_options_from_text("\n".join(raw_sources))
        if len(raw_alternatives) >= 2:
            if len(statement) < 18:
                statement = raw_statement
            alternatives = raw_alternatives

    current_type = str(repaired.get("tipo", "")).strip().lower()
    is_true_false = bool(
        current_type == "certo_errado"
        or (
            len(alternatives) < 3
            and _TRUE_FALSE_HINT_RE.search(statement)
        )
        or (
            len(alternatives) == 2
            and {str(item.get("texto", "")).strip().lower() for item in alternatives}
            & {"certo", "errado", "verdadeiro", "falso"}
        )
    )
    if is_true_false:
        alternatives = [
            {"chave": "C", "texto": "Certo"},
            {"chave": "E", "texto": "Errado"},
        ]
        repaired["tipo"] = "certo_errado"
    elif len(alternatives) >= 2:
        repaired["tipo"] = "multipla_escolha"

    # Corrige chaves sequenciais quando o OCR confundiu símbolos.
    if alternatives and not is_true_false:
        expected = list("ABCDEFGH")[: len(alternatives)]
        keys = [str(item.get("chave", "")).upper() for item in alternatives]
        if len(set(keys)) != len(keys) or any(key not in "ABCDEFGH" for key in keys):
            for item, key in zip(alternatives, expected):
                item["chave"] = key

    repaired["enunciado"] = statement
    repaired["alternativas"] = alternatives
    keys = [str(item.get("chave", "")).upper() for item in alternatives]
    correct_index = keys.index(answer) if answer in keys else None
    repaired["telegram"] = {
        "modo": "quiz",
        "pergunta": statement,
        "opcoes": [str(item.get("texto", "")) for item in alternatives],
        "indice_correto": correct_index,
    }

    if taxonomy is not None and (
        not repaired.get("materia")
        or not repaired.get("assunto")
        or repaired.get("classificacao_planilha", {}).get("status") == "revisar"
    ):
        taxonomy.apply_to_question(repaired)

    confidence, alerts = _question_status(repaired)
    if answer == "ANULADA":
        alerts.append("Questão anulada: não pode ser enviada como quiz comum")
        confidence = min(confidence, 0.55)
    classification = repaired.get("classificacao_planilha", {}) if isinstance(repaired.get("classificacao_planilha"), dict) else {}
    if classification.get("status") == "revisar":
        alerts.append("Classificação da planilha precisa de revisão")
        confidence = max(0.0, confidence - 0.05)

    complete = _core_question_complete(repaired)
    review = repaired.setdefault("revisao", {})
    existing_alerts = [
        str(item) for item in review.get("alertas", [])
        if str(item) and not str(item).startswith("Processamento apurado")
    ]
    merged_alerts = []
    for item in [*alerts, *existing_alerts]:
        if item not in merged_alerts:
            merged_alerts.append(item)
    if complete and allow_auto_approve and confidence >= 0.88 and classification.get("status") != "revisar":
        status = "aprovado_automaticamente"
        merged_alerts = []
        confidence = max(confidence, 0.95)
    else:
        status = "pendente"
        if not complete:
            merged_alerts.insert(0, "Processamento apurado ainda encontrou dados incompletos")
    review.update({
        "status": status,
        "confianca": round(float(confidence), 2),
        "alertas": merged_alerts,
    })
    repaired["processamento_apurado"] = {
        "metodo": method,
        "completo": complete,
        "autoaprovado": status == "aprovado_automaticamente",
    }
    repaired["fingerprint"] = _fingerprint(repaired)
    return repaired


def _question_status(question: dict) -> tuple[float, list[str]]:
    score = 1.0
    alerts: list[str] = []
    if question.get("ano") is None:
        score -= 0.12
        alerts.append("Ano não reconhecido")
    if not question.get("banca"):
        score -= 0.10
        alerts.append("Banca não reconhecida")
    if not question.get("orgao"):
        score -= 0.08
        alerts.append("Órgão não reconhecido")
    if not question.get("enunciado"):
        score -= 0.25
        alerts.append("Enunciado vazio")
    alternative_count = len(question.get("alternativas", []))
    if not 2 <= alternative_count <= 12:
        score -= 0.25
        alerts.append(f"{alternative_count} alternativas detectadas")
    answer = question.get("gabarito", "")
    keys = [item.get("chave") for item in question.get("alternativas", [])]
    if not answer:
        score -= 0.20
        alerts.append("Gabarito não reconhecido")
    elif answer not in keys:
        score -= 0.20
        alerts.append("Gabarito fora das alternativas detectadas")
    if any(not item.get("texto", "").strip() for item in question.get("alternativas", [])):
        score -= 0.15
        alerts.append("Alternativa vazia")
    return round(max(0.0, score), 2), alerts



_NATIVE_QUESTION_RE = re.compile(
    # pymupdf4llm preserves headings/highlights around the question number,
    # producing lines such as ``**1. (...)`` and ``**<mark>1. (...)``.
    # Accept only presentation decorators before the numeric marker; the
    # mandatory parenthesized exam metadata keeps ordinary numbered prose out.
    r"(?m)^\s*(?:(?:[*_~#>-]+|</?[A-Za-z][^>\n]*>)\s*)*"
    r"(\d{1,3})\s*[.)]\s*\(\s*([^\)\n]+?)\s*\)\s*"
)
_NATIVE_OPTION_RE = re.compile(
    r"(?mi)^\s*(?:\(([A-E])\)|([A-E])\s*[.)])\s+"
)
_COMMENTED_BOOK_SIGNATURE_RE = re.compile(
    r"(?:RESOLVIDAS\s+E\s+COMENTADAS|Q\s*UEST(?:ÕES|OES)\s+C\s*OMENTADAS)",
    re.I,
)
_NATIVE_COMMENT_MARKER_RE = re.compile(
    r"(?mi)^\s*(?:(?:[*_>#-]+|</?[A-Za-z][^>\n]*>)\s*)*"
    r"Coment\S*?rios\s*:?\s*(?:[*_]+)?\s*$"
)


def _native_clean_page_text(text: str) -> str:
    """Remove cabeçalhos e rodapés recorrentes sem apagar o conteúdo das questões."""
    text = (
        text.replace("\u00ad", "")
        .replace("\ufffe", "-")
        .replace("\ufeff", "")
        .replace("\r", "\n")
    )
    output: list[str] = []
    skip_patterns = [
        r"^Diego Carvalho(?:,|$)",
        r"^Equipe Informática e TI(?:,|$)",
        r"^Luciano Rosa,\s*Júlio Cardozo\s+Aula\s+\d{1,2}",
        r"^Aula\s+\d{1,2}\s*-\s*Prof\.",
        r"^Aula\s+\d{1,2}\s*$",
        r"^Guilherme Sant['’]Anna,\s*Tonyvan de Carvalho Oliveira$",
        r"^Concursos da Área Fiscal\b",
        r"^www\.estrategiaconcursos\.com\.br\b",
        r"^\d{8,}\s*-\s*.+$",
        r"^==[A-Za-z0-9]+==$",
    ]
    for raw_line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        line = re.sub(r"^<!--\s*page:\d+\s*-->\s*", "", line, flags=re.I)
        if not line:
            output.append("")
            continue
        if re.fullmatch(r"\d{1,3}", line):
            # Paginação impressa, como 147 / 154.
            continue
        match_line = re.sub(r"</?[A-Za-z][^>\n]*>", "", line)
        match_line = re.sub(r"^[*_#>~\s-]+", "", match_line).strip()
        if any(re.search(pattern, match_line, re.I) for pattern in skip_patterns):
            continue
        output.append(line)
    cleaned = "\n".join(output)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _native_plain_markdown(text: str) -> str:
    """Remove presentation markup after the Markdown structure was consumed."""
    value = str(text or "")
    value = re.sub(r"<!--.*?-->", " ", value, flags=re.S)
    value = re.sub(r"!\[([^\]]*)\]\([^\)]+\)", r" \1 ", value)
    value = re.sub(r"</?(?:mark|u|br)\b[^>]*>", " ", value, flags=re.I)
    value = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", value)
    value = value.replace("**", "").replace("__", "").replace("`", "")
    return _clean_text(value)


def _native_trim_post_answer(text: str) -> str:
    """Drop the lead-in of the next question without truncating the commentary."""
    boundary = re.search(
        r"(?mi)^\s*(?:No\s+que\s+diz\s+respeito|Em\s+rela[çc][aã]o|"
        r"Com\s+rela[çc][aã]o|Julgue\b|A\s+respeito|Acerca\s+d[eo]|"
        r"Considerando\b|No\s+tocante)\b",
        str(text or ""),
    )
    return str(text or "")[: boundary.start()] if boundary else str(text or "")


def _native_page_for_offset(page_starts: list[int], offset: int) -> int:
    page_index = 0
    for index, start in enumerate(page_starts):
        if start > offset:
            break
        page_index = index
    return page_index


def _native_answer_key(text: str) -> tuple[dict[int, str], str]:
    normalized = unicodedata.normalize("NFKD", text)
    normalized = normalized.encode("ascii", "ignore").decode("ascii").upper()
    answers: dict[int, str] = {}
    pattern = re.compile(
        r"(?m)^\s*(\d{1,3})\s*[.)-]\s*(?:LETRA\s*)?(CORRETO|CERTO|ERRADO|[A-E])\b"
    )
    for match in pattern.finditer(normalized):
        number = int(match.group(1))
        value = match.group(2)
        if value in {"CORRETO", "CERTO", "VERDADEIRO"}:
            value = "C"
        elif value in {"ERRADO", "INCORRETO", "FALSO"}:
            value = "E"
        answers[number] = value
    return answers, _clean_text(normalized)


def _native_inline_answer(line: str) -> str:
    """Read inline answers even when OCR changes quotes, accents or punctuation."""
    normalized = unicodedata.normalize("NFKD", str(line or ""))
    normalized = normalized.encode("ascii", "ignore").decode("ascii").upper()
    normalized = _clean_text(normalized)
    if "GABARITO" not in normalized:
        return ""
    tail = normalized.split("GABARITO", 1)[1]
    letter = re.search(r"\bLETRA\s*([A-H])\b", tail)
    if letter:
        return letter.group(1)
    if re.search(r"\b(?:ERRADO|INCORRETO|FALSO)\b", tail):
        return "E"
    if re.search(r"\b(?:CORRETO|CERTO|VERDADEIRO)\b", tail):
        return "C"
    candidates = re.findall(r"\b([A-H])\b", tail)
    return candidates[-1] if candidates else ""


def _native_metadata(raw_header: str) -> tuple[int | None, str, str, str]:
    header = _clean_text(raw_header.replace("–", "-").replace("—", "-"))
    years = re.findall(r"\b(?:19|20)\d{2}\b", header)
    year = int(years[-1]) if years else None
    without_year = re.sub(r"\s*[-–—]?\s*\b(?:19|20)\d{2}\b\s*$", "", header).strip()
    parts = [_clean_text(part) for part in re.split(r"\s*/\s*", without_year) if _clean_text(part)]
    board = parts[0] if parts else ""
    agency = " / ".join(parts[1:]) if len(parts) > 1 else ""
    exam_parts = [part for part in [board, str(year or ""), agency] if part]
    return year, _normalize_board(board), agency, " - ".join(exam_parts)


def _infer_native_category(document_text: str, statement: str) -> str:
    """Infere a disciplina da planilha para PDFs que não trazem categoria por questão."""
    combined = f"{document_text[:8000]}\n{statement}".lower()
    rules: list[tuple[str, str, tuple[str, ...]]] = [
        (
            "FLUÊNCIA EM DADOS",
            "SISTEMAS DE SUPORTE À DECISÃO, DATA WAREHOUSE, BUSINESS INTELLIGENCE E ETL",
            (
                "tecnologia da informação", "data warehouse", "datawarehouse", "etl",
                "business intelligence", "data mart", "olap", "oltp", "mineração de dados",
                "machine learning", "integração de dados", "staging area", "banco de dados",
                "modelo entidade-relacionamento", "modelo relacional", "normalização",
                "cardinalidade", "chave primária", "chave estrangeira", "sgbd", "sql",
            ),
        ),
        (
            "AUDITORIA",
            "CONCEITOS E PROCEDIMENTOS DE AUDITORIA",
            ("auditoria", "auditor", "evidência de auditoria", "parecer do auditor"),
        ),
        (
            "DIREITO TRIBUTÁRIO",
            "SISTEMA TRIBUTÁRIO E OBRIGAÇÃO TRIBUTÁRIA",
            ("tributo", "obrigação tributária", "crédito tributário", "imunidade tributária"),
        ),
        (
            "DIREITO CONSTITUCIONAL",
            "DIREITO CONSTITUCIONAL",
            ("constituição federal", "controle de constitucionalidade", "direitos fundamentais"),
        ),
        (
            "DIREITO ADMINISTRATIVO",
            "DIREITO ADMINISTRATIVO",
            ("ato administrativo", "licitação", "administração pública", "agente público"),
        ),
        (
            "CONTABILIDADE GERAL E AVANÇADA",
            "CONTABILIDADE GERAL E AVANÇADA",
            ("balanço patrimonial", "demonstrações contábeis", "lançamento contábil", "patrimônio líquido"),
        ),
        (
            "ESTATÍSTICA",
            "ESTATÍSTICA",
            ("probabilidade", "distribuição de frequência", "desvio padrão", "variância", "amostragem estatística"),
        ),
        (
            "RACIOCÍNIO-LÓGICO MATEMÁTICO",
            "RACIOCÍNIO LÓGICO MATEMÁTICO",
            ("proposição lógica", "tabela verdade", "equivalência lógica", "raciocínio lógico"),
        ),
        (
            "PORTUGUÊS",
            "LÍNGUA PORTUGUESA",
            ("língua portuguesa", "regência", "concordância", "pontuação", "interpretação de texto"),
        ),
    ]
    best: tuple[int, str, str] | None = None
    for matter, topic, keywords in rules:
        # Count complete terms.  A substring count made "tributo" match every
        # occurrence of "atributo", which classified database-modeling books
        # as Direito Tributario.
        score = sum(
            len(re.findall(rf"(?<!\w){re.escape(keyword)}(?!\w)", combined))
            for keyword in keywords
        )
        if score and (best is None or score > best[0]):
            best = (score, matter, topic)
    if best:
        return f"{best[1]} > {best[2]}"
    return ""


def _sanitize_asset_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe or "questao"


def _save_pdf_clip(page: pymupdf.Page, bbox: tuple[float, float, float, float], output_path: Path, dpi: int) -> None:
    rect = pymupdf.Rect(bbox)
    page_rect = page.rect
    rect = pymupdf.Rect(
        max(0, rect.x0 - 8),
        max(0, rect.y0 - 8),
        min(page_rect.width, rect.x1 + 8),
        min(page_rect.height, rect.y1 + 8),
    )
    pix = page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), clip=rect, alpha=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pix.save(output_path)


def _attach_native_question_images(
    document: pymupdf.Document,
    questions: list[dict],
    config: ExtractorConfig,
    asset_dir: str | Path | None,
) -> None:
    if asset_dir is None:
        return
    asset_root = Path(asset_dir)
    asset_root.mkdir(parents=True, exist_ok=True)
    for question in questions:
        visual = question.get("contexto_visual", {}) if isinstance(question.get("contexto_visual"), dict) else {}
        pages = list(visual.get("paginas") or [])
        if not pages:
            start_page = question.get("fonte", {}).get("pagina_inicial")
            end_page = question.get("fonte", {}).get("pagina_final") or start_page
            if start_page and end_page and re.search(r"\b(?:imagem|figura|gráfico|grafico|diagrama)\b", str(question.get("enunciado", "")), re.I):
                pages = list(range(int(start_page), int(end_page) + 1))
        if not pages:
            continue

        candidates: list[tuple[float, int, tuple[float, float, float, float]]] = []
        for page_number in pages:
            if page_number < 1 or page_number > len(document):
                continue
            page = document[page_number - 1]
            page_height = float(page.rect.height)
            blocks = page.get_text("dict").get("blocks", [])
            for block in blocks:
                if int(block.get("type", -1)) != 1:
                    continue
                x0, y0, x1, y1 = [float(value) for value in block.get("bbox", (0, 0, 0, 0))]
                width = x1 - x0
                height = y1 - y0
                area = width * height
                if y0 < 60 or y1 > page_height - 60:
                    continue
                if width < 80 or height < 50:
                    continue
                if area < 12000:
                    continue
                candidates.append((area, page_number, (x0, y0, x1, y1)))

        image_origin = "extraida_automaticamente"
        if candidates:
            _, page_number, bbox = max(candidates, key=lambda item: item[0])
        else:
            method = str((question.get("ocr") or {}).get("metodo", ""))
            if not pages:
                continue
            page_number = int(pages[0])
            page = document[page_number - 1]
            fragmented_visual_page = len(page.get_images(full=True)) >= 50
            # PDFium may flatten a page into hundreds of image tiles. When no
            # independent diagram block survives, or the Markdown explicitly
            # referenced an image/table that became vector text, keep the page
            # context so the reviewer never receives an incomplete question.
            bbox = (0.0, 0.0, float(page.rect.width), float(page.rect.height))
            image_origin = (
                "pagina_fragmentada_contexto_visual"
                if fragmented_visual_page and not method.startswith("ocr_")
                else "pagina_digitalizada_contexto_visual"
                if method.startswith("ocr_")
                else "pagina_nativa_contexto_visual"
            )
        safe_code = _sanitize_asset_name(str(question.get("codigo_origem") or question.get("id") or "questao"))
        output_path = asset_root / f"{safe_code}.png"
        _save_pdf_clip(document[page_number - 1], bbox, output_path, config.dpi)
        question["imagem_questao"] = {
            "path": str(output_path),
            "origem": image_origin,
            "recorte_automatico": True,
            "pagina": page_number,
            "precisa_revisao": True,
        }
        if visual:
            visual["imagem_extraida"] = True
            visual["arquivo_imagem"] = str(output_path)


def _native_body_parts(body: str, answer: str) -> tuple[str, list[dict], str]:
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    statement, alternatives = _extract_options_from_text(body)
    if len(alternatives) >= 2:
        return statement, alternatives, "multipla_escolha"

    # Some publisher PDFs emit option labels as bare capitals (``A text``)
    # and may collapse several options into one line. Restrict this fallback
    # to letter-answer questions and require an ordered A, B, C... sequence.
    if answer in {"A", "B", "C", "D", "E"}:
        prompt_patterns = (
            r"Assinale\b[^\n]*?(?:\.|:|\?)",
            r"A\s+sequ[eê]ncia\b[^\n]*?(?:\.|:|\?)",
            r"Quais\s+est[aã]o\s+corret[ao]s?\s*\?",
        )
        prompt_ends = [
            match.end()
            for pattern in prompt_patterns
            for match in re.finditer(pattern, body, re.I)
        ]
        if prompt_ends:
            search_start = max(prompt_ends)
        else:
            colon_matches = list(re.finditer(r":\s*(?=\n|[*_~<]|[A-E]\s)", body))
            search_start = colon_matches[-1].end() if colon_matches else 0
        tail = body[search_start:]
        candidates = list(re.finditer(r"(?<![A-Za-z0-9])([A-E])\s+(?=\S)", tail))
        ordered: list[re.Match] = []
        expected = ord("A")
        for candidate in candidates:
            if candidate.group(1) == chr(expected):
                ordered.append(candidate)
                expected += 1
                if expected > ord("E"):
                    break
        if len(ordered) >= 2 and ordered[0].group(1) == "A":
            alternatives = []
            for index, candidate in enumerate(ordered):
                end = ordered[index + 1].start() if index + 1 < len(ordered) else len(tail)
                option_text = _clean_option(tail[candidate.end() : end])
                if option_text:
                    alternatives.append({"chave": candidate.group(1), "texto": option_text})
            if len(alternatives) >= 2:
                statement_end = search_start + ordered[0].start()
                return _clean_text(body[:statement_end]), alternatives, "multipla_escolha"

    statement = _clean_text(body)
    is_true_false = answer in {"C", "E"} or bool(
        re.search(r"\b(?:julgue|certo\s+ou\s+errado|item\s+(?:a\s+seguir|subsequente))\b", statement, re.I)
    )
    if is_true_false:
        alternatives = [
            {"chave": "C", "texto": "Certo"},
            {"chave": "E", "texto": "Errado"},
        ]
        return statement, alternatives, "certo_errado"
    return statement, alternatives, "multipla_escolha"



_QCONCURSOS_HEADER_RE = re.compile(
    r"^\s*(\d{1,3})\s+Q\s*(\d{5,8})\s+(.+?)\s*$", re.I
)
_QCONCURSOS_META_RE = re.compile(r"^(?:Ano|Banca|Órgão|Orgao|Prova|Provas)\s*:", re.I)
_QCONCURSOS_OPTION_KEY_RE = re.compile(r"^[A-H]$", re.I)


def _qconcursos_is_chrome_line(text: str) -> bool:
    value = _clean_text(text)
    if not value:
        return True
    if re.fullmatch(r"\d{2}/\d{2}/\d{4},\s*\d{1,2}:\d{2}", value):
        return True
    if re.fullmatch(r"Questões de Concurso Público\s*-\s*Qconcursos", value, re.I):
        return True
    if re.fullmatch(r"qconcursos\.com", value, re.I):
        return True
    if value.lower().startswith(("https://elite.qconcursos.com/", "http://elite.qconcursos.com/")):
        return True
    if re.fullmatch(r"\d{1,3}/\d{1,3}", value):
        return True
    return False


def _qconcursos_native_layout(document: pymupdf.Document) -> tuple[list[dict], list[dict], list[float]]:
    """Return text lines and image blocks in true visual order.

    QConcursos browser-print PDFs often store all question headers before option
    blocks in the internal content stream. ``page.get_text('text')`` therefore
    scrambles the semantic order even though the rendered page is correct.  The
    line/image coordinates are stable, so we build a document-wide Y axis and
    segment questions geometrically.
    """
    lines: list[dict] = []
    images: list[dict] = []
    page_offsets: list[float] = []
    offset = 0.0
    for page_index, page in enumerate(document):
        page_offsets.append(offset)
        payload = page.get_text("dict", sort=True)
        for block in payload.get("blocks", []):
            block_type = int(block.get("type", -1))
            bbox = tuple(float(value) for value in block.get("bbox", (0, 0, 0, 0)))
            if block_type == 1:
                images.append(
                    {
                        "page": page_index,
                        "bbox": bbox,
                        "global_y0": offset + bbox[1],
                        "global_y1": offset + bbox[3],
                    }
                )
                continue
            if block_type != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = "".join(str(span.get("text", "")) for span in spans).strip()
                if not text or _qconcursos_is_chrome_line(text):
                    continue
                x0, y0, x1, y1 = [float(value) for value in line.get("bbox", bbox)]
                lines.append(
                    {
                        "page": page_index,
                        "x": x0,
                        "y": y0,
                        "x1": x1,
                        "y1": y1,
                        "global_y": offset + y0,
                        "global_y1": offset + y1,
                        "text": text,
                    }
                )
        offset += float(page.rect.height) + 20.0
    lines.sort(key=lambda item: (item["global_y"], item["x"]))
    images.sort(key=lambda item: (item["global_y0"], item["bbox"][0]))
    return lines, images, page_offsets


def _qconcursos_native_answer_key(lines: list[dict]) -> tuple[dict[int, str], float | None, str]:
    marker_index = None
    for index in range(len(lines) - 1, -1, -1):
        if re.fullmatch(r"Respostas?", _clean_text(lines[index]["text"]), re.I):
            marker_index = index
            break
    if marker_index is None:
        return {}, None, ""
    marker_y = float(lines[marker_index]["global_y"])
    answer_lines = lines[marker_index + 1 :]
    raw = " ".join(item["text"] for item in answer_lines)
    answers: dict[int, str] = {}
    for number, value in re.findall(
        r"(?<!\d)(\d{1,3})\s*:\s*(CORRETO|CERTO|VERDADEIRO|ERRADO|INCORRETO|FALSO|ANULADA|[A-H])\b",
        raw,
        flags=re.I,
    ):
        answers[int(number)] = _normalize_answer_value(value)
    return answers, marker_y, _clean_text(raw)


def _qconcursos_lesson_from_filename(path: Path) -> str:
    match = re.search(r"(?:^|[^A-Za-z0-9])Aula[\s._-]*0*(\d{1,2})(?=$|[^0-9])", path.stem, re.I)
    if not match:
        return ""
    return f"Aula {int(match.group(1)):02d}"


def _qconcursos_taxonomy_matter_from_filename(
    path: Path, taxonomy: SpreadsheetTaxonomy | None
) -> str:
    if taxonomy is None:
        return ""
    normalized_name = unicodedata.normalize("NFKD", path.stem)
    normalized_name = normalized_name.encode("ascii", "ignore").decode("ascii").upper()
    name_tokens = set(re.findall(r"[A-Z0-9]{2,}", normalized_name))
    candidates: list[tuple[int, str]] = []
    for matter in taxonomy.materias:
        normalized_matter = unicodedata.normalize("NFKD", str(matter))
        normalized_matter = normalized_matter.encode("ascii", "ignore").decode("ascii").upper()
        matter_tokens = {
            token for token in re.findall(r"[A-Z0-9]{2,}", normalized_matter)
            if token not in {"E", "EM", "DE", "DA", "DO", "DAS", "DOS"}
        }
        if matter_tokens and matter_tokens.issubset(name_tokens):
            candidates.append((len(matter_tokens), str(matter)))
    return max(candidates, default=(0, ""))[1]


def _qconcursos_question_metadata(region: list[dict], header_y: float) -> tuple[list[dict], float]:
    metadata: list[dict] = []
    seen_exam = False
    last_meta_y = header_y
    for item in region:
        if item["global_y"] <= header_y + 0.5:
            continue
        text = _clean_text(item["text"])
        if _QCONCURSOS_META_RE.match(text):
            metadata.append(item)
            last_meta_y = max(last_meta_y, float(item["global_y"]))
            if re.match(r"^Provas?\s*:", text, re.I):
                seen_exam = True
            continue
        # Prova(s) can wrap to the next visual line and is indented on QConcursos.
        if seen_exam and float(item["global_y"]) - last_meta_y <= 18.0 and float(item["x"]) <= 90.0:
            metadata.append(item)
            last_meta_y = max(last_meta_y, float(item["global_y"]))
            continue
        if seen_exam:
            return metadata, float(item["global_y"])
    return metadata, last_meta_y + 1.0


def _qconcursos_visual_clip(
    document: pymupdf.Document,
    path: Path,
    source_code: str,
    region_images: list[dict],
    option_markers: list[dict],
    question_end: float,
    page_offsets: list[float],
    asset_dir: str | Path | None,
    dpi: int,
) -> dict:
    if not region_images or asset_dir is None:
        return {}
    # QConcursos visual alternatives are normally on one page.  Clip the whole
    # alternatives area instead of one embedded bitmap so labels A/B/C/D remain
    # meaningful and missing/transparent parts are visible to the reviewer.
    page_index = int(region_images[0]["page"])
    same_page_images = [item for item in region_images if int(item["page"]) == page_index]
    same_page_markers = [item for item in option_markers if int(item["page"]) == page_index]
    page = document[page_index]
    local_end = question_end - page_offsets[page_index]
    y0_candidates = [float(item["bbox"][1]) for item in same_page_images]
    y0_candidates.extend(float(item["y"]) for item in same_page_markers)
    y1_candidates = [float(item["bbox"][3]) for item in same_page_images]
    y1_candidates.extend(float(item["y1"]) + 18.0 for item in same_page_markers)
    y0 = max(0.0, min(y0_candidates) - 10.0)
    y1 = min(float(page.rect.height), max(y1_candidates + [min(local_end, float(page.rect.height))]) - 8.0)
    if y1 <= y0 + 20:
        return {}
    output = Path(asset_dir) / f"{_sanitize_asset_name(source_code)}_visual.png"
    _save_pdf_clip(page, (20.0, y0, float(page.rect.width) - 20.0, y1), output, dpi)
    return {
        "path": str(output),
        "origem": "qconcursos_alternativas_visuais",
        "recorte_automatico": True,
        "pagina": page_index + 1,
        "precisa_revisao": True,
    }


def _extract_native_qconcursos_pdf(
    document: pymupdf.Document,
    path: Path,
    config: ExtractorConfig,
    progress: ProgressCallback | None,
    cancel_event,
    taxonomy: SpreadsheetTaxonomy | None,
    asset_dir: str | Path | None = None,
) -> dict | None:
    """Extract browser-print QConcursos PDFs without OCR.

    This strategy follows rendered coordinates, not PDF content-stream order. It
    therefore handles questions/options that PyMuPDF returns out of order, answers
    split across pages, and multi-page question bodies.
    """
    signature = "\n".join((page.get_text("text") or "")[:1400] for page in document[: min(3, len(document))])
    if not re.search(r"qconcursos\.com|Questões de Concurso Público\s*-\s*Qconcursos", signature, re.I):
        return None

    lines, images, page_offsets = _qconcursos_native_layout(document)
    headers: list[dict] = []
    for item in lines:
        match = _QCONCURSOS_HEADER_RE.match(_clean_text(item["text"]))
        if not match:
            continue
        headers.append(
            {
                **item,
                "number": int(match.group(1)),
                "source_code": f"Q{match.group(2)}",
                "category": _clean_text(match.group(3)),
            }
        )
    headers.sort(key=lambda item: item["global_y"])
    if len(headers) < 1:
        return None

    answers, answer_marker_y, answer_text = _qconcursos_native_answer_key(lines)
    content_end = answer_marker_y if answer_marker_y is not None else (
        page_offsets[-1] + float(document[-1].rect.height)
    )
    source_lesson = _qconcursos_lesson_from_filename(path)
    filename_matter = _qconcursos_taxonomy_matter_from_filename(path, taxonomy)
    _progress(progress, 0.06, f"QConcursos nativo identificado: {len(headers)} questões")

    questions: list[dict] = []
    for index, header in enumerate(headers):
        _check_cancel(cancel_event)
        _progress(
            progress,
            0.08 + 0.88 * index / max(1, len(headers)),
            f"Lendo layout nativo QConcursos {index + 1}/{len(headers)}",
        )
        question_start = float(header["global_y"])
        question_end = (
            float(headers[index + 1]["global_y"])
            if index + 1 < len(headers)
            else float(content_end)
        )
        region = [
            item for item in lines
            if question_start - 0.5 <= float(item["global_y"]) < question_end - 0.5
            and not re.fullmatch(r"Respostas?", _clean_text(item["text"]), re.I)
        ]
        metadata_lines, body_start = _qconcursos_question_metadata(region, question_start)
        year, board, agency, exam, raw_metadata = _parse_metadata(metadata_lines)
        body_lines = [item for item in region if float(item["global_y"]) >= body_start - 0.1]
        option_markers = [
            item for item in body_lines
            if _QCONCURSOS_OPTION_KEY_RE.fullmatch(_clean_text(item["text"]))
            and 32.0 <= float(item["x"]) <= 48.5
        ]
        option_markers.sort(key=lambda item: item["global_y"])

        first_option_y = (
            float(option_markers[0]["global_y"]) - 12.0
            if option_markers else question_end
        )
        statement_parts = [
            item["text"] for item in body_lines
            if float(item["global_y"]) < first_option_y
        ]
        statement = _clean_text(" ".join(statement_parts))

        region_images = [
            item for item in images
            if question_start <= float(item["global_y0"]) < question_end
        ]
        alternatives: list[dict] = []
        seen_keys: set[str] = set()
        for marker_index, marker in enumerate(option_markers[:8]):
            key = _clean_text(marker["text"]).upper()
            if key in seen_keys:
                continue
            start_y = float(marker["global_y"]) - 12.0
            end_y = (
                float(option_markers[marker_index + 1]["global_y"]) - 12.0
                if marker_index + 1 < len(option_markers)
                else question_end
            )
            parts = [
                item["text"]
                for item in body_lines
                if start_y <= float(item["global_y"]) < end_y
                and float(item["x"]) >= 52.0
                and item is not marker
            ]
            option_text = _clean_option(" ".join(parts))
            alternatives.append({"chave": key, "texto": option_text})
            seen_keys.add(key)

        visual_question = bool(region_images) and bool(option_markers)
        if visual_question:
            for alternative in alternatives:
                if not _clean_text(alternative.get("texto", "")):
                    alternative["texto"] = f"Alternativa visual {alternative['chave']}"
                    alternative["visual"] = True

        answer = _normalize_answer_value(answers.get(int(header["number"]), ""))
        keys = [str(item.get("chave", "")).upper() for item in alternatives]
        is_true_false = bool(
            _TRUE_FALSE_HINT_RE.search(statement)
            or (
                len(alternatives) == 2
                and {str(item.get("texto", "")).strip().lower() for item in alternatives}
                & {"certo", "errado", "verdadeiro", "falso"}
            )
        )
        if is_true_false:
            alternatives = [
                {"chave": "C", "texto": "Certo"},
                {"chave": "E", "texto": "Errado"},
            ]
            keys = ["C", "E"]
        correct_index = keys.index(answer) if answer in keys else None

        raw_category = str(header["category"])
        classification_category = raw_category
        if filename_matter:
            source_topics = raw_category.split(">", 1)[1].strip() if ">" in raw_category else raw_category
            classification_category = f"{filename_matter} > {source_topics}" if source_topics else filename_matter
        subject, topics, topic_path = _classification(raw_category)
        role, area, specialty, shift = _derive_exam_fields(exam)

        start_page = int(header["page"])
        end_page = start_page
        for item in [*body_lines, *option_markers]:
            end_page = max(end_page, int(item.get("page", start_page)))
        visual_info = _qconcursos_visual_clip(
            document,
            path,
            str(header["source_code"]),
            region_images,
            option_markers,
            question_end,
            page_offsets,
            asset_dir,
            config.dpi,
        )

        question = {
            "id": str(header["source_code"]),
            "numero_origem": int(header["number"]),
            "codigo_origem": str(header["source_code"]),
            "materia": subject,
            "assuntos": topics,
            "trilha_assuntos": topic_path,
            "aula_origem": source_lesson,
            "banca": board,
            "ano": year,
            "orgao": agency,
            "prova": exam,
            "cargo": role,
            "area": area,
            "especialidade": specialty,
            "turno": shift,
            "tipo": "certo_errado" if is_true_false else "multipla_escolha",
            "enunciado": statement,
            "alternativas": alternatives,
            "gabarito": answer,
            "explicacao": "",
            "fonte": {
                "plataforma": "QConcursos",
                "arquivo": path.name,
                "caminho_arquivo": str(path.resolve()),
                "pagina_inicial": start_page + 1,
                "pagina_final": end_page + 1,
                "codigo": str(header["source_code"]),
            },
            "telegram": {
                "modo": "quiz",
                "pergunta": statement,
                "opcoes": [str(item.get("texto", "")) for item in alternatives],
                "indice_correto": correct_index,
            },
            "ocr": {
                "metodo": "texto_nativo_qconcursos_layout",
                "metadados_brutos": raw_metadata,
                "categoria_bruta": classification_category,
                "categoria_bruta_original": raw_category,
                "texto_bruto": "\n".join(item.get("text", "") for item in region),
            },
            "contexto_visual": {
                "necessario": visual_question,
                "paginas": sorted({int(item["page"]) + 1 for item in region_images}),
                "observacao": (
                    "Alternativas visuais detectadas no PDF do QConcursos; revisar a imagem recortada."
                    if visual_question else ""
                ),
            },
        }
        if visual_info:
            question["imagem_questao"] = visual_info
        if taxonomy is not None:
            taxonomy.apply_to_question(question)
            # A filename such as ``fluencia-dados_Aula01.pdf`` is an explicit
            # user-side organization hint.  When it matches a canonical matter
            # from the study sheet, prefer that matter/lesson over an unconstrained
            # similarity match that could incorrectly send Banco de Dados to a
            # different lesson.  Fine-grained topics still come from QConcursos.
            if filename_matter:
                source_subjects = [str(item).strip() for item in topics if str(item).strip()]
                primary_subject = source_subjects[0].upper() if source_subjects else str(question.get("assunto", ""))
                question["materia"] = filename_matter
                if source_lesson:
                    question["aula_planilha"] = source_lesson
                if primary_subject:
                    question["assunto"] = primary_subject
                    question["assuntos"] = [item.upper() for item in source_subjects] or [primary_subject]
                question["trilha_assuntos"] = [
                    item for item in [filename_matter, source_lesson, primary_subject] if item
                ]
                question["classificacao_planilha"] = {
                    "status": "classificado",
                    "confianca": 0.98 if source_lesson else 0.92,
                    "metodo": "nome_arquivo_qconcursos",
                    "referencia": path.name,
                    "fonte": taxonomy.source_name,
                    "categoria_origem": raw_category,
                    "assuntos_origem": source_subjects,
                }
        question = deep_repair_question(
            question,
            taxonomy,
            allow_auto_approve=not visual_question,
            method="texto_nativo_qconcursos_layout",
        )
        confidence, alerts = _question_status(question)
        if visual_question:
            confidence = min(confidence, 0.78)
            visual_alert = "Questão com alternativas visuais: conferir o recorte antes do envio"
            if visual_alert not in alerts:
                alerts.append(visual_alert)
        question["revisao"] = {
            "status": "pendente" if visual_question or confidence < 0.90 else "aprovado_automaticamente",
            "confianca": round(confidence, 2),
            "alertas": alerts,
        }
        question["fingerprint"] = _fingerprint(question)
        questions.append(question)

    _progress(progress, 1.0, f"{len(questions)} questões extraídas de {path.name} pelo layout nativo QConcursos")
    return {
        "schema": "questflow.questions.v1",
        "schema_version": 1,
        "source_file": path.name,
        "source_path": str(path),
        "extractor": "QuestFlow Studio - QConcursos nativo",
        "extractor_mode": "texto_nativo_qconcursos_layout",
        "starts_found": len(headers),
        "answers_found": len([item for item in questions if item.get("gabarito")]),
        "answer_ocr": answer_text,
        "taxonomy": taxonomy.source_name if taxonomy is not None else "",
        "questions": questions,
    }


def _is_scanned_strategy_question_book(
    document: pymupdf.Document,
    config: ExtractorConfig,
) -> bool:
    """Cheaply identify scanned Estratégia resolved/commented question books."""
    if not len(document):
        return False
    sampled = document[: min(2, len(document))]
    native_chars = sum(len((page.get_text("text") or "").strip()) for page in sampled)
    sampled_visuals = sum(
        len(page.get_images(full=True)) + len(page.get_drawings())
        for page in sampled
    )
    # PDFium and some virtual printers turn every glyph into vector paths. Such
    # pages have no text and no raster image object, but thousands of drawings.
    if native_chars >= 180 or sampled_visuals < 1:
        return False
    image = _render_page(document[0], max(180, min(config.dpi, 220)))
    signature = pytesseract.image_to_string(
        image,
        lang=config.languages,
        config="--psm 6",
    )
    signature_ascii = unicodedata.normalize("NFKD", signature)
    signature_ascii = signature_ascii.encode("ascii", "ignore").decode("ascii")
    return bool(_COMMENTED_BOOK_SIGNATURE_RE.search(signature_ascii))


def _extract_native_strategy_pdf(
    document: pymupdf.Document,
    path: Path,
    config: ExtractorConfig,
    progress: ProgressCallback | None,
    cancel_event,
    taxonomy: SpreadsheetTaxonomy | None,
    asset_dir: str | Path | None = None,
    markdown_bundle: MarkdownBundle | None = None,
) -> dict | None:
    """Extrai listas do Estratégia e formatos textuais semelhantes a partir do Markdown estruturado."""
    raw_pages = list(markdown_bundle.pages) if markdown_bundle is not None and markdown_bundle.pages else [page.get_text("text") or "" for page in document]
    raw_document = "\n".join(raw_pages)
    has_list_answer_key = bool(
        re.search(r"LISTA\s+DE\s+QUEST", raw_document, re.I)
        and re.search(r"(?m)^\s*GABARITO\s*$", raw_document, re.I)
    )
    inline_answer_count = sum(
        1
        for candidate in re.findall(r"(?mi)^[^\r\n]*\bGabarito\b[^\r\n]*$", raw_document)
        if _native_inline_answer(candidate)
    )
    comment_marker_count = len(list(_NATIVE_COMMENT_MARKER_RE.finditer(raw_document)))
    has_commented_answers = bool(
        inline_answer_count >= 2
        and (
            comment_marker_count >= 2
            or _COMMENTED_BOOK_SIGNATURE_RE.search(raw_document)
        )
    )
    if not (has_list_answer_key or has_commented_answers):
        return None

    detected_label = "questões resolvidas e comentadas" if has_commented_answers else "lista de questões"
    _progress(progress, 0.08, f"Formato textual de {detected_label} identificado")
    page_texts = [_native_clean_page_text(text) for text in raw_pages]
    page_starts: list[int] = []
    full_text = ""
    for page_text in page_texts:
        page_starts.append(len(full_text))
        full_text += page_text + "\n\n"

    list_marker = re.search(r"LISTA\s+DE\s+QUEST(?:ÕES|OES)", full_text, re.I)
    answer_marker = re.search(r"(?m)^\s*GABARITO\s*$", full_text, re.I)
    if has_list_answer_key:
        if not list_marker or not answer_marker or answer_marker.start() <= list_marker.end():
            return None
        question_area_start = list_marker.end()
        question_area_end = answer_marker.start()
    else:
        question_area_start = 0
        question_area_end = len(full_text)
    question_area = full_text[question_area_start:question_area_end]
    starts = list(_NATIVE_QUESTION_RE.finditer(question_area))
    if not starts:
        return None

    if has_list_answer_key and answer_marker is not None:
        answers, answer_text = _native_answer_key(full_text[answer_marker.end() :])
    else:
        answers, answer_text = {}, ""
    file_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:10].upper()
    source_lesson_match = re.search(r"\bAula\s+(\d{1,2})\b", raw_document, re.I)
    source_lesson = f"Aula {int(source_lesson_match.group(1)):02d}" if source_lesson_match else ""
    platform = (
        "Estratégia Concursos"
        if re.search(r"estrategiaconcursos", raw_document, re.I)
        or _COMMENTED_BOOK_SIGNATURE_RE.search(raw_document)
        else config.platform
    )
    document_category = _infer_native_category(raw_document, question_area)
    source_is_ocr = bool(markdown_bundle is not None and markdown_bundle.used_ocr)
    extraction_mode = (
        "ocr_comentado" if source_is_ocr and has_commented_answers
        else "ocr_lista_gabarito" if source_is_ocr
        else "texto_nativo_comentado" if has_commented_answers
        else "texto_nativo_lista_gabarito"
    )
    number_counts: dict[int, int] = {}
    for start_match in starts:
        start_number = int(start_match.group(1))
        number_counts[start_number] = number_counts.get(start_number, 0) + 1

    questions: list[dict] = []
    total = max(1, len(starts))
    for index, match in enumerate(starts):
        _check_cancel(cancel_event)
        _progress(progress, 0.12 + 0.82 * index / total, f"Organizando questão textual {index + 1}/{len(starts)}")
        number = int(match.group(1))
        raw_header = match.group(2)
        body_start = match.end()
        body_end = starts[index + 1].start() if index + 1 < len(starts) else len(question_area)
        body = question_area[body_start:body_end]
        explanation = ""
        answer = answers.get(number, "")
        question_body = body
        if has_commented_answers:
            comment_marker = _NATIVE_COMMENT_MARKER_RE.search(body)
            inline_answer_line = next(
                (
                    candidate
                    for candidate in re.finditer(r"(?mi)^[^\r\n]*\bGabarito\b[^\r\n]*$", body)
                    if _native_inline_answer(candidate.group(0))
                ),
                None,
            )
            if inline_answer_line:
                answer = _native_inline_answer(inline_answer_line.group(0))
                answer_text += f"{number}. {answer}\n"
            content_end = comment_marker.start() if comment_marker else (inline_answer_line.start() if inline_answer_line else len(body))
            question_body = body[:content_end]
            if comment_marker:
                explanation_start = comment_marker.end()
                if inline_answer_line and inline_answer_line.start() >= explanation_start:
                    # The answer declaration is metadata, not the boundary of the
                    # commentary. Preserve explanations that continue after it.
                    explanation_source = (
                        body[explanation_start : inline_answer_line.start()]
                        + "\n"
                        + _native_trim_post_answer(body[inline_answer_line.end() :])
                    )
                else:
                    explanation_source = body[explanation_start:]
                explanation = _native_plain_markdown(explanation_source)
        statement, alternatives, question_type = _native_body_parts(question_body, answer)
        statement = _native_plain_markdown(statement)
        for alternative in alternatives:
            alternative["texto"] = _native_plain_markdown(alternative.get("texto", ""))
        year, board, agency, exam = _native_metadata(raw_header)
        absolute_start = question_area_start + match.start()
        absolute_end = question_area_start + body_end
        start_page = _native_page_for_offset(page_starts, absolute_start)
        end_page = _native_page_for_offset(page_starts, max(absolute_start, absolute_end - 1))
        raw_category = document_category or _infer_native_category(raw_document, statement)
        subject, topics, topic_path = _classification(raw_category)
        source_code = (
            f"ESTRATEGIA-{file_hash}-{number:03d}-{index + 1:03d}"
            if number_counts.get(number, 0) > 1
            else f"ESTRATEGIA-{file_hash}-{number:03d}"
        )
        has_visual_context = bool(
            re.search(r"!\[[^\]]*\]\([^\)]+\)", question_body)
            or re.search(
                r"\b(?:imagem|figura|diagrama|gráfico|grafico|tabela|quadro|esquema)\s+(?:abaixo|a\s+seguir)\b"
                r"|considere\s+(?:a\s+|o\s+)?(?:imagem|figura|diagrama|gráfico|grafico|tabela|quadro|esquema)",
                statement,
                re.I,
            )
            or (
                not alternatives
                and answer in {"A", "B", "C", "D", "E"}
                and re.search(
                    r"\b(?:nota(?:ç|c)[aã]o|s[ií]mbolo\s+gr[aá]fico|diagrama\s+(?:ER|entidade)|crow'?s?\s+foot|p[eé]\s+de\s+galinha)\b",
                    statement,
                    re.I,
                )
            )
        )
        if has_visual_context and not alternatives and answer in {"A", "B", "C", "D", "E"}:
            alternatives = [
                {"chave": key, "texto": f"Alternativa visual {key}", "visual": True}
                for key in ("A", "B", "C", "D", "E")
            ]
        keys = [item.get("chave", "") for item in alternatives]
        correct_index = keys.index(answer) if answer in keys else None

        question = {
            "id": source_code,
            "numero_origem": number,
            "codigo_origem": source_code,
            "materia": subject,
            "assuntos": topics,
            "trilha_assuntos": topic_path,
            "aula_origem": source_lesson,
            "banca": board,
            "ano": year,
            "orgao": agency,
            "prova": exam,
            "cargo": "",
            "area": "",
            "especialidade": "",
            "turno": "",
            "tipo": question_type,
            "enunciado": statement,
            "alternativas": alternatives,
            "gabarito": answer,
            "explicacao": explanation,
            "fonte": {
                "plataforma": platform,
                "arquivo": path.name,
                "caminho_arquivo": str(path.resolve()),
                "pagina_inicial": start_page + 1,
                "pagina_final": end_page + 1,
                "codigo": source_code,
            },
            "telegram": {
                "modo": "quiz",
                "pergunta": statement,
                "opcoes": [item.get("texto", "") for item in alternatives],
                "indice_correto": correct_index,
            },
            "ocr": {
                "metodo": extraction_mode,
                "metadados_brutos": raw_header,
                "categoria_bruta": raw_category,
            },
            "contexto_visual": {
                "necessario": has_visual_context,
                "paginas": list(range(start_page + 1, end_page + 2)) if has_visual_context else [],
                "observacao": "Questão menciona imagem ou figura; confira o PDF na revisão." if has_visual_context else "",
            },
        }
        if taxonomy is not None:
            taxonomy.apply_to_question(question)
        question = deep_repair_question(
            question,
            taxonomy,
            allow_auto_approve=False,
            method="extracao_textual_apurada",
        )

        confidence, alerts = _question_status(question)
        if has_visual_context:
            confidence = round(max(0.0, confidence - 0.12), 2)
            alerts.append("Questão com figura ou imagem: revisar contexto visual")
        taxonomy_status = question.get("classificacao_planilha", {}).get("status")
        if taxonomy_status == "revisar":
            confidence = round(max(0.0, confidence - 0.05), 2)
            alerts.append("Classificação da planilha precisa de revisão")
        question["revisao"] = {
            "status": "aprovado_automaticamente" if confidence >= 0.90 else "pendente",
            "confianca": confidence,
            "alertas": alerts,
        }
        question["fingerprint"] = _fingerprint(question)
        questions.append(question)

    _attach_native_question_images(document, questions, config, asset_dir)
    repaired_questions: list[dict] = []
    for question in questions:
        question = deep_repair_question(
            question,
            taxonomy,
            allow_auto_approve=True,
            method="validacao_final_texto_imagem",
        )
        if question.get("contexto_visual", {}).get("necessario"):
            review = question.setdefault("revisao", {})
            alerts = list(review.get("alertas", []))
            if question.get("imagem_questao"):
                visual_alert = "Questão com tabela, figura ou imagem: conferir o contexto visual"
            else:
                visual_alert = "Imagem não recortada automaticamente: anexe manualmente na revisão"
            if visual_alert not in alerts:
                alerts.append(visual_alert)
            review["alertas"] = alerts
            review["status"] = "pendente"
        repaired_questions.append(question)
    questions = repaired_questions
    _progress(progress, 1.0, f"{len(questions)} questões extraídas de {path.name} por texto nativo")
    return {
        "schema": "questflow.questions.v1",
        "schema_version": 1,
        "source_file": path.name,
        "source_path": str(path),
        "extractor": "QuestFlow Studio - extrator multiformato",
        "extractor_mode": extraction_mode,
        "starts_found": len(starts),
        "answers_found": len([question for question in questions if question.get("gabarito")]),
        "answer_ocr": answer_text,
        "taxonomy": taxonomy.source_name if taxonomy is not None else "",
        "markdown": markdown_bundle.as_dict() if markdown_bundle is not None else {},
        "questions": questions,
    }


def extract_pdf(
    pdf_path: str | Path,
    config: ExtractorConfig | None = None,
    progress: ProgressCallback | None = None,
    cancel_event=None,
    taxonomy: SpreadsheetTaxonomy | None = None,
    asset_dir: str | Path | None = None,
    markdown_cache_dir: str | Path | None = None,
    force_markdown_ocr: bool = False,
) -> dict:
    config = config or ExtractorConfig()
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(path)

    # Fast path for browser-printed QConcursos PDFs.  These files contain good
    # native text but a misleading content-stream order, so OCR is both slower and
    # less accurate than coordinate-aware native parsing.
    if path.suffix.lower() == ".pdf":
        qconcursos_document = pymupdf.open(path)
        try:
            qconcursos_result = _extract_native_qconcursos_pdf(
                qconcursos_document, path, config, progress, cancel_event, taxonomy, asset_dir
            )
        finally:
            qconcursos_document.close()
        if qconcursos_result is not None:
            return qconcursos_result

    _progress(progress, 0.0, f"Convertendo {path.name} para Markdown estruturado")
    markdown_bundle = None
    try:
        cache_root = Path(markdown_cache_dir) if markdown_cache_dir is not None else path.parent / ".questflow_markdown_cache"
        markdown_bundle = build_markdown_bundle(
            path,
            cache_root,
            languages=config.languages,
            force_ocr=bool(force_markdown_ocr),
            dpi=max(config.dpi, 220),
        )
    except Exception:
        markdown_bundle = None
    if path.suffix.lower() == ".pdf":
        native_document = pymupdf.open(path)
        try:
            native_result = _extract_native_strategy_pdf(
                native_document, path, config, progress, cancel_event, taxonomy, asset_dir, markdown_bundle
            )
        finally:
            native_document.close()
        if native_result is not None:
            return native_result

        # Scanned Estratégia books have no native text layer. Detect their
        # first-page signature, create cached page-preserving OCR Markdown and
        # reuse the same semantic parser used by text-native question books.
        configure_tesseract(config.tesseract_cmd)
        scanned_document = pymupdf.open(path)
        try:
            is_scanned_strategy = _is_scanned_strategy_question_book(scanned_document, config)
        finally:
            scanned_document.close()
        if is_scanned_strategy:
            _progress(progress, 0.02, "Caderno digitalizado do Estratégia identificado; iniciando OCR")
            cache_root = Path(markdown_cache_dir) if markdown_cache_dir is not None else path.parent / ".questflow_markdown_cache"
            scanned_bundle = build_markdown_bundle(
                path,
                cache_root,
                languages=config.languages,
                force_ocr=True,
                dpi=max(config.dpi, 220),
            )
            scanned_document = pymupdf.open(path)
            try:
                scanned_result = _extract_native_strategy_pdf(
                    scanned_document,
                    path,
                    config,
                    progress,
                    cancel_event,
                    taxonomy,
                    asset_dir,
                    scanned_bundle,
                )
            finally:
                scanned_document.close()
            if scanned_result is not None:
                return scanned_result

    # Formatos sem texto estruturado continuam usando OCR e análise visual.
    configure_tesseract(config.tesseract_cmd)
    document = pymupdf.open(path)
    pages: list[PageAnalysis] = []
    offset = 0
    page_count = max(1, len(document))

    for page_index, page in enumerate(document):
        _check_cancel(cancel_event)
        _progress(
            progress,
            0.04 + 0.72 * page_index / page_count,
            f"OCR da página {page_index + 1}/{page_count}",
        )
        image = _render_page(page, config.dpi)
        lines = _ocr_lines(image, config.languages)
        rules = _detect_horizontal_rules(image)
        circles = _detect_option_circles(image, config.dpi)
        pages.append(
            PageAnalysis(
                index=page_index,
                image=image,
                width=image.width,
                height=image.height,
                offset=offset,
                lines=lines,
                horizontal_rules=rules,
                option_circles=circles,
            )
        )
        offset += image.height + 10

    global_lines: list[dict] = []
    global_circles: list[dict] = []
    global_rules: list[dict] = []
    for page in pages:
        for line in page.lines:
            global_lines.append(
                {**line, "page": page.index, "global_y": page.offset + line["y"]}
            )
        for x, y, radius in page.option_circles:
            global_circles.append(
                {
                    "x": x,
                    "y": y,
                    "radius": radius,
                    "page": page.index,
                    "global_y": page.offset + y,
                }
            )
        for y in page.horizontal_rules:
            global_rules.append(
                {"page": page.index, "y": y, "global_y": page.offset + y}
            )
    global_lines.sort(key=lambda item: item["global_y"])
    global_circles.sort(key=lambda item: item["global_y"])
    global_rules.sort(key=lambda item: item["global_y"])

    starts: list[dict] = []
    previous_number = 0
    for page in pages:
        for line_index, line in enumerate(page.lines):
            if not re.search(r"Ano\s*:", line["text"], re.I):
                continue
            previous_lines = page.lines[max(0, line_index - 4) : line_index]
            inferred_number = previous_number + 1
            number, source_code = _header_identity(previous_lines, inferred_number)
            # OCR sometimes drops the second digit in labels such as 71 or 77.
            # QConcursos exports are ordered, so a value that goes backwards is
            # safely repaired from the immediately preceding question.
            if previous_number and number <= previous_number:
                number = inferred_number
                if source_code.startswith("QFLOW-"):
                    source_code = f"QFLOW-{number:04d}"
            previous_number = number
            previous_rule = max(
                [rule for rule in page.horizontal_rules if rule < line["y"]],
                default=max(0, line["y"] - int(100 * config.dpi / 180)),
            )
            candidates = [
                item["y"]
                for item in previous_lines
                if re.search(r">|\d{5,}", item["text"], re.I)
            ]
            local_start = (
                min(candidates)
                if candidates
                else max(0, line["y"] - int(90 * config.dpi / 180))
            )
            if line["y"] - previous_rule < int(160 * config.dpi / 180):
                local_start = max(previous_rule + 2, local_start - 8)
            else:
                local_start = max(0, local_start - 8)
            starts.append(
                {
                    "number": number,
                    "source_code": source_code,
                    "page": page.index,
                    "local_start": local_start,
                    "metadata_y": line["y"],
                    "global_start": page.offset + local_start,
                    "global_metadata_y": page.offset + line["y"],
                }
            )
    starts.sort(key=lambda item: item["global_start"])

    answer_marker: tuple[int, int, int] | None = None
    # Search backwards and accept only the small standalone label of the answer box.
    # Question statements can contain ordinary phrases such as "respostas a indagações".
    for page in reversed(pages):
        for line in reversed(page.lines):
            label = _clean_text(line["text"])
            if re.fullmatch(r"Respostas?", label, re.I):
                answer_marker = (
                    page.index,
                    line["y"],
                    page.offset + line["y"],
                )
                break
        if answer_marker:
            break

    answers: dict[int, str] = {}
    answer_ocr = ""
    if answer_marker:
        raw_answers, answer_ocr = _answer_key(
            pages[answer_marker[0]].image,
            answer_marker[1],
            config.dpi,
            config.languages,
        )
        answers = _align_answers_to_questions(raw_answers, starts)
    content_end = (
        answer_marker[2] - int(10 * config.dpi / 180)
        if answer_marker
        else offset
    )

    questions: list[dict] = []
    total_questions = max(1, len(starts))
    for index, start in enumerate(starts):
        _check_cancel(cancel_event)
        _progress(
            progress,
            0.78 + 0.19 * index / total_questions,
            f"Organizando questão {index + 1}/{len(starts)}",
        )
        question_top = start["global_start"]
        question_end = (
            starts[index + 1]["global_start"]
            if index + 1 < len(starts)
            else content_end
        )
        region_lines = [
            line
            for line in global_lines
            if question_top <= line["global_y"] < question_end
        ]
        metadata_global_y = start["global_metadata_y"]
        first_rule = next(
            (
                rule["global_y"]
                for rule in global_rules
                if metadata_global_y < rule["global_y"] < question_end
            ),
            None,
        )
        if first_rule is None:
            first_rule = metadata_global_y + int(42 * config.dpi / 180)
        body_start = first_rule + int(8 * config.dpi / 180)

        top_lines = [line for line in region_lines if line["global_y"] < body_start]
        category_parts: list[str] = []
        for line in top_lines:
            if line["global_y"] >= metadata_global_y:
                continue
            text = re.sub(
                r"^\s*\d{1,3}\s*[).]?\s*(?:Q|O|0)?\s*\d{5,8}\s*",
                "",
                line["text"],
                flags=re.I,
            )
            if ">" in text or category_parts:
                if text:
                    category_parts.append(text)
        raw_category = _clean_text(" ".join(category_parts))

        metadata_lines = [
            line for line in top_lines if line["global_y"] >= metadata_global_y
        ]
        year, board, agency, exam, raw_metadata = _parse_metadata(metadata_lines)

        circles = [
            circle
            for circle in global_circles
            if body_start < circle["global_y"] < question_end
        ]
        if len(circles) > 5:
            circles = circles[:5]

        if circles:
            first_option_start = max(
                body_start, circles[0]["global_y"] - int(40 * config.dpi / 180)
            )
        else:
            first_option_start = question_end

        statement_lines = [
            line
            for line in region_lines
            if body_start <= line["global_y"] < first_option_start
        ]
        statement = _clean_text(" ".join(line["text"] for line in statement_lines))

        option_texts: list[str] = []
        for option_index, circle in enumerate(circles):
            option_start = (
                first_option_start
                if option_index == 0
                else (
                    circles[option_index - 1]["global_y"] + circle["global_y"]
                )
                // 2
            )
            option_end = (
                (circle["global_y"] + circles[option_index + 1]["global_y"])
                // 2
                if option_index + 1 < len(circles)
                else question_end
            )
            option_lines = [
                line
                for line in region_lines
                if option_start <= line["global_y"] < option_end
            ]
            x_cut = circle["x"] + circle["radius"] + int(8 * config.dpi / 180)
            pieces = [
                _word_text_right_of(line, x_cut) for line in option_lines
            ]
            option_texts.append(_clean_option(" ".join(piece for piece in pieces if piece)))

        is_true_false = (
            len(option_texts) == 2
            and any(re.search(r"\bCerto\b", option, re.I) for option in option_texts)
            and any(re.search(r"\bErrado\b", option, re.I) for option in option_texts)
        )
        if is_true_false:
            option_texts = ["Certo", "Errado"]
            keys = ["C", "E"]
        else:
            keys = list("ABCDE")[: len(option_texts)]
        alternatives = [
            {"chave": key, "texto": text}
            for key, text in zip(keys, option_texts)
        ]

        subject, topics, topic_path = _classification(raw_category)
        role, area, specialty, shift = _derive_exam_fields(exam)
        answer = _normalize_answer_value(answers.get(start["number"], ""))
        # Fallback essencial: questões de Certo/Errado podem não ter círculos reconhecidos.
        if _TRUE_FALSE_HINT_RE.search(statement) or (answer in {"C", "E"} and is_true_false):
            option_texts = ["Certo", "Errado"]
            keys = ["C", "E"]
            alternatives = [
                {"chave": "C", "texto": "Certo"},
                {"chave": "E", "texto": "Errado"},
            ]
            is_true_false = True
        elif not alternatives:
            parsed_statement, parsed_options = _extract_options_from_text(statement)
            if len(parsed_options) >= 2:
                statement = parsed_statement
                alternatives = parsed_options
                keys = [str(item.get("chave", "")).upper() for item in alternatives]
        correct_index = keys.index(answer) if answer in keys else None

        question = {
            "id": start["source_code"],
            "numero_origem": start["number"],
            "codigo_origem": start["source_code"],
            "materia": subject,
            "assuntos": topics,
            "trilha_assuntos": topic_path,
            "banca": board,
            "ano": year,
            "orgao": agency,
            "prova": exam,
            "cargo": role,
            "area": area,
            "especialidade": specialty,
            "turno": shift,
            "tipo": "certo_errado" if is_true_false else "multipla_escolha",
            "enunciado": statement,
            "alternativas": alternatives,
            "gabarito": answer,
            "explicacao": "",
            "fonte": {
                "plataforma": config.platform,
                "arquivo": path.name,
                "caminho_arquivo": str(path.resolve()),
                "pagina_inicial": start["page"] + 1,
                "codigo": start["source_code"],
            },
            "telegram": {
                "modo": "quiz",
                "pergunta": statement,
                "opcoes": [item["texto"] for item in alternatives],
                "indice_correto": correct_index,
            },
            "ocr": {
                "metadados_brutos": raw_metadata,
                "categoria_bruta": raw_category,
                "texto_bruto": "\n".join(line.get("text", "") for line in region_lines),
            },
        }
        if taxonomy is not None:
            taxonomy.apply_to_question(question)
        question = deep_repair_question(
            question,
            taxonomy,
            allow_auto_approve=False,
            method="extracao_ocr_apurada",
        )

        confidence, alerts = _question_status(question)
        taxonomy_status = question.get("classificacao_planilha", {}).get("status")
        if taxonomy_status == "revisar":
            confidence = round(max(0.0, confidence - 0.05), 2)
            alerts.append("Classificação da planilha precisa de revisão")
        question["revisao"] = {
            "status": "aprovado_automaticamente" if confidence >= 0.90 else "pendente",
            "confianca": confidence,
            "alertas": alerts,
        }
        question["fingerprint"] = _fingerprint(question)
        questions.append(question)

    _progress(progress, 1.0, f"{len(questions)} questões extraídas de {path.name}")
    return {
        "schema": "questflow.questions.v1",
        "schema_version": 1,
        "source_file": path.name,
        "source_path": str(path),
        "extractor": "QuestFlow PDF Importer",
        "starts_found": len(starts),
        "answers_found": len(answers),
        "answer_ocr": answer_ocr,
        "taxonomy": taxonomy.source_name if taxonomy is not None else "",
        "markdown": markdown_bundle.as_dict() if markdown_bundle is not None else {},
        "questions": questions,
    }


def save_extraction_json(result: dict, output_path: str | Path) -> None:
    Path(output_path).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
