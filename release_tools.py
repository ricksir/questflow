from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from app_shared import APP_VERSION, BASE_DIR
from core.production_hardening import (
    BackupPolicy,
    apply_retention_policy,
    compatibility_matrix_report,
    create_backup,
    generate_sbom,
    runtime_dependency_report,
    safe_apply_update,
    sha256_file,
    smoke_test,
    test_restore,
    verify_backup,
    verify_lock_integrity,
    vulnerability_audit,
)


def _print(payload: object, *, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    elif isinstance(payload, dict):
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(payload)


def command_lock(args: argparse.Namespace) -> int:
    report = verify_lock_integrity()
    if args.runtime:
        report["runtime"] = runtime_dependency_report()
    _print(report, as_json=args.json)
    return 0 if report["ok"] else 1


def command_sbom(args: argparse.Namespace) -> int:
    output = Path(args.output or (BASE_DIR / f"SBOM_{APP_VERSION}.cdx.json"))
    payload = generate_sbom(output)
    print(f"[OK] SBOM gerado: {output}")
    if args.json:
        _print(payload, as_json=True)
    return 0


def command_audit(args: argparse.Namespace) -> int:
    output = Path(args.output or (BASE_DIR / f"AUDITORIA_VULNERABILIDADES_{APP_VERSION}.json"))
    result = vulnerability_audit(strict=args.strict, output=output)
    _print(result, as_json=True)
    return 0 if result["ok"] else 1


def command_backup(args: argparse.Namespace) -> int:
    result = create_backup(label=args.label)
    verification = verify_backup(result.path)
    restore = test_restore(result.path) if args.test_restore else None
    if args.retention:
        retention = apply_retention_policy(
            policy=BackupPolicy(daily=args.daily, weekly=args.weekly, monthly=args.monthly)
        )
    else:
        retention = None
    payload = {
        "backup": asdict(result),
        "verification": verification,
        "restore_test": restore,
        "retention": retention,
    }
    _print(payload, as_json=True)
    return 0 if verification["ok"] and (restore is None or restore["ok"]) else 1


def command_restore_test(args: argparse.Namespace) -> int:
    result = test_restore(args.backup)
    _print(result, as_json=True)
    return 0 if result["ok"] else 1


def command_compat(args: argparse.Namespace) -> int:
    report = compatibility_matrix_report(run_smoke=not args.no_smoke)
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _print(report, as_json=True)
    failures = [row for row in report["matrix"] if row.get("available") and row.get("smoke") and not row["smoke"]["ok"]]
    return 1 if failures else 0


def command_smoke(args: argparse.Namespace) -> int:
    report = smoke_test(args.root or BASE_DIR)
    _print(report, as_json=True)
    return 0 if report["ok"] else 1


def _node_check() -> dict:
    node = shutil.which("node")
    target = BASE_DIR / "web" / "app.js"
    if not node:
        return {"ok": True, "status": "skipped", "detail": "Node.js não encontrado"}
    process = subprocess.run([node, "--check", str(target)], cwd=BASE_DIR, capture_output=True, text=True, check=False)
    return {
        "ok": process.returncode == 0,
        "status": "ok" if process.returncode == 0 else "failed",
        "detail": "\n".join(x.strip() for x in (process.stdout, process.stderr) if x.strip()),
    }


def _test_environment() -> dict[str, str]:
    return {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def _unit_tests(pattern: str, *, timeout_seconds: int = 120) -> dict:
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stream:
        try:
            process = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", pattern, "-q"],
                cwd=BASE_DIR,
                stdout=stream,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                timeout=timeout_seconds,
                env=_test_environment(),
            )
            returncode = process.returncode
            status = None
        except subprocess.TimeoutExpired:
            returncode = 124
            status = "timeout"
        stream.seek(0)
        detail = stream.read()[-12000:]
    payload = {"ok": returncode == 0, "returncode": returncode, "detail": detail}
    if status:
        payload.update({"status": status, "timeout_seconds": timeout_seconds})
    return payload


def _full_unit_tests_isolated(*, timeout_per_partition: int = 120, partitions: int = 4) -> dict:
    """Executa toda a suíte em partições determinísticas e processos isolados.

    A saída dos testes é descartada durante o caminho verde. Alguns testes de
    runtime iniciam processos auxiliares que se comportam mal quando stdout é
    capturado por PIPE/arquivo em certos ambientes Linux; DEVNULL evita que o
    próprio coletor de CI se torne a causa de um falso travamento.
    """
    pytest_available = importlib.util.find_spec("pytest") is not None
    skipped: list[dict[str, str]] = []
    modules: list[str] = []
    for path in sorted((BASE_DIR / "tests").glob("test_*.py")):
        if not path.is_file():
            continue
        if not pytest_available and "import pytest" in path.read_text(encoding="utf-8", errors="ignore"):
            skipped.append({"module": f"tests.{path.stem}", "reason": "pytest_not_installed"})
            continue
        modules.append(f"tests.{path.stem}")
    buckets = [modules[index::partitions] for index in range(partitions)]
    results: list[dict] = []
    for index, bucket in enumerate(buckets, start=1):
        if not bucket:
            continue
        try:
            process = subprocess.run(
                [sys.executable, "-m", "unittest", "-q", *bucket],
                cwd=BASE_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
                timeout=timeout_per_partition,
                env=_test_environment(),
            )
            returncode = process.returncode
            status = "ok" if returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            returncode = 124
            status = "timeout"
        item = {
            "partition": index,
            "modules": len(bucket),
            "ok": returncode == 0,
            "returncode": returncode,
            "status": status,
        }
        if status == "timeout":
            item["timeout_seconds"] = timeout_per_partition
        results.append(item)
    failures = [item for item in results if not item["ok"]]
    return {
        "ok": not failures,
        "strategy": "deterministic_partitions_devnull",
        "partitions": results,
        "modules": len(modules),
        "skipped": skipped,
        "failures": failures,
    }


def command_ci(args: argparse.Namespace) -> int:
    sbom_path = BASE_DIR / f"SBOM_{APP_VERSION}.cdx.json"
    audit_path = BASE_DIR / f"AUDITORIA_VULNERABILIDADES_{APP_VERSION}.json"
    matrix_path = BASE_DIR / f"MATRIZ_COMPATIBILIDADE_{APP_VERSION}.json"

    lock = verify_lock_integrity()
    smoke = smoke_test(BASE_DIR)
    node = _node_check()
    sbom = generate_sbom(sbom_path)
    audit = vulnerability_audit(strict=args.strict_audit, output=audit_path)
    matrix = compatibility_matrix_report(run_smoke=True)
    matrix_path.write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tests = _unit_tests("test_production_hardening_673.py")
    full_tests = _full_unit_tests_isolated() if args.full else {"ok": True, "status": "not_requested"}

    payload = {
        "app_version": APP_VERSION,
        "lock": lock,
        "smoke": smoke,
        "node": node,
        "sbom": {"ok": bool(sbom.get("components")), "path": str(sbom_path)},
        "audit": audit,
        "compatibility": {"path": str(matrix_path), "matrix": matrix["matrix"]},
        "tests": tests,
        "full_tests": full_tests,
    }
    ok = all(bool(item.get("ok")) for item in (lock, smoke, node, audit, tests, full_tests))
    payload["ok"] = ok
    _print(payload, as_json=True)
    return 0 if ok else 1


def command_update(args: argparse.Namespace) -> int:
    result = safe_apply_update(
        args.package,
        install_root=args.install_root,
        expected_sha256=args.sha256,
    )
    _print(result, as_json=True)
    return 0 if result["ok"] else 1


def command_hash(args: argparse.Namespace) -> int:
    print(sha256_file(args.path))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Ferramentas de hardening e release do QuestFlow Studio {APP_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("lock-check", help="Valida o lock exato e seu SHA-256")
    p.add_argument("--runtime", action="store_true", help="Compara também as versões instaladas")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=command_lock)

    p = sub.add_parser("sbom", help="Gera SBOM CycloneDX 1.5")
    p.add_argument("--output")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=command_sbom)

    p = sub.add_parser("audit", help="Executa pip-audit quando disponível")
    p.add_argument("--strict", action="store_true", help="Falha se pip-audit/rede não estiverem disponíveis")
    p.add_argument("--output")
    p.set_defaults(func=command_audit)

    p = sub.add_parser("backup", help="Cria e verifica backup consistente do diretório data")
    p.add_argument("--label", default="manual")
    p.add_argument("--test-restore", action="store_true")
    p.add_argument("--retention", action="store_true")
    p.add_argument("--daily", type=int, default=7)
    p.add_argument("--weekly", type=int, default=4)
    p.add_argument("--monthly", type=int, default=6)
    p.set_defaults(func=command_backup)

    p = sub.add_parser("restore-test", help="Testa restauração de um backup em área temporária")
    p.add_argument("backup")
    p.set_defaults(func=command_restore_test)

    p = sub.add_parser("compat", help="Executa a matriz 3.11–3.14 nos runtimes disponíveis")
    p.add_argument("--no-smoke", action="store_true")
    p.add_argument("--output")
    p.set_defaults(func=command_compat)

    p = sub.add_parser("smoke", help="Executa smoke test do pacote")
    p.add_argument("--root")
    p.set_defaults(func=command_smoke)

    p = sub.add_parser("ci", help="CI local/reprodutível da release")
    p.add_argument("--full", action="store_true", help="Executa toda a suíte unittest")
    p.add_argument("--strict-audit", action="store_true", help="Exige pip-audit funcional")
    p.set_defaults(func=command_ci)

    p = sub.add_parser("update", help="Aplica pacote com backup, staging, smoke e rollback")
    p.add_argument("package")
    p.add_argument("--install-root")
    p.add_argument("--sha256")
    p.set_defaults(func=command_update)

    p = sub.add_parser("sha256", help="Calcula SHA-256 de um arquivo")
    p.add_argument("path")
    p.set_defaults(func=command_hash)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
