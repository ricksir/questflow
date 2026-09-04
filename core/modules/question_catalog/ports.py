from __future__ import annotations

from typing import Any, Protocol


class QuestionCatalogPort(Protocol):
    provider_id: str

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
    ) -> tuple[int, list[dict[str, Any]], dict[str, Any]]: ...

    def get(self, question_id: str) -> dict[str, Any] | None: ...

    def subjects(self) -> list[dict[str, Any]]: ...

    def health(self) -> dict[str, Any]: ...


__all__ = ["QuestionCatalogPort"]

