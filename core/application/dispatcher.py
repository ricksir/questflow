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
        create_question: Callable[[], dict[str, Any]] | None = None,
        save_question: Callable[[str, dict[str, Any], bool], dict[str, Any]] | None = None,
        delete_question: Callable[[str], dict[str, Any]] | None = None,
        annul_question: Callable[[str, str], dict[str, Any]] | None = None,
        remove_image: Callable[[str], dict[str, Any]] | None = None,
        list_subjects: Callable[[], dict[str, Any]] | None = None,
        get_classification_options: Callable[[str, str], dict[str, Any]] | None = None,
        update_classification: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        organize_lesson_group: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.catalog = catalog
        self.architecture = architecture
        self.persist_config = persist_config
        self.present_question = present_question
        self.create_question = create_question
        self.save_question = save_question
        self.delete_question = delete_question
        self.annul_question = annul_question
        self.remove_image = remove_image
        self.list_subjects = list_subjects
        self.get_classification_options = get_classification_options
        self.update_classification = update_classification
        self.organize_lesson_group = organize_lesson_group
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
        self.register(UseCaseDefinition("questions.create", self._questions_create, mutating=True, module="editorial_bank"))
        self.register(UseCaseDefinition("questions.update", self._questions_update, mutating=True, module="editorial_bank"))
        self.register(UseCaseDefinition("questions.delete", self._questions_delete, mutating=True, module="editorial_bank"))
        self.register(UseCaseDefinition("questions.annul", self._questions_annul, mutating=True, module="editorial_bank"))
        self.register(UseCaseDefinition("questions.image.remove", self._questions_image_remove, mutating=True, module="editorial_bank"))
        self.register(UseCaseDefinition("questions.classification.update", self._questions_classification_update, mutating=True, module="editorial_bank"))
        self.register(UseCaseDefinition("taxonomy.subjects.list", self._taxonomy_subjects_list, module="editorial_bank"))
        self.register(UseCaseDefinition("taxonomy.classification.options", self._taxonomy_classification_options, module="editorial_bank"))
        self.register(UseCaseDefinition("taxonomy.lesson_group.organize", self._taxonomy_lesson_group_organize, mutating=True, module="editorial_bank"))
        self.register(UseCaseDefinition("editorial.bank.summary", self._editorial_bank_summary, module="editorial_bank"))
        self.register(UseCaseDefinition("editorial.curation.attention", self._editorial_curation_attention, module="editorial_bank"))
        self.register(UseCaseDefinition("curation.review.complete", self._curation_review_complete, mutating=True, module="editorial_bank"))
        self.register(UseCaseDefinition("knowledge.semantic.summary", self._knowledge_semantic_summary, module="knowledge"))
        self.register(UseCaseDefinition("learning.recommendations.dashboard", self._learning_recommendations_dashboard, module="learning"))
        self.register(UseCaseDefinition("learning.simulations.get", self._learning_simulation_get, module="learning"))
        self.register(UseCaseDefinition("governance.ai.audit.list", self._governance_ai_audit_list, module="governance"))
        self.register(UseCaseDefinition("governance.ai.interactions.get", self._governance_ai_interaction_get, module="governance"))
        self.register(UseCaseDefinition("questions.intelligence.refresh", self._question_intelligence_refresh, mutating=True, module="editorial_bank"))
        self.register(UseCaseDefinition("knowledge.questions.graph", self._knowledge_question_graph, module="knowledge"))
        self.register(UseCaseDefinition("knowledge.rag.context", self._knowledge_rag_context, module="knowledge"))
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

    def _questions_create(self, _payload: dict[str, Any]) -> dict[str, Any]:
        if self.create_question is None:
            raise UseCaseError("Criação manual indisponível.", code="unavailable", status=503)
        result = self.create_question()
        if not isinstance(result, dict) or not str(result.get("uid") or "").strip():
            raise UseCaseError("Criação manual retornou um resultado inválido.", code="internal_error", status=500)
        return result

    def _questions_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or payload.get("id") or "").strip()
        question = payload.get("question")
        approve = bool(payload.get("approve", False))
        if not uid:
            raise UseCaseError("Informe o identificador da questão.", code="validation_error")
        if not isinstance(question, dict):
            raise UseCaseError("Dados inválidos.", code="validation_error")
        if self.save_question is None:
            raise UseCaseError("Salvamento editorial indisponível.", code="unavailable", status=503)
        result = self.save_question(uid, question, approve)
        if not isinstance(result, dict):
            raise UseCaseError("Salvamento editorial retornou um resultado inválido.", code="internal_error", status=500)
        if result.get("ok") is False:
            raise UseCaseError(
                str(result.get("error") or "Falha ao salvar a questão."),
                code=str(result.get("code") or "validation_error"),
                status=int(result.get("status") or 400),
            )
        return {key: value for key, value in result.items() if key != "ok"}

    def _questions_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or payload.get("id") or "").strip()
        if not uid:
            raise UseCaseError("Informe o identificador da questão.", code="validation_error")
        if self.delete_question is None:
            raise UseCaseError("Exclusão editorial indisponível.", code="unavailable", status=503)
        result = self.delete_question(uid)
        if not isinstance(result, dict):
            raise UseCaseError("Exclusão editorial retornou um resultado inválido.", code="internal_error", status=500)
        if result.get("ok") is False:
            raise UseCaseError(
                str(result.get("error") or "Não foi possível excluir a questão."),
                code=str(result.get("code") or "validation_error"),
                status=int(result.get("status") or 400),
            )
        return {key: value for key, value in result.items() if key != "ok"}

    def _questions_annul(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or payload.get("id") or "").strip()
        reason = str(payload.get("reason") or "Questão anulada pela banca").strip()
        if not uid:
            raise UseCaseError("Informe o identificador da questão.", code="validation_error")
        if self.annul_question is None:
            raise UseCaseError("Anulação editorial indisponível.", code="unavailable", status=503)
        result = self.annul_question(uid, reason)
        if not isinstance(result, dict):
            raise UseCaseError("Anulação editorial retornou um resultado inválido.", code="internal_error", status=500)
        if result.get("ok") is False:
            raise UseCaseError(
                str(result.get("error") or "Não foi possível anular a questão."),
                code=str(result.get("code") or "validation_error"),
                status=int(result.get("status") or 400),
            )
        return {key: value for key, value in result.items() if key != "ok"}

    def _questions_image_remove(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or payload.get("id") or "").strip()
        if not uid:
            raise UseCaseError("Informe o identificador da questão.", code="validation_error")
        if self.remove_image is None:
            raise UseCaseError("Remoção de imagem indisponível.", code="unavailable", status=503)
        result = self.remove_image(uid)
        if not isinstance(result, dict):
            raise UseCaseError("Remoção de imagem retornou um resultado inválido.", code="internal_error", status=500)
        if result.get("ok") is False:
            raise UseCaseError(
                str(result.get("error") or "Não foi possível remover a imagem."),
                code=str(result.get("code") or "validation_error"),
                status=int(result.get("status") or 400),
            )
        return {key: value for key, value in result.items() if key != "ok"}

    def _questions_classification_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or payload.get("id") or "").strip()
        classification = payload.get("classification")
        if not uid:
            raise UseCaseError("Informe o identificador da questão.", code="validation_error")
        if not isinstance(classification, dict):
            raise UseCaseError("Dados de classificação inválidos.", code="validation_error")
        if self.update_classification is None:
            raise UseCaseError("Correção de classificação indisponível.", code="unavailable", status=503)
        result = self.update_classification(uid, classification)
        if not isinstance(result, dict):
            raise UseCaseError("Correção de classificação retornou um resultado inválido.", code="internal_error", status=500)
        if result.get("ok") is False:
            raise UseCaseError(
                str(result.get("error") or "Não foi possível salvar a classificação."),
                code=str(result.get("code") or "validation_error"),
                status=int(result.get("status") or 400),
            )
        return {key: value for key, value in result.items() if key != "ok"}

    def _taxonomy_subjects_list(self, _payload: dict[str, Any]) -> dict[str, Any]:
        if self.list_subjects is None:
            raise UseCaseError("Listagem de matérias indisponível.", code="unavailable", status=503)
        result = self.list_subjects()
        if not isinstance(result, dict):
            raise UseCaseError("Listagem de matérias retornou um resultado inválido.", code="internal_error", status=500)
        if result.get("ok") is False:
            raise UseCaseError(
                str(result.get("error") or "Não foi possível listar as matérias."),
                code=str(result.get("code") or "validation_error"),
                status=int(result.get("status") or 400),
            )
        return {key: value for key, value in result.items() if key != "ok"}

    def _taxonomy_classification_options(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.get_classification_options is None:
            raise UseCaseError("Opções de classificação indisponíveis.", code="unavailable", status=503)
        subject = str(payload.get("subject") or "").strip()
        lesson = str(payload.get("lesson") or "").strip()
        result = self.get_classification_options(subject, lesson)
        if not isinstance(result, dict):
            raise UseCaseError("Opções de classificação retornaram um resultado inválido.", code="internal_error", status=500)
        if result.get("ok") is False:
            raise UseCaseError(
                str(result.get("error") or "Não foi possível carregar as opções de classificação."),
                code=str(result.get("code") or "validation_error"),
                status=int(result.get("status") or 400),
            )
        return {key: value for key, value in result.items() if key != "ok"}

    def _taxonomy_lesson_group_organize(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.organize_lesson_group is None:
            raise UseCaseError("Organização de aula indisponível.", code="unavailable", status=503)
        result = self.organize_lesson_group(dict(payload))
        if not isinstance(result, dict):
            raise UseCaseError("Organização de aula retornou um resultado inválido.", code="internal_error", status=500)
        if result.get("ok") is False:
            raise UseCaseError(
                str(result.get("error") or "Não foi possível organizar a aula."),
                code=str(result.get("code") or "validation_error"),
                status=int(result.get("status") or 400),
            )
        return {key: value for key, value in result.items() if key != "ok"}

    def _curation_review_complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or payload.get("id") or "").strip()
        reviewer = str(payload.get("reviewer") or "").strip()
        if not uid:
            raise UseCaseError("Informe o identificador da questão.", code="validation_error")
        try:
            editorial = self.architecture.modules.get("editorial_bank").instance
        except KeyError as error:
            raise UseCaseError("Módulo editorial indisponível.", code="unavailable", status=503) from error
        if editorial is None or not callable(getattr(editorial, "complete_review", None)):
            raise UseCaseError("Conclusão de curadoria indisponível.", code="unavailable", status=503)
        result = editorial.complete_review(uid, reviewer=reviewer)
        if not isinstance(result, dict):
            raise UseCaseError("Conclusão de curadoria retornou um resultado inválido.", code="internal_error", status=500)
        if result.get("ok") is False:
            # Pendências de curadoria são um resultado de negócio válido.
            # Mantemos blocking_missing e demais detalhes para o Studio orientar
            # o usuário sem converter a decisão editorial em erro de transporte.
            return dict(result)
        return {key: value for key, value in result.items() if key != "ok"}

    def _editorial_bank_summary(self, _payload: dict[str, Any]) -> dict[str, Any]:
        try:
            editorial = self.architecture.modules.get("editorial_bank").instance
        except KeyError as error:
            raise UseCaseError("Módulo editorial indisponível.", code="unavailable", status=503) from error
        if editorial is None or not callable(getattr(editorial, "summary", None)):
            raise UseCaseError("Inteligência editorial indisponível.", code="unavailable", status=503)
        summary = editorial.summary()
        if not isinstance(summary, dict):
            raise UseCaseError("Inteligência editorial retornou um resultado inválido.", code="internal_error", status=500)
        return {"summary": summary}

    def _editorial_curation_attention(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            editorial = self.architecture.modules.get("editorial_bank").instance
        except KeyError as error:
            raise UseCaseError("Módulo editorial indisponível.", code="unavailable", status=503) from error
        if editorial is None or not callable(getattr(editorial, "attention", None)):
            raise UseCaseError("Fila de atenção editorial indisponível.", code="unavailable", status=503)
        result = editorial.attention(
            str(payload.get("kind") or "curation"),
            limit=int(payload.get("limit") or 100),
        )
        if not isinstance(result, dict):
            raise UseCaseError("Fila de atenção editorial retornou um resultado inválido.", code="internal_error", status=500)
        return result

    def _knowledge_semantic_summary(self, _payload: dict[str, Any]) -> dict[str, Any]:
        try:
            knowledge = self.architecture.modules.get("knowledge").instance
        except KeyError as error:
            raise UseCaseError("Módulo de conhecimento indisponível.", code="unavailable", status=503) from error
        if knowledge is None or not callable(getattr(knowledge, "summary", None)):
            raise UseCaseError("Índice semântico indisponível.", code="unavailable", status=503)
        summary = knowledge.summary()
        if not isinstance(summary, dict):
            raise UseCaseError("Índice semântico retornou um resultado inválido.", code="internal_error", status=500)
        return {"summary": summary}

    def _learning_recommendations_dashboard(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            learning = self.architecture.modules.get("learning").instance
        except KeyError as error:
            raise UseCaseError("Learning Engine indisponível.", code="unavailable", status=503) from error
        if learning is None or not callable(getattr(learning, "recommendation_dashboard", None)):
            raise UseCaseError("Recomendador indisponível.", code="unavailable", status=503)
        dashboard = learning.recommendation_dashboard(mode=str(payload.get("mode") or "equilibrado"))
        if not isinstance(dashboard, dict):
            raise UseCaseError("Recomendador retornou um resultado inválido.", code="internal_error", status=500)
        return {"dashboard": dashboard}

    def _learning_simulation_get(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id") or payload.get("id") or "").strip()
        if not session_id:
            raise UseCaseError("Informe a sessão do simulado.", code="validation_error")
        try:
            learning = self.architecture.modules.get("learning").instance
        except KeyError as error:
            raise UseCaseError("Learning Engine indisponível.", code="unavailable", status=503) from error
        if learning is None or not callable(getattr(learning, "simulation", None)):
            raise UseCaseError("Simulado adaptativo indisponível.", code="unavailable", status=503)
        simulation = learning.simulation(session_id)
        if not isinstance(simulation, dict):
            raise UseCaseError("Simulado adaptativo retornou um resultado inválido.", code="internal_error", status=500)
        return {"simulation": simulation}

    def _governance_ai_audit_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            governance = self.architecture.modules.get("governance").instance
        except KeyError as error:
            raise UseCaseError("Governança de IA indisponível.", code="unavailable", status=503) from error
        if (
            governance is None
            or not callable(getattr(governance, "dashboard", None))
            or not callable(getattr(governance, "recent_audit", None))
        ):
            raise UseCaseError("Auditoria de IA indisponível.", code="unavailable", status=503)
        limit = max(1, min(100, int(payload.get("limit") or 20)))
        summary = governance.dashboard()
        items = governance.recent_audit(limit=limit)
        if not isinstance(summary, dict) or not isinstance(items, list):
            raise UseCaseError("Auditoria de IA retornou um resultado inválido.", code="internal_error", status=500)
        return {"summary": summary, "items": items}

    def _governance_ai_interaction_get(self, payload: dict[str, Any]) -> dict[str, Any]:
        interaction_id = str(payload.get("interaction_id") or payload.get("id") or "").strip()
        if not interaction_id:
            raise UseCaseError("Informe a interação de IA.", code="validation_error")
        try:
            governance = self.architecture.modules.get("governance").instance
        except KeyError as error:
            raise UseCaseError("Governança de IA indisponível.", code="unavailable", status=503) from error
        if governance is None or not callable(getattr(governance, "interaction", None)):
            raise UseCaseError("Auditoria de interação indisponível.", code="unavailable", status=503)
        interaction = governance.interaction(interaction_id)
        if not isinstance(interaction, dict):
            raise UseCaseError("Interação de IA retornou um resultado inválido.", code="internal_error", status=500)
        return {"interaction": interaction}

    def _question_intelligence_refresh(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or payload.get("id") or "").strip()
        if not uid:
            raise UseCaseError("Informe o identificador da questão.", code="validation_error")
        try:
            editorial = self.architecture.modules.get("editorial_bank").instance
            learner = self.architecture.modules.get("learner_model").instance
        except KeyError as error:
            raise UseCaseError("Inteligência da questão indisponível.", code="unavailable", status=503) from error
        if editorial is None or not callable(getattr(editorial, "intelligence", None)):
            raise UseCaseError("Inteligência editorial indisponível.", code="unavailable", status=503)
        if learner is None or not callable(getattr(learner, "question_state", None)):
            raise UseCaseError("Learner Model indisponível.", code="unavailable", status=503)
        intelligence = editorial.intelligence(uid, scan_duplicates=bool(payload.get("scan_duplicates", True)))
        if not isinstance(intelligence, dict):
            raise UseCaseError("Inteligência da questão retornou um resultado inválido.", code="internal_error", status=500)
        intelligence["learning_model"] = learner.question_state(uid)
        return {"intelligence": intelligence}

    def _knowledge_question_graph(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or payload.get("id") or "").strip()
        if not uid:
            raise UseCaseError("Informe o identificador da questão.", code="validation_error")
        try:
            knowledge = self.architecture.modules.get("knowledge").instance
        except KeyError as error:
            raise UseCaseError("Módulo de conhecimento indisponível.", code="unavailable", status=503) from error
        if knowledge is None or not callable(getattr(knowledge, "graph", None)):
            raise UseCaseError("Grafo de conhecimento indisponível.", code="unavailable", status=503)
        graph = knowledge.graph(uid)
        if not isinstance(graph, dict):
            raise UseCaseError("Grafo de conhecimento retornou um resultado inválido.", code="internal_error", status=500)
        return {"graph": graph}

    def _knowledge_rag_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or payload.get("id") or "").strip()
        if not uid:
            raise UseCaseError("Informe o identificador da questão.", code="validation_error")
        try:
            knowledge = self.architecture.modules.get("knowledge").instance
        except KeyError as error:
            raise UseCaseError("Módulo de conhecimento indisponível.", code="unavailable", status=503) from error
        if knowledge is None or not callable(getattr(knowledge, "retrieve", None)):
            raise UseCaseError("Contexto RAG indisponível.", code="unavailable", status=503)
        retrieval = knowledge.retrieve(
            uid,
            str(payload.get("query") or ""),
            limit=max(1, min(20, int(payload.get("limit") or 8))),
        )
        if not isinstance(retrieval, dict):
            raise UseCaseError("Contexto RAG retornou um resultado inválido.", code="internal_error", status=500)
        return {"retrieval": retrieval}

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
