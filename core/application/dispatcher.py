from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from core.architecture import DomainEvent


class UseCaseError(RuntimeError):
    def __init__(self, message: str, *, code: str = "use_case_error", status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = int(status)


@dataclass(frozen=True, slots=True)
class UseCaseDefinition:
    name: str
    handler: Callable[[dict[str, Any]], Any]
    mutating: bool = False
    module: str = "platform"


def _summary(question: dict[str, Any]) -> dict[str, Any]:
    review = question.get("revisao", {}) if isinstance(question.get("revisao"), dict) else {}
    image = question.get("imagem_questao", {}) if isinstance(question.get("imagem_questao"), dict) else {}
    return {
        "uid": str(question.get("database_uid") or question.get("uid") or ""),
        "codigo": str(question.get("codigo_origem") or question.get("source_code") or ""),
        "materia": str(question.get("materia") or question.get("subject") or ""),
        "aula": str(question.get("aula_planilha") or question.get("lesson") or ""),
        "titulo_aula": str(question.get("titulo_aula") or question.get("lesson_title") or ""),
        "assunto": str(question.get("assunto") or question.get("primary_topic") or ""),
        "ano": question.get("ano") or question.get("exam_year") or "",
        "banca": str(question.get("banca") or question.get("board") or ""),
        "arquivo": str(question.get("source_file") or ""),
        "pagina": question.get("source_page") or "",
        "status": str(review.get("status") or question.get("review_status") or "pendente"),
        "origem": str(question.get("origem_questao") or question.get("origin_type") or "nao_informada"),
        "curadoria": str(question.get("curation_status") or "revisar"),
        "qualidade": float(question.get("quality_score") or 0),
        "dificuldade": str(question.get("difficulty_label") or question.get("dificuldade") or "sem_dados"),
        "comentario_origem": str(question.get("commentary_source") or "sem_comentario"),
        "enunciado": str(question.get("enunciado") or question.get("statement") or ""),
        "has_image": bool(str(image.get("path") or "").strip()),
        "external_read_only": bool(question.get("external_read_only")),
    }


class StudioUseCaseDispatcher:
    """Application layer versionada usada por HTTP e pela fachada legada."""

    contract = "questflow.studio.v1"

    def __init__(
        self,
        *,
        catalog: Any,
        architecture: Any,
        persist_config: Callable[[], None],
        present_question: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.catalog = catalog
        self.architecture = architecture
        self.persist_config = persist_config
        self.present_question = present_question
        self._definitions: dict[str, UseCaseDefinition] = {}
        self._register_defaults()

    def register(self, definition: UseCaseDefinition, *, replace: bool = False) -> None:
        if definition.name in self._definitions and not replace:
            raise ValueError(f"Caso de uso já registrado: {definition.name}")
        self._definitions[definition.name] = definition

    def _register_defaults(self) -> None:
        self.register(UseCaseDefinition("system.architecture", self._architecture, module="platform"))
        self.register(UseCaseDefinition("system.projections.status", self._projection_status, module="platform"))
        self.register(UseCaseDefinition("system.projections.rebuild", self._projection_rebuild, mutating=True, module="platform"))
        self.register(UseCaseDefinition("system.events.pending", self._events_pending, module="platform"))
        self.register(UseCaseDefinition("system.events.drain", self._events_drain, mutating=True, module="platform"))
        self.register(UseCaseDefinition("questions.list", self._questions_list, module="editorial_bank"))
        self.register(UseCaseDefinition("questions.get", self._questions_get, module="editorial_bank"))
        self.register(UseCaseDefinition("questions.source.settings", self._source_settings, module="editorial_bank"))
        self.register(UseCaseDefinition("questions.source.save", self._source_save, mutating=True, module="editorial_bank"))
        self.register(UseCaseDefinition("questions.source.test", self._source_test, module="editorial_bank"))

    def catalog_contract(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "operations": [
                {"name": item.name, "module": item.module, "mutating": item.mutating}
                for item in self._definitions.values()
            ],
        }

    def dispatch(self, name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        definition = self._definitions.get(str(name or ""))
        if definition is None:
            raise UseCaseError("Caso de uso desconhecido.", code="unknown_use_case", status=404)
        data = dict(payload or {})
        try:
            result = definition.handler(data)
        except UseCaseError:
            raise
        except (TypeError, ValueError, KeyError) as error:
            raise UseCaseError(str(error), code="validation_error", status=400) from error
        return {
            "ok": True,
            "contract": self.contract,
            "operation": definition.name,
            "module": definition.module,
            "data": result,
        }

    def _architecture(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return self.architecture.architecture()

    def _projection_status(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return {"items": self.architecture.projections.status()}

    def _projection_rebuild(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        if name:
            result = self.architecture.projections.rebuild(name)
        else:
            result = self.architecture.projections.rebuild_all()
        self.architecture.events.publish(DomainEvent(
            event_type="projections.rebuilt",
            module="platform",
            aggregate_type="projection",
            aggregate_id=name or "all",
            payload={"projection": name or "all"},
        ))
        return result

    def _events_pending(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = self.architecture.events.pending(int(payload.get("limit") or 100))
        return {"count": len(items), "items": [event.__dict__ if hasattr(event, "__dict__") else {
            "event_id": event.event_id, "event_type": event.event_type, "module": event.module,
            "aggregate_type": event.aggregate_type, "aggregate_id": event.aggregate_id,
            "payload": event.payload, "occurred_at": event.occurred_at,
        } for event in items]}

    def _events_drain(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.architecture.events.drain(int(payload.get("limit") or 100))

    def _questions_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        start = max(0, int(payload.get("offset") or 0))
        size = max(1, min(2000, int(payload.get("limit") or 500)))
        total, rows, meta = self.catalog.page(
            search=str(payload.get("search") or ""),
            status=str(payload.get("status") or "todos"),
            subject=str(payload.get("subject") or ""),
            lesson=str(payload.get("lesson") or ""),
            offset=start,
            limit=size,
            filters=payload.get("filters") if isinstance(payload.get("filters"), dict) else None,
        )
        return {"total": total, "items": [_summary(item) for item in rows], "meta": meta}

    def _questions_get(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or payload.get("id") or "").strip()
        if not uid:
            raise UseCaseError("Informe o identificador da questão.", code="validation_error")
        question = self.catalog.get(uid)
        if not question:
            raise UseCaseError("Questão não encontrada.", code="not_found", status=404)
        if self.present_question is not None:
            detail = self.present_question(uid, dict(question))
            if not isinstance(detail, dict) or not isinstance(detail.get("question"), dict):
                raise UseCaseError("Apresentação da questão inválida.", code="internal_error", status=500)
            return detail
        return {"question": question, "image": None}

    def _source_settings(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return self.catalog.public_settings()

    def _source_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self.catalog.save_settings(payload)
        self.persist_config()
        self.architecture.events.publish(DomainEvent(
            event_type="question_source.changed",
            module="editorial_bank",
            aggregate_type="question_source",
            aggregate_id=str(settings.get("provider") or "local"),
            payload={"provider": settings.get("provider")},
        ))
        return settings

    def _source_test(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.catalog.test(str(payload.get("provider") or "") or None)


__all__ = ["StudioUseCaseDispatcher", "UseCaseDefinition", "UseCaseError"]
