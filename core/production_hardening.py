from __future__ import annotations

"""Production hardening helpers for QuestFlow 6.8.0 (introduced in 6.7.3).

The module intentionally depends only on the Python standard library so that
backup, rollback and release diagnostics remain available even when optional
application dependencies are broken.
"""

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app_shared import APP_NAME, APP_VERSION, BASE_DIR, DATA_DIR, DATABASE_PATH

LOCK_SCHEMA = "questflow.dependency-lock.v1"
BACKUP_SCHEMA = "questflow.backup.v1"
SBOM_SCHEMA = "CycloneDX-1.5"
UPDATE_SCHEMA = "questflow.safe-update.v1"

LOCK_FILE = BASE_DIR / "requirements.lock"
LOCK_HASH_FILE = BASE_DIR / "requirements.lock.sha256"


def _remove_tree(path: str | Path, *, ignore_errors: bool = False) -> None:
    """Remove a tree after clearing Windows read-only attributes when needed."""
    target = Path(path)
    if not target.exists():
        return

    def make_writable_and_retry(function, filename, _exc_info) -> None:
        try:
            os.chmod(filename, stat.S_IREAD | stat.S_IWRITE)
            function(filename)
        except FileNotFoundError:
            return
        except Exception:
            if not ignore_errors:
                raise

    shutil.rmtree(target, ignore_errors=ignore_errors, onerror=make_writable_and_retry)
BACKUP_ROOT = DATA_DIR / "backups"

# Python 3.14 is included in the automated matrix but remains controlled/
# experimental until the complete dependency stack is proven on that runtime.
COMPATIBILITY_MATRIX = (
    {"python": "3.11", "tier": "validated"},
    {"python": "3.12", "tier": "validated"},
    {"python": "3.13", "tier": "validated"},
    {"python": "3.14", "tier": "controlled_experimental"},
)


@dataclass(frozen=True)
class BackupPolicy:
    daily: int = 7
    weekly: int = 4
    monthly: int = 6


@dataclass(frozen=True)
class BackupResult:
    path: str
    created_at: str
    files: int
    databases: int
    manifest_sha256: str
    quick_check_ok: bool


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_distribution_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def parse_lock(path: str | Path | None = None) -> list[dict[str, str]]:
    target = Path(path or LOCK_FILE)
    entries: list[dict[str, str]] = []
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Extras are preserved in the display name, while package lookup strips them.
        if "==" not in line:
            raise ValueError(f"Entrada não exata no lock: {line}")
        name, version = line.split("==", 1)
        name = name.strip()
        version = version.strip()
        if not name or not version or any(ch in version for ch in "<>~,* "):
            raise ValueError(f"Entrada inválida no lock: {line}")
        lookup = name.split("[", 1)[0]
        entries.append(
            {
                "name": name,
                "lookup_name": lookup,
                "version": version,
                "entry": line,
                "entry_sha256": sha256_bytes(line.encode("utf-8")),
            }
        )
    if not entries:
        raise ValueError("requirements.lock está vazio")
    return entries


def verify_lock_integrity(
    lock_path: str | Path | None = None,
    hash_path: str | Path | None = None,
) -> dict[str, Any]:
    lock = Path(lock_path or LOCK_FILE)
    digest_file = Path(hash_path or LOCK_HASH_FILE)
    actual = sha256_file(lock)
    expected = digest_file.read_text(encoding="utf-8").strip().split()[0].lower()
    exact = parse_lock(lock)
    valid_hash = bool(expected) and actual.lower() == expected
    return {
        "ok": valid_hash,
        "schema": LOCK_SCHEMA,
        "path": str(lock),
        "sha256": actual,
        "expected_sha256": expected,
        "exact_entries": len(exact),
        "entries": exact,
        "error": "" if valid_hash else "SHA-256 do requirements.lock diverge do release hash",
    }


