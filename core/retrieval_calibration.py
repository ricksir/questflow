from __future__ import annotations

"""QuestFlow 6.8.2 · reranking calibrado e regressão contínua de retrieval.

A calibração é local, determinística e auditável. Perfis candidatos têm pesos
explícitos; nenhuma LLM escolhe pesos e nenhum perfil é promovido sem ação
humana. Baselines e histórico ficam em JSON/JSONL fora do schema SQLite.
"""

import json
import math
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RETRIEVAL_CALIBRATION_VERSION = "qf-retrieval-calibration-1"
_TOKEN_RE = re.compile(r"[a-záéíóúâêôãõç0-9]{4,}", re.I)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tokens(value: Any) -> set[str]:
    return {m.group(0).casefold() for m in _TOKEN_RE.finditer(str(value or ""))}


def _visual_expected(question: dict) -> bool:
    visual = question.get("contexto_visual") if isinstance(question.get("contexto_visual"), dict) else {}
    image = question.get("imagem_questao") if isinstance(question.get("imagem_questao"), dict) else {}
    return bool(visual or image.get("path") or str(question.get("source_file") or "").lower().endswith(".pdf"))


DEFAULT_PROFILE = {
    "id": "balanced-v1",
    "label": "Balanceado 6.8.2",
    "version": 1,
    "weights": {"original_score": 0.45, "query_overlap": 0.25, "grounding": 0.20, "visual_context": 0.10},
    "thresholds": {"score_drop_warn": 4.0, "recall_drop_warn": 5.0, "grounding_drop_warn": 3.0, "min_cases": 3},
    "source": "built_in",
}

CANDIDATE_PROFILES = [
    DEFAULT_PROFILE,
    {
        "id": "text-relevance-v1", "label": "Relevância textual", "version": 1,
        "weights": {"original_score": 0.52, "query_overlap": 0.30, "grounding": 0.15, "visual_context": 0.03},
        "thresholds": deepcopy(DEFAULT_PROFILE["thresholds"]), "source": "candidate_grid",
    },
    {
        "id": "grounding-first-v1", "label": "Grounding prioritário", "version": 1,
        "weights": {"original_score": 0.36, "query_overlap": 0.22, "grounding": 0.32, "visual_context": 0.10},
        "thresholds": deepcopy(DEFAULT_PROFILE["thresholds"]), "source": "candidate_grid",
    },
    {
        "id": "multimodal-context-v1", "label": "Contexto multimodal", "version": 1,
        "weights": {"original_score": 0.38, "query_overlap": 0.22, "grounding": 0.20, "visual_context": 0.20},
        "thresholds": deepcopy(DEFAULT_PROFILE["thresholds"]), "source": "candidate_grid",
    },
]


def profile_by_id(profile_id: str) -> dict | None:
    wanted = str(profile_id or "").strip()
    for profile in CANDIDATE_PROFILES:
        if profile["id"] == wanted:
            return deepcopy(profile)
    return None


def validate_profile(profile: dict) -> dict:
    if not isinstance(profile, dict):
        raise ValueError("Perfil de retrieval inválido.")
    weights = profile.get("weights") if isinstance(profile.get("weights"), dict) else {}
    required = ("original_score", "query_overlap", "grounding", "visual_context")
    values = {key: float(weights.get(key, 0) or 0) for key in required}
    if any(value < 0 or not math.isfinite(value) for value in values.values()):
        raise ValueError("Os pesos do reranking devem ser números não negativos.")
    total = sum(values.values())
    if total <= 0:
        raise ValueError("O perfil de reranking precisa ter pelo menos um peso positivo.")
    values = {key: round(value / total, 6) for key, value in values.items()}
    clean = deepcopy(profile)
    clean["weights"] = values
    clean.setdefault("thresholds", deepcopy(DEFAULT_PROFILE["thresholds"]))
    clean.setdefault("id", "custom")
    clean.setdefault("label", clean["id"])
    clean.setdefault("version", 1)
    return clean


