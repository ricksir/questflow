from __future__ import annotations

from .common import *  # noqa: F401,F403


class SettingsExportMixin:
    def _build_export_page(self) -> tk.Frame:
        page = self._page()
        container = tk.Frame(page, bg=COLORS["background"])
        container.pack(fill="both", expand=True, padx=24, pady=20)
        self._section_title(
            container,
            "Backup, migração e exportação",
            "O banco já é usado diretamente pelo fluxo Telegram; as exportações ficam disponíveis para cópia e compatibilidade.",
        )
        self._build_stat_cards(container)

        columns = tk.Frame(container, bg=COLORS["background"])
        columns.pack(fill="both", expand=True)
        left = self._surface(columns, side="left", fill="both", expand=True, padx=(0, 8))
        right = self._surface(columns, side="left", fill="both", expand=True, padx=(8, 0))

        self._card_title(left, "Pacote do banco")
        tk.Label(
            left,
            text="Você não precisa mais importar a base em outro programa. Use esta área para migrar o banco antigo, criar cópias de segurança ou exportar os dados em JSON e CSV.",
            bg="#FFFFFF",
            fg=COLORS["muted"],
            justify="left",
            wraplength=480,
        ).pack(anchor="w", padx=18, pady=(0, 15))
        self.export_approved_var = tk.BooleanVar(value=bool(self.config_data.get("approved_only_export")))
        ttk.Checkbutton(left, text="Exportar somente questões aprovadas", variable=self.export_approved_var).pack(anchor="w", padx=18, pady=(0, 10))
        ttk.Button(left, text="Exportar para QuestFlow (.JSON NATIVO)", style="Primary.TButton", command=self.export_qflow).pack(fill="x", padx=18, pady=5)
        ttk.Button(left, text="Exportar backup completo (.QFLOWPKG)", command=self.export_qflow_package_file).pack(fill="x", padx=18, pady=5)
        ttk.Button(left, text="Exportar JSON técnico completo", command=self.export_json_file).pack(fill="x", padx=18, pady=5)
        ttk.Button(left, text="Exportar CSV", command=self.export_csv_file).pack(fill="x", padx=18, pady=5)
        ttk.Button(left, text="Fazer backup do banco SQLite", command=self.backup_database).pack(fill="x", padx=18, pady=5)
        ttk.Button(left, text="Migrar banco do PDF Importer (.SQLITE)", style="Success.TButton", command=self.migrate_importer_database).pack(fill="x", padx=18, pady=5)
        ttk.Separator(left).pack(fill="x", padx=18, pady=15)
        ttk.Button(left, text="Importar banco salvo (JSON/QFLOW/QFLOWPKG)", style="Success.TButton", command=self.import_qflow).pack(fill="x", padx=18, pady=5)
        ttk.Button(left, text="Converter base antiga para JSON QuestFlow", command=self.convert_qflow_file).pack(fill="x", padx=18, pady=(5, 18))

        self._card_title(right, "Envio manual ao Telegram")
        tk.Label(
            right,
            text="Use a questão selecionada na aba Revisar. O envio é feito como enquete do tipo quiz, com a alternativa correta marcada pelo gabarito.",
            bg="#FFFFFF",
            fg=COLORS["muted"],
            justify="left",
            wraplength=480,
        ).pack(anchor="w", padx=18, pady=(0, 15))
        self.telegram_selected_label = tk.Label(
            right,
            text="Nenhuma questão selecionada",
            bg="#EFF5FB",
            fg=COLORS["navy"],
            justify="left",
            anchor="w",
            padx=12,
            pady=10,
            wraplength=480,
        )
        self.telegram_selected_label.pack(fill="x", padx=18, pady=(0, 12))
        ttk.Button(right, text="Enviar questão selecionada como quiz", style="Primary.TButton", command=self.send_selected_to_telegram).pack(fill="x", padx=18, pady=5)
        ttk.Button(right, text="Abrir configurações do bot", command=lambda: self.show_page("settings")).pack(fill="x", padx=18, pady=5)
        tk.Label(
            right,
            text="O token e o Chat ID ficam apenas no arquivo local data/config.json.",
            bg="#FFFFFF",
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=18, pady=12)
        return page

    def _card_title(self, parent: tk.Widget, title: str) -> None:
        tk.Label(parent, text=title, bg="#FFFFFF", fg=COLORS["text"], font=("Segoe UI Semibold", 15)).pack(anchor="w", padx=18, pady=(18, 8))

    def _build_settings_page(self) -> tk.Frame:
        page = self._page()
        container = tk.Frame(page, bg=COLORS["background"])
        container.pack(fill="both", expand=True, padx=24, pady=20)
        self._section_title(
            container,
            "Configurações",
            "Ajuste o OCR, a taxonomia da planilha AFRFB e a conexão do bot do Telegram.",
        )
        surface = self._surface(container, fill="both", expand=True)
        canvas = tk.Canvas(surface, bg="#FFFFFF", highlightthickness=0)
        scroll = ttk.Scrollbar(surface, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg="#FFFFFF")
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(1, width=e.width))

        content = tk.Frame(inner, bg="#FFFFFF")
        content.pack(fill="x", padx=22, pady=20)
        self.setting_vars: dict[str, tk.StringVar] = {
            "dpi": tk.StringVar(value=str(self.config_data.get("dpi", 180))),
            "languages": tk.StringVar(value=str(self.config_data.get("languages", "por+eng"))),
            "tesseract_cmd": tk.StringVar(value=str(self.config_data.get("tesseract_cmd", ""))),
            "telegram_bot_token": tk.StringVar(value=str(self.config_data.get("telegram_bot_token", ""))),
            "telegram_chat_id": tk.StringVar(value=str(self.config_data.get("telegram_chat_id", ""))),
            "taxonomy_spreadsheet_url": tk.StringVar(value=str(self.config_data.get("taxonomy_spreadsheet_url", DEFAULT_SPREADSHEET_URL))),
            "network_mode": tk.StringVar(value=str(self.config_data.get("network_mode", "auto"))),
            "network_proxy_host": tk.StringVar(value=str(self.config_data.get("network_proxy_host", ""))),
            "network_proxy_port": tk.StringVar(value=str(self.config_data.get("network_proxy_port", ""))),
            "network_pac_url": tk.StringVar(value=str(self.config_data.get("network_pac_url", ""))),
            "network_proxy_bypass": tk.StringVar(value=str(self.config_data.get("network_proxy_bypass", "localhost;127.0.0.1;::1;<local>"))),
            "network_proxy_auth": tk.StringVar(value=str(self.config_data.get("network_proxy_auth", "none"))),
            "network_proxy_username": tk.StringVar(value=str(self.config_data.get("network_proxy_username", ""))),
        }
        self.appearance_vars: dict[str, tk.Variable] = {
            "ui_theme": tk.StringVar(value=str(self.config_data.get("ui_theme", "claro"))),
            "ui_accent": tk.StringVar(value=str(self.config_data.get("ui_accent", "laranja"))),
            "ui_scale": tk.StringVar(value=str(self.config_data.get("ui_scale", 1.0))),
            "ui_density": tk.StringVar(value=str(self.config_data.get("ui_density", "confortavel"))),
            "ui_sidebar_width": tk.StringVar(value=str(self.config_data.get("ui_sidebar_width", 210))),
            "web_enrichment_enabled": tk.BooleanVar(value=bool(self.config_data.get("web_enrichment_enabled", False))),
            "web_enrichment_max_per_run": tk.StringVar(value=str(self.config_data.get("web_enrichment_max_per_run", 10))),
            "markdown_force_ocr_pending": tk.BooleanVar(value=bool(self.config_data.get("markdown_force_ocr_pending", True))),
            "deep_analysis_dpi": tk.StringVar(value=str(self.config_data.get("deep_analysis_dpi", 300))),
        }

        tk.Label(content, text="APARÊNCIA E LAYOUT", bg="#FFFFFF", fg=COLORS["navy"], font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(0, 5))
        appearance_grid = tk.Frame(content, bg="#FFFFFF")
        appearance_grid.pack(fill="x", pady=(0, 8))
        appearance_fields = [
            ("ui_theme", "Tema", ["claro", "escuro", "alto_contraste"]),
            ("ui_accent", "Cor de destaque", list(ACCENT_PRESETS)),
            ("ui_scale", "Escala da interface", ["0.80", "0.90", "1.00", "1.10", "1.20", "1.35", "1.50"]),
            ("ui_density", "Densidade", ["compacta", "confortavel", "ampla"]),
            ("ui_sidebar_width", "Largura do menu", ["180", "210", "240", "280", "320"]),
        ]
        for index, (key, label, values) in enumerate(appearance_fields):
            row, col = divmod(index, 2)
            field = tk.Frame(appearance_grid, bg="#FFFFFF")
            field.grid(row=row, column=col, sticky="ew", padx=(0 if col == 0 else 8, 8 if col == 0 else 0), pady=5)
            appearance_grid.grid_columnconfigure(col, weight=1)
            tk.Label(field, text=label, bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w")
            ttk.Combobox(field, textvariable=self.appearance_vars[key], values=values, state="normal").pack(fill="x", pady=(2, 0))
        tk.Label(
            content,
            text="Tema, cor e densidade são aplicados completamente ao reiniciar. A escala e o menu lateral podem ser ajustados também pelo cabeçalho.",
            bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 8), wraplength=900, justify="left",
        ).pack(anchor="w", pady=(0, 8))

        ttk.Separator(content).pack(fill="x", pady=16)
        tk.Label(content, text="OCR E MARKDOWN DOS PDFs", bg="#FFFFFF", fg=COLORS["navy"], font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(0, 5))
        self._setting_row(content, "Resolução OCR (DPI)", "180 é o equilíbrio recomendado para os PDFs do QConcursos.", "dpi")
        self._setting_row(content, "Idiomas do OCR", "Use por+eng para textos em português com siglas e termos em inglês.", "languages")

        row = tk.Frame(content, bg="#FFFFFF")
        row.pack(fill="x", pady=8)
        row.grid_columnconfigure(0, weight=0, minsize=300)
        row.grid_columnconfigure(1, weight=1)
        label = tk.Frame(row, bg="#FFFFFF")
        label.grid(row=0, column=0, sticky="nw", padx=(0, 14))
        tk.Label(label, text="Executável do Tesseract", bg="#FFFFFF", fg=COLORS["text"], font=("Segoe UI Semibold", 10)).pack(anchor="w")
        tk.Label(label, text="Deixe vazio para detecção automática.", bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 8), wraplength=290, justify="left").pack(anchor="w", pady=(2, 0))
        input_box = tk.Frame(row, bg="#FFFFFF")
        input_box.grid(row=0, column=1, sticky="ew")
        input_box.grid_columnconfigure(0, weight=1)
        ttk.Entry(input_box, textvariable=self.setting_vars["tesseract_cmd"]).grid(row=0, column=0, sticky="ew")
        ttk.Button(input_box, text="Procurar", command=self.browse_tesseract).grid(row=0, column=1, padx=(8, 0))

        ttk.Separator(content).pack(fill="x", pady=16)
        tk.Label(content, text="ESTUDOS E TRILHAS", bg="#FFFFFF", fg=COLORS["navy"], font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(0, 5))
        tk.Label(content, text="Planilha de estudos e trilhas", bg="#FFFFFF", fg=COLORS["text"], font=("Segoe UI Semibold", 14)).pack(anchor="w", pady=(0, 4))
        tk.Label(
            content,
            text="A planilha atualiza a estrutura do curso. O progresso que o QuestFlow já conhece fica protegido no banco e não é apagado por células vazias de uma planilha nova.",
            bg="#FFFFFF", fg=COLORS["muted"], justify="left", wraplength=860,
        ).pack(anchor="w", pady=(0, 8))
        self._setting_row(
            content,
            "Link da nova planilha",
            "Cole o Google Sheets que deseja testar. O endereço só vira a fonte ativa depois do preflight, backup e mesclagem segura. Abas aceitas: MAPA_AF/MAPA_AT/MAPA + CICLO_REG/CICLO.",
            "taxonomy_spreadsheet_url",
        )
        self.taxonomy_status_label = tk.Label(
            content, text="", bg="#EEF5FB", fg=COLORS["navy"], anchor="w", justify="left", padx=12, pady=9,
        )
        self.taxonomy_status_label.pack(fill="x", pady=(5, 8))
        taxonomy_actions = tk.Frame(content, bg="#FFFFFF")
        taxonomy_actions.pack(fill="x", pady=(0, 5))
        ttk.Button(taxonomy_actions, text="Testar planilha", command=self.test_taxonomy_spreadsheet).pack(side="left")
        ttk.Button(taxonomy_actions, text="Trocar/Atualizar planilha", style="Primary.TButton", command=self.update_taxonomy_from_internet).pack(side="left", padx=8)
        ttk.Button(taxonomy_actions, text="Importar .XLSX e mesclar", command=self.import_taxonomy_xlsx).pack(side="left")
        ttk.Button(taxonomy_actions, text="Reclassificar banco", command=self.reclassify_database).pack(side="left", padx=(8, 0))

        ttk.Separator(content).pack(fill="x", pady=16)
        tk.Label(content, text="ANÁLISE AVANÇADA E PESQUISA WEB", bg="#FFFFFF", fg=COLORS["navy"], font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(0, 5))
        ttk.Checkbutton(
            content,
            text="Permitir pesquisa Google visível para questões pendentes (abre o navegador e lê a página carregada)",
            variable=self.appearance_vars["web_enrichment_enabled"],
        ).pack(anchor="w", pady=4)
        advanced_row = tk.Frame(content, bg="#FFFFFF")
        advanced_row.pack(fill="x", pady=5)
        tk.Label(advanced_row, text="Máximo de pesquisas web por processamento", bg="#FFFFFF", fg=COLORS["muted"], width=42, anchor="w").pack(side="left")
        ttk.Entry(advanced_row, textvariable=self.appearance_vars["web_enrichment_max_per_run"], width=12).pack(side="left")
        dpi_row = tk.Frame(content, bg="#FFFFFF")
        dpi_row.pack(fill="x", pady=5)
        tk.Label(dpi_row, text="Resolução da análise apurada (DPI)", bg="#FFFFFF", fg=COLORS["muted"], width=42, anchor="w").pack(side="left")
        ttk.Entry(dpi_row, textvariable=self.appearance_vars["deep_analysis_dpi"], width=12).pack(side="left")
        source_row = tk.Frame(content, bg="#FFFFFF")
        source_row.pack(fill="x", pady=5)
        self.source_directories_label = tk.Label(
            source_row,
            text=self._source_directories_summary(),
            bg="#FFFFFF",
            fg=COLORS["muted"],
            anchor="w",
            justify="left",
            wraplength=650,
        )
        self.source_directories_label.pack(side="left", fill="x", expand=True)
        ttk.Button(source_row, text="Adicionar pasta dos PDFs", command=self.choose_source_pdf_directory).pack(side="right", padx=(8, 0))
        ttk.Checkbutton(
            content,
            text="Forçar OCR no Markdown durante a análise apurada de pendentes",
            variable=self.appearance_vars["markdown_force_ocr_pending"],
        ).pack(anchor="w", pady=4)
        tk.Label(
            content,
            text="A pesquisa abre somente o Google, lê a página renderizada e confirma código/enunciado, banca e ano antes de completar gabarito ou justificativa.",
            bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 8), wraplength=900, justify="left",
        ).pack(anchor="w", pady=(2, 6))

        ttk.Separator(content).pack(fill="x", pady=16)
        tk.Label(content, text="REDE E PROXY CORPORATIVO", bg="#FFFFFF", fg=COLORS["navy"], font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(0, 5))
        tk.Label(
            content,
            text="A interface local continua em 127.0.0.1 sem proxy. Estas opções valem apenas para Telegram, Google, Google Sheets, Selenium e instalação.",
            bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 8), wraplength=900, justify="left",
        ).pack(anchor="w", pady=(0, 6))
        self._setting_row(content, "Modo de rede", "auto, system, manual, pac ou direct.", "network_mode")
        self._setting_row(content, "Servidor do proxy", "Usado no modo manual.", "network_proxy_host")
        self._setting_row(content, "Porta do proxy", "Ex.: 8080 ou 3128.", "network_proxy_port")
        self._setting_row(content, "URL do PAC", "Usada no modo pac; no Windows o PAC/WPAD é resolvido pelo WinHTTP.", "network_pac_url")
        self._setting_row(content, "Ignorar proxy para", "localhost, 127.0.0.1 e ::1 são sempre preservados.", "network_proxy_bypass")
        self._setting_row(content, "Autenticação", "none, windows (SSO) ou basic.", "network_proxy_auth")
        self._setting_row(content, "Usuário do proxy", "A senha é configurada com segurança na interface web e protegida pelo Windows.", "network_proxy_username")
        network_tools = tk.Frame(content, bg="#FFFFFF")
        network_tools.pack(fill="x", pady=(5, 0))
        ttk.Button(network_tools, text="Detectar proxy", command=self.detect_network_proxy_classic).pack(side="left")
        ttk.Button(network_tools, text="Testar rede", command=self.test_network_classic).pack(side="left", padx=8)

        ttk.Separator(content).pack(fill="x", pady=16)
        tk.Label(content, text="TELEGRAM", bg="#FFFFFF", fg=COLORS["navy"], font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(0, 5))
        self._setting_row(content, "Token do bot do Telegram", "Token fornecido pelo BotFather.", "telegram_bot_token", secret=True)
        self._setting_row(content, "Chat ID", "Destino onde o QuestFlow enviará os quizzes.", "telegram_chat_id")
        telegram_tools = tk.Frame(content, bg="#FFFFFF")
        telegram_tools.pack(fill="x", pady=(5, 0))
        ttk.Button(
            telegram_tools,
            text="Detectar Chat ID após enviar /start ao bot",
            command=self.detect_telegram_chat_id,
        ).pack(side="left")
        ttk.Button(
            telegram_tools,
            text="Testar bot",
            command=self.test_telegram_bot,
        ).pack(side="left", padx=8)

        actions = tk.Frame(content, bg="#FFFFFF")
        actions.pack(fill="x", pady=(18, 0))
        ttk.Button(actions, text="Salvar configurações", style="Primary.TButton", command=self.save_settings).pack(side="left")
        ttk.Button(actions, text="Testar Tesseract", command=self.test_tesseract).pack(side="left", padx=8)
        ttk.Button(actions, text="Abrir pasta de dados", command=self.open_data_folder).pack(side="right")
        self.after(50, self.refresh_taxonomy_status)
        return page

    def _setting_row(self, parent: tk.Widget, title: str, help_text: str, key: str, secret: bool = False) -> None:
        row = tk.Frame(parent, bg="#FFFFFF")
        row.pack(fill="x", pady=8)
        row.grid_columnconfigure(0, weight=0, minsize=300)
        row.grid_columnconfigure(1, weight=1)
        label = tk.Frame(row, bg="#FFFFFF")
        label.grid(row=0, column=0, sticky="nw", padx=(0, 14))
        tk.Label(
            label,
            text=title,
            bg="#FFFFFF",
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 10),
            anchor="w",
            justify="left",
            wraplength=290,
        ).pack(anchor="w")
        tk.Label(
            label,
            text=help_text,
            bg="#FFFFFF",
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
            wraplength=290,
            justify="left",
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))
        ttk.Entry(row, textvariable=self.setting_vars[key], show="•" if secret else "").grid(
            row=0, column=1, sticky="ew"
        )

    def _questions_for_export(self) -> list[dict]:
        approved_only = bool(self.export_approved_var.get())
        self.config_data["approved_only_export"] = approved_only
        save_config(self.config_data)
        return self.question_queries.all(approved_only=approved_only)

    def export_qflow(self) -> None:
        questions = self._questions_for_export()
        if not questions:
            messagebox.showinfo(APP_NAME, "Não há questões para exportar.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("Base nativa do QuestFlow", "*.json")],
            initialfile="QuestFlow-base-de-questoes.json",
        )
        if path:
            output = export_qflow_bundle(questions, path, DATABASE_PATH)
            raw_payload = json.loads(Path(output).read_text(encoding="utf-8-sig"))
            errors = validate_questflow_question_bank(raw_payload)
            if errors:
                messagebox.showerror(APP_NAME, "A base foi gravada, mas falhou na validação:\n- " + "\n- ".join(errors[:20]))
                return
            exported = len(raw_payload.get("questions", []))
            skipped = len(questions) - count_exportable_questions(questions)
            message = f"Base nativa do QuestFlow criada com {exported} questões:\n{output}"
            if skipped:
                message += f"\n\n{skipped} registro(s) incompleto(s) não foram exportados."
            messagebox.showinfo(APP_NAME, message)

    def export_qflow_package_file(self) -> None:
        questions = self._questions_for_export()
        if not questions:
            messagebox.showinfo(APP_NAME, "Não há questões para exportar.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".qflowpkg",
            filetypes=[("Backup completo QuestFlow", "*.qflowpkg")],
            initialfile="QuestFlow_Backup_Completo.qflowpkg",
        )
        if path:
            output = export_qflow_package(questions, path, DATABASE_PATH)
            messagebox.showinfo(
                APP_NAME,
                f"Backup completo criado com {len(questions)} questões:\n{output}",
            )

    def convert_qflow_file(self) -> None:
        source = filedialog.askopenfilename(
            filetypes=[("Bases QuestFlow", "*.json *.qflow *.qflowpkg"), ("Todos os arquivos", "*.*")],
            title="Selecione a base antiga",
        )
        if not source:
            return
        destination = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("Base nativa do QuestFlow", "*.json")],
            initialfile="QuestFlow-base-de-questoes-COMPATIVEL.json",
        )
        if not destination:
            return
        try:
            output = convert_legacy_qflow(source, destination)
            converted = import_qflow_bundle(output)
        except Exception as error:
            messagebox.showerror(APP_NAME, str(error))
            return
        exported = len(converted.get("questions", []))
        message = f"Conversão concluída no formato nativo do QuestFlow: {exported} questões exportadas.\n{output}"
        messagebox.showinfo(APP_NAME, message)

    def export_json_file(self) -> None:
        questions = self._questions_for_export()
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")], initialfile="QuestFlow_Questoes.json")
        if path:
            export_json(questions, path)
            messagebox.showinfo(APP_NAME, f"JSON exportado com {len(questions)} questões.")

    def export_csv_file(self) -> None:
        questions = self._questions_for_export()
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="QuestFlow_Questoes.csv")
        if path:
            export_csv(questions, path)
            messagebox.showinfo(APP_NAME, f"CSV exportado com {len(questions)} questões.")

    def backup_database(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".sqlite", filetypes=[("Banco SQLite", "*.sqlite")], initialfile="QuestFlow_Backup.sqlite")
        if path:
            self.question_commands.backup(path)
            messagebox.showinfo(APP_NAME, f"Backup salvo em:\n{path}")

    def offer_legacy_database_migration(self) -> None:
        try:
            if self.question_queries.stats().get("total", 0) > 0:
                return
            candidates = []
            for pattern in ("QuestFlow_PDF_Importer*/data/questflow_questions.sqlite", "QuestFlow_PDF_Importer/data/questflow_questions.sqlite"):
                candidates.extend(BASE_DIR.parent.glob(pattern))
            candidates = [path for path in candidates if path.resolve() != DATABASE_PATH.resolve() and path.is_file()]
            if not candidates:
                return
            source = max(candidates, key=lambda path: path.stat().st_mtime)
        except Exception:
            return
        if not messagebox.askyesno(
            APP_NAME,
            "Foi encontrado um banco do QuestFlow PDF Importer na pasta ao lado:\n\n"
            f"{source}\n\nDeseja migrar as questões automaticamente para o QuestFlow Studio?",
        ):
            return
        try:
            result = self.question_commands.import_database(source)
            self.study.sync_questions()
            self.refresh_all()
        except Exception as error:
            messagebox.showerror(APP_NAME, f"A migração automática falhou:\n{error}")
            return
        messagebox.showinfo(
            APP_NAME,
            f"Migração automática concluída: {result.get('inserted', 0)} questão(ões) nova(s) e "
            f"{result.get('duplicates', 0)} duplicata(s) ignorada(s).",
        )

    def migrate_importer_database(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecionar banco do QuestFlow PDF Importer",
            filetypes=[("Banco SQLite", "*.sqlite *.db"), ("Todos os arquivos", "*.*")],
        )
        if not path:
            return
        try:
            result = self.question_commands.import_database(path)
            self.study.sync_questions()
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Não foi possível migrar o banco:\n{error}")
            return
        self.refresh_all()
        message = (
            f"Migração concluída.\n\n"
            f"Registros encontrados: {result.get('source_total', 0)}\n"
            f"Questões novas: {result.get('inserted', 0)}\n"
            f"Duplicatas ignoradas: {result.get('duplicates', 0)}"
        )
        if result.get("invalid"):
            message += f"\nRegistros inválidos ignorados: {result['invalid']}"
        messagebox.showinfo(APP_NAME, message)

    def import_qflow(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Bases QuestFlow", "*.json *.qflow *.qflowpkg"), ("JSON", "*.json"), ("Todos os arquivos", "*.*")])
        if not path:
            return
        try:
            payload = import_qflow_bundle(path)
            result = self.question_commands.import_extraction({"source_file": Path(path).name, "questions": payload.get("questions", []), "schema": payload.get("schema")})
        except Exception as error:
            messagebox.showerror(APP_NAME, str(error))
            return
        self.study.sync_questions()
        self.refresh_all()
        messagebox.showinfo(APP_NAME, f"Importação concluída: {result['inserted']} novas e {result['duplicates']} duplicatas ignoradas.")

    def update_telegram_selection(self) -> None:
        if not hasattr(self, "telegram_selected_label"):
            return
        question = self.question_queries.get(self.current_question_uid) if self.current_question_uid else None
        if not question:
            self.telegram_selected_label.configure(text="Nenhuma questão selecionada na aba Revisar.")
            return
        preview = question.get("enunciado", "")
        if len(preview) > 250:
            preview = preview[:247] + "..."
        self.telegram_selected_label.configure(text=f"{question.get('codigo_origem', '')} • {question.get('banca', '')} • {question.get('ano', '')}\n{preview}")

    def send_selected_to_telegram(self) -> None:
        if not self.current_question_uid:
            messagebox.showinfo(APP_NAME, "Selecione uma questão na aba Revisar.")
            return
        question = self.question_queries.get(self.current_question_uid)
        if not question:
            return
        token = str(self.config_data.get("telegram_bot_token", ""))
        chat_id = str(self.config_data.get("telegram_chat_id", ""))
        import uuid as _uuid
        cycle_id = f"manual-{_uuid.uuid4()}"
        try:
            attempts = max(1, min(8, int(self.config_data.get("flow_question_retry_attempts", 3) or 3)))
            result = send_quiz_with_retry(token, chat_id, question, attempts=attempts)
            self.study.record_delivery(
                self.current_question_uid,
                chat_id,
                result,
                cycle_id,
                attempt_count=int(result.get("_attempt_count", 1) or 1),
            )
        except Exception as error:
            parsed = classify_exception(error)
            retry_minutes = max(1, min(1440, int(self.config_data.get("flow_retry_minutes", 10) or 10)))
            from datetime import datetime, timedelta, timezone
            next_retry = None
            if parsed.retryable and bool(self.config_data.get("flow_auto_retry_failed", True)):
                next_retry = (datetime.now(timezone.utc) + timedelta(minutes=retry_minutes)).replace(microsecond=0).isoformat()
            self.study.record_delivery_error(
                self.current_question_uid,
                chat_id,
                str(parsed),
                cycle_id,
                category=parsed.category,
                retryable=parsed.retryable,
                next_retry_at=next_retry,
                attempt_count=attempts,
            )
            self.refresh_flow_dashboard()
            messagebox.showerror(
                APP_NAME,
                f"A questão não foi enviada. O motivo foi registrado no histórico.\n\n{parsed}",
            )
            return
        self.refresh_flow_dashboard()
        messagebox.showinfo(APP_NAME, "Quiz enviado ao Telegram e registrado no histórico.")

    def detect_telegram_chat_id(self) -> None:
        token = self.setting_vars["telegram_bot_token"].get().strip()
        if not token:
            messagebox.showinfo(APP_NAME, "Informe primeiro o token do bot.")
            return
        try:
            updates = get_updates(token, timeout=0, allowed_updates=["message"])
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Não foi possível consultar as mensagens do bot:\n{error}")
            return
        chats: list[tuple[str, str]] = []
        seen: set[str] = set()
        for update in reversed(updates):
            message = update.get("message") or update.get("edited_message") or {}
            chat = message.get("chat") or {}
            chat_id = str(chat.get("id", "") or "")
            if not chat_id or chat_id in seen:
                continue
            seen.add(chat_id)
            name = str(chat.get("title") or chat.get("username") or chat.get("first_name") or "Chat")
            chats.append((chat_id, name))
        if not chats:
            messagebox.showinfo(
                APP_NAME,
                "Nenhuma conversa foi encontrada. Abra o bot no Telegram, envie /start e clique novamente.",
            )
            return
        chat_id, name = chats[0]
        self.setting_vars["telegram_chat_id"].set(chat_id)
        self.config_data["telegram_chat_id"] = chat_id
        self.config_data["telegram_bot_token"] = token
        try:
            from core.telegram_secrets import save_telegram_token
            save_telegram_token(CONFIG_PATH, token)
        except Exception:
            pass
        save_config(self.config_data)
        messagebox.showinfo(APP_NAME, f"Chat encontrado: {name}\nID: {chat_id}")

    def _source_directories_summary(self) -> str:
        directories = list(self.config_data.get("source_pdf_directories", []) or [])
        if not directories:
            return "Pastas adicionais dos PDFs: nenhuma. Durante a análise, o programa também procura em Downloads e Documentos."
        return "Pastas adicionais dos PDFs: " + " | ".join(str(item) for item in directories[:4])

    def choose_source_pdf_directory(self) -> None:
        directory = filedialog.askdirectory(title="Adicionar pasta raiz dos PDFs originais")
        if not directory:
            return
        resolved = str(Path(directory).resolve())
        directories = list(self.config_data.get("source_pdf_directories", []) or [])
        if resolved not in directories:
            directories.insert(0, resolved)
        self.config_data["source_pdf_directories"] = directories[:10]
        save_config(self.config_data)
        if hasattr(self, "source_directories_label"):
            self.source_directories_label.configure(text=self._source_directories_summary())

    def detect_network_proxy_classic(self) -> None:
        try:
            from core.network import detect_system_proxy
            detected = detect_system_proxy()
            proxy = detected.get("https_proxy") or detected.get("http_proxy") or "conexão direta"
            pac = detected.get("pac_url") or "não informado"
            messagebox.showinfo(
                APP_NAME,
                f"Origem: {detected.get('source', 'desconhecida')}\nProxy: {proxy}\nPAC: {pac}\nAutodetecção/WPAD: {'sim' if detected.get('auto_detect') else 'não'}",
            )
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Não foi possível detectar o proxy: {error}")

    def test_network_classic(self) -> None:
        self.save_settings(silent=True)
        try:
            from core.network import test_network
            result = test_network(self.config_data, timeout=8)
            lines = [f"{'OK' if item.get('ok') else 'FALHA'} - {item.get('name')}: {item.get('detail', '')}" for item in result.get('tests', [])]
            messagebox.showinfo(APP_NAME, "Diagnóstico de rede\n\n" + "\n".join(lines))
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Falha no diagnóstico de rede: {error}")

    def browse_tesseract(self) -> None:
        path = filedialog.askopenfilename(title="Localizar tesseract.exe", filetypes=[("Tesseract", "tesseract.exe"), ("Executáveis", "*.exe"), ("Todos", "*.*")])
        if path:
            self.setting_vars["tesseract_cmd"].set(path)

    def save_settings(self, silent: bool = False) -> None:
        try:
            dpi = int(self.setting_vars["dpi"].get())
            if dpi < 120 or dpi > 400:
                raise ValueError("O DPI deve ficar entre 120 e 400.")
            scale = float(self.appearance_vars["ui_scale"].get())
            if not 0.75 <= scale <= 1.60:
                raise ValueError("A escala da interface deve ficar entre 0,75 e 1,60.")
            sidebar_width = int(self.appearance_vars["ui_sidebar_width"].get())
            if not 160 <= sidebar_width <= 420:
                raise ValueError("A largura do menu deve ficar entre 160 e 420 pixels.")
            web_limit = int(self.appearance_vars["web_enrichment_max_per_run"].get())
            if not 0 <= web_limit <= 100:
                raise ValueError("O limite de pesquisas web deve ficar entre 0 e 100.")
            deep_dpi = int(self.appearance_vars["deep_analysis_dpi"].get())
            if not 220 <= deep_dpi <= 400:
                raise ValueError("O DPI da análise apurada deve ficar entre 220 e 400.")
        except (ValueError, TypeError) as error:
            if not silent:
                messagebox.showerror(APP_NAME, str(error))
            return
        for key, variable in self.setting_vars.items():
            # 6.15.0: a URL digitada é apenas candidata. A fonte ativa só muda
            # depois de preflight + backup + mesclagem segura.
            if key == "taxonomy_spreadsheet_url":
                continue
            self.config_data[key] = variable.get().strip()
        self.config_data["dpi"] = dpi
        self.config_data.update(
            {
                "ui_theme": str(self.appearance_vars["ui_theme"].get()).strip(),
                "ui_accent": str(self.appearance_vars["ui_accent"].get()).strip(),
                "ui_scale": scale,
                "ui_density": str(self.appearance_vars["ui_density"].get()).strip(),
                "ui_sidebar_width": sidebar_width,
                "web_enrichment_enabled": bool(self.appearance_vars["web_enrichment_enabled"].get()),
                "web_enrichment_max_per_run": web_limit,
                "markdown_force_ocr_pending": bool(self.appearance_vars["markdown_force_ocr_pending"].get()),
                "deep_analysis_dpi": deep_dpi,
            }
        )
        try:
            from core.telegram_secrets import save_telegram_token
            if self.config_data.get("telegram_bot_token"):
                save_telegram_token(CONFIG_PATH, str(self.config_data.get("telegram_bot_token") or ""))
        except Exception:
            pass
        save_config(self.config_data)
        if self.config_data.get("telegram_bot_token") and self.config_data.get("telegram_chat_id"):
            self.flow_engine.start(start_listener=True)
        self._apply_sidebar_state()
        if hasattr(self, "ui_scale_label"):
            self.ui_scale_label.configure(text=f"{scale*100:.0f}%")
        self._apply_live_ui_scale()
        if not silent:
            messagebox.showinfo(
                APP_NAME,
                "Configurações salvas. Tema, cor e densidade serão aplicados completamente na próxima abertura.",
            )

    def test_tesseract(self) -> None:
        self.save_settings(silent=True)
        try:
            path = configure_tesseract(str(self.config_data.get("tesseract_cmd", "")))
        except Exception as error:
            messagebox.showerror(APP_NAME, str(error))
            return
        messagebox.showinfo(APP_NAME, f"Tesseract localizado e pronto:\n{path}")

    def open_data_folder(self) -> None:
        path = str(DATA_DIR.resolve())
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception:
            messagebox.showinfo(APP_NAME, path)

