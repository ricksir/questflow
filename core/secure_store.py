from __future__ import annotations

"""Small Windows-DPAPI secret store used for cloud credentials.

QuestFlow never writes cloud/database tokens to config.json. On Windows the
payload is encrypted for the current Windows user with DPAPI. On non-Windows
systems (used by tests) persistence is deliberately disabled.
"""

import base64
import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path
from typing import Mapping


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes) -> tuple[_DataBlob, object | None]:
    if not data:
        return _DataBlob(0, None), None
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _protect(data: bytes, description: str) -> bytes:
    if os.name != "nt":
        raise OSError("DPAPI está disponível somente no Windows.")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.POINTER(_DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    source, keepalive = _blob(data)
    output = _DataBlob()
    ok = crypt32.CryptProtectData(ctypes.byref(source), description, None, None, None, 0, ctypes.byref(output))
    _ = keepalive
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        if output.pbData:
            kernel32.LocalFree(output.pbData)


def _unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise OSError("DPAPI está disponível somente no Windows.")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(_DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    source, keepalive = _blob(data)
    output = _DataBlob()
    description = ctypes.c_void_p()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(source), ctypes.byref(description), None, None, None, 0, ctypes.byref(output)
    )
    _ = keepalive
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        if output.pbData:
            kernel32.LocalFree(output.pbData)
        if description:
            kernel32.LocalFree(description)


def save_secret_map(path: str | Path, values: Mapping[str, str], *, description: str = "QuestFlow Secrets") -> None:
    target = Path(path)
    payload = json.dumps({str(k): str(v) for k, v in values.items()}, ensure_ascii=False).encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        # Never persist tokens as plain text outside the supported Windows runtime.
        target.write_text(json.dumps({"schema": 1, "protection": "unsupported", "data": ""}), encoding="utf-8")
        return
    encrypted = _protect(payload, description)
    envelope = {
        "schema": 1,
        "protection": "windows-dpapi",
        "data": base64.b64encode(encrypted).decode("ascii"),
    }
    target.write_text(json.dumps(envelope, separators=(",", ":")), encoding="utf-8")


def load_secret_map(path: str | Path) -> dict[str, str]:
    target = Path(path)
    if not target.exists() or os.name != "nt":
        return {}
    try:
        envelope = json.loads(target.read_text(encoding="utf-8"))
        if envelope.get("protection") != "windows-dpapi":
            return {}
        encrypted = base64.b64decode(str(envelope.get("data", "")))
        payload = json.loads(_unprotect(encrypted).decode("utf-8"))
        return {str(k): str(v) for k, v in payload.items()}
    except Exception:
        return {}


def clear_secret(path: str | Path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


__all__ = ["clear_secret", "load_secret_map", "save_secret_map"]