def runtime_dependency_report(lock_path: str | Path | None = None) -> dict[str, Any]:
    report = verify_lock_integrity(lock_path)
    rows: list[dict[str, Any]] = []
    all_match = report["ok"]
    for entry in report["entries"]:
        try:
            installed = importlib.metadata.version(entry["lookup_name"])
        except importlib.metadata.PackageNotFoundError:
            installed = None
        except Exception:
            installed = "indisponível"
        match = installed == entry["version"]
        rows.append({**entry, "installed": installed, "match": match})
        all_match = all_match and match
    return {"ok": all_match, "lock_ok": report["ok"], "packages": rows}


def generate_sbom(output: str | Path | None = None, *, lock_path: str | Path | None = None) -> dict[str, Any]:
    lock = verify_lock_integrity(lock_path)
    components = []
    for entry in lock["entries"]:
        components.append(
            {
                "type": "library",
                "name": entry["lookup_name"],
                "version": entry["version"],
                "purl": f"pkg:pypi/{entry['lookup_name']}@{entry['version']}",
                "properties": [
                    {"name": "questflow:lock-entry", "value": entry["entry"]},
                    {"name": "questflow:lock-entry-sha256", "value": entry["entry_sha256"]},
                ],
            }
        )
    payload = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{hashlib.sha256((APP_VERSION + lock['sha256']).encode()).hexdigest()[:32]}",
        "version": 1,
        "metadata": {
            "timestamp": utc_now(),
            "component": {"type": "application", "name": APP_NAME, "version": APP_VERSION},
            "properties": [
                {"name": "questflow:dependency-lock-sha256", "value": lock["sha256"]},
                {"name": "questflow:lock-integrity", "value": "valid" if lock["ok"] else "invalid"},
            ],
        },
        "components": components,
    }
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def sqlite_quick_check(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {"path": str(target), "ok": False, "detail": "arquivo ausente"}
    connection = None
    try:
        uri = target.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=15)
        row = connection.execute("PRAGMA quick_check(1)").fetchone()
        result = str(row[0] if row else "sem resultado")
        fk = connection.execute("PRAGMA foreign_key_check").fetchall()
        return {"path": str(target), "ok": result.lower() == "ok" and not fk, "detail": result, "foreign_key_violations": len(fk)}
    except Exception as error:
        return {"path": str(target), "ok": False, "detail": str(error), "foreign_key_violations": -1}
    finally:
        # sqlite3.Connection as a context manager commits/rolls back but does
        # not close the handle. On Windows that can keep restore-test files
        # locked and make TemporaryDirectory cleanup fail with WinError 32.
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def _backup_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    src = None
    dst = None
    try:
        src = sqlite3.connect(source, timeout=30)
        dst = sqlite3.connect(destination, timeout=30)
        src.execute("PRAGMA busy_timeout=30000")
        src.backup(dst)
        dst.commit()
    finally:
        # Explicit close is required for Windows-safe backup/restore tests.
        if dst is not None:
            try:
                dst.close()
            except Exception:
                pass
        if src is not None:
            try:
                src.close()
            except Exception:
                pass


def _backup_candidates(data_dir: Path) -> list[Path]:
    # Only persistent QuestFlow data belongs in a safety backup. Browser
    # profiles/runtimes are disposable working state and routinely contain
    # files locked by Chrome on Windows (WinError 32). Including them makes a
    # perfectly healthy database backup fail during the restore self-test.
    excluded_roots = {
        "backups", "runtime", "logs", "markdown_cache", "tmp", "temp",
        "google_browser_profile",
    }
    excluded_prefixes = ("chrome_runtime_", "browser_runtime_")
    result: list[Path] = []
    if not data_dir.exists():
        return result
    for path in data_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(data_dir)
        parts_lower = tuple(part.lower() for part in rel.parts)
        if parts_lower and parts_lower[0] in excluded_roots:
            continue
        if any(part.startswith(excluded_prefixes) for part in parts_lower):
            continue
        # Caches and transient journal/WAL files are rebuilt and should not be
        # restored over a clean SQLite backup.
        if path.suffix.lower() in {".wal", ".shm"} or path.name.endswith("-wal") or path.name.endswith("-shm"):
            continue
        result.append(path)
    return sorted(result)


