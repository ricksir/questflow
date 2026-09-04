from __future__ import annotations

from .common import *  # noqa: F401,F403


class FlowMixin:
    def _build_flow_page(self) -> tk.Frame:
        page = self._page()
        container = tk.Frame(page, bg=COLORS["background"])
        container.pack(fill="both", expand=True, padx=24, pady=20)
        self._section_title(
            container,
            "Ciclo diário inteligente para carreiras de Auditor",
            "Usa FSRS 6, alterna matérias/aulas/assuntos estudados e aprende com seu histórico real de recuperação.",
        )

        stats_row = tk.Frame(container, bg=COLORS["background"])
        stats_row.pack(fill="x", pady=(0, 12))
        self.flow_stat_labels: dict[str, tk.Label] = {}
        for key, label, color in [
            ("sent", "Questões enviadas", COLORS["navy"]),
            ("attempts", "Respostas", COLORS["orange_dark"]),
            ("correct", "Acertos", COLORS["green"]),
            ("wrong", "Erros", COLORS["red"]),
            ("accuracy", "Desempenho", COLORS["yellow"]),
        ]:
            card = tk.Frame(stats_row, bg="#FFFFFF", highlightbackground=COLORS["border"], highlightthickness=1)
            card.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Frame(card, bg=color, width=5).pack(side="left", fill="y")
            box = tk.Frame(card, bg="#FFFFFF")
            box.pack(side="left", padx=11, pady=8)
            value = tk.Label(box, text="0", bg="#FFFFFF", fg=color, font=("Segoe UI Semibold", 16))
            value.pack(anchor="w")
            tk.Label(box, text=label, bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w")
            self.flow_stat_labels[key] = value

        split = tk.PanedWindow(container, orient="horizontal", bg=COLORS["background"], sashwidth=8, relief="flat", sashrelief="raised")
        self.flow_split = split
        split.pack(fill="both", expand=True)
        left = tk.Frame(split, bg="#FFFFFF", highlightbackground=COLORS["border"], highlightthickness=1)
        right = tk.Frame(split, bg="#FFFFFF", highlightbackground=COLORS["border"], highlightthickness=1)
        split.add(left, minsize=420, width=620, stretch="always")
        split.add(right, minsize=420, stretch="always")
        def restore_flow_sash() -> None:
            try:
                ratio = float(self.config_data.get("flow_sash_ratio", 0.52) or 0.52)
                split.sash_place(0, max(360, int(split.winfo_width() * ratio)), 0)
            except Exception:
                pass
        self.after(180, restore_flow_sash)

        left_canvas = tk.Canvas(left, bg="#FFFFFF", highlightthickness=0)
        left_scroll = ttk.Scrollbar(left, orient="vertical", command=left_canvas.yview)
        left_inner = tk.Frame(left_canvas, bg="#FFFFFF")
        left_inner.bind("<Configure>", lambda _e: left_canvas.configure(scrollregion=left_canvas.bbox("all")))
        window_id = left_canvas.create_window((0, 0), window=left_inner, anchor="nw")
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_canvas.pack(side="left", fill="both", expand=True)
        left_scroll.pack(side="right", fill="y")
        left_canvas.bind("<Configure>", lambda e: left_canvas.itemconfigure(window_id, width=e.width))

        self._card_title(left_inner, "Programação do ciclo diário")
        tk.Label(
            left_inner,
            text=(
                "O modo Auditor inteligente distribui o ciclo entre as matérias disponíveis, evita repetir sempre o mesmo assunto "
                "e prioriza correções, relearning, revisões vencidas e questões novas de conteúdos já estudados."
            ),
            bg="#EEF5FB",
            fg=COLORS["navy"],
            justify="left",
            wraplength=540,
            padx=12,
            pady=9,
        ).pack(fill="x", padx=18, pady=(0, 10))

        self.flow_vars: dict[str, tk.Variable] = {
            "flow_enabled": tk.BooleanVar(value=bool(self.config_data.get("flow_enabled", False))),
            "flow_questions_per_cycle": tk.StringVar(value=str(self.config_data.get("flow_questions_per_cycle", 20))),
            "flow_extra_questions_count": tk.StringVar(value=str(self.config_data.get("flow_extra_questions_count", 5))),
            "flow_daily_time": tk.StringVar(value=str(self.config_data.get("flow_daily_time", "19:00"))),
            "flow_delay_seconds": tk.StringVar(value=str(self.config_data.get("flow_delay_seconds", 5))),
            "flow_reminder_minutes": tk.StringVar(value=str(self.config_data.get("flow_reminder_minutes", 15))),
            "flow_retry_minutes": tk.StringVar(value=str(self.config_data.get("flow_retry_minutes", 10))),
            "flow_question_retry_attempts": tk.StringVar(value=str(self.config_data.get("flow_question_retry_attempts", 3))),
            "flow_auto_retry_failed": tk.BooleanVar(value=bool(self.config_data.get("flow_auto_retry_failed", True))),
            "flow_unanswered_resend_enabled": tk.BooleanVar(value=bool(self.config_data.get("flow_unanswered_resend_enabled", True))),
            "flow_unanswered_resend_hours": tk.StringVar(value=str(self.config_data.get("flow_unanswered_resend_hours", 24))),
            "flow_unanswered_max_resends": tk.StringVar(value=str(self.config_data.get("flow_unanswered_max_resends", 2))),
            "flow_unanswered_daily_cap": tk.StringVar(value=str(self.config_data.get("flow_unanswered_daily_cap", 3))),
            "flow_background_startup_grace_minutes": tk.StringVar(value=str(self.config_data.get("flow_background_startup_grace_minutes", 5))),
            "flow_topic": tk.StringVar(value=str(self.config_data.get("flow_topic", ""))),
            "flow_strategy": tk.StringVar(value=str(self.config_data.get("flow_strategy", "adaptativo"))),
            "flow_target_retention": tk.StringVar(value=f"{float(self.config_data.get('flow_target_retention', 0.88) or 0.88):.2f}"),
            "flow_target_retention_mode": tk.StringVar(value="Otimizada pelo FSRS" if str(self.config_data.get("flow_target_retention_mode", "optimized")) == "optimized" else "Manual"),
            "flow_exam_date": tk.StringVar(value=str(self.config_data.get("flow_exam_date", "") or "")),
            "flow_daily_study_minutes": tk.StringVar(value=str(self.config_data.get("flow_daily_study_minutes", 45) or 45)),
            "flow_relearning_minutes": tk.StringVar(value=str(self.config_data.get("flow_relearning_minutes", 10) or 10)),
            "flow_fsrs_max_interval_days": tk.StringVar(value=str(self.config_data.get("flow_fsrs_max_interval_days", 365) or 365)),
            "flow_studied_only": tk.BooleanVar(value=bool(self.config_data.get("flow_studied_only", True))),
            "flow_relearning_enabled": tk.BooleanVar(value=bool(self.config_data.get("flow_relearning_enabled", True))),
            "flow_fsrs_auto_optimize": tk.BooleanVar(value=bool(self.config_data.get("flow_fsrs_auto_optimize", True))),
            "flow_dynamic_cycle_size": tk.BooleanVar(value=bool(self.config_data.get("flow_dynamic_cycle_size", True))),
            "flow_early_review_enabled": tk.BooleanVar(value=bool(self.config_data.get("flow_early_review_enabled", False))),
            "flow_approved_only": tk.BooleanVar(value=bool(self.config_data.get("flow_approved_only", True))),
            "flow_recycle_when_empty": tk.BooleanVar(value=bool(self.config_data.get("flow_recycle_when_empty", True))),
            "flow_send_pre_reminder": tk.BooleanVar(value=bool(self.config_data.get("flow_send_pre_reminder", True))),
            "flow_catch_up_missed": tk.BooleanVar(value=bool(self.config_data.get("flow_catch_up_missed", True))),
            "flow_send_completion_menu": tk.BooleanVar(value=bool(self.config_data.get("flow_send_completion_menu", True))),
            "flow_explanation_mode": tk.StringVar(value={
                "automatico": "Explicação completa após responder",
                "resultado_curto": "Resultado curto + botão de explicação",
                "somente_botao": "Somente pelo botão Ver explicação",
            }.get(str(self.config_data.get("flow_explanation_mode", "automatico")), "Explicação completa após responder")),
            "flow_question_card_enabled": tk.BooleanVar(value=bool(self.config_data.get("flow_question_card_enabled", True))),
        }
        ttk.Checkbutton(
            left_inner,
            text="Ativar ciclo diário automaticamente ao abrir o programa",
            variable=self.flow_vars["flow_enabled"],
        ).pack(anchor="w", padx=18, pady=(0, 10))

        form = tk.Frame(left_inner, bg="#FFFFFF")
        form.pack(fill="x", padx=18)
        form_fields = [
            ("flow_daily_time", "Horário diário (HH:MM)"),
            ("flow_questions_per_cycle", "Questões por ciclo diário"),
            ("flow_extra_questions_count", "Questões no botão 'Mais'"),
            ("flow_delay_seconds", "Intervalo entre questões (s)"),
            ("flow_reminder_minutes", "Lembrar antes do ciclo (min)"),
            ("flow_retry_minutes", "Repetir tentativa após falha (min)"),
            ("flow_question_retry_attempts", "Tentativas imediatas por questão"),
            ("flow_unanswered_resend_hours", "Reenviar sem resposta após (horas)"),
            ("flow_unanswered_max_resends", "Máximo por questão sem resposta"),
            ("flow_unanswered_daily_cap", "Limite diário de reenvios sem resposta"),
            ("flow_background_startup_grace_minutes", "Aguardar após iniciar (min)"),
            ("flow_target_retention", "Retenção manual/inicial (0,70–0,97)"),
            ("flow_exam_date", "Data da prova (AAAA-MM-DD)"),
            ("flow_daily_study_minutes", "Tempo diário para questões (min)"),
            ("flow_relearning_minutes", "Relearning após erro (min)"),
            ("flow_fsrs_max_interval_days", "Intervalo máximo FSRS (dias)"),
        ]
        for index, (key, label) in enumerate(form_fields):
            row, col = divmod(index, 2)
            field = tk.Frame(form, bg="#FFFFFF")
            field.grid(row=row, column=col, sticky="ew", padx=(0 if col == 0 else 8, 8 if col == 0 else 0), pady=5)
            form.grid_columnconfigure(col, weight=1)
            tk.Label(field, text=label, bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w")
            ttk.Entry(field, textvariable=self.flow_vars[key]).pack(fill="x", pady=(2, 0))

        field = tk.Frame(left_inner, bg="#FFFFFF")
        field.pack(fill="x", padx=18, pady=6)
        tk.Label(field, text="Retenção do FSRS", bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w")
        ttk.Combobox(
            field, textvariable=self.flow_vars["flow_target_retention_mode"],
            values=["Otimizada pelo FSRS", "Manual"], state="readonly",
        ).pack(fill="x", pady=(2, 0))

        field = tk.Frame(left_inner, bg="#FFFFFF")
        field.pack(fill="x", padx=18, pady=6)
        tk.Label(field, text="Estratégia de seleção", bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w")
        ttk.Combobox(
            field,
            textvariable=self.flow_vars["flow_strategy"],
            values=["auditor_inteligente", "adaptativo", "erros_primeiro", "novas_primeiro", "aleatorio"],
            state="readonly",
        ).pack(fill="x", pady=(2, 0))

        field = tk.Frame(left_inner, bg="#FFFFFF")
        field.pack(fill="x", padx=18, pady=6)
        tk.Label(field, text="Como apresentar a explicação no Telegram", bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w")
        ttk.Combobox(
            field,
            textvariable=self.flow_vars["flow_explanation_mode"],
            values=[
                "Explicação completa após responder",
                "Resultado curto + botão de explicação",
                "Somente pelo botão Ver explicação",
            ],
            state="readonly",
        ).pack(fill="x", pady=(2, 0))

        field = tk.Frame(left_inner, bg="#FFFFFF")
        field.pack(fill="x", padx=18, pady=6)
        tk.Label(field, text="Filtrar assunto ou aula (opcional)", bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w")
        ttk.Entry(field, textvariable=self.flow_vars["flow_topic"]).pack(fill="x", pady=(2, 0))

        options = tk.Frame(left_inner, bg="#FFFFFF")
        options.pack(fill="x", padx=18, pady=5)
        ttk.Checkbutton(options, text="Enviar lembrete antes do horário", variable=self.flow_vars["flow_send_pre_reminder"]).pack(anchor="w")
        ttk.Checkbutton(
            options,
            text="Ao reabrir, enviar o ciclo perdido como recuperação",
            variable=self.flow_vars["flow_catch_up_missed"],
        ).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(
            options,
            text="Mostrar botões para pedir mais questões no Telegram",
            variable=self.flow_vars["flow_send_completion_menu"],
        ).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(
            options,
            text="Enviar cartão visual com matéria, aula, banca, ano e código antes do quiz",
            variable=self.flow_vars["flow_question_card_enabled"],
        ).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(
            options,
            text="Reenviar automaticamente falhas temporárias",
            variable=self.flow_vars["flow_auto_retry_failed"],
        ).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(
            options,
            text="Reenviar questões que ficaram sem resposta",
            variable=self.flow_vars["flow_unanswered_resend_enabled"],
        ).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(options, text="Revisar somente matéria/aula já estudada na planilha", variable=self.flow_vars["flow_studied_only"]).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(options, text="Recuperação automática após erro (relearning)", variable=self.flow_vars["flow_relearning_enabled"]).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(options, text="Otimizar parâmetros FSRS automaticamente", variable=self.flow_vars["flow_fsrs_auto_optimize"]).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(options, text="Ajustar tamanho do ciclo à carga diária estimada", variable=self.flow_vars["flow_dynamic_cycle_size"]).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(options, text="Permitir antecipar revisão ainda não vencida", variable=self.flow_vars["flow_early_review_enabled"]).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(
            options,
            text="Priorizar APROVADO; usar APROVADO_AUTOMATICAMENTE só quando necessário",
            variable=self.flow_vars["flow_approved_only"],
        ).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(
            options,
            text="Reciclar as menos vistas quando nenhuma estiver vencida",
            variable=self.flow_vars["flow_recycle_when_empty"],
        ).pack(anchor="w", pady=(4, 0))

        tk.Label(left_inner, text="Dias de envio", bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w", padx=18, pady=(10, 3))
        weekdays = self.config_data.get("flow_weekdays", [0, 1, 2, 3, 4, 5, 6])
        try:
            selected_days = {int(item) for item in weekdays}
        except Exception:
            selected_days = set(range(7))
        self.flow_day_vars: list[tk.BooleanVar] = []
        day_row = tk.Frame(left_inner, bg="#FFFFFF")
        day_row.pack(fill="x", padx=18)
        for index, name in enumerate(["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]):
            variable = tk.BooleanVar(value=index in selected_days)
            self.flow_day_vars.append(variable)
            ttk.Checkbutton(day_row, text=name, variable=variable).pack(side="left", padx=(0, 7))

        tk.Label(left_inner, text="Matérias do ciclo", bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w", padx=18, pady=(12, 3))
        self.flow_subject_list = tk.Listbox(
            left_inner,
            selectmode="multiple",
            exportselection=False,
            height=7,
            font=("Segoe UI", 9),
            relief="solid",
            bd=1,
        )
        subject_values = self.taxonomy.materias if self.taxonomy else sorted(
            {row.get("subject", "") for row in self.question_queries.list(limit=10000) if row.get("subject")}
        )
        for subject in subject_values:
            self.flow_subject_list.insert("end", subject)
        saved_subjects = set(self.config_data.get("flow_subjects", []) or [])
        for index, subject in enumerate(subject_values):
            if subject in saved_subjects:
                self.flow_subject_list.selection_set(index)
        self.flow_subject_list.pack(fill="x", padx=18)
        tk.Label(
            left_inner,
            text="Sem seleção = todas as matérias e assuntos da planilha que tenham questões no banco.",
            bg="#FFFFFF",
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=18, pady=(3, 8))

        buttons = tk.Frame(left_inner, bg="#FFFFFF")
        buttons.pack(fill="x", padx=18, pady=(8, 18))
        ttk.Button(buttons, text="Salvar fluxo", style="Primary.TButton", command=self.save_flow_settings).pack(side="left")
        ttk.Button(buttons, text="Iniciar", style="Success.TButton", command=self.start_flow).pack(side="left", padx=6)
        ttk.Button(buttons, text="Pausar/retomar", command=self.toggle_flow_pause).pack(side="left")
        ttk.Button(buttons, text="Parar", style="Danger.TButton", command=self.stop_flow).pack(side="right")

        self._card_title(right, "Controle e acompanhamento")
        self.flow_status_label = tk.Label(
            right,
            text="Fluxo parado",
            bg="#EEF5FB",
            fg=COLORS["navy"],
            anchor="w",
            justify="left",
            padx=12,
            pady=10,
        )
        self.flow_status_label.pack(fill="x", padx=18, pady=(0, 8))
        self.listener_status_label = tk.Label(
            right,
            text="Captura de respostas e botões parada",
            bg="#F7F7F8",
            fg=COLORS["muted"],
            anchor="w",
            padx=12,
            pady=8,
        )
        self.listener_status_label.pack(fill="x", padx=18, pady=(0, 10))

        tk.Label(
            right,
            text=(
                "No Telegram: /proxima envia 1 questão; /mais envia um bloco extra; /ciclo inicia outro ciclo; "
                "/desempenho mostra as estatísticas. Os mesmos comandos aparecem como botões ao final do ciclo."
            ),
            bg="#FFF8E8",
            fg=COLORS["yellow"],
            justify="left",
            wraplength=520,
            padx=12,
            pady=9,
        ).pack(fill="x", padx=18, pady=(0, 10))

        actions = tk.Frame(right, bg="#FFFFFF")
        actions.pack(fill="x", padx=18)
        ttk.Button(
            actions,
            text="Enviar ciclo de 20 agora",
            style="Primary.TButton",
            command=lambda: self.send_cycle_now(None, "novo_ciclo"),
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Enviar bloco extra",
            command=self.send_extra_cycle_now,
        ).pack(side="left", padx=6)
        ttk.Button(actions, text="Capturar respostas", command=self.prepare_response_listener).pack(side="left")
        ttk.Button(
            actions,
            text="Reiniciar ciclo de estudos",
            style="Danger.TButton",
            command=self.reset_study_cycle,
        ).pack(side="right", padx=(6, 0))
        ttk.Button(actions, text="Testar bot", command=self.test_telegram_bot).pack(side="right")

        history_header = tk.Frame(right, bg="#FFFFFF")
        history_header.pack(fill="x", padx=18, pady=(16, 5))
        tk.Label(history_header, text="Histórico recente", bg="#FFFFFF", fg=COLORS["text"], font=("Segoe UI Semibold", 11)).pack(side="left")
        self.failed_delivery_label = tk.Label(history_header, text="0 falhas pendentes", bg="#FFF1F1", fg=COLORS["red"], padx=8, pady=3)
        self.failed_delivery_label.pack(side="right")

        history_table = tk.Frame(right, bg="#FFFFFF")
        history_table.pack(fill="both", expand=True, padx=18, pady=(0, 7))
        history_table.rowconfigure(0, weight=1)
        history_table.columnconfigure(0, weight=1)
        self.flow_history_tree = ttk.Treeview(
            history_table,
            columns=("data", "codigo", "materia", "status", "tentativas", "motivo", "respostas", "acertos"),
            show="headings",
            height=10,
            selectmode="browse",
        )
        for key, title, width in [
            ("data", "Data", 118),
            ("codigo", "Código", 88),
            ("materia", "Matéria", 130),
            ("status", "Status", 78),
            ("tentativas", "Tent.", 54),
            ("motivo", "Motivo do erro", 235),
            ("respostas", "Resp.", 50),
            ("acertos", "Certas", 50),
        ]:
            self.flow_history_tree.heading(key, text=title)
            self.flow_history_tree.column(key, width=width, anchor="w" if key in ("materia", "motivo") else "center")
        history_vscroll = ttk.Scrollbar(history_table, orient="vertical", command=self.flow_history_tree.yview)
        history_hscroll = ttk.Scrollbar(history_table, orient="horizontal", command=self.flow_history_tree.xview)
        self.flow_history_tree.configure(yscrollcommand=history_vscroll.set, xscrollcommand=history_hscroll.set)
        self.flow_history_tree.grid(row=0, column=0, sticky="nsew")
        history_vscroll.grid(row=0, column=1, sticky="ns")
        history_hscroll.grid(row=1, column=0, sticky="ew")
        self.flow_history_tree.bind("<Double-1>", lambda _event: self.show_selected_delivery_error())
        self.flow_history_tree.tag_configure("erro", background="#FFF1F1", foreground=COLORS["red"])
        self.flow_history_tree.tag_configure("reenviado", background="#EAF7F0", foreground=COLORS["green"])

        retry_actions = tk.Frame(right, bg="#FFFFFF")
        retry_actions.pack(fill="x", padx=18, pady=(0, 9))
        ttk.Button(retry_actions, text="Ver motivo", command=self.show_selected_delivery_error).pack(side="left")
        ttk.Button(retry_actions, text="Reenviar selecionada", style="Success.TButton", command=self.retry_selected_delivery).pack(side="left", padx=6)
        ttk.Button(retry_actions, text="Reenviar todas com erro", style="Primary.TButton", command=self.retry_all_failed_deliveries).pack(side="left")

        log_frame = tk.Frame(right, bg="#FFFFFF")
        log_frame.pack(fill="x", padx=18, pady=(0, 18))
        tk.Label(log_frame, text="Eventos", bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w")
        self.flow_log = tk.Text(log_frame, height=6, wrap="word", font=("Consolas", 8), state="disabled", relief="solid", bd=1)
        self.flow_log.pack(fill="x", pady=(3, 0))
        return page

    def _on_flow_engine_event(self, event: str, payload: dict) -> None:
        self.event_queue.put(("flow_event", event, payload))

    def _flow_log_line(self, text: str) -> None:
        if not hasattr(self, "flow_log"):
            return
        stamp = __import__("datetime").datetime.now().strftime("%H:%M:%S")
        self.flow_log.configure(state="normal")
        self.flow_log.insert("end", f"[{stamp}] {text}\n")
        lines = int(self.flow_log.index("end-1c").split(".")[0])
        if lines > 180:
            self.flow_log.delete("1.0", f"{lines - 150}.0")
        self.flow_log.see("end")
        self.flow_log.configure(state="disabled")

    def _handle_flow_event(self, event: str, payload: dict) -> None:
        if event == "engine_started":
            next_run = str(payload.get("next_run", "")).replace("T", " ")
            self._flow_log_line(f"Ciclo diário iniciado. Próximo horário: {next_run or 'calculando...'}")
        elif event == "engine_paused":
            self._flow_log_line("Fluxo pausado.")
        elif event == "engine_resumed":
            self._flow_log_line("Fluxo retomado.")
        elif event == "engine_stopped":
            self._flow_log_line("Fluxo e captura de respostas parados.")
        elif event == "listener_started":
            self._flow_log_line("Captura de respostas, comandos e botões iniciada.")
        elif event == "listener_status":
            if hasattr(self, "listener_status_label"):
                self.listener_status_label.configure(
                    text=payload.get("status", "Captura ativa"), bg="#EAF7F0", fg=COLORS["green"]
                )
        elif event == "listener_error":
            error = str(payload.get("error", "Erro na captura"))
            self._flow_log_line(f"Captura: {error}")
            if hasattr(self, "listener_status_label"):
                self.listener_status_label.configure(
                    text=f"Captura com erro: {error[:100]}", bg="#FFF1F1", fg=COLORS["red"]
                )
        elif event == "review_requested":
            request = payload.get("request") or {}
            code = str(request.get("source_code", "") or "questão")
            self._flow_log_line(f"{code} foi encaminhada pelo Telegram para correção.")
            self.refresh_corrections_list()
            self.refresh_correction_badge()
            self.show_page("corrections")
            request_id = str(request.get("id", ""))
            if request_id and hasattr(self, "corrections_tree") and self.corrections_tree.exists(request_id):
                self.corrections_tree.selection_set(request_id)
                self.corrections_tree.see(request_id)
                self.on_correction_select()
            try:
                self.deiconify()
                self.lift()
                self.focus_force()
            except tk.TclError:
                pass
        elif event == "review_request_error":
            self._flow_log_line(f"Falha ao guardar correção do Telegram: {payload.get('error', '')}")
        elif event == "callback_recovered":
            self._flow_log_line("Solicitação de correção pendente foi recuperada após iniciar o programa.")
        elif event == "callback_recovery_error":
            self._flow_log_line(f"Correção pendente continuará na fila: {payload.get('error', '')}")
        elif event == "outbox_sent":
            self._flow_log_line("Confirmação pendente do Telegram foi enviada.")
        elif event == "outbox_error":
            self._flow_log_line(f"Confirmação do Telegram ficou na fila para nova tentativa: {payload.get('error', '')}")
        elif event == "listener_update_error":
            self._flow_log_line(f"Atualização do Telegram foi preservada para nova tentativa: {payload.get('error', '')}")
        elif event == "pre_reminder_sent":
            self._flow_log_line("Lembrete prévio enviado ao Telegram.")
        elif event == "missed_notice_sent":
            self._flow_log_line("Aviso de ciclo perdido enviado; iniciando recuperação.")
        elif event == "reminder_error":
            self._flow_log_line(f"Não foi possível enviar o lembrete: {payload.get('error', '')}")
        elif event == "menu_error":
            self._flow_log_line(f"As questões foram enviadas, mas o menu final falhou: {payload.get('error', '')}")
        elif event == "cycle_started":
            kind = str(payload.get("cycle_kind", "ciclo")).replace("_", " ")
            self._flow_log_line(
                f"{kind.capitalize()} iniciado com {payload.get('count', 0)} questão(ões) "
                f"via {payload.get('requested_via', 'programa')}."
            )
        elif event == "question_sent":
            self._flow_log_line(
                f"Enviada {payload.get('index')}/{payload.get('total')}: "
                f"{payload.get('code', '')} · {payload.get('subject', '')} · {payload.get('topic', '')}"
            )
        elif event == "question_error":
            self._flow_log_line(f"Erro em {payload.get('code', '')}: {payload.get('error', '')}")
        elif event == "cycle_finished":
            subjects = payload.get("subjects", []) or []
            subject_text = f" · {len(subjects)} matéria(s)" if subjects else ""
            self._flow_log_line(
                f"Ciclo concluído: {payload.get('sent', 0)} enviada(s), "
                f"{payload.get('errors', 0)} erro(s){subject_text}."
            )
        elif event == "cycle_empty":
            self._flow_log_line("Nenhuma questão corresponde aos filtros do fluxo.")
        elif event == "cycle_error":
            self._flow_log_line(f"Falha no ciclo: {payload.get('error', '')}")
        elif event == "cycle_retry_pending":
            self._flow_log_line(
                f"O ciclo não foi enviado. Nova tentativa em cerca de {payload.get('retry_minutes', 10)} minuto(s)."
            )
        elif event == "cycle_skipped":
            self._flow_log_line(str(payload.get("reason", "Ciclo ignorado.")))
        elif event == "question_retry_wait":
            self._flow_log_line(
                f"Nova tentativa automática de {payload.get('code', '')} em {payload.get('delay', 0)}s: "
                f"{payload.get('error', '')}"
            )
        elif event == "retry_wait":
            self._flow_log_line(
                f"Reenvio de {payload.get('code', '')}: aguardando {payload.get('delay', 0)}s após "
                f"{payload.get('error', '')}"
            )
        elif event == "retry_sent":
            self._flow_log_line(f"Questão reenviada com sucesso: {payload.get('code', '')}")
        elif event == "retry_failed":
            self._flow_log_line(
                f"Reenvio ainda falhou em {payload.get('code', '')}: {payload.get('error', '')}"
            )
        elif event == "retry_batch_started":
            self._flow_log_line(f"Reenvio em lote iniciado para {payload.get('count', 0)} falha(s).")
        elif event == "retry_batch_finished":
            self._flow_log_line("Reenvio em lote concluído.")
        elif event == "retry_skipped":
            self._flow_log_line(str(payload.get("reason", "Reenvio adiado.")))
        elif event == "unanswered_backlog_quarantined":
            self._flow_log_line(
                "Proteção de inicialização: o estoque antigo de questões sem resposta foi bloqueado para evitar envio em massa."
            )
        elif event == "unanswered_resent":
            self._flow_log_line(
                f"Questão sem resposta reenviada: {payload.get('code', '')} "
                f"(reenvio {payload.get('resend_count', 1)})."
            )
        elif event == "unanswered_resend_error":
            self._flow_log_line(
                f"Falha ao reenviar questão sem resposta {payload.get('code', '')}: {payload.get('error', '')}"
            )
        elif event == "answer_received":
            result = "ACERTO" if payload.get("is_correct") else "ERRO"
            question = payload.get("question", {})
            self._flow_log_line(
                f"Resposta recebida ({result}): {question.get('codigo_origem', '')} · "
                f"{question.get('materia', '')} · {payload.get('username', payload.get('user_id', ''))}"
            )
        self.refresh_flow_dashboard()
        if event in {"question_sent", "retry_sent", "unanswered_resent", "answer_received", "cycle_finished"}:
            self.refresh_coverage_map()

    def _selected_flow_subjects(self) -> list[str]:
        if not hasattr(self, "flow_subject_list"):
            return list(self.config_data.get("flow_subjects", []) or [])
        return [self.flow_subject_list.get(index) for index in self.flow_subject_list.curselection()]

    def save_flow_settings(self, silent: bool = False) -> bool:
        if not hasattr(self, "flow_vars"):
            return True
        try:
            questions = int(self.flow_vars["flow_questions_per_cycle"].get())
            extra_questions = int(self.flow_vars["flow_extra_questions_count"].get())
            delay = int(self.flow_vars["flow_delay_seconds"].get())
            reminder = int(self.flow_vars["flow_reminder_minutes"].get())
            retry = int(self.flow_vars["flow_retry_minutes"].get())
            question_retry_attempts = int(self.flow_vars["flow_question_retry_attempts"].get())
            unanswered_hours = float(self.flow_vars["flow_unanswered_resend_hours"].get().replace(",", "."))
            unanswered_max = int(self.flow_vars["flow_unanswered_max_resends"].get())
            unanswered_daily_cap = int(self.flow_vars["flow_unanswered_daily_cap"].get())
            startup_grace = int(self.flow_vars["flow_background_startup_grace_minutes"].get())
            target_retention = float(str(self.flow_vars["flow_target_retention"].get()).replace(",", "."))
            exam_date = str(self.flow_vars["flow_exam_date"].get()).strip()
            daily_study_minutes = int(self.flow_vars["flow_daily_study_minutes"].get())
            relearning_minutes = int(self.flow_vars["flow_relearning_minutes"].get())
            max_interval_days = int(self.flow_vars["flow_fsrs_max_interval_days"].get())
            if exam_date:
                datetime.fromisoformat(exam_date)
            if not 5 <= daily_study_minutes <= 600:
                raise ValueError("Tempo diário para questões deve ficar entre 5 e 600 minutos.")
            if not 1 <= relearning_minutes <= 1440:
                raise ValueError("Relearning deve ficar entre 1 e 1440 minutos.")
            if not 1 <= max_interval_days <= 36500:
                raise ValueError("Intervalo máximo FSRS deve ficar entre 1 e 36500 dias.")
            daily_time = str(self.flow_vars["flow_daily_time"].get()).strip()
            hour_text, minute_text = daily_time.split(":", 1)
            hour, minute = int(hour_text), int(minute_text)
            if not 1 <= questions <= 50:
                raise ValueError("Questões por ciclo deve ficar entre 1 e 50.")
            if not 1 <= extra_questions <= 20:
                raise ValueError("O bloco extra deve ter entre 1 e 20 questões.")
            if not 0 <= delay <= 600:
                raise ValueError("O intervalo entre questões deve ficar entre 0 e 600 segundos.")
            if not 1 <= reminder <= 180:
                raise ValueError("O lembrete deve ser enviado entre 1 e 180 minutos antes.")
            if not 1 <= retry <= 1440:
                raise ValueError("A nova tentativa deve ficar entre 1 minuto e 24 horas.")
            if not 1 <= question_retry_attempts <= 8:
                raise ValueError("As tentativas imediatas por questão devem ficar entre 1 e 8.")
            if not 0.25 <= unanswered_hours <= 720:
                raise ValueError("O reenvio sem resposta deve ficar entre 0,25 e 720 horas.")
            if not 0 <= unanswered_max <= 10:
                raise ValueError("O máximo de reenvios sem resposta deve ficar entre 0 e 10.")
            if not 0 <= unanswered_daily_cap <= 20:
                raise ValueError("O limite diário de reenvios sem resposta deve ficar entre 0 e 20.")
            if not 0 <= startup_grace <= 120:
                raise ValueError("A espera após iniciar deve ficar entre 0 e 120 minutos.")
            if not 0.70 <= target_retention <= 0.97:
                raise ValueError("A retenção-alvo deve ficar entre 0,70 e 0,97.")
            if not 0 <= hour <= 23 or not 0 <= minute <= 59:
                raise ValueError("Informe o horário no formato HH:MM, por exemplo 19:30.")
            daily_time = f"{hour:02d}:{minute:02d}"
            weekdays = [index for index, variable in enumerate(self.flow_day_vars) if variable.get()]
            if not weekdays:
                raise ValueError("Selecione pelo menos um dia da semana.")
        except (ValueError, TypeError) as error:
            if not silent:
                messagebox.showerror(APP_NAME, str(error))
            return False
        self.config_data.update(
            {
                "flow_enabled": bool(self.flow_vars["flow_enabled"].get()),
                "flow_questions_per_cycle": questions,
                "flow_extra_questions_count": extra_questions,
                "flow_daily_time": daily_time,
                "flow_delay_seconds": delay,
                "flow_reminder_minutes": reminder,
                "flow_retry_minutes": retry,
                "flow_question_retry_attempts": question_retry_attempts,
                "flow_auto_retry_failed": bool(self.flow_vars["flow_auto_retry_failed"].get()),
                "flow_unanswered_resend_enabled": bool(self.flow_vars["flow_unanswered_resend_enabled"].get()),
                "flow_unanswered_resend_hours": unanswered_hours,
                "flow_unanswered_max_resends": unanswered_max,
                "flow_unanswered_daily_cap": unanswered_daily_cap,
                "flow_unanswered_session_cap": min(3, unanswered_daily_cap) if unanswered_daily_cap else 0,
                "flow_unanswered_batch_limit": 1,
                "flow_background_startup_grace_minutes": startup_grace,
                "flow_target_retention": target_retention,
                "flow_target_retention_mode": "optimized" if self.flow_vars["flow_target_retention_mode"].get() == "Otimizada pelo FSRS" else "manual",
                "flow_exam_date": exam_date,
                "flow_daily_study_minutes": daily_study_minutes,
                "flow_relearning_minutes": relearning_minutes,
                "flow_fsrs_max_interval_days": max_interval_days,
                "flow_studied_only": bool(self.flow_vars["flow_studied_only"].get()),
                "flow_relearning_enabled": bool(self.flow_vars["flow_relearning_enabled"].get()),
                "flow_fsrs_auto_optimize": bool(self.flow_vars["flow_fsrs_auto_optimize"].get()),
                "flow_dynamic_cycle_size": bool(self.flow_vars["flow_dynamic_cycle_size"].get()),
                "flow_early_review_enabled": bool(self.flow_vars["flow_early_review_enabled"].get()),
                "flow_send_pre_reminder": bool(self.flow_vars["flow_send_pre_reminder"].get()),
                "flow_catch_up_missed": bool(self.flow_vars["flow_catch_up_missed"].get()),
                "flow_send_completion_menu": bool(self.flow_vars["flow_send_completion_menu"].get()),
                "flow_explanation_mode": {
                    "Explicação completa após responder": "automatico",
                    "Resultado curto + botão de explicação": "resultado_curto",
                    "Somente pelo botão Ver explicação": "somente_botao",
                }.get(str(self.flow_vars["flow_explanation_mode"].get()), "automatico"),
                "flow_question_card_enabled": bool(self.flow_vars["flow_question_card_enabled"].get()),
                "flow_native_quiz_explanation": False,
                "flow_weekdays": weekdays,
                "flow_subjects": self._selected_flow_subjects(),
                "flow_topic": str(self.flow_vars["flow_topic"].get()).strip(),
                "flow_strategy": str(self.flow_vars["flow_strategy"].get()).strip(),
                "flow_approved_only": bool(self.flow_vars["flow_approved_only"].get()),
                "flow_recycle_when_empty": bool(self.flow_vars["flow_recycle_when_empty"].get()),
            }
        )
        self.flow_vars["flow_daily_time"].set(daily_time)
        self.flow_vars["flow_target_retention"].set(f"{target_retention:.2f}")
        self.study.set_learning_preferences(
            target_retention=target_retention,
            retention_mode=self.config_data["flow_target_retention_mode"],
            exam_date=exam_date, daily_minutes=daily_study_minutes,
            maximum_interval_days=max_interval_days, relearning_minutes=relearning_minutes,
            studied_only=self.config_data["flow_studied_only"],
            early_review_enabled=self.config_data["flow_early_review_enabled"],
        )
        save_config(self.config_data)
        if not silent:
            messagebox.showinfo(
                APP_NAME,
                f"Ciclo salvo: {questions} questões às {daily_time}.\n"
                "Mantenha o programa aberto ou use o início automático do Windows para receber no horário.",
            )
        return True

    def start_flow(self) -> None:
        self.save_settings(silent=True)
        if not self.save_flow_settings(silent=True):
            return
        if not str(self.config_data.get("telegram_bot_token", "")).strip() or not str(self.config_data.get("telegram_chat_id", "")).strip():
            messagebox.showinfo(APP_NAME, "Informe o token e o Chat ID na aba Configurações.")
            self.show_page("settings")
            return
        self.config_data["flow_enabled"] = True
        self.flow_vars["flow_enabled"].set(True)
        save_config(self.config_data)
        self.flow_engine.start(start_listener=True)
        self.refresh_flow_dashboard()

    def toggle_flow_pause(self) -> None:
        if not self.flow_engine.running:
            self.start_flow()
            return
        if self.flow_engine.paused:
            self.flow_engine.resume()
        else:
            self.flow_engine.pause()
        self.refresh_flow_dashboard()

    def stop_flow(self) -> None:
        # Desativa apenas o ciclo diário. A manutenção do Telegram continua ativa
        # para sincronizar correções, falhas e questões sem resposta.
        self.config_data["flow_enabled"] = False
        if hasattr(self, "flow_vars"):
            self.flow_vars["flow_enabled"].set(False)
        save_config(self.config_data)
        if self.config_data.get("telegram_bot_token") and self.config_data.get("telegram_chat_id"):
            self.flow_engine.start(start_listener=True)
        self.refresh_flow_dashboard()

    def reset_study_cycle(self) -> None:
        if self.flow_engine.sending:
            messagebox.showwarning(
                APP_NAME,
                "Há um ciclo enviando questões neste momento. Aguarde o envio terminar e tente novamente.",
            )
            return
        warning = (
            "Esta ação reinicia todo o ciclo de estudos e apaga o histórico de envios, "
            "respostas, acertos, erros e revisões espaçadas.\n\n"
            "A base de questões e as solicitações da aba Correções Telegram serão preservadas. "
            "Questões ainda em correção continuarão suspensas.\n\n"
            "Digite REINICIAR para confirmar."
        )
        confirmation = simpledialog.askstring(APP_NAME, warning, parent=self)
        if str(confirmation or "").strip().upper() != "REINICIAR":
            return
        was_running = self.flow_engine.running and not self.flow_engine.paused
        if self.flow_engine.running:
            self.flow_engine.pause()
        backup_path = None
        try:
            from datetime import datetime as _dt, timezone as _tz
            backup_dir = DATABASE_PATH.parent / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"QuestFlow-pre-reset-{_dt.now():%Y%m%d-%H%M%S}.sqlite"
            self.question_commands.backup(backup_path)
            self.study.reset_progress()
            self.study.sync_questions()
            self.study.set_runtime("unanswered_policy_version", "3.0.14")
            self.study.set_runtime(
                "unanswered_resend_activated_at",
                _dt.now(_tz.utc).replace(microsecond=0).isoformat(),
            )
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Não foi possível reiniciar o ciclo:\n{error}")
            if was_running:
                self.flow_engine.resume()
            return
        if was_running:
            self.flow_engine.resume()
        self.refresh_all()
        messagebox.showinfo(
            APP_NAME,
            "Ciclo de estudos reiniciado. Todas as questões elegíveis voltarão a ser tratadas como não estudadas.\n\n"
            f"Backup de segurança: {backup_path}",
        )

    def send_cycle_now(self, limit_override: int | None = None, cycle_kind: str = "extra") -> None:
        self.save_settings(silent=True)
        if not self.save_flow_settings(silent=True):
            return
        if not str(self.config_data.get("telegram_bot_token", "")).strip() or not str(self.config_data.get("telegram_chat_id", "")).strip():
            messagebox.showinfo(APP_NAME, "Informe o token e o Chat ID na aba Configurações.")
            return
        if limit_override is None:
            limit_override = int(self.config_data.get("flow_questions_per_cycle", 20) or 20)
        self.flow_engine.send_cycle_now(
            limit_override=limit_override,
            cycle_kind=cycle_kind,
            requested_via="programa",
        )

    def send_extra_cycle_now(self) -> None:
        if not self.save_flow_settings(silent=True):
            return
        count = int(self.config_data.get("flow_extra_questions_count", 5) or 5)
        self.send_cycle_now(count, "extra")

    def prepare_response_listener(self) -> None:
        self.save_settings(silent=True)
        token = str(self.config_data.get("telegram_bot_token", "")).strip()
        if not token:
            messagebox.showinfo(APP_NAME, "Informe o token do bot nas configurações.")
            return
        try:
            info = get_webhook_info(token).get("result", {})
            webhook_url = str(info.get("url", "") or "")
            if webhook_url:
                if not messagebox.askyesno(
                    APP_NAME,
                    "Este bot está usando webhook em outro sistema. Para o QuestFlow Studio capturar respostas, "
                    "é necessário remover esse webhook. Deseja remover agora?",
                ):
                    return
                delete_webhook(token, drop_pending_updates=False)
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Não foi possível preparar a captura de respostas:\n{error}")
            return
        self.flow_engine.start_listener()
        self.refresh_flow_dashboard()

    def test_telegram_bot(self) -> None:
        self.save_settings(silent=True)
        token = str(self.config_data.get("telegram_bot_token", "")).strip()
        chat_id = str(self.config_data.get("telegram_chat_id", "")).strip()
        if not token or not chat_id:
            messagebox.showinfo(APP_NAME, "Informe o token e o Chat ID nas configurações.")
            return
        try:
            result = get_me(token).get("result", {})
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Falha ao conectar ao bot:\n{error}")
            return
        name = result.get("username") or result.get("first_name") or "bot"
        messagebox.showinfo(APP_NAME, f"Conexão realizada com @{name}.\nChat ID configurado: {chat_id}")

    def refresh_flow_dashboard(self) -> None:
        if not hasattr(self, "flow_stat_labels"):
            return
        try:
            stats = self.study.stats()
        except Exception:
            return
        self.flow_stat_labels["sent"].configure(text=str(stats["sent"]))
        self.flow_stat_labels["attempts"].configure(text=str(stats["attempts"]))
        self.flow_stat_labels["correct"].configure(text=str(stats["correct"]))
        self.flow_stat_labels["wrong"].configure(text=str(stats["wrong"]))
        self.flow_stat_labels["accuracy"].configure(text=f"{stats['accuracy']:.1f}%")
        if self.flow_engine.running:
            state = "Pausado" if self.flow_engine.paused else "Ativo"
            next_run = self.flow_engine.next_run
            suffix = f" · próximo ciclo {next_run.strftime('%d/%m %H:%M')}" if next_run else ""
            bg = "#FFF8E8" if self.flow_engine.paused else "#EAF7F0"
            fg = COLORS["yellow"] if self.flow_engine.paused else COLORS["green"]
        else:
            state, suffix, bg, fg = "Parado", "", "#EEF5FB", COLORS["navy"]
        self.flow_status_label.configure(text=f"Fluxo: {state}{suffix}", bg=bg, fg=fg)
        if self.flow_engine.listening:
            self.listener_status_label.configure(text="Respostas e botões do Telegram ativos", bg="#EAF7F0", fg=COLORS["green"])
        elif not str(self.listener_status_label.cget("text")).startswith("Captura com erro"):
            self.listener_status_label.configure(text="Captura de respostas e botões parada", bg="#F7F7F8", fg=COLORS["muted"])
        self.refresh_flow_history()

    def refresh_flow_history(self) -> None:
        if not hasattr(self, "flow_history_tree"):
            return
        selected = self.flow_history_tree.selection()
        selected_id = selected[0] if selected else None
        for item in self.flow_history_tree.get_children():
            self.flow_history_tree.delete(item)
        failed_count = 0
        for row in self.study.recent_deliveries(120):
            date = str(row.get("sent_at", "")).replace("T", " ").replace("+00:00", "")[:16]
            status = str(row.get("status", ""))
            error_text = str(row.get("error_text", "") or "")
            if status == "erro" and not row.get("resolved_by_delivery_id"):
                failed_count += 1
            reason = error_text.replace("\n", " ")[:120]
            tag = "erro" if status == "erro" and not row.get("resolved_by_delivery_id") else ("reenviado" if status == "reenviado" else "")
            iid = str(row.get("id", ""))
            self.flow_history_tree.insert(
                "",
                "end",
                iid=iid,
                tags=(tag,) if tag else (),
                values=(
                    date,
                    row.get("source_code", ""),
                    row.get("subject", ""),
                    status,
                    row.get("attempt_count", 1) or 1,
                    reason,
                    row.get("answers", 0),
                    row.get("correct_answers", 0),
                ),
            )
        if hasattr(self, "failed_delivery_label"):
            self.failed_delivery_label.configure(text=f"{failed_count} falha(s) pendente(s)")
        if selected_id and self.flow_history_tree.exists(selected_id):
            self.flow_history_tree.selection_set(selected_id)
            self.flow_history_tree.see(selected_id)

    def _selected_delivery_id(self) -> str | None:
        if not hasattr(self, "flow_history_tree"):
            return None
        selection = self.flow_history_tree.selection()
        return str(selection[0]) if selection else None

    def show_selected_delivery_error(self) -> None:
        delivery_id = self._selected_delivery_id()
        if not delivery_id:
            messagebox.showinfo(APP_NAME, "Selecione um envio no histórico.")
            return
        row = self.study.get_delivery(delivery_id)
        if not row:
            messagebox.showinfo(APP_NAME, "O registro selecionado não foi encontrado.")
            return
        question = row.get("question", {})
        error_text = str(row.get("error_text", "") or "Sem erro registrado.")
        retry_text = "Sim" if row.get("is_retryable") else "Não"
        next_retry = str(row.get("next_retry_at", "") or "Não agendada").replace("T", " ")
        messagebox.showinfo(
            "Detalhes do envio",
            f"Questão: {question.get('codigo_origem', '')}\n"
            f"Status: {row.get('status', '')}\n"
            f"Categoria: {row.get('error_category', '') or 'não classificada'}\n"
            f"Tentativas: {row.get('attempt_count', 1)}\n"
            f"Pode tentar novamente: {retry_text}\n"
            f"Próxima tentativa: {next_retry}\n\n"
            f"Motivo informado pelo Telegram/programa:\n{error_text}",
        )

    def retry_selected_delivery(self) -> None:
        delivery_id = self._selected_delivery_id()
        if not delivery_id:
            messagebox.showinfo(APP_NAME, "Selecione uma questão com erro no histórico.")
            return
        row = self.study.get_delivery(delivery_id)
        if not row:
            return
        if row.get("status") not in {"erro", "reenviando"} or row.get("resolved_by_delivery_id"):
            messagebox.showinfo(APP_NAME, "O envio selecionado não possui falha pendente.")
            return
        self.flow_engine.retry_delivery_now(delivery_id, requested_via="botao_programa")
        self._flow_log_line(f"Reenvio manual solicitado para {row.get('source_code', '')}.")

    def retry_all_failed_deliveries(self) -> None:
        failures = self.study.failed_deliveries(500, due_only=False)
        if not failures:
            messagebox.showinfo(APP_NAME, "Não há questões com erro pendente.")
            return
        if not messagebox.askyesno(APP_NAME, f"Tentar reenviar {len(failures)} questão(ões) com erro?"):
            return
        self.flow_engine.retry_all_failed(requested_via="botao_programa")

