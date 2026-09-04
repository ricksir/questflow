from __future__ import annotations

"""Configurador independente do Turso Cloud para QuestFlow Studio 5.4.0.

Não depende do SDK nativo do Turso. O runtime do QuestFlow usa o endpoint oficial
SQL-over-HTTP, de modo que a mesma camada de proxy/PAC/TLS usada pelo Telegram e
Google também é usada para o Cloud Sync.
"""

import os
import socket
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from app_shared import APP_VERSION, CONFIG_PATH, load_config, save_config
from core.cloud_sync import TursoHttpClient, load_turso_token, save_turso_token
from core.network import NetworkManager


OFFICIAL_COMMANDS = r"""WINDOWS / WSL — criação inicial do Turso

1. Se ainda não tiver WSL, em PowerShell como administrador:
   wsl --install
   (reinicie o Windows se ele solicitar)

2. Abra o WSL e instale o Turso CLI:
   curl -sSfL https://get.tur.so/install.sh | bash
   exec $SHELL -l

3. Entre ou crie sua conta:
   turso auth login
   ou, em ambiente sem navegador:
   turso auth signup --headless

4. Crie o banco do QuestFlow:
   turso db create questflow

5. Obtenha a URL HTTP do banco:
   turso db show questflow --http-url

6. Crie um token exclusivo para esse banco:
   turso db tokens create questflow

Cole a URL e o token nesta janela. Depois disso o Turso CLI NÃO precisa ficar
aberto nem instalado para o QuestFlow sincronizar: o programa fala com o Turso
Cloud por HTTPS e usa seu Gerenciador de Rede/Proxy.
"""


class TursoSetup(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"QuestFlow Studio {APP_VERSION} — Configurar Turso Cloud")
        self.geometry("880x720")
        self.minsize(760, 620)
        self.config_data = load_config()
        self._build()
        self._load()

    def _build(self) -> None:
        container = ttk.Frame(self, padding=18)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="QuestFlow Cloud Sync — Turso", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            container,
            text="Configure uma única vez em cada computador. A senha/token é protegida pelo usuário do Windows (DPAPI).",
            wraplength=820,
        ).pack(anchor="w", pady=(4, 14))

        form = ttk.LabelFrame(container, text="Credenciais do banco", padding=12)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="URL Turso / HTTPS:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=6)
        self.url = ttk.Entry(form)
        self.url.grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Label(form, text="Token do banco:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=6)
        self.token = ttk.Entry(form, show="•")
        self.token.grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(form, text="Nome deste computador:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=6)
        self.device = ttk.Entry(form)
        self.device.grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Label(form, text="Intervalo (segundos):").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=6)
        self.interval = ttk.Spinbox(form, from_=10, to=900, width=12)
        self.interval.grid(row=3, column=1, sticky="w", pady=6)
        self.enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="Ativar Cloud Sync neste computador", variable=self.enabled).grid(row=4, column=0, columnspan=2, sticky="w", pady=6)

        buttons = ttk.Frame(container)
        buttons.pack(fill="x", pady=12)
        ttk.Button(buttons, text="Testar conexão", command=self.test_connection).pack(side="left")
        ttk.Button(buttons, text="Salvar configuração", command=self.save).pack(side="left", padx=8)
        ttk.Button(buttons, text="Mostrar comandos do Turso", command=self.show_commands).pack(side="left")

        self.status = ttk.Label(container, text="Pronto para configurar.", wraplength=820)
        self.status.pack(fill="x", pady=(0, 10))

        guide = ttk.LabelFrame(container, text="Instalação/criação inicial", padding=10)
        guide.pack(fill="both", expand=True)
        self.instructions = tk.Text(guide, wrap="word", height=18, font=("Consolas", 10))
        self.instructions.pack(fill="both", expand=True)
        self.instructions.insert("1.0", OFFICIAL_COMMANDS)
        self.instructions.configure(state="disabled")

    def _load(self) -> None:
        self.url.insert(0, str(self.config_data.get("cloud_turso_url", "") or ""))
        existing = load_turso_token(CONFIG_PATH)
        if existing:
            self.token.insert(0, existing)
        self.device.insert(0, str(self.config_data.get("cloud_device_name") or os.environ.get("COMPUTERNAME") or socket.gethostname()))
        self.interval.insert(0, str(self.config_data.get("cloud_sync_interval_seconds", 30) or 30))
        self.enabled.set(bool(self.config_data.get("cloud_sync_enabled", False)))

    def _network(self) -> NetworkManager:
        latest = load_config()
        return NetworkManager(latest, config_path=CONFIG_PATH)

    def test_connection(self) -> None:
        url = self.url.get().strip()
        token = self.token.get().strip() or load_turso_token(CONFIG_PATH)
        if not url or not token:
            messagebox.showwarning("Turso", "Informe a URL e o token do banco.")
            return
        self.status.configure(text="Testando Turso pela configuração de rede/proxy do QuestFlow...")
        self.update_idletasks()
        try:
            client = TursoHttpClient(url, token, network_manager=self._network(), timeout=15)
            result = client.test()
        except Exception as error:
            self.status.configure(text=f"Falha: {error}")
            messagebox.showerror("Teste do Turso", str(error))
            return
        self.status.configure(text=f"Conectado. Geração remota {result.get('generation', 1)} · {result.get('elapsed_ms', 0)} ms")
        messagebox.showinfo("Turso", "Conexão com o Turso Cloud concluída com sucesso.")

    def save(self) -> None:
        url = self.url.get().strip()
        token = self.token.get().strip()
        if self.enabled.get() and (not url or not token and not load_turso_token(CONFIG_PATH)):
            messagebox.showwarning("Turso", "Para ativar, informe URL e token do banco.")
            return
        try:
            interval = min(900, max(10, int(self.interval.get() or 30)))
        except ValueError:
            interval = 30
        cfg = load_config()
        cfg.update(
            {
                "cloud_sync_enabled": bool(self.enabled.get()),
                "cloud_turso_url": url,
                "cloud_device_name": self.device.get().strip() or socket.gethostname(),
                "cloud_sync_interval_seconds": interval,
                "cloud_sync_timeout_seconds": int(cfg.get("cloud_sync_timeout_seconds", 15) or 15),
                "cloud_sync_on_start": True,
                "cloud_sync_on_shutdown": True,
            }
        )
        save_config(cfg)
        if token:
            try:
                save_turso_token(CONFIG_PATH, token)
            except Exception as error:
                messagebox.showerror("Credencial", f"Não foi possível proteger o token pelo Windows: {error}")
                return
        self.config_data = cfg
        self.status.configure(text="Configuração salva. Abra o QuestFlow e use Configurações → Cloud Sync → Preparar/Sincronizar.")
        messagebox.showinfo("QuestFlow", "Configuração do Turso salva.")

    def show_commands(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Comandos oficiais do Turso")
        dialog.geometry("820x600")
        text = tk.Text(dialog, wrap="word", font=("Consolas", 10))
        text.pack(fill="both", expand=True, padx=12, pady=12)
        text.insert("1.0", OFFICIAL_COMMANDS)
        text.configure(state="disabled")


def main() -> int:
    if sys.version_info < (3, 11):
        print("QuestFlow 5.4.0 requer Python 3.11 ou superior.")
        return 2
    app = TursoSetup()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
