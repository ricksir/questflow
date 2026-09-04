from __future__ import annotations

"""Camada central de rede e proxy do QuestFlow Studio.

A interface principal continua isolada em 127.0.0.1 e nunca depende de proxy.
Somente tráfego externo (Telegram, Google, Google Sheets, Selenium e instalador)
passa por esta camada.
"""

import base64
import ctypes
import fnmatch
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app_shared import APP_VERSION, CONFIG_PATH, DATA_DIR, load_config

DEFAULT_BYPASS = "localhost;127.0.0.1;::1;<local>"
CREDENTIAL_FILE = DATA_DIR / "proxy_credentials.dat"


@dataclass(slots=True)
class ProxyResolution:
    mode: str
    source: str
    proxy_url: str = ""
    pac_url: str = ""
    bypass: str = DEFAULT_BYPASS
    username: str = ""
    password: str = ""
    auth_mode: str = "none"
    detail: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.proxy_url or self.pac_url) and self.mode != "direct"

    def public(self) -> dict[str, Any]:
        parsed = urllib.parse.urlparse(self.proxy_url) if self.proxy_url else None
        host = parsed.hostname if parsed else ""
        port = parsed.port if parsed else None
        return {
            "mode": self.mode,
            "source": self.source,
            "enabled": self.enabled,
            "proxy": f"{host}:{port}" if host and port else (host or ""),
            "pac_url": self.pac_url,
            "bypass": self.bypass,
            "auth_mode": self.auth_mode,
            "username": self.username,
            "password_configured": bool(self.password),
            "detail": self.detail,
        }


class NetworkConfigurationError(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes) -> tuple[_DataBlob, Any]:
    if not data:
        return _DataBlob(0, None), None
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _dpapi_protect(data: bytes) -> bytes:
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
    description = "QuestFlow Proxy Credentials"
    ok = crypt32.CryptProtectData(
        ctypes.byref(source),
        description,
        None,
        None,
        None,
        0,
        ctypes.byref(output),
    )
    _ = keepalive
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        if output.pbData:
            kernel32.LocalFree(output.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
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
        ctypes.byref(source),
        ctypes.byref(description),
        None,
        None,
        None,
        0,
        ctypes.byref(output),
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


def save_proxy_credentials(username: str, password: str, path: str | Path = CREDENTIAL_FILE) -> None:
    """Store proxy credentials protected by the current Windows user (DPAPI)."""
    target = Path(path)
    username = str(username or "").strip()
    password = str(password or "")
    if not username and not password:
        clear_proxy_credentials(target)
        return
    payload = json.dumps({"username": username, "password": password}, ensure_ascii=False).encode("utf-8")
    if os.name == "nt":
        encrypted = _dpapi_protect(payload)
        envelope = {"schema": 1, "protection": "windows-dpapi", "data": base64.b64encode(encrypted).decode("ascii")}
    else:
        # QuestFlow is a Windows desktop application. On other systems (mainly
        # automated tests), never persist a password in clear text.
        envelope = {"schema": 1, "protection": "unsupported", "data": ""}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(envelope, separators=(",", ":")), encoding="utf-8")


def load_proxy_credentials(path: str | Path = CREDENTIAL_FILE) -> tuple[str, str]:
    target = Path(path)
    if not target.exists():
        return "", ""
    try:
        envelope = json.loads(target.read_text(encoding="utf-8"))
        if envelope.get("protection") != "windows-dpapi" or os.name != "nt":
            return "", ""
        encrypted = base64.b64decode(str(envelope.get("data", "")))
        payload = json.loads(_dpapi_unprotect(encrypted).decode("utf-8"))
        return str(payload.get("username", "")), str(payload.get("password", ""))
    except Exception:
        return "", ""


def clear_proxy_credentials(path: str | Path = CREDENTIAL_FILE) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def credential_path_for_config(config_path: str | Path | None = None) -> Path:
    if config_path is None:
        return CREDENTIAL_FILE
    return Path(config_path).resolve().parent / "proxy_credentials.dat"


def _split_bypass(value: str) -> list[str]:
    text = str(value or "").replace(",", ";")
    return [part.strip() for part in text.split(";") if part.strip()]


def _is_local_host(host: str) -> bool:
    value = (host or "").strip("[]").lower()
    return value in {"localhost", "127.0.0.1", "::1"} or value.startswith("127.")


