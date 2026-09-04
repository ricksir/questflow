from __future__ import annotations

"""Serviço isolado de Observabilidade/Quality Gates de retrieval.

QuestFlow 6.11.0 separa o plano de observabilidade do AI Engine. O serviço usa
CQRS local: consultas leem somente snapshots persistidos; avaliações explícitas
são serializadas em um Evaluator Worker dedicado e publicam um snapshot
consistente para Studio e futuros consumidores Mobile.
"""

import json
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.retrieval_calibration import benchmark_snapshot
from core.retrieval_observability import RetrievalObservabilityService, RetrievalObservabilityStore
from core.retrieval_quality_gates import RetrievalQualityGateService, RetrievalQualityGateStore

RETRIEVAL_HEALTH_SERVICE_VERSION = "qf-retrieval-health-service-1"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RetrievalHealthSnapshotStore:
    """Store canônico de snapshots/estado do serviço, fora do SQLite acadêmico."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.snapshot_path = self.root / "retrieval_health_snapshot.json"
        self.state_path = self.root / "retrieval_health_service_state.json"
        self.jobs_path = self.root / "retrieval_health_jobs.jsonl"
        self._io_lock = threading.RLock()
        self._repair_interrupted_state()

    @staticmethod
    def _load(path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else deepcopy(default)
        except (OSError, json.JSONDecodeError):
            return deepcopy(default)

    @staticmethod
    def _atomic_write(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    def _repair_interrupted_state(self) -> None:
        state = self._load(self.state_path, {})
        if not isinstance(state, dict) or state.get("status") not in {"queued", "running"}:
            return
        state.update({
            "status": "interrupted",
            "updated_at": _utcnow(),
            "message": "A avaliação anterior foi interrompida pelo encerramento do aplicativo.",
            "active_job": None,
        })
        try:
            self._atomic_write(self.state_path, state)
        except OSError:
            pass

    def snapshot(self) -> dict | None:
        value = self._load(self.snapshot_path, None)
        return value if isinstance(value, dict) else None

    def state(self) -> dict:
        value = self._load(self.state_path, {})
        return value if isinstance(value, dict) else {}

    def save_snapshot(self, payload: dict) -> dict:
        with self._io_lock:
            self._atomic_write(self.snapshot_path, payload)
        return deepcopy(payload)

    def save_state(self, payload: dict) -> dict:
        with self._io_lock:
            self._atomic_write(self.state_path, payload)
        return deepcopy(payload)

    def append_job(self, payload: dict) -> None:
        with self._io_lock:
            with self.jobs_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def jobs(self, limit: int = 30) -> list[dict]:
        if not self.jobs_path.exists():
            return []
        try:
            lines = self.jobs_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out: list[dict] = []
        for line in reversed(lines[-max(1, min(200, int(limit or 30))):]):
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    out.append(item)
            except json.JSONDecodeError:
                continue
        return out


class RetrievalHealthService:
    """Boundary dedicado entre Retrieval Engine e UI/controle de release.

    - Query side: somente snapshots persistidos.
    - Command side: um worker serializado executa benchmark + índice uma vez.
    - Promotion side: usa exclusivamente o último gate já avaliado.
    """

    def __init__(
        self,
        *,
        knowledge: Any,
        governance: Any,
        editorial: Any,
        calibration_store: Any,
        root: str | Path,
    ) -> None:
        self.knowledge = knowledge
        self.governance = governance
        self.editorial = editorial
        self.calibration_store = calibration_store
        self.observability_store = RetrievalObservabilityStore(root)
        self.quality_store = RetrievalQualityGateStore(root)
        self.snapshot_store = RetrievalHealthSnapshotStore(root)
        self.observability = RetrievalObservabilityService(
            knowledge, governance, editorial, self.observability_store
        )
        self.quality_gate = RetrievalQualityGateService(
            knowledge, governance, calibration_store, self.quality_store
        )
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qf-retrieval-evaluator")
        self._lock = threading.RLock()
        self._future: Future | None = None
        self._jobs: dict[str, dict] = {}
        self._active_job_id = ""
        self._shutdown = False

    @staticmethod
    def _engine_descriptor(knowledge: Any) -> dict:
        return {
            "id": str(getattr(knowledge, "engine_id", "knowledge_engine") or "knowledge_engine"),
            "name": str(getattr(knowledge, "name", "Knowledge Engine") or "Knowledge Engine"),
            "version": str(getattr(knowledge, "version", "") or ""),
        }

    def _base_state(self) -> dict:
        persisted = self.snapshot_store.state()
        with self._lock:
            active = deepcopy(self._jobs.get(self._active_job_id)) if self._active_job_id else None
        return {
            "schema": "questflow.retrieval_health_service_state.v1",
            "version": RETRIEVAL_HEALTH_SERVICE_VERSION,
            "status": (active or {}).get("status") or persisted.get("status") or "idle",
            "updated_at": _utcnow(),
            "execution_mode": "dedicated_serial_evaluator_worker",
            "query_mode": "metrics_snapshot_store_only",
            "active_job": active,
            "last_job": persisted.get("last_job"),
            "last_error": persisted.get("last_error"),
            "message": (active or {}).get("message") or persisted.get("message") or "Serviço de retrieval pronto.",
        }

    def status(self) -> dict:
        state = self._base_state()
        snapshot = self.snapshot_store.snapshot()
        state["snapshot"] = {
            "available": bool(snapshot),
            "release": str((snapshot or {}).get("release") or ""),
            "evaluation_id": str((snapshot or {}).get("evaluation_id") or ""),
            "evaluated_at": (snapshot or {}).get("evaluated_at"),
            "consistent": bool((snapshot or {}).get("consistent", False)) if snapshot else None,
        }
        state["engine"] = self._engine_descriptor(self.knowledge)
        return state

    def health(self) -> dict:
        status = self.status()
        state = str(status.get("status") or "idle")
        failed = state in {"failed", "interrupted"}
        return {
            "ok": not failed,
            "state": "degraded" if failed else "healthy",
            "service_status": state,
            "worker": status.get("execution_mode"),
            "query_mode": status.get("query_mode"),
            "snapshot": status.get("snapshot"),
            "last_error": status.get("last_error"),
        }

    def read_observability(self, *, release: str) -> dict:
        # RetrievalObservabilityService.latest_dashboard é snapshot-store-only em 6.11+.
        payload = self.observability.latest_dashboard(release=release)
        payload["service"] = self.status()
        return payload

    def read_quality_gate(self, *, release: str) -> dict:
        payload = self.quality_gate.cached(release=release)
        payload["service"] = self.status()
        return payload

    def combined_snapshot(self, *, release: str) -> dict:
        canonical = self.snapshot_store.snapshot()
        return {
            "schema": "questflow.retrieval_health_contract.v1",
            "version": RETRIEVAL_HEALTH_SERVICE_VERSION,
            "release": str(release or ""),
            "service": self.status(),
            "observability": self.read_observability(release=release),
            "quality_gate": self.read_quality_gate(release=release),
            "canonical_snapshot": canonical,
        }


    def start_evaluation(self, *, release: str, limit: int = 30, source: str = "manual") -> dict:
        safe_limit = max(1, min(100, int(limit or 30)))
        with self._lock:
            if self._shutdown:
                raise RuntimeError("O serviço de retrieval está em encerramento.")
            if self._future is not None and not self._future.done() and self._active_job_id:
                active = deepcopy(self._jobs.get(self._active_job_id) or {})
                active["deduplicated"] = True
                return active
            job_id = uuid.uuid4().hex
            job = {
                "schema": "questflow.retrieval_evaluation_job.v1",
                "id": job_id,
                "release": str(release or ""),
                "source": str(source or "manual"),
                "limit": safe_limit,
                "status": "queued",
                "progress": 0.0,
                "message": "Avaliação de retrieval enfileirada.",
                "created_at": _utcnow(),
                "started_at": None,
                "finished_at": None,
                "evaluation_id": None,
                "error": None,
            }
            self._jobs[job_id] = job
            self._active_job_id = job_id
            self.snapshot_store.save_state({
                **self._base_state(), "status": "queued", "active_job": deepcopy(job),
                "message": job["message"], "last_error": None,
            })
            self._future = self._executor.submit(self._run_evaluation, job_id)
            return deepcopy(job)

    def _update_job(self, job_id: str, **changes: Any) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(job_id)
            job.update(changes)
            snapshot = deepcopy(job)
        persisted = self.snapshot_store.state()
        self.snapshot_store.save_state({
            "schema": "questflow.retrieval_health_service_state.v1",
            "version": RETRIEVAL_HEALTH_SERVICE_VERSION,
            "status": snapshot.get("status") or "running",
            "updated_at": _utcnow(),
            "execution_mode": "dedicated_serial_evaluator_worker",
            "query_mode": "metrics_snapshot_store_only",
            "active_job": snapshot if snapshot.get("status") in {"queued", "running"} else None,
            "last_job": snapshot if snapshot.get("status") in {"completed", "failed"} else persisted.get("last_job"),
            "last_error": snapshot.get("error") if snapshot.get("status") == "failed" else None,
            "message": snapshot.get("message") or "",
        })
        return snapshot

    def _run_evaluation(self, job_id: str) -> None:
        try:
            job = self._update_job(
                job_id, status="running", progress=0.08, started_at=_utcnow(),
                message="Preparando benchmark no Evaluator Worker…",
            )
            release = str(job.get("release") or "")
            limit = int(job.get("limit") or 30)
            evaluation_id = uuid.uuid4().hex
            self._update_job(
                job_id, evaluation_id=evaluation_id, progress=0.18,
                message="Executando benchmark de grounding/retrieval…",
            )

            from core.grounding_benchmark import MultimodalGroundingBenchmark
            report = MultimodalGroundingBenchmark(self.knowledge, self.governance).run(limit=limit)
            retrieval = benchmark_snapshot(report, release=release)
            retrieval["evaluation_id"] = evaluation_id

            self._update_job(
                job_id, progress=0.58,
                message="Capturando fingerprint do índice sem bloquear a interface…",
            )
            index_snapshot = self.knowledge.observability_snapshot()
            retrieval["index_coverage"] = index_snapshot.get("coverage")
            retrieval["rag_chunks"] = index_snapshot.get("rag_chunks")
            retrieval["source_count"] = index_snapshot.get("source_count")

            self._update_job(
                job_id, progress=0.72,
                message="Calculando Quality Gates a partir do mesmo snapshot…",
            )
            gate = self.quality_gate.evaluate_snapshot(
                current=retrieval, release=release, record=False
            )
            gate["evaluation_id"] = evaluation_id

            self._update_job(
                job_id, progress=0.84,
                message="Publicando snapshot consistente no Metrics Snapshot Store…",
            )
            observation = self.observability.record_snapshot(
                release=release, retrieval=retrieval, index_snapshot=index_snapshot,
                force_record=True,
            )
            self.quality_store.record_evaluation(gate)

            canonical = {
                "schema": "questflow.retrieval_health_snapshot.v1",
                "version": RETRIEVAL_HEALTH_SERVICE_VERSION,
                "evaluation_id": evaluation_id,
                "release": release,
                "evaluated_at": gate.get("evaluated_at") or _utcnow(),
                "consistent": True,
                "engine": self._engine_descriptor(self.knowledge),
                "profile": deepcopy(gate.get("profile") or {}),
                "retrieval": deepcopy(retrieval),
                "index": {k: v for k, v in index_snapshot.items() if k not in {"chunk_fingerprints", "source_fingerprints"}},
                "drift": deepcopy(observation.get("drift") or {}),
                "quality_gate": deepcopy(gate),
            }
            self.snapshot_store.save_snapshot(canonical)
            result_summary = {
                "evaluation_id": evaluation_id,
                "release": release,
                "cases": int(retrieval.get("cases") or 0),
                "score": (retrieval.get("hybrid") or {}).get("score"),
                "gate_status": gate.get("status"),
                "index_coverage": index_snapshot.get("coverage"),
                "recorded": bool(observation.get("recorded")),
            }
            completed = self._update_job(
                job_id, status="completed", progress=1.0, finished_at=_utcnow(),
                message="Avaliação concluída e snapshot publicado.", result=result_summary,
            )
            self.snapshot_store.append_job(completed)
        except Exception as error:
            try:
                failed = self._update_job(
                    job_id, status="failed", finished_at=_utcnow(),
                    message="A avaliação falhou; o último snapshot válido foi preservado.",
                    error=str(error),
                )
                self.snapshot_store.append_job(failed)
            except Exception:
                pass
        finally:
            with self._lock:
                if self._active_job_id == job_id:
                    self._active_job_id = ""

    def job(self, job_id: str = "") -> dict:
        with self._lock:
            if job_id and job_id in self._jobs:
                return deepcopy(self._jobs[job_id])
            if self._active_job_id and self._active_job_id in self._jobs:
                return deepcopy(self._jobs[self._active_job_id])
        state = self.snapshot_store.state()
        last = state.get("last_job") if isinstance(state.get("last_job"), dict) else None
        if job_id and last and str(last.get("id") or "") != str(job_id):
            for item in self.snapshot_store.jobs(limit=100):
                if str(item.get("id") or "") == str(job_id):
                    return item
            return {"id": str(job_id), "status": "not_found", "message": "Job de retrieval não encontrado."}
        return deepcopy(last or {"status": "idle", "message": "Nenhuma avaliação em execução."})

    def promote(self, *, release: str, reason: str) -> dict:
        return self.quality_gate.promote_cached(release=release, reason=reason)

    def override(self, *, release: str, reason: str) -> dict:
        return self.quality_gate.override_cached(release=release, reason=reason)

    def rollback(self) -> dict:
        return self.quality_gate.rollback()

    def suggest_gold_expansion(self, *, limit: int = 12) -> dict:
        return self.observability.suggest_gold_expansion(limit=limit)

    def export_observability(self, *, release: str, format: str = "json", limit: int = 30) -> dict:
        return self.observability.export_report(release=release, format=format, limit=limit)

    def export_quality_gate(self, *, release: str, format: str = "json", limit: int = 30) -> dict:
        return self.quality_gate.export_report(release=release, format=format, limit=limit)

    def shutdown(self, *, wait: bool = False) -> None:
        with self._lock:
            self._shutdown = True
        try:
            self._executor.shutdown(wait=bool(wait), cancel_futures=True)
        except TypeError:
            self._executor.shutdown(wait=bool(wait))


__all__ = [
    "RETRIEVAL_HEALTH_SERVICE_VERSION",
    "RetrievalHealthSnapshotStore",
    "RetrievalHealthService",
]
