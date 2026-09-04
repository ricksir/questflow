from __future__ import annotations

import hashlib
import html
import json
import re
from html.parser import HTMLParser
from typing import Any


class _ReadableHtml(HTMLParser):
    BLOCKS = {"p", "div", "blockquote", "li", "ul", "ol", "br"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        if lowered in self.BLOCKS and self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")
        if lowered == "img":
            values = {str(key).casefold(): str(value or "") for key, value in attrs}
            source = values.get("src", "").strip()
            if source:
                self.images.append(source)
            alt = values.get("alt", "").strip()
            if alt:
                self.parts.append(f"[{alt}]")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in self.BLOCKS and self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        value = html.unescape("".join(self.parts)).replace("\r", "")
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r" *\n *", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()


def html_to_readable(value: Any) -> tuple[str, list[str]]:
    parser = _ReadableHtml()
    try:
        parser.feed(str(value or ""))
        parser.close()
    except Exception:
        return re.sub(r"<[^>]+>", "", str(value or "")).strip(), []
    return parser.text(), parser.images


def _reference_name(value: Any) -> str:
    return (
        str(value.get("nome") or value.get("label") or value.get("name") or "").strip()
        if isinstance(value, dict)
        else str(value or "").strip()
    )


def _reference_id(value: Any) -> int | str | None:
    if not isinstance(value, dict):
        return None
    result = value.get("id")
    return result if result not in (None, "") else None


def normalize_api_question(payload: dict[str, Any], *, review_status: str = "pendente") -> dict[str, Any]:
    """Converte o JSON público da APIdasQuestões para o modelo QuestFlow."""

    raw_id = str(payload.get("id") or "").strip()
    if not raw_id:
        raise ValueError("A questão externa não possui id.")
    external_id = str(payload.get("externalId") or raw_id).strip()
    source_code = external_id.upper()
    if source_code and source_code.isdigit():
        source_code = f"Q{source_code}"

    statement, statement_images = html_to_readable(payload.get("enunciado"))
    base = payload.get("textoBase") if isinstance(payload.get("textoBase"), dict) else {}
    base_text, base_images = html_to_readable(base.get("texto"))
    options: list[dict[str, str]] = []
    for index, option in enumerate(payload.get("options") or []):
        if not isinstance(option, dict):
            continue
        key = str(option.get("key") or chr(97 + index)).strip().upper()
        option_text, _images = html_to_readable(option.get("text"))
        options.append({"chave": key, "texto": option_text})

    answer = str(payload.get("resposta") or "").strip().upper()
    true_false = bool(payload.get("certoOuErrado"))
    if true_false and not options:
        options = [{"chave": "C", "texto": "Certo"}, {"chave": "E", "texto": "Errado"}]
        if answer in {"CERTO", "C", "TRUE", "1"}:
            answer = "C"
        elif answer in {"ERRADO", "E", "FALSE", "0"}:
            answer = "E"

    canonical = {
        "provider": "api_das_questoes",
        "id": raw_id,
        "external_id": external_id,
        "statement": statement,
        "answer": answer,
        "options": options,
        "subject": _reference_name(payload.get("materia")),
        "topic": _reference_name(payload.get("topico")),
        "board": _reference_name(payload.get("banca")),
        "institution": _reference_name(payload.get("instituicao")),
        "year": payload.get("ano"),
        "exam": payload.get("nomeProva"),
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    images = [*statement_images, *base_images]
    image_url = str(payload.get("imagemUrl") or (images[0] if images else "")).strip()
    status = "anulada" if bool(payload.get("anulada")) else str(review_status or "pendente")
    currency = "desatualizada" if bool(payload.get("desatualizada")) else "atualidade_nao_verificada"

    return {
        "database_uid": f"api_das_questoes:{raw_id}",
        "uid": f"api_das_questoes:{raw_id}",
        "id": source_code or f"APIQ-{raw_id}",
        "codigo_origem": source_code or f"APIQ-{raw_id}",
        "fingerprint": fingerprint,
        "materia": canonical["subject"],
        "aula_planilha": "",
        "assunto": canonical["topic"],
        "assuntos": [canonical["topic"]] if canonical["topic"] else [],
        "banca": canonical["board"],
        "ano": payload.get("ano"),
        "orgao": canonical["institution"],
        "prova": str(payload.get("nomeProva") or ""),
        "nivel": str(payload.get("nivel") or ""),
        "dificuldade": str(payload.get("dificuldade") or ""),
        "tipo": "certo_errado" if true_false else "multipla_escolha",
        "enunciado": statement,
        "texto_base": {
            "id": str(base.get("id") or ""),
            "texto": base_text,
        } if base_text else {},
        "alternativas": options,
        "gabarito": answer,
        "explicacao": "",
        "origem_questao": "api_externa",
        "review_status": status,
        "revisao": {"status": status, "confianca": 1.0 if answer else 0.5, "alertas": []},
        "question_currency": currency,
        "imagem_questao": {"path": image_url, "remote": True} if image_url else {},
        "fonte": {
            "provedor": "APIdasQuestões",
            "api_version": "v1",
            "api_id": raw_id,
            "external_id": external_id,
            "pagina_documentacao": "https://www.apidasquestoes.com.br/documentacao",
            "texto_html": str(payload.get("enunciado") or ""),
            "texto_base_html": str(base.get("texto") or ""),
            "reference_ids": {
                "banca": _reference_id(payload.get("banca")),
                "materia": _reference_id(payload.get("materia")),
                "topico": _reference_id(payload.get("topico")),
                "instituicao": _reference_id(payload.get("instituicao")),
            },
        },
        "external_read_only": True,
    }


__all__ = ["html_to_readable", "normalize_api_question"]
