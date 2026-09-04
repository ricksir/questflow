from __future__ import annotations

import html
import json
import mimetypes
import os
import random
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from .network import network_urlopen
import uuid
from dataclasses import dataclass
from typing import Any, Callable

POLL_QUESTION_LIMIT = 300
POLL_OPTION_LIMIT = 100
POLL_EXPLANATION_LIMIT = 200
MESSAGE_LIMIT = 4096


def _escape(value: object) -> str:
    return html.escape(str(value or ""), quote=False)


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _option_label(item: dict, index: int, *, include_key: bool = True) -> str:
    key = _clean_text(item.get("chave", "")).upper() or chr(65 + index)
    value = _clean_text(item.get("texto", ""))
    if include_key and not re.match(rf"^{re.escape(key)}\s*[\)\.\-:]\s*", value, re.I):
        return f"{key}) {value}"
    return value


def _question_header_html(question: dict, position: int | None = None, total: int | None = None) -> str:
    code = _clean_text(question.get("codigo_origem") or question.get("id"))
    subject = _clean_text(question.get("materia")) or "Matéria não informada"
    lesson = _clean_text(question.get("aula_planilha") or question.get("aula_origem"))
    topic = _clean_text(question.get("assunto"))
    board = _clean_text(question.get("banca"))
    year = _clean_text(question.get("ano"))
    agency = _clean_text(question.get("orgao"))

    if position and total:
        title = f"🧠 <b>QUESTFLOW • QUESTÃO {position}/{total}</b>"
    elif position:
        title = f"🧠 <b>QUESTFLOW • QUESTÃO {position}</b>"
    else:
        title = "🧠 <b>QUESTFLOW • QUESTÃO</b>"
    lines = [title, "━━━━━━━━━━━━━━━━"]
    lines.append(f"📚 <b>{_escape(subject)}</b>")
    detail = " • ".join(item for item in (lesson, topic) if item)
    if detail:
        lines.append(f"🗂 {_escape(detail)}")
    source = " • ".join(item for item in (board, year, agency) if item)
    if source:
        lines.append(f"🏛 {_escape(source)}")
    if code:
        lines.append(f"🔖 <code>{_escape(code)}</code>")
    reason = _clean_text(question.get("selection_reason"))
    if reason:
        lines.append(f"🧭 <i>{_escape(reason)}</i>")
    lines.extend(["", "👇 <i>Marque a alternativa correta na enquete abaixo.</i>"])
    return "\n".join(lines)


def _question_action_markup(question: dict) -> dict | None:
    uid = str(question.get("database_uid", "") or "").strip()
    if not uid:
        return None
    rows: list[list[dict]] = []
    if _clean_text(question.get("explicacao")):
        rows.append([
            {"text": "📖 Ver explicação", "callback_data": f"qf:explain:{uid}", "style": "primary"},
            {"text": "⚠️ Corrigir", "callback_data": f"qf:review:{uid}", "style": "danger"},
        ])
    else:
        rows.append([
            {"text": "⚠️ Corrigir esta questão", "callback_data": f"qf:review:{uid}", "style": "danger"},
        ])
    rows.append([
        {"text": "➡️ Próxima questão", "callback_data": "qf:more:1", "style": "success"},
    ])
    for row in rows:
        for item in row:
            if len(str(item.get("callback_data", "")).encode("utf-8")) > 64:
                return None
    return {"inline_keyboard": rows}


