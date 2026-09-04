from __future__ import annotations

"""Runtime desktop do QuestFlow usando exclusivamente o Google Chrome.

A interface web roda em um perfil isolado, sem extensões e sem proxy, para que
antivírus/extensões do navegador não alterem as requisições ao motor local.
"""

import json
import os
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterable

from app_shared import APP_NAME, BASE_DIR, DATABASE_PATH, DATA_DIR

_INSTANCE_HANDLE: BinaryIO | None = None
_NATIVE_PATH = type(Path.cwd())

HEARTBEAT_TIMEOUT_SECONDS = 12.0
HEARTBEAT_CLOSE_GRACE_SECONDS = 6.0
SUSPEND_GAP_THRESHOLD_SECONDS = 20.0
RESUME_HEARTBEAT_GRACE_SECONDS = 45.0
RESUME_RELAUNCH_RETRY_SECONDS = 30.0


def _journal_runtime_event(event: str, **detail: object) -> None:
    """Persist small lifecycle breadcrumbs independently of the web UI.

    This journal is deliberately owned by the desktop runtime because a
    suspend/resume gap can make the browser unavailable before the Web API is
    able to record why the interface disappeared.
    """
    try:
        path = DATA_DIR / "runtime_lifecycle.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size >= 1024 * 1024:
            rotated = path.with_suffix(path.suffix + ".1")
            rotated.unlink(missing_ok=True)
            path.replace(rotated)
        payload = {
            "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "event": str(event),
            "detail": detail,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    except (OSError, TypeError, ValueError):
        pass


def _sampling_gap_seconds(
    previous_monotonic: float,
    previous_wall: float,
    current_monotonic: float,
    current_wall: float,
) -> float:
    """Return the scheduling gap even on clocks that pause during sleep."""
    return max(
        0.0,
        float(current_monotonic) - float(previous_monotonic),
        float(current_wall) - float(previous_wall),
    )


def show_message(message: str, *, error: bool = False) -> None:
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10 if error else 0x40)
            return
        except Exception:
            pass
    print(message)


def acquire_single_instance() -> bool:
    global _INSTANCE_HANDLE
    lock_path = Path(DATABASE_PATH).parent / "questflow_instance.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    try:
        if lock_path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        handle.close()
        return False
    _INSTANCE_HANDLE = handle
    return True


def release_single_instance() -> None:
    global _INSTANCE_HANDLE
    handle, _INSTANCE_HANDLE = _INSTANCE_HANDLE, None
    if handle is None:
        return
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        handle.close()
    except Exception:
        pass


def _registry_chrome_paths() -> Iterable[str]:
    """Read Chrome's App Paths registrations without importing winreg elsewhere."""
    if os.name != "nt":
        return ()
    try:
        import winreg
    except Exception:
        return ()

    result: list[str] = []
    key_name = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for access in (
            getattr(winreg, "KEY_READ", 0),
            getattr(winreg, "KEY_READ", 0) | getattr(winreg, "KEY_WOW64_64KEY", 0),
            getattr(winreg, "KEY_READ", 0) | getattr(winreg, "KEY_WOW64_32KEY", 0),
        ):
            try:
                with winreg.OpenKey(hive, key_name, 0, access) as key:
                    value, _ = winreg.QueryValueEx(key, None)
                    if value:
                        result.append(str(value))
            except OSError:
                continue
    return result


def browser_candidates() -> list[Path]:
    """Return only Google Chrome executables, never Edge/WebView/Chromium."""
    windows = os.name == "nt"
    local = os.environ.get("LOCALAPPDATA", "") if windows else ""
    program_files = os.environ.get("PROGRAMFILES", "") if windows else ""
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)", "") if windows else ""

    values: list[str | None] = [
        shutil.which("chrome.exe"),
        shutil.which("chrome"),
        *list(_registry_chrome_paths()),
        str(_NATIVE_PATH(local) / "Google/Chrome/Application/chrome.exe") if local else None,
        str(_NATIVE_PATH(program_files) / "Google/Chrome/Application/chrome.exe") if program_files else None,
        str(_NATIVE_PATH(program_files_x86) / "Google/Chrome/Application/chrome.exe") if program_files_x86 else None,
    ]

    result: list[Path] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        path = _NATIVE_PATH(value).expanduser()
        try:
            path = path.resolve()
        except OSError:
            pass
        key = str(path).casefold()
        # Keep the contract strict: this runtime must never silently select Edge.
        if "chrome" not in path.name.casefold():
            continue
        if key not in seen and path.is_file():
            seen.add(key)
            result.append(path)
    return result