def should_bypass(url: str, bypass: str = DEFAULT_BYPASS) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    if _is_local_host(host):
        return True
    for rule in _split_bypass(bypass):
        lowered = rule.casefold()
        if lowered == "<local>" and "." not in host:
            return True
        rule_host = rule
        if "://" in rule_host:
            rule_host = urllib.parse.urlparse(rule_host).hostname or rule_host
        rule_host = rule_host.strip("[]")
        if fnmatch.fnmatch(host.casefold(), rule_host.casefold()):
            return True
        if rule_host.startswith(".") and host.casefold().endswith(rule_host.casefold()):
            return True
    return False


def _normalize_proxy_url(value: str, port: Any = None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if ";" in text or "=" in text:
        # WinINET style list is handled elsewhere.
        return text
    if "://" not in text:
        text = "http://" + text
    parsed = urllib.parse.urlparse(text)
    host = parsed.hostname or ""
    if not host:
        return ""
    selected_port = parsed.port
    try:
        explicit_port = int(port) if str(port or "").strip() else None
    except (TypeError, ValueError):
        explicit_port = None
    selected_port = explicit_port or selected_port
    netloc = host if selected_port is None else f"{host}:{selected_port}"
    return urllib.parse.urlunparse((parsed.scheme or "http", netloc, "", "", "", ""))


def _proxy_from_list(proxy_text: str, scheme: str = "https") -> str:
    text = str(proxy_text or "").strip()
    if not text:
        return ""
    pieces = [part.strip() for part in text.split(";") if part.strip()]
    mapping: dict[str, str] = {}
    generic = ""
    for piece in pieces:
        if "=" in piece:
            key, value = piece.split("=", 1)
            mapping[key.strip().lower()] = value.strip()
        elif not generic:
            generic = piece
    selected = mapping.get(scheme.lower()) or mapping.get("http") or generic
    return _normalize_proxy_url(selected)


def _windows_ie_proxy_config() -> dict[str, Any]:
    if os.name != "nt":
        return {"available": False, "auto_detect": False, "pac_url": "", "proxy": "", "bypass": ""}

    class IEProxyConfig(ctypes.Structure):
        _fields_ = [
            ("fAutoDetect", wintypes.BOOL),
            ("lpszAutoConfigUrl", ctypes.c_void_p),
            ("lpszProxy", ctypes.c_void_p),
            ("lpszProxyBypass", ctypes.c_void_p),
        ]

    winhttp = ctypes.WinDLL("winhttp", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    winhttp.WinHttpGetIEProxyConfigForCurrentUser.argtypes = [ctypes.POINTER(IEProxyConfig)]
    winhttp.WinHttpGetIEProxyConfigForCurrentUser.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p
    config = IEProxyConfig()
    try:
        ok = winhttp.WinHttpGetIEProxyConfigForCurrentUser(ctypes.byref(config))
        if not ok:
            return {"available": False, "auto_detect": False, "pac_url": "", "proxy": "", "bypass": ""}
        result = {
            "available": True,
            "auto_detect": bool(config.fAutoDetect),
            "pac_url": ctypes.wstring_at(config.lpszAutoConfigUrl) if config.lpszAutoConfigUrl else "",
            "proxy": ctypes.wstring_at(config.lpszProxy) if config.lpszProxy else "",
            "bypass": ctypes.wstring_at(config.lpszProxyBypass) if config.lpszProxyBypass else "",
        }
        return result
    finally:
        for pointer in (config.lpszAutoConfigUrl, config.lpszProxy, config.lpszProxyBypass):
            if pointer:
                try:
                    kernel32.GlobalFree(pointer)
                except Exception:
                    pass


def _winhttp_proxy_for_url(url: str, *, pac_url: str = "", auto_detect: bool = False) -> tuple[str, str]:
    """Resolve PAC/WPAD with Windows WinHTTP without shipping a JS PAC engine."""
    if os.name != "nt":
        return "", "WinHTTP indisponível fora do Windows."

    class AutoProxyOptions(ctypes.Structure):
        _fields_ = [
            ("dwFlags", wintypes.DWORD),
            ("dwAutoDetectFlags", wintypes.DWORD),
            ("lpszAutoConfigUrl", wintypes.LPCWSTR),
            ("lpvReserved", wintypes.LPVOID),
            ("dwReserved", wintypes.DWORD),
            ("fAutoLogonIfChallenged", wintypes.BOOL),
        ]

    class ProxyInfo(ctypes.Structure):
        _fields_ = [
            ("dwAccessType", wintypes.DWORD),
            ("lpszProxy", ctypes.c_void_p),
            ("lpszProxyBypass", ctypes.c_void_p),
        ]

    WINHTTP_ACCESS_TYPE_NO_PROXY = 1
    WINHTTP_AUTOPROXY_AUTO_DETECT = 0x00000001
    WINHTTP_AUTOPROXY_CONFIG_URL = 0x00000002
    WINHTTP_AUTO_DETECT_TYPE_DHCP = 0x00000001
    WINHTTP_AUTO_DETECT_TYPE_DNS_A = 0x00000002

    winhttp = ctypes.WinDLL("winhttp", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    winhttp.WinHttpOpen.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    winhttp.WinHttpOpen.restype = wintypes.HANDLE
    winhttp.WinHttpGetProxyForUrl.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, ctypes.POINTER(AutoProxyOptions), ctypes.POINTER(ProxyInfo)]
    winhttp.WinHttpGetProxyForUrl.restype = wintypes.BOOL
    winhttp.WinHttpCloseHandle.argtypes = [wintypes.HANDLE]
    winhttp.WinHttpCloseHandle.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p
    session = winhttp.WinHttpOpen(f"QuestFlow/{APP_VERSION}", WINHTTP_ACCESS_TYPE_NO_PROXY, None, None, 0)
    if not session:
        return "", f"WinHttpOpen falhou: {ctypes.get_last_error()}"
    info = ProxyInfo()
    options = AutoProxyOptions()
    try:
        if pac_url:
            options.dwFlags |= WINHTTP_AUTOPROXY_CONFIG_URL
            options.lpszAutoConfigUrl = str(pac_url)
        if auto_detect:
            options.dwFlags |= WINHTTP_AUTOPROXY_AUTO_DETECT
            options.dwAutoDetectFlags = WINHTTP_AUTO_DETECT_TYPE_DHCP | WINHTTP_AUTO_DETECT_TYPE_DNS_A
        options.fAutoLogonIfChallenged = True
        if not options.dwFlags:
            return "", "Nenhum PAC/WPAD configurado."
        ok = winhttp.WinHttpGetProxyForUrl(session, str(url), ctypes.byref(options), ctypes.byref(info))
        if not ok:
            error = ctypes.get_last_error()
            return "", f"WinHttpGetProxyForUrl falhou: {error}"
        proxy_text = ctypes.wstring_at(info.lpszProxy) if info.lpszProxy else ""
        proxy_url = _proxy_from_list(proxy_text, urllib.parse.urlparse(url).scheme or "https")
        return proxy_url, "PAC/WPAD resolvido pelo Windows."
    finally:
        for pointer in (info.lpszProxy, info.lpszProxyBypass):
            if pointer:
                try:
                    kernel32.GlobalFree(pointer)
                except Exception:
                    pass
        winhttp.WinHttpCloseHandle(session)


def detect_system_proxy() -> dict[str, Any]:
    """Return a public, password-free snapshot of the current proxy sources."""
    ie = _windows_ie_proxy_config()
    proxies = urllib.request.getproxies()
    proxy = str(ie.get("proxy") or "")
    pac_url = str(ie.get("pac_url") or "")
    bypass = str(ie.get("bypass") or proxies.get("no") or DEFAULT_BYPASS)
    https_proxy = _proxy_from_list(proxy, "https") if proxy else _normalize_proxy_url(proxies.get("https", ""))
    http_proxy = _proxy_from_list(proxy, "http") if proxy else _normalize_proxy_url(proxies.get("http", ""))
    source = "windows" if ie.get("available") and (proxy or pac_url or ie.get("auto_detect")) else ("environment" if https_proxy or http_proxy else "direct")
    return {
        "source": source,
        "https_proxy": https_proxy,
        "http_proxy": http_proxy,
        "pac_url": pac_url,
        "auto_detect": bool(ie.get("auto_detect")),
        "bypass": bypass or DEFAULT_BYPASS,
    }


def _ssl_context_with_windows_roots() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if os.name == "nt" and hasattr(ssl, "enum_certificates"):
        for store in ("ROOT", "CA"):
            try:
                certificates = ssl.enum_certificates(store)
            except Exception:
                continue
            pem_parts: list[str] = []
            for certificate, encoding, _trust in certificates:
                if encoding == "x509_asn":
                    try:
                        pem_parts.append(ssl.DER_cert_to_PEM_cert(certificate))
                    except Exception:
                        pass
            if pem_parts:
                try:
                    context.load_verify_locations(cadata="\n".join(pem_parts))
                except Exception:
                    pass
    return context


class NetworkManager:
    def __init__(
        self,
        config: dict | None = None,
        *,
        config_path: str | Path | None = None,
        credential_path: str | Path | None = None,
    ) -> None:
        self.config = dict(config) if config is not None else load_config()
        self.config_path = Path(config_path) if config_path else CONFIG_PATH
        self.credential_path = Path(credential_path) if credential_path else credential_path_for_config(self.config_path)
        self._cache: dict[str, tuple[float, ProxyResolution]] = {}

    def settings(self) -> dict[str, Any]:
        system = detect_system_proxy()
        username, password = load_proxy_credentials(self.credential_path)
        configured_username = str(self.config.get("network_proxy_username", "") or "").strip()
        return {
            "network_mode": str(self.config.get("network_mode", "auto") or "auto"),
            "network_proxy_host": str(self.config.get("network_proxy_host", "") or ""),
            "network_proxy_port": str(self.config.get("network_proxy_port", "") or ""),
            "network_pac_url": str(self.config.get("network_pac_url", "") or ""),
            "network_proxy_bypass": str(self.config.get("network_proxy_bypass", DEFAULT_BYPASS) or DEFAULT_BYPASS),
            "network_proxy_auth": str(self.config.get("network_proxy_auth", "none") or "none"),
            "network_proxy_username": configured_username or username,
            "network_proxy_password_configured": bool(password),
            "network_system_detected": system,
        }

    def _credentials(self) -> tuple[str, str]:
        stored_username, stored_password = load_proxy_credentials(self.credential_path)
        username = str(self.config.get("network_proxy_username", "") or "").strip() or stored_username
        return username, stored_password

    def resolve(self, url: str, *, refresh: bool = False) -> ProxyResolution:
        parsed = urllib.parse.urlparse(url)
        cache_key = f"{parsed.scheme}:{parsed.hostname}"
        now = time.monotonic()
        if not refresh and cache_key in self._cache:
            saved, resolution = self._cache[cache_key]
            if now - saved < 600:
                return resolution

        mode = str(self.config.get("network_mode", "auto") or "auto").strip().lower()
        if mode not in {"auto", "system", "manual", "pac", "direct"}:
            mode = "auto"
        bypass = str(self.config.get("network_proxy_bypass", DEFAULT_BYPASS) or DEFAULT_BYPASS)
        auth_mode = str(self.config.get("network_proxy_auth", "none") or "none").strip().lower()
        username, password = self._credentials()

        if should_bypass(url, bypass):
            resolution = ProxyResolution(mode=mode, source="bypass", bypass=bypass, username=username, password=password, auth_mode=auth_mode, detail="Destino ignorado pelo proxy.")
            self._cache[cache_key] = (now, resolution)
            return resolution

        if mode == "direct":
            resolution = ProxyResolution(mode=mode, source="direct", bypass=bypass, username=username, password=password, auth_mode=auth_mode, detail="Conexão direta selecionada.")
            self._cache[cache_key] = (now, resolution)
            return resolution

        system = detect_system_proxy()
        scheme = parsed.scheme.lower() or "https"
        proxy_url = ""
        pac_url = ""
        source = "direct"
        detail = ""

        if mode == "manual":
            proxy_url = _normalize_proxy_url(self.config.get("network_proxy_host", ""), self.config.get("network_proxy_port", ""))
            source = "manual" if proxy_url else "direct"
            detail = "Proxy manual configurado." if proxy_url else "Proxy manual sem servidor/porta."
        elif mode == "pac":
            pac_url = str(self.config.get("network_pac_url", "") or "").strip()
            proxy_url, detail = _winhttp_proxy_for_url(url, pac_url=pac_url, auto_detect=False)
            source = "pac" if proxy_url else "direct"
        elif mode == "system":
            proxy_url = str(system.get(f"{scheme}_proxy") or system.get("https_proxy") or system.get("http_proxy") or "")
            pac_url = str(system.get("pac_url") or "")
            if not proxy_url and pac_url:
                proxy_url, detail = _winhttp_proxy_for_url(url, pac_url=pac_url, auto_detect=False)
            source = "windows" if proxy_url or pac_url else "direct"
            detail = detail or ("Configuração de proxy do Windows." if source == "windows" else "Windows sem proxy explícito.")
        else:  # auto
            explicit_pac = str(self.config.get("network_pac_url", "") or "").strip()
            pac_url = explicit_pac or str(system.get("pac_url") or "")
            if pac_url or system.get("auto_detect"):
                proxy_url, detail = _winhttp_proxy_for_url(url, pac_url=pac_url, auto_detect=bool(system.get("auto_detect")))
            if not proxy_url:
                proxy_url = str(system.get(f"{scheme}_proxy") or system.get("https_proxy") or system.get("http_proxy") or "")
            source = str(system.get("source") or "auto") if proxy_url or pac_url or system.get("auto_detect") else "direct"
            detail = detail or ("Proxy detectado automaticamente." if proxy_url else "Nenhum proxy necessário/detectado.")

        resolution = ProxyResolution(
            mode=mode,
            source=source,
            proxy_url=proxy_url,
            pac_url=pac_url,
            bypass=bypass,
            username=username,
            password=password,
            auth_mode=auth_mode,
            detail=detail,
        )
        self._cache[cache_key] = (now, resolution)
        return resolution

    def build_opener(self, url: str) -> urllib.request.OpenerDirector:
        resolution = self.resolve(url)
        handlers: list[Any] = []
        if resolution.proxy_url:
            proxy_map = {"http": resolution.proxy_url, "https": resolution.proxy_url}
            handlers.append(urllib.request.ProxyHandler(proxy_map))
            if resolution.auth_mode in {"basic", "userpass"} and resolution.username and resolution.password:
                manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
                manager.add_password(None, resolution.proxy_url, resolution.username, resolution.password)
                handlers.extend([
                    urllib.request.ProxyBasicAuthHandler(manager),
                    urllib.request.ProxyDigestAuthHandler(manager),
                ])
        else:
            # Explicit empty ProxyHandler is important: local/direct mode must
            # not be silently affected by HTTP_PROXY inherited by the process.
            handlers.append(urllib.request.ProxyHandler({}))
        handlers.append(urllib.request.HTTPSHandler(context=_ssl_context_with_windows_roots()))
        return urllib.request.build_opener(*handlers)

    def open(self, request: urllib.request.Request | str, timeout: int | float = 30):
        url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
        opener = self.build_opener(url)
        return opener.open(request, timeout=timeout)

    def chrome_arguments(self, url: str = "https://www.google.com/") -> list[str]:
        mode = str(self.config.get("network_mode", "auto") or "auto").lower()
        bypass = str(self.config.get("network_proxy_bypass", DEFAULT_BYPASS) or DEFAULT_BYPASS)
        chrome_bypass = bypass.replace(";", ",")
        args = [f"--proxy-bypass-list={chrome_bypass}"]
        if mode == "direct":
            args.append("--no-proxy-server")
            return args
        if mode == "pac":
            pac_url = str(self.config.get("network_pac_url", "") or "").strip()
            if pac_url:
                args.append(f"--proxy-pac-url={pac_url}")
            return args
        if mode == "manual":
            resolution = self.resolve(url, refresh=True)
            if resolution.proxy_url:
                parsed = urllib.parse.urlparse(resolution.proxy_url)
                endpoint = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}" if parsed.hostname and parsed.port else resolution.proxy_url
                args.append(f"--proxy-server={endpoint}")
            return args
        # system/auto deliberately inherit Chrome's Windows policy/settings.
        return args

    def environment(self, url: str = "https://pypi.org/simple/") -> dict[str, str]:
        resolution = self.resolve(url, refresh=True)
        env = {
            "NO_PROXY": "localhost,127.0.0.1,::1",
            "no_proxy": "localhost,127.0.0.1,::1",
        }
        if resolution.proxy_url:
            proxy = resolution.proxy_url
            if resolution.auth_mode in {"basic", "userpass"} and resolution.username and resolution.password:
                parsed = urllib.parse.urlparse(proxy)
                user = urllib.parse.quote(resolution.username, safe="")
                password = urllib.parse.quote(resolution.password, safe="")
                netloc = f"{user}:{password}@{parsed.hostname or ''}"
                if parsed.port:
                    netloc += f":{parsed.port}"
                proxy = urllib.parse.urlunparse((parsed.scheme or "http", netloc, "", "", "", ""))
            env.update({"HTTP_PROXY": proxy, "HTTPS_PROXY": proxy, "http_proxy": proxy, "https_proxy": proxy})
        return env


def network_urlopen(request: urllib.request.Request | str, timeout: int | float = 30, *, config: dict | None = None):
    return NetworkManager(config).open(request, timeout=timeout)


def proxy_environment(config: dict | None = None, *, config_path: str | Path | None = None) -> dict[str, str]:
    return NetworkManager(config, config_path=config_path).environment()


def chrome_proxy_arguments(config: dict | None = None, url: str = "https://www.google.com/") -> list[str]:
    return NetworkManager(config).chrome_arguments(url)


def _classify_network_error(error: BaseException) -> tuple[str, str]:
    if isinstance(error, urllib.error.HTTPError):
        if error.code == 407:
            return "proxy_auth", "O proxy respondeu 407 e exige autenticação ou credenciais diferentes."
        return "http", f"O destino respondeu HTTP {error.code}."
    if isinstance(error, urllib.error.URLError):
        reason = getattr(error, "reason", error)
        if isinstance(reason, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(reason):
            return "tls", "O certificado HTTPS apresentado pela rede/proxy não foi reconhecido."
        if isinstance(reason, socket.gaierror):
            return "dns", "O nome do servidor não pôde ser resolvido pelo DNS."
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return "timeout", "A conexão expirou antes de receber resposta."
        return "connection", f"Falha de conexão: {reason}"
    if isinstance(error, ssl.SSLError):
        return "tls", "Falha de certificado/TLS."
    if isinstance(error, (socket.timeout, TimeoutError)):
        return "timeout", "A conexão expirou."
    return "error", str(error) or error.__class__.__name__


def test_network(config: dict | None = None, *, config_path: str | Path | None = None, timeout: int = 10) -> dict[str, Any]:
    manager = NetworkManager(config, config_path=config_path)
    sample = manager.resolve("https://www.google.com/", refresh=True)
    tests: list[dict[str, Any]] = [
        {"name": "Motor local", "ok": True, "category": "local", "detail": "127.0.0.1 permanece fora do proxy."},
    ]
    try:
        started = time.perf_counter()
        socket.getaddrinfo("api.telegram.org", 443, type=socket.SOCK_STREAM)
        tests.append({"name": "DNS", "ok": True, "category": "dns", "elapsed_ms": round((time.perf_counter() - started) * 1000), "detail": "api.telegram.org resolvido."})
    except Exception as error:
        category, detail = _classify_network_error(error)
        tests.append({"name": "DNS", "ok": False, "category": category, "detail": detail})

    targets = [
        ("Google", "https://www.google.com/generate_204"),
        ("Google Sheets", "https://docs.google.com/"),
        ("Telegram", "https://api.telegram.org/"),
    ]
    for name, url in targets:
        request = urllib.request.Request(url, headers={"User-Agent": f"QuestFlowStudio/{APP_VERSION}"}, method="GET")
        started = time.perf_counter()
        try:
            with manager.open(request, timeout=timeout) as response:
                response.read(128)
                status = int(getattr(response, "status", 200) or 200)
            tests.append({"name": name, "ok": status < 500, "category": "https", "status": status, "elapsed_ms": round((time.perf_counter() - started) * 1000), "detail": f"HTTP {status}"})
        except urllib.error.HTTPError as error:
            # 4xx proves DNS/TLS/proxy routing worked; 407 is the exception.
            category, detail = _classify_network_error(error)
            tests.append({"name": name, "ok": error.code != 407 and error.code < 500, "category": category, "status": error.code, "elapsed_ms": round((time.perf_counter() - started) * 1000), "detail": detail})
        except Exception as error:
            category, detail = _classify_network_error(error)
            tests.append({"name": name, "ok": False, "category": category, "elapsed_ms": round((time.perf_counter() - started) * 1000), "detail": detail})

    return {
        "ok": all(item.get("ok") for item in tests),
        "proxy": sample.public(),
        "settings": manager.settings(),
        "tests": tests,
    }


__all__ = [
    "DEFAULT_BYPASS",
    "NetworkConfigurationError",
    "NetworkManager",
    "ProxyResolution",
    "chrome_proxy_arguments",
    "clear_proxy_credentials",
    "credential_path_for_config",
    "detect_system_proxy",
    "load_proxy_credentials",
    "network_urlopen",
    "proxy_environment",
    "save_proxy_credentials",
    "should_bypass",
    "test_network",
]