def create_backup(
    *,
    data_dir: str | Path | None = None,
    backup_root: str | Path | None = None,
    label: str = "manual",
) -> BackupResult:
    source_root = Path(data_dir or DATA_DIR).resolve()
    root = Path(backup_root or BACKUP_ROOT).resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_label = "".join(ch for ch in label if ch.isalnum() or ch in "-_" )[:40] or "backup"
    destination = root / f"{stamp}_{safe_label}"
    counter = 1
    while destination.exists():
        destination = root / f"{stamp}_{safe_label}_{counter}"
        counter += 1
    payload_root = destination / "data"
    payload_root.mkdir(parents=True, exist_ok=False)

    manifest_files: list[dict[str, Any]] = []
    database_count = 0
    quick_ok = True
    for source in _backup_candidates(source_root):
        rel = source.relative_to(source_root)
        target = payload_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
            _backup_sqlite(source, target)
            database_count += 1
            check = sqlite_quick_check(target)
            quick_ok = quick_ok and bool(check["ok"])
        else:
            shutil.copy2(source, target)
            check = None
        manifest_files.append(
            {
                "path": rel.as_posix(),
                "size": target.stat().st_size,
                "sha256": sha256_file(target),
                "sqlite": check,
            }
        )

    manifest = {
        "schema": BACKUP_SCHEMA,
        "app": APP_NAME,
        "app_version": APP_VERSION,
        "created_at": utc_now(),
        "label": safe_label,
        "source_data_dir": str(source_root),
        "files": manifest_files,
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_sha = sha256_file(manifest_path)
    (destination / "manifest.sha256").write_text(manifest_sha + "\n", encoding="utf-8")
    return BackupResult(
        path=str(destination),
        created_at=manifest["created_at"],
        files=len(manifest_files),
        databases=database_count,
        manifest_sha256=manifest_sha,
        quick_check_ok=quick_ok,
    )


def verify_backup(backup_dir: str | Path) -> dict[str, Any]:
    root = Path(backup_dir)
    manifest_path = root / "manifest.json"
    hash_path = root / "manifest.sha256"
    if not manifest_path.exists() or not hash_path.exists():
        return {"ok": False, "error": "manifesto de backup ausente"}
    expected = hash_path.read_text(encoding="utf-8").strip().split()[0]
    actual = sha256_file(manifest_path)
    if expected != actual:
        return {"ok": False, "error": "hash do manifesto divergente", "expected": expected, "actual": actual}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    sqlite_checks: list[dict[str, Any]] = []
    for item in manifest.get("files", []):
        path = root / "data" / item["path"]
        if not path.exists():
            failures.append(f"ausente: {item['path']}")
            continue
        digest = sha256_file(path)
        if digest != item.get("sha256"):
            failures.append(f"hash divergente: {item['path']}")
        if item.get("sqlite") is not None:
            check = sqlite_quick_check(path)
            sqlite_checks.append(check)
            if not check["ok"]:
                failures.append(f"SQLite inválido: {item['path']}: {check['detail']}")
    return {"ok": not failures, "manifest": manifest, "failures": failures, "sqlite_checks": sqlite_checks}


def restore_backup(backup_dir: str | Path, destination_data_dir: str | Path, *, overwrite: bool = False) -> dict[str, Any]:
    verified = verify_backup(backup_dir)
    if not verified["ok"]:
        raise RuntimeError("Backup recusado: " + "; ".join(verified.get("failures") or [verified.get("error", "inválido")]))
    source = Path(backup_dir) / "data"
    destination = Path(destination_data_dir)
    if destination.exists() and any(destination.iterdir()) and not overwrite:
        raise FileExistsError("Destino de restauração não está vazio")
    destination.mkdir(parents=True, exist_ok=True)
    for file in source.rglob("*"):
        if not file.is_file():
            continue
        rel = file.relative_to(source)
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
    checks = [sqlite_quick_check(path) for path in destination.rglob("*") if path.is_file() and path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}]
    return {"ok": all(check["ok"] for check in checks), "destination": str(destination), "sqlite_checks": checks}


