from __future__ import annotations

"""Protected Telegram credential handling.

The bot token is kept in memory for the running process because the Flow
engine expects it in the runtime config, but it is never persisted in
``config.json``. On Windows the token is protected with DPAPI. Legacy clear
text tokens are migrated on startup.
"""

from pathlib import Path

from .secure_store import clear_secret, load_secret_map, save_secret_map


def secret_path_for_config(config_path: str | Path) -> Path:
    return Path(config_path).resolve().parent / "telegram_credentials.dat"


def load_telegram_token(config_path: str | Path) -> str:
    try:
        return str(load_secret_map(secret_path_for_config(config_path)).get("bot_token") or "")
    except Exception:
        return ""


def save_telegram_token(config_path: str | Path, token: str) -> None:
    value = str(token or "").strip()
    target = secret_path_for_config(config_path)
    if not value:
        clear_secret(target)
        return
    save_secret_map(target, {"bot_token": value}, description="QuestFlow Telegram Bot Token")


def hydrate_and_migrate(config: dict, config_path: str | Path) -> dict:
    """Return runtime config with token hydrated and legacy clear text migrated.

    On non-Windows test environments the DPAPI store intentionally does not
    persist secrets. The legacy token therefore stays available in memory for
    the current process, while callers still remove it before writing JSON.
    """
    legacy = str(config.get("telegram_bot_token") or "").strip()
    protected = load_telegram_token(config_path)
    token = protected or legacy
    if legacy and not protected:
        try:
            save_telegram_token(config_path, legacy)
        except Exception:
            pass
    config["telegram_bot_token"] = token
    return config


__all__ = [
    "hydrate_and_migrate",
    "load_telegram_token",
    "save_telegram_token",
    "secret_path_for_config",
]
