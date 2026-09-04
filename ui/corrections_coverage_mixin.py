from __future__ import annotations

from .common import *  # noqa: F401,F403


class CorrectionsCoverageMixin:
    def _build_corrections_page(self) -> tk.Frame:
        page = self._page()
        container = tk.Frame(page, bg=COLORS["background"])
        container.pack(fill="both", expand=True, padx=24, pady=20)
        self._section_title(
            container,
            "Correções solicitadas no Telegram",
            "O botão da questão cria uma fila local. Se o programa estiver fechado, o Telegram entrega a solicitação quando ele voltar a funcionar.",
        )

        notice = tk.Label(
            container,
            text=(
                "As atualizações pendentes do Bot API ficam disponíveis por até 24 horas. "
                "Se o programa permanecer fechado por mais tempo, toque novamente no botão da questão no Telegram."
            ),
            bg="#FFF8E8", fg=COLORS["yellow"], anchor="w", justify="left",
            padx=12, pady=9, wraplength=1100,
        )
        notice.pack(fill="x", pady=(0, 10))

        toolbar = tk.Frame(container, bg=COLORS["background"])
        toolbar.pack(fill="x", pady=(0, 10))
        self.correction_status_filter = tk.StringVar(value="ativas")
        ttk.Combobox(
            toolbar, textvariable=self.correction_status_filter,
            values=["ativas", "pendente", "aberta", "resolvida", "todas"],
            state="readonly", width=18,
        ).pack(side="left")
        ttk.Button(toolbar, text="Atualizar fila", command=self.refresh_corrections_list).pack(side="left", padx=8)
        self.correction_count_label = tk.Label(
            toolbar, text="", bg=COLORS["background"], fg=COLORS["muted"]
        )
        self.correction_count_label.pack(side="left", padx=8)

        split = tk.PanedWindow(container, orient="horizontal", bg=COLORS["background"], sashwidth=6, relief="flat")
        split.pack(fill="both", expand=True)
        left = tk.Frame(split, bg="#FFFFFF", highlightbackground=COLORS["border"], highlightthickness=1)
        right = tk.Frame(split, bg="#FFFFFF", highlightbackground=COLORS["border"], highlightthickness=1)
        split.add(left, minsize=580, width=780)
        split.add(right, minsize=360)

        columns = ("data", "codigo", "materia", "status", "usuario")
        self.corrections_tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        specs = [
            ("data", "Solicitada em", 150),
            ("codigo", "Código", 115),
            ("materia", "Matéria", 190),
            ("status", "Status", 95),
            ("usuario", "Usuário", 140),
        ]
        for key, title, width in specs:
            self.corrections_tree.heading(key, text=title)
            self.corrections_tree.column(key, width=width, anchor="w")
        yscroll = ttk.Scrollbar(left, orient="vertical", command=self.corrections_tree.yview)
        self.corrections_tree.configure(yscrollcommand=yscroll.set)
        self.corrections_tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        yscroll.pack(side="right", fill="y", padx=(0, 10), pady=10)
        self.corrections_tree.bind("<<TreeviewSelect>>", self.on_correction_select)
        self.corrections_tree.bind("<Double-1>", lambda _e: self.open_selected_correction())

        tk.Label(right, text="Questão encaminhada", bg="#FFFFFF", fg=COLORS["navy"], font=("Segoe UI Semibold", 11)).pack(anchor="w", padx=16, pady=(16, 5))
        self.correction_meta_label = tk.Label(
            right, text="Selecione uma solicitação.", bg="#FFFFFF", fg=COLORS["muted"],
            anchor="w", justify="left", wraplength=430,
        )
        self.correction_meta_label.pack(fill="x", padx=16, pady=(0, 8))
        self.correction_preview = tk.Text(
            right, height=18, wrap="word", font=("Segoe UI", 10), relief="solid", bd=1, state="disabled"
        )
        self.correction_preview.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        actions = tk.Frame(right, bg="#FFFFFF")
        actions.pack(fill="x", padx=16, pady=(0, 16))
        ttk.Button(actions, text="Abrir e editar", style="Primary.TButton", command=self.open_selected_correction).pack(side="left")
        ttk.Button(actions, text="Marcar resolvida", style="Success.TButton", command=self.resolve_selected_correction).pack(side="left", padx=8)
        ttk.Button(actions, text="Excluir da fila", style="Danger.TButton", command=self.delete_selected_correction).pack(side="right")
        return page

    def _build_coverage_page(self) -> tk.Frame:
        page = self._page()
        container = tk.Frame(page, bg=COLORS["background"])
        container.pack(fill="both", expand=True, padx=24, pady=20)
        self._section_title(
            container,
            "Cobertura dos estudos",
            "Mostra somente os conteúdos marcados como estudados no CICLO_REG e quantas questões ainda precisam ser adicionadas ao banco.",
        )

        cards = tk.Frame(container, bg=COLORS["background"])
        cards.pack(fill="x", pady=(0, 12))
        self.coverage_stat_labels: dict[str, tk.Label] = {}
        for key, label, color in [
            ("studied", "Conteúdos estudados", COLORS["navy"]),
            ("attention", "Precisam de questões", COLORS["red"]),
            ("missing", "Faltam adicionar", COLORS["orange_dark"]),
            ("covered", "Cobertos", COLORS["green"]),
        ]:
            card = tk.Frame(cards, bg=COLORS["surface"], highlightbackground=COLORS["border"], highlightthickness=1)
            card.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Frame(card, bg=color, width=5).pack(side="left", fill="y")
            body = tk.Frame(card, bg=COLORS["surface"])
            body.pack(side="left", padx=10, pady=8)
            value = tk.Label(body, text="0", bg=COLORS["surface"], fg=color, font=("Segoe UI Semibold", 16))
            value.pack(anchor="w")
            tk.Label(body, text=label, bg=COLORS["surface"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w")
            self.coverage_stat_labels[key] = value

        notice = tk.Label(
            container,
            text=(
                "Faltam adicionar = TOT QUEST FEITAS da planilha − questões correspondentes no banco. "
                "Quando a planilha não informa uma quantidade, o conteúdo estudado é sinalizado sem criar uma meta artificial."
            ),
            bg="#EEF5FB", fg=COLORS["navy"], anchor="w", justify="left",
            padx=12, pady=9, wraplength=1200,
        )
        notice.pack(fill="x", pady=(0, 10))

        self.trail_guide_status_label = tk.Label(
            container,
            text="Carregando documentação das trilhas...",
            bg="#EEF5FB", fg=COLORS["navy"], anchor="w", justify="left",
            padx=12, pady=9, wraplength=1200,
        )
        self.trail_guide_status_label.pack(fill="x", pady=(0, 10))

        toolbar = tk.Frame(container, bg=COLORS["background"])
        toolbar.pack(fill="x", pady=(0, 10))
        self.coverage_search_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.coverage_search_var).pack(side="left", fill="x", expand=True)
        self.coverage_subject_var = tk.StringVar(value="Todas as matérias")
        self.coverage_subject_combo = ttk.Combobox(
            toolbar,
            textvariable=self.coverage_subject_var,
            values=["Todas as matérias"] + (self.taxonomy.materias if self.taxonomy else []),
            state="readonly",
            width=30,
        )
        self.coverage_subject_combo.pack(side="left", padx=8)
        self.coverage_status_var = tk.StringVar(value="Somente pendências")
        ttk.Combobox(
            toolbar,
            textvariable=self.coverage_status_var,
            values=[
                "Somente pendências",
                "Sem cobertura",
                "Cobertura parcial",
                "Sem questão e sem meta",
                "Cobertos",
                "Todos os estudados",
            ],
            state="readonly",
            width=26,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Filtrar", command=self.refresh_coverage_map).pack(side="left")

        actions = tk.Frame(container, bg=COLORS["background"])
        actions.pack(fill="x", pady=(0, 10))
        ttk.Button(actions, text="Recalcular", style="Primary.TButton", command=self.refresh_coverage_map).pack(side="left")
        ttk.Button(actions, text="Sincronizar planilha Google", command=self.update_taxonomy_from_internet).pack(side="left", padx=8)
        ttk.Button(actions, text="Importar planilha .XLSX", command=self.import_taxonomy_xlsx).pack(side="left")
        ttk.Button(actions, text="Adicionar PDF explicativo da trilha", command=self.import_trail_guide_pdfs_classic).pack(side="left", padx=8)
        ttk.Button(actions, text="Exportar cobertura CSV", command=self.export_coverage_csv).pack(side="right")

        table_frame = tk.Frame(container, bg=COLORS["surface"], highlightbackground=COLORS["border"], highlightthickness=1)
        table_frame.pack(fill="both", expand=True)
        columns = (
            "trilha", "materia", "aula", "conteudo", "ch", "feitas", "banco",
            "faltam", "acertos", "desempenho", "status",
        )
        self.coverage_tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "trilha": "Trilha",
            "materia": "Matéria",
            "aula": "Aula",
            "conteudo": "Conteúdo estudado",
            "ch": "CH efetiva",
            "feitas": "Questões feitas",
            "banco": "No banco",
            "faltam": "Faltam adicionar",
            "acertos": "Acertos",
            "desempenho": "Desempenho",
            "status": "Situação",
        }
        widths = {
            "trilha": 78,
            "materia": 180, "aula": 80, "conteudo": 360, "ch": 85,
            "feitas": 95, "banco": 80, "faltam": 105, "acertos": 75,
            "desempenho": 90, "status": 190,
        }
        for key in columns:
            self.coverage_tree.heading(key, text=headings[key])
            self.coverage_tree.column(
                key, width=widths[key], minwidth=60,
                anchor="w" if key in {"materia", "conteudo", "status"} else "center",
            )
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.coverage_tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.coverage_tree.xview)
        self.coverage_tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.coverage_tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        self.make_tree_sortable(
            self.coverage_tree,
            headings,
            {"feitas": "int", "banco": "int", "faltam": "int", "acertos": "int"},
        )
        self.coverage_tree.tag_configure("missing", background="#FFF1F1")
        self.coverage_tree.tag_configure("partial", background="#FFF8E8")
        self.coverage_tree.tag_configure("covered", background="#EAF8F0")
        self.coverage_rows: list[dict] = []
        return page

    def refresh_trail_guide_status(self, *, notify: bool = True) -> dict:
        tasks = self.taxonomy.tasks if self.taxonomy is not None else []
        registry = ensure_registry(TRAIL_GUIDES_PATH)
        status = guide_status_for_tasks(tasks, registry)
        missing = list(status.get("missing_studied_trails", []))
        available = status.get("available_label", "Nenhuma trilha")
        next_label = status.get("next_expected_label", "próxima trilha")
        if missing:
            labels = ", ".join(str(item.get("label") or trail_label(item.get("trail"))) for item in missing)
            details = []
            for item in missing:
                subjects = ", ".join(item.get("subjects", [])[:6])
                tasks = ", ".join(item.get("tasks", [])[:12])
                parts = []
                if subjects:
                    parts.append(subjects)
                if tasks:
                    parts.append(f"tarefas {tasks}")
                if parts:
                    details.append(f"{item.get('label', '')}: " + " — ".join(parts))
            text = (
                f"ATENÇÃO — explicações incorporadas: {available}. Falta o PDF explicativo de {labels}. "
                "Já há estudo registrado nessas trilhas; adicione o(s) PDF(s) para completar a referência."
            )
            if details:
                text += " Matérias detectadas: " + " | ".join(details)
            if hasattr(self, "trail_guide_status_label"):
                self.trail_guide_status_label.configure(text=text, bg="#FFF8E8", fg=COLORS["yellow"])
            signature = ",".join(str(item.get("trail")) for item in missing)
            previous = getattr(self, "_last_trail_guide_warning_signature", "")
            if notify and signature != previous:
                self._last_trail_guide_warning_signature = signature
                messagebox.showwarning(APP_NAME, text)
        else:
            self._last_trail_guide_warning_signature = ""
            text = (
                f"Explicações incorporadas: {available}. O próximo documento esperado é {next_label}. "
                "Quando você registrar estudo em uma trilha ainda sem PDF, o QuestFlow exibirá um aviso."
            )
            if hasattr(self, "trail_guide_status_label"):
                self.trail_guide_status_label.configure(text=text, bg="#EAF8F0", fg=COLORS["green"])
        return status

    def import_trail_guide_pdfs_classic(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Selecionar PDF(s) explicativo(s) da trilha",
            filetypes=[("PDF da trilha", "*.pdf"), ("Todos os arquivos", "*.*")],
        )
        if not paths:
            return
        try:
            result = import_guide_pdfs(paths, TRAIL_GUIDES_PATH)
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Não foi possível incorporar o PDF da trilha:\n{error}")
            return
        imported = result.get("imported", [])
        errors = result.get("errors", [])
        if imported:
            labels = ", ".join(trail_label(item.get("trail")) for item in imported)
            message = f"Explicação incorporada: {labels}."
            if errors:
                message += f" {len(errors)} arquivo(s) não puderam ser lidos."
            messagebox.showinfo(APP_NAME, message)
        elif errors:
            messagebox.showerror(APP_NAME, "Nenhum PDF foi incorporado.\n\n" + "\n".join(item.get("error", "") for item in errors[:5]))
        self.refresh_trail_guide_status(notify=True)

    def refresh_coverage_map(self) -> None:
        if not hasattr(self, "coverage_tree"):
            return
        for item in self.coverage_tree.get_children():
            self.coverage_tree.delete(item)
        if self.taxonomy is None:
            self.coverage_rows = []
            return
        analysis = self.study.studied_content_coverage(self.taxonomy.tasks)
        self.refresh_trail_guide_status(notify=True)
        rows = list(analysis.get("items", []))
        self.coverage_rows = rows
        search = str(self.coverage_search_var.get() if hasattr(self, "coverage_search_var") else "").strip().casefold()
        subject_filter = str(self.coverage_subject_var.get() if hasattr(self, "coverage_subject_var") else "Todas as matérias")
        status_filter = str(self.coverage_status_var.get() if hasattr(self, "coverage_status_var") else "Somente pendências")
        status_map = {
            "Sem cobertura": {"faltam_questoes"},
            "Cobertura parcial": {"cobertura_parcial"},
            "Sem questão e sem meta": {"sem_questoes"},
            "Cobertos": {"coberto", "coberto_sem_meta"},
        }
        labels = {
            "faltam_questoes": "Sem cobertura: adicionar questões",
            "cobertura_parcial": "Cobertura parcial",
            "sem_questoes": "Conteúdo estudado sem questão",
            "coberto": "Coberto",
            "coberto_sem_meta": "Há questões cadastradas",
        }
        tags = {
            "faltam_questoes": "missing",
            "sem_questoes": "missing",
            "cobertura_parcial": "partial",
            "coberto": "covered",
            "coberto_sem_meta": "covered",
        }
        for row in rows:
            if subject_filter != "Todas as matérias" and row.get("subject") != subject_filter:
                continue
            if status_filter == "Somente pendências" and not row.get("needs_attention"):
                continue
            if status_filter in status_map and row.get("status") not in status_map[status_filter]:
                continue
            haystack = " ".join(
                str(row.get(key, "")) for key in ("subject", "lesson", "content", "description", "status")
            ).casefold()
            if search and search not in haystack:
                continue
            missing = row.get("missing_question_count")
            missing_display = "A definir" if missing is None and row.get("needs_attention") else ("—" if missing is None else str(missing))
            performance = f"{float(row.get('performance', 0) or 0):.2f}%".replace(".", ",")
            self.coverage_tree.insert(
                "",
                "end",
                values=(
                    trail_label(trail_number(row.get("trilha", ""))),
                    row.get("subject", ""), row.get("lesson", ""), row.get("content", ""),
                    row.get("effective_time", ""), row.get("questions_done", 0),
                    row.get("bank_question_count", 0), missing_display,
                    row.get("correct_answers", 0), performance,
                    labels.get(row.get("status"), row.get("status", "")),
                ),
                tags=(tags.get(row.get("status"), ""),),
            )
        self._reapply_tree_sort(self.coverage_tree)
        summary = analysis.get("summary", {})
        values = {
            "studied": int(summary.get("studied_contents", 0) or 0),
            "attention": int(summary.get("contents_needing_questions", 0) or 0),
            "missing": int(summary.get("known_missing_questions", 0) or 0),
            "covered": int(summary.get("covered_contents", 0) or 0),
        }
        if hasattr(self, "coverage_stat_labels"):
            for key, value in values.items():
                self.coverage_stat_labels[key].configure(text=str(value))

    def export_coverage_csv(self) -> None:
        if self.taxonomy is None:
            messagebox.showinfo(APP_NAME, "Atualize ou importe a planilha antes de exportar a cobertura.")
            return
        rows = self.study.studied_content_coverage(self.taxonomy.tasks).get("items", [])
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="QuestFlow_Cobertura_dos_Estudos.csv",
        )
        if not path:
            return
        fields = [
            "trilha", "tarefa", "data", "subject", "lesson", "content", "description",
            "effective_time", "questions_done", "correct_answers", "performance",
            "question_goal", "bank_question_count", "missing_question_count", "status",
        ]
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter=";")
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fields})
        messagebox.showinfo(APP_NAME, f"Cobertura exportada com {len(rows)} conteúdo(s) estudado(s).")

    def refresh_correction_badge(self) -> None:
        if not hasattr(self, "nav_buttons") or "corrections" not in self.nav_buttons:
            return
        count = self.study.pending_review_count()
        label, icon = self.nav_meta.get("corrections", ("Correções Telegram", "04"))
        if self.sidebar_collapsed:
            text = f"{icon}\n{count}" if count else icon
        else:
            suffix = f" ({count})" if count else ""
            text = f"{icon}   {label}{suffix}"
        self.nav_buttons["corrections"].configure(text=text)

    def refresh_corrections_list(self) -> None:
        if not hasattr(self, "corrections_tree"):
            return
        selected = self.corrections_tree.selection()
        selected_id = selected[0] if selected else ""
        for item in self.corrections_tree.get_children():
            self.corrections_tree.delete(item)
        status = self.correction_status_filter.get() if hasattr(self, "correction_status_filter") else "ativas"
        rows = self.study.list_review_requests(status=status)
        for row in rows:
            date = str(row.get("requested_at", "")).replace("T", " ").replace("+00:00", "")[:19]
            self.corrections_tree.insert(
                "", "end", iid=str(row["id"]),
                values=(date, row.get("source_code", ""), row.get("subject", ""), row.get("status", ""), row.get("username", "")),
            )
        if hasattr(self, "correction_count_label"):
            self.correction_count_label.configure(text=f"{len(rows)} solicitação(ões) exibida(s)")
        if selected_id and self.corrections_tree.exists(selected_id):
            self.corrections_tree.selection_set(selected_id)
        self.refresh_correction_badge()

    def on_correction_select(self, _event=None) -> None:
        if not hasattr(self, "corrections_tree"):
            return
        selected = self.corrections_tree.selection()
        if not selected:
            return
        row = self.study.get_review_request(selected[0])
        if not row:
            return
        self.correction_meta_label.configure(
            text=(
                f"{row.get('source_code', '')} • {row.get('subject', '')} • "
                f"{row.get('board', '')} {row.get('exam_year', '')}\n"
                f"Status: {row.get('status', '')} • Solicitado por: {row.get('username', '') or row.get('user_id', '')}"
            )
        )
        self.correction_preview.configure(state="normal")
        self.correction_preview.delete("1.0", "end")
        self.correction_preview.insert("1.0", str(row.get("statement", "")))
        self.correction_preview.configure(state="disabled")

    def open_selected_correction(self) -> None:
        if not hasattr(self, "corrections_tree"):
            return
        selected = self.corrections_tree.selection()
        if not selected:
            messagebox.showinfo(APP_NAME, "Selecione uma solicitação de correção.")
            return
        request_id = selected[0]
        row = self.study.get_review_request(request_id)
        if not row:
            return
        self.study.mark_review_opened(request_id)
        self.status_filter.set("todos")
        self.show_page("review")
        self.current_question_uid = str(row.get("question_uid", ""))
        self.refresh_question_list()
        uid = self.current_question_uid
        if uid and self.question_tree.exists(uid):
            self.question_tree.selection_set(uid)
            self.question_tree.see(uid)
            self.on_question_select()
        self.refresh_corrections_list()

    def resolve_selected_correction(self) -> None:
        selected = self.corrections_tree.selection() if hasattr(self, "corrections_tree") else ()
        if not selected:
            messagebox.showinfo(APP_NAME, "Selecione uma solicitação.")
            return
        self.study.resolve_review_request(selected[0])
        self.refresh_corrections_list()
        self.refresh_correction_badge()

    def delete_selected_correction(self) -> None:
        selected = self.corrections_tree.selection() if hasattr(self, "corrections_tree") else ()
        if not selected:
            return
        if not messagebox.askyesno(APP_NAME, "Excluir esta solicitação da fila? A questão continuará na base."):
            return
        self.study.delete_review_request(selected[0])
        self.refresh_corrections_list()
        self.refresh_correction_badge()