def test_restore(backup_dir: str | Path) -> dict[str, Any]:
    # Do not let a transient Windows file-handle delay turn a successful
    # restore validation into a failed application update. Restore first,
    # explicitly close all SQLite handles (sqlite_quick_check does that), then
    # clean the disposable directory with bounded retries.
    temp_root = Path(tempfile.mkdtemp(prefix="qf-restore-test-"))
    try:
        result = restore_backup(backup_dir, temp_root / "data")
        return {**result, "tested_at": utc_now(), "temporary": True}
    finally:
        import gc
        import time
        gc.collect()
        for attempt in range(5):
            try:
                shutil.rmtree(temp_root)
                break
            except FileNotFoundError:
                break
            except PermissionError:
                if attempt == 4:
                    # The restore result has already been verified. A temp-file
                    # cleanup delay is not evidence that the backup is invalid.
                    break
                time.sleep(0.25 * (attempt + 1))


def apply_retention_policy(backup_root: str | Path | None = None, policy: BackupPolicy | None = None) -> dict[str, Any]:
    root = Path(backup_root or BACKUP_ROOT)
    policy = policy or BackupPolicy()
    if not root.exists():
        return {"ok": True, "deleted": [], "kept": []}
    backups = [p for p in root.iterdir() if p.is_dir() and (p / "manifest.json").exists()]
    backups.sort(key=lambda p: p.name, reverse=True)

    keep: set[Path] = set()
    seen_days: set[str] = set()
    seen_weeks: set[str] = set()
    seen_months: set[str] = set()
    for path in backups:
        try:
            stamp = path.name.split("_", 1)[0]
            dt = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
        except ValueError:
            keep.add(path)
            continue
        day = dt.strftime("%Y-%m-%d")
        week = f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"
        month = dt.strftime("%Y-%m")
        if len(seen_days) < policy.daily and day not in seen_days:
            keep.add(path); seen_days.add(day); continue
        if len(seen_weeks) < policy.weekly and week not in seen_weeks:
            keep.add(path); seen_weeks.add(week); continue
        if len(seen_months) < policy.monthly and month not in seen_months:
            keep.add(path); seen_months.add(month); continue

    deleted: list[str] = []
    for path in backups:
        if path in keep:
            continue
        shutil.rmtree(path)
        deleted.append(str(path))
    return {"ok": True, "deleted": deleted, "kept": [str(path) for path in backups if path in keep], "policy": asdict(policy)}


def _safe_zip_members(archive: zipfile.ZipFile, destination: Path) -> Iterable[zipfile.ZipInfo]:
    # ZIP member names are POSIX-like regardless of the host OS. Validate them
    # lexically before combining them with a Windows destination. This avoids
    # both Zip Slip and ntpath errors such as "Can't mix absolute and relative
    # paths" when a malformed release accidentally contains C:\\... entries.
    from pathlib import PurePosixPath

    base = destination.resolve()
    for member in archive.infolist():
        raw = str(member.filename or "")
        normalized = raw.replace("\\", "/")
        pure = PurePosixPath(normalized)
        first = pure.parts[0] if pure.parts else ""
        if (
            not normalized
            or normalized.startswith("/")
            or ".." in pure.parts
            or ":" in first
            or raw.startswith("\\")
        ):
            raise ValueError(f"ZIP contém caminho inseguro: {raw}")
        candidate = (base / Path(*pure.parts)).resolve()
        try:
            candidate.relative_to(base)
        except ValueError as exc:
            raise ValueError(f"ZIP contém caminho inseguro: {raw}") from exc
        yield member