def chrome_profile_dir() -> Path:
    """Return the dedicated Chrome profile used only by QuestFlow Studio."""
    profile = DATA_DIR / "chrome_runtime_5_4_0"
    profile.mkdir(parents=True, exist_ok=True)
    return profile


def terminate_stale_questflow_chrome(*, wait_seconds: float = 4.0) -> int:
    """Terminate only Chrome processes that own QuestFlow's dedicated profile.

    The safe updater may stop the Python engine before Chrome has time to close.
    A subsequent launch with the same ``--user-data-dir`` can then be forwarded
    to that orphaned Chrome process and never reach the new local server. Normal
    Chrome sessions are never selected because matching is profile-specific.
    """
    if os.name != "nt":
        return 0

    profile = str(chrome_profile_dir().resolve())
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        return 0

    script = """
$target = $env:QF_CHROME_PROFILE
if (-not $target) { Write-Output 0; exit 0 }
$escaped = [regex]::Escape($target)
$matches = @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and $_.CommandLine -match $escaped
})
foreach ($item in $matches) {
    try { Stop-Process -Id $item.ProcessId -Force -ErrorAction SilentlyContinue } catch { }
}
Write-Output $matches.Count
"""
    env = os.environ.copy()
    env["QF_CHROME_PROFILE"] = profile
    try:
        completed = subprocess.run(
            [powershell, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            env=env,
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=max(2.0, float(wait_seconds) + 2.0),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        output = str(completed.stdout or "").strip().splitlines()
        count = int(output[-1]) if output and output[-1].strip().isdigit() else 0
        if count > 0:
            # Give Windows/Chrome a short window to release the profile lock.
            time.sleep(min(max(float(wait_seconds), 0.0), 4.0))
        return count
    except Exception:
        return 0


def _wait_for_server_transport(server, *, timeout: float = 8.0) -> bool:
    """Confirm the loopback listener accepts connections before Chrome is opened."""
    # Compatibility with embedded/test transports that expose heartbeat/url
    # but no numeric socket port. The production HTTP server always has port.
    if not hasattr(server, "port") and int(getattr(server, "heartbeat_count", 0) or 0) > 0:
        return True
    deadline = time.monotonic() + max(0.2, float(timeout))
    while time.monotonic() < deadline:
        port = int(getattr(server, "port", 0) or 0)
        if port > 0:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.35):
                    return True
            except OSError:
                pass
        time.sleep(0.08)
    return False


def _chrome_command(browser: Path, url: str) -> list[str]:
    # Use a Chrome-only profile. Previous versions shared one folder between
    # Edge and Chrome, which can corrupt preferences and load unwanted add-ons.
    profile = chrome_profile_dir()
    return [
        str(browser),
        f"--app={url}",
        f"--user-data-dir={profile}",
        "--profile-directory=Default",
        "--start-maximized",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-mode",
        "--disable-session-crashed-bubble",
        "--disable-extensions",
        "--disable-default-apps",
        "--disable-sync",
        "--disable-component-update",
        "--no-proxy-server",
        "--proxy-bypass-list=*",
        "--disable-features=MediaRouter,OptimizationHints,AutofillServerCommunication",
        "--disk-cache-size=134217728",
        "--media-cache-size=33554432",
    ]

def run_chrome(server, api) -> bool:
    """Launch Chrome and keep the Python engine alive while the app window exists.

    Startup is intentionally defensive after an update: wait until the local
    listener is reachable, clean an orphaned QuestFlow-only Chrome profile and
    retry once before surfacing a connection error to the user.
    """
    if not _wait_for_server_transport(server, timeout=8.0):
        return False

    terminate_stale_questflow_chrome(wait_seconds=1.0)

    for browser in browser_candidates():
        for attempt in range(2):
            process: subprocess.Popen | None = None
            try:
                flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
                baseline_heartbeat = (
                    int(getattr(server, "heartbeat_count", 0) or 0)
                    if hasattr(server, "port")
                    else 0
                )
                process = subprocess.Popen(
                    _chrome_command(browser, server.url),
                    cwd=BASE_DIR,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                )
                deadline = time.monotonic() + 35.0
                launcher_exited_at: float | None = None
                while time.monotonic() < deadline and server.heartbeat_count <= baseline_heartbeat:
                    # A close action may arrive while Chrome is handing the app
                    # window to another process. Honor it before waiting for a
                    # fresh heartbeat so shutdown cannot stall indefinitely.
                    if bool(getattr(api, "close_requested", False)):
                        try:
                            api.shutdown(reason="botao_fechar")
                        except Exception:
                            pass
                        if process.poll() is None:
                            try:
                                process.terminate()
                            except Exception:
                                pass
                        return True
                    if process.poll() is not None:
                        if launcher_exited_at is None:
                            launcher_exited_at = time.monotonic()
                        # chrome.exe may hand the URL to another Chrome process
                        # and exit. Give that process a brief delivery window.
                        if time.monotonic() - launcher_exited_at >= 6.0:
                            break
                    time.sleep(0.12)

                if server.heartbeat_count <= baseline_heartbeat:
                    try:
                        if process.poll() is None:
                            process.terminate()
                    except Exception:
                        pass
                    if attempt == 0:
                        terminate_stale_questflow_chrome(wait_seconds=1.0)
                        time.sleep(0.35)
                        continue
                    break

                api.start_services()
                # Chrome's app process can remain alive in background even after the
                # QuestFlow app window is closed. A normally aging heartbeat still
                # identifies that close. A large scheduler/wall-clock gap, however,
                # means Windows suspended or hibernated the notebook; in that state
                # the backend must survive and the UI is allowed to wake or relaunch.
                heartbeat_timeout = HEARTBEAT_TIMEOUT_SECONDS
                heartbeat_grace = HEARTBEAT_CLOSE_GRACE_SECONDS
                suspend_gap_threshold = SUSPEND_GAP_THRESHOLD_SECONDS
                resume_heartbeat_grace = RESUME_HEARTBEAT_GRACE_SECONDS
                resume_relaunch_retry = RESUME_RELAUNCH_RETRY_SECONDS
                previous_monotonic = time.monotonic()
                previous_wall = time.time()
                last_observed_heartbeat = int(getattr(server, "heartbeat_count", 0) or 0)
                resume_recovery = False
                resume_heartbeat_baseline = last_observed_heartbeat
                resume_relaunch_after = 0.0
                while True:
                    current_monotonic = time.monotonic()
                    current_wall = time.time()
                    sampling_gap = _sampling_gap_seconds(
                        previous_monotonic,
                        previous_wall,
                        current_monotonic,
                        current_wall,
                    )
                    previous_monotonic = current_monotonic
                    previous_wall = current_wall
                    current_heartbeat = int(getattr(server, "heartbeat_count", 0) or 0)

                    if sampling_gap >= suspend_gap_threshold:
                        resume_recovery = True
                        resume_heartbeat_baseline = last_observed_heartbeat
                        resume_relaunch_after = current_monotonic + resume_heartbeat_grace
                        _journal_runtime_event(
                            "suspend_resume_detected",
                            sampling_gap_seconds=round(sampling_gap, 3),
                            heartbeat_age_seconds=round(float(server.last_heartbeat_age), 3),
                            heartbeat_baseline=resume_heartbeat_baseline,
                        )

                    if bool(getattr(api, "close_requested", False)):
                        try:
                            api.shutdown(reason="botao_fechar")
                        except Exception:
                            pass
                        if process.poll() is None:
                            try:
                                process.terminate()
                            except Exception:
                                pass
                        return True

                    if server.last_heartbeat_age <= heartbeat_timeout:
                        if resume_recovery:
                            if current_heartbeat > resume_heartbeat_baseline:
                                _journal_runtime_event(
                                    "interface_resumed",
                                    recovery="heartbeat",
                                    heartbeat_age_seconds=round(float(server.last_heartbeat_age), 3),
                                )
                                resume_recovery = False
                            else:
                                # Some Windows clocks pause during hibernation and
                                # can report a deceptively young heartbeat. Require
                                # a new UI emission before leaving recovery mode.
                                time.sleep(0.5)
                                continue
                        last_observed_heartbeat = current_heartbeat
                        time.sleep(0.5)
                        continue

                    if resume_recovery:
                        # Chrome may need several seconds after resume to thaw its
                        # renderer and service worker. Do not confuse that delay with
                        # a real window close. If it never returns, relaunch only the
                        # dedicated QuestFlow window and keep all backend services.
                        if current_monotonic < resume_relaunch_after:
                            time.sleep(0.5)
                            continue

                        baseline_heartbeat = int(getattr(server, "heartbeat_count", 0) or 0)
                        _journal_runtime_event(
                            "interface_relaunch_started",
                            heartbeat_age_seconds=round(float(server.last_heartbeat_age), 3),
                        )
                        try:
                            if process.poll() is None:
                                process.terminate()
                        except Exception:
                            pass
                        terminate_stale_questflow_chrome(wait_seconds=1.0)
                        try:
                            process = subprocess.Popen(
                                _chrome_command(browser, server.url),
                                cwd=BASE_DIR,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                creationflags=flags,
                            )
                        except Exception as error:
                            _journal_runtime_event("interface_relaunch_failed", error=str(error))
                            resume_relaunch_after = time.monotonic() + resume_relaunch_retry
                            previous_monotonic = time.monotonic()
                            previous_wall = time.time()
                            continue

                        relaunch_deadline = time.monotonic() + 35.0
                        while time.monotonic() < relaunch_deadline:
                            if bool(getattr(api, "close_requested", False)):
                                break
                            if int(getattr(server, "heartbeat_count", 0) or 0) > baseline_heartbeat:
                                resume_recovery = False
                                last_observed_heartbeat = int(getattr(server, "heartbeat_count", 0) or 0)
                                _journal_runtime_event("interface_resumed", recovery="relaunch")
                                break
                            time.sleep(0.25)

                        previous_monotonic = time.monotonic()
                        previous_wall = time.time()
                        if resume_recovery:
                            _journal_runtime_event("interface_relaunch_pending")
                            resume_relaunch_after = previous_monotonic + resume_relaunch_retry
                        continue

                    grace_deadline = time.monotonic() + heartbeat_grace
                    recovered = False
                    while time.monotonic() < grace_deadline:
                        time.sleep(0.5)
                        if bool(getattr(api, "close_requested", False)):
                            break
                        if server.last_heartbeat_age <= heartbeat_timeout:
                            recovered = True
                            break
                    if recovered:
                        continue

                    try:
                        api.shutdown(reason="janela_fechada")
                    except Exception:
                        pass
                    if process.poll() is None:
                        try:
                            process.terminate()
                        except Exception:
                            pass
                    return True
            except Exception:
                if process is not None:
                    try:
                        process.terminate()
                    except Exception:
                        pass
                if attempt == 0:
                    terminate_stale_questflow_chrome(wait_seconds=0.5)
                    continue
                break
    return False


# Compatibility alias for older tests/integrations; it still launches Chrome only.
run_chromium = run_chrome


__all__ = [
    "acquire_single_instance",
    "browser_candidates",
    "chrome_profile_dir",
    "release_single_instance",
    "run_chrome",
    "run_chromium",
    "show_message",
    "terminate_stale_questflow_chrome",
]
