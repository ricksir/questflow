from __future__ import annotations

"""QuestFlow 6.8.3 · observabilidade de retrieval e expansão assistida do dataset Ouro.

A camada é local, determinística e não altera pesos, questões ou Questões Ouro
sem ação humana. Histórico e fingerprints ficam fora do schema SQLite.
"""

import csv
import hashlib
import io
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RETRIEVAL_OBSERVABILITY_VERSION = "qf-retrieval-observability-2"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8", errors="ignore")).hexdigest()


def compare_index_drift(current: dict, previous: dict | None) -> dict:
    if not previous:
        return {
            "status": "baseline", "added_chunks": 0, "removed_chunks": 0, "changed_chunks": 0,
            "added_sources": 0, "removed_sources": 0, "changed_sources": 0,
            "coverage_delta": None, "message": "Primeiro snapshot do índice; drift será medido na próxima observação.",
        }
    cur_chunks = current.get("chunk_fingerprints") if isinstance(current.get("chunk_fingerprints"), dict) else {}
    old_chunks = previous.get("chunk_fingerprints") if isinstance(previous.get("chunk_fingerprints"), dict) else {}
    cur_sources = current.get("source_fingerprints") if isinstance(current.get("source_fingerprints"), dict) else {}
    old_sources = previous.get("source_fingerprints") if isinstance(previous.get("source_fingerprints"), dict) else {}
    added_chunks = set(cur_chunks) - set(old_chunks)
    removed_chunks = set(old_chunks) - set(cur_chunks)
    common_chunks = set(cur_chunks) & set(old_chunks)
    changed_chunks = {key for key in common_chunks if cur_chunks.get(key) != old_chunks.get(key)}
    added_sources = set(cur_sources) - set(old_sources)
    removed_sources = set(old_sources) - set(cur_sources)
    common_sources = set(cur_sources) & set(old_sources)
    changed_sources = {key for key in common_sources if cur_sources.get(key) != old_sources.get(key)}
    old_coverage = previous.get("coverage")
    cur_coverage = current.get("coverage")
    coverage_delta = None
    if old_coverage is not None and cur_coverage is not None:
        coverage_delta = round(float(cur_coverage) - float(old_coverage), 1)
    total_changes = sum(map(len, (added_chunks, removed_chunks, changed_chunks, added_sources, removed_sources, changed_sources)))
    return {
        "status": "drift" if total_changes or (coverage_delta is not None and abs(coverage_delta) >= .1) else "stable",
        "added_chunks": len(added_chunks), "removed_chunks": len(removed_chunks), "changed_chunks": len(changed_chunks),
        "added_sources": len(added_sources), "removed_sources": len(removed_sources), "changed_sources": len(changed_sources),
        "coverage_delta": coverage_delta,
        "message": "Mudanças no índice detectadas." if total_changes else "Índice estável em relação ao snapshot anterior.",
    }


class RetrievalObservabilityStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.history_path = self.root / "observability_history.jsonl"
        self.index_state_path = self.root / "index_observability_state.json"

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else deepcopy(default)
        except (OSError, json.JSONDecodeError):
            return deepcopy(default)

    def index_state(self) -> dict | None:
        value = self._read_json(self.index_state_path, None)
        return value if isinstance(value, dict) else None

    def history(self, limit: int = 100) -> list[dict]:
        if not self.history_path.exists():
            return []
        try:
            lines = self.history_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out: list[dict] = []
        for line in reversed(lines[-max(1, min(1000, int(limit or 100))):]):
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    out.append(item)
            except json.JSONDecodeError:
                continue
        return out

    def record(self, *, retrieval: dict, index_snapshot: dict, release: str, profile: dict, force: bool = False) -> dict:
        previous_index = self.index_state()
        drift = compare_index_drift(index_snapshot, previous_index)
        hybrid = retrieval.get("hybrid") if isinstance(retrieval.get("hybrid"), dict) else {}
        entry = {
            "schema": "questflow.retrieval_observability_event.v1",
            "version": RETRIEVAL_OBSERVABILITY_VERSION,
            "at": _utcnow(), "release": str(release or ""),
            "profile_id": str(profile.get("id") or ""), "profile_label": str(profile.get("label") or ""),
            "evaluation_id": str(retrieval.get("evaluation_id") or ""),
            "cases": int(retrieval.get("cases") or 0), "sample_status": str(retrieval.get("sample_status") or ""),
            "score": hybrid.get("score"), "recall": hybrid.get("recall"), "grounding_rate": hybrid.get("grounding_rate"),
            "index_coverage": index_snapshot.get("coverage"), "rag_chunks": index_snapshot.get("rag_chunks"),
            "sources": index_snapshot.get("source_count"), "subjects": retrieval.get("subjects") or {}, "drift": drift,
        }
        latest = self.history(limit=1)
        fingerprint_payload = {k: entry.get(k) for k in ("release", "profile_id", "cases", "score", "recall", "grounding_rate", "index_coverage", "rag_chunks", "sources")}
        fingerprint_payload["index_digest"] = index_snapshot.get("index_digest")
        fingerprint = _hash(json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=False))
        entry["fingerprint"] = fingerprint
        recorded = True
        if latest and not force and latest[0].get("fingerprint") == fingerprint and str(latest[0].get("at") or "")[:10] == str(entry.get("at") or "")[:10]:
            recorded = False
        if recorded:
            with self.history_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        state = dict(index_snapshot)
        state["observed_at"] = entry["at"]
        self.index_state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"recorded": recorded, "entry": entry, "drift": drift}


