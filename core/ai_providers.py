from __future__ import annotations

import base64
import json
from pathlib import Path
import random
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

from .network import network_urlopen
from .rate_limiter import acquire_external_slot
from .secure_store import clear_secret, load_secret_map, save_secret_map

PROVIDER_META = {
    "local": {"label": "QuestFlow local (RAG)", "requires_key": False, "requires_model": False},
    "google_ai_mode": {"label": "Google Modo IA (navegador)", "requires_key": False, "requires_model": False},
    "openai": {"label": "OpenAI / ChatGPT API", "requires_key": True, "requires_model": True, "model_placeholder": "Ex.: modelo disponível na sua conta OpenAI"},
    "gemini": {"label": "Google Gemini API", "requires_key": True, "requires_model": True, "model_placeholder": "Ex.: gemini-3.6-flash"},
    "anthropic": {"label": "Anthropic Claude API", "requires_key": True, "requires_model": True, "model_placeholder": "Ex.: modelo Claude disponível na sua conta"},
}




def _prepare_inline_attachments(attachments: list[dict] | None, *, max_total_bytes: int = 18 * 1024 * 1024) -> list[dict]:
    prepared: list[dict] = []
    total = 0
    for raw in attachments or []:
        if not isinstance(raw, dict):
            continue
        path = Path(str(raw.get("path") or ""))
        if not path.is_file():
            continue
        kind = str(raw.get("kind") or ("pdf" if path.suffix.lower() == ".pdf" else "image")).casefold()
        mime_type = str(raw.get("mime_type") or "").strip() or ("application/pdf" if kind == "pdf" else "application/octet-stream")
        if kind not in {"image", "pdf"}:
            continue
        size = int(path.stat().st_size)
        if size <= 0:
            continue
        total += size
        if total > max_total_bytes:
            raise ValueError("As mídias selecionadas excedem o limite seguro de 18 MB por chamada multimodal do QuestFlow.")
        prepared.append({
            "kind": kind,
            "name": path.name,
            "mime_type": mime_type,
            "size_bytes": size,
            "data": base64.b64encode(path.read_bytes()).decode("ascii"),
        })
    return prepared

def _secret_path(config_path: str | Path) -> Path:
    return Path(config_path).resolve().parent / "ai_provider_credentials.dat"


def load_keys(config_path: str | Path) -> dict[str, str]:
    try:
        return {str(k): str(v) for k, v in load_secret_map(_secret_path(config_path)).items() if str(v)}
    except Exception:
        return {}


def save_keys(config_path: str | Path, updates: dict[str, str], *, clear: list[str] | None = None) -> None:
    current = load_keys(config_path)
    for name in clear or []:
        current.pop(str(name), None)
    for name, value in (updates or {}).items():
        if str(value or ""):
            current[str(name)] = str(value)
    target = _secret_path(config_path)
    if current:
        save_secret_map(target, current, description="QuestFlow AI Provider API Keys")
    else:
        clear_secret(target)


def public_settings(config: dict, config_path: str | Path) -> dict:
    keys = load_keys(config_path)
    providers = []
    for pid, meta in PROVIDER_META.items():
        providers.append({"id": pid, **meta, "configured": (not meta.get("requires_key")) or bool(keys.get(pid))})
    return {
        "active_provider": str(config.get("ai_active_provider") or "local"),
        "models": {
            "openai": str(config.get("ai_openai_model") or ""),
            "gemini": str(config.get("ai_gemini_model") or "gemini-3.6-flash"),
            "anthropic": str(config.get("ai_anthropic_model") or ""),
        },
        "providers": providers,
        "keys_configured": {pid: bool(keys.get(pid)) for pid in ("openai", "gemini", "anthropic")},
        "pricing": {pid: {
            "input_per_million": float(config.get(f"ai_cost_{pid}_input_per_million") or 0),
            "output_per_million": float(config.get(f"ai_cost_{pid}_output_per_million") or 0),
        } for pid in ("openai", "gemini", "anthropic")},
        "capabilities": {pid: provider_capabilities(pid, str(config.get(f"ai_{pid}_model") or "")) for pid in ("openai", "gemini", "anthropic")},
        "security": "As chaves são armazenadas no Windows com DPAPI e não são gravadas no config.json.",
        "privacy": "OpenAI e Gemini são chamados em modo stateless (store=false); o Centro de Privacidade controla os campos enviados.",
    }


def _retry_delay(error: BaseException, attempt: int) -> float:
    retry_after = None
    if isinstance(error, HTTPError):
        try:
            retry_after = float(error.headers.get("Retry-After") or 0)
        except Exception:
            retry_after = None
    if retry_after and retry_after > 0:
        return min(12.0, retry_after)
    return min(8.0, (0.75 * (2 ** attempt)) + random.uniform(0.0, 0.35))


def _should_retry(error: BaseException) -> bool:
    if isinstance(error, HTTPError):
        return int(getattr(error, "code", 0) or 0) in {408, 409, 425, 429, 500, 502, 503, 504}
    return isinstance(error, (URLError, TimeoutError, ConnectionError, OSError))


