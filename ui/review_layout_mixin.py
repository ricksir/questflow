from __future__ import annotations

from .common import *  # noqa: F401,F403


class ReviewLayoutMixin:
    def _build_review_page(self) -> tk.Frame:
        page = self._page()
        container = tk.Frame(page, bg=COLORS["background"])
        container.pack(fill="both", expand=True, padx=24, pady=20)
        self._section_title(
            container,
            "Revisar e organizar o banco",
            "As questões são classificadas pela matéria, aula e assunto da planilha AFRFB.",
        )

        search_bar = tk.Frame(container, bg=COLORS["background"])
        search_bar.pack(fill="x", pady=(0, 10))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_bar, textvariable=self.search_var)
        search_entry.pack(side="left", fill="x", expand=True)
        search_entry.bind("<Return>", lambda _event: self.refresh_question_list())
        self.status_filter = tk.StringVar(value="todos")
        ttk.Combobox(
            search_bar,
            textvariable=self.status_filter,
            values=["todos", "pendente", "aprovado", "aprovado_automaticamente"],
            state="readonly",
            width=24,
        ).pack(side="left", padx=8)
        ttk.Button(search_bar, text="Pesquisar", command=self.refresh_question_list).pack(side="left")
        ttk.Button(search_bar, text="Nova questão manual", style="Success.TButton", command=self.new_manual_question).pack(side="left", padx=(8, 0))

        review_tools = tk.Frame(container, bg=COLORS["background"])
        review_tools.pack(fill="x", pady=(0, 8))
        review_primary = tk.Frame(review_tools, bg=COLORS["background"])
        review_primary.pack(fill="x", pady=(0, 6))
        self.reread_button = ttk.Button(
            review_primary,
            text="Reler PDF (Ctrl+R)",
            style="Primary.TButton",
            command=self.reread_current_question,
        )
        self.reread_button.pack(side="left")
        self.reread_cancel_button = ttk.Button(
            review_primary,
            text="Cancelar",
            command=self.cancel_reread,
            state="disabled",
        )
        self.reread_cancel_button.pack(side="left", padx=(6, 0))
        self.deep_process_button = ttk.Button(
            review_primary,
            text="Analisar todas pendentes",
            command=self.process_pending_questions,
        )
        self.deep_process_button.pack(side="left", padx=(8, 0))
        self.deep_selected_button = ttk.Button(
            review_primary,
            text="Analisar selecionadas",
            command=self.process_selected_pending_questions,
        )
        self.deep_selected_button.pack(side="left", padx=(8, 0))

        review_web = tk.Frame(review_tools, bg=COLORS["background"])
        review_web.pack(fill="x")
        self.web_enrichment_button = ttk.Button(
            review_web,
            text="Web: questão selecionada",
            command=self.enrich_current_question_web,
        )
        self.web_enrichment_button.pack(side="left")
        self.web_batch_button = ttk.Button(
            review_web,
            text="Web: várias pendentes",
            command=self.enrich_pending_questions_web,
        )
        self.web_batch_button.pack(side="left", padx=(8, 0))
        self.reread_status = tk.Label(
            review_web,
            text="",
            bg=COLORS["background"],
            fg=COLORS["muted"],
            anchor="w",
            justify="left",
            wraplength=700,
        )
        self.reread_status.pack(side="left", padx=10, fill="x", expand=True)

        layout_tools = tk.Frame(container, bg=COLORS["background"])
        layout_tools.pack(fill="x", pady=(0, 10))
        ttk.Button(layout_tools, text="Duas janelas", command=self.show_review_both).pack(side="left", padx=3)
        ttk.Button(layout_tools, text="Só lista", command=self.show_review_list_only).pack(side="left", padx=3)
        ttk.Button(layout_tools, text="Só editor", command=self.show_review_editor_only).pack(side="left", padx=3)
        ttk.Button(layout_tools, text="Horizontal / vertical", command=self.toggle_review_orientation).pack(side="left", padx=3)
        ttk.Button(layout_tools, text="Trocar lados", command=self.swap_review_panes).pack(side="left", padx=3)
        ttk.Button(
            layout_tools,
            text="Excluir da base (Ctrl+Del)",
            style="Danger.TButton",
            command=self.delete_current_question,
        ).pack(side="right", padx=(8, 0))
        ttk.Button(
            layout_tools,
            text="Questão anulada",
            command=self.mark_current_question_annulled,
        ).pack(side="right", padx=(8, 0))

        self.review_split = tk.PanedWindow(
            container,
            orient=self.review_layout_orientation,
            bg=COLORS["background"],
            sashwidth=8,
            sashrelief="raised",
            relief="flat",
        )
        self.review_split.pack(fill="both", expand=True)

        self.review_list_surface = tk.Frame(self.review_split, bg="#FFFFFF", highlightbackground=COLORS["border"], highlightthickness=1)
        self.review_edit_surface = tk.Frame(self.review_split, bg="#FFFFFF", highlightbackground=COLORS["border"], highlightthickness=1)
        list_surface = self.review_list_surface
        edit_surface = self.review_edit_surface
        self._apply_review_layout()

        self.question_tree = ttk.Treeview(
            list_surface,
            columns=("codigo", "materia", "aula", "assunto", "ano", "banca", "status"),
            show="headings",
            selectmode="extended",
        )
        for key, title, width in [
            ("codigo", "Código", 82),
            ("materia", "Matéria", 115),
            ("aula", "Aula", 75),
            ("assunto", "Assunto", 245),
            ("ano", "Ano", 52),
            ("banca", "Banca", 105),
            ("status", "Revisão", 105),
        ]:
            self.question_tree.heading(key, text=title)
            self.question_tree.column(key, width=width, anchor="center" if key in ("ano", "aula") else "w")
        self.question_tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.question_tree.bind("<<TreeviewSelect>>", self.on_question_select)

        editor_canvas = tk.Canvas(edit_surface, bg="#FFFFFF", highlightthickness=0)
        self.editor_canvas = editor_canvas
        scrollbar = ttk.Scrollbar(edit_surface, orient="vertical", command=editor_canvas.yview)
        self.editor = tk.Frame(editor_canvas, bg="#FFFFFF")
        self.editor.bind("<Configure>", lambda _e: editor_canvas.configure(scrollregion=editor_canvas.bbox("all")))
        self.editor_canvas_window = editor_canvas.create_window((0, 0), window=self.editor, anchor="nw")
        editor_canvas.configure(yscrollcommand=scrollbar.set)
        editor_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        editor_canvas.bind(
            "<Configure>",
            lambda e: editor_canvas.itemconfigure(self.editor_canvas_window, width=e.width),
        )

        self.editor_vars: dict[str, tk.StringVar] = {}
        fields = [
            ("codigo_origem", "Código da questão"),
            ("materia", "Matéria da planilha"),
            ("aula_planilha", "Aula da planilha"),
            ("assunto", "Assunto principal"),
            ("assuntos", "Subassuntos (separados por |)"),
            ("banca", "Banca"),
            ("ano", "Ano"),
            ("orgao", "Órgão"),
            ("prova", "Prova completa"),
            ("cargo", "Cargo"),
            ("area", "Área"),
            ("especialidade", "Especialidade"),
            ("turno", "Turno"),
            ("tipo", "Tipo"),
            ("gabarito", "Gabarito"),
        ]
        grid = tk.Frame(self.editor, bg="#FFFFFF")
        grid.pack(fill="x", padx=16, pady=(14, 5))
        matter_values = self.taxonomy.materias if self.taxonomy else []
        for index, (key, label) in enumerate(fields):
            row, column = divmod(index, 2)
            field = tk.Frame(grid, bg="#FFFFFF")
            field.grid(row=row, column=column, sticky="ew", padx=(0 if column == 0 else 8, 8 if column == 0 else 0), pady=5)
            grid.grid_columnconfigure(column, weight=1)
            tk.Label(field, text=label, bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w")
            variable = tk.StringVar()
            self.editor_vars[key] = variable
            if key == "codigo_origem":
                widget = ttk.Entry(field, textvariable=variable, state="normal")
            elif key == "tipo":
                widget = ttk.Combobox(field, textvariable=variable, values=["certo_errado", "multipla_escolha"], state="normal")
            elif key == "materia":
                widget = ttk.Combobox(field, textvariable=variable, values=matter_values, state="normal")
                self.matter_combo = widget
            else:
                widget = ttk.Entry(field, textvariable=variable)
            widget.pack(fill="x", pady=(2, 0))

        self.statement_text = self._text_field(self.editor, "Enunciado", height=8)
        self.alternatives_text = self._text_field(
            self.editor,
            "Alternativas — uma por linha no formato A|texto. Para Certo/Errado use C|Certo e E|Errado.",
            height=9,
        )
        self.explanation_text = self._text_field(self.editor, "Explicação após a resposta (opcional)", height=4)

        image_box = tk.Frame(self.editor, bg="#FFFFFF", highlightbackground=COLORS["border"], highlightthickness=1)
        image_box.pack(fill="x", padx=16, pady=(6, 8))
        tk.Label(
            image_box,
            text="Imagem da questão",
            bg="#FFFFFF",
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=10, pady=(8, 4))
        self.question_image_info = tk.Label(
            image_box,
            text="O recorte automático aparecerá aqui. Se não ficar correto, anexe manualmente.",
            bg="#FFFFFF",
            fg=COLORS["text"],
            justify="left",
            anchor="w",
            wraplength=720,
        )
        self.question_image_info.pack(fill="x", padx=10)
        self.question_image_label = tk.Label(
            image_box,
            text="Sem imagem",
            bg="#F8FAFC",
            fg=COLORS["muted"],
            relief="solid",
            bd=1,
            width=60,
            height=18,
            anchor="center",
            justify="center",
            cursor="hand2",
        )
        self.question_image_label.pack(fill="both", expand=True, padx=10, pady=8)
        self.question_image_label.bind("<Button-1>", lambda _e: self.open_image_preview())
        image_actions = tk.Frame(image_box, bg="#FFFFFF")
        image_actions.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(image_actions, text="Ver imagem ampliada", command=self.open_image_preview).pack(side="left")
        ttk.Button(image_actions, text="Escolher/trocar imagem", command=self.attach_manual_image).pack(side="left", padx=8)
        ttk.Button(image_actions, text="Remover imagem", command=self.remove_current_image).pack(side="left")

        self.review_alerts = tk.Label(
            self.editor,
            text="Selecione uma questão.",
            bg="#FFF8E8",
            fg=COLORS["yellow"],
            anchor="w",
            justify="left",
            padx=10,
            pady=8,
            wraplength=720,
        )
        self.review_alerts.pack(fill="x", padx=16, pady=8)

        actions = tk.Frame(self.editor, bg="#FFFFFF")
        actions.pack(fill="x", padx=16, pady=(4, 18))
        ttk.Button(actions, text="Salvar alterações", style="Primary.TButton", command=self.save_current_question).pack(side="left")
        ttk.Button(actions, text="Salvar e aprovar", style="Success.TButton", command=lambda: self.save_current_question(approve=True)).pack(side="left", padx=8)
        ttk.Button(actions, text="Ver questão completa", command=self.open_full_question_preview).pack(side="left", padx=(18, 0))
        ttk.Button(actions, text="Prévia Telegram", command=self.open_telegram_preview).pack(side="left", padx=8)
        ttk.Button(actions, text="Excluir da base", style="Danger.TButton", command=self.delete_current_question).pack(side="right")
        ttk.Button(actions, text="Marcar anulada", command=self.mark_current_question_annulled).pack(side="right", padx=(0, 8))
        return page

    def _widget_is_inside(self, widget: tk.Widget | None, ancestor: tk.Widget) -> bool:
        current = widget
        while current is not None:
            if current == ancestor:
                return True
            try:
                current = current.master
            except Exception:
                return False
        return False

    def _route_review_mousewheel(self, event):
        if self.current_page != "review" or not hasattr(self, "editor_canvas"):
            return None
        try:
            target = self.winfo_containing(event.x_root, event.y_root)
        except Exception:
            target = None
        if target is None or not self._widget_is_inside(target, self.review_edit_surface):
            return None
        if self.review_layout_mode == "list":
            return None
        if getattr(event, "num", None) == 4:
            steps = -3
        elif getattr(event, "num", None) == 5:
            steps = 3
        else:
            delta = int(getattr(event, "delta", 0) or 0)
            if delta == 0:
                return None
            steps = -3 if delta > 0 else 3
            if abs(delta) >= 240:
                steps *= max(1, abs(delta) // 120)
        self.editor_canvas.yview_scroll(steps, "units")
        return "break"

    def _apply_review_layout(self) -> None:
        if not hasattr(self, "review_split"):
            return
        for pane in (self.review_list_surface, self.review_edit_surface):
            try:
                self.review_split.forget(pane)
            except tk.TclError:
                pass
        self.review_split.configure(orient=self.review_layout_orientation)
        ordered = [self.review_list_surface, self.review_edit_surface]
        if self.review_layout_swapped:
            ordered.reverse()
        if self.review_layout_mode == "list":
            self.review_split.add(self.review_list_surface, minsize=420, stretch="always")
        elif self.review_layout_mode == "editor":
            self.review_split.add(self.review_edit_surface, minsize=500, stretch="always")
        else:
            first, second = ordered
            self.review_split.add(first, minsize=360, stretch="always")
            self.review_split.add(second, minsize=420, stretch="always")
        self.after(80, self._set_default_review_sash)

    def _set_default_review_sash(self) -> None:
        if self.review_layout_mode != "both" or not hasattr(self, "review_split"):
            return
        try:
            if self.review_layout_orientation == "horizontal":
                position = max(360, int(self.review_split.winfo_width() * float(self.config_data.get("review_sash_ratio", 0.47) or 0.47)))
                self.review_split.sash_place(0, position, 0)
            else:
                position = max(260, int(self.review_split.winfo_height() * 0.43))
                self.review_split.sash_place(0, 0, position)
        except tk.TclError:
            pass

    def show_review_both(self) -> None:
        self.review_layout_mode = "both"
        self._apply_review_layout()

    def show_review_list_only(self) -> None:
        self.review_layout_mode = "list"
        self._apply_review_layout()

    def show_review_editor_only(self) -> None:
        self.review_layout_mode = "editor"
        self._apply_review_layout()

    def toggle_review_orientation(self) -> None:
        self.review_layout_orientation = "vertical" if self.review_layout_orientation == "horizontal" else "horizontal"
        self.review_layout_mode = "both"
        self._apply_review_layout()

    def swap_review_panes(self) -> None:
        self.review_layout_swapped = not self.review_layout_swapped
        self.review_layout_mode = "both"
        self._apply_review_layout()

    def _text_field(self, parent: tk.Widget, label: str, height: int) -> tk.Text:
        frame = tk.Frame(parent, bg="#FFFFFF")
        frame.pack(fill="x", padx=16, pady=5)
        tk.Label(frame, text=label, bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w")
        text = tk.Text(
            frame,
            height=height,
            wrap="word",
            font=("Segoe UI", 10),
            relief="solid",
            bd=1,
            highlightthickness=0,
            borderwidth=1,
        )
        text.pack(fill="x", pady=(2, 0))
        return text

    def refresh_question_list(self) -> None:
        if not hasattr(self, "question_tree"):
            return
        selected_uid = self.current_question_uid
        for item in self.question_tree.get_children():
            self.question_tree.delete(item)
        rows = self.question_queries.list(self.search_var.get(), self.status_filter.get())
        for row in rows:
            status = row["review_status"].replace("aprovado_automaticamente", "autoaprovada")
            topic = row.get("primary_topic", "") or row.get("topics_text", "")
            self.question_tree.insert(
                "",
                "end",
                iid=row["uid"],
                values=(
                    row["source_code"],
                    row.get("subject", ""),
                    row.get("lesson", ""),
                    topic,
                    row["exam_year"] or "",
                    row["board"],
                    status,
                ),
            )
        if selected_uid and self.question_tree.exists(selected_uid):
            self.question_tree.selection_set(selected_uid)
            self.question_tree.see(selected_uid)