def _is_transient_update_member(filename: str) -> bool:
    """Return True for release entries that must never be unpacked as app code.

    Mobile dependency trees contain Apple frameworks and generated build files with
    very deep paths. On Windows, a normal staging prefix can push those entries to
    the legacy MAX_PATH boundary (260 chars), causing an otherwise valid update to
    fail before the package is even validated. These directories are disposable and
    are already preserved/restored by the QuestFlow Manager, so excluding them is
    both safer and substantially faster. The local ``data`` tree is also protected
    by safe_apply_update and does not belong in an application update payload.
    """
    from pathlib import PurePosixPath

    normalized = str(filename or "").replace("\\", "/").strip("/")
    parts = tuple(part.lower() for part in PurePosixPath(normalized).parts)
    if not parts:
        return False

    # Package may be wrapped in a top-level QuestFlow directory or may contain
    # files directly at its root. Only treat data as protected at that root level.
    logical = parts[1:] if parts[0].startswith("questflow") and len(parts) > 1 else parts
    if logical and logical[0] == "data":
        return True

    transient_names = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    if any(part in transient_names for part in logical):
        return True
    if logical and logical[-1].endswith((".pyc", ".pyo")):
        return True

    sequences = (
        ("mobile", "node_modules"),
        ("mobile", ".expo"),
        ("mobile", ".core-test-build"),
        ("mobile", "android", ".gradle"),
        ("mobile", "android", "app", "build"),
        ("mobile", "ios", "pods"),
        ("mobile", "ios", "build"),
    )
    for seq in sequences:
        width = len(seq)
        if any(logical[i : i + width] == seq for i in range(0, max(0, len(logical) - width + 1))):
            return True
    return False


def extract_update_zip(package_zip: str | Path, destination: str | Path) -> Path:
    package = Path(package_zip)
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package, "r") as archive:
        members = [
            member
            for member in _safe_zip_members(archive, target)
            if not _is_transient_update_member(member.filename)
        ]
        archive.extractall(target, members=members)
    children = [p for p in target.iterdir() if not p.name.startswith(".")]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return target


def smoke_test(root: str | Path | None = None, *, python_executable: str | None = None) -> dict[str, Any]:
    target = Path(root or BASE_DIR)
    python = python_executable or sys.executable
    commands = [
        [python, "-m", "compileall", "-q", "core", "app_shared.py", "web_api.py", "installer.py", "release_tools.py"],
        [python, "-c", "import app_shared, sqlite3; assert app_shared.APP_VERSION; print(app_shared.APP_VERSION)"],
    ]
    results = []
    ok = True
    for command in commands:
        process = subprocess.run(command, cwd=target, capture_output=True, text=True, check=False)
        detail = "\n".join(part.strip() for part in (process.stdout, process.stderr) if part.strip())
        results.append({"command": command, "returncode": process.returncode, "detail": detail[-4000:]})
        ok = ok and process.returncode == 0
    db = target / "data" / DATABASE_PATH.name
    db_check = sqlite_quick_check(db) if db.exists() else {"ok": True, "detail": "sem banco no pacote de teste", "path": str(db)}
    ok = ok and bool(db_check["ok"])
    return {"ok": ok, "commands": results, "database": db_check, "tested_at": utc_now()}


