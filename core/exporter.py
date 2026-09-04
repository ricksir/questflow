from __future__ import annotations

import copy
from contextlib import closing
import csv
import hashlib
import json
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


QUESTFLOW_SCHEMA = "questflow.questions.v1"
QUESTFLOW_BANK_FORMAT = "questflow-question-bank"
QUESTFLOW_BANK_FORMAT_VERSION = 1
QUESTFLOW_TARGET_APP_VERSION = "0.7.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json(payload: Any, output_path: str | Path) -> Path:
    """Write strict UTF-8 JSON without BOM and validate it immediately."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    output.write_text(serialized, encoding="utf-8", newline="\n")
    json.loads(output.read_text(encoding="utf-8-sig"))
    return output


def export_json(questions: list[dict], output_path: str | Path) -> Path:
    """Technical/rich export used by the PDF Importer itself."""
    payload = {
        "schema": QUESTFLOW_SCHEMA,
        "schema_version": 1,
        "generated_at": utc_now(),
        "question_count": len(questions),
        "questions": questions,
    }
    return _write_json(payload, output_path)


def _alternative_objects(question: dict) -> list[dict[str, str]]:
    raw = question.get("alternativas", [])
    result: list[dict[str, str]] = []
    if isinstance(raw, dict):
        raw = [{"chave": key, "texto": value} for key, value in raw.items()]
    if not isinstance(raw, list):
        return result
    for index, item in enumerate(raw):
        default_key = chr(ord("A") + index)
        if isinstance(item, dict):
            key = str(
                item.get("chave")
                or item.get("letra")
                or item.get("key")
                or item.get("id")
                or default_key
            ).strip().upper()
            text = str(
                item.get("texto")
                or item.get("text")
                or item.get("label")
                or item.get("value")
                or ""
            ).strip()
        else:
            key = default_key
            text = str(item).strip()
            # Accept imported strings such as "A) text" without duplicating the letter.
            if len(text) >= 2 and text[0].upper() == default_key and text[1] in ").-:":
                text = text[2:].strip()
        if text:
            result.append({"chave": key or default_key, "texto": text})
    return result


def _answer_index(alternatives: list[dict[str, str]], answer: str) -> int | None:
    normalized = str(answer or "").strip().upper()
    for index, item in enumerate(alternatives):
        if item["chave"].upper() == normalized:
            return index
    try:
        numeric = int(normalized)
    except (TypeError, ValueError):
        return None
    return numeric if 0 <= numeric < len(alternatives) else None


def _answer_key(question: dict, alternatives: list[dict[str, str]]) -> str:
    raw = str(
        question.get("gabarito")
        or question.get("resposta")
        or question.get("answer")
        or question.get("correctAnswer")
        or ""
    ).strip()
    normalized = raw.upper()
    if any(item["chave"].upper() == normalized for item in alternatives):
        return normalized
    # Some banks store the complete correct alternative text.
    for item in alternatives:
        if item["texto"].strip().casefold() == raw.casefold():
            return item["chave"].upper()
    try:
        index = int(normalized)
    except (TypeError, ValueError):
        return normalized
    return alternatives[index]["chave"].upper() if 0 <= index < len(alternatives) else normalized


def _is_structurally_exportable(question: dict) -> bool:
    statement = str(question.get("enunciado") or question.get("statement") or "").strip()
    alternatives = _alternative_objects(question)
    answer = _answer_key(question, alternatives)
    return bool(statement and len(alternatives) >= 2 and answer)


def questflow_question(question: dict) -> dict:
    """Convert an internal rich record to the object used by QuestFlow 0.7.0.

    QuestFlow's native backup identifies duplicates from ``enunciado``,
    ``alternativas`` and ``resposta``. Therefore those three fields are always
    emitted in their simplest portable representation: statement string,
    alternative text array and answer letter.
    """
    source = question.get("fonte", {}) if isinstance(question.get("fonte"), dict) else {}
    alternatives = _alternative_objects(question)
    option_texts = [entry["texto"] for entry in alternatives]
    option_details = [
        {"letra": entry["chave"], "texto": entry["texto"]} for entry in alternatives
    ]
    answer = _answer_key(question, alternatives)
    answer_index = _answer_index(alternatives, answer)
    answer_text = option_texts[answer_index] if answer_index is not None else ""
    statement = str(
        question.get("enunciado")
        or question.get("statement")
        or question.get("question")
        or ""
    ).strip()
    topics = question.get("assuntos", [])
    if not isinstance(topics, list):
        topics = [str(topics)] if topics else []

    # Keep the native fields first. Additional metadata is plain JSON and is
    # ignored safely by QuestFlow builds that do not use it.
    return {
        "id": str(
            question.get("id")
            or question.get("codigo_origem")
            or question.get("database_uid")
            or question.get("fingerprint")
            or ""
        ),
        "enunciado": statement,
        "alternativas": option_texts,
        "resposta": answer,
        "explicacao": str(question.get("explicacao", "") or ""),
        "materia": str(question.get("materia", "") or ""),
        "assunto": str(question.get("assunto", "") or (topics[0] if topics else "")),
        "assuntos": [str(item) for item in topics if str(item).strip()],
        "aula": str(question.get("aula_planilha", "") or ""),
        "banca": str(question.get("banca", "") or ""),
        "ano": question.get("ano"),
        "orgao": str(question.get("orgao", "") or ""),
        "prova": str(question.get("prova", "") or ""),
        "cargo": str(question.get("cargo", "") or ""),
        "area": str(question.get("area", "") or ""),
        "especialidade": str(question.get("especialidade", "") or ""),
        "tipo": str(question.get("tipo", "") or ""),
        "codigo_origem": str(question.get("codigo_origem", "") or ""),
        "alternativas_detalhadas": option_details,
        "gabarito": answer,
        "resposta_texto": answer_text,
        "indice_resposta": answer_index,
        "fonte": {
            "plataforma": str(source.get("plataforma", "") or ""),
            "arquivo": str(source.get("arquivo", "") or ""),
            "pagina": source.get("pagina_inicial"),
            "codigo": str(source.get("codigo", "") or ""),
        },
        "fingerprint": str(question.get("fingerprint", "") or ""),
    }


def build_questflow_question_bank(questions: list[dict]) -> dict:
    """Build the exact top-level object exported by QuestFlow 0.7.0."""
    compatible = [questflow_question(item) for item in questions if _is_structurally_exportable(item)]
    return {
        "format": QUESTFLOW_BANK_FORMAT,
        "format_version": QUESTFLOW_BANK_FORMAT_VERSION,
        "app_version": QUESTFLOW_TARGET_APP_VERSION,
        "exported_at": utc_now(),
        "question_count": len(compatible),
        "questions": compatible,
    }


def count_exportable_questions(questions: list[dict]) -> int:
    return sum(1 for item in questions if _is_structurally_exportable(item))


def validate_questflow_question_bank(payload: Any) -> list[str]:
    """Return validation errors for the native QuestFlow question-bank format."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["O conteúdo raiz deve ser um objeto JSON."]
    if payload.get("format") != QUESTFLOW_BANK_FORMAT:
        errors.append(f'format deve ser "{QUESTFLOW_BANK_FORMAT}".')
    if payload.get("format_version") != QUESTFLOW_BANK_FORMAT_VERSION:
        errors.append(f"format_version deve ser {QUESTFLOW_BANK_FORMAT_VERSION}.")
    if not isinstance(payload.get("app_version"), str) or not payload.get("app_version"):
        errors.append("app_version deve ser um texto não vazio.")
    if not isinstance(payload.get("exported_at"), str) or not payload.get("exported_at"):
        errors.append("exported_at deve ser um texto ISO-8601 não vazio.")
    questions = payload.get("questions")
    if not isinstance(questions, list):
        errors.append("questions deve ser uma lista.")
        return errors
    if payload.get("question_count") != len(questions):
        errors.append("question_count não corresponde ao tamanho de questions.")
    for index, item in enumerate(questions, start=1):
        prefix = f"Questão {index}"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: deve ser um objeto.")
            continue
        if not str(item.get("enunciado", "")).strip():
            errors.append(f"{prefix}: enunciado ausente.")
        alternatives = item.get("alternativas")
        if not isinstance(alternatives, list) or len(alternatives) < 2:
            errors.append(f"{prefix}: alternativas deve conter ao menos 2 textos.")
        elif not all(isinstance(value, str) and value.strip() for value in alternatives):
            errors.append(f"{prefix}: todas as alternativas devem ser textos não vazios.")
        if not str(item.get("resposta", "")).strip():
            errors.append(f"{prefix}: resposta ausente.")
    return errors