def _feedback_markup(question: dict, *, attempt_id: str = "", is_correct: bool | None = None) -> dict | None:
    uid = str(question.get("database_uid", "") or "").strip()
    if not uid:
        return None
    rows: list[list[dict]] = []
    attempt = str(attempt_id or "").strip()
    if attempt:
        rows.append([
            {"text": "🧠 Sabia", "callback_data": f"qf:m:{attempt}:c:s", "style": "success"},
            {"text": "🤔 Dúvida", "callback_data": f"qf:m:{attempt}:c:d"},
            {"text": "🎲 Chutei", "callback_data": f"qf:m:{attempt}:c:g"},
        ])
        rows.append([
            {"text": "🟢 Fácil", "callback_data": f"qf:m:{attempt}:d:e"},
            {"text": "🟡 Média", "callback_data": f"qf:m:{attempt}:d:m"},
            {"text": "🔴 Difícil", "callback_data": f"qf:m:{attempt}:d:h"},
        ])
        if is_correct is False:
            rows.append([
                {"text": "📕 Não sabia", "callback_data": f"qf:m:{attempt}:e:n", "style": "danger"},
                {"text": "🔀 Confundi", "callback_data": f"qf:m:{attempt}:e:c"},
                {"text": "👀 Desatenção", "callback_data": f"qf:m:{attempt}:e:d"},
            ])
        rows.append([
            {"text": "📚 Preciso estudar este conteúdo", "callback_data": f"qf:m:{attempt}:g:y", "style": "primary"},
        ])
    rows.extend([
        [
            {"text": "🛠 Corrigir questão", "callback_data": f"qf:review:{uid}", "style": "danger"},
            {"text": "➡️ Próxima", "callback_data": "qf:more:1", "style": "success"},
        ],
        [{"text": "📊 Meu desempenho", "callback_data": "qf:stats", "style": "primary"}],
    ])
    # Telegram limita callback_data a 64 bytes; UUID + prefixos permanecem abaixo.
    for row in rows:
        if any(len(str(item.get("callback_data", "")).encode("utf-8")) > 64 for item in row):
            return {"inline_keyboard": rows[-2:]}
    return {"inline_keyboard": rows}


@dataclass(slots=True)
class TelegramError(RuntimeError):
    """Erro estruturado do Telegram, útil para decidir se uma nova tentativa faz sentido."""

    message: str
    category: str = "desconhecido"
    retryable: bool = False
    retry_after: int | None = None
    http_status: int | None = None
    error_code: int | None = None
    migrate_to_chat_id: str | None = None
    raw: dict | None = None

    def __str__(self) -> str:
        suffix = []
        if self.retry_after:
            suffix.append(f"tente novamente em {self.retry_after}s")
        if self.category:
            suffix.append(f"categoria: {self.category}")
        return f"{self.message}" + (f" ({'; '.join(suffix)})" if suffix else "")


def _friendly_category(description: str, status: int | None = None) -> tuple[str, bool]:
    text = description.lower()
    if status == 429 or "too many requests" in text or "retry after" in text:
        return "limite_de_requisicoes", True
    if status and status >= 500:
        return "servidor_telegram", True
    if any(term in text for term in ("timed out", "timeout", "temporarily unavailable", "connection reset")):
        return "conexao_temporaria", True
    if "chat not found" in text:
        return "chat_nao_encontrado", False
    if "bot was blocked" in text or "bot is blocked" in text:
        return "bot_bloqueado", False
    if "unauthorized" in text or status == 401:
        return "token_invalido", False
    if "not enough rights" in text or "have no rights" in text:
        return "sem_permissao", False
    if "poll" in text or "question" in text or "option" in text or "message is too long" in text:
        return "conteudo_invalido", False
    if "wrong file identifier" in text or "failed to get http url content" in text:
        return "midia_invalida", False
    if status and 400 <= status < 500:
        return "requisicao_invalida", False
    return "desconhecido", False


def _parse_error_payload(detail: str) -> dict:
    try:
        value = json.loads(detail)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _telegram_error_from_payload(payload: dict, *, status: int | None = None) -> TelegramError:
    description = str(payload.get("description") or f"Falha HTTP {status or ''}").strip()
    parameters = payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {}
    retry_after = parameters.get("retry_after")
    try:
        retry_after = int(retry_after) if retry_after is not None else None
    except (TypeError, ValueError):
        retry_after = None
    migrate_to_chat_id = parameters.get("migrate_to_chat_id")
    category, retryable = _friendly_category(description, status)
    if retry_after:
        retryable = True
    return TelegramError(
        description,
        category=category,
        retryable=retryable,
        retry_after=retry_after,
        http_status=status,
        error_code=payload.get("error_code") if isinstance(payload.get("error_code"), int) else status,
        migrate_to_chat_id=str(migrate_to_chat_id) if migrate_to_chat_id is not None else None,
        raw=payload,
    )