def _release_comparison(history: list[dict], fallback_baseline: dict | None = None) -> dict:
    by_release: dict[str, dict] = {}
    for row in history:
        release = str(row.get("release") or "sem_release")
        if release not in by_release:
            by_release[release] = row
    rows = list(by_release.values())
    if len(rows) < 2 and fallback_baseline and isinstance(fallback_baseline, dict):
        hybrid = fallback_baseline.get("hybrid") if isinstance(fallback_baseline.get("hybrid"), dict) else {}
        baseline_row = {
            "at": fallback_baseline.get("saved_at"), "release": fallback_baseline.get("release") or "baseline",
            "profile_id": ((fallback_baseline.get("profile") or {}).get("id") if isinstance(fallback_baseline.get("profile"),dict) else "baseline"),
            "cases": fallback_baseline.get("cases"), "score": hybrid.get("score"), "recall": hybrid.get("recall"),
            "grounding_rate": hybrid.get("grounding_rate"), "index_coverage": None, "drift": {"status":"baseline"},
        }
        if not rows or str(baseline_row.get("release")) != str(rows[0].get("release")):
            rows.append(baseline_row)
    if len(rows) < 2:
        return {"available": False, "current": rows[0] if rows else None, "previous": None, "deltas": {}}
    current, previous = rows[0], rows[1]
    deltas = {}
    for key in ("score", "recall", "grounding_rate", "index_coverage"):
        if current.get(key) is not None and previous.get(key) is not None:
            deltas[key] = round(float(current[key]) - float(previous[key]), 1)
    return {"available": True, "current": current, "previous": previous, "deltas": deltas}