def export_questflow_bank(questions: list[dict], output_path: str | Path) -> Path:
    output = Path(output_path)
    if output.suffix.lower() != ".json":
        output = output.with_suffix(".json")
    payload = build_questflow_question_bank(questions)
    errors = validate_questflow_question_bank(payload)
    if errors:
        raise ValueError("Base QuestFlow inválida antes da gravação:\n- " + "\n- ".join(errors[:20]))
    result = _write_json(payload, output)
    reloaded = json.loads(result.read_text(encoding="utf-8-sig"))
    errors = validate_questflow_question_bank(reloaded)
    if errors:
        raise ValueError("Base QuestFlow falhou na validação após a gravação.")
    return result


def export_csv(questions: list[dict], output_path: str | Path) -> Path:
    output = Path(output_path)
    fieldnames = [
        "codigo", "materia", "aula_planilha", "assunto", "assuntos",
        "status_classificacao", "confianca_classificacao", "fonte_taxonomia",
        "banca", "ano", "orgao", "prova", "cargo", "area", "especialidade",
        "tipo", "enunciado", "alternativa_a", "alternativa_b", "alternativa_c",
        "alternativa_d", "alternativa_e", "gabarito", "explicacao",
        "arquivo_origem", "pagina_origem", "status_revisao", "confianca", "fingerprint",
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for question in questions:
            alternatives = {item["chave"]: item["texto"] for item in _alternative_objects(question)}
            source = question.get("fonte", {}) if isinstance(question.get("fonte"), dict) else {}
            review = question.get("revisao", {}) if isinstance(question.get("revisao"), dict) else {}
            classification = question.get("classificacao_planilha", {}) if isinstance(question.get("classificacao_planilha"), dict) else {}
            writer.writerow({
                "codigo": question.get("codigo_origem", question.get("id", "")),
                "materia": question.get("materia", ""),
                "aula_planilha": question.get("aula_planilha", ""),
                "assunto": question.get("assunto", ""),
                "assuntos": " | ".join(question.get("assuntos", [])),
                "status_classificacao": classification.get("status", ""),
                "confianca_classificacao": classification.get("confianca", ""),
                "fonte_taxonomia": classification.get("fonte", ""),
                "banca": question.get("banca", ""), "ano": question.get("ano", ""),
                "orgao": question.get("orgao", ""), "prova": question.get("prova", ""),
                "cargo": question.get("cargo", ""), "area": question.get("area", ""),
                "especialidade": question.get("especialidade", ""), "tipo": question.get("tipo", ""),
                "enunciado": question.get("enunciado", ""),
                "alternativa_a": alternatives.get("A", ""), "alternativa_b": alternatives.get("B", ""),
                "alternativa_c": alternatives.get("C", ""), "alternativa_d": alternatives.get("D", ""),
                "alternativa_e": alternatives.get("E", ""), "gabarito": question.get("gabarito", ""),
                "explicacao": question.get("explicacao", ""), "arquivo_origem": source.get("arquivo", ""),
                "pagina_origem": source.get("pagina_inicial", ""), "status_revisao": review.get("status", ""),
                "confianca": review.get("confianca", ""), "fingerprint": question.get("fingerprint", ""),
            })
    return output


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_qflow_package(
    questions: list[dict], output_path: str | Path, source_database: str | Path | None = None,
) -> Path:
    """Export a complete ZIP backup. It is not the file imported by QuestFlow."""
    output = Path(output_path)
    if output.suffix.lower() != ".qflowpkg":
        output = output.with_suffix(".qflowpkg")
    with tempfile.TemporaryDirectory(prefix="questflow_export_") as temp_dir:
        temp = Path(temp_dir)
        technical_file = export_json(questions, temp / "questions-tecnico.json")
        native_file = export_questflow_bank(questions, temp / "QuestFlow-base-de-questoes.json")
        manifest = {
            "format": "QuestFlow Portable Question Package",
            "generated_at": utc_now(),
            "question_count": count_exportable_questions(questions),
            "files": {
                technical_file.name: {"sha256": _sha256(technical_file), "required": False},
                native_file.name: {
                    "sha256": _sha256(native_file), "required": True,
                    "questflow_desktop_compatible": True,
                },
            },
        }
        if source_database:
            database = Path(source_database)
            if database.exists() and database.stat().st_size:
                database_copy = temp / "questflow_questions.sqlite"
                with closing(sqlite3.connect(database, timeout=30)) as source:
                    with closing(sqlite3.connect(database_copy, timeout=30)) as target:
                        source.execute("PRAGMA busy_timeout = 30000")
                        target.execute("PRAGMA busy_timeout = 30000")
                        source.backup(target)
                        target.commit()
                manifest["files"][database_copy.name] = {"sha256": _sha256(database_copy), "required": False}
        (temp / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (temp / "LEIA-ME.txt").write_text(
            "Para importar no QuestFlow 0.7.0, extraia e selecione o arquivo "
            "QuestFlow-base-de-questoes.json. O .qflowpkg é somente um backup ZIP.\n",
            encoding="utf-8",
        )
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(temp.iterdir()):
                archive.write(item, item.name)
    return output


def _questions_from_payload(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise ValueError("Base QuestFlow inválida: o JSON não é um objeto nem uma lista.")
    for key in ("questions", "questoes", "questionBank", "bancoQuestoes"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    data = payload.get("data")
    if isinstance(data, dict):
        return _questions_from_payload(data)
    raise ValueError("Base válida como JSON, mas sem uma lista de questões reconhecível.")


def _to_internal_question(item: dict) -> dict:
    """Rehydrate a QuestFlow native object for editing in the PDF Importer."""
    result = copy.deepcopy(item)
    detailed = result.get("alternativas_detalhadas")
    if isinstance(detailed, list) and detailed:
        temp = dict(result)
        temp["alternativas"] = detailed
        alternatives = _alternative_objects(temp)
    else:
        alternatives = _alternative_objects(result)
        texts = [entry["texto"].strip().casefold() for entry in alternatives]
        if len(alternatives) == 2 and texts == ["certo", "errado"]:
            alternatives[0]["chave"] = "C"
            alternatives[1]["chave"] = "E"
    result["alternativas"] = alternatives
    result["gabarito"] = _answer_key(result, alternatives)
    result.setdefault("resposta", result["gabarito"])
    result.setdefault("aula_planilha", result.get("aula", ""))
    result.setdefault("codigo_origem", result.get("codigo_origem") or result.get("id") or "")
    result.setdefault("assuntos", [result.get("assunto", "")] if result.get("assunto") else [])
    source = result.get("fonte") if isinstance(result.get("fonte"), dict) else {}
    if "pagina" in source and "pagina_inicial" not in source:
        source["pagina_inicial"] = source.get("pagina")
    result["fonte"] = source
    result.setdefault("revisao", {"status": "pendente", "confianca": 1.0, "alertas": []})
    if not result.get("fingerprint"):
        basis = json.dumps(
            [result.get("enunciado", ""), result.get("alternativas", []), result.get("gabarito", "")],
            ensure_ascii=False,
            sort_keys=True,
        )
        result["fingerprint"] = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return result


def _read_old_zip_bundle(bundle: Path) -> dict:
    with zipfile.ZipFile(bundle, "r") as archive:
        names = set(archive.namelist())
        for preferred in (
            "QuestFlow-base-de-questoes.json",
            "QuestFlow_Banco_Questoes.qflow",
            "questions.json",
            "questions-tecnico.json",
        ):
            if preferred in names:
                payload = json.loads(archive.read(preferred).decode("utf-8-sig"))
                questions = [_to_internal_question(item) for item in _questions_from_payload(payload)]
                return {**(payload if isinstance(payload, dict) else {}), "questions": questions}
        raise ValueError("Pacote antigo inválido: nenhum arquivo de questões foi encontrado.")


def import_qflow_file(bundle_path: str | Path) -> dict:
    """Read native .json, legacy .qflow JSON/ZIP, or .qflowpkg backup."""
    bundle = Path(bundle_path)
    if not bundle.exists():
        raise ValueError("Arquivo de base não encontrado.")
    if zipfile.is_zipfile(bundle):
        return _read_old_zip_bundle(bundle)
    try:
        payload = json.loads(bundle.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError as error:
        raise ValueError("O arquivo não está em UTF-8.") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON inválido na linha {error.lineno}, coluna {error.colno}.") from error
    questions = [_to_internal_question(item) for item in _questions_from_payload(payload)]
    if isinstance(payload, list):
        payload = {"questions": questions}
    else:
        payload["questions"] = questions
    return payload


def convert_legacy_qflow(input_path: str | Path, output_path: str | Path) -> Path:
    payload = import_qflow_file(input_path)
    return export_questflow_bank(payload.get("questions", []), output_path)


# Backward-compatible names used by the existing UI.
def export_qflow_compatible(questions: list[dict], output_path: str | Path) -> Path:
    return export_questflow_bank(questions, output_path)


def build_questflow_database_payload(questions: list[dict]) -> dict:
    return build_questflow_question_bank(questions)


def questflow_compatible_question(question: dict) -> dict:
    return questflow_question(question)


def export_qflow_bundle(
    questions: list[dict], output_path: str | Path, source_database: str | Path | None = None,
) -> Path:
    del source_database
    return export_questflow_bank(questions, output_path)


def import_qflow_bundle(bundle_path: str | Path) -> dict:
    return import_qflow_file(bundle_path)
