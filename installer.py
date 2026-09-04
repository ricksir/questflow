from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "QuestFlow Studio"
MARKER_SCHEMA = "questflow.dependencies.v3"
MODULES = (
    "pymupdf",
    "PIL",
    "pytesseract",
    "cv2",
    "pymupdf4llm",
    "selenium",
    "fsrs",
)
OPTIONAL_PACKAGES: dict[str, str] = {}


@dataclass(frozen=True)
class DependencyState:
    requirements_hash: str
    python_version: str
    python_executable: str
    lock_verified: bool = True


def project_root() -> Path:
    return Path(__file__).resolve().parent


def requirements_path() -> Path:
    locked = project_root() / "requirements.lock"
    return locked if locked.exists() else project_root() / "requirements.txt"


def verify_dependency_lock() -> tuple[bool, str]:
    lock = project_root() / "requirements.lock"
    digest = project_root() / "requirements.lock.sha256"
    if not lock.exists() or not digest.exists():
        return False, "requirements.lock ou requirements.lock.sha256 ausente"
    try:
        expected = digest.read_text(encoding="utf-8").strip().split()[0].lower()
        actual = hashlib.sha256(lock.read_bytes()).hexdigest().lower()
        exact_lines = [
            line.strip() for line in lock.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except OSError as error:
        return False, str(error)
    if not expected or expected != actual:
        return False, "SHA-256 do requirements.lock não confere"
    if not exact_lines or any("==" not in line for line in exact_lines):
        return False, "requirements.lock contém dependência não fixada exatamente"
    return True, ""


def marker_path() -> Path:
    return Path(sys.prefix) / ".questflow_dependencies.json"


def requirements_hash(path: Path | None = None) -> str:
    target = path or requirements_path()
    content = target.read_bytes()
    return hashlib.sha256(content).hexdigest()


def current_state() -> DependencyState:
    return DependencyState(
        requirements_hash=requirements_hash(),
        python_version=".".join(str(value) for value in sys.version_info[:3]),
        python_executable=str(Path(sys.executable).resolve()),
        lock_verified=verify_dependency_lock()[0],
    )


def read_marker(path: Path | None = None) -> dict:
    target = path or marker_path()
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_marker(state: DependencyState, path: Path | None = None) -> None:
    target = path or marker_path()
    payload = {
        "schema": MARKER_SCHEMA,
        "requirements_hash": state.requirements_hash,
        "python_version": state.python_version,
        "python_executable": state.python_executable,
        "lock_verified": state.lock_verified,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def marker_matches(state: DependencyState, payload: dict | None = None) -> bool:
    marker = payload if payload is not None else read_marker()
    return bool(
        marker.get("schema") == MARKER_SCHEMA
        and marker.get("requirements_hash") == state.requirements_hash
        and marker.get("python_version") == state.python_version
        and marker.get("python_executable") == state.python_executable
        and bool(marker.get("lock_verified")) == state.lock_verified
        and state.lock_verified
    )


def import_check() -> tuple[bool, str]:
    failures: list[str] = []
    for module_name in MODULES:
        try:
            module = importlib.import_module(module_name)
            if module_name == "fsrs":
                required = ("Scheduler", "Card", "Rating", "ReviewLog", "Optimizer")
                missing = [name for name in required if not hasattr(module, name)]
                if missing:
                    raise RuntimeError("Py-FSRS sem componentes obrigatórios: " + ", ".join(missing))
                version = str(getattr(module, "__version__", ""))
                if version and version != "6.3.2":
                    raise RuntimeError(f"Py-FSRS {version} encontrado; esta versão foi validada com 6.3.2")
        except Exception as error:  # pragma: no cover - text is user-facing
            failures.append(f"{module_name}: {error}")
    if failures:
        return False, "; ".join(failures)
    return True, ""


def pip_check() -> tuple[bool, str]:
    process = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        cwd=project_root(),
        text=True,
        capture_output=True,
        env=_pip_environment(),
        check=False,
    )
    detail = "\n".join(part.strip() for part in (process.stdout, process.stderr) if part.strip())
    return process.returncode == 0, detail


def runtime_root() -> Path:
    """Diretório curto e compartilhado para artefatos pesados do runtime.

    No Windows, pacotes como PyTorch possuem árvores internas muito profundas.
    Manter venv/cache dentro de uma pasta extraída em Downloads pode ultrapassar
    o limite legado de caminhos do sistema. Os BATs definem QF_RUNTIME_ROOT para
    %LOCALAPPDATA%\\QFS; este fallback mantém o instalador seguro quando executado
    diretamente.
    """
    configured = str(os.environ.get("QF_RUNTIME_ROOT", "") or "").strip()
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        local = str(os.environ.get("LOCALAPPDATA", "") or "").strip()
        if local:
            return Path(local) / "QFS"
    return project_root() / "data" / "runtime"


def _pip_environment() -> dict[str, str]:
    environment = os.environ.copy()
    cache_dir = runtime_root() / "pip-cache"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        # O pip ainda pode usar seu cache padrão caso a pasta não possa ser criada.
        pass
    environment.update(
        {
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            # 5.7.1: cache fora da pasta extraída e em caminho curto. Além de
            # reduzir downloads repetidos, evita somar o nome longo do projeto
            # aos caminhos internos de wheels grandes (notadamente PyTorch).
            "PIP_CACHE_DIR": str(cache_dir),
        }
    )
    try:
        from core.network import proxy_environment

        environment.update(proxy_environment())
    except Exception:
        # O instalador precisa continuar utilizável mesmo se a configuração de
        # rede ainda não tiver sido criada. Nesse caso o pip usa o ambiente do
        # Windows/processo como antes.
        pass
    return environment


def pip_install_command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--progress-bar",
        "off",
        "--quiet",
        "-r",
        str(requirements_path()),
    ]


