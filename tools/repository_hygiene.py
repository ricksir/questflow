"""Fail fast when repository-only safety invariants are violated."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
MAX_TRACKED_FILE_BYTES = 10 * 1024 * 1024

FORBIDDEN_DIRECTORIES = {
    ".expo",
    ".venv",
    "backups",
    "build",
    "data",
    "dist",
    "logs",
    "node_modules",
    "outputs",
    "runtime",
    "venv",
    "work",
}

FORBIDDEN_EXTENSIONS = {
    ".aab",
    ".apk",
    ".db",
    ".jks",
    ".keystore",
    ".p12",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
    ".zip",
}

FORBIDDEN_FILENAMES = {
    "google-services.json",
    "googleservice-info.plist",
}


@dataclass(frozen=True)
class TrackedFile:
    mode: str
    path: str


def _tracked_files(root: Path) -> list[TrackedFile]:
    result = subprocess.run(
        ["git", "ls-files", "-s", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
        text=False,
    )
    entries: list[TrackedFile] = []
    for raw_entry in result.stdout.split(b"\0"):
        if not raw_entry:
            continue
        metadata, raw_path = raw_entry.split(b"\t", 1)
        mode = metadata.split(b" ", 1)[0].decode("ascii")
        entries.append(TrackedFile(mode=mode, path=raw_path.decode("utf-8")))
    return entries


def _path_problems(root: Path, files: Iterable[TrackedFile]) -> list[str]:
    problems: list[str] = []
    for entry in files:
        path = PurePosixPath(entry.path)
        folded_parts = {part.casefold() for part in path.parts[:-1]}
        filename = path.name.casefold()

        if entry.mode == "120000":
            problems.append(f"link simbólico versionado: {entry.path}")
        if folded_parts & FORBIDDEN_DIRECTORIES:
            problems.append(f"diretório local/gerado versionado: {entry.path}")
        if path.suffix.casefold() in FORBIDDEN_EXTENSIONS:
            problems.append(f"artefato ou dado persistente versionado: {entry.path}")
        if filename in FORBIDDEN_FILENAMES:
            problems.append(f"arquivo de credencial versionado: {entry.path}")
        if filename == ".env" or (filename.startswith(".env.") and filename != ".env.example"):
            problems.append(f"arquivo de ambiente versionado: {entry.path}")

        disk_path = root / Path(*path.parts)
        if disk_path.is_file() and disk_path.stat().st_size > MAX_TRACKED_FILE_BYTES:
            size_mb = disk_path.stat().st_size / (1024 * 1024)
            problems.append(f"arquivo versionado acima de 10 MiB ({size_mb:.1f} MiB): {entry.path}")
    return problems


def _version_problems(root: Path) -> list[str]:
    studio_version = (root / "VERSION.txt").read_text(encoding="utf-8").strip()
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((root / "mobile" / "package.json").read_text(encoding="utf-8"))
    app = json.loads((root / "mobile" / "app.json").read_text(encoding="utf-8"))["expo"]

    problems: list[str] = []
    if project["project"]["version"] != studio_version:
        problems.append("VERSION.txt e pyproject.toml divergem")
    if package["version"] != app["version"]:
        problems.append("mobile/package.json e mobile/app.json divergem")
    if not isinstance(app.get("android", {}).get("versionCode"), int):
        problems.append("mobile/app.json não possui android.versionCode inteiro")
    return problems


def _lock_problems(root: Path) -> list[str]:
    lock_path = root / "requirements.lock"
    checksum_path = root / "requirements.lock.sha256"
    expected = checksum_path.read_text(encoding="utf-8").strip().casefold()
    actual = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    if expected != actual:
        return ["requirements.lock.sha256 não corresponde a requirements.lock"]
    return []


def validate(root: Path = ROOT) -> list[str]:
    return [
        *_path_problems(root, _tracked_files(root)),
        *_version_problems(root),
        *_lock_problems(root),
    ]


def main() -> int:
    try:
        problems = validate()
    except (FileNotFoundError, KeyError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERRO: não foi possível validar a higiene do repositório: {exc}", file=sys.stderr)
        return 2

    if problems:
        print("Falha na higiene do repositório:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1

    print("Higiene do repositório validada: arquivos, versões e lock estão coerentes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

