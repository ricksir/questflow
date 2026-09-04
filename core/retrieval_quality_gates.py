from __future__ import annotations

"""QuestFlow 6.8.4 · Retrieval Quality Gates e promoção segura de release.

A camada é local, determinística e human-in-the-loop. Ela transforma as métricas
já produzidas pelo benchmark/observabilidade em gates explícitos antes de uma
release ser considerada aprovada para retrieval. Nenhum override é silencioso e
nenhuma promoção altera FSRS/KT/IRT.
"""

import csv
import io
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.retrieval_calibration import benchmark_snapshot, compare_regression

RETRIEVAL_QUALITY_GATE_VERSION = "qf-retrieval-quality-gates-2"
DEFAULT_GATE_POLICY = {
    "coverage_drop_warn": 3.0,
    "subject_min_cases": 2,
    "override_reason_min_chars": 15,
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class RetrievalQualityGateStore:
    """Estado de promoção fora do schema SQLite.

    A baseline aprovada é deliberadamente separada da baseline de calibração:
    calibração mede regressão; quality gate representa decisão de promoção.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "release_quality_gate_state.json"
        self.history_path = self.root / "release_quality_gate_history.jsonl"
        self.approved_path = self.root / "approved_retrieval_release.json"
        self.latest_gate_path = self.root / "latest_retrieval_quality_gate.json"

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else deepcopy(default)
        except (OSError, json.JSONDecodeError):
            return deepcopy(default)

    def approved_baseline(self) -> dict | None:
        value = self._read_json(self.approved_path, None)
        return value if isinstance(value, dict) else None

    def state(self) -> dict:
        value = self._read_json(self.state_path, {})
        return value if isinstance(value, dict) else {}

    def latest_gate(self) -> dict | None:
        value = self._read_json(self.latest_gate_path, None)
        return value if isinstance(value, dict) else None

    def history(self, limit: int = 50) -> list[dict]:
        if not self.history_path.exists():
            return []
        try:
            lines = self.history_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out: list[dict] = []
        for line in reversed(lines[-max(1, min(1000, int(limit or 50))):]):
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    out.append(row)
            except json.JSONDecodeError:
                continue
        return out

    def _append(self, event: dict) -> None:
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def record_evaluation(self, gate: dict) -> dict:
        # 6.10.3: mantém o último gate completo para consultas read-only. Abrir a
        # tela deixa de disparar benchmark; somente "Reavaliar gates" recalcula.
        try:
            self.latest_gate_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        state = {
            "schema": "questflow.retrieval_quality_gate_state.v1",
            "version": RETRIEVAL_QUALITY_GATE_VERSION,
            "release": gate.get("release"),
            "status": gate.get("status"),
            "evaluated_at": gate.get("evaluated_at") or _utcnow(),
            "can_promote": bool(gate.get("can_promote")),
            "blocker_count": len(gate.get("blockers") or []),
            "approved_release": (gate.get("approved_baseline") or {}).get("release"),
        }
        previous = self.state()
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        # Não polui o journal quando nada relevante mudou.
        if any(previous.get(k) != state.get(k) for k in ("release", "status", "blocker_count", "approved_release")):
            self._append({"at": state["evaluated_at"], "action": "evaluate", "state": state})
        return state

    def approve(self, snapshot: dict, *, profile: dict, action: str, reason: str, gate: dict) -> dict:
        previous = self.approved_baseline()
        approved = deepcopy(snapshot)
        approved.update({
            "schema": "questflow.approved_retrieval_release.v1",
            "quality_gate_version": RETRIEVAL_QUALITY_GATE_VERSION,
            "approved_at": _utcnow(),
            "approval_action": action,
            "approval_reason": str(reason or ""),
            "profile": deepcopy(profile),
            "gate_status_at_approval": gate.get("status"),
            "override": action == "override",
        })
        self.approved_path.write_text(json.dumps(approved, ensure_ascii=False, indent=2), encoding="utf-8")
        event = {
            "at": approved["approved_at"], "action": action, "release": approved.get("release"),
            "reason": approved["approval_reason"], "previous_approved": previous,
            "approved": approved, "gate_summary": {
                "status": gate.get("status"), "blockers": gate.get("blockers") or [],
            },
        }
        self._append(event)
        self.state_path.write_text(json.dumps({
            "schema": "questflow.retrieval_quality_gate_state.v1", "version": RETRIEVAL_QUALITY_GATE_VERSION,
            "release": approved.get("release"), "status": "overridden" if action == "override" else "promoted",
            "evaluated_at": approved["approved_at"], "can_promote": False, "blocker_count": 0,
            "approved_release": approved.get("release"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"approved": approved, "previous_approved": previous, "event": event}

    def rollback(self) -> dict:
        for event in self.history(limit=200):
            if event.get("action") not in {"promote", "override"}:
                continue
            previous = event.get("previous_approved") if isinstance(event.get("previous_approved"), dict) else None
            if not previous:
                continue
            current = self.approved_baseline()
            self.approved_path.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8")
            rollback_event = {
                "at": _utcnow(), "action": "rollback", "from_release": (current or {}).get("release"),
                "to_release": previous.get("release"), "restored": previous,
            }
            self._append(rollback_event)
            self.state_path.write_text(json.dumps({
                "schema": "questflow.retrieval_quality_gate_state.v1", "version": RETRIEVAL_QUALITY_GATE_VERSION,
                "release": previous.get("release"), "status": "rollback", "evaluated_at": rollback_event["at"],
                "can_promote": False, "blocker_count": 0, "approved_release": previous.get("release"),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"restored": previous, "previous_current": current, "event": rollback_event}
        return {"restored": None, "warning": "Não existe promoção anterior com baseline aprovada para rollback."}

    def can_rollback(self) -> bool:
        return any(
            event.get("action") in {"promote", "override"} and isinstance(event.get("previous_approved"), dict)
            for event in self.history(limit=200)
        )


def _subject_alert_is_actionable(alert: dict, current: dict, baseline: dict, min_cases: int) -> bool:
    if alert.get("scope") != "subject":
        return True
    subject = str(alert.get("subject") or "")
    cur_row = (current.get("subjects") or {}).get(subject) if isinstance(current.get("subjects"), dict) else None
    old_row = (baseline.get("subjects") or {}).get(subject) if isinstance(baseline.get("subjects"), dict) else None
    return bool(
        isinstance(cur_row, dict) and isinstance(old_row, dict)
        and int(cur_row.get("cases") or 0) >= min_cases and int(old_row.get("cases") or 0) >= min_cases
    )


class RetrievalQualityGateService:
    def __init__(self, knowledge: Any, governance: Any, calibration_store: Any, store: RetrievalQualityGateStore):
        self.knowledge = knowledge
        self.governance = governance
        self.calibration_store = calibration_store
        self.store = store

    def _current_snapshot(self, *, release: str, limit: int) -> dict:
        from core.grounding_benchmark import MultimodalGroundingBenchmark
        report = MultimodalGroundingBenchmark(self.knowledge, self.governance).run(limit=max(1, min(100, int(limit or 30))))
        snapshot = benchmark_snapshot(report, release=release)
        index = self.knowledge.observability_snapshot()
        snapshot["index_coverage"] = index.get("coverage")
        snapshot["rag_chunks"] = index.get("rag_chunks")
        snapshot["source_count"] = index.get("source_count")
        return snapshot

    def cached(self, *, release: str, limit: int = 30) -> dict:
        """Retorna o último Quality Gate sem executar retrieval/benchmark."""
        cached = self.store.latest_gate()
        if isinstance(cached, dict) and str(cached.get("release") or "") == str(release or ""):
            result = deepcopy(cached)
            approved_now = self.store.approved_baseline()
            approved_current = bool(approved_now and str(approved_now.get("release") or "") == str(release or ""))
            if approved_current:
                result["status"] = "overridden" if approved_now.get("override") else "promoted"
                result["approved_baseline"] = approved_now
                result["baseline_source"] = "approved_release"
                result["can_promote"] = False
                result["can_override"] = False
                result["message"] = "Release já promovida pelo quality gate." if not approved_now.get("override") else "Release promovida por override humano auditado."
            elif result.get("status") in {"promoted", "overridden"}:
                # Um rollback de baseline invalida o estado de promoção exibido para
                # a release atual até nova reavaliação explícita.
                result["status"] = "pending_evaluation"
                result["evaluated_at"] = None
                result["can_promote"] = False
                result["can_override"] = False
                result["message"] = "A baseline aprovada foi restaurada para outra release. Reavalie antes de nova promoção."
            result["cached"] = True
            result["can_rollback"] = self.store.can_rollback()
            result["engine"] = {
                "id": str(getattr(self.knowledge, "engine_id", "knowledge_engine") or "knowledge_engine"),
                "name": str(getattr(self.knowledge, "name", "Knowledge Engine") or "Knowledge Engine"),
                "version": str(getattr(self.knowledge, "version", "") or ""),
            }
            return result

        profile = self.calibration_store.current()
        thresholds = {**(profile.get("thresholds") or {}), **DEFAULT_GATE_POLICY}
        min_cases = int(thresholds.get("min_cases", 3) or 3)
        # 6.11.0: o caminho de leitura não consulta Governance nem Knowledge.
        # Usa exclusivamente o último snapshot persistido para manter a Query
        # side livre de benchmark, varredura do índice e efeitos colaterais.
        latest_any = self.store.latest_gate()
        latest_current = latest_any.get("current") if isinstance(latest_any, dict) and isinstance(latest_any.get("current"), dict) else {}
        gold_cases = int(latest_current.get("cases") or 0)
        index = {
            "coverage": latest_current.get("index_coverage"),
            "rag_chunks": latest_current.get("rag_chunks"),
            "source_count": latest_current.get("source_count"),
        }
        approved = self.store.approved_baseline()
        legacy = self.calibration_store.baseline() if hasattr(self.calibration_store, "baseline") else None
        comparison_baseline = approved or legacy
        baseline_source = "approved_release" if approved else ("legacy_regression_baseline" if legacy else "none")
        current = {
            "schema": "questflow.retrieval_regression_baseline.v1", "release": str(release or ""),
            "benchmark_version": "", "cases": gold_cases,
            "sample_status": "suficiente" if gold_cases >= min_cases else "insuficiente",
            "hybrid": {"score": None, "grounding_rate": None, "commentary_support": None, "precision": None, "recall": None, "visual_coverage": None, "path_safety": None},
            "subjects": {}, "index_coverage": index.get("coverage"), "rag_chunks": index.get("rag_chunks"), "source_count": index.get("source_count"),
        }
        blockers = []
        if gold_cases < min_cases:
            blockers.append({"scope": "global", "metric": "sample", "current": gold_cases, "required": min_cases, "reason": "amostra insuficiente"})
        warnings = []
        if not comparison_baseline:
            warnings.append({"scope": "global", "metric": "baseline", "reason": "nenhuma baseline aprovada; a primeira promoção estabelecerá a referência"})
        return {
            "schema": "questflow.retrieval_quality_gate.v2", "version": RETRIEVAL_QUALITY_GATE_VERSION,
            "release": str(release or ""), "evaluated_at": None, "status": "pending_evaluation",
            "current": current, "approved_baseline": approved, "comparison_baseline": comparison_baseline,
            "baseline_source": baseline_source, "profile": profile, "policy": thresholds,
            "comparison": {"status": "nao_avaliado", "alerts": [], "deltas": {}, "subjects": {}, "thresholds": thresholds},
            "blockers": blockers, "warnings": warnings, "sample_ok": gold_cases >= min_cases,
            "can_promote": False, "can_override": False, "can_rollback": self.store.can_rollback(),
            "requires_human_action": True, "auto_promote": False, "cached": False,
            "snapshot_store_only": True,
            "source_snapshot_release": str((latest_any or {}).get("release") or ""),
            "engine": {
                "id": str(getattr(self.knowledge, "engine_id", "knowledge_engine") or "knowledge_engine"),
                "name": str(getattr(self.knowledge, "name", "Knowledge Engine") or "Knowledge Engine"),
                "version": str(getattr(self.knowledge, "version", "") or ""),
            },
            "message": "Esta release ainda não foi avaliada. Clique em Reavaliar gates para executar o benchmark explicitamente.",
        }

    def evaluate_snapshot(self, *, current: dict, release: str, record: bool = True) -> dict:
        """Avalia Quality Gates a partir de snapshot pré-computado.

        O Evaluator Worker executa o benchmark uma única vez e fornece o mesmo
        snapshot à Observabilidade e aos Quality Gates, eliminando divergência
        entre métricas e trabalho duplicado.
        """
        current = deepcopy(current or {})
        current["release"] = str(release or current.get("release") or "")
        profile = self.calibration_store.current()
        thresholds = {**(profile.get("thresholds") or {}), **DEFAULT_GATE_POLICY}
        approved = self.store.approved_baseline()
        legacy = self.calibration_store.baseline() if hasattr(self.calibration_store, "baseline") else None
        comparison_baseline = approved or legacy
        baseline_source = "approved_release" if approved else ("legacy_regression_baseline" if legacy else "none")
        min_cases = int(thresholds.get("min_cases", 3) or 3)
        blockers: list[dict] = []
        warnings: list[dict] = []
        cases = int(current.get("cases") or 0)
        sample_ok = cases >= min_cases
        if not sample_ok:
            blockers.append({"scope": "global", "metric": "sample", "current": cases, "required": min_cases, "reason": "amostra insuficiente"})

        comparison = {"status": "sem_baseline", "alerts": [], "deltas": {}, "subjects": {}, "thresholds": thresholds}
        if comparison_baseline:
            comparison = compare_regression(current, comparison_baseline, thresholds=thresholds)
            subject_min = int(thresholds.get("subject_min_cases", 2) or 2)
            for alert in comparison.get("alerts") or []:
                if _subject_alert_is_actionable(alert, current, comparison_baseline, subject_min):
                    blockers.append(dict(alert, reason="regressão acima do quality gate"))
                else:
                    warnings.append(dict(alert, reason="alerta por matéria ignorado pelo gate por amostra pequena"))
            old_coverage = _safe_float(comparison_baseline.get("index_coverage"))
            cur_coverage = _safe_float(current.get("index_coverage"))
            if old_coverage is not None:
                if cur_coverage is None:
                    blockers.append({"scope": "global", "metric": "index_coverage", "reason": "cobertura atual indisponível"})
                else:
                    delta = round(cur_coverage - old_coverage, 1)
                    comparison.setdefault("deltas", {})["index_coverage"] = delta
                    limit_drop = float(thresholds.get("coverage_drop_warn", 3.0) or 3.0)
                    if delta < -limit_drop:
                        blockers.append({"scope": "global", "metric": "index_coverage", "delta": delta, "threshold": -limit_drop, "reason": "queda de cobertura acima do gate"})
            else:
                warnings.append({"scope": "global", "metric": "index_coverage", "reason": "baseline anterior não possui cobertura; gate de cobertura começa após a primeira promoção"})
        else:
            warnings.append({"scope": "global", "metric": "baseline", "reason": "nenhuma baseline aprovada; a primeira promoção estabelecerá a referência"})

        approved_current = bool(approved and str(approved.get("release") or "") == str(release or ""))
        if approved_current and not blockers:
            status = "overridden" if approved.get("override") else "promoted"
        elif blockers:
            status = "quarantine"
        elif not comparison_baseline:
            status = "baseline_required"
        else:
            status = "pass"
        can_promote = bool(sample_ok and not blockers and not approved_current)
        can_override = bool(cases > 0 and status == "quarantine")
        gate = {
            "schema": "questflow.retrieval_quality_gate.v3", "version": RETRIEVAL_QUALITY_GATE_VERSION,
            "release": str(release or ""), "evaluated_at": _utcnow(), "status": status,
            "engine": {
                "id": str(getattr(self.knowledge, "engine_id", "knowledge_engine") or "knowledge_engine"),
                "name": str(getattr(self.knowledge, "name", "Knowledge Engine") or "Knowledge Engine"),
                "version": str(getattr(self.knowledge, "version", "") or ""),
            },
            "current": current, "approved_baseline": approved, "comparison_baseline": comparison_baseline,
            "baseline_source": baseline_source, "profile": profile, "policy": thresholds,
            "comparison": comparison, "blockers": blockers, "warnings": warnings,
            "sample_ok": sample_ok, "can_promote": can_promote, "can_override": can_override,
            "can_rollback": self.store.can_rollback(), "requires_human_action": status not in {"promoted", "overridden"},
            "auto_promote": False, "snapshot_store_only": False,
            "message": {
                "promoted": "Release já promovida pelo quality gate.",
                "overridden": "Release promovida por override humano auditado.",
                "pass": "Quality gates aprovados; promoção humana está disponível.",
                "baseline_required": "Amostra suficiente; a primeira promoção criará a baseline aprovada.",
                "quarantine": "Release em quarentena: um ou mais gates bloquearam a promoção.",
            }.get(status, "Quality gate avaliado."),
        }
        if record:
            self.store.record_evaluation(gate)
        return gate

    def evaluate(self, *, release: str, limit: int = 30, record: bool = True) -> dict:
        """Compatibilidade de baixo nível. O app 6.11+ usa Evaluator Worker."""
        current = self._current_snapshot(release=release, limit=limit)
        return self.evaluate_snapshot(current=current, release=release, record=record)

    def promote_cached(self, *, release: str, reason: str = "human_release_promotion") -> dict:
        gate = self.cached(release=release)
        if not gate.get("evaluated_at") or gate.get("status") == "pending_evaluation":
            raise ValueError("A release precisa ser reavaliada antes da promoção.")
        if not gate.get("can_promote"):
            raise ValueError("A release não pode ser promovida: resolva os quality gates ou use override humano auditado quando aplicável.")
        result = self.store.approve(gate["current"], profile=gate["profile"], action="promote", reason=reason, gate=gate)
        if hasattr(self.calibration_store, "save_baseline"):
            self.calibration_store.save_baseline(gate["current"])
        return result

    def override_cached(self, *, release: str, reason: str) -> dict:
        reason = str(reason or "").strip()
        min_chars = int(DEFAULT_GATE_POLICY["override_reason_min_chars"])
        if len(reason) < min_chars:
            raise ValueError(f"O override exige justificativa humana com pelo menos {min_chars} caracteres.")
        gate = self.cached(release=release)
        if not gate.get("evaluated_at") or gate.get("status") == "pending_evaluation":
            raise ValueError("A release precisa ser reavaliada antes de um override.")
        if not gate.get("can_override"):
            raise ValueError("Override só é permitido quando a release está em quarentena com evidência mensurável.")
        result = self.store.approve(gate["current"], profile=gate["profile"], action="override", reason=reason, gate=gate)
        if hasattr(self.calibration_store, "save_baseline"):
            self.calibration_store.save_baseline(gate["current"])
        return result

    def promote(self, *, release: str, limit: int = 30, reason: str = "human_release_promotion") -> dict:
        # API legada para testes/CLI: avalia antes de promover. O Studio usa promote_cached.
        gate = self.evaluate(release=release, limit=limit, record=True)
        if not gate.get("can_promote"):
            raise ValueError("A release não pode ser promovida: resolva os quality gates ou use override humano auditado quando aplicável.")
        result = self.store.approve(gate["current"], profile=gate["profile"], action="promote", reason=reason, gate=gate)
        if hasattr(self.calibration_store, "save_baseline"):
            self.calibration_store.save_baseline(gate["current"])
        return result

    def override(self, *, release: str, reason: str, limit: int = 30) -> dict:
        # API legada para testes/CLI: avalia antes do override. O Studio usa override_cached.
        reason = str(reason or "").strip()
        min_chars = int(DEFAULT_GATE_POLICY["override_reason_min_chars"])
        if len(reason) < min_chars:
            raise ValueError(f"O override exige justificativa humana com pelo menos {min_chars} caracteres.")
        gate = self.evaluate(release=release, limit=limit, record=True)
        if not gate.get("can_override"):
            raise ValueError("Override só é permitido quando a release está em quarentena com evidência mensurável.")
        result = self.store.approve(gate["current"], profile=gate["profile"], action="override", reason=reason, gate=gate)
        if hasattr(self.calibration_store, "save_baseline"):
            self.calibration_store.save_baseline(gate["current"])
        return result

    def rollback(self) -> dict:
        result = self.store.rollback()
        restored = result.get("restored") if isinstance(result.get("restored"), dict) else None
        if restored:
            profile = restored.get("profile") if isinstance(restored.get("profile"), dict) else None
            if profile and hasattr(self.calibration_store, "apply"):
                self.calibration_store.apply(profile, reason="quality_gate_rollback")
            if hasattr(self.calibration_store, "save_baseline"):
                self.calibration_store.save_baseline(restored)
        return result

    def export_report(self, *, release: str, format: str = "json", limit: int = 30) -> dict:
        gate = self.cached(release=release, limit=limit)
        history = self.store.history(limit=100)
        fmt = str(format or "json").strip().lower()
        if fmt == "json":
            return {
                "filename": f"QuestFlow_Retrieval_Quality_Gate_{release}.json",
                "mime": "application/json;charset=utf-8",
                "content": json.dumps({"gate": gate, "history": history}, ensure_ascii=False, indent=2),
            }
        if fmt != "csv":
            raise ValueError("Formato de relatório deve ser json ou csv.")
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["release", "status", "metric", "scope", "subject", "delta", "threshold", "reason"])
        if gate.get("blockers"):
            for item in gate["blockers"]:
                writer.writerow([release, gate.get("status"), item.get("metric"), item.get("scope"), item.get("subject"), item.get("delta"), item.get("threshold"), item.get("reason")])
        else:
            writer.writerow([release, gate.get("status"), "all", "global", "", "", "", gate.get("message")])
        return {
            "filename": f"QuestFlow_Retrieval_Quality_Gate_{release}.csv",
            "mime": "text/csv;charset=utf-8", "content": out.getvalue(),
        }


__all__ = [
    "RETRIEVAL_QUALITY_GATE_VERSION", "DEFAULT_GATE_POLICY", "RetrievalQualityGateStore",
    "RetrievalQualityGateService",
]