class RetrievalObservabilityService:
    def __init__(self, knowledge: Any, governance: Any, editorial: Any, store: RetrievalObservabilityStore):
        self.knowledge, self.governance, self.editorial, self.store = knowledge, governance, editorial, store

    def _retrieval_snapshot(self, limit: int = 30) -> dict:
        from core.grounding_benchmark import MultimodalGroundingBenchmark
        from core.retrieval_calibration import benchmark_snapshot
        report = MultimodalGroundingBenchmark(self.knowledge, self.governance).run(limit=max(1, min(100, int(limit or 30))))
        return benchmark_snapshot(report)

    def _dashboard_payload(self, *, release: str, retrieval: dict, index_snapshot: dict, drift: dict, history: list[dict], recorded: bool, snapshot_entry: dict | None = None) -> dict:
        profile = self.knowledge.retrieval_calibration_store.current()
        baseline_getter = getattr(self.knowledge.retrieval_calibration_store, "baseline", None)
        fallback_baseline = baseline_getter() if callable(baseline_getter) else None
        engine = {
            "id": str(getattr(self.knowledge, "engine_id", "knowledge_engine") or "knowledge_engine"),
            "name": str(getattr(self.knowledge, "name", "Knowledge Engine") or "Knowledge Engine"),
            "version": str(getattr(self.knowledge, "version", "") or ""),
        }
        return {
            "schema": "questflow.retrieval_observability.v2", "version": RETRIEVAL_OBSERVABILITY_VERSION,
            "release": str(release or ""), "engine": engine, "profile": profile, "retrieval": retrieval,
            "index": {k: v for k, v in index_snapshot.items() if k not in {"chunk_fingerprints", "source_fingerprints"}},
            "drift": drift or {}, "history": history[:40],
            "release_comparison": _release_comparison(history, fallback_baseline),
            "recorded": bool(recorded),
            "snapshot_release": str((snapshot_entry or {}).get("release") or ""),
            "snapshot_at": (snapshot_entry or {}).get("at"),
            "snapshot_current": bool(snapshot_entry and str((snapshot_entry or {}).get("release") or "") == str(release or "")),
            "caveat": "Leitura instantânea do último snapshot registrado. Benchmarks só são executados por ação explícita; alertas de drift não alteram pesos, fontes nem o conjunto Ouro automaticamente.",
        }

    @staticmethod
    def _retrieval_from_entry(entry: dict | None) -> dict:
        row = entry if isinstance(entry, dict) else {}
        cases = int(row.get("cases") or 0)
        hybrid = {
            "score": row.get("score"), "recall": row.get("recall"),
            "grounding_rate": row.get("grounding_rate"),
        }
        if cases <= 0:
            hybrid = {"score": None, "recall": None, "grounding_rate": None}
        return {
            "cases": cases,
            "sample_status": str(row.get("sample_status") or "insuficiente"),
            "hybrid": hybrid,
            "subjects": row.get("subjects") if isinstance(row.get("subjects"), dict) else {},
        }

    def latest_dashboard(self, *, release: str) -> dict:
        """Consulta estritamente read-only do Metrics Snapshot Store.

        A leitura não toca o Knowledge Engine, não percorre chunks e não executa
        benchmark. O estado do índice exibido é o do último snapshot persistido.
        """
        history = self.store.history(limit=120)
        latest = history[0] if history else None
        retrieval = self._retrieval_from_entry(latest)
        index_snapshot = self.store.index_state() or {
            "coverage": None, "rag_chunks": None, "source_count": None,
            "index_digest": None, "chunk_fingerprints": {}, "source_fingerprints": {},
        }
        drift = (latest or {}).get("drift") if isinstance((latest or {}).get("drift"), dict) else {
            "status": "not_evaluated", "changed_chunks": 0, "changed_sources": 0,
            "message": "Ainda não existe snapshot persistido para medir drift.",
        }
        payload = self._dashboard_payload(
            release=release, retrieval=retrieval, index_snapshot=index_snapshot, drift=drift,
            history=history, recorded=False, snapshot_entry=latest,
        )
        payload["snapshot_store_only"] = True
        payload["caveat"] = (
            "Leitura do Metrics Snapshot Store. Abrir esta tela não consulta o índice RAG nem executa benchmark; "
            "use Reavaliar para produzir um novo snapshot pelo Evaluator Worker."
        )
        return payload

    def record_snapshot(self, *, release: str, retrieval: dict, index_snapshot: dict, force_record: bool = False) -> dict:
        """Persiste uma avaliação já calculada pelo Evaluator Worker.

        Este método evita que Observabilidade e Quality Gates executem benchmarks
        independentes e garante que ambos enxerguem exatamente a mesma amostra.
        """
        profile = self.knowledge.retrieval_calibration_store.current()
        observation = self.store.record(
            retrieval=retrieval, index_snapshot=index_snapshot, release=release,
            profile=profile, force=force_record,
        )
        history = self.store.history(limit=120)
        entry = observation.get("entry") if isinstance(observation, dict) else None
        return self._dashboard_payload(
            release=release, retrieval=retrieval, index_snapshot=index_snapshot,
            drift=observation.get("drift") or {}, history=history,
            recorded=bool(observation.get("recorded")), snapshot_entry=entry,
        )

    def dashboard(self, *, release: str, limit: int = 30, record: bool = True, force_record: bool = False) -> dict:
        """Compatibilidade de baixo nível para testes/CLI legados.

        O aplicativo não chama este caminho desde 6.11.0; avaliações normais passam
        exclusivamente pelo RetrievalHealthService/Evaluator Worker.
        """
        retrieval = self._retrieval_snapshot(limit=limit)
        index_snapshot = self.knowledge.observability_snapshot()
        if record:
            return self.record_snapshot(
                release=release, retrieval=retrieval, index_snapshot=index_snapshot,
                force_record=force_record,
            )
        history = self.store.history(limit=120)
        drift = compare_index_drift(index_snapshot, self.store.index_state())
        return self._dashboard_payload(
            release=release, retrieval=retrieval, index_snapshot=index_snapshot, drift=drift,
            history=history, recorded=False, snapshot_entry=None,
        )

    def suggest_gold_expansion(self, limit: int = 12) -> dict:
        gold = self.governance.gold_questions(active_only=True)
        gold_uids = {str(item.get("question_uid") or "") for item in gold}
        subject_counts: dict[str, int] = {}
        for item in gold:
            subject = str(item.get("subject") or "SEM_MATERIA")
            subject_counts[subject] = subject_counts.get(subject, 0) + 1
        candidates = []
        for row in self.editorial.question_candidates(limit=200):
            uid = str(row.get("uid") or "")
            if not uid or uid in gold_uids or not str(row.get("answer") or "").strip():
                continue
            subject = str(row.get("subject") or "SEM_MATERIA")
            try:
                quality = float(row.get("quality_score") or 0)
            except (TypeError, ValueError):
                quality = 0.0
            review = str(row.get("review_status") or "").casefold()
            commentary = str(row.get("commentary_source") or "").strip()
            underrepresented = max(0, 3 - int(subject_counts.get(subject, 0)))
            score = quality * .65 + underrepresented * 8.0 + (8.0 if commentary else 0.0) + (8.0 if "aprov" in review else 0.0)
            reasons = []
            if underrepresented: reasons.append(f"matéria com apenas {subject_counts.get(subject,0)} questão(ões) ouro")
            if quality >= 80: reasons.append("qualidade editorial alta")
            if commentary: reasons.append("comentário disponível")
            if "aprov" in review: reasons.append("questão já aprovada no fluxo editorial")
            candidates.append({
                "uid": uid, "code": str(row.get("source_code") or ""), "subject": subject,
                "topic": str(row.get("primary_topic") or ""), "quality_score": round(quality, 1),
                "review_status": str(row.get("review_status") or ""), "score": round(score, 1),
                "reasons": reasons or ["candidato para ampliar diversidade do conjunto Ouro"],
                "requires_human_approval": True, "auto_approved": False,
            })
        candidates.sort(key=lambda x: (-float(x["score"]), x["subject"], x["code"]))
        safe_limit = max(1, min(30, int(limit or 12)))
        return {
            "schema": "questflow.gold_expansion_suggestions.v1", "version": RETRIEVAL_OBSERVABILITY_VERSION,
            "active_gold_questions": len(gold), "suggestions": candidates[:safe_limit], "auto_apply": False,
            "message": "Sugestões apenas. A inclusão em Questões Ouro exige confirmação humana individual.",
        }

    def export_report(self, *, release: str, format: str = "json", limit: int = 30) -> dict:
        fmt = str(format or "json").strip().lower()
        dashboard = self.latest_dashboard(release=release)
        gold = self.suggest_gold_expansion(limit=20)
        if fmt == "json":
            payload = {"dashboard": dashboard, "gold_expansion": gold}
            return {
                "filename": f"QuestFlow_Retrieval_Observability_{str(release or 'release').replace(' ','_')}.json",
                "mime": "application/json;charset=utf-8", "content": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        if fmt != "csv":
            raise ValueError("Formato de relatório deve ser json ou csv.")
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(["timestamp", "release", "profile", "cases", "score", "recall", "grounding", "index_coverage", "rag_chunks", "sources", "drift_status"])
        for row in dashboard.get("history") or []:
            writer.writerow([
                row.get("at"), row.get("release"), row.get("profile_id"), row.get("cases"), row.get("score"),
                row.get("recall"), row.get("grounding_rate"), row.get("index_coverage"), row.get("rag_chunks"),
                row.get("sources"), (row.get("drift") or {}).get("status"),
            ])
        return {
            "filename": f"QuestFlow_Retrieval_Observability_{str(release or 'release').replace(' ','_')}.csv",
            "mime": "text/csv;charset=utf-8", "content": output.getvalue(),
        }


__all__ = [
    "RETRIEVAL_OBSERVABILITY_VERSION", "RetrievalObservabilityStore", "RetrievalObservabilityService",
    "compare_index_drift",
]
