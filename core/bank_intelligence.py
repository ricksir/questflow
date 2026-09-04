from __future__ import annotations

"""Curadoria, proveniência e qualidade do banco de questões.

A camada mantém os sinais editoriais separados do conteúdo pedagógico bruto.
Ela foi desenhada para combinar práticas comuns de grandes bancos de questões:
proveniência explícita, taxonomia rica, curadoria humana, controle de duplicidade,
dificuldade empírica e comentários assistidos por IA com revisão antes da publicação.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Any, Iterable

INTELLIGENCE_VERSION = "qf-bank-intelligence-4"

ORIGIN_TYPES = {
    "oficial",
    "inedita_propria",
    "adaptada",
    "literal_norma",
    "manual",
    "nao_informada",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: Any) -> str:
    text = _clean(value).casefold()
    text = re.sub(r"[^a-z0-9áéíóúâêôãõç]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_origin_type(value: Any) -> str:
    raw = _norm(value).replace(" ", "_")
    aliases = {
        "prova_oficial": "oficial",
        "questao_oficial": "oficial",
        "inédita": "inedita_propria",
        "inedita": "inedita_propria",
        "autoral": "inedita_propria",
        "propria": "inedita_propria",
        "própria": "inedita_propria",
        "adaptacao": "adaptada",
        "adaptação": "adaptada",
        "lei_seca": "literal_norma",
        "literal": "literal_norma",
    }
    value = aliases.get(raw, raw)
    return value if value in ORIGIN_TYPES else "nao_informada"


def infer_origin_type(question: dict) -> str:
    provenance = question.get("proveniencia", {}) if isinstance(question.get("proveniencia"), dict) else {}
    explicit = (
        provenance.get("tipo")
        or question.get("origem_questao")
        or question.get("tipo_origem")
        or question.get("origem")
    )
    normalized = normalize_origin_type(explicit)
    if normalized != "nao_informada":
        return normalized

    flags = " ".join(
        _norm(question.get(key))
        for key in ("observacao", "observacoes", "prova", "fonte_tipo", "natureza")
    )
    if "inedit" in flags or "autoral" in flags:
        return "inedita_propria"
    if "adaptad" in flags:
        return "adaptada"
    if "lei seca" in flags or "literal" in flags:
        return "literal_norma"

    source = question.get("fonte", {}) if isinstance(question.get("fonte"), dict) else {}
    method = _norm(source.get("metodo") or source.get("origem") or question.get("metodo_extracao"))
    if method == "manual" or _norm(source.get("arquivo")) in {"manual", "nova questao"}:
        return "manual"

    # Banca + ano + prova/órgão é um sinal forte de questão oriunda de prova.
    if _clean(question.get("banca")) and question.get("ano") and (
        _clean(question.get("prova")) or _clean(question.get("orgao"))
    ):
        return "oficial"
    return "nao_informada"


def commentary_source(question: dict) -> str:
    meta = question.get("comentario_meta", {}) if isinstance(question.get("comentario_meta"), dict) else {}
    explicit = _clean(meta.get("origem") or question.get("origem_comentario"))
    if explicit:
        return explicit
    explanation = _clean(question.get("explicacao"))
    if not explanation:
        return "sem_comentario"
    method = _norm(meta.get("metodo") or question.get("metodo_comentario"))
    if "ia" in method or "google" in method or "gpt" in method or "gemini" in method:
        return "ia_assistida"
    if method:
        return method.replace(" ", "_")
    return "manual_nao_classificado"


def rights_status(question: dict) -> str:
    meta = question.get("direitos", {}) if isinstance(question.get("direitos"), dict) else {}
    explicit = _clean(meta.get("status") or question.get("status_direitos"))
    if explicit:
        return explicit
    origin = infer_origin_type(question)
    if origin == "oficial":
        return "origem_oficial_identificada"
    if origin in {"inedita_propria", "adaptada", "literal_norma", "manual"}:
        return "autoria_ou_base_deve_ser_confirmada"
    return "origem_nao_verificada"


def _alternatives(question: dict) -> list[dict]:
    raw = question.get("alternativas")
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def statement_integrity(question: dict) -> dict:
    """Valida integridade do enunciado pelo contexto, não por tamanho arbitrário.

    Enunciados curtos são comuns em provas objetivas (ex.: ``A imunidade
    tributária:``). O validador só bloqueia ausências objetivas de conteúdo.
    Sinais heurísticos de possível corte viram *alertas*, não impedimentos à
    revisão humana.
    """
    statement = _clean(question.get("enunciado"))
    if not statement:
        return {"ok": False, "reason": "empty", "detail": "Enunciado ausente.", "warning": False}

    words = re.findall(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]+", statement, flags=re.UNICODE)
    if len(words) < 2:
        return {
            "ok": False,
            "reason": "insufficient_content",
            "detail": "Enunciado sem conteúdo textual suficiente para identificar a pergunta.",
            "warning": False,
        }

    lower = statement.casefold()
    explicit_missing_markers = (
        "[enunciado ausente]", "[texto ausente]", "enunciado não identificado",
        "enunciado nao identificado", "texto não identificado", "texto nao identificado",
    )
    if any(marker in lower for marker in explicit_missing_markers):
        return {
            "ok": False,
            "reason": "missing_marker",
            "detail": "O campo contém um marcador explícito de enunciado ausente/não identificado.",
            "warning": False,
        }

    alts = _alternatives(question)
    keys = {_clean(item.get("chave")).upper() for item in alts if _clean(item.get("chave"))}
    answer = _clean(question.get("gabarito")).upper()
    qtype = _norm(question.get("tipo"))
    answer_ok = bool(answer and answer in keys)
    if "certo" in qtype and "errado" in qtype:
        answer_ok = answer in {"C", "E"}

    stripped = statement.rstrip()
    last_word = words[-1].casefold()
    trailing_connectors = {
        "a", "à", "ao", "aos", "às", "com", "conforme", "da", "das", "de", "do", "dos",
        "e", "em", "mediante", "nos", "nas", "ou", "para", "pela", "pelas", "pelo", "pelos",
        "por", "que", "segundo", "sem", "sob", "quando",
    }
    suspicious = (
        stripped.endswith(("...", "…", ",", ";", "/", "(", "[", "{"))
        or (last_word in trailing_connectors and not stripped.endswith((":", "?", ".", "!")))
    )

    # Em questões objetivas a unidade semântica é enunciado + alternativas +
    # gabarito. Não há qualquer mínimo de caracteres para o stem.
    if len(alts) >= 2 and answer_ok:
        return {
            "ok": True,
            "reason": "contextual_short" if len(statement) < 40 else "contextual",
            "detail": (
                "Enunciado curto, mas estruturalmente íntegro no contexto das alternativas e do gabarito."
                if len(statement) < 40 else
                "Enunciado estruturalmente íntegro no contexto da questão."
            ),
            "warning": bool(suspicious),
            "warning_detail": "Há um sinal de possível corte no final do texto; confira visualmente antes de concluir a revisão." if suspicious else "",
        }

    # Gabarito e alternativas são checks independentes. A falta deles não deve
    # converter automaticamente um texto legível em 'enunciado incompleto'.
    return {
        "ok": True,
        "reason": "textual",
        "detail": "Enunciado textual presente e sem ausência objetiva de conteúdo.",
        "warning": bool(suspicious),
        "warning_detail": "Há um sinal de possível corte no final do texto; confira visualmente antes de concluir a revisão." if suspicious else "",
    }


def calculate_quality(question: dict) -> dict:
    """Pontuação editorial 0..100 com checklist explicável."""
    score = 0.0
    checks: list[dict] = []

    def add(label: str, ok: bool, weight: float, detail: str) -> None:
        nonlocal score
        if ok:
            score += weight
        checks.append({"label": label, "ok": bool(ok), "weight": weight, "detail": detail})

    statement = _clean(question.get("enunciado"))
    alts = _alternatives(question)
    keys = {_clean(item.get("chave")).upper() for item in alts if _clean(item.get("chave"))}
    answer = _clean(question.get("gabarito")).upper()
    qtype = _norm(question.get("tipo"))
    answer_ok = bool(answer and answer in keys)
    if "certo" in qtype and "errado" in qtype:
        answer_ok = answer in {"C", "E"}

    statement_check = statement_integrity(question)
    add("Enunciado íntegro", bool(statement_check["ok"]), 18, str(statement_check["detail"]))
    add("Gabarito consistente", answer_ok, 14, "Gabarito corresponde às opções disponíveis.")
    add("Alternativas estruturadas", len(alts) >= 2, 10, "Opções separadas e reutilizáveis no Telegram.")
    add("Matéria informada", bool(_clean(question.get("materia"))), 9, "Matéria disponível para filtros e prioridade.")
    add("Assunto informado", bool(_clean(question.get("assunto"))), 9, "Assunto principal disponível para taxonomia.")
    add("Banca identificada", bool(_clean(question.get("banca"))), 6, "Banca permite análise de incidência e estilo.")
    add("Ano identificado", bool(question.get("ano")), 5, "Ano permite recorte temporal.")
    add("Prova/órgão identificados", bool(_clean(question.get("prova")) or _clean(question.get("orgao"))), 5, "Contexto de origem rastreável.")
    add("Proveniência classificada", infer_origin_type(question) != "nao_informada", 7, "Origem editorial da questão registrada.")
    source_meta = question.get("fonte", {}) if isinstance(question.get("fonte"), dict) else {}
    provenance = question.get("proveniencia", {}) if isinstance(question.get("proveniencia"), dict) else {}
    traceable_source = _clean(
        provenance.get("fonte_primaria")
        or question.get("fonte_primaria")
        or source_meta.get("arquivo")
        or source_meta.get("url")
        or source_meta.get("documento")
    )
    add("Fonte rastreável", bool(traceable_source), 5, "Arquivo, URL, documento ou referência primária associada.")
    add("Comentário disponível", bool(_clean(question.get("explicacao"))), 8, "Explicação pronta para pós-resposta.")
    review = question.get("revisao", {}) if isinstance(question.get("revisao"), dict) else {}
    add("Curadoria aprovada", _norm(review.get("status")) in {"aprovado", "aprovado automaticamente"}, 4, "Questão já passou por aprovação editorial.")

    score = round(min(100.0, score), 1)
    if score >= 88:
        grade, status = "A", "pronta"
    elif score >= 72:
        grade, status = "B", "revisar"
    elif score >= 52:
        grade, status = "C", "incompleta"
    else:
        grade, status = "D", "bloqueada"
    warnings: list[dict] = []
    if statement_check.get("warning"):
        warnings.append({
            "label": "Conferir enunciado",
            "detail": str(statement_check.get("warning_detail") or "Confira visualmente o enunciado."),
            "blocking": False,
        })
    return {
        "version": INTELLIGENCE_VERSION,
        "score": score,
        "grade": grade,
        "status": status,
        "checks": checks,
        "missing": [item["label"] for item in checks if not item["ok"]],
        "warnings": warnings,
    }


CRITICAL_CURATION_CHECKS = {
    "Enunciado íntegro",
    "Gabarito consistente",
    "Alternativas estruturadas",
    "Matéria informada",
    "Assunto informado",
}


def curation_readiness(question: dict) -> dict:
    """Separa qualidade editorial de conclusão da revisão humana.

    A nota de qualidade continua medindo o grau de enriquecimento do registro,
    porém não pode anular uma decisão humana explícita. Uma questão aprovada por
    uma pessoa fica ``pronta`` quando os controles críticos estão íntegros e a
    qualidade mínima é B (>=72). Campos de enriquecimento — comentário, fonte
    detalhada, banca/ano/prova etc. — continuam visíveis como oportunidades, mas
    deixam de prender indefinidamente uma questão já revisada na fila.
    """
    quality = calculate_quality(question)
    checks = list(quality.get("checks") or [])
    blocking_missing = [
        str(item.get("label")) for item in checks
        if not bool(item.get("ok")) and str(item.get("label")) in CRITICAL_CURATION_CHECKS
    ]
    review = question.get("revisao", {}) if isinstance(question.get("revisao"), dict) else {}
    review_status = _norm(review.get("status"))
    meta = question.get("curadoria", {}) if isinstance(question.get("curadoria"), dict) else {}

    # 6.6.5: aprovação automática do extrator/fluxo NÃO equivale a uma revisão
    # humana concluída. Esse era o ponto que tornava a interface ambígua: o
    # editor exibia "Aprovada auto.", mas a Curadoria continuava aguardando uma
    # decisão humana. A conclusão explícita fica registrada no bloco curadoria.
    auto_approved = review_status in {"aprovado automaticamente", "autoaprovado", "autoaprovada"}
    explicit_human_completion = bool(meta.get("revisao_humana_concluida"))
    manual_review_status = review_status in {"aprovado", "aprovado manualmente"}
    human_approved = bool(explicit_human_completion or manual_review_status)
    manual_block = bool(meta.get("bloqueio_manual"))

    # A aprovação editorial vale 4 pontos no checklist. Se a questão ainda está
    # pendente, concluir a revisão humana acrescentará esse crédito; se já foi
    # autoaprovada, o crédito já existe na nota, mas ainda falta a decisão humana.
    current_score = float(quality.get("score") or 0)
    quality_already_has_review_credit = review_status in {
        "aprovado", "aprovado manualmente", "aprovado automaticamente", "autoaprovado", "autoaprovada"
    }
    prospective_score = min(100.0, current_score + (0.0 if quality_already_has_review_credit else 4.0))
    can_complete_review = not manual_block and not blocking_missing and prospective_score >= 72.0

    if manual_block:
        status = "bloqueada"
    elif human_approved and can_complete_review:
        status = "pronta"
    else:
        status = str(quality.get("status") or "revisar")

    return {
        "status": status,
        "quality": quality,
        "review_status": review_status or "pendente",
        "human_approved": human_approved,
        "auto_approved": auto_approved,
        "explicit_human_completion": explicit_human_completion,
        "can_complete_review": can_complete_review,
        "prospective_score": prospective_score,
        "blocking_missing": blocking_missing,
        "enrichment_missing": [
            str(item.get("label")) for item in checks
            if not bool(item.get("ok")) and str(item.get("label")) not in CRITICAL_CURATION_CHECKS
        ],
        "human_override": bool(human_approved and status == "pronta" and str(quality.get("status")) != "pronta"),
    }


def curation_status(question: dict) -> str:
    """Estado editorial final, respeitando a revisão humana explícita."""
    return str(curation_readiness(question)["status"])


def empirical_difficulty(*, attempts: int, correct: int, hard_count: int = 0) -> dict:
    attempts = max(0, int(attempts or 0))
    correct = max(0, min(attempts, int(correct or 0)))
    hard_count = max(0, int(hard_count or 0))
    if attempts == 0:
        return {"score": None, "label": "sem_dados", "accuracy": None, "confidence": "sem_amostra"}
    accuracy = correct / attempts
    # Erro observado domina; percepção de dificuldade refina o sinal.
    hard_ratio = min(1.0, hard_count / attempts)
    score = min(1.0, max(0.0, (1.0 - accuracy) * 0.82 + hard_ratio * 0.18))
    if score >= 0.58:
        label = "dificil"
    elif score >= 0.34:
        label = "media"
    else:
        label = "facil"
    confidence = "baixa" if attempts < 8 else "moderada" if attempts < 25 else "boa"
    return {
        "score": round(score * 100.0, 1),
        "label": label,
        "accuracy": round(accuracy * 100.0, 1),
        "confidence": confidence,
    }


def duplicate_similarity(left: str, right: str) -> float:
    a, b = _norm(left), _norm(right)
    if not a or not b:
        return 0.0
    seq = SequenceMatcher(None, a[:4000], b[:4000]).ratio()
    at = {token for token in a.split() if len(token) >= 4}
    bt = {token for token in b.split() if len(token) >= 4}
    jaccard = len(at & bt) / max(1, len(at | bt))
    prefix = 1.0 if len(a) >= 90 and (a[:90] in b or b[:90] in a) else 0.0
    return round(min(1.0, seq * 0.48 + jaccard * 0.42 + prefix * 0.10), 4)


def split_pipe(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    return [_clean(item) for item in str(value or "").split("|") if _clean(item)]


def intelligence_snapshot(question: dict) -> dict:
    quality = calculate_quality(question)
    readiness = curation_readiness(question)
    provenance = question.get("proveniencia", {}) if isinstance(question.get("proveniencia"), dict) else {}
    curation = question.get("curadoria", {}) if isinstance(question.get("curadoria"), dict) else {}
    return {
        "version": INTELLIGENCE_VERSION,
        "origin_type": infer_origin_type(question),
        "origin_source": _clean(provenance.get("fonte_primaria") or provenance.get("url") or provenance.get("documento")),
        "origin_verified": bool(provenance.get("verificada")),
        "curation_status": str(readiness.get("status") or curation_status(question)),
        "curation_review": {
            "review_status": str(readiness.get("review_status") or "pendente"),
            "human_approved": bool(readiness.get("human_approved")),
            "auto_approved": bool(readiness.get("auto_approved")),
            "can_complete_review": bool(readiness.get("can_complete_review")),
            "blocking_missing": list(readiness.get("blocking_missing") or []),
            "enrichment_missing": list(readiness.get("enrichment_missing") or []),
            "prospective_score": float(readiness.get("prospective_score") or quality.get("score") or 0),
        },
        "curation_owner": _clean(curation.get("responsavel")),
        "curation_notes": _clean(curation.get("notas")),
        "quality": quality,
        "commentary_source": commentary_source(question),
        "rights_status": rights_status(question),
        "tags": split_pipe(question.get("tags")),
        "law_refs": split_pipe(question.get("referencias_legais")),
    }


def build_ai_commentary_brief(question: dict) -> dict:
    """Pacote auditável para comentário assistido por IA/RAG.

    Não chama provedor externo. A UI pode usá-lo antes de uma pesquisa/LLM e
    sempre mantém o resultado como rascunho até aprovação humana.
    """
    alts = _alternatives(question)
    lines = [f"{_clean(item.get('chave')).upper()}) {_clean(item.get('texto'))}" for item in alts]
    context = {
        "codigo": _clean(question.get("codigo_origem")),
        "materia": _clean(question.get("materia")),
        "assunto": _clean(question.get("assunto")),
        "banca": _clean(question.get("banca")),
        "ano": question.get("ano"),
        "enunciado": _clean(question.get("enunciado")),
        "alternativas": lines,
        "gabarito_oficial": _clean(question.get("gabarito")).upper(),
        "referencias_legais": split_pipe(question.get("referencias_legais")),
    }
    instruction = (
        "Explique a questão para estudo de concurso. Preserve o gabarito informado como dado de referência, "
        "mas sinalize conflito se a fundamentação apontar resultado diferente. Diferencie regra, exceção e pegadinha; "
        "não invente artigo, jurisprudência ou fonte. Quando não houver evidência suficiente, declare a lacuna."
    )
    return {
        "schema": "questflow.ai-commentary.v2",
        "instruction": instruction,
        "context": context,
        "publication_policy": "rascunho_requer_aprovacao_humana",
        "recommended_evidence": ["RAG híbrido local", "PDF/aula vinculada", "legislação oficial", "gabarito oficial", "fonte primária"],
    }


__all__ = [
    "INTELLIGENCE_VERSION",
    "ORIGIN_TYPES",
    "build_ai_commentary_brief",
    "calculate_quality",
    "commentary_source",
    "curation_status",
    "curation_readiness",
    "CRITICAL_CURATION_CHECKS",
    "duplicate_similarity",
    "empirical_difficulty",
    "infer_origin_type",
    "intelligence_snapshot",
    "normalize_origin_type",
    "rights_status",
    "split_pipe",
]
