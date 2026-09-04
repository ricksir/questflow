from __future__ import annotations

"""Tutor IA QuestFlow 6.1.

O motor gera rascunhos contextualizados pelo aluno, RAG e diagnóstico. A
avaliação e a decisão de publicação pertencem a outro motor.
"""

import json
import re
from typing import Any

AI_ENGINE_VERSION = "qf-ai-engine-4"
GENERATOR_VERSION = "qf-controlled-generator-1"
GOLD_MODEL_VERSION = "qf-gold-grounded-baseline-2"
ERROR_MODEL_VERSION = "qf-error-diagnosis-1"
TUTOR_MODES = {"rapido", "professor", "socratico", "banca"}
SCAFFOLD_VERSION = "qf-scaffold-1"
SCAFFOLD_LEVELS = {
    0: ("Tentativa independente", "Sem pista de conteúdo; apenas organize o comando e formule sua hipótese."),
    1: ("Pista metacognitiva", "Identifique comando, negação, exceção e o que exatamente precisa ser provado."),
    2: ("Pista conceitual", "Recupere a regra ou conceito central sem olhar o gabarito."),
    3: ("Pista de contraste", "Compare condições e elimine alternativas incompatíveis com a evidência."),
    4: ("Pista quase completa", "Aplique a regra aos elementos do item, ainda sem revelar a alternativa correta."),
    5: ("Explicação completa", "Revela gabarito e fundamentação auditada depois das tentativas graduais."),
}
SCAFFOLD_REPRESENTATIONS = {"texto", "flashcard", "passo_a_passo", "visual"}

ERROR_LABELS = {
    "desconhecimento_conteudo": "Desconhecimento do conteúdo",
    "confusao_conceitual": "Confusão conceitual",
    "excecao_regra": "Regra/exceção",
    "interpretacao": "Interpretação do enunciado",
    "calculo": "Cálculo/procedimento",
    "desatencao": "Desatenção",
    "chute": "Chute / baixa certeza",
    "memoria_esquecimento": "Esquecimento / recuperação da memória",
    "leitura_incompleta": "Leitura incompleta",
    "indeterminado": "Ainda indeterminado",
}


