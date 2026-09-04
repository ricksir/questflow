from __future__ import annotations

from typing import Any


class LocalQuestionCatalogAdapter:
    provider_id = "local"

    def __init__(self, queries: Any) -> None:
        self.queries = queries

    def page(self, *, search: str = "", status: str = "todos", subject: str = "", lesson: str = "", offset: int = 0, limit: int = 100, filters: dict[str, Any] | None = None):
        del filters
        total, rows = self.queries.page(
            search=str(search or ""), status=str(status or "todos"), subject=str(subject or ""),
            lesson=str(lesson or ""), offset=max(0, int(offset or 0)), limit=max(1, int(limit or 100)),
        )
        return total, rows, {"provider": self.provider_id, "offline": True}

    def get(self, question_id: str):
        return self.queries.get(str(question_id))

    def subjects(self) -> list[dict[str, Any]]:
        return [{"id": item, "nome": item} for item in self.queries.subjects()]

    def health(self) -> dict[str, Any]:
        return {"ok": True, "provider": self.provider_id, "offline": True, "stats": self.queries.stats()}


__all__ = ["LocalQuestionCatalogAdapter"]

