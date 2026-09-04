from __future__ import annotations

"""Rate limiting local e thread-safe para integrações externas do QuestFlow.

O objetivo é proteger provedores/serviços contra rajadas acidentais sem criar
uma dependência externa. O limiter nunca é usado para o SQLite local.
"""

from dataclasses import dataclass
import threading
import time
from typing import Any


@dataclass(slots=True)
class RateLimitSnapshot:
    key: str
    rate_per_minute: float
    burst: float
    tokens: float
    waits: int
    rejected: int
    last_wait_seconds: float

    def public(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "rate_per_minute": round(self.rate_per_minute, 3),
            "burst": round(self.burst, 3),
            "available_tokens": round(self.tokens, 3),
            "waits": self.waits,
            "rejected": self.rejected,
            "last_wait_seconds": round(self.last_wait_seconds, 3),
        }


class TokenBucket:
    def __init__(self, key: str, *, rate_per_minute: float, burst: float | None = None) -> None:
        self.key = str(key)
        self._lock = threading.RLock()
        self.rate_per_minute = max(0.1, float(rate_per_minute))
        self.burst = max(1.0, float(burst if burst is not None else max(2.0, self.rate_per_minute / 6.0)))
        self._tokens = self.burst
        self._updated = time.monotonic()
        self._waits = 0
        self._rejected = 0
        self._last_wait = 0.0

    def configure(self, *, rate_per_minute: float, burst: float | None = None) -> None:
        with self._lock:
            self._refill_locked()
            self.rate_per_minute = max(0.1, float(rate_per_minute))
            if burst is not None:
                self.burst = max(1.0, float(burst))
                self._tokens = min(self._tokens, self.burst)

    def _refill_locked(self) -> None:
        now = time.monotonic()
        elapsed = max(0.0, now - self._updated)
        self._updated = now
        per_second = self.rate_per_minute / 60.0
        self._tokens = min(self.burst, self._tokens + elapsed * per_second)

    def acquire(self, *, tokens: float = 1.0, timeout: float = 15.0) -> float:
        needed = max(0.01, float(tokens))
        deadline = time.monotonic() + max(0.0, float(timeout))
        total_wait = 0.0
        while True:
            with self._lock:
                self._refill_locked()
                if self._tokens >= needed:
                    self._tokens -= needed
                    self._last_wait = total_wait
                    if total_wait > 0:
                        self._waits += 1
                    return total_wait
                per_second = self.rate_per_minute / 60.0
                wait_for = (needed - self._tokens) / max(0.001, per_second)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                with self._lock:
                    self._rejected += 1
                    self._last_wait = total_wait
                raise TimeoutError(f"Rate limit de {self.key} excedido; tente novamente em instantes.")
            sleep_for = min(max(0.01, wait_for), remaining, 1.0)
            time.sleep(sleep_for)
            total_wait += sleep_for

    def snapshot(self) -> RateLimitSnapshot:
        with self._lock:
            self._refill_locked()
            return RateLimitSnapshot(
                key=self.key,
                rate_per_minute=self.rate_per_minute,
                burst=self.burst,
                tokens=self._tokens,
                waits=self._waits,
                rejected=self._rejected,
                last_wait_seconds=self._last_wait,
            )


class RateLimiterRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._buckets: dict[str, TokenBucket] = {}

    def bucket(self, key: str, *, rate_per_minute: float, burst: float | None = None) -> TokenBucket:
        name = str(key)
        with self._lock:
            bucket = self._buckets.get(name)
            if bucket is None:
                bucket = TokenBucket(name, rate_per_minute=rate_per_minute, burst=burst)
                self._buckets[name] = bucket
            else:
                bucket.configure(rate_per_minute=rate_per_minute, burst=burst)
            return bucket

    def acquire(self, key: str, *, rate_per_minute: float, burst: float | None = None, timeout: float = 15.0) -> float:
        return self.bucket(key, rate_per_minute=rate_per_minute, burst=burst).acquire(timeout=timeout)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            buckets = list(self._buckets.values())
        return [item.snapshot().public() for item in sorted(buckets, key=lambda x: x.key)]


_GLOBAL_REGISTRY = RateLimiterRegistry()


def _rate_from_config(config: dict, key: str) -> float:
    defaults = {
        "ai:openai": 30.0,
        "ai:gemini": 30.0,
        "ai:anthropic": 30.0,
        "turso": 120.0,
        "update_monitor": 30.0,
        "telegram": 50.0 * 60.0,  # capacidade local alta; Telegram ainda aplica os próprios limites.
    }
    config_keys = {
        "ai:openai": "ai_rate_limit_per_minute",
        "ai:gemini": "ai_rate_limit_per_minute",
        "ai:anthropic": "ai_rate_limit_per_minute",
        "turso": "cloud_rate_limit_per_minute",
        "update_monitor": "update_monitor_rate_limit_per_minute",
        "telegram": "telegram_rate_limit_per_minute",
    }
    try:
        return max(0.1, float(config.get(config_keys.get(key, ""), defaults.get(key, 60.0)) or defaults.get(key, 60.0)))
    except Exception:
        return defaults.get(key, 60.0)


def acquire_external_slot(config: dict, key: str, *, timeout: float = 15.0, burst: float | None = None) -> float:
    return _GLOBAL_REGISTRY.acquire(
        key,
        rate_per_minute=_rate_from_config(config, key),
        burst=burst,
        timeout=timeout,
    )


def rate_limit_status() -> list[dict[str, Any]]:
    return _GLOBAL_REGISTRY.snapshot()


__all__ = [
    "RateLimiterRegistry",
    "TokenBucket",
    "acquire_external_slot",
    "rate_limit_status",
]
