from __future__ import annotations

"""QuestFlow 6.8.1 · Benchmark Multimodal & Grounding Quality.

O benchmark é deliberadamente local e determinístico. Ele não chama LLM externa,
não altera o Learner Model e não cria um novo motor. As Questões Ouro fornecem a
referência editorial e o Knowledge Engine fornece os backends text/visual/hybrid.
"""

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

GROUNDING_BENCHMARK_VERSION = "qf-grounding-benchmark-1"
_TOKEN_RE = re.compile(r"[a-záéíóúâêôãõç0-9]{4,}", re.I)


def _tokens(value: Any) -> set[str]:
    return {m.group(0).casefold() for m in _TOKEN_RE.finditer(str(value or ""))}


def _sha(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8", errors="replace")).hexdigest()


def _source_keys(item: dict) -> set[str]:
    keys: set[str] = set()
    for field in ("chunk_id", "id", "source_ref", "source_id"):
        value = str(item.get(field) or "").strip().casefold()
        if value:
            keys.add(f"id:{value}")
    grounding = item.get("grounding") if isinstance(item.get("grounding"), dict) else {}
    for field in ("source_id", "source_ref"):
        value = str(grounding.get(field) or "").strip().casefold()
        if value:
            keys.add(f"id:{value}")
    title = " ".join(str(item.get(k) or "") for k in ("title", "source_label", "provider")).strip()
    if title:
        keys.add("title:" + " ".join(sorted(_tokens(title))))
    content = str(item.get("content") or "").strip()
    if content:
        keys.add("content:" + _sha(content))
    return keys


def _similar_source(a: dict, b: dict) -> bool:
    if _source_keys(a) & _source_keys(b):
        return True
    a_title = _tokens(" ".join(str(a.get(k) or "") for k in ("title", "source_label")))
    b_title = _tokens(" ".join(str(b.get(k) or "") for k in ("title", "source_label")))
    if a_title and b_title:
        overlap = len(a_title & b_title) / max(1, min(len(a_title), len(b_title)))
        if overlap >= .72:
            return True
    a_content = _tokens(str(a.get("content") or ""))
    b_content = _tokens(str(b.get("content") or ""))
    if a_content and b_content:
        overlap = len(a_content & b_content) / max(1, min(len(a_content), len(b_content)))
        return overlap >= .72
    return False


def _expected_visual(question: dict) -> bool:
    visual = question.get("contexto_visual") if isinstance(question.get("contexto_visual"), dict) else {}
    image = question.get("imagem_questao") if isinstance(question.get("imagem_questao"), dict) else {}
    return bool(visual or image.get("path") or str(question.get("source_file") or "").lower().endswith(".pdf"))


def _support_score(question: dict, items: list[dict]) -> float:
    reference = str(question.get("explicacao") or "").strip()
    if not reference:
        reference = str(question.get("enunciado") or "").strip()
    ref = _tokens(reference)
    if not ref:
        return 0.0
    evidence = _tokens(" ".join(str(item.get("content") or "") for item in items if isinstance(item, dict)))
    if not evidence:
        return 0.0
    coverage = len(ref & evidence) / max(1, len(ref))
    # Saturate at 60% lexical coverage: evidence may be concise/paraphrased.
    return round(min(100.0, coverage / .60 * 100.0), 1)


def _safe_local_paths(question: dict, result: dict) -> bool:
    serialized = json.dumps(result, ensure_ascii=False)
    candidates: list[str] = []
    image = question.get("imagem_questao") if isinstance(question.get("imagem_questao"), dict) else {}
    for value in (image.get("path"), question.get("source_file")):
        text = str(value or "").strip()
        if text:
            candidates.append(text)
    return not any(value in serialized for value in candidates)


def evaluate_retrieval(*, question: dict, expected_sources: list[dict], result: dict, backend: str) -> dict:
    items = [item for item in (result.get("items") or []) if isinstance(item, dict)] if isinstance(result, dict) else []
    expected = [item for item in (expected_sources or []) if isinstance(item, dict)]
    matched_retrieved = [item for item in items if any(_similar_source(item, ref) for ref in expected)] if expected else []
    matched_expected = [ref for ref in expected if any(_similar_source(item, ref) for item in items)] if expected else []
    precision = (len(matched_retrieved) / len(items) * 100.0) if expected and items else (0.0 if expected else None)
    recall = (len(matched_expected) / len(expected) * 100.0) if expected else None
    grounded = sum(1 for item in items if isinstance(item.get("grounding"), dict))
    grounding_rate = grounded / max(1, len(items)) * 100.0 if items else 0.0
    support = _support_score(question, items)
    visual_expected = _expected_visual(question)
    has_visual = any(str(item.get("modality") or "") == "visual" for item in items)
    visual_coverage = 100.0 if (not visual_expected or has_visual) else 0.0
    path_safe = _safe_local_paths(question, result if isinstance(result, dict) else {})

    weighted: list[tuple[float, float]] = [(grounding_rate, .30), (support, .35), (visual_coverage, .15), (100.0 if path_safe else 0.0, .10)]
    if precision is not None:
        weighted.append((precision, .05))
    if recall is not None:
        weighted.append((recall, .05))
    denom = sum(weight for _, weight in weighted) or 1.0
    composite = sum(value * weight for value, weight in weighted) / denom
    flags: list[str] = []
    if not items:
        flags.append("sem_evidencias_recuperadas")
    if items and grounding_rate < 100:
        flags.append("evidencia_sem_grounding")
    if visual_expected and not has_visual and backend in {"visual", "hybrid"}:
        flags.append("contexto_visual_nao_recuperado")
    if not path_safe:
        flags.append("caminho_local_exposto")
    if expected and (recall or 0) < 50:
        flags.append("baixo_recall_das_fontes_ouro")
    if support < 35:
        flags.append("baixo_suporte_ao_comentario_ouro")
    return {
        "backend": backend,
        "retrieved": len(items),
        "expected_sources": len(expected),
        "matched_sources": len(matched_expected),
        "precision": None if precision is None else round(precision, 1),
        "recall": None if recall is None else round(recall, 1),
        "grounding_rate": round(grounding_rate, 1),
        "commentary_support": support,
        "visual_expected": visual_expected,
        "visual_present": has_visual,
        "visual_coverage": round(visual_coverage, 1),
        "local_path_safe": path_safe,
        "composite_score": round(composite, 1),
        "flags": flags,
    }


def _aggregate(rows: list[dict], backend: str) -> dict:
    subset = [row for row in rows if row.get("backend") == backend]
    if not subset:
        return {"backend": backend, "cases": 0, "score": 0.0, "grounding_rate": 0.0, "commentary_support": 0.0, "precision": None, "recall": None, "visual_coverage": None, "flags": []}
    avg = lambda key: round(sum(float(row.get(key) or 0) for row in subset) / len(subset), 1)
    precision_values = [float(row["precision"]) for row in subset if row.get("precision") is not None]
    recall_values = [float(row["recall"]) for row in subset if row.get("recall") is not None]
    visual_rows = [row for row in subset if row.get("visual_expected")]
    flags: dict[str, int] = {}
    for row in subset:
        for flag in row.get("flags") or []:
            flags[str(flag)] = flags.get(str(flag), 0) + 1
    return {
        "backend": backend,
        "cases": len(subset),
        "score": avg("composite_score"),
        "grounding_rate": avg("grounding_rate"),
        "commentary_support": avg("commentary_support"),
        "precision": round(sum(precision_values) / len(precision_values), 1) if precision_values else None,
        "recall": round(sum(recall_values) / len(recall_values), 1) if recall_values else None,
        "visual_coverage": round(sum(float(row.get("visual_coverage") or 0) for row in visual_rows) / len(visual_rows), 1) if visual_rows else None,
        "path_safety": round(sum(1 for row in subset if row.get("local_path_safe")) / len(subset) * 100.0, 1),
        "flags": [{"code": key, "count": count} for key, count in sorted(flags.items(), key=lambda item: (-item[1], item[0]))],
    }


class MultimodalGroundingBenchmark:
    def __init__(self, knowledge: Any, governance: Any):
        self.knowledge = knowledge
        self.governance = governance

    def run(self, *, limit: int = 30) -> dict:
        cases = self.governance.gold_questions(active_only=True)[: max(1, min(100, int(limit or 30)))]
        run_id = str(uuid.uuid4())
        rows: list[dict] = []
        case_rows: list[dict] = []
        for case in cases:
            question = case.get("question") if isinstance(case.get("question"), dict) else {}
            uid = str(case.get("question_uid") or question.get("database_uid") or "")
            query = str(question.get("enunciado") or question.get("assunto") or "")[:1800]
            expected_sources = case.get("sources") if isinstance(case.get("sources"), list) else []
            backend_metrics: list[dict] = []
            for backend in ("text", "visual", "hybrid"):
                try:
                    result = self.knowledge.retrieve_multimodal(uid, query, limit=8, backend=backend)
                    metric = evaluate_retrieval(question=question, expected_sources=expected_sources, result=result, backend=backend)
                except Exception as error:
                    metric = {"backend": backend, "retrieved": 0, "expected_sources": len(expected_sources), "matched_sources": 0, "precision": None, "recall": None, "grounding_rate": 0.0, "commentary_support": 0.0, "visual_expected": _expected_visual(question), "visual_present": False, "visual_coverage": 0.0, "local_path_safe": True, "composite_score": 0.0, "flags": ["erro_backend"], "error": str(error)}
                metric["gold_id"] = str(case.get("id") or "")
                metric["question_uid"] = uid
                metric["source_code"] = str(case.get("source_code") or question.get("codigo_origem") or "")
                rows.append(metric)
                backend_metrics.append(metric)
            scores = {m["backend"]: float(m.get("composite_score") or 0) for m in backend_metrics}
            single_best = max(scores.get("text", 0.0), scores.get("visual", 0.0))
            case_rows.append({
                "gold_id": str(case.get("id") or ""),
                "question_uid": uid,
                "source_code": str(case.get("source_code") or question.get("codigo_origem") or ""),
                "subject": str(case.get("subject") or question.get("materia") or ""),
                "visual_expected": _expected_visual(question),
                "backends": backend_metrics,
                "hybrid_gain": round(scores.get("hybrid", 0.0) - single_best, 1),
            })
        aggregates = [_aggregate(rows, backend) for backend in ("text", "visual", "hybrid")]
        agg = {item["backend"]: item for item in aggregates}
        hybrid_score = float((agg.get("hybrid") or {}).get("score") or 0)
        single_best = max(float((agg.get("text") or {}).get("score") or 0), float((agg.get("visual") or {}).get("score") or 0))
        visual_cases = sum(1 for case in case_rows if case.get("visual_expected"))
        sample_status = "suficiente" if len(case_rows) >= 8 else "limitada" if len(case_rows) >= 3 else "insuficiente"
        if sample_status == "insuficiente":
            quality_label = "Amostra insuficiente"
        elif hybrid_score >= 82:
            quality_label = "Grounding forte"
        elif hybrid_score >= 68:
            quality_label = "Grounding adequado"
        else:
            quality_label = "Grounding requer atenção"
        recommendations: list[str] = []
        if not case_rows:
            recommendations.append("Adicione Questões Ouro antes de interpretar o benchmark.")
        if visual_cases < 3:
            recommendations.append("Inclua ao menos 3 Questões Ouro com imagem/PDF para avaliar o backend visual.")
        hybrid = agg.get("hybrid") or {}
        if hybrid.get("grounding_rate", 0) < 95:
            recommendations.append("Existem evidências híbridas sem grounding completo; revise os backends antes de ampliar uso automático.")
        if hybrid.get("recall") is not None and float(hybrid.get("recall") or 0) < 70:
            recommendations.append("O recall das fontes ouro está abaixo de 70%; priorize qualidade de indexação e reranking.")
        if hybrid_score < single_best:
            recommendations.append("O modo híbrido não superou o melhor backend isolado; revise a fusão antes de promovê-lo como padrão.")
        if not recommendations:
            recommendations.append("O benchmark não detectou bloqueadores; continue ampliando a amostra ouro e acompanhando regressões.")
        return {
            "schema": "questflow.multimodal_grounding_benchmark.v1",
            "version": GROUNDING_BENCHMARK_VERSION,
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cases": len(case_rows),
            "visual_cases": visual_cases,
            "sample_status": sample_status,
            "quality_label": quality_label,
            "backends": aggregates,
            "hybrid_gain": round(hybrid_score - single_best, 1),
            "items": case_rows,
            "recommendations": recommendations,
            "caveat": "Benchmark determinístico sobre Questões Ouro locais; mede recuperação/grounding e não substitui revisão humana nem demonstra causalidade pedagógica.",
        }


__all__ = ["GROUNDING_BENCHMARK_VERSION", "MultimodalGroundingBenchmark", "evaluate_retrieval"]
