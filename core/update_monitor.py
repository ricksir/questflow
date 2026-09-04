from __future__ import annotations

"""Consent-first, offline-safe update monitor for QuestFlow dependencies.

The scheduler itself performs no network access. Twice a month it only marks a
check as due so the UI can ask the user whether to run it. Network I/O starts
only after explicit consent and runs in a worker thread outside SQLite.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.request import Request

from app_shared import APP_VERSION
from .network import network_urlopen
from .rate_limiter import acquire_external_slot


DEFAULT_DAYS = (1, 15)
MAX_BYTES = 900_000

# Official / first-party pages only. Product pages are intentionally stable
# feature surfaces rather than fast-moving third-party news feeds.
DEFAULT_SOURCES: tuple[dict[str, str], ...] = (
    {"id": "openai_changelog", "group": "IA", "name": "OpenAI API · changelog", "url": "https://developers.openai.com/api/docs/changelog", "mode": "full"},
    {"id": "openai_deprecations", "group": "IA", "name": "OpenAI API · depreciações", "url": "https://developers.openai.com/api/docs/deprecations", "mode": "full"},
    {"id": "gemini_changelog", "group": "IA", "name": "Google Gemini API · release notes", "url": "https://ai.google.dev/gemini-api/docs/changelog", "mode": "full"},
    {"id": "claude_release_notes", "group": "IA", "name": "Anthropic Claude API · release notes", "url": "https://platform.claude.com/docs/en/release-notes/overview", "mode": "full"},
    {"id": "turso_python", "group": "Turso", "name": "Turso · Python / sync", "url": "https://docs.turso.tech/sdk/python/reference", "mode": "full"},
    {"id": "gran_questoes", "group": "Concursos", "name": "Gran Questões", "url": "https://questoes.grancursosonline.com.br/", "mode": "features"},
    {"id": "estrategia_sq", "group": "Concursos", "name": "Estratégia · Sistema de Questões", "url": "https://www.estrategiaconcursos.com.br/sistema-de-questoes/", "mode": "features"},
    {"id": "qconcursos", "group": "Concursos", "name": "QConcursos", "url": "https://www.qconcursos.com/", "mode": "features"},
    {"id": "tec_concursos", "group": "Concursos", "name": "TEC Concursos", "url": "https://www.tecconcursos.com.br/", "mode": "features"},
)

FEATURE_TERMS = (
    "quest", "simulad", "intelig", "ia", "desempenho", "raio-x", "raio x",
    "coment", "revis", "plano", "programa de estudo", "caderno", "filtro",
    "estat", "dificuldade", "inédit", "inedit", "atualiz", "novidade",
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts: list[str] = []
        self.title: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden += 1
        if tag == "title":
            self._in_title = True
        if tag in {"p", "li", "h1", "h2", "h3", "h4", "section", "article", "br"} and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self.hidden:
            self.hidden -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self.hidden:
            return
        if self._in_title:
            self.title.append(data)
        self.parts.append(data)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now_utc()).replace(microsecond=0).isoformat()


def _normalise(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip().casefold()
    # Remove highly volatile standalone counters and timestamps while keeping
    # version identifiers such as 6.4.1 / 2026-05-07.
    text = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", text)
    text = re.sub(r"\b\d{1,3}(?:[.,]\d{3})+\b", "#", text)
    return re.sub(r"\s+", " ", text).strip()


def _fingerprint(html: str, mode: str) -> tuple[str, str, str]:
    parser = _TextExtractor()
    parser.feed(html)
    title = re.sub(r"\s+", " ", " ".join(parser.title)).strip()
    raw = "\n".join(parser.parts)
    lines = [re.sub(r"\s+", " ", line).strip() for line in raw.splitlines()]
    lines = [line for line in lines if len(line) >= 8]
    if mode == "features":
        selected = [line for line in lines if any(term in line.casefold() for term in FEATURE_TERMS)]
        if selected:
            lines = selected[:260]
        else:
            lines = lines[:180]
    else:
        lines = lines[:650]
    canonical = _normalise("\n".join(lines))
    digest = hashlib.sha256(canonical.encode("utf-8", errors="ignore")).hexdigest()
    preview = " · ".join(lines[:4])[:520]
    return digest, title[:180], preview


def _load_state(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except (OSError, json.JSONDecodeError):
        pass
    return {"schema": 1, "snapshots": {}, "history": []}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def cycle_for(moment: datetime, days: tuple[int, int] = DEFAULT_DAYS) -> tuple[str, int]:
    first, second = sorted((max(1, min(28, int(days[0]))), max(1, min(28, int(days[1])))))
    marker = "A" if moment.day < second else "B"
    due_day = first if marker == "A" else second
    return f"{moment.year:04d}-{moment.month:02d}-{marker}", due_day


class UpdateMonitor:
    def __init__(self, *, config: dict, state_path: str | Path) -> None:
        self.config = config
        self.state_path = Path(state_path)

    def _days(self) -> tuple[int, int]:
        raw = self.config.get("update_monitor_days") or [1, 15]
        try:
            values = sorted({max(1, min(28, int(x))) for x in raw})
        except Exception:
            values = [1, 15]
        if len(values) < 2:
            values = [values[0] if values else 1, 15]
        if values[0] == values[1]:
            values[1] = 15 if values[0] != 15 else 28
        return int(values[0]), int(values[1])

    def status(self, now: datetime | None = None) -> dict[str, Any]:
        moment = now or _now_utc().astimezone()
        state = _load_state(self.state_path)
        cycle, due_day = cycle_for(moment, self._days())
        enabled = bool(self.config.get("update_monitor_enabled", True))
        snooze_until = str(state.get("snooze_until") or "")
        snoozed = False
        if snooze_until:
            try:
                snoozed = datetime.fromisoformat(snooze_until).astimezone(moment.tzinfo) > moment
            except ValueError:
                pass
        resolved_cycle = str(state.get("resolved_cycle") or "")
        due = enabled and moment.day >= due_day and cycle != resolved_cycle and not snoozed
        return {
            "ok": True,
            "enabled": enabled,
            "days": list(self._days()),
            "cycle": cycle,
            "due_day": due_day,
            "due": due,
            "snoozed": snoozed,
            "snooze_until": snooze_until,
            "last_check_at": state.get("last_check_at", ""),
            "last_success_at": state.get("last_success_at", ""),
            "last_summary": state.get("last_summary", {}),
            "history": list(state.get("history") or [])[-12:],
            "source_count": len(DEFAULT_SOURCES),
            "privacy": "O agendador não acessa a internet. Só há tráfego externo depois de sua confirmação.",
        }

    def defer(self, action: str, now: datetime | None = None) -> dict[str, Any]:
        moment = now or _now_utc().astimezone()
        state = _load_state(self.state_path)
        cycle, _ = cycle_for(moment, self._days())
        action = str(action or "snooze").lower()
        if action == "skip":
            state["resolved_cycle"] = cycle
            state["snooze_until"] = ""
            state.setdefault("history", []).append({"at": _iso(), "cycle": cycle, "event": "skipped"})
        else:
            until = moment + timedelta(hours=24)
            state["snooze_until"] = until.isoformat(timespec="seconds")
            state.setdefault("history", []).append({"at": _iso(), "cycle": cycle, "event": "snoozed", "until": state["snooze_until"]})
        state["history"] = state.get("history", [])[-30:]
        _save_state(self.state_path, state)
        return self.status(moment)

    def _fetch_one(self, source: dict[str, str], timeout: float) -> dict[str, Any]:
        acquire_external_slot(self.config, "update_monitor", timeout=min(4.0, timeout), burst=6.0)
        req = Request(
            source["url"],
            headers={
                "User-Agent": f"QuestFlow-Studio/{APP_VERSION} UpdateMonitor (+local desktop; consented check)",
                "Accept": "text/html,text/plain,application/xhtml+xml;q=0.9,*/*;q=0.5",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
            },
            method="GET",
        )
        with network_urlopen(req, timeout=timeout, config=self.config) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raw = raw[:MAX_BYTES]
            charset = "utf-8"
            try:
                charset = response.headers.get_content_charset() or "utf-8"
            except Exception:
                pass
            html = raw.decode(charset, errors="replace")
            digest, title, preview = _fingerprint(html, source.get("mode", "full"))
            return {
                **source,
                "ok": True,
                "status": int(getattr(response, "status", 200) or 200),
                "fingerprint": digest,
                "title": title,
                "preview": preview,
                "etag": str(response.headers.get("ETag") or ""),
                "last_modified": str(response.headers.get("Last-Modified") or ""),
                "checked_at": _iso(),
            }

    def run(self, *, progress=None, timeout: float = 7.0) -> dict[str, Any]:
        """Fetch first-party sources concurrently; never opens or writes SQLite."""
        state = _load_state(self.state_path)
        previous = dict(state.get("snapshots") or {})
        results: list[dict[str, Any]] = []
        sources = list(DEFAULT_SOURCES)
        if progress:
            progress(0.03, "Verificando conectividade nas fontes oficiais…")
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="qf-update-monitor") as pool:
            futures = {pool.submit(self._fetch_one, source, timeout): source for source in sources}
            done = 0
            for future in as_completed(futures):
                source = futures[future]
                try:
                    item = future.result()
                except Exception as error:
                    item = {**source, "ok": False, "error": str(error), "checked_at": _iso()}
                done += 1
                old = previous.get(source["id"], {}) if isinstance(previous.get(source["id"]), dict) else {}
                item["baseline"] = not bool(old.get("fingerprint"))
                item["changed"] = bool(item.get("ok") and old.get("fingerprint") and old.get("fingerprint") != item.get("fingerprint"))
                results.append(item)
                if progress:
                    progress(0.08 + 0.84 * (done / max(1, len(sources))), f"Verificando {source['name']}…")
        results.sort(key=lambda x: (x.get("group", ""), x.get("name", "")))
        successes = [x for x in results if x.get("ok")]
        failures = [x for x in results if not x.get("ok")]
        changed = [x for x in successes if x.get("changed")]
        for item in successes:
            state.setdefault("snapshots", {})[item["id"]] = {
                "fingerprint": item.get("fingerprint", ""),
                "title": item.get("title", ""),
                "etag": item.get("etag", ""),
                "last_modified": item.get("last_modified", ""),
                "checked_at": item.get("checked_at", ""),
            }
        moment = _now_utc().astimezone()
        cycle, _ = cycle_for(moment, self._days())
        state["last_check_at"] = _iso()
        state["snooze_until"] = ""
        # Only resolve the cycle if at least one source was reached. If the PC
        # is offline the prompt will remain available on the next app session.
        if successes:
            state["resolved_cycle"] = cycle
            state["last_success_at"] = _iso()
        summary = {
            "cycle": cycle,
            "successes": len(successes),
            "failures": len(failures),
            "changed": len(changed),
            "baseline": sum(1 for x in successes if x.get("baseline")),
            "offline_or_blocked": len(successes) == 0,
        }
        state["last_summary"] = summary
        state.setdefault("history", []).append({"at": _iso(), "event": "check", **summary})
        state["history"] = state.get("history", [])[-30:]
        _save_state(self.state_path, state)
        if progress:
            progress(0.98, "Consolidando relatório local…")
        return {
            "ok": bool(successes),
            "summary": summary,
            "items": results,
            "changed_items": changed,
            "message": (
                "Sem internet ou acesso externo bloqueado. Nada foi alterado no banco; a verificação continuará pendente."
                if not successes
                else (f"{len(changed)} fonte(s) mudou/mudaram desde a última verificação." if changed else "Nenhuma mudança detectada nas fontes já monitoradas.")
            ),
        }


__all__ = ["DEFAULT_DAYS", "DEFAULT_SOURCES", "UpdateMonitor", "cycle_for"]