def classify_exception(error: Exception) -> TelegramError:
    if isinstance(error, TelegramError):
        return error
    if isinstance(error, ValueError):
        return TelegramError(str(error), category="validacao_local", retryable=False)
    if isinstance(error, (socket.timeout, TimeoutError)):
        return TelegramError(str(error) or "Tempo de conexão esgotado.", category="conexao_temporaria", retryable=True)
    if isinstance(error, urllib.error.URLError):
        reason = getattr(error, "reason", error)
        return TelegramError(f"Não foi possível acessar o Telegram: {reason}", category="conexao_temporaria", retryable=True)
    return TelegramError(str(error) or error.__class__.__name__, category="desconhecido", retryable=False)


def _read_response(request: urllib.request.Request, timeout: int) -> dict:
    try:
        with network_urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            result = json.loads(raw)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        payload = _parse_error_payload(detail)
        if not payload:
            payload = {"description": f"Telegram retornou erro HTTP {error.code}: {detail[:600]}"}
        raise _telegram_error_from_payload(payload, status=error.code) from error
    except urllib.error.URLError as error:
        raise TelegramError(
            f"Não foi possível acessar o Telegram: {error.reason}",
            category="conexao_temporaria",
            retryable=True,
        ) from error
    except (socket.timeout, TimeoutError) as error:
        raise TelegramError("Tempo de conexão com o Telegram esgotado.", category="conexao_temporaria", retryable=True) from error
    except json.JSONDecodeError as error:
        raise TelegramError("O Telegram retornou uma resposta que não pôde ser interpretada.", category="resposta_invalida", retryable=True) from error
    if not isinstance(result, dict) or not result.get("ok"):
        raise _telegram_error_from_payload(result if isinstance(result, dict) else {"description": "Falha desconhecida no Telegram."})
    return result


def _post(bot_token: str, method: str, payload: dict, timeout: int) -> dict:
    endpoint = f"https://api.telegram.org/bot{bot_token}/{method}"
    encoded = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(endpoint, data=encoded, method="POST")
    return _read_response(request, timeout)