def discover_python_runtimes() -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for item in COMPATIBILITY_MATRIX:
        version = item["python"]
        candidates: list[list[str]] = []
        if os.name == "nt":
            candidates.append(["py", f"-{version}"])
        candidates.extend([[f"python{version}"], [f"python{version}.exe"]])
        resolved = None
        for command in candidates:
            try:
                process = subprocess.run(command + ["-c", "import sys; print(sys.executable)"], capture_output=True, text=True, check=False, timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                continue
            if process.returncode == 0 and process.stdout.strip():
                resolved = process.stdout.strip().splitlines()[-1]
                break
        found.append({**item, "executable": resolved, "available": bool(resolved)})
    return found


def compatibility_matrix_report(root: str | Path | None = None, *, run_smoke: bool = True) -> dict[str, Any]:
    target = Path(root or BASE_DIR)
    rows = []
    for runtime in discover_python_runtimes():
        row = dict(runtime)
        if runtime["available"] and run_smoke:
            row["smoke"] = smoke_test(target, python_executable=runtime["executable"])
        else:
            row["smoke"] = None
        rows.append(row)
    return {
        "app_version": APP_VERSION,
        "generated_at": utc_now(),
        "current_python": platform.python_version(),
        "matrix": rows,
        "policy": "3.11–3.13 validados; 3.14 é validação controlada/experimental até a pilha completa passar no CI.",
    }


def _snapshot_application(root: Path, destination: Path) -> None:
    excluded = {".venv", "venv", "data", "backups", "runtime", "__pycache__", ".git"}
    destination.mkdir(parents=True, exist_ok=False)
    for item in root.iterdir():
        if item.name in excluded:
            continue
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        elif item.is_file():
            shutil.copy2(item, target)


def _restore_application_snapshot(snapshot: Path, root: Path) -> None:
    excluded = {"data", ".venv", "venv", "backups", "runtime", ".git"}
    for item in list(root.iterdir()):
        if item.name in excluded:
            continue
        if item.is_dir():
            _remove_tree(item)
        else:
            item.unlink()
    for item in snapshot.iterdir():
        target = root / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def safe_apply_update(
    package_zip: str | Path,
    *,
    install_root: str | Path | None = None,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Apply an update with staging, backup, quick_check, smoke test and rollback.

    This function must be executed by the external updater after the QuestFlow UI
    has closed. The ``data`` directory is never overwritten by package contents.
    """
    package = Path(package_zip).resolve()
    root = Path(install_root or BASE_DIR).resolve()
    installed_version_file = root / "VERSION.txt"
    from_version = (installed_version_file.read_text(encoding="utf-8").strip() if installed_version_file.exists() else APP_VERSION)
    if expected_sha256:
        actual = sha256_file(package)
        if actual.lower() != expected_sha256.lower():
            raise ValueError("Hash SHA-256 do pacote de atualização não confere")

    root.parent.mkdir(parents=True, exist_ok=True)
    update_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    workspace = root.parent / f".{root.name}.update-{update_id}"
    rollback_dir = root.parent / f".{root.name}.rollback-{update_id}"
    if workspace.exists(): _remove_tree(workspace)
    if rollback_dir.exists(): _remove_tree(rollback_dir)

    # Keep pre-update backups outside the installation data tree. Besides
    # avoiding recursive backups, this uses a shorter Windows path and avoids
    # WinError 123/legacy path handling observed when QuestFlow is extracted
    # under deeply nested Downloads folders.
    pre_update_backup_root = root.parent / "QuestFlow_Backups"
    try:
        pre_update_backup_root.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Last-resort Windows-safe location. tempfile is already imported and
        # resolves to the current user's writable temporary directory.
        pre_update_backup_root = Path(tempfile.gettempdir()) / "QuestFlow_Backups"
        pre_update_backup_root.mkdir(parents=True, exist_ok=True)
    backup = create_backup(
        data_dir=root / "data",
        backup_root=pre_update_backup_root,
        label=f"pre-update-{update_id}",
    )
    if not backup.quick_check_ok:
        raise RuntimeError("Atualização abortada: backup prévio contém SQLite inválido")

    try:
        staged = extract_update_zip(package, workspace)
        version_file = staged / "VERSION.txt"
        if not version_file.exists():
            raise RuntimeError("Pacote de atualização sem VERSION.txt")
        new_version = version_file.read_text(encoding="utf-8").strip()
        if not new_version:
            raise RuntimeError("VERSION.txt vazio")
        staged_smoke = smoke_test(staged)
        if not staged_smoke["ok"]:
            raise RuntimeError("Smoke test do pacote em staging falhou")

        _snapshot_application(root, rollback_dir)
        # Replace application code, while preserving local data/venv/runtime.
        for item in staged.iterdir():
            if item.name in {"data", ".venv", "venv", "runtime", "backups"}:
                continue
            target = root / item.name
            if target.exists():
                if target.is_dir(): _remove_tree(target)
                else: target.unlink()
            if item.is_dir(): shutil.copytree(item, target)
            else: shutil.copy2(item, target)

        db_check = sqlite_quick_check(root / "data" / DATABASE_PATH.name)
        if (root / "data" / DATABASE_PATH.name).exists() and not db_check["ok"]:
            raise RuntimeError(f"quick_check pós-atualização falhou: {db_check['detail']}")
        installed_smoke = smoke_test(root)
        if not installed_smoke["ok"]:
            raise RuntimeError("Smoke test pós-atualização falhou")
        restore_test = test_restore(backup.path)
        if not restore_test["ok"]:
            raise RuntimeError("Teste de restauração do backup prévio falhou")
        _remove_tree(rollback_dir, ignore_errors=True)
        _remove_tree(workspace, ignore_errors=True)
        return {
            "ok": True,
            "schema": UPDATE_SCHEMA,
            "from_version": from_version,
            "to_version": new_version,
            "backup": asdict(backup),
            "database": db_check,
            "smoke": installed_smoke,
            "restore_test": restore_test,
            "rollback_performed": False,
        }
    except Exception as error:
        if rollback_dir.exists():
            _restore_application_snapshot(rollback_dir, root)
        # Data was preserved in place; restore only if quick_check is bad.
        db_path = root / "data" / DATABASE_PATH.name
        check = sqlite_quick_check(db_path) if db_path.exists() else {"ok": True}
        if not check.get("ok"):
            restore_backup(backup.path, root / "data", overwrite=True)
        _remove_tree(workspace, ignore_errors=True)
        _remove_tree(rollback_dir, ignore_errors=True)
        return {
            "ok": False,
            "schema": UPDATE_SCHEMA,
            "error": str(error),
            "backup": asdict(backup),
            "rollback_performed": True,
        }


def vulnerability_audit(*, strict: bool = False, output: str | Path | None = None) -> dict[str, Any]:
    """Run pip-audit when available.

    The release remains offline-first: diagnostics never download or install an
    auditor silently. CI can use ``strict=True`` to require the audit tool and a
    successful advisory query in a connected build environment.
    """
    command = [sys.executable, "-m", "pip_audit", "-r", str(LOCK_FILE), "-f", "json"]
    try:
        probe = subprocess.run([sys.executable, "-c", "import pip_audit"], capture_output=True, text=True, check=False)
    except OSError as error:
        probe = None
        unavailable = str(error)
    else:
        unavailable = "pip-audit não instalado"
    if probe is None or probe.returncode != 0:
        result = {
            "ok": not strict,
            "status": "unavailable",
            "strict": strict,
            "detail": unavailable,
            "command": command,
            "generated_at": utc_now(),
        }
    else:
        process = subprocess.run(command, cwd=BASE_DIR, capture_output=True, text=True, check=False, timeout=180)
        raw = process.stdout.strip()
        try:
            findings = json.loads(raw) if raw else []
        except json.JSONDecodeError:
            findings = []
        result = {
            "ok": process.returncode == 0,
            "status": "clean" if process.returncode == 0 else "findings_or_error",
            "strict": strict,
            "returncode": process.returncode,
            "findings": findings,
            "detail": process.stderr.strip()[-4000:],
            "command": command,
            "generated_at": utc_now(),
        }
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


__all__ = [
    "BackupPolicy", "BackupResult", "COMPATIBILITY_MATRIX", "LOCK_FILE", "LOCK_HASH_FILE",
    "apply_retention_policy", "compatibility_matrix_report", "create_backup", "extract_update_zip",
    "generate_sbom", "parse_lock", "restore_backup", "runtime_dependency_report", "safe_apply_update",
    "sha256_file", "smoke_test", "sqlite_quick_check", "test_restore", "verify_backup",
    "verify_lock_integrity", "vulnerability_audit",
]