def _friendly_install_detail(detail: str) -> str:
    text = str(detail or "")
    lowered = text.lower()
    long_path_signals = (
        "long path support",
        "enable-long-paths",
        "mem_eff_attention",
        "no such file or directory",
    )
    if any(signal in lowered for signal in long_path_signals) and (
        "torch" in lowered or "site-packages" in lowered
    ):
        prefix = (
            "[DIAGNOSTICO] O Windows recusou um caminho interno muito longo de uma dependência.\n"
            f"Runtime atual: {Path(sys.prefix)}\n"
            f"Runtime curto recomendado: {runtime_root() / 'venv'}\n"
            "Use INICIAR_QUESTFLOW_STUDIO.bat ou INSTALAR_E_DIAGNOSTICAR.bat desta versão; "
            "eles criam o ambiente em %LOCALAPPDATA%\\QFS, fora da pasta longa do ZIP.\n"
        )
        return prefix + text
    return text


def install_dependencies() -> tuple[bool, str]:
    process = subprocess.run(
        pip_install_command(),
        cwd=project_root(),
        text=True,
        capture_output=True,
        env=_pip_environment(),
        check=False,
    )
    detail = "\n".join(part.strip() for part in (process.stdout, process.stderr) if part.strip())
    return process.returncode == 0, _friendly_install_detail(detail)




def install_optional_dependencies() -> list[str]:
    """Tenta instalar extensões avançadas sem bloquear o programa."""
    warnings: list[str] = []
    for module_name, package_spec in OPTIONAL_PACKAGES.items():
        try:
            importlib.import_module(module_name)
            continue
        except Exception:
            pass
        process = subprocess.run(
            [
                sys.executable, "-m", "pip", "install",
                "--disable-pip-version-check", "--no-input",
                "--progress-bar", "off", "--quiet", package_spec,
            ],
            cwd=project_root(),
            text=True,
            capture_output=True,
            env=_pip_environment(),
            check=False,
        )
        if process.returncode != 0:
            detail = " ".join(
                part.strip().replace("\n", " ")
                for part in (process.stdout, process.stderr)
                if part.strip()
            )
            warnings.append(f"{module_name}: {detail[:600] or 'não foi possível instalar'}")
    return warnings


def dependencies_are_ready() -> tuple[bool, str]:
    state = current_state()
    if not marker_matches(state):
        return False, "marcador de dependências ausente ou desatualizado"
    imports_ok, import_detail = import_check()
    if not imports_ok:
        return False, import_detail
    pip_ok, pip_detail = pip_check()
    if not pip_ok:
        return False, pip_detail
    return True, ""


def prepare_dependencies(force: bool = False) -> int:
    lock_ok, lock_detail = verify_dependency_lock()
    if not lock_ok:
        print("[FALHA] O lock reprodutível de dependências não passou na verificação SHA-256.")
        if lock_detail:
            print(lock_detail)
        return 1
    state = current_state()
    if not force:
        ready, _ = dependencies_are_ready()
        if ready:
            print("[OK] Dependências já instaladas e válidas. Nenhum download necessário.")
            return 0

    print("[INFO] Instalando ou atualizando as dependências do programa...")
    print("[INFO] O instalador preserva o cache do pip e valida versões para reduzir downloads repetidos.")
    installed, detail = install_dependencies()
    if not installed:
        print("[FALHA] Não foi possível instalar as dependências.")
        if detail:
            print(detail)
        return 1

    imports_ok, import_detail = import_check()
    if not imports_ok:
        print("[FALHA] As dependências foram instaladas, mas alguns módulos não carregaram.")
        print(import_detail)
        return 1

    pip_ok, pip_detail = pip_check()
    if not pip_ok:
        print("[FALHA] O pip encontrou dependências incompatíveis.")
        if pip_detail:
            print(pip_detail)
        return 1

    try:
        fsrs = importlib.import_module("fsrs")
        if not hasattr(fsrs, "Optimizer"):
            raise RuntimeError("o extra optimizer do Py-FSRS não está disponível")
        print(f"[OK] Py-FSRS {getattr(fsrs, '__version__', '')} + Optimizer disponíveis.")
    except Exception as error:
        print("[FALHA] Py-FSRS/Optimizer é obrigatório nesta versão.")
        print(str(error))
        return 1

    write_marker(state)
    legacy_marker = Path(sys.prefix) / ".dependencias_ok"
    try:
        legacy_marker.write_text("ok\n", encoding="utf-8")
    except OSError:
        pass
    print("[OK] Dependências instaladas e verificadas.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Preparador de dependências do {APP_NAME}")
    parser.add_argument("--check-only", action="store_true", help="Apenas verifica o ambiente e não instala.")
    parser.add_argument("--force", action="store_true", help="Força uma nova instalação das dependências.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.check_only:
        ready, detail = dependencies_are_ready()
        if ready:
            return 0
        if detail:
            print(detail)
        return 1
    return prepare_dependencies(force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