def _post(
    url: str,
    payload: dict,
    headers: dict[str, str],
    *,
    config: dict,
    timeout: int = 60,
    attempts: int = 3,
    rate_limit_key: str = "",
) -> dict:
    """POST JSON with bounded exponential retry for transient failures.

    Retries occur only for rate limits, temporary server failures and network
    errors. Invalid credentials / malformed requests are returned immediately.
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if rate_limit_key:
        acquire_external_slot(config, rate_limit_key, timeout=min(15.0, max(2.0, float(timeout) / 4.0)), burst=6.0)
    last_error: BaseException | None = None
    for attempt in range(max(1, int(attempts))):
        req = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with network_urlopen(req, timeout=timeout, config=config) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except BaseException as error:
            last_error = error
            if attempt >= attempts - 1 or not _should_retry(error):
                raise
            time.sleep(_retry_delay(error, attempt))
    assert last_error is not None
    raise last_error


def _anthropic_supports_sampling(model: str) -> bool:
    """Claude 4.7+ / 5+ reject non-default temperature/top_p/top_k.

    Model ids have historically appeared both as ``claude-opus-4-7`` and
    aliases containing dots. Unknown future models default to the safer path of
    omitting sampling only when their version can be parsed as >= 4.7.
    """
    text = str(model or "").casefold().replace(".", "-")
    match = re.search(r"claude-(?:opus|sonnet|haiku|[a-z]+)-(\d+)(?:-(\d+))?", text)
    if not match:
        return True
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    return not (major >= 5 or (major == 4 and minor >= 7))


def _usage_from(provider: str, data: dict) -> dict[str, int]:
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    if provider == "openai":
        return {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "cache_read_tokens": int(((usage.get("input_tokens_details") or {}).get("cached_tokens")) or 0),
        }
    if provider == "anthropic":
        return {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "cache_read_tokens": int(usage.get("cache_read_input_tokens") or 0),
        }
    # Gemini Interactions / generateContent have used more than one usage shape.
    meta = usage or (data.get("usageMetadata") if isinstance(data.get("usageMetadata"), dict) else {})
    return {
        "input_tokens": int(meta.get("input_tokens") or meta.get("promptTokenCount") or meta.get("inputTokenCount") or 0),
        "output_tokens": int(meta.get("output_tokens") or meta.get("candidatesTokenCount") or meta.get("outputTokenCount") or 0),
        "cache_read_tokens": int(meta.get("cachedContentTokenCount") or 0),
    }


def estimate_cost(config: dict, provider: str, usage: dict) -> float | None:
    """Estimate USD cost only from user-configured rates; never hard-code prices."""
    try:
        inp = float(config.get(f"ai_cost_{provider}_input_per_million") or 0)
        out = float(config.get(f"ai_cost_{provider}_output_per_million") or 0)
    except Exception:
        return None
    if inp <= 0 and out <= 0:
        return None
    return round((float(usage.get("input_tokens") or 0) / 1_000_000.0) * inp + (float(usage.get("output_tokens") or 0) / 1_000_000.0) * out, 8)


def provider_capabilities(provider: str, model: str = "") -> dict[str, Any]:
    pid = str(provider or "local")
    return {
        "provider": pid,
        "model": str(model or ""),
        "rest": pid in {"openai", "gemini", "anthropic"},
        "stateless": pid in {"openai", "gemini"},
        "sampling_parameters": (pid != "anthropic") or _anthropic_supports_sampling(model),
        "retry": pid in {"openai", "gemini", "anthropic"},
        "structured_outputs": pid in {"openai", "gemini", "anthropic"},
        "multimodal_binary": pid in {"gemini", "anthropic"},
        "multimodal_images": pid in {"gemini", "anthropic"},
        "multimodal_pdf": pid in {"gemini", "anthropic"},
    }


def generate(provider: str, prompt: str, *, config: dict, config_path: str | Path, model: str = "", schema: dict | None = None, schema_name: str = "questflow_response", attachments: list[dict] | None = None) -> dict:
    provider = str(provider or "local")
    if provider in {"local", "google_ai_mode"}:
        raise ValueError("Este provedor não usa chamada REST direta.")
    keys = load_keys(config_path)
    key = keys.get(provider, "")
    if not key:
        raise ValueError(f"Chave da API não configurada para {PROVIDER_META.get(provider, {}).get('label', provider)}.")
    model = str(model or config.get(f"ai_{provider}_model") or "").strip()
    if not model:
        raise ValueError("Informe o modelo do provedor nas Configurações > Provedores de IA.")

    prepared_attachments = _prepare_inline_attachments(attachments) if attachments else []
    if prepared_attachments and not provider_capabilities(provider, model).get("multimodal_binary"):
        raise ValueError(f"O adaptador multimodal binário do provedor {provider} não está habilitado nesta versão do QuestFlow.")

    if provider == "openai":
        payload: dict[str, Any] = {"model": model, "input": prompt, "max_output_tokens": 1800, "store": False}
        if schema:
            payload["text"] = {"format": {"type": "json_schema", "name": str(schema_name or "questflow_response")[:64], "schema": schema, "strict": True}}
        started = time.perf_counter()
        data = _post(
            "https://api.openai.com/v1/responses",
            payload,
            {"Authorization": f"Bearer {key}"},
            config=config,
            rate_limit_key="ai:openai",
        )
        latency_ms = round((time.perf_counter() - started) * 1000.0, 1)
        text = str(data.get("output_text") or "").strip()
        if not text:
            parts = []
            for out in data.get("output", []) or []:
                for content in out.get("content", []) or []:
                    if isinstance(content, dict) and content.get("text"):
                        parts.append(str(content["text"]))
            text = "\n".join(parts).strip()
        usage = _usage_from(provider, data)
        structured = None
        if schema and text:
            structured = json.loads(text)
        return {
            "text": text, "structured": structured,
            "provider": "OpenAI API", "provider_id": provider,
            "model": model, "raw_id": data.get("id", ""),
            "privacy": "store=false", "usage": usage, "latency_ms": latency_ms,
            "estimated_cost_usd": estimate_cost(config, provider, usage),
            "structured_output": bool(schema),
        }

    if provider == "gemini":
        gemini_input: Any = prompt
        if prepared_attachments:
            gemini_input = [{"type": "text", "text": prompt}]
            for item in prepared_attachments:
                gemini_input.append({
                    "type": "document" if item["kind"] == "pdf" else "image",
                    "data": item["data"],
                    "mime_type": item["mime_type"],
                })
        payload: dict[str, Any] = {"model": model, "input": gemini_input, "store": False}
        if schema:
            payload["response_format"] = {"type": "text", "mime_type": "application/json", "schema": schema}
        else:
            payload["generation_config"] = {"temperature": 0.2}
        started = time.perf_counter()
        data = _post(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            payload,
            {"x-goog-api-key": key},
            config=config,
            rate_limit_key="ai:gemini",
        )
        latency_ms = round((time.perf_counter() - started) * 1000.0, 1)
        text = str(data.get("output_text") or "").strip()
        if not text:
            parts = []
            for step in data.get("steps", []) or []:
                if not isinstance(step, dict):
                    continue
                content_value = step.get("content")
                if isinstance(content_value, str):
                    parts.append(content_value)
                elif isinstance(content_value, list):
                    for content in content_value:
                        if isinstance(content, dict) and content.get("text"):
                            parts.append(str(content["text"]))
            text = "\n".join(parts).strip()
        usage = _usage_from(provider, data)
        structured = json.loads(text) if schema and text else None
        return {
            "text": text, "structured": structured,
            "provider": "Google Gemini API", "provider_id": provider,
            "model": model, "raw_id": str(data.get("id") or ""),
            "privacy": "store=false", "usage": usage, "latency_ms": latency_ms,
            "estimated_cost_usd": estimate_cost(config, provider, usage),
            "structured_output": bool(schema),
            "media_sent_count": len(prepared_attachments),
            "media_sent_bytes": sum(int(x.get("size_bytes", 0) or 0) for x in prepared_attachments),
        }

    if provider == "anthropic":
        anthropic_content: Any = prompt
        if prepared_attachments:
            blocks: list[dict[str, Any]] = []
            for item in prepared_attachments:
                blocks.append({
                    "type": "document" if item["kind"] == "pdf" else "image",
                    "source": {
                        "type": "base64",
                        "media_type": item["mime_type"],
                        "data": item["data"],
                    },
                })
            blocks.append({"type": "text", "text": prompt})
            anthropic_content = blocks
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": 1800,
            "messages": [{"role": "user", "content": anthropic_content}],
        }
        if _anthropic_supports_sampling(model):
            payload["temperature"] = 0.2
        if schema:
            payload["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        started = time.perf_counter()
        data = _post(
            "https://api.anthropic.com/v1/messages",
            payload,
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            config=config,
            rate_limit_key="ai:anthropic",
        )
        latency_ms = round((time.perf_counter() - started) * 1000.0, 1)
        text = "\n".join(
            str(item.get("text") or "")
            for item in data.get("content", []) or []
            if isinstance(item, dict) and item.get("type") == "text"
        ).strip()
        usage = _usage_from(provider, data)
        structured = json.loads(text) if schema and text else None
        return {
            "text": text, "structured": structured,
            "provider": "Anthropic Claude API", "provider_id": provider,
            "model": model, "raw_id": data.get("id", ""),
            "capabilities": provider_capabilities(provider, model),
            "usage": usage, "latency_ms": latency_ms,
            "estimated_cost_usd": estimate_cost(config, provider, usage),
            "structured_output": bool(schema),
            "media_sent_count": len(prepared_attachments),
            "media_sent_bytes": sum(int(x.get("size_bytes", 0) or 0) for x in prepared_attachments),
        }

    raise ValueError("Provedor de IA desconhecido.")


__all__ = [
    "PROVIDER_META",
    "generate",
    "load_keys",
    "estimate_cost",
    "provider_capabilities",
    "public_settings",
    "save_keys",
]
