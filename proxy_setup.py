from __future__ import annotations

"""Configurador de Rede e Proxy que funciona antes da instalação das dependências.

Usa somente a biblioteca padrão do Python/Tkinter. Assim uma máquina corporativa
pode configurar o proxy antes do primeiro ``pip install`` do QuestFlow.
"""

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from app_shared import APP_NAME, load_config, save_config
from core.network import (
    DEFAULT_BYPASS,
    NetworkManager,
    clear_proxy_credentials,
    credential_path_for_config,
    detect_system_proxy,
    save_proxy_credentials,
    test_network,
)


class ProxySetup(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} — Rede e Proxy")
        self.geometry("760x650")
        self.minsize(680, 560)
        self.config_data = load_config()
        self.vars = {
            "network_mode": tk.StringVar(value=str(self.config_data.get("network_mode", "auto"))),
            "network_proxy_host": tk.StringVar(value=str(self.config_data.get("network_proxy_host", ""))),
            "network_proxy_port": tk.StringVar(value=str(self.config_data.get("network_proxy_port", ""))),
            "network_pac_url": tk.StringVar(value=str(self.config_data.get("network_pac_url", ""))),
            "network_proxy_bypass": tk.StringVar(value=str(self.config_data.get("network_proxy_bypass", DEFAULT_BYPASS))),
            "network_proxy_auth": tk.StringVar(value=str(self.config_data.get("network_proxy_auth", "none"))),
            "network_proxy_username": tk.StringVar(value=str(self.config_data.get("network_proxy_username", ""))),
            "network_proxy_password": tk.StringVar(value=""),
        }
        self._build()
        self._refresh_visibility()
        self.after(150, self.detect)

    def _build(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="Rede e Proxy Corporativo", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            root,
            text="Este configurador funciona antes da instalação. A interface local (localhost/127.0.0.1) nunca usa proxy.",
            wraplength=700,
        ).pack(anchor="w", pady=(4, 14))

        form = ttk.Frame(root)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.rows: dict[str, tuple[ttk.Label, tk.Widget]] = {}

        def row(index: int, key: str, label: str, widget: tk.Widget) -> None:
            lbl = ttk.Label(form, text=label)
            lbl.grid(row=index, column=0, sticky="w", padx=(0, 12), pady=6)
            widget.grid(row=index, column=1, sticky="ew", pady=6)
            self.rows[key] = (lbl, widget)

        mode = ttk.Combobox(form, textvariable=self.vars["network_mode"], state="readonly", values=("auto", "system", "manual", "pac", "direct"))
        mode.bind("<<ComboboxSelected>>", lambda _e: self._refresh_visibility())
        row(0, "mode", "Modo", mode)
        row(1, "host", "Servidor do proxy", ttk.Entry(form, textvariable=self.vars["network_proxy_host"]))
        row(2, "port", "Porta", ttk.Entry(form, textvariable=self.vars["network_proxy_port"]))
        row(3, "pac", "URL do PAC", ttk.Entry(form, textvariable=self.vars["network_pac_url"]))
        auth = ttk.Combobox(form, textvariable=self.vars["network_proxy_auth"], state="readonly", values=("none", "windows", "basic"))
        auth.bind("<<ComboboxSelected>>", lambda _e: self._refresh_visibility())
        row(4, "auth", "Autenticação", auth)
        row(5, "username", "Usuário", ttk.Entry(form, textvariable=self.vars["network_proxy_username"]))
        row(6, "password", "Senha", ttk.Entry(form, textvariable=self.vars["network_proxy_password"], show="•"))
        row(7, "bypass", "Ignorar proxy para", ttk.Entry(form, textvariable=self.vars["network_proxy_bypass"]))

        actions = ttk.Frame(root)
        actions.pack(fill="x", pady=(14, 8))
        ttk.Button(actions, text="Detectar proxy", command=self.detect).pack(side="left")
        ttk.Button(actions, text="Testar conexão", command=self.test).pack(side="left", padx=8)
        ttk.Button(actions, text="Salvar", command=self.save).pack(side="right")

        self.status = tk.Text(root, height=12, wrap="word", state="disabled")
        self.status.pack(fill="both", expand=True, pady=(8, 0))

    def _show_row(self, key: str, visible: bool) -> None:
        label, widget = self.rows[key]
        if visible:
            label.grid()
            widget.grid()
        else:
            label.grid_remove()
            widget.grid_remove()

    def _refresh_visibility(self) -> None:
        mode = self.vars["network_mode"].get()
        auth = self.vars["network_proxy_auth"].get()
        self._show_row("host", mode == "manual")
        self._show_row("port", mode == "manual")
        self._show_row("pac", mode == "pac")
        self._show_row("username", auth == "basic")
        self._show_row("password", auth == "basic")

    def _write_status(self, text: str) -> None:
        self.status.configure(state="normal")
        self.status.delete("1.0", "end")
        self.status.insert("1.0", text)
        self.status.configure(state="disabled")

    def detect(self) -> None:
        try:
            value = detect_system_proxy()
            lines = [
                f"Origem detectada: {value.get('source')}",
                f"Proxy HTTPS: {value.get('https_proxy') or 'não informado'}",
                f"Proxy HTTP: {value.get('http_proxy') or 'não informado'}",
                f"PAC: {value.get('pac_url') or 'não informado'}",
                f"WPAD/autodetecção: {'sim' if value.get('auto_detect') else 'não'}",
                f"Bypass: {value.get('bypass') or DEFAULT_BYPASS}",
            ]
            self._write_status("\n".join(lines))
        except Exception as error:
            self._write_status(f"Falha na detecção: {error}")

    def _payload(self) -> dict:
        payload = {key: var.get().strip() for key, var in self.vars.items()}
        if payload["network_mode"] == "manual":
            if not payload["network_proxy_host"]:
                raise ValueError("Informe o servidor do proxy manual.")
            port = int(payload["network_proxy_port"])
            if not 1 <= port <= 65535:
                raise ValueError("A porta deve ficar entre 1 e 65535.")
            payload["network_proxy_port"] = str(port)
        if payload["network_mode"] == "pac" and not payload["network_pac_url"]:
            raise ValueError("Informe a URL do PAC.")
        rules = [item.strip() for item in payload["network_proxy_bypass"].replace(",", ";").split(";") if item.strip()]
        for mandatory in ("localhost", "127.0.0.1", "::1"):
            if mandatory not in rules:
                rules.append(mandatory)
        payload["network_proxy_bypass"] = ";".join(rules)
        return payload

    def save(self, quiet: bool = False) -> bool:
        try:
            payload = self._payload()
            password = payload.pop("network_proxy_password", "")
            for key, value in payload.items():
                self.config_data[key] = value
            save_config(self.config_data)
            cred_path = credential_path_for_config()
            if password:
                save_proxy_credentials(payload.get("network_proxy_username", ""), password, cred_path)
                self.vars["network_proxy_password"].set("")
            elif payload.get("network_proxy_auth") != "basic":
                clear_proxy_credentials(cred_path)
            if not quiet:
                messagebox.showinfo(APP_NAME, "Configuração de rede salva. Agora o instalador e o programa podem usar esse proxy.")
            return True
        except Exception as error:
            if not quiet:
                messagebox.showerror(APP_NAME, str(error))
            return False

    def test(self) -> None:
        if not self.save(quiet=True):
            return
        self._write_status("Testando rede…")

        def worker() -> None:
            try:
                result = test_network(load_config(), timeout=8)
                lines = [f"Proxy efetivo: {result.get('proxy', {}).get('proxy') or result.get('proxy', {}).get('source', 'direto')}"]
                for item in result.get("tests", []):
                    prefix = "OK" if item.get("ok") else "FALHA"
                    lines.append(f"{prefix} — {item.get('name')}: {item.get('detail', '')}")
                self.after(0, lambda: self._write_status("\n".join(lines)))
            except Exception as error:
                self.after(0, lambda: self._write_status(f"Falha no teste: {error}"))

        threading.Thread(target=worker, daemon=True).start()


def main() -> int:
    ProxySetup().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
