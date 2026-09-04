from __future__ import annotations

"""Knowledge registry for Estratégia trail explanation PDFs.

QuestFlow only stores compact, derived metadata from the PDFs. The source PDFs are
not copied into the application package. This is enough to know which trails have
been explained, validate the task ranges and reproduce the spreadsheet-filling
rules without making normal startup depend on PDF libraries.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "questflow.trail-guides.v1"

# Derived from the supplied Trilha 00-05 documents and from the spreadsheet's
# own Instruções tab. Keep this intentionally concise: these are operating rules,
# not a reproduction of the course material.
DEFAULT_SHEET_KNOWLEDGE: dict[str, Any] = {
    "purpose": "Acompanhar execução das tarefas, evolução e desempenho por aula.",
    "sheet_roles": {
        "ciclo": {
            "known_names": ["CICLO_REG", "CICLO"],
            "role": "Registro das tarefas executadas em cada trilha.",
            "fill_fields": [
                "DATA",
                "CH EFETIVA",
                "TOT QUEST FEITAS",
                "TOT ACERTOS",
            ],
            "derived_fields": ["DESEMPENHO"],
            "study_evidence": ["DATA", "CH EFETIVA", "TOT QUEST FEITAS", "TOT ACERTOS"],
        },
        "mapa": {
            "known_names": ["MAPA_AF", "MAPA_AT", "MAPA"],
            "role": "Resumo de evolução e desempenho por matéria/aula.",
            "fill_fields": ["T+R = SIM quando a teoria e a revisão da aula forem concluídas", "QTD EXE", "ACERTOS"],
            "derived_fields": ["DES (%)", "MÉDIA", "gráfico de evolução"],
        },
    },
    "workflow": [
        "Executar as tarefas na ordem da trilha, adaptando apenas quando necessário.",
        "Registrar no CICLO a tarefa à medida que ela for realizada.",
        "Usar os exercícios e acertos para acompanhar o desempenho.",
        "Marcar a aula concluída no MAPA quando teoria e revisão estiverem finalizadas.",
        "Revisitar questões erradas nas tarefas de revisão de erros.",
    ],
    "trail_update_rule": "Novas trilhas acrescentam novas tarefas ao CICLO e ampliam o planejamento do MAPA.",
}

# Metadata derived from the six PDFs supplied by the user in this conversation.
# The SHA-256 values let future imports recognize the same documents without
# storing/repackaging the PDFs themselves.
DEFAULT_GUIDES: list[dict[str, Any]] = [
    {
        "trail": 0,
        "source_name": "curso-373719-trilha-00-d1f4-completo.pdf",
        "sha256": "b69307836e9647b55b3171367fc765454c6c296e6f8c134deae5735d89f12a31",
        "pages": 64,
        "task_min": 1,
        "task_max": 25,
        "task_count": 25,
        "subjects": ["DIREITO TRIBUTÁRIO", "FLUÊNCIA EM DADOS", "DIREITO ADMINISTRATIVO", "RACIOCÍNIO LÓGICO MATEMÁTICO", "DIREITO CONSTITUCIONAL", "AUDITORIA", "PORTUGUÊS", "CONTABILIDADE GERAL"],
    },
    {
        "trail": 1,
        "source_name": "curso-373719-trilha-01-0aa2-completo.pdf",
        "sha256": "04d60e8fe57feda6fd3c863b463913a303eafbdc7ba5cd319d6d502ed9bf84af",
        "pages": 48,
        "task_min": 26,
        "task_max": 50,
        "task_count": 25,
        "subjects": ["FLUÊNCIA EM DADOS", "DIREITO ADMINISTRATIVO", "RACIOCÍNIO LÓGICO MATEMÁTICO", "DIREITO CONSTITUCIONAL", "PORTUGUÊS", "DIREITO TRIBUTÁRIO", "CONTABILIDADE GERAL", "AUDITORIA"],
    },
    {
        "trail": 2,
        "source_name": "curso-373719-trilha-02-20fc-completo.pdf",
        "sha256": "1abf077b72fda247c328d279061be14f7341c36d26dde4d8a85d0cd8a8e02e3e",
        "pages": 50,
        "task_min": 51,
        "task_max": 75,
        "task_count": 25,
        "subjects": ["FLUÊNCIA EM DADOS", "DIREITO ADMINISTRATIVO", "PORTUGUÊS", "RACIOCÍNIO LÓGICO MATEMÁTICO", "DIREITO CONSTITUCIONAL", "CONTABILIDADE GERAL", "AUDITORIA", "DIREITO TRIBUTÁRIO"],
    },
    {
        "trail": 3,
        "source_name": "curso-373719-trilha-03-2cbd-completo.pdf",
        "sha256": "ece2530ac5d0f91ee346d8b311ed5a9df4da948151a728717395ac2a8e762bd5",
        "pages": 44,
        "task_min": 76,
        "task_max": 100,
        "task_count": 25,
        "subjects": ["AUDITORIA", "DIREITO CONSTITUCIONAL", "FLUÊNCIA EM DADOS", "DIREITO ADMINISTRATIVO", "PORTUGUÊS", "DIREITO TRIBUTÁRIO", "CONTABILIDADE GERAL", "RACIOCÍNIO LÓGICO MATEMÁTICO"],
    },
    {
        "trail": 4,
        "source_name": "curso-373719-trilha-04-0193-completo.pdf",
        "sha256": "aecc5f24de804822af9e616891e1bc70503e7fc59571107405782c781cbe46af",
        "pages": 47,
        "task_min": 101,
        "task_max": 125,
        "task_count": 25,
        "subjects": ["DIREITO ADMINISTRATIVO", "PORTUGUÊS", "AUDITORIA", "DIREITO CONSTITUCIONAL", "CONTABILIDADE GERAL", "DIREITO TRIBUTÁRIO", "RACIOCÍNIO LÓGICO MATEMÁTICO", "FLUÊNCIA EM DADOS"],
    },
    {
        "trail": 5,
        "source_name": "curso-373719-trilha-05-bc60-completo.pdf",
        "sha256": "2674cd920e94800c925ef7a90c0f51205bf840feed86270158882d07ea4ff684",
        "pages": 40,
        "task_min": 126,
        "task_max": 150,
        "task_count": 25,
        "subjects": ["PORTUGUÊS", "DIREITO CONSTITUCIONAL", "CONTABILIDADE GERAL", "DIREITO ADMINISTRATIVO", "FLUÊNCIA EM DADOS", "DIREITO TRIBUTÁRIO", "RACIOCÍNIO LÓGICO MATEMÁTICO", "AUDITORIA"],
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def trail_number(value: Any) -> int | None:
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    match = re.search(r"\bTRILHA\s*0*(\d{1,3})\b", text, re.I)
    if match:
        return int(match.group(1))
    if re.fullmatch(r"\d{1,3}", text):
        return int(text)
    return None


def trail_label(number: int | None) -> str:
    if number is None:
        return "Trilha não identificada"
    return f"Trilha {int(number):02d}"


def default_registry() -> dict[str, Any]:
    now = utc_now()
    return {
        "schema": SCHEMA,
        "schema_version": 1,
        "generated_at": now,
        "updated_at": now,
        "knowledge": DEFAULT_SHEET_KNOWLEDGE,
        "guides": [dict(item, imported_at=now, origin="documentos_incorporados_5.5.2") for item in DEFAULT_GUIDES],
    }


def _normalize_registry(payload: dict[str, Any] | None) -> dict[str, Any]:
    base = default_registry()
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        return base
    guides_by_trail: dict[int, dict[str, Any]] = {
        int(item["trail"]): dict(item)
        for item in base["guides"]
        if isinstance(item, dict) and isinstance(item.get("trail"), int)
    }
    for raw in payload.get("guides", []):
        if not isinstance(raw, dict):
            continue
        number = trail_number(raw.get("trail"))
        if number is None:
            continue
        guides_by_trail[number] = dict(raw, trail=number)
    base["guides"] = [guides_by_trail[key] for key in sorted(guides_by_trail)]
    if isinstance(payload.get("knowledge"), dict):
        # Preserve future locally imported knowledge while ensuring the core
        # rules from 00-05 are never lost by an older registry file.
        merged = dict(DEFAULT_SHEET_KNOWLEDGE)
        merged.update(payload["knowledge"])
        base["knowledge"] = merged
    base["generated_at"] = str(payload.get("generated_at") or base["generated_at"])
    base["updated_at"] = str(payload.get("updated_at") or base["updated_at"])
    return base


def load_registry(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if target.exists():
        try:
            return _normalize_registry(json.loads(target.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return default_registry()


def save_registry(payload: dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_registry(payload)
    normalized["updated_at"] = utc_now()
    target.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def ensure_registry(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    payload = load_registry(target)
    if not target.exists():
        save_registry(payload, target)
    return payload


def _task_is_studied(task: dict[str, Any]) -> bool:
    if bool(task.get("estudado")):
        return True
    numeric_keys = ("ch_efetiva_min", "questoes_feitas", "acertos")
    for key in numeric_keys:
        try:
            if float(task.get(key, 0) or 0) > 0:
                return True
        except (TypeError, ValueError):
            pass
    return bool(str(task.get("data", "") or "").strip())


def guide_status_for_tasks(tasks: Iterable[dict[str, Any]], registry: dict[str, Any]) -> dict[str, Any]:
    guides = [item for item in registry.get("guides", []) if isinstance(item, dict)]
    available = sorted({int(item.get("trail")) for item in guides if trail_number(item.get("trail")) is not None})
    available_set = set(available)
    contiguous = -1
    for number in range(0, max(available, default=-1) + 1):
        if number not in available_set:
            break
        contiguous = number

    studied_by_trail: dict[int, dict[str, Any]] = {}
    for raw in tasks or []:
        task = dict(raw)
        if not _task_is_studied(task):
            continue
        number = trail_number(task.get("trilha"))
        if number is None:
            continue
        bucket = studied_by_trail.setdefault(number, {"trail": number, "contents": 0, "subjects": set(), "tasks": []})
        bucket["contents"] += 1
        subject = str(task.get("materia", "") or "").strip()
        if subject:
            bucket["subjects"].add(subject)
        task_number = str(task.get("tarefa", "") or "").strip()
        if task_number and task_number not in bucket["tasks"]:
            bucket["tasks"].append(task_number)

    missing: list[dict[str, Any]] = []
    for number in sorted(studied_by_trail):
        if number in available_set:
            continue
        bucket = studied_by_trail[number]
        missing.append(
            {
                "trail": number,
                "label": trail_label(number),
                "studied_contents": int(bucket["contents"]),
                "subjects": sorted(bucket["subjects"]),
                "tasks": bucket["tasks"][:50],
                "message": (
                    f"Você já registrou estudo na {trail_label(number)}, mas o PDF explicativo dessa trilha "
                    "ainda não foi incorporado ao QuestFlow. Adicione o PDF para completar a referência da trilha."
                ),
            }
        )

    if available:
        if available == list(range(min(available), max(available) + 1)) and min(available) == 0:
            available_label = f"Trilhas 00 a {max(available):02d}"
        else:
            available_label = ", ".join(trail_label(value) for value in available)
    else:
        available_label = "Nenhuma trilha"

    next_expected = contiguous + 1 if contiguous >= 0 else 0
    return {
        "available_trails": available,
        "available_label": available_label,
        "documented_through": contiguous,
        "documented_through_label": trail_label(contiguous) if contiguous >= 0 else "Nenhuma",
        "next_expected_trail": next_expected,
        "next_expected_label": trail_label(next_expected),
        "studied_trails": sorted(studied_by_trail),
        "missing_studied_trails": missing,
        "missing_count": len(missing),
        "needs_attention": bool(missing),
        "knowledge": registry.get("knowledge", DEFAULT_SHEET_KNOWLEDGE),
    }


def _pdf_metadata(path: Path) -> dict[str, Any]:
    """Extract only structural metadata from a trail PDF, lazily importing PyMuPDF."""
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"{path.name}: selecione um arquivo PDF da trilha.")
    try:
        import pymupdf  # type: ignore
    except Exception as error:  # pragma: no cover - dependency is part of QuestFlow runtime
        raise RuntimeError("PyMuPDF não está disponível para ler o PDF da trilha.") from error

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pymupdf.open(path) as document:
        pages = int(document.page_count)
        first_text = "\n".join(document.load_page(index).get_text("text") for index in range(min(pages, 5)))
        number = trail_number(first_text) or trail_number(path.stem.replace("-", " ").replace("_", " "))
        if number is None:
            raise ValueError(f"{path.name}: não foi possível identificar o número da trilha.")
        chunks = [first_text]
        # Task headings and the summary are spread throughout the PDFs. Full text
        # extraction happens only during this explicit import action, never at startup.
        for index in range(5, pages):
            chunks.append(document.load_page(index).get_text("text"))
        text = "\n".join(chunks)

    task_numbers = sorted({int(value) for value in re.findall(r"(?im)^\s*TAREFA\s+(\d{1,4})\s*$", text)})
    subjects: list[str] = []
    for match in re.finditer(r"(?im)^\s*TAREFA\s+\d{1,4}\s*\n\s*([^\n]{3,90})", text):
        subject = re.sub(r"\s+", " ", match.group(1)).strip().upper()
        if subject and subject not in subjects and "TRILHA" not in subject:
            subjects.append(subject)

    return {
        "trail": number,
        "source_name": path.name,
        "sha256": digest,
        "pages": pages,
        "task_min": min(task_numbers) if task_numbers else None,
        "task_max": max(task_numbers) if task_numbers else None,
        "task_count": len(task_numbers),
        "subjects": subjects[:40],
        "imported_at": utc_now(),
        "origin": "pdf_adicionado_pelo_usuario",
    }


def import_guide_pdfs(paths: Iterable[str | Path], registry_path: str | Path) -> dict[str, Any]:
    registry = ensure_registry(registry_path)
    by_trail: dict[int, dict[str, Any]] = {
        int(item["trail"]): dict(item)
        for item in registry.get("guides", [])
        if isinstance(item, dict) and trail_number(item.get("trail")) is not None
    }
    imported: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for raw in paths or []:
        path = Path(raw)
        try:
            if not path.exists() or not path.is_file():
                raise ValueError("arquivo não encontrado")
            metadata = _pdf_metadata(path)
            number = int(metadata["trail"])
            by_trail[number] = metadata
            imported.append(metadata)
        except Exception as error:
            errors.append({"path": str(path), "error": str(error)})

    registry["guides"] = [by_trail[key] for key in sorted(by_trail)]
    save_registry(registry, registry_path)
    status = guide_status_for_tasks([], registry)
    return {
        "ok": bool(imported) and not errors,
        "imported": imported,
        "errors": errors,
        "registry": registry,
        "status": status,
    }
