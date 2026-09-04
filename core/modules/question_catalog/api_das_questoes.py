from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from core.network import NetworkManager

from .normalizer import normalize_api_question


class ApiDasQuestoesError(RuntimeError):
    def __init__(self, message: str, *, status: int = 0, retry_after: int = 0) -> None:
        super().__init__(message)
        self.status = int(status or 0)
        self.retry_after = int(retry_after or 0)


@dataclass(slots=True)
class ApiResponse:
    data: Any
    headers: dict[str, str]
    elapsed_ms: int


class ApiDasQuestoesAdapter:
    provider_id = "api_das_questoes"
    DEFAULT_BASE_URL = "https://api.apidasquestoes.com.br/api/v1"

    def __init__(
        self,
        *,
        api_key: str,
        config: dict[str, Any] | None = None,
        config_path: Any | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int | float = 20,
        transport: Callable[[urllib.request.Request, float], Any] | None = None,
        review_status: str = "pendente",
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.config = dict(config or {})
        self.config_path = config_path
        self.base_url = str(base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        if not self.base_url.lower().startswith("https://"):
            raise ValueError("A APIdasQuestões deve usar uma URL HTTPS.")
        self.timeout = max(3.0, min(120.0, float(timeout or 20)))
        self.transport = transport
        self.review_status = str(review_status or "pendente")
        self.last_quota: dict[str, Any] = {}
        self._subject_cache: tuple[float, list[dict[str, Any]]] | None = None

    def _open(self, request: urllib.request.Request):
        if self.transport is not None:
            return self.transport(request, self.timeout)
        return NetworkManager(self.config, config_path=self.config_path).open(request, timeout=self.timeout)

    def _request(self, path: str, *, params: dict[str, Any] | None = None, require_key: bool = True) -> ApiResponse:
        query = urllib.parse.urlencode(
            [(str(key), str(value)) for key, value in (params or {}).items() if value not in (None, "", [])]
        )
        url = f"{self.base_url}/{path.lstrip('/')}" + (f"?{query}" if query else "")
        headers = {"Accept": "application/json", "User-Agent": "QuestFlow-Studio/6"}
        if require_key:
            if not self.api_key:
                raise ApiDasQuestoesError("Configure a API Key da APIdasQuestões antes de buscar questões.", status=401)
            headers["x-api-key"] = self.api_key
        request = urllib.request.Request(url, headers=headers, method="GET")
        started = time.perf_counter()
        try:
            response = self._open(request)
            raw = response.read()
            response_headers = {str(key): str(value) for key, value in response.headers.items()}
        except urllib.error.HTTPError as error:
            retry = int(str(error.headers.get("Retry-After") or "0") or 0)
            try:
                detail = json.loads(error.read().decode("utf-8", "replace"))
                message = str(detail.get("message") or detail.get("error") or "")
            except Exception:
                message = ""
            friendly = {
                400: "Filtros inválidos para a APIdasQuestões.",
                401: "API Key ausente ou inválida.",
                403: "A conta da APIdasQuestões não está autorizada.",
                404: "Questão não encontrada na APIdasQuestões.",
                429: "Limite da APIdasQuestões atingido.",
            }.get(int(error.code), f"A APIdasQuestões respondeu HTTP {error.code}.")
            raise ApiDasQuestoesError(message or friendly, status=int(error.code), retry_after=retry) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ApiDasQuestoesError(f"Não foi possível acessar a APIdasQuestões: {error}") from error
        elapsed = int((time.perf_counter() - started) * 1000)
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as error:
            raise ApiDasQuestoesError("A APIdasQuestões retornou JSON inválido.") from error
        lower_headers = {key.casefold(): value for key, value in response_headers.items()}
        self.last_quota = {
            "limit": lower_headers.get("x-ratelimit-limit", ""),
            "remaining": lower_headers.get("x-ratelimit-remaining", ""),
            "plan": lower_headers.get("x-plano", ""),
            "question_limit": lower_headers.get("x-quota-questoes-limite", ""),
            "question_remaining": lower_headers.get("x-quota-questoes-restantes", ""),
        }
        return ApiResponse(data=data, headers=response_headers, elapsed_ms=elapsed)

    @staticmethod
    def _csv(value: Any) -> str:
        if isinstance(value, (list, tuple, set)):
            return ",".join(str(item) for item in value if str(item).strip())
        return str(value or "").strip()

    def _subject_id(self, subject: str) -> str:
        target = str(subject or "").strip().casefold()
        if not target:
            return ""
        for item in self.subjects():
            if str(item.get("nome") or item.get("label") or "").strip().casefold() == target:
                return str(item.get("id") or "")
        return ""

    def page(
        self,
        *,
        search: str = "",
        status: str = "todos",
        subject: str = "",
        lesson: str = "",
        offset: int = 0,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
    ) -> tuple[int, list[dict[str, Any]], dict[str, Any]]:
        del lesson  # A API pública não oferece uma dimensão equivalente a aula.
        normalized_status = str(status or "todos").strip().casefold()
        if normalized_status in {"aprovado", "aprovado_automaticamente"}:
            # Aprovação é estado editorial local. Itens externos entram como
            # somente leitura/pendentes e portanto não podem satisfazer esse filtro.
            return 0, [], {"provider": self.provider_id, "external_review_state": "read_only_pending"}
        wanted = max(1, min(2000, int(limit or 100)))
        requested = min(100, wanted)  # limite oficial por chamada
        offset = max(0, int(offset or 0))
        page = offset // requested
        first_page = page
        first_skip = offset % requested
        params: dict[str, Any] = {"size": requested}
        if search:
            params["q"] = str(search)
        subject_id = self._subject_id(subject)
        if subject_id:
            params["materiaId"] = subject_id
        if normalized_status in {"anulada", "anuladas"}:
            params["anulada"] = "true"
        elif normalized_status in {"pendente", "pendentes"}:
            params["anulada"] = "false"
        allowed = {
            "sort", "materiaId", "bancaId", "topicoId", "instituicaoId", "areaId", "ambitoId",
            "cargoId", "provaId", "ano", "nivel", "dificuldade", "certoOuErrado", "anulada",
            "desatualizada", "cargo", "q", "externalId",
        }
        for key, value in (filters or {}).items():
            if key in allowed and value not in (None, "", []):
                params[key] = self._csv(value)
        items: list[dict[str, Any]] = []
        total = 0
        total_pages = 0
        elapsed_ms = 0
        fetched_pages = 0
        reached_last = False
        while len(items) < wanted and not reached_last:
            page_params = {**params, "page": page}
            response = self._request("questoes", params=page_params)
            elapsed_ms += response.elapsed_ms
            fetched_pages += 1
            payload = response.data if isinstance(response.data, dict) else {}
            rows = payload.get("content") if isinstance(payload.get("content"), list) else []
            total = int(payload.get("totalElements") or total or len(rows))
            total_pages = int(payload.get("totalPages") or total_pages or 0)
            normalized = [
                normalize_api_question(row, review_status=self.review_status)
                for row in rows if isinstance(row, dict)
            ]
            if page == first_page and first_skip:
                normalized = normalized[first_skip:]
            remaining = wanted - len(items)
            items.extend(normalized[:remaining])
            reached_last = bool(payload.get("last", False)) or not rows
            if total_pages:
                reached_last = reached_last or page + 1 >= total_pages
            # Proteção contra APIs que omitem ``last``/``totalPages``.
            reached_last = reached_last or len(rows) < requested
            page += 1
        return total, items, {
            "provider": self.provider_id,
            "page": first_page,
            "size": int(payload.get("size") or requested),
            "total_pages": total_pages,
            "first": offset == 0,
            "last": reached_last,
            "fetched_pages": fetched_pages,
            "returned": len(items),
            "quota": dict(self.last_quota),
            "elapsed_ms": elapsed_ms,
        }

    def get(self, question_id: str) -> dict[str, Any] | None:
        raw = str(question_id or "").strip()
        if raw.startswith("api_das_questoes:"):
            raw = raw.split(":", 1)[1]
        if not raw:
            return None
        try:
            response = self._request(f"questoes/{urllib.parse.quote(raw, safe='')}")
        except ApiDasQuestoesError as error:
            if error.status == 404:
                return None
            raise
        if not isinstance(response.data, dict):
            return None
        return normalize_api_question(response.data, review_status=self.review_status)

    def subjects(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._subject_cache and now - self._subject_cache[0] < 900:
            return list(self._subject_cache[1])
        response = self._request("materias", params={"withTopics": "false"}, require_key=False)
        raw = response.data
        if isinstance(raw, dict):
            raw = raw.get("content") or raw.get("items") or raw.get("data") or []
        items = []
        if isinstance(raw, list):
            for value in raw:
                if not isinstance(value, dict):
                    continue
                item = dict(value)
                # A API pública usa atualmente ``label`` nas listas de
                # referência; ``nome`` mantém o port interno estável.
                item["nome"] = str(item.get("nome") or item.get("label") or item.get("name") or "").strip()
                items.append(item)
        self._subject_cache = (now, items)
        return list(items)

    def health(self) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            if self.api_key:
                total, items, meta = self.page(limit=1)
                return {
                    "ok": True, "provider": self.provider_id, "authenticated": True,
                    "sample_count": len(items), "total": total, "quota": meta.get("quota", {}),
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                }
            subjects = self.subjects()
            return {
                "ok": True, "provider": self.provider_id, "authenticated": False,
                "reference_lists_available": True, "subjects": len(subjects),
                "detail": "Listas abertas disponíveis; configure a API Key para buscar questões.",
            }
        except ApiDasQuestoesError as error:
            return {"ok": False, "provider": self.provider_id, "status": error.status, "error": str(error), "retry_after": error.retry_after}


__all__ = ["ApiDasQuestoesAdapter", "ApiDasQuestoesError"]
