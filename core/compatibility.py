from __future__ import annotations

"""Relatório de compatibilidade do runtime sem dependências externas."""

import importlib.metadata
import platform
import sqlite3
import struct
import sys
from typing import Any

from app_shared import APP_VERSION

VALIDATED_PYTHON_MIN = (3, 11)
VALIDATED_PYTHON_MAX = (3, 13)
CONTROLLED_PYTHON = (3, 14)
MIN_SQLITE = (3, 24, 0)  # UPSERT / ON CONFLICT DO UPDATE, usado extensivamente.


def _version_tuple(text: str) -> tuple[int, ...]:
    values: list[int] = []
    for part in str(text).split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if not digits:
            break
        values.append(int(digits))
    return tuple(values)


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "não instalado"
    except Exception:
        return "indisponível"


def compatibility_report() -> dict[str, Any]:
    py = sys.version_info[:3]
    py_minor = py[:2]
    sqlite_version = _version_tuple(sqlite3.sqlite_version)
    python_supported = py >= VALIDATED_PYTHON_MIN
    python_validated = VALIDATED_PYTHON_MIN <= py_minor <= VALIDATED_PYTHON_MAX
    python_controlled = py_minor == CONTROLLED_PYTHON
    sqlite_supported = sqlite_version >= MIN_SQLITE
    warnings: list[str] = []
    if not python_supported:
        warnings.append("Python anterior a 3.11 não é suportado.")
    elif python_controlled:
        warnings.append(
            "Python 3.14 faz parte da matriz de validação controlada introduzida na 6.7.3 e preservada na 6.8.0, mas ainda não é o runtime preferencial de produção."
        )
    elif not python_validated:
        warnings.append("Esta versão do Python está fora da matriz validada/controlada da release.")
    if not sqlite_supported:
        warnings.append("SQLite muito antigo para os UPSERTs usados pelo QuestFlow.")

    accepted_python = python_validated or python_controlled
    ok = python_supported and accepted_python and sqlite_supported
    if not ok:
        status = "incompatível"
    elif python_controlled:
        status = "compatível_experimental"
    elif warnings:
        status = "compatível_com_aviso"
    else:
        status = "compatível"

    hardening: dict[str, Any]
    try:
        from core.production_hardening import verify_lock_integrity

        lock = verify_lock_integrity()
        hardening = {
            "dependency_lock": "válido" if lock["ok"] else "inválido",
            "dependency_lock_sha256": lock.get("sha256", ""),
            "sbom_supported": True,
            "safe_update_supported": True,
            "backup_restore_test_supported": True,
        }
    except Exception as error:
        hardening = {
            "dependency_lock": "indisponível",
            "detail": str(error),
            "sbom_supported": True,
            "safe_update_supported": True,
            "backup_restore_test_supported": True,
        }

    return {
        "ok": ok,
        "status": status,
        "app_version": APP_VERSION,
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "validated_range": "3.11–3.13",
            "controlled_experimental": "3.14",
            "supported": python_supported,
            "validated": python_validated,
            "controlled": python_controlled,
        },
        "sqlite": {
            "version": sqlite3.sqlite_version,
            "minimum": ".".join(map(str, MIN_SQLITE)),
            "supported": sqlite_supported,
            "thread_safety": sqlite3.threadsafety,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "bits": struct.calcsize("P") * 8,
        },
        "packages": {
            "fsrs": _package_version("fsrs"),
            "PyMuPDF": _package_version("PyMuPDF"),
            "Pillow": _package_version("Pillow"),
            "selenium": _package_version("selenium"),
        },
        "production_hardening": hardening,
        "warnings": warnings,
        "policy": (
            "Python 3.11–3.13 são a faixa validada. Python 3.14 é aceito apenas como validação controlada; "
            "dependências opcionais degradam de forma segura e o SQLite local permanece a autoridade dos dados."
        ),
    }


__all__ = [
    "CONTROLLED_PYTHON",
    "MIN_SQLITE",
    "VALIDATED_PYTHON_MAX",
    "VALIDATED_PYTHON_MIN",
    "compatibility_report",
]