def _post_multipart(bot_token: str, method: str, fields: dict[str, str], files: dict[str, str], timeout: int) -> dict:
    endpoint = f"https://api.telegram.org/bot{bot_token}/{method}"
    boundary = f"----QuestFlowBoundary{uuid.uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")
    for name, file_path in files.items():
        path = str(file_path)
        filename = os.path.basename(path)
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        with open(path, "rb") as handle:
            content = handle.read()
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8"))
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(content)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    request = urllib.request.Request(
        endpoint,
        data=bytes(body),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    return _read_response(request, timeout)


def with_retry(
    operation: Callable[[], dict],
    *,
    attempts: int = 3,
    base_delay: float = 1.5,
    max_delay: float = 30.0,
    progress: Callable[[int, TelegramError, float], None] | None = None,
) -> dict:
    """Executa uma operação do Telegram com backoff exponencial e jitter."""

    attempts = max(1, min(int(attempts), 8))
    last_error: TelegramError | None = None
    for attempt in range(1, attempts + 1):
        try:
            result = operation()
            if isinstance(result, dict):
                result.setdefault("_attempt_count", attempt)
            return result
        except Exception as error:
            parsed = classify_exception(error)
            last_error = parsed
            if not parsed.retryable or attempt >= attempts:
                raise parsed from error
            delay = float(parsed.retry_after or min(max_delay, base_delay * (2 ** (attempt - 1))))
            delay += random.uniform(0, min(0.75, delay * 0.15))
            if progress:
                progress(attempt, parsed, delay)
            time.sleep(delay)
    raise last_error or TelegramError("Falha de envio sem detalhes.")


def _question_image_path(question: dict) -> str:
    image_info = question.get("imagem_questao", {})
    if not isinstance(image_info, dict):
        return ""
    path = str(image_info.get("path", "")).strip()
    return path if path and os.path.exists(path) else ""


def send_photo(bot_token: str, chat_id: str, photo_path: str, caption: str = "", timeout: int = 30, parse_mode: str = "") -> dict:
    token = bot_token.strip()
    target = str(chat_id).strip()
    if not token:
        raise ValueError("Token do bot não informado.")
    if not target:
        raise ValueError("Chat ID não informado.")
    if not photo_path or not os.path.exists(photo_path):
        raise ValueError("Imagem da questão não encontrada.")
    fields = {"chat_id": target}
    if caption.strip():
        fields["caption"] = caption.strip()[:1024]
    if parse_mode:
        fields["parse_mode"] = parse_mode
    return _post_multipart(token, "sendPhoto", fields, {"photo": photo_path}, timeout)


def _split_message(text: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _answer_index(question: dict, alternatives: list[dict]) -> int:
    telegram = question.get("telegram", {})
    answer_index = telegram.get("indice_correto") if isinstance(telegram, dict) else None
    if isinstance(answer_index, int) and 0 <= answer_index < len(alternatives):
        return answer_index
    keys = [str(item.get("chave", "")).upper() for item in alternatives]
    answer = str(question.get("gabarito", "")).upper()
    if answer in keys:
        return keys.index(answer)
    raise ValueError("A questão ainda não possui gabarito compatível com as alternativas.")


def _context_text(question: dict, alternatives: list[dict]) -> str:
    number = question.get("numero_origem")
    code = question.get("codigo_origem") or question.get("id") or ""
    header_parts = []
    if number:
        header_parts.append(f"Questão {number}")
    if code:
        header_parts.append(str(code))
    metadata = " • ".join(
        part
        for part in [
            str(question.get("materia", "")).strip(),
            str(question.get("aula_planilha") or question.get("aula_origem") or "").strip(),
            str(question.get("assunto", "")).strip(),
            str(question.get("banca", "")).strip(),
            str(question.get("ano", "")).strip(),
            str(question.get("orgao", "")).strip(),
        ]
        if part
    )
    header = " • ".join(header_parts)
    lines = []
    if header:
        lines.append(header)
    if metadata:
        lines.append(metadata)
    if lines:
        lines.append("")
    lines.extend(["📝 ENUNCIADO", str(question.get("enunciado", "")).strip(), "", "ALTERNATIVAS"])
    for item in alternatives:
        key = str(item.get("chave", "")).upper()
        text = str(item.get("texto", "")).strip()
        lines.append(f"{key}) {text}")
    return "\n".join(lines).strip()




def question_review_markup(question: dict) -> dict | None:
    """Compatibilidade: retorna o novo conjunto de ações da questão."""
    return _question_action_markup(question)


def telegram_payload(question: dict, chat_id: str, *, native_explanation: bool = False) -> dict:
    # Bases antigas podiam conter tipo=certo_errado com alternativas A-E.
    # O Telegram também deve obedecer ao tipo canônico, mesmo antes de a questão
    # ser aberta e salva novamente no editor.
    if str(question.get("tipo", "")).strip() == "certo_errado":
        try:
            from core.question_types import canonicalize_question_format

            _, alternatives, normalized_answer = canonicalize_question_format(
                "certo_errado", question.get("alternativas", []), question.get("gabarito", "")
            )
            question = dict(question)
            question["alternativas"] = alternatives
            question["gabarito"] = normalized_answer
        except Exception:
            alternatives = list(question.get("alternativas", []))
    else:
        alternatives = list(question.get("alternativas", []))
    if len(alternatives) < 2:
        raise ValueError("A questão precisa ter pelo menos duas alternativas.")
    if len(alternatives) > 12:
        raise ValueError("O Telegram aceita no máximo doze alternativas em uma enquete.")
    statement = str(question.get("enunciado", "")).strip()
    if not statement:
        raise ValueError("O enunciado da questão está vazio.")
    answer_index = _answer_index(question, alternatives)
    full_options = [_option_label(item, index, include_key=True) for index, item in enumerate(alternatives)]
    if any(not option for option in full_options):
        raise ValueError("Há alternativa vazia. Revise a questão antes do envio.")

    direct_poll = len(statement) <= POLL_QUESTION_LIMIT and all(len(option) <= POLL_OPTION_LIMIT for option in full_options)
    if direct_poll:
        poll_question = f"📝 {statement}" if len(statement) <= POLL_QUESTION_LIMIT - 2 else statement
        poll_options = full_options
        context = ""
    else:
        number = question.get("numero_origem")
        poll_question = f"Questão {number}: selecione a alternativa correta." if number else "Selecione a alternativa correta."
        if str(question.get("tipo", "")) == "certo_errado":
            poll_options = full_options
        else:
            poll_options = [str(item.get("chave", "")).upper() or chr(65 + index) for index, item in enumerate(alternatives)]
        context = _context_text(question, alternatives)

    payload = {
        "chat_id": chat_id,
        "question": poll_question[:POLL_QUESTION_LIMIT],
        "options": json.dumps([{"text": option[:POLL_OPTION_LIMIT]} for option in poll_options], ensure_ascii=False),
        "type": "quiz",
        "correct_option_ids": json.dumps([answer_index]),
        "is_anonymous": "false",
        "allows_revoting": "false",
    }
    explanation = re.sub(r"\n{3,}", "\n\n", str(question.get("explicacao", "")).strip())
    # A explicação nativa do quiz fica limitada a 200 caracteres e aparece em uma caixa
    # pequena. O QuestFlow envia a explicação completa em uma mensagem organizada após a resposta.
    if native_explanation and explanation:
        payload["explanation"] = explanation[:POLL_EXPLANATION_LIMIT]
    review_markup = _question_action_markup(question)
    if review_markup is not None:
        payload["reply_markup"] = json.dumps(review_markup, ensure_ascii=False)
    payload["_context"] = context
    payload["_direct_poll"] = direct_poll
    return payload


def send_quiz(
    bot_token: str,
    chat_id: str,
    question: dict,
    timeout: int = 30,
    *,
    position: int | None = None,
    total: int | None = None,
    show_question_card: bool = True,
    native_explanation: bool = False,
) -> dict:
    token = bot_token.strip()
    if not token:
        raise ValueError("Token do bot não informado.")
    target_chat = str(chat_id).strip()
    if not target_chat:
        raise ValueError("Chat ID não informado.")
    payload = telegram_payload(question, target_chat, native_explanation=native_explanation)
    context = payload.pop("_context", "")
    direct_poll = bool(payload.pop("_direct_poll", False))
    image_result = None
    card_results: list[dict] = []
    image_path = _question_image_path(question)
    header = _question_header_html(question, position=position, total=total)
    if image_path:
        image_result = send_photo(token, target_chat, image_path, caption=header if show_question_card else "Imagem da questão", timeout=timeout, parse_mode="HTML" if show_question_card else "")
    elif show_question_card:
        card_results.append(_post(token, "sendMessage", {
            "chat_id": target_chat,
            "text": header,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }, timeout))
    context_results: list[dict] = []
    context_chunks = _split_message(context, limit=3500)
    for index, chunk in enumerate(context_chunks, start=1):
        heading = "📝 <b>ENUNCIADO E ALTERNATIVAS</b>" if index == 1 else f"↪️ <b>CONTINUAÇÃO {index}/{len(context_chunks)}</b>"
        context_results.append(_post(token, "sendMessage", {
            "chat_id": target_chat,
            "text": f"{heading}\n\n{_escape(chunk)}",
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }, timeout))
    poll_result = _post(token, "sendPoll", payload, timeout)
    return {
        "ok": True,
        "direct_poll": direct_poll,
        "image": image_result,
        "question_cards": card_results,
        "context_messages": context_results,
        "poll": poll_result,
    }


def _selected_option_text(question: dict, selected_indices: list[int]) -> str:
    alternatives = list(question.get("alternativas", []))
    labels = []
    for index in selected_indices:
        if 0 <= index < len(alternatives):
            labels.append(_option_label(alternatives[index], index, include_key=True))
    return ", ".join(labels) or "não identificada"


def _correct_option_text(question: dict, correct_index: int | None = None) -> str:
    alternatives = list(question.get("alternativas", []))
    if correct_index is None:
        correct_index = _answer_index(question, alternatives)
    if 0 <= int(correct_index) < len(alternatives):
        return _option_label(alternatives[int(correct_index)], int(correct_index), include_key=True)
    return str(question.get("gabarito", "") or "não identificada")


def _explanation_chunks(question: dict, *, max_body: int = 3100) -> list[str]:
    explanation = re.sub(r"\n{3,}", "\n\n", str(question.get("explicacao", "") or "").strip())
    if not explanation:
        return []
    return _split_message(explanation, limit=max_body)


def send_explanation_card(
    bot_token: str,
    chat_id: str,
    question: dict,
    *,
    selected_indices: list[int] | None = None,
    correct_index: int | None = None,
    is_correct: bool | None = None,
    reply_to_message_id: int | None = None,
    timeout: int = 30,
    compact_result: bool = False,
    study_state: dict | None = None,
    attempt_id: str = "",
) -> dict:
    token = bot_token.strip()
    target = str(chat_id).strip()
    if not token or not target:
        raise ValueError("Token do bot ou Chat ID não informado.")
    selected_indices = list(selected_indices or [])
    correct_text = _correct_option_text(question, correct_index)
    selected_text = _selected_option_text(question, selected_indices) if selected_indices else ""
    subject = _clean_text(question.get("materia")) or "Matéria não informada"
    lesson = _clean_text(question.get("aula_planilha") or question.get("aula_origem"))
    topic = _clean_text(question.get("assunto"))
    code = _clean_text(question.get("codigo_origem") or question.get("id"))
    explanation_chunks = _explanation_chunks(question)

    if is_correct is True:
        title = "✅ <b>RESPOSTA CORRETA</b>"
        subtitle = "Sua marcação foi registrada. Continue assim!"
    elif is_correct is False:
        title = "❌ <b>REVISÃO NECESSÁRIA</b>"
        subtitle = "A resposta foi registrada. Veja o gabarito e a explicação abaixo."
    else:
        title = "📖 <b>EXPLICAÇÃO DA QUESTÃO</b>"
        subtitle = "Resumo do gabarito e do conteúdo cadastrado."

    summary_lines = [title, f"<i>{_escape(subtitle)}</i>", "━━━━━━━━━━━━━━━━"]
    if selected_text:
        marker = "✅" if is_correct is True else "❌" if is_correct is False else "👤"
        summary_lines.extend(["", f"{marker} <b>SUA MARCAÇÃO</b>", _escape(selected_text)])
    summary_lines.extend(["", "🎯 <b>GABARITO</b>", _escape(correct_text)])

    detail = " • ".join(item for item in (lesson, topic) if item)
    summary_lines.extend(["", f"📚 <b>{_escape(subject)}</b>"])
    if detail:
        summary_lines.append(f"🗂 {_escape(detail)}")
    if code:
        summary_lines.append(f"🔖 <code>{_escape(code)}</code>")

    state = study_state or {}
    streak = max(0, int(state.get("streak", 0) or 0))
    response_seconds = float(state.get("response_seconds", 0.0) or 0.0)
    predicted = state.get("predicted_recall")
    reward = state.get("reward") if isinstance(state.get("reward"), dict) else {}
    xp = int(reward.get("xp", 0) or 0)
    if not xp:
        xp = 12 if is_correct is True else 3 if is_correct is False else 0
    progress_bits = []
    if xp:
        progress_bits.append(f"+{xp} XP")
    if reward.get("level"):
        progress_bits.append(f"nível {int(reward.get('level') or 1)}")
    if streak:
        progress_bits.append(f"sequência {streak}")
    if response_seconds > 0:
        progress_bits.append(f"{max(1, int(round(response_seconds)))}s")
    if predicted is not None:
        try:
            progress_bits.append(f"retenção prevista {float(predicted)*100:.0f}%")
        except (TypeError, ValueError):
            pass
    if progress_bits:
        summary_lines.extend(["", "🎮 <b>PROGRESSO</b>", _escape(" • ".join(progress_bits))])

    if compact_result and explanation_chunks:
        summary_lines.extend(["", "💡 <b>EXPLICAÇÃO</b>", "<i>Toque no botão “Explicação” para abrir o conteúdo completo.</i>"])
        explanation_chunks = []
    elif explanation_chunks:
        summary_lines.extend(["", "💡 <b>EXPLICAÇÃO</b>"])
    else:
        summary_lines.extend(["", "💡 <b>EXPLICAÇÃO</b>", "<i>Não cadastrada. Use “Corrigir questão” para completar este conteúdo.</i>"])

    results: list[dict] = []
    first_text = "\n".join(summary_lines)
    if explanation_chunks:
        first_text += "\n\n" + _escape(explanation_chunks[0])
    results.extend(send_message(
        token,
        target,
        first_text,
        timeout=timeout,
        reply_markup=_feedback_markup(question, attempt_id=attempt_id, is_correct=is_correct) if len(explanation_chunks) <= 1 else None,
        parse_mode="HTML",
        reply_to_message_id=reply_to_message_id,
    ).get("messages", []))
    for index, chunk in enumerate(explanation_chunks[1:], start=2):
        tail = f"💡 <b>EXPLICAÇÃO — PARTE {index}/{len(explanation_chunks)}</b>\n\n{_escape(chunk)}"
        results.extend(send_message(
            token,
            target,
            tail,
            timeout=timeout,
            reply_markup=_feedback_markup(question, attempt_id=attempt_id, is_correct=is_correct) if index == len(explanation_chunks) else None,
            parse_mode="HTML",
            reply_to_message_id=reply_to_message_id,
        ).get("messages", []))
    return {"ok": True, "messages": results}


def send_answer_feedback(bot_token: str, answer: dict, *, mode: str = "automatico", timeout: int = 30) -> dict:
    mode = str(mode or "automatico").strip().lower()
    if mode == "somente_botao":
        return {"ok": True, "skipped": True}
    return send_explanation_card(
        bot_token,
        str(answer.get("chat_id", "")),
        answer.get("question") or {},
        selected_indices=list(answer.get("selected_indices") or []),
        correct_index=answer.get("correct_index"),
        is_correct=bool(answer.get("is_correct")),
        reply_to_message_id=answer.get("message_id") if isinstance(answer.get("message_id"), int) else None,
        timeout=timeout,
        compact_result=(mode == "resultado_curto"),
        study_state=answer.get("state") if isinstance(answer.get("state"), dict) else None,
        attempt_id=str(answer.get("attempt_id", "") or ""),
    )

def send_quiz_with_retry(
    bot_token: str,
    chat_id: str,
    question: dict,
    *,
    timeout: int = 35,
    attempts: int = 3,
    progress: Callable[[int, TelegramError, float], None] | None = None,
    position: int | None = None,
    total: int | None = None,
    show_question_card: bool = True,
    native_explanation: bool = False,
) -> dict:
    return with_retry(
        lambda: send_quiz(
            bot_token,
            chat_id,
            question,
            timeout=timeout,
            position=position,
            total=total,
            show_question_card=show_question_card,
            native_explanation=native_explanation,
        ),
        attempts=attempts,
        progress=progress,
    )


def send_message(
    bot_token: str,
    chat_id: str,
    text: str,
    timeout: int = 30,
    reply_markup: dict | None = None,
    *,
    parse_mode: str = "",
    reply_to_message_id: int | None = None,
    disable_web_page_preview: bool = True,
) -> dict:
    token = bot_token.strip()
    target = str(chat_id).strip()
    if not token:
        raise ValueError("Token do bot não informado.")
    if not target:
        raise ValueError("Chat ID não informado.")
    chunks = _split_message(text)
    results: list[dict] = []
    for index, chunk in enumerate(chunks):
        payload: dict[str, str] = {"chat_id": target, "text": chunk}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if disable_web_page_preview:
            payload["disable_web_page_preview"] = "true"
        if reply_to_message_id is not None:
            payload["reply_parameters"] = json.dumps({"message_id": int(reply_to_message_id)}, ensure_ascii=False)
        if reply_markup is not None and index == len(chunks) - 1:
            payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        results.append(_post(token, "sendMessage", payload, timeout))
    return {"ok": True, "messages": results}


def study_menu_markup(extra_count: int = 5, cycle_count: int = 20, paused: bool = False) -> dict:
    pause_text = "▶️ Retomar fluxo" if paused else "⏸ Pausar fluxo"
    pause_data = "qf:resume" if paused else "qf:pause"
    return {
        "inline_keyboard": [
            [
                {"text": f"➕ Mais {max(1, extra_count)} questões", "callback_data": f"qf:more:{max(1, extra_count)}", "style": "success"},
                {"text": f"🔄 Novo ciclo ({max(1, cycle_count)})", "callback_data": f"qf:cycle:{max(1, cycle_count)}", "style": "primary"},
            ],
            [
                {"text": "📊 Meu desempenho", "callback_data": "qf:stats"},
                {"text": pause_text, "callback_data": pause_data, "style": "danger" if not paused else "success"},
            ],
        ]
    }


def send_study_menu(bot_token: str, chat_id: str, text: str, *, extra_count: int = 5, cycle_count: int = 20, paused: bool = False, timeout: int = 30) -> dict:
    return send_message(bot_token, chat_id, text, timeout=timeout, reply_markup=study_menu_markup(extra_count=extra_count, cycle_count=cycle_count, paused=paused))


def answer_callback_query(
    bot_token: str,
    callback_query_id: str,
    text: str = "",
    timeout: int = 20,
    *,
    show_alert: bool = False,
) -> dict:
    token = bot_token.strip()
    callback_id = str(callback_query_id).strip()
    if not token or not callback_id:
        raise ValueError("Token ou identificador do botão não informado.")
    payload: dict[str, str] = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text[:200]
    if show_alert:
        payload["show_alert"] = "true"
    return _post(token, "answerCallbackQuery", payload, timeout)


def get_me(bot_token: str, timeout: int = 20) -> dict:
    token = bot_token.strip()
    if not token:
        raise ValueError("Token do bot não informado.")
    return _post(token, "getMe", {}, timeout)


def get_webhook_info(bot_token: str, timeout: int = 20) -> dict:
    token = bot_token.strip()
    if not token:
        raise ValueError("Token do bot não informado.")
    return _post(token, "getWebhookInfo", {}, timeout)


def delete_webhook(bot_token: str, drop_pending_updates: bool = False, timeout: int = 20) -> dict:
    token = bot_token.strip()
    if not token:
        raise ValueError("Token do bot não informado.")
    return _post(token, "deleteWebhook", {"drop_pending_updates": "true" if drop_pending_updates else "false"}, timeout)


def get_updates(bot_token: str, offset: int | None = None, timeout: int = 25, allowed_updates: list[str] | None = None) -> list[dict]:
    token = bot_token.strip()
    if not token:
        raise ValueError("Token do bot não informado.")
    payload: dict[str, str | int] = {"timeout": max(0, min(int(timeout), 50)), "limit": 100}
    if offset is not None:
        payload["offset"] = int(offset)
    if allowed_updates is not None:
        payload["allowed_updates"] = json.dumps(allowed_updates, ensure_ascii=False)
    result = _post(token, "getUpdates", payload, timeout=max(10, int(timeout) + 10))
    updates = result.get("result", [])
    return updates if isinstance(updates, list) else []
