from __future__ import annotations

from pathlib import Path
from typing import Any

from core.secure_store import clear_secret, load_secret_map, save_secret_map

from .api_das_questoes import ApiDasQuestoesAdapter
from .local import LocalQuestionCatalogAdapter


PROVIDERS = frozenset({"local", "api_das_questoes"})


def credential_path(config_path: str | Path) -> Path:
    return Path(config_path).resolve().parent / "api_das_questoes_credentials.dat"


class QuestionCatalogService:
    """Caso de uso vertical que escolhe o adapter sem expor infraestrutura à UI."""

    def __init__(self, queries: Any, *, config: dict[str, Any], config_path: str | Path) -> None:
        self.queries = queries
        self.config = config
        self.config_path = Path(config_path)

    def provider_id(self) -> str:
        value = str(self.config.get("question_source_provider") or "local").strip().casefold()
        return value if value in PROVIDERS else "local"

    def _api_key(self) -> str:
        return str(load_secret_map(credential_path(self.config_path)).get("api_key") or "")

    def provider(self, provider_id: str | None = None):
        selected = str(provider_id or self.provider_id()).strip().casefold()
        if selected == "api_das_questoes":
            return ApiDasQuestoesAdapter(
                api_key=self._api_key(),
                config=self.config,
                config_path=self.config_path,
                base_url=str(self.config.get("api_das_questoes_base_url") or ApiDasQuestoesAdapter.DEFAULT_BASE_URL),
                timeout=float(self.config.get("api_das_questoes_timeout_seconds") or 20),
                review_status=str(self.config.get("api_das_questoes_default_review_status") or "pendente"),
            )
        return LocalQuestionCatalogAdapter(self.queries)

    def page(self, **kwargs: Any):
        return self.provider().page(**kwargs)

    def get(self, question_id: str):
        return self.provider().get(question_id)

    def subjects(self):
        return self.provider().subjects()

    def public_settings(self) -> dict[str, Any]:
        return {
            "provider": self.provider_id(),
            "providers": [
                {"id": "local", "name": "SQLite local", "offline": True},
                {"id": "api_das_questoes", "name": "APIdasQuestões", "offline": False},
            ],
            "api_das_questoes": {
                "base_url": str(self.config.get("api_das_questoes_base_url") or ApiDasQuestoesAdapter.DEFAULT_BASE_URL),
                "timeout_seconds": int(self.config.get("api_das_questoes_timeout_seconds") or 20),
                "api_key_configured": bool(self._api_key()),
                "documentation": "https://www.apidasquestoes.com.br/documentacao",
                "server_side_only": True,
            },
        }

    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = dict(payload or {})
        provider = str(data.get("provider") or self.provider_id()).strip().casefold()
        if provider not in PROVIDERS:
            raise ValueError("Fonte de questões inválida.")
        base_url = str(data.get("base_url") or self.config.get("api_das_questoes_base_url") or ApiDasQuestoesAdapter.DEFAULT_BASE_URL).strip().rstrip("/")
        if not base_url.lower().startswith("https://"):
            raise ValueError("A URL da fonte externa deve usar HTTPS.")
        self.config["question_source_provider"] = provider
        self.config["api_das_questoes_base_url"] = base_url
        if "timeout_seconds" in data:
            self.config["api_das_questoes_timeout_seconds"] = max(3, min(120, int(data.get("timeout_seconds") or 20)))
        key = str(data.get("api_key") or "").strip()
        path = credential_path(self.config_path)
        if bool(data.get("clear_api_key")):
            clear_secret(path)
        elif key:
            save_secret_map(path, {"api_key": key}, description="QuestFlow APIdasQuestoes API Key")
        return self.public_settings()

    def test(self, provider_id: str | None = None) -> dict[str, Any]:
        return self.provider(provider_id).health()


__all__ = ["PROVIDERS", "QuestionCatalogService", "credential_path"]