def rerank_items(items: list[dict], *, query: str, question: dict | None = None, profile: dict | None = None) -> list[dict]:
    profile = validate_profile(profile or DEFAULT_PROFILE)
    weights = profile["weights"]
    q_tokens = _tokens(query)
    expected_visual = _visual_expected(question or {})
    raw_scores = []
    for item in items:
        scores = item.get("scores") if isinstance(item.get("scores"), dict) else {}
        try:
            raw_scores.append(max(0.0, float(scores.get("score", item.get("score", 0)) or 0)))
        except (TypeError, ValueError):
            raw_scores.append(0.0)
    max_raw = max(raw_scores or [0.0]) or 1.0
    ranked: list[dict] = []
    for index, item in enumerate(items):
        content_tokens = _tokens(item.get("content"))
        overlap = len(q_tokens & content_tokens) / max(1, len(q_tokens)) if q_tokens else 0.0
        original = raw_scores[index] / max_raw
        grounding = 1.0 if isinstance(item.get("grounding"), dict) and item.get("grounding") else 0.0
        modality = str(item.get("modality") or "text")
        visual_context = 1.0 if expected_visual and modality == "visual" else (0.35 if modality == "visual" else 0.0)
        score = (
            original * weights["original_score"]
            + overlap * weights["query_overlap"]
            + grounding * weights["grounding"]
            + visual_context * weights["visual_context"]
        )
        enriched = dict(item)
        enriched["reranking"] = {
            "version": RETRIEVAL_CALIBRATION_VERSION,
            "profile_id": profile["id"],
            "score": round(score, 6),
            "features": {
                "original_score": round(original, 6), "query_overlap": round(overlap, 6),
                "grounding": grounding, "visual_context": visual_context,
            },
        }
        ranked.append(enriched)
    ranked.sort(key=lambda item: (-float((item.get("reranking") or {}).get("score", 0)), str(item.get("modality") or ""), str(item.get("title") or "")))
    return ranked


class RetrievalCalibrationStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "profile_state.json"
        self.history_path = self.root / "profile_history.jsonl"
        self.baseline_path = self.root / "regression_baseline.json"

    def _read_json(self, path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else deepcopy(default)
        except (OSError, json.JSONDecodeError):
            return deepcopy(default)

    def current(self) -> dict:
        state = self._read_json(self.state_path, {})
        active = state.get("active") if isinstance(state, dict) and isinstance(state.get("active"), dict) else None
        return validate_profile(active or DEFAULT_PROFILE)

    def history(self, limit: int = 20) -> list[dict]:
        if not self.history_path.exists():
            return []
        try:
            lines = self.history_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in reversed(lines[-max(1, int(limit or 20)):]):
            try:
                item = json.loads(line)
                if isinstance(item, dict): out.append(item)
            except json.JSONDecodeError:
                pass
        return out

    def apply(self, profile: dict, *, reason: str = "human_approval") -> dict:
        profile = validate_profile(profile)
        previous = self.current()
        event = {"at": _utcnow(), "action": "apply", "reason": str(reason or "human_approval"), "previous": previous, "profile": profile}
        state = {"schema": "questflow.retrieval_profile_state.v1", "active": profile, "updated_at": event["at"]}
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return {"active": profile, "previous": previous, "event": event}

    def rollback(self) -> dict:
        history = self.history(limit=50)
        for event in history:
            previous = event.get("previous") if isinstance(event.get("previous"), dict) else None
            if previous:
                return self.apply(previous, reason="human_rollback")
        return {"active": self.current(), "previous": None, "warning": "Não existe perfil anterior para rollback."}

    def baseline(self) -> dict | None:
        value = self._read_json(self.baseline_path, None)
        return value if isinstance(value, dict) else None

    def save_baseline(self, snapshot: dict) -> dict:
        payload = dict(snapshot or {})
        payload["saved_at"] = _utcnow()
        payload["profile"] = self.current()
        self.baseline_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload


def benchmark_snapshot(report: dict, *, release: str = "") -> dict:
    backends = {str(item.get("backend")): item for item in (report.get("backends") or []) if isinstance(item, dict)}
    hybrid = backends.get("hybrid") or {}
    subjects: dict[str, list[dict]] = {}
    for case in report.get("items") or []:
        if not isinstance(case, dict): continue
        subject = str(case.get("subject") or "SEM_MATERIA")
        metric = next((x for x in (case.get("backends") or []) if isinstance(x, dict) and x.get("backend") == "hybrid"), None)
        if metric: subjects.setdefault(subject, []).append(metric)
    subject_rows = {}
    for subject, rows in subjects.items():
        recall = [float(x["recall"]) for x in rows if x.get("recall") is not None]
        subject_rows[subject] = {
            "cases": len(rows),
            "score": round(sum(float(x.get("composite_score") or 0) for x in rows) / len(rows), 1),
            "grounding_rate": round(sum(float(x.get("grounding_rate") or 0) for x in rows) / len(rows), 1),
            "recall": round(sum(recall) / len(recall), 1) if recall else None,
        }
    cases = int(report.get("cases") or 0)
    hybrid_snapshot = {key: hybrid.get(key) for key in ("score", "grounding_rate", "commentary_support", "precision", "recall", "visual_coverage", "path_safety")}
    # 6.10.3: ausência de amostra não é qualidade zero. Zero só é preservado
    # quando existe ao menos um caso realmente medido. Isso evita que Studio e
    # Mobile interpretem "sem avaliação" como desempenho ruim.
    if cases <= 0:
        hybrid_snapshot = {key: None for key in hybrid_snapshot}
    return {
        "schema": "questflow.retrieval_regression_baseline.v1", "release": str(release or ""),
        "benchmark_version": str(report.get("version") or ""), "cases": cases,
        "sample_status": str(report.get("sample_status") or ""),
        "hybrid": hybrid_snapshot,
        "subjects": subject_rows,
    }


def compare_regression(current: dict, baseline: dict | None, *, thresholds: dict | None = None) -> dict:
    thresholds = {**DEFAULT_PROFILE["thresholds"], **(thresholds or {})}
    if not baseline:
        return {"status": "sem_baseline", "alerts": [], "deltas": {}, "subjects": {}, "message": "Salve um baseline para habilitar regressão contínua."}
    cur = current.get("hybrid") if isinstance(current.get("hybrid"), dict) else {}
    old = baseline.get("hybrid") if isinstance(baseline.get("hybrid"), dict) else {}
    deltas = {}
    for key in ("score", "grounding_rate", "recall"):
        if cur.get(key) is not None and old.get(key) is not None:
            deltas[key] = round(float(cur[key]) - float(old[key]), 1)
    alerts = []
    checks = (("score", "score_drop_warn"), ("recall", "recall_drop_warn"), ("grounding_rate", "grounding_drop_warn"))
    for metric, threshold_key in checks:
        delta = deltas.get(metric)
        if delta is not None and delta < -float(thresholds[threshold_key]):
            alerts.append({"scope": "global", "metric": metric, "delta": delta, "threshold": -float(thresholds[threshold_key])})
    subject_results = {}
    old_subjects = baseline.get("subjects") if isinstance(baseline.get("subjects"), dict) else {}
    for subject, cur_row in (current.get("subjects") or {}).items():
        old_row = old_subjects.get(subject) if isinstance(old_subjects.get(subject), dict) else None
        if not old_row: continue
        row_deltas = {}
        for key in ("score", "grounding_rate", "recall"):
            if cur_row.get(key) is not None and old_row.get(key) is not None:
                row_deltas[key] = round(float(cur_row[key]) - float(old_row[key]), 1)
        subject_results[subject] = row_deltas
        for metric, threshold_key in checks:
            delta = row_deltas.get(metric)
            if delta is not None and delta < -float(thresholds[threshold_key]):
                alerts.append({"scope": "subject", "subject": subject, "metric": metric, "delta": delta, "threshold": -float(thresholds[threshold_key])})
    return {"status": "regressao" if alerts else "ok", "alerts": alerts, "deltas": deltas, "subjects": subject_results, "thresholds": thresholds}


class RetrievalCalibrationService:
    def __init__(self, knowledge: Any, governance: Any, store: RetrievalCalibrationStore):
        self.knowledge, self.governance, self.store = knowledge, governance, store

    def _score_profile(self, profile: dict, cases: list[dict]) -> dict:
        from core.grounding_benchmark import evaluate_retrieval
        metrics = []
        for case in cases:
            question = case.get("question") if isinstance(case.get("question"), dict) else {}
            uid = str(case.get("question_uid") or question.get("database_uid") or "")
            query = str(question.get("enunciado") or question.get("assunto") or "")[:1800]
            expected = case.get("sources") if isinstance(case.get("sources"), list) else []
            text = self.knowledge.retrieve_multimodal(uid, query, limit=8, backend="text").get("items", [])
            visual = self.knowledge.retrieve_multimodal(uid, query, limit=8, backend="visual").get("items", [])
            ranked = rerank_items([*visual, *text], query=query, question=question, profile=profile)[:8]
            metric = evaluate_retrieval(question=question, expected_sources=expected, result={"items": ranked}, backend="hybrid")
            metric["subject"] = str(case.get("subject") or question.get("materia") or "")
            metrics.append(metric)
        if not metrics:
            return {"profile": profile, "cases": 0, "score": 0.0, "recall": None, "grounding_rate": 0.0, "objective": 0.0}
        recalls = [float(m["recall"]) for m in metrics if m.get("recall") is not None]
        score = sum(float(m.get("composite_score") or 0) for m in metrics) / len(metrics)
        grounding = sum(float(m.get("grounding_rate") or 0) for m in metrics) / len(metrics)
        recall = sum(recalls) / len(recalls) if recalls else None
        # Objective is intentionally explicit and stable, not learned/opaque.
        objective = score * .70 + grounding * .10 + (recall if recall is not None else score) * .20
        return {"profile": profile, "cases": len(metrics), "score": round(score, 1), "recall": None if recall is None else round(recall, 1), "grounding_rate": round(grounding, 1), "objective": round(objective, 2)}

    def calibrate(self, *, limit: int = 30) -> dict:
        cases = self.governance.gold_questions(active_only=True)[:max(1, min(100, int(limit or 30)))]
        candidates = [self._score_profile(profile, cases) for profile in CANDIDATE_PROFILES]
        candidates.sort(key=lambda row: (-float(row.get("objective") or 0), str((row.get("profile") or {}).get("id") or "")))
        current = self.store.current()
        current_eval = next((row for row in candidates if row["profile"]["id"] == current["id"]), None) or self._score_profile(current, cases)
        best = candidates[0] if candidates else current_eval
        improvement = round(float(best.get("objective") or 0) - float(current_eval.get("objective") or 0), 2)
        min_cases = int(current.get("thresholds", {}).get("min_cases", 3) or 3)
        recommend = bool(len(cases) >= min_cases and best.get("profile", {}).get("id") != current.get("id") and improvement >= 1.0)
        return {
            "schema": "questflow.retrieval_calibration.v1", "version": RETRIEVAL_CALIBRATION_VERSION,
            "cases": len(cases), "sample_status": "suficiente" if len(cases) >= min_cases else "insuficiente",
            "objective": "70% composite + 20% recall (ou composite quando sem fonte ouro) + 10% grounding",
            "current": current_eval, "candidates": candidates, "recommended": best if recommend else current_eval,
            "recommended_change": recommend, "objective_gain": improvement if recommend else 0.0,
            "auto_apply": False, "caveat": "O QuestFlow apenas recomenda; aplicar pesos exige confirmação humana e mantém rollback versionado.",
        }


__all__ = [
    "RETRIEVAL_CALIBRATION_VERSION", "DEFAULT_PROFILE", "CANDIDATE_PROFILES", "RetrievalCalibrationStore",
    "RetrievalCalibrationService", "rerank_items", "profile_by_id", "benchmark_snapshot", "compare_regression",
]