class AIEngine:
    engine_id = "ai_engine"
    name = "AI Engine"
    version = AI_ENGINE_VERSION

    def __init__(self, editorial: Any, learner: Any, learning: Any, knowledge: Any, governance: Any):
        self.editorial = editorial
        self.learner = learner
        self.learning = learning
        self.knowledge = knowledge
        self.governance = governance
        self.api = getattr(editorial, "api", None) or getattr(knowledge, "api", None)

    @staticmethod
    def _answer_text(question: dict, attempt: dict | None) -> str:
        if not attempt:
            return ""
        alternatives = question.get("alternativas") if isinstance(question.get("alternativas"), list) else []
        labels = []
        for index in attempt.get("selected_indices", []) or []:
            if 0 <= int(index) < len(alternatives):
                item = alternatives[int(index)] if isinstance(alternatives[int(index)], dict) else {}
                labels.append(f"{item.get('chave','?')}) {item.get('texto','')}")
        return " | ".join(labels)

    def diagnose_error(self, uid: str, *, persist: bool = True) -> dict:
        question = self.editorial.question(uid)
        attempt = self.learning.latest_attempt(uid)
        learning_state = self.learner.question_state(uid)
        if not attempt:
            diagnosis = {
                "version": ERROR_MODEL_VERSION, "error_type": "indeterminado", "label": ERROR_LABELS["indeterminado"],
                "confidence": 0.12, "signals": ["Ainda não há tentativa registrada para esta questão."],
                "intervention": "Responder a questão ao menos uma vez para habilitar o diagnóstico.",
                "explanation": "Sem evidência comportamental, o QuestFlow evita inventar a causa do erro.",
            }
            return self.governance.record_diagnosis(question_uid=uid, attempt_id=None, diagnosis=diagnosis) if persist else diagnosis

        signals: list[str] = []
        scores = {key: 0.0 for key in ERROR_LABELS}
        correct = bool(attempt.get("is_correct"))
        confidence = str(attempt.get("confidence") or "").casefold()
        reported = str(attempt.get("error_type") or "").casefold()
        response_seconds = float(attempt.get("response_seconds") or 0.0)
        subject_context = self.learning.subject_context(str(question.get("materia") or question.get("subject") or ""))
        avg_seconds = float(subject_context.get("avg_response_seconds") or 0.0)
        mastery = learning_state.get("mastery")
        mastery_conf = float(learning_state.get("mastery_confidence") or 0.0)
        learner_evidence = learning_state.get("evidence") if isinstance(learning_state.get("evidence"), dict) else {}
        learner_abstains = bool(learner_evidence.get("abstain"))
        retrievability = learning_state.get("retrievability")
        scaffold_signal = learning_state.get("scaffolding") if isinstance(learning_state.get("scaffolding"), dict) else {}
        statement = str(question.get("enunciado") or "").casefold()
        subject = str(question.get("materia") or "").casefold()

        if correct:
            scores["indeterminado"] += 0.65
            signals.append("A tentativa mais recente foi correta; não há erro objetivo a explicar.")
        if confidence == "chutei":
            scores["chute"] += 1.35; signals.append("Você marcou a tentativa como chute.")
        if reported == "desatencao":
            scores["desatencao"] += 1.5; signals.append("O erro foi marcado manualmente como desatenção.")
        elif reported == "confundi":
            scores["confusao_conceitual"] += 1.45; signals.append("O erro foi marcado manualmente como confusão.")
        elif reported == "nao_sabia":
            scores["desconhecimento_conteudo"] += 1.5; signals.append("O erro foi marcado manualmente como conteúdo não sabido.")
        if int(attempt.get("learning_gap") or 0):
            scores["desconhecimento_conteudo"] += 0.8; signals.append("A tentativa está marcada como lacuna de estudo.")
        if learner_abstains:
            signals.append("O Learner Model se abstém de concluir domínio porque a evidência ainda é insuficiente.")
        if mastery is not None and mastery_conf >= 0.35 and not learner_abstains:
            mastery = float(mastery)
            if mastery < 0.46:
                scores["desconhecimento_conteudo"] += 0.95; signals.append(f"KT estima domínio baixo ({mastery*100:.0f}%) com evidência útil.")
            elif mastery >= 0.76 and not correct:
                scores["desatencao"] += 0.35
                scores["interpretacao"] += 0.30
                signals.append(f"KT estima domínio alto ({mastery*100:.0f}%); o erro pode não ser falta de conteúdo.")
        if retrievability is not None and float(retrievability) < 0.55 and mastery is not None and not learner_abstains and float(mastery) >= 0.58 and not correct:
            scores["memoria_esquecimento"] += 0.95; signals.append("Domínio conceitual é maior que a recuperabilidade FSRS; sinal de esquecimento.")
        if int(scaffold_signal.get("sessions") or 0) > 0 and float(scaffold_signal.get("average_support") or 0.0) >= 0.68:
            scores["desconhecimento_conteudo"] += 0.28
            scores["confusao_conceitual"] += 0.18
            signals.append("Sessões recentes do Tutor exigiram níveis altos de apoio; sinal complementar de baixa independência nesta questão.")
        elif int(scaffold_signal.get("sessions") or 0) > 0 and float(scaffold_signal.get("independence_score") or 0.0) >= 0.80:
            signals.append("Você resolveu sessões recentes com pouca ajuda do Tutor; o diagnóstico evita interpretar o erro atual automaticamente como falta de conteúdo.")
        if response_seconds > 0 and avg_seconds > 0 and response_seconds < max(5.0, avg_seconds * 0.34) and not correct:
            scores["leitura_incompleta"] += 0.75; scores["desatencao"] += 0.45
            signals.append("Tempo de resposta ficou muito abaixo da sua média recente na matéria.")
        negation_markers = ("exceto", "incorreta", "não é", "nao e", "salvo", "errada")
        if any(marker in statement for marker in negation_markers) and not correct:
            scores["excecao_regra"] += 0.55; scores["interpretacao"] += 0.50
            signals.append("O enunciado contém negação/exceção, padrão com maior risco de inversão da resposta.")
        if any(term in subject for term in ("matem", "estat", "contab", "racioc")) and re.search(r"\d", statement) and not correct:
            scores["calculo"] += 0.35
        if not signals:
            scores["indeterminado"] += 0.7; signals.append("Os sinais disponíveis ainda não distinguem uma causa dominante.")

        error_type, best = max(scores.items(), key=lambda item: item[1])
        total = sum(value for value in scores.values() if value > 0) or 1.0
        conf_score = min(0.96, max(0.18, 0.36 + best / total * 0.62))
        interventions = {
            "desconhecimento_conteudo": "Reestudar o conceito-base no material fonte e resolver 2–3 itens graduais antes de repetir esta questão.",
            "confusao_conceitual": "Comparar lado a lado os conceitos confundidos e registrar uma regra de diferenciação curta.",
            "excecao_regra": "Separar regra geral e exceções em duas linhas; depois refazer o enunciado procurando termos de inversão.",
            "interpretacao": "Reformular o comando da questão em suas palavras antes de analisar as alternativas.",
            "calculo": "Refazer o procedimento sem olhar alternativas e conferir a etapa em que o resultado divergiu.",
            "desatencao": "Usar uma checagem final de 10 segundos: comando, negações e alternativa marcada.",
            "chute": "Transformar o chute em hipótese: justificar por que cada alternativa é correta ou incorreta antes de revelar o gabarito.",
            "memoria_esquecimento": "Fazer recuperação ativa curta agora e manter a revisão FSRS programada; não releia passivamente primeiro.",
            "leitura_incompleta": "Forçar uma segunda leitura do comando e destacar palavras restritivas antes de responder.",
            "indeterminado": "Registrar confiança e tipo de erro na próxima tentativa para aumentar a precisão do diagnóstico.",
        }
        diagnosis = {
            "version": ERROR_MODEL_VERSION,
            "error_type": error_type,
            "label": ERROR_LABELS[error_type],
            "confidence": round(conf_score, 3),
            "signals": signals[:8],
            "intervention": interventions[error_type],
            "explanation": f"Diagnóstico inferido por sinais comportamentais + FSRS/KT/IRT; não é uma certeza causal. Principal hipótese: {ERROR_LABELS[error_type]}.",
            "attempt_id": str(attempt.get("id") or ""),
            "selected_answer": self._answer_text(question, attempt),
        }
        return self.governance.record_diagnosis(question_uid=uid, attempt_id=str(attempt.get("id") or "") or None, diagnosis=diagnosis) if persist else diagnosis

    @staticmethod
    def _source_items(retrieval: dict, question: dict) -> list[dict]:
        sources = []
        explanation = str(question.get("explicacao") or "").strip()
        if explanation:
            sources.append({"title": "Comentário existente no QuestFlow", "provider": "Banco Editorial", "content": explanation, "score": 1.0})
        for item in retrieval.get("items", []) if isinstance(retrieval, dict) else []:
            sources.append({
                "title": str(item.get("title") or "Evidência RAG local"),
                "provider": "Knowledge Engine / RAG híbrido",
                "content": str(item.get("content") or ""),
                "score": float((item.get("scores") or {}).get("score", 0) or 0),
                "modality": str(item.get("modality") or "text"),
                "backend": str(item.get("backend") or "local_text_rag"),
                "grounding": dict(item.get("grounding") or {}),
            })
        return sources[:10]

    def tutor_packet(self, uid: str, *, mode: str = "professor", user_prompt: str = "", persist_diagnosis: bool = True) -> dict:
        mode = str(mode or "professor").casefold()
        if mode not in TUTOR_MODES:
            mode = "professor"
        question = self.editorial.question(uid)
        learning_state = self.learner.question_state(uid)
        attempt = self.learning.latest_attempt(uid)
        diagnosis = self.diagnose_error(uid, persist=bool(persist_diagnosis))
        query = str(user_prompt or question.get("assunto") or question.get("enunciado") or "")[:1200]
        retrieval = self.knowledge.retrieve_multimodal(uid, query, limit=8, backend="hybrid")
        graph = self.knowledge.graph(uid)
        sources = self._source_items(retrieval, question)
        visual_info = question.get("imagem_questao") if isinstance(question.get("imagem_questao"), dict) else {}
        visual_context = question.get("contexto_visual") if isinstance(question.get("contexto_visual"), dict) else {}
        media = []
        for item in retrieval.get("items", []) if isinstance(retrieval, dict) else []:
            if isinstance(item, dict):
                media.extend([dict(x) for x in (item.get("media") or []) if isinstance(x, dict)])
        multimodal = {
            "engine": str(retrieval.get("engine") or "qf-multimodal-rag-3") if isinstance(retrieval, dict) else "qf-multimodal-rag-3",
            "retrieval_backend": str(retrieval.get("backend") or "hybrid") if isinstance(retrieval, dict) else "hybrid",
            "has_image": any(str(x.get("kind") or "") == "image" for x in media) or bool(str(visual_info.get("path") or "").strip()),
            "has_pdf": any(str(x.get("kind") or "") == "pdf" for x in media),
            "media": media,
            "image_meta": {k: v for k, v in visual_info.items() if k != "path"},
            "visual_context": visual_context,
            "source_page": question.get("source_page"),
            "external_image_upload": False,
            "privacy_note": "Imagem/PDF permanece local por padrão e só é anexado a uma IA externa após opt-in explícito no Centro de Privacidade.",
        }
        learner_context = {
            "mastery": learning_state.get("mastery"),
            "mastery_confidence": learning_state.get("mastery_confidence"),
            "mastery_label": learning_state.get("mastery_label"),
            "evidence": learning_state.get("evidence", {}),
            "retrievability": learning_state.get("retrievability"),
            "theta_scale": learning_state.get("theta_scale"),
            "item_difficulty": learning_state.get("item_difficulty_label"),
            "fusion_priority": learning_state.get("fusion_priority"),
            "support_adjusted_mastery": learning_state.get("support_adjusted_mastery"),
            "support_adjusted_confidence": learning_state.get("support_adjusted_confidence"),
            "scaffolding": learning_state.get("scaffolding", {}),
            "concepts": learning_state.get("concepts", [])[:12],
            "latest_attempt": attempt,
        }
        return {
            "schema": "questflow.tutor.packet.v1",
            "mode": mode,
            "question": question,
            "learner": learner_context,
            "diagnosis": diagnosis,
            "retrieval": retrieval,
            "graph": graph,
            "sources": sources,
            "multimodal": multimodal,
            "user_prompt": str(user_prompt or "").strip(),
        }

    @staticmethod
    def _prompt(packet: dict) -> str:
        question = packet["question"]
        learner = packet["learner"]
        diagnosis = packet["diagnosis"]
        evidence = "\n\n".join(f"[{i+1}] {src.get('title')}: {src.get('content','')[:1200]}" for i, src in enumerate(packet["sources"]))
        return (
            "Você é o Tutor IA do QuestFlow. Use somente as evidências fornecidas para fatos específicos. "
            "Não invente artigo, jurisprudência ou dado. O gabarito cadastrado é referência, mas conflitos devem ser sinalizados.\n"
            f"MODO={packet['mode']}\nPERGUNTA_DO_ALUNO={packet.get('user_prompt','')}\n"
            f"MATÉRIA={question.get('materia','')} | ASSUNTO={question.get('assunto','')} | BANCA={question.get('banca','')}\n"
            f"ENUNCIADO={question.get('enunciado','')}\nGABARITO={question.get('gabarito','')}\n"
            f"DOMÍNIO_KT={learner.get('mastery')} | EVIDÊNCIA_KT={learner.get('evidence')} | RECUPERABILIDADE_FSRS={learner.get('retrievability')} | IRT={learner.get('item_difficulty')}\n"
            f"DIAGNÓSTICO={diagnosis.get('label')} | INTERVENÇÃO={diagnosis.get('intervention')}\nEVIDÊNCIAS:\n{evidence}"
        )

    @staticmethod
    def _offline_compose(packet: dict, provider_text: str = "") -> str:
        q = packet["question"]
        mode = packet["mode"]
        diagnosis = packet["diagnosis"]
        sources = packet["sources"]
        official = str(q.get("gabarito") or "").strip().upper()
        base = str(provider_text or "").strip() or next((str(src.get("content") or "").strip() for src in sources if str(src.get("content") or "").strip()), "")
        if not base:
            base = "As evidências locais ainda são insuficientes para explicar o conteúdo com segurança."
        topic = str(q.get("assunto") or q.get("materia") or "este conteúdo")
        user = str(packet.get("user_prompt") or "").strip()
        if mode == "socratico":
            concepts = [str(item.get("label") or "") for item in packet.get("learner", {}).get("concepts", []) if str(item.get("label") or "")][:3]
            concept_hint = ", ".join(concepts) or topic
            return (
                f"**Modo socrático — {topic}**\n\n"
                f"Antes de revelar o gabarito, responda mentalmente: (1) qual regra central se aplica a {concept_hint}? "
                "(2) o comando pede regra, exceção, item correto ou incorreto? (3) qual alternativa você consegue eliminar citando uma evidência?\n\n"
                f"Seu diagnóstico atual sugere **{diagnosis.get('label','indeterminado')}**. {diagnosis.get('intervention','')}\n\n"
                f"Pista fundamentada: {base[:1100]}\n\n"
                "Quando você formular sua hipótese, use o campo de pergunta para pedir a próxima pista."
            )
        if mode == "rapido":
            return (
                f"**Resposta rápida — {topic}**\n\nGabarito: {official or 'não informado'}.\n\n"
                f"Ponto-chave: {base[:700]}\n\nPor que revisar: {diagnosis.get('label','indeterminado')}. "
                f"Próximo passo: {diagnosis.get('intervention','')}"
            )
        if mode == "banca":
            banca = str(q.get("banca") or "banca não informada")
            trap = "Leia o comando literalmente e confira negações/exceções antes de comparar alternativas."
            return (
                f"**Modo banca — {banca}**\n\nGabarito: {official or 'não informado'}.\n\n"
                f"Fundamentação disponível: {base[:1000]}\n\n**Como atacar este item:** {trap}\n\n"
                f"**Seu ponto de risco:** {diagnosis.get('label','indeterminado')}. {diagnosis.get('intervention','')}"
                + (f"\n\nPergunta específica: {user}" if user else "")
            )
        return (
            f"**Modo professor — {topic}**\n\nGabarito: {official or 'não informado'}.\n\n"
            f"**Fundamentação:** {base[:1500]}\n\n"
            f"**Diagnóstico do seu erro:** {diagnosis.get('label','indeterminado')} "
            f"(confiança {float(diagnosis.get('confidence',0))*100:.0f}%). {diagnosis.get('explanation','')}\n\n"
            f"**Intervenção recomendada:** {diagnosis.get('intervention','')}"
            + (f"\n\n**Sua pergunta:** {user}" if user else "")
        )

    def editorial_commentary_brief(self, uid: str) -> dict:
        from core.bank_intelligence import build_ai_commentary_brief

        question = self.editorial.question(uid)
        brief = build_ai_commentary_brief(question)
        try:
            brief["hybrid_retrieval"] = self.knowledge.retrieve(uid, "", limit=6)
        except Exception as error:
            brief["hybrid_retrieval"] = {"items": [], "error": str(error)}
        return brief

    def generate_editorial_commentary(self, uid: str, *, online: bool = True) -> dict:
        """Gera rascunho editorial sob a mesma política de governança do Tutor.

        Esta função absorve a assistência legada da Curadoria para que toda
        geração de IA passe pelo AI Engine e pelo avaliador independente.
        """
        import copy
        from core.enrichment import apply_safe_suggestions, enrich_question

        question = self.editorial.question(uid)
        brief = self.editorial_commentary_brief(uid)
        local_retrieval = brief.get("hybrid_retrieval", {}) if isinstance(brief, dict) else {}
        enrichment: dict = {"results": [], "errors": [], "confidence": 0.0, "verified_match": False, "structured_question": {}}
        provider = "QuestFlow Grounded Composer"
        model = "qf-editorial-grounded-1"
        warnings: list[str] = []
        if online:
            try:
                from core.ai_safety import filtered_question_for_external, privacy_settings
                privacy = privacy_settings(dict(getattr(self.api, "config", {}) or {}) if hasattr(self, "api") else {})
                external_question = filtered_question_for_external(question, dict(getattr(self.api, "config", {}) or {}) if hasattr(self, "api") else {})
                if privacy.get("mode") == "private" or not external_question:
                    warnings.append("Centro de Privacidade em modo privado: curadoria online não recebeu dados; usado contexto local.")
                else:
                    enrichment = enrich_question(external_question, max_results=10)
                    provider = "Google Modo IA + QuestFlow RAG"
                    model = "modelo_nao_divulgado_pelo_provedor"
            except Exception as error:
                warnings.append(f"IA online indisponível: {error}")

        proposed = apply_safe_suggestions(copy.deepcopy(question), enrichment) if enrichment else copy.deepcopy(question)
        structured = enrichment.get("structured_question", {}) if isinstance(enrichment, dict) else {}
        explanation = str(proposed.get("explicacao", "") or "").strip() or str(structured.get("explicacao", "") or "").strip()
        if not explanation:
            explanation = next((str(item.get("content") or "").strip() for item in local_retrieval.get("items", []) if isinstance(item, dict) and str(item.get("content") or "").strip()), "")

        sources: list[dict] = []
        for item in local_retrieval.get("items", []) if isinstance(local_retrieval, dict) else []:
            if not isinstance(item, dict):
                continue
            sources.append({
                "title": str(item.get("title") or "Contexto local"),
                "url": "",
                "provider": "Knowledge Engine / RAG híbrido",
                "score": float((item.get("scores") or {}).get("score", 0) or 0),
                "content": str(item.get("content") or "")[:1200],
            })
        for item in enrichment.get("results", []) if isinstance(enrichment, dict) else []:
            if isinstance(item, dict):
                sources.append({
                    "title": str(item.get("title") or "Resultado web"),
                    "url": str(item.get("url") or ""),
                    "provider": str(item.get("provider") or "Google"),
                    "content": str(item.get("snippet") or ""),
                })
        warnings.extend(str(x) for x in (enrichment.get("errors", []) if isinstance(enrichment, dict) else []) if str(x))
        prompt = (
            "Assistência editorial QuestFlow. Produza somente um rascunho fundamentado para revisão humana. "
            "Não altere silenciosamente o gabarito e não invente referências.\n"
            f"QUESTÃO={question.get('enunciado','')}\nGABARITO={question.get('gabarito','')}\n"
            f"MATÉRIA={question.get('materia','')} | ASSUNTO={question.get('assunto','')}"
        )
        diagnosis = {
            "version": "qf-editorial-assist-1",
            "error_type": "nao_aplicavel",
            "label": "Curadoria editorial",
            "confidence": 1.0,
            "signals": [],
            "intervention": "Conferir evidências, gabarito e redação antes de aprovar.",
            "explanation": "Saída de curadoria; não é diagnóstico do aluno.",
        }
        interaction_id = self.governance.record_interaction(
            question_uid=uid, interaction_type="editorial_commentary", mode="curadoria",
            provider=provider, model=model, prompt_text=prompt, response_text=explanation,
            learner_context={}, sources=sources[:14], diagnosis=diagnosis,
        )
        evaluation = self.governance.evaluate(
            interaction_id, response_text=explanation, mode="curadoria", official_answer=str(question.get("gabarito") or ""),
            source_texts=[str(src.get("content") or "") for src in sources], diagnosis=diagnosis, sources=sources,
            question_context={"reference_date": str((question.get("contexto_temporal") or {}).get("data_prova") or "") if isinstance(question.get("contexto_temporal"), dict) else ""},
        )
        return {
            "provider": provider, "model": model, "interaction_id": interaction_id, "brief": brief,
            "explanation": explanation, "suggested_answer": str(structured.get("gabarito", "") or ""),
            "confidence": float(enrichment.get("confidence", 0) or 0) if isinstance(enrichment, dict) else 0.0,
            "verified_match": bool(enrichment.get("verified_match")) if isinstance(enrichment, dict) else False,
            "sources": sources[:14], "warnings": warnings, "evaluation": evaluation,
            "publication_policy": "rascunho_requer_aprovacao_humana",
        }

    def research_google_commentary(
        self,
        uid: str,
        question_override: dict | None = None,
        progress_callback=None,
    ) -> dict:
        """Pesquisa a questão no Google Modo IA e produz um comentário editorial rastreável.

        Diferentemente da assistência genérica, esta operação é explicitamente Google-first:
        se o Centro de Privacidade impedir envio externo, ou se o Google não devolver uma
        explicação utilizável, a função falha em vez de substituir silenciosamente por outro
        provedor. O gabarito encontrado é apenas um sinal de conferência e nunca altera o
        gabarito persistido da questão.
        """
        from core.ai_safety import filtered_question_for_external, privacy_settings
        from core.enrichment import enrich_question, _clean_commentary_fragment, _commentary_is_substantive

        question = self.editorial.question(uid)
        if isinstance(question_override, dict) and question_override:
            # A pesquisa pode usar o que está atualmente no editor sem obrigar o usuário
            # a salvar antes. Somente campos editoriais da própria questão são aceitos.
            allowed = {
                "codigo_origem", "materia", "aula_planilha", "assunto", "assuntos", "banca",
                "ano", "orgao", "prova", "cargo", "tipo", "gabarito", "enunciado", "alternativas",
            }
            question = dict(question)
            for key in allowed:
                if key in question_override:
                    question[key] = question_override.get(key)
        config = dict(getattr(self.api, "config", {}) or {}) if hasattr(self, "api") else {}
        privacy = privacy_settings(config)
        if privacy.get("mode") == "private":
            raise ValueError(
                "O Centro de Privacidade está no modo Privado. Para pesquisar esta questão no Google, "
                "altere temporariamente o modo de privacidade ou use a assistência local/RAG."
            )
        external_question = filtered_question_for_external(question, config)
        # O código público da questão é o sinal mais preciso para a pesquisa no Google.
        # Ele acompanha a taxonomia somente quando esse grupo está autorizado pela política.
        if privacy.get("share_taxonomy") and str(question.get("codigo_origem") or "").strip():
            external_question["codigo_origem"] = str(question.get("codigo_origem") or "").strip()
            external_question["id"] = external_question["codigo_origem"]
        if not external_question:
            raise ValueError("A política de privacidade atual não permite enviar os dados mínimos desta questão ao Google.")

        if progress_callback is None:
            # Compatibilidade com adaptadores/test doubles 6.7.x que expõem a
            # assinatura antiga de enrich_question(question, max_results=...).
            enrichment = enrich_question(external_question, max_results=10)
        else:
            enrichment = enrich_question(
                external_question,
                max_results=10,
                progress_callback=progress_callback,
            )
        structured = enrichment.get("structured_question", {}) if isinstance(enrichment, dict) else {}
        best = enrichment.get("best_candidate", {}) if isinstance(enrichment, dict) else {}
        explanation = str(structured.get("explicacao") or best.get("justificativa") or "").strip()
        # Limpeza final defensiva: a pesquisa pode ter encontrado a resposta correta
        # mesmo quando o layout do Google mistura rótulos e elementos de interface.
        # Removemos o ruído, mas não descartamos uma justificativa substantiva só
        # porque ela foi redigida de forma diferente do heurístico esperado.
        explanation, final_noise_removed = _clean_commentary_fragment(explanation)
        explanation_confidence = float(enrichment.get("explanation_confidence", best.get("explanation_confidence", 0)) or 0)
        if explanation and bool(enrichment.get("verified_match")) and explanation_confidence <= 0:
            # Compatibilidade com adaptadores/test doubles 6.7.x que já entregavam
            # um campo estruturado de explicação, mas ainda não informavam a confiança de extração.
            explanation_confidence = max(0.72, min(0.92, float(enrichment.get("confidence", best.get("score", 0.72)) or 0.72)))
        explanation_method = str(enrichment.get("explanation_method") or best.get("explanation_method") or "none")
        # Hotfix 3: confiança é um indicador para o revisor, não uma condição para
        # apagar a resposta. A recusa só ocorre quando não há texto substantivo ou
        # quando a consulta não pôde ser vinculada à questão pesquisada.
        if not _commentary_is_substantive(explanation) or not bool(enrichment.get("verified_match")):
            details = "; ".join(str(x) for x in (enrichment.get("errors") or []) if str(x).strip())
            suffix = f" Detalhes: {details}" if details else ""
            raise ValueError(
                "O Google não retornou uma explicação verificável e utilizável para esta questão; "
                "o QuestFlow recusou preencher o campo com metadados ou texto de navegação." + suffix
            )

        low_confidence_warning = ""
        if explanation_confidence < 0.62:
            low_confidence_warning = (
                f"A justificativa foi encontrada e limpa, mas a confiança automática ficou em "
                f"{round(explanation_confidence * 100)}%. O texto foi preenchido para revisão humana em vez de ser descartado."
            )

        official_answer = str(question.get("gabarito") or "").strip().upper()
        google_answer = str(structured.get("gabarito") or "").strip().upper()
        search_mode = str(enrichment.get("search_mode") or "google_modo_ia_pagina_renderizada")
        research_provider = (
            "Google + fonte pública verificada"
            if search_mode == "google_web_fonte_publica_verificada"
            else "Google Modo IA"
        )
        warnings = [str(x) for x in (enrichment.get("errors") or []) if str(x).strip()]
        if low_confidence_warning:
            warnings.append(low_confidence_warning)
        if official_answer and google_answer and official_answer != google_answer:
            warnings.append(
                f"O Google sugeriu gabarito {google_answer}, diferente do gabarito {official_answer} registrado no QuestFlow. "
                "O gabarito local não foi alterado; confira manualmente antes de concluir a revisão."
            )

        # A explicação recebe o gabarito já registrado no banco apenas como contexto pedagógico;
        # uma divergência detectada no Google permanece como alerta e nunca sobrescreve o banco.
        rendered = explanation
        if official_answer and not rendered.casefold().lstrip().startswith("gabarito"):
            rendered = f"Gabarito: {official_answer}.\n\n{rendered}"

        sources: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for item in enrichment.get("results", []) if isinstance(enrichment, dict) else []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "Resposta exibida no Google").strip()
            key = (url, title)
            if key in seen:
                continue
            seen.add(key)
            sources.append({
                "title": title,
                "url": url,
                "provider": str(item.get("provider") or research_provider),
                "score": float(item.get("score", 0) or 0),
                "content": str(item.get("snippet") or "")[:1600],
            })
        source_url = str(enrichment.get("justification_source_url") or enrichment.get("answer_source_url") or enrichment.get("verified_source_url") or "").strip()
        if source_url and not any(str(item.get("url") or "") == source_url for item in sources):
            sources.insert(0, {
                "title": "Fonte verificada da pesquisa",
                "url": source_url,
                "provider": research_provider,
                "content": str(best.get("justificativa") or best.get("google_overview_text") or "")[:1600],
            })

        prompt = (
            "Pesquisa editorial QuestFlow no Google Modo IA. Localize a questão e produza uma explicação fundamentada "
            "para revisão humana. Não altere o gabarito local automaticamente e não invente referências.\n"
            f"CÓDIGO={question.get('codigo_origem','')}\nQUESTÃO={question.get('enunciado','')}\n"
            f"GABARITO_LOCAL={official_answer}\nMATÉRIA={question.get('materia','')} | ASSUNTO={question.get('assunto','')}"
        )
        diagnosis = {
            "version": "qf-google-commentary-1",
            "error_type": "nao_aplicavel",
            "label": "Pesquisa editorial no Google",
            "confidence": float(enrichment.get("confidence", 0) or 0),
            "signals": [
                f"correspondencia_verificada={bool(enrichment.get('verified_match'))}",
                f"gabarito_google={google_answer or 'nao_identificado'}",
                f"extracao_resposta={explanation_method}",
                f"confianca_extracao={explanation_confidence:.3f}",
            ],
            "intervention": "Conferir o texto, o gabarito local e as fontes antes de salvar/concluir a revisão.",
            "explanation": "Saída de pesquisa editorial; requer revisão humana antes da publicação.",
        }
        interaction_id = self.governance.record_interaction(
            question_uid=uid, interaction_type="google_commentary_research", mode="curadoria",
            provider=research_provider, model="modelo_nao_divulgado_pelo_provedor",
            prompt_text=prompt, response_text=rendered, learner_context={}, sources=sources[:14], diagnosis=diagnosis,
        )
        evaluation = self.governance.evaluate(
            interaction_id, response_text=rendered, mode="curadoria", official_answer=official_answer,
            source_texts=[str(src.get("content") or "") for src in sources], diagnosis=diagnosis, sources=sources,
            question_context={
                "reference_date": str((question.get("contexto_temporal") or {}).get("data_prova") or "")
                if isinstance(question.get("contexto_temporal"), dict) else ""
            },
        )
        return {
            "ok": True,
            "provider": research_provider,
            "model": "modelo_nao_divulgado_pelo_provedor",
            "interaction_id": interaction_id,
            "explanation": rendered,
            "suggested_answer": google_answer,
            "official_answer": official_answer,
            "confidence": float(enrichment.get("confidence", 0) or 0),
            "verified_match": bool(enrichment.get("verified_match")),
            "explanation_confidence": explanation_confidence,
            "explanation_method": explanation_method,
            "noise_removed": int(enrichment.get("noise_removed", 0) or 0) + int(final_noise_removed or 0),
            "sources": sources[:14],
            "warnings": warnings,
            "evaluation": evaluation,
            "commentary_source": "ia_assistida",
            "publication_policy": "preenche_editor_requer_salvamento_e_revisao_humana",
            "search_mode": search_mode,
        }

    @staticmethod
    def _structured_tutor_text(data: dict) -> str:
        answer = str(data.get("answer") or "").strip()
        explanation = str(data.get("explanation") or "").strip()
        diagnosis = str(data.get("diagnosis_note") or "").strip()
        intervention = str(data.get("intervention") or "").strip()
        citations = [str(x).strip() for x in (data.get("citations") or []) if str(x).strip()]
        warnings = [str(x).strip() for x in (data.get("warnings") or []) if str(x).strip()]
        parts=[]
        if answer: parts.append(f"**Conclusão/Gabarito:** {answer}")
        if explanation: parts.append(f"**Fundamentação:** {explanation}")
        if diagnosis: parts.append(f"**Leitura pedagógica:** {diagnosis}")
        if intervention: parts.append(f"**Próxima ação:** {intervention}")
        if citations: parts.append("**Evidências citadas:** " + "; ".join(citations[:8]))
        if warnings: parts.append("**Limites/alertas:** " + "; ".join(warnings[:8]))
        return "\n\n".join(parts).strip()

    def privacy_preview(self, uid: str, *, mode: str = "professor", user_prompt: str = "") -> dict:
        from core.ai_safety import compose_tutor_prompt
        packet = self.tutor_packet(uid, mode=mode, user_prompt=user_prompt, persist_diagnosis=False)
        config = dict(getattr(self.api, "config", {}) or {}) if hasattr(self, "api") else {}
        _prompt, _sources, security, preview = compose_tutor_prompt(packet, config)
        return {"ok": True, "provider": str(config.get("ai_active_provider") or "local"), "preview": preview, "security": security}

    @staticmethod
    def _scaffold_representation(text: str, question: str, *, representation: str, level: int) -> str:
        rep = str(representation or "texto").casefold()
        clean = str(text or "").strip()
        prompt = str(question or "").strip()
        if rep == "flashcard":
            return f"**Flashcard de recuperação · nível {level}/5**\n\n**Frente:** {prompt or 'Qual regra resolve este item?'}\n\n**Pista:** {clean}"
        if rep == "passo_a_passo":
            return f"**Passo a passo · nível {level}/5**\n\n1. Leia o comando.\n2. Recupere a regra sem consultar o gabarito.\n3. Use esta pista: {clean}\n4. Formule sua resposta antes de pedir o próximo nível."
        if rep == "visual":
            return f"**Revisão visual · nível {level}/5**\n\nObserve a imagem/figura da questão quando disponível e relacione cada elemento visual ao conceito cobrado.\n\n**Pista:** {clean}\n\n**Pergunta-guia:** {prompt or 'Que elemento visual altera a aplicação da regra?'}"
        return clean

    @staticmethod
    def _scaffold_local_hint(packet: dict, *, level: int, representation: str) -> dict:
        q = packet.get("question") or {}
        diagnosis = packet.get("diagnosis") or {}
        topic = str(q.get("assunto") or q.get("materia") or "o tema")
        statement = str(q.get("enunciado") or "").strip()
        alternatives = [a for a in (q.get("alternativas") or []) if isinstance(a, dict)]
        sources = [str(src.get("content") or "").strip() for src in (packet.get("sources") or []) if str(src.get("content") or "").strip()]
        evidence = sources[0][:650] if sources else ""
        command = "Identifique exatamente o que o comando pede e formule uma hipótese antes de consultar qualquer pista de conteúdo."
        if level == 0:
            hint = command
            question = "Qual é sua resposta inicial e qual regra você acredita que controla o item?"
        elif level == 1:
            neg = " Há termo de negação/exceção no comando; marque-o antes de comparar as opções." if re.search(r"\b(exceto|incorreta|não|nao|salvo|errada)\b", statement.casefold()) else ""
            hint = f"Separe o comando do conteúdo: o item cobra **{topic}**.{neg}"
            question = "O que a questão pede: regra geral, exceção, definição, consequência ou alternativa incorreta?"
        elif level == 2:
            hint = f"Recupere a regra central de **{topic}** em uma frase. Diagnóstico atual: {diagnosis.get('label','indeterminado')}."
            question = "Quais são os requisitos/elementos indispensáveis dessa regra?"
        elif level == 3:
            if evidence:
                hint = f"Compare as alternativas com esta evidência, sem procurar a letra do gabarito: {evidence}"
            else:
                hint = "Compare cada alternativa com os requisitos da regra e elimine primeiro as que usam termos absolutos ou trocam regra por exceção."
            question = "Qual alternativa você consegue eliminar com maior segurança e por quê?"
        elif level == 4:
            keys = ", ".join(str(a.get("chave") or "?") for a in alternatives[:6])
            hint = f"Aplique a regra de **{topic}** uma alternativa por vez ({keys or 'opções'}). Procure a opção cuja consequência e requisitos coincidam integralmente com a regra, sem revelar a letra ainda."
            question = "Depois dessa comparação, qual opção resta e qual requisito foi decisivo?"
        else:
            hint = "A explicação completa será exibida com o gabarito e a fundamentação auditada."
            question = "Compare sua hipótese anterior com a solução e identifique o ponto em que seu raciocínio mudou."
        return {
            "hint": AIEngine._scaffold_representation(hint, question, representation=representation, level=level),
            "question_to_student": question,
            "strategy": SCAFFOLD_LEVELS[level][0],
            "confidence": 0.82 if sources or level <= 2 else 0.62,
            "citations": [],
            "warnings": [] if sources or level <= 2 else ["Evidências locais limitadas; pista mantida em nível metacognitivo."],
        }

    def _scaffold_hint(self, packet: dict, *, level: int, representation: str, online: bool) -> dict:
        from core.ai_safety import compose_tutor_prompt, scaffold_schema
        level = max(0, min(4, int(level)))
        local = self._scaffold_local_hint(packet, level=level, representation=representation)
        config = dict(getattr(self.api, "config", {}) or {}) if hasattr(self, "api") else {}
        selected_provider = str(config.get("ai_active_provider") or "local")
        provider = "QuestFlow Scaffolding local"
        model = SCAFFOLD_VERSION
        structured = dict(local)
        warnings = list(local.get("warnings") or [])
        provider_metric = None
        # Para níveis de pista, nunca compartilha o gabarito nem o comentário editorial completo.
        safe_packet = dict(packet)
        safe_question = dict(packet.get("question") or {})
        safe_question["gabarito"] = ""
        safe_packet["question"] = safe_question
        safe_packet["sources"] = [src for src in (packet.get("sources") or []) if str(src.get("provider") or "") != "Banco Editorial"]
        external_prompt, sanitized_sources, security, privacy_preview = compose_tutor_prompt(safe_packet, config)
        external_prompt += (
            f"\n[SCAFFOLDING]\nNIVEL={level}/5\nREPRESENTACAO={representation}\n"
            "Gere SOMENTE uma pista gradual. Não revele a letra, o texto integral da alternativa correta nem o gabarito. "
            "Faça uma pergunta de recuperação ativa. Quanto menor o nível, menor a quantidade de conteúdo entregue."
        )
        if bool(online) and selected_provider in {"openai", "gemini", "anthropic"} and int((privacy_preview or {}).get("shared_count") or 0) > 0:
            try:
                from core.ai_providers import generate as provider_generate
                direct = provider_generate(
                    selected_provider, external_prompt, config=config, config_path=self.api.config_path,
                    schema=scaffold_schema(), schema_name="questflow_scaffold_v1",
                )
                candidate = dict(direct.get("structured") or {})
                if candidate.get("hint"):
                    candidate["hint"] = self._scaffold_representation(str(candidate.get("hint") or ""), str(candidate.get("question_to_student") or ""), representation=representation, level=level)
                    structured = candidate
                provider = str(direct.get("provider") or selected_provider) + " + QuestFlow Scaffold"
                model = str(direct.get("model") or "modelo_nao_informado")
                provider_metric = direct
            except Exception as error:
                warnings.append(f"IA externa indisponível para a pista; mantido scaffolding local: {error}")
        structured["warnings"] = [*list(structured.get("warnings") or []), *warnings]
        return {
            "level": level, "level_label": SCAFFOLD_LEVELS[level][0], "level_description": SCAFFOLD_LEVELS[level][1],
            "representation": representation, "content": structured, "provider": provider, "model": model,
            "sources": sanitized_sources, "security": security, "privacy_preview": privacy_preview,
            "provider_metric": provider_metric,
        }

    def _audit_scaffold_hint(self, uid: str, packet: dict, step: dict) -> dict:
        content = step.get("content") if isinstance(step.get("content"), dict) else {}
        response_text = (str(content.get("hint") or "") + "\n\n" + str(content.get("question_to_student") or "")).strip()
        interaction_id = self.governance.record_interaction(
            question_uid=uid, interaction_type="tutor_scaffold_hint", mode=f"scaffold_{int(step.get('level') or 0)}",
            provider=str(step.get("provider") or "QuestFlow Scaffolding local"), model=str(step.get("model") or SCAFFOLD_VERSION),
            prompt_text=f"Scaffolding nível {int(step.get('level') or 0)}/5; representação={step.get('representation')}",
            response_text=response_text, learner_context=packet.get("learner") or {},
            sources=step.get("sources") or packet.get("sources") or [], diagnosis=packet.get("diagnosis") or {},
        )
        evaluation = self.governance.evaluate(
            interaction_id, response_text=response_text, mode="socratico", official_answer="",
            source_texts=[str(src.get("content") or "") for src in (step.get("sources") or packet.get("sources") or [])],
            diagnosis=packet.get("diagnosis") or {}, sources=step.get("sources") or packet.get("sources") or [],
            question_context={"reference_date": ""},
        )
        metric = step.get("provider_metric") if isinstance(step.get("provider_metric"), dict) else None
        if metric is not None:
            try:
                self.governance.record_provider_metric(
                    interaction_id=interaction_id, provider=str(metric.get("provider_id") or ""), model=str(step.get("model") or ""),
                    operation="tutor_scaffold", status="ok", latency_ms=float(metric.get("latency_ms") or 0),
                    usage=metric.get("usage") or {}, estimated_cost_usd=metric.get("estimated_cost_usd"), structured_output=bool(metric.get("structured_output")),
                    prompt_injection_flags=int((step.get("security") or {}).get("sources_with_signals") or 0),
                )
            except Exception:
                pass
        step["interaction_id"] = interaction_id
        step["evaluation"] = evaluation
        step.pop("provider_metric", None)
        return step

    def start_scaffolding(self, uid: str, *, user_prompt: str = "", representation: str = "texto", media_notes: str = "", online: bool = False) -> dict:
        rep = str(representation or "texto").casefold()
        if rep not in SCAFFOLD_REPRESENTATIONS:
            rep = "texto"
        combined_prompt = str(user_prompt or "").strip()
        if str(media_notes or "").strip():
            combined_prompt = (combined_prompt + "\n\n[TRANSCRIÇÃO/DESCRIÇÃO VISUAL DO ALUNO]\n" + str(media_notes or "").strip()).strip()
        packet = self.tutor_packet(uid, mode="socratico", user_prompt=combined_prompt)
        packet["media_notes"] = str(media_notes or "").strip()
        session = self.learning.start_scaffold_session(
            uid, representation=rep, user_prompt=user_prompt, media_notes=media_notes, online=online, learner_snapshot=packet.get("learner") or {},
        )
        step = self._audit_scaffold_hint(uid, packet, self._scaffold_hint(packet, level=0, representation=rep, online=online))
        session = self.learning.record_scaffold_event(
            session["id"], level=0, event_type="hint_shown", content_preview=str((step.get("content") or {}).get("hint") or ""),
            metadata={"provider": step.get("provider"), "model": step.get("model"), "version": SCAFFOLD_VERSION},
        )
        return {"ok": True, "session": session, "step": step, "learner": self.learner.question_state(uid), "levels": SCAFFOLD_LEVELS}

    def advance_scaffolding(self, session_id: str, *, action: str = "next", online: bool | None = None) -> dict:
        session = self.learning.scaffold_session(str(session_id))
        uid = str(session.get("question_uid") or "")
        action_key = str(action or "next").casefold()
        use_online = bool(session.get("online")) if online is None else bool(online)
        if action_key in {"solved", "consegui", "resolved"}:
            level = int(session.get("current_level") or 0)
            session = self.learning.record_scaffold_event(
                session["id"], level=level, event_type="solved", content_preview="Aluno informou que conseguiu resolver neste nível.",
                metadata={"version": SCAFFOLD_VERSION},
            )
            return {"ok": True, "session": session, "completed": True, "learner": self.learner.question_state(uid), "signal": self.learning.scaffolding_signal(uid)}
        if action_key in {"reveal", "full", "explicacao"}:
            level = 5
        else:
            level = min(5, int(session.get("current_level") or 0) + 1)
        if level >= 5:
            final_prompt = str(session.get("user_prompt") or "").strip()
            if str(session.get("media_notes") or "").strip():
                final_prompt = (final_prompt + "\n\n[TRANSCRIÇÃO/DESCRIÇÃO VISUAL DO ALUNO]\n" + str(session.get("media_notes") or "").strip()).strip()
            final = self.generate_tutor(uid, mode="professor", user_prompt=final_prompt, online=use_online)
            session = self.learning.record_scaffold_event(
                session["id"], level=5, event_type="full_explanation", content_preview=str(final.get("response") or "")[:1200],
                metadata={"interaction_id": final.get("interaction_id"), "provider": final.get("provider"), "model": final.get("model"), "version": SCAFFOLD_VERSION},
            )
            return {"ok": True, "session": session, "step": {"level": 5, "level_label": SCAFFOLD_LEVELS[5][0], "level_description": SCAFFOLD_LEVELS[5][1], "representation": session.get("representation"), "final_tutor": final}, "completed": True, "learner": self.learner.question_state(uid)}
        combined_prompt = str(session.get("user_prompt") or "").strip()
        if str(session.get("media_notes") or "").strip():
            combined_prompt = (combined_prompt + "\n\n[TRANSCRIÇÃO/DESCRIÇÃO VISUAL DO ALUNO]\n" + str(session.get("media_notes") or "").strip()).strip()
        packet = self.tutor_packet(uid, mode="socratico", user_prompt=combined_prompt)
        packet["media_notes"] = str(session.get("media_notes") or "")
        step = self._audit_scaffold_hint(uid, packet, self._scaffold_hint(packet, level=level, representation=str(session.get("representation") or "texto"), online=use_online))
        session = self.learning.record_scaffold_event(
            session["id"], level=level, event_type="hint_shown", content_preview=str((step.get("content") or {}).get("hint") or ""),
            metadata={"provider": step.get("provider"), "model": step.get("model"), "version": SCAFFOLD_VERSION},
        )
        return {"ok": True, "session": session, "step": step, "completed": False, "learner": self.learner.question_state(uid)}

    def scaffolding_state(self, session_id: str) -> dict:
        session = self.learning.scaffold_session(str(session_id))
        return {"ok": True, "session": session, "learner": self.learner.question_state(str(session.get("question_uid") or "")), "levels": SCAFFOLD_LEVELS}

    def generate_tutor(self, uid: str, *, mode: str = "professor", user_prompt: str = "", online: bool = False) -> dict:
        from core.ai_safety import compose_tutor_prompt, privacy_settings, tutor_schema

        packet = self.tutor_packet(uid, mode=mode, user_prompt=user_prompt)
        question = packet["question"]
        config = dict(getattr(self.api, "config", {}) or {}) if hasattr(self, "api") else {}
        external_prompt, sanitized_sources, security, privacy_preview = compose_tutor_prompt(packet, config)
        packet["sources"] = sanitized_sources
        prompt = external_prompt if online else self._prompt(packet)
        provider = "QuestFlow Grounded Composer"
        model = "qf-tutor-grounded-2"
        provider_text = ""
        structured_response: dict = {}
        warnings: list[str] = []
        online_sources: list[dict] = []
        provider_metric: dict | None = None
        selected_provider = str(config.get("ai_active_provider") or "local")
        shared_count = int((privacy_preview or {}).get("shared_count") or 0)
        privacy = privacy_settings(config)
        media_attachments: list[dict] = []
        available_media = list((packet.get("multimodal") or {}).get("media") or [])
        if available_media and bool(privacy.get("share_binary_media")):
            try:
                from core.multimodal_rag import media_paths_for_question
                media_attachments = media_paths_for_question(question)
            except Exception as error:
                warnings.append(f"Não foi possível preparar a mídia local para envio multimodal: {error}")
        elif available_media:
            warnings.append("Há imagem/PDF associado, mas o binário permaneceu local porque o opt-in multimodal está desativado.")
        packet["multimodal"]["external_image_upload"] = bool(media_attachments)

        if bool(online) and selected_provider in {"openai", "gemini", "anthropic"}:
            if shared_count <= 0:
                warnings.append("Centro de Privacidade está em modo privado; nenhuma informação foi enviada ao provedor externo.")
            else:
                try:
                    from core.ai_providers import generate as provider_generate
                    direct = provider_generate(
                        selected_provider, external_prompt, config=config, config_path=self.api.config_path,
                        schema=tutor_schema(), schema_name="questflow_tutor_v1",
                        attachments=media_attachments if bool(privacy.get("share_binary_media")) else None,
                    )
                    structured_response = dict(direct.get("structured") or {})
                    provider_text = self._structured_tutor_text(structured_response) or str(direct.get("text") or "").strip()
                    provider = str(direct.get("provider") or selected_provider) + " + QuestFlow RAG"
                    model = str(direct.get("model") or "modelo_nao_informado")
                    provider_metric = direct
                except Exception as error:
                    warnings.append(f"Provedor configurado indisponível ou Structured Output incompatível; usado modo local fundamentado: {error}")
                    self.governance.record_provider_metric(
                        provider=selected_provider, model=str(config.get(f"ai_{selected_provider}_model") or ""),
                        operation="tutor", status="error", structured_output=True,
                        prompt_injection_flags=int(security.get("sources_with_signals") or 0), error_code=type(error).__name__,
                    )
        elif bool(online) and selected_provider == "google_ai_mode":
            if shared_count <= 0:
                warnings.append("Centro de Privacidade está em modo privado; nenhuma informação foi enviada ao Google Modo IA.")
            else:
                try:
                    from core.enrichment import enrich_question
                    from core.ai_safety import filtered_question_for_external
                    enrichment = enrich_question(filtered_question_for_external(question, config), max_results=8)
                    structured = enrichment.get("structured_question", {}) if isinstance(enrichment, dict) else {}
                    provider_text = str(structured.get("justificativa") or "").strip()
                    provider = "Google Modo IA + QuestFlow RAG"
                    model = "modelo_nao_divulgado_pelo_provedor"
                    warnings.extend(str(x) for x in (enrichment.get("errors", []) if isinstance(enrichment, dict) else []) if str(x))
                    for item in enrichment.get("results", []) if isinstance(enrichment, dict) else []:
                        if isinstance(item, dict):
                            online_sources.append({"title": str(item.get("title") or "Resultado web"), "provider": str(item.get("provider") or "Google"), "url": str(item.get("url") or ""), "content": str(item.get("snippet") or ""), "security": {"trust":"untrusted_data"}})
                except Exception as error:
                    warnings.append(f"Google Modo IA indisponível; usado modo local fundamentado: {error}")

        sources = [*packet["sources"], *online_sources][:14]
        packet["sources"] = sources
        response = provider_text if provider_text else self._offline_compose(packet, provider_text="")
        if security.get("sources_with_signals"):
            warnings.append(f"Defesa contra prompt injection sinalizou {security.get('sources_with_signals')} fonte(s); trechos suspeitos foram tratados como dados não confiáveis.")
        interaction_id = self.governance.record_interaction(
            question_uid=uid, interaction_type="tutor", mode=packet["mode"], provider=provider, model=model,
            prompt_text=prompt, response_text=response, learner_context=packet["learner"], sources=sources, diagnosis=packet["diagnosis"],
        )
        if provider_metric is not None:
            self.governance.record_provider_metric(
                interaction_id=interaction_id, provider=str(provider_metric.get("provider_id") or selected_provider), model=model,
                operation="tutor", status="ok", latency_ms=float(provider_metric.get("latency_ms") or 0),
                usage=provider_metric.get("usage") or {}, estimated_cost_usd=provider_metric.get("estimated_cost_usd"),
                structured_output=bool(provider_metric.get("structured_output")),
                prompt_injection_flags=int(security.get("sources_with_signals") or 0),
            )
        evaluation = self.governance.evaluate(
            interaction_id, response_text=response, mode=packet["mode"], official_answer=str(question.get("gabarito") or ""),
            source_texts=[str(src.get("content") or "") for src in sources], diagnosis=packet["diagnosis"], sources=sources,
            question_context={"reference_date": str((question.get("contexto_temporal") or {}).get("data_prova") or "") if isinstance(question.get("contexto_temporal"), dict) else ""},
        )
        return {
            "ok": True, "interaction_id": interaction_id, "mode": packet["mode"], "provider": provider, "model": model,
            "response": response, "structured_response": structured_response,
            "diagnosis": packet["diagnosis"], "learner": packet["learner"], "sources": sources,
            "evaluation": evaluation, "warnings": warnings, "privacy_preview": privacy_preview, "security": security,
            "usage": (provider_metric or {}).get("usage") or {}, "estimated_cost_usd": (provider_metric or {}).get("estimated_cost_usd"),
            "multimodal": packet.get("multimodal") or {},
            "media_sent_count": int((provider_metric or {}).get("media_sent_count") or 0),
            "publication_policy": "rascunho_requer_aprovacao_humana",
        }

    @staticmethod
    def _source_sentences(sources: list[dict]) -> list[str]:
        sentences: list[str] = []
        for src in sources:
            text = re.sub(r"\s+", " ", str(src.get("content") or "")).strip()
            for part in re.split(r"(?<=[.!?;])\s+", text):
                clean = part.strip(" -•\t\n")
                if 55 <= len(clean) <= 420 and len(re.findall(r"\w+", clean)) >= 9:
                    sentences.append(clean)
        # Prefer sentences with normative/definitional markers because they are
        # more suitable as a verifiable correct alternative.
        sentences.sort(key=lambda x: (0 if any(k in x.casefold() for k in ("deve", "pode", "é ", "são ", "considera", "compete", "art.")) else 1, len(x)))
        return sentences

    @staticmethod
    def _distractors(correct: str, error_profile: dict, topic: str) -> list[dict]:
        ranked = [str(item.get("error_type") or "") for item in (error_profile.get("items") or [])]
        patterns = ranked + ["excecao_regra", "confusao_conceitual", "interpretacao", "memoria_esquecimento", "desatencao"]
        seen = set()
        choices = []
        templates = {
            "excecao_regra": f"A regra sobre {topic or 'o tema'} é absoluta e se aplica sem qualquer condição, ressalva ou exceção prevista na fonte.",
            "confusao_conceitual": f"O efeito jurídico descrito para {topic or 'o tema'} pertence necessariamente a instituto diverso, ainda que os requisitos da fonte estejam presentes.",
            "interpretacao": "A conclusão depende apenas de uma palavra isolada do enunciado, sendo dispensável verificar as condições e o contexto descritos na fonte.",
            "memoria_esquecimento": f"A disciplina de {topic or 'o tema'} produz o resultado oposto ao indicado pela fonte selecionada.",
            "desatencao": "Todos os requisitos mencionados na fonte podem ser ignorados quando a alternativa reproduz a terminologia principal do assunto.",
            "leitura_incompleta": "A primeira oração da regra é suficiente para definir a resposta, mesmo quando o restante do dispositivo estabelece restrições relevantes.",
            "chute": "Na ausência de certeza, a alternativa mais abrangente deve ser considerada correta independentemente da fundamentação selecionada.",
            "calculo": "O procedimento pode ser concluído sem observar a sequência ou os parâmetros definidos na fonte.",
        }
        for code in patterns:
            text = templates.get(code)
            if not text or text in seen or text.casefold() == str(correct).casefold():
                continue
            seen.add(text); choices.append({"text": text, "based_on_error": code})
            if len(choices) >= 4:
                break
        return choices

    def generation_workspace(self, uid: str = "") -> dict:
        candidates = self.editorial.question_candidates(limit=60)
        selected_uid = str(uid or "").strip()
        if not selected_uid and candidates:
            selected_uid = str(candidates[0].get("uid") or "")
        selected = None
        sources = []
        if selected_uid:
            try:
                question = self.editorial.question(selected_uid)
                retrieval = self.knowledge.retrieve(selected_uid, "", limit=12)
                sources = retrieval.get("items", []) if isinstance(retrieval, dict) else []
                selected = {
                    "uid": selected_uid, "code": str(question.get("codigo_origem") or ""),
                    "subject": str(question.get("materia") or ""), "topic": str(question.get("assunto") or ""),
                    "board": str(question.get("banca") or ""), "statement": str(question.get("enunciado") or "")[:800],
                }
            except Exception:
                selected = None
        return {
            "schema": "questflow.stage5.workspace.v1",
            "selected": selected,
            "candidates": candidates[:60],
            "source_pool": sources,
            "legislation": self.editorial.legislation_versions(limit=80),
            "legislation_summary": self.editorial.legislation_summary(),
            "drafts": self.governance.generation_drafts(limit=20),
            "gold": self.governance.gold_dashboard(),
            "policies": {
                "selected_sources_only": True, "second_model_validation": True,
                "human_approval_required": True, "generated_origin": "inedita_propria",
            },
        }

    def generate_controlled_question(self, *, seed_uid: str = "", source_chunk_ids: list[str] | None = None,
                                     question_type: str = "multipla_escolha", board_style: str = "",
                                     subject: str = "", topic: str = "", exam_date: str = "") -> dict:
        import hashlib, uuid
        selected_ids = [str(x).strip() for x in (source_chunk_ids or []) if str(x).strip()]
        if not selected_ids:
            raise ValueError("Selecione ao menos uma fonte do Knowledge Engine. A Etapa 5 não gera questão sem evidência escolhida.")
        sources = self.knowledge.selected_sources(selected_ids)
        if len(sources) != len(set(selected_ids)):
            found = {str(src.get("id")) for src in sources}
            missing = [item for item in selected_ids if item not in found]
            raise ValueError("Fonte selecionada não encontrada no índice: " + ", ".join(missing[:5]))
        seed = None
        if str(seed_uid or "").strip():
            seed = self.editorial.question(str(seed_uid))
        effective_subject = str(subject or (seed or {}).get("materia") or sources[0].get("subject") or "").strip()
        effective_topic = str(topic or (seed or {}).get("assunto") or sources[0].get("topic") or "").strip()
        error_profile = self.governance.error_profile(subject=effective_subject, topic=effective_topic)
        sentences = self._source_sentences(sources)
        if not sentences:
            raise ValueError("As fontes selecionadas não contêm trecho textual suficiente para uma geração fundamentada.")
        correct = sentences[0]
        qtype = str(question_type or "multipla_escolha").casefold()
        prompt = (
            "QuestFlow Etapa 5: gere UMA questão inédita usando EXCLUSIVAMENTE as fontes explicitamente selecionadas. "
            "Não acrescente jurisprudência, artigo, exceção ou fato ausente. Distratores devem ser falsos e inspirados somente em padrões de erro do aluno. "
            f"MATÉRIA={effective_subject}; ASSUNTO={effective_topic}; BANCA_ALVO={board_style}; DATA_PROVA={exam_date}; "
            f"FONTES_IDS={','.join(selected_ids)}\n" + "\n---\n".join(str(src.get("content") or "") for src in sources)
        )
        code = "QFLOW-IA-" + uuid.uuid4().hex[:10].upper()
        alternatives = []
        if "certo" in qtype or qtype in {"ce", "c_e", "certo_errado"}:
            statement = f"Julgue o item a seguir acerca de {effective_topic or effective_subject or 'tema indicado'}: {correct}"
            answer = "C"
            kind = "CERTO/ERRADO"
        else:
            statement = f"A respeito de {effective_topic or effective_subject or 'conteúdo da fonte selecionada'}, assinale a alternativa correta."
            distractors = self._distractors(correct, error_profile, effective_topic)
            raw = [{"texto": correct, "role": "correct", "based_on_error": "fonte_selecionada"}] + [
                {"texto": item["text"], "role": "distractor", "based_on_error": item["based_on_error"]} for item in distractors
            ]
            # Deterministic rotation avoids always placing the answer in A while
            # preserving reproducibility for audit.
            shift = int(hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:2], 16) % len(raw)
            raw = raw[shift:] + raw[:shift]
            for idx, item in enumerate(raw):
                key = chr(ord("A") + idx)
                alternatives.append({"chave": key, "texto": item["texto"], "geracao_meta": {"role": item["role"], "based_on_error": item["based_on_error"]}})
                if item["role"] == "correct":
                    answer = key
            kind = "Múltipla escolha"
        law_keys = []
        temporal_sources = []
        for src in sources:
            meta = src.get("metadata") if isinstance(src.get("metadata"), dict) else {}
            if str(src.get("source_kind")) == "legislation":
                if meta.get("canonical_key"): law_keys.append(str(meta.get("canonical_key")))
                temporal_sources.append({"id":src.get("id"),"canonical_key":meta.get("canonical_key"),"effective_from":meta.get("effective_from"),"effective_to":meta.get("effective_to")})
        source_titles = [str(src.get("title") or src.get("id") or "Fonte") for src in sources]
        explanation = "Questão inédita gerada como rascunho a partir das fontes selecionadas: " + "; ".join(source_titles[:6]) + ". A alternativa correta reproduz conteúdo suportado pelas evidências; os distratores usam padrões de erro do aluno e exigem validação independente + revisão humana."
        fingerprint_raw = statement + "|" + "|".join(str(a.get("texto") or "") for a in alternatives) + "|" + answer
        draft = {
            "id": code, "codigo_origem": code, "fingerprint": hashlib.sha256(fingerprint_raw.encode("utf-8")).hexdigest(),
            "materia": effective_subject, "assunto": effective_topic, "assuntos": [effective_topic] if effective_topic else [],
            "banca": str(board_style or "QuestFlow inédita"), "ano": None, "orgao": "", "prova": "QuestFlow · geração controlada",
            "tipo": kind, "enunciado": statement, "alternativas": alternatives, "gabarito": answer, "explicacao": explanation,
            "tipo_origem": "inedita_propria", "origem_questao": "inedita_propria",
            "proveniencia": {"tipo":"inedita_propria","fonte_primaria":" | ".join(source_titles),"verificada":False,"fontes_selecionadas":selected_ids},
            "fonte": {"arquivo":"QuestFlow Generator","metodo":"geracao_controlada_stage5","pagina_inicial":None},
            "direitos": {"status":"autoria_questflow_derivada_de_fontes_selecionadas_requer_revisao"},
            "referencias_legais": sorted(set(law_keys)),
            "geracao_ia": {"versao":GENERATOR_VERSION,"fontes_selecionadas":selected_ids,"modelo":GENERATOR_VERSION,"padroes_erro":error_profile,"politica":"selected_sources_only"},
            "contexto_temporal": {"data_prova":str(exam_date or ""),"fontes_legislativas":temporal_sources},
            "revisao": {"status":"pendente","confianca":0.0,"alertas":["Rascunho de IA: publicar somente após validação independente e aprovação humana."]},
            "comentario_meta": {"origem":"ia_assistida","metodo":"geracao_controlada_stage5"},
        }
        record = self.governance.create_generation_draft(
            seed_question_uid=str(seed_uid or "") or None, subject=effective_subject, topic=effective_topic,
            board_style=str(board_style or ""), question_type=kind, generator_model=GENERATOR_VERSION,
            prompt_text=prompt, sources=sources, error_profile=error_profile, draft=draft,
        )
        validation = self.governance.validate_generation_draft(record["id"])
        return {"ok":True,"draft":self.governance.generation_draft(record["id"]),"validation":validation,
                "publication_policy":"validacao_independente_mais_aprovacao_humana"}

    def publish_generation_draft(self, draft_id: str) -> dict:
        item = self.governance.generation_draft(str(draft_id))
        if str(item.get("status")) != "aprovado":
            raise ValueError("Somente rascunhos aprovados por uma pessoa podem ser publicados no Banco Editorial.")
        question = dict(item.get("draft") or {})
        question.setdefault("revisao", {})["status"] = "aprovado"
        question["revisao"]["confianca"] = 1.0
        question.setdefault("curadoria", {})["responsavel"] = "Aprovação humana · Etapa 5"
        question["curadoria"]["notas"] = str(item.get("human_note") or "Rascunho validado e aprovado antes da publicação.")
        result = self.editorial.publish_generated_question(question)
        uid = str(result.get("uid") or "")
        self.governance.mark_generation_published(str(draft_id), uid)
        return {"draft":self.governance.generation_draft(str(draft_id)),"published":result}

    def run_multimodal_grounding_benchmark(self, limit: int = 30) -> dict:
        from core.grounding_benchmark import MultimodalGroundingBenchmark
        benchmark = MultimodalGroundingBenchmark(self.knowledge, self.governance)
        return benchmark.run(limit=max(1, min(100, int(limit or 30))))

    def run_retrieval_calibration(self, limit: int = 30) -> dict:
        from core.retrieval_calibration import RetrievalCalibrationService
        service = RetrievalCalibrationService(self.knowledge, self.governance, self.knowledge.retrieval_calibration_store)
        return service.calibrate(limit=max(1, min(100, int(limit or 30))))

    def apply_retrieval_calibration(self, profile_id: str) -> dict:
        from core.retrieval_calibration import profile_by_id
        profile = profile_by_id(str(profile_id or ""))
        if not profile:
            raise ValueError("Perfil de reranking desconhecido.")
        return self.knowledge.retrieval_calibration_store.apply(profile, reason="human_approval_ui")

    def rollback_retrieval_calibration(self) -> dict:
        return self.knowledge.retrieval_calibration_store.rollback()

    def save_retrieval_regression_baseline(self, limit: int = 30) -> dict:
        from app_shared import APP_VERSION
        from core.retrieval_calibration import benchmark_snapshot
        report = self.run_multimodal_grounding_benchmark(limit=limit)
        snapshot = benchmark_snapshot(report, release=APP_VERSION)
        return self.knowledge.retrieval_calibration_store.save_baseline(snapshot)

    def get_retrieval_regression_status(self, limit: int = 30) -> dict:
        from app_shared import APP_VERSION
        from core.retrieval_calibration import benchmark_snapshot, compare_regression
        report = self.run_multimodal_grounding_benchmark(limit=limit)
        current = benchmark_snapshot(report, release=APP_VERSION)
        profile = self.knowledge.retrieval_calibration_store.current()
        comparison = compare_regression(current, self.knowledge.retrieval_calibration_store.baseline(), thresholds=profile.get("thresholds"))
        return {"current": current, "baseline": self.knowledge.retrieval_calibration_store.baseline(), "comparison": comparison, "profile": profile}

    # QuestFlow 6.11.0: Observabilidade e Quality Gates de retrieval não pertencem
    # mais ao AI Engine. O plano de controle foi movido para
    # core.retrieval_health_service.RetrievalHealthService, com worker e store
    # próprios. O AI Engine mantém apenas geração/tutoria e tarefas de IA.

    def add_gold_question(self, uid: str, *, label: str = "", notes: str = "") -> dict:
        question = self.editorial.question(str(uid))
        retrieval = self.knowledge.retrieve(str(uid), "", limit=8)
        sources = retrieval.get("items", []) if isinstance(retrieval, dict) else []
        return self.governance.add_gold_question(question, sources=sources, label=label, notes=notes)

    @staticmethod
    def _predict_gold_answer(question: dict, sources: list[dict]) -> tuple[str, str, bool | None]:
        source_text = " ".join(str(src.get("content") or "") for src in sources if isinstance(src, dict))
        source_tokens = {x for x in re.findall(r"[a-záéíóúâêôãõç0-9]{4,}", source_text.casefold())}
        alternatives = [x for x in (question.get("alternativas") or []) if isinstance(x, dict)]
        if alternatives:
            scored = []
            for alt in alternatives:
                toks = {x for x in re.findall(r"[a-záéíóúâêôãõç0-9]{4,}", str(alt.get("texto") or "").casefold())}
                overlap = len(toks & source_tokens) / max(1, len(toks))
                scored.append((overlap, str(alt.get("chave") or "").upper(), str(alt.get("texto") or "")))
            scored.sort(reverse=True)
            best = scored[0]
            return best[1], f"Alternativa com maior suporte lexical nas evidências selecionadas ({best[0]*100:.0f}%).", bool(best[0] >= .35)
        statement_tokens = {x for x in re.findall(r"[a-záéíóúâêôãõç0-9]{4,}", str(question.get("enunciado") or "").casefold())}
        overlap = len(statement_tokens & source_tokens) / max(1, len(statement_tokens))
        return ("C" if overlap >= .42 else "E"), f"Item C/E estimado por suporte textual ({overlap*100:.0f}%).", bool(overlap >= .30)

    def run_gold_regression(self, limit: int = 50) -> dict:
        import uuid
        cases = self.governance.gold_questions(active_only=True)[:max(1,min(200,int(limit or 50)))]
        if not cases:
            return {"run_id":"","cases":0,"average_score":0,"correct":0,"items":[],"warning":"Nenhuma questão ouro ativa."}
        run_id = str(uuid.uuid4())
        results = []
        for case in cases:
            question = case.get("question") or {}
            sources = case.get("sources") or []
            if not sources:
                retrieval = self.knowledge.retrieve(str(case.get("question_uid") or ""), "", limit=8)
                sources = retrieval.get("items", []) if isinstance(retrieval, dict) else []
            predicted, response, supported = self._predict_gold_answer(question, sources)
            expected = str(case.get("expected_answer") or "").upper()
            correct = predicted == expected if predicted else None
            # Governance 2.0 evaluates the regression response as atomic claims,
            # not as one response-level bag of words.
            claim_eval = self.governance._claim_evaluation_payload(
                response_text=f"Gabarito: {predicted}. {response}", mode="gold_regression", official_answer=expected,
                sources=sources, source_texts=[str(src.get("content") or "") for src in sources if isinstance(src,dict)],
                question_context={"reference_date": str((question.get("contexto_temporal") or {}).get("data_prova") or "") if isinstance(question.get("contexto_temporal"),dict) else ""},
            )
            summary = claim_eval.get("claim_summary") or {}
            flags = list(claim_eval.get("flags") or [])
            expectations = case.get("expectations") if isinstance(case.get("expectations"), dict) else {}
            if not sources: flags.append("sem_fontes_para_regressao")
            if supported is False: flags.append("baixo_suporte_nas_fontes")
            if int(summary.get("contradicted") or 0): flags.append("regressao_com_afirmacao_contradita")
            required_refs = [str(x) for x in (expectations.get("required_refs") or []) if str(x)]
            response_low = str(response or "").casefold()
            missing_refs = [ref for ref in required_refs if str(ref).split(":",1)[-1].casefold() not in response_low]
            if missing_refs: flags.append("regressao_nao_mencionou_referencias_ouro:" + ",".join(missing_refs))
            claim_score = float(claim_eval.get("groundedness") or 0)
            min_support = float(expectations.get("min_claim_support") or 58.0)
            if claim_score < min_support: flags.append(f"suporte_abaixo_do_minimo_ouro:{min_support:.0f}")
            score = (55.0 if correct else 0.0) + claim_score * .35 + (10.0 if not int(summary.get("contradicted") or 0) else 0.0)
            if missing_refs: score -= min(12.0, len(missing_refs)*4.0)
            score = round(min(100.0, max(0.0, score)), 1)
            result = self.governance.record_gold_run(
                run_id=run_id,gold_id=str(case.get("id")),model=GOLD_MODEL_VERSION,
                predicted_answer=predicted,response_text=response,answer_correct=correct,
                source_supported=(claim_score >= 55 and not int(summary.get("contradicted") or 0)),score=score,flags=list(dict.fromkeys(flags)),
            )
            self.governance.record_gold_claim_evaluation(result["id"], claim_eval)
            result.update({"expected_answer":expected,"source_code":case.get("source_code"),"subject":case.get("subject"),
                           "claim_summary":summary,"claim_support_score":round(claim_score,1)})
            results.append(result)
        avg = sum(float(x.get("score") or 0) for x in results)/max(1,len(results))
        return {"run_id":run_id,"model":GOLD_MODEL_VERSION,"cases":len(results),"average_score":round(avg,1),
                "correct":sum(1 for x in results if x.get("answer_correct") is True),"items":results,
                "purpose":"regressao_permanente_do_pipeline_de_IA_por_afirmacao_e_evidencia",
                "evaluator":"qf-claim-evidence-evaluator-2"}

    def _tutor_error_workflow(self, *, pending_limit: int = 12, treated_limit: int = 12) -> tuple[list[dict], list[dict]]:
        """Split incorrect attempts into an actionable Tutor queue and treated history.

        A question leaves the queue only when there is a human-approved Tutor
        interaction at or after its latest incorrect attempt.  If the learner gets
        the same question wrong again later, the new attempt is newer than the last
        treatment anchor and the question automatically returns to the queue.

        This is a Tutor workflow rule only; it does not change FSRS, KT, IRT or the
        Learning Engine scheduler.
        """
        pending_limit = max(1, min(50, int(pending_limit or 12)))
        treated_limit = max(1, min(50, int(treated_limit or 12)))
        scan_limit = max(80, pending_limit + treated_limit)
        try:
            with self.learning.database.connect() as connection:
                rows = connection.execute(
                    """
                    WITH latest_error AS (
                        SELECT a.id AS attempt_id, a.question_uid, a.answered_at, a.confidence,
                               a.error_type, a.perceived_difficulty, a.learning_gap, a.response_seconds,
                               a.source, q.source_code, q.subject, q.primary_topic,
                               ROW_NUMBER() OVER (
                                   PARTITION BY a.question_uid
                                   ORDER BY a.answered_at DESC, a.id DESC
                               ) AS rn
                        FROM telegram_attempts a
                        JOIN questions q ON q.uid=a.question_uid
                        WHERE a.is_correct=0
                    ),
                    approved AS (
                        SELECT question_uid,
                               MAX(COALESCE(NULLIF(reviewed_at,''), created_at)) AS treated_at
                        FROM qf_ai_interactions
                        WHERE interaction_type='tutor' AND status='aprovado'
                        GROUP BY question_uid
                    )
                    SELECT e.attempt_id, e.question_uid, e.answered_at, e.confidence,
                           e.error_type, e.perceived_difficulty, e.learning_gap, e.response_seconds,
                           e.source, e.source_code, e.subject, e.primary_topic,
                           a.treated_at,
                           CASE
                               WHEN a.treated_at IS NOT NULL AND a.treated_at >= e.answered_at THEN 1
                               ELSE 0
                           END AS treated
                    FROM latest_error e
                    LEFT JOIN approved a ON a.question_uid=e.question_uid
                    WHERE e.rn=1
                    ORDER BY e.answered_at DESC, e.attempt_id DESC
                    LIMIT ?
                    """,
                    (scan_limit,),
                ).fetchall()
        except Exception:
            # Compatibility fallback for partially initialized legacy databases.
            return self.learning.recent_errors(limit=pending_limit), []

        pending: list[dict] = []
        treated: list[dict] = []
        for row in rows:
            item = dict(row)
            item["treated"] = bool(item.get("treated"))
            item["workflow_status"] = "tratado" if item["treated"] else "revisar"
            if item["treated"]:
                if len(treated) < treated_limit:
                    treated.append(item)
            elif len(pending) < pending_limit:
                pending.append(item)
        return pending, treated

    def workspace(self, uid: str = "") -> dict:
        recent, treated = self._tutor_error_workflow(pending_limit=12, treated_limit=12)
        selected_uid = str(uid or "").strip() or (str(recent[0].get("question_uid")) if recent else "")
        selected = None
        if selected_uid:
            try:
                question = self.editorial.question(selected_uid)
                selected = {
                    "uid": selected_uid,
                    "code": str(question.get("codigo_origem") or question.get("database_uid") or selected_uid),
                    "subject": str(question.get("materia") or ""), "topic": str(question.get("assunto") or ""),
                    "statement": str(question.get("enunciado") or "")[:1100],
                    "has_image": bool(isinstance(question.get("imagem_questao"), dict) and str((question.get("imagem_questao") or {}).get("path") or "").strip()),
                    "visual_context": question.get("contexto_visual") if isinstance(question.get("contexto_visual"), dict) else {},
                    "diagnosis": self.diagnose_error(selected_uid, persist=True),
                    "learner": self.learner.question_state(selected_uid),
                    "scaffolding": self.learning.scaffolding_signal(selected_uid),
                }
            except Exception:
                selected = None
        raw_candidates = self.editorial.question_candidates(limit=250)
        # The Tutor UI must never expose database UUIDs as the human-facing
        # identity of a question.  Keep the stable UID only as an internal
        # value and publish a small, explicit view-model for selection.
        candidates = []
        for item in raw_candidates:
            if not isinstance(item, dict):
                continue
            candidate_uid = str(item.get("uid") or item.get("database_uid") or "").strip()
            if not candidate_uid:
                continue
            candidates.append({
                "uid": candidate_uid,
                "code": str(item.get("source_code") or item.get("codigo_origem") or item.get("codigo") or "").strip(),
                "subject": str(item.get("subject") or item.get("materia") or "").strip(),
                "topic": str(item.get("primary_topic") or item.get("assunto") or "").strip(),
                "lesson": str(item.get("lesson") or item.get("aula_planilha") or "").strip(),
                "statement": str(item.get("statement") or item.get("enunciado") or "").strip()[:360],
            })
        latest_interaction = None
        if selected_uid:
            try:
                latest_interaction = self.governance.latest_interaction(selected_uid, interaction_type="tutor")
            except Exception:
                latest_interaction = None
        return {"selected": selected, "recent_errors": recent, "error_review_queue": recent,
                "treated_errors": treated, "candidates": candidates,
                "latest_interaction": latest_interaction,
                "governance": self.governance.dashboard(), "modes": sorted(TUTOR_MODES),
                "scaffolding": {"version": SCAFFOLD_VERSION, "levels": SCAFFOLD_LEVELS, "representations": sorted(SCAFFOLD_REPRESENTATIONS)}}

    def health(self) -> dict:
        return {
            "id": self.engine_id, "name": self.name, "version": self.version, "status": "ready",
            "metrics": {"modes": 4, "online_provider": "multi_provider_gateway", "offline_fallback": True, "human_in_the_loop": True,
                        "controlled_generation": True, "gold_regression": True, "generator_version": GENERATOR_VERSION,
                        "structured_outputs": True, "prompt_injection_defense": True, "privacy_center": True,
                        "progressive_scaffolding": True, "scaffold_levels": 6, "multimodal_local_review": True,
                        "multimodal_rag_3": True, "binary_media_opt_in": True},
        }
