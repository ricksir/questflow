from __future__ import annotations

from .common import *  # noqa: F401,F403


class ImportMixin:
    def _build_import_page(self) -> tk.Frame:
        page = self._page()
        container = tk.Frame(page, bg=COLORS["background"])
        container.pack(fill="both", expand=True, padx=24, pady=20)
        self._section_title(
            container,
            "Importar questões de PDFs e imagens",
            "O programa usa OCR, identifica metadados, alternativas e relaciona o gabarito final.",
        )
        self._build_stat_cards(container)

        self.import_split = tk.PanedWindow(
            container,
            orient="vertical",
            sashwidth=9,
            sashrelief="raised",
            bg=COLORS["border"],
            bd=0,
            relief="flat",
            showhandle=True,
            opaqueresize=True,
        )
        self.import_split.pack(fill="both", expand=True)
        self.import_split.bind("<ButtonRelease-1>", self._save_import_split)

        surface = tk.Frame(
            self.import_split,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            bd=0,
        )
        self.import_split.add(surface, minsize=260, stretch="always")

        toolbar = tk.Frame(surface, bg="#FFFFFF")
        toolbar.pack(fill="x", padx=16, pady=14)
        ttk.Button(toolbar, text="Selecionar PDFs/imagens", style="Primary.TButton", command=self.select_pdfs).pack(side="left")
        ttk.Button(toolbar, text="Remover selecionado", command=self.remove_selected_pdf).pack(side="left", padx=8)
        ttk.Button(toolbar, text="Limpar lista", command=self.clear_pdf_list).pack(side="left")
        self.start_button = ttk.Button(toolbar, text="Analisar e guardar no banco", style="Success.TButton", command=self.start_import)
        self.start_button.pack(side="right")
        self.cancel_button = ttk.Button(toolbar, text="Cancelar", style="Danger.TButton", command=self.cancel_import, state="disabled")
        self.cancel_button.pack(side="right", padx=8)

        pdf_table = tk.Frame(surface, bg="#FFFFFF")
        pdf_table.pack(fill="both", expand=True, padx=16)
        pdf_table.rowconfigure(0, weight=1)
        pdf_table.columnconfigure(0, weight=1)
        columns = ("arquivo", "tamanho", "status")
        self.pdf_tree = ttk.Treeview(pdf_table, columns=columns, show="headings", selectmode="extended")
        pdf_headings = {"arquivo": "Arquivo PDF ou imagem", "tamanho": "Tamanho", "status": "Situação"}
        self.pdf_tree.column("arquivo", width=620, minwidth=220, anchor="w", stretch=True)
        self.pdf_tree.column("tamanho", width=110, minwidth=80, anchor="center", stretch=False)
        self.pdf_tree.column("status", width=180, minwidth=120, anchor="center", stretch=False)
        self.make_tree_sortable(self.pdf_tree, pdf_headings, {"arquivo": "text", "tamanho": "text", "status": "text"})
        pdf_vscroll = ttk.Scrollbar(pdf_table, orient="vertical", command=self.pdf_tree.yview)
        pdf_hscroll = ttk.Scrollbar(pdf_table, orient="horizontal", command=self.pdf_tree.xview)
        self.pdf_tree.configure(yscrollcommand=pdf_vscroll.set, xscrollcommand=pdf_hscroll.set)
        self.pdf_tree.grid(row=0, column=0, sticky="nsew")
        pdf_vscroll.grid(row=0, column=1, sticky="ns")
        pdf_hscroll.grid(row=1, column=0, sticky="ew")

        status_area = tk.Frame(surface, bg="#FFFFFF")
        status_area.pack(fill="x", padx=16, pady=15)
        self.import_status = tk.Label(
            status_area,
            text="Selecione um ou mais PDFs ou imagens para começar.",
            bg="#FFFFFF",
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.import_status.pack(fill="x")
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(status_area, variable=self.progress_var, maximum=100)
        self.progress.pack(fill="x", pady=(7, 0))

        recent = tk.Frame(
            self.import_split,
            bg="#FFFFFF",
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            bd=0,
        )
        self.import_split.add(recent, minsize=140, stretch="never")

        recent_header = tk.Frame(recent, bg="#FFFFFF")
        recent_header.pack(fill="x", padx=14, pady=(10, 6))
        title_area = tk.Frame(recent_header, bg="#FFFFFF")
        title_area.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_area, text="Importações recentes", bg="#FFFFFF", fg=COLORS["text"],
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w")
        tk.Label(
            title_area,
            text="Clique em um cabeçalho para ordenar. Arraste a barra divisória para aumentar ou diminuir esta área.",
            bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(1, 0))

        view_controls = tk.Frame(recent_header, bg="#FFFFFF")
        view_controls.pack(side="right")
        ttk.Button(view_controls, text="A−", width=3, command=lambda: self.change_imports_table_zoom(-1)).pack(side="left")
        self.imports_zoom_label = tk.Label(
            view_controls,
            text=f"{int(self.config_data.get('imports_table_font_size', 10))} pt",
            bg="#FFFFFF", fg=COLORS["muted"], font=("Segoe UI", 9), width=5,
        )
        self.imports_zoom_label.pack(side="left", padx=4)
        ttk.Button(view_controls, text="A+", width=3, command=lambda: self.change_imports_table_zoom(1)).pack(side="left")
        ttk.Button(view_controls, text="Restaurar", command=self.reset_imports_table_view).pack(side="left", padx=(8, 0))

        recent_table = tk.Frame(recent, bg="#FFFFFF")
        recent_table.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        recent_table.rowconfigure(0, weight=1)
        recent_table.columnconfigure(0, weight=1)
        import_columns = ("data", "arquivo", "extraidas", "inseridas", "duplicadas")
        self.imports_tree = ttk.Treeview(
            recent_table,
            columns=import_columns,
            show="headings",
            height=5,
            style="Imports.Treeview",
        )
        import_headings = {
            "data": "Data",
            "arquivo": "Arquivo",
            "extraidas": "Extraídas",
            "inseridas": "Novas",
            "duplicadas": "Duplicadas",
        }
        for key, width, minwidth, anchor, stretch in [
            ("data", 165, 135, "center", False),
            ("arquivo", 520, 220, "w", True),
            ("extraidas", 105, 80, "center", False),
            ("inseridas", 95, 75, "center", False),
            ("duplicadas", 110, 85, "center", False),
        ]:
            self.imports_tree.column(key, width=width, minwidth=minwidth, anchor=anchor, stretch=stretch)
        self.make_tree_sortable(
            self.imports_tree,
            import_headings,
            {"data": "text", "arquivo": "text", "extraidas": "int", "inseridas": "int", "duplicadas": "int"},
        )
        recent_vscroll = ttk.Scrollbar(recent_table, orient="vertical", command=self.imports_tree.yview)
        recent_hscroll = ttk.Scrollbar(recent_table, orient="horizontal", command=self.imports_tree.xview)
        self.imports_tree.configure(yscrollcommand=recent_vscroll.set, xscrollcommand=recent_hscroll.set)
        self.imports_tree.grid(row=0, column=0, sticky="nsew")
        recent_vscroll.grid(row=0, column=1, sticky="ns")
        recent_hscroll.grid(row=1, column=0, sticky="ew")

        self.after(180, self._restore_import_split)
        return page

    def refresh_recent_imports(self) -> None:
        if not hasattr(self, "imports_tree"):
            return
        for item in self.imports_tree.get_children():
            self.imports_tree.delete(item)
        for row in self.question_queries.recent_imports():
            date = row["imported_at"].replace("T", " ").replace("+00:00", "")
            self.imports_tree.insert("", "end", values=(date, row["source_file"], row["extracted_count"], row["inserted_count"], row["duplicate_count"]))
        self._reapply_tree_sort(self.imports_tree)

    def select_pdfs(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Selecionar PDFs ou imagens de questões",
            filetypes=[
                ("PDFs e imagens", "*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp"),
                ("Arquivos PDF", "*.pdf"),
                ("Imagens", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        for path in paths:
            if path not in self.import_files:
                self.import_files.append(path)
        self.refresh_pdf_list()

    def refresh_pdf_list(self) -> None:
        for item in self.pdf_tree.get_children():
            self.pdf_tree.delete(item)
        for path in self.import_files:
            size = Path(path).stat().st_size / (1024 * 1024)
            self.pdf_tree.insert("", "end", iid=path, values=(Path(path).name, f"{size:.1f} MB", "Aguardando"))
        self._reapply_tree_sort(self.pdf_tree)

    def remove_selected_pdf(self) -> None:
        selected = set(self.pdf_tree.selection())
        self.import_files = [path for path in self.import_files if path not in selected]
        self.refresh_pdf_list()

    def clear_pdf_list(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.import_files.clear()
        self.refresh_pdf_list()

    def start_import(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not self.import_files:
            messagebox.showinfo(APP_NAME, "Selecione pelo menos um PDF ou uma imagem.")
            return
        self.save_settings(silent=True)
        self.cancel_event.clear()
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress_var.set(0)
        self.import_status.configure(text="Preparando a análise...")
        files = list(self.import_files)
        self.worker = threading.Thread(target=self._import_worker, args=(files,), daemon=True)
        self.worker.start()

    def _import_worker(self, files: list[str]) -> None:
        try:
            total = len(files)
            summary = {"extracted": 0, "inserted": 0, "duplicates": 0, "repaired": 0, "pending": 0}
            for file_index, path in enumerate(files):
                if self.cancel_event.is_set():
                    raise ExtractionCancelled()
                self.event_queue.put(("file_status", path, "Analisando"))
                config = ExtractorConfig(
                    dpi=int(self.config_data.get("dpi", 180)),
                    languages=str(self.config_data.get("languages", "por+eng")),
                    tesseract_cmd=str(self.config_data.get("tesseract_cmd", "")),
                )

                def report(value: float, message: str) -> None:
                    overall = (file_index + value) / total
                    self.event_queue.put(("progress", overall, message))

                extraction = extract_pdf(
                    path,
                    config=config,
                    progress=report,
                    cancel_event=self.cancel_event,
                    taxonomy=self.taxonomy,
                    asset_dir=QUESTION_IMAGE_DIR,
                    markdown_cache_dir=MARKDOWN_CACHE_DIR,
                    force_markdown_ocr=False,
                )
                for question in extraction.get("questions", []):
                    question.setdefault("fonte", {})["caminho_arquivo"] = str(Path(path).resolve())
                result = self.question_commands.import_extraction(extraction)
                for key in summary:
                    summary[key] += result[key]
                self.event_queue.put(("file_status", path, f"Concluído: {result['inserted']} novas"))
            self.event_queue.put(("done", summary))
        except ExtractionCancelled:
            self.event_queue.put(("cancelled",))
        except Exception as error:
            self.event_queue.put(("error", str(error), traceback.format_exc()))

    def _poll_events(self) -> None:
        try:
            while True:
                event = self.event_queue.get_nowait()
                kind = event[0]
                if kind == "progress":
                    self.progress_var.set(event[1] * 100)
                    self.import_status.configure(text=event[2])
                elif kind == "file_status":
                    path, status = event[1], event[2]
                    if self.pdf_tree.exists(path):
                        values = list(self.pdf_tree.item(path, "values"))
                        values[2] = status
                        self.pdf_tree.item(path, values=values)
                elif kind == "done":
                    summary = event[1]
                    self._finish_worker()
                    self.progress_var.set(100)
                    self.import_status.configure(
                        text=(
                            f"Concluído: {summary['extracted']} extraídas, {summary['inserted']} novas, "
                            f"{summary['duplicates']} duplicatas ignoradas, {summary['repaired']} existentes reparadas "
                            f"e {summary['pending']} pendentes."
                        )
                    )
                    self.study.sync_questions()
                    self.refresh_all()
                    messagebox.showinfo(APP_NAME, self.import_status.cget("text"))
                elif kind == "cancelled":
                    self._finish_worker()
                    self.import_status.configure(text="Análise cancelada.")
                elif kind == "error":
                    self._finish_worker()
                    self.import_status.configure(text="Falha durante a análise.")
                    messagebox.showerror(APP_NAME, f"{event[1]}\n\n{event[2][-1200:]}")
                    self.update_idletasks()
                elif kind == "reread_progress":
                    self.reread_status.configure(text=str(event[1]))
                    self.update_idletasks()
                elif kind == "reread_done":
                    uid, message = event[1], event[2]
                    self._finish_reread()
                    self.reread_status.configure(text="100% • Concluído • questão atualizada")
                    self.study.sync_questions()
                    self.refresh_all()
                    if self.question_tree.exists(uid):
                        self.question_tree.selection_set(uid)
                        self.question_tree.see(uid)
                    self.current_question_uid = uid
                    self.on_question_select()
                    messagebox.showinfo(APP_NAME, message)
                elif kind == "reread_cancelled":
                    self._finish_reread()
                    self.reread_status.configure(text="Releitura cancelada.")
                elif kind == "reread_error":
                    self._finish_reread()
                    self.reread_status.configure(text="Falha na releitura.")
                    messagebox.showerror(APP_NAME, f"{event[1]}\n\n{event[2][-1400:]}")
                elif kind == "deep_progress":
                    self.reread_status.configure(text=str(event[1]))
                    self.update_idletasks()
                elif kind == "deep_done":
                    summary = event[1]
                    self._finish_deep_process()
                    self.reread_status.configure(
                        text=(
                            f"100% • Concluído: {summary['processed']} processadas, "
                            f"{summary['approved']} aprovadas, {summary['pending']} ainda pendentes"
                        )
                    )
                    self.study.sync_questions()
                    self.refresh_all()
                    messagebox.showinfo(
                        APP_NAME,
                        (
                            "Processamento apurado concluído.\n\n"
                            f"Processadas: {summary['processed']}\n"
                            f"Aprovadas automaticamente: {summary['approved']}\n"
                            f"Ainda pendentes: {summary['pending']}\n"
                            f"Questões relidas no PDF/Markdown: {summary['reread']}\n"
                            f"PDF original não localizado: {summary.get('source_missing', 0)}\n"
                            f"Falhas na releitura: {summary.get('reread_failed', 0)}\n"
                            f"Questão não localizada após reler o PDF: {summary.get('candidate_missing', 0)}\n"
                            f"Pesquisas web assistidas: {summary.get('web', 0)}"
                        ),
                    )
                elif kind == "deep_cancelled":
                    self._finish_deep_process()
                    self.reread_status.configure(text="Processamento apurado cancelado.")
                    self.study.sync_questions()
                    self.refresh_all()
                elif kind == "deep_error":
                    self._finish_deep_process()
                    self.reread_status.configure(text="Falha no processamento apurado.")
                    messagebox.showerror(APP_NAME, f"{event[1]}\n\n{event[2][-1800:]}")
                elif kind == "web_enrichment_progress":
                    self.reread_status.configure(text=str(event[1]))
                    self.update_idletasks()
                elif kind == "web_enrichment_batch_done":
                    items = list(event[1])
                    self._finish_web_enrichment()
                    total_results = sum(int(item.get("results", 0) or 0) for item in items)
                    self.reread_status.configure(
                        text=f"100% • Pesquisa concluída: {len(items)} questão(ões), {total_results} resultado(s)"
                    )
                    self.study.sync_questions()
                    self.refresh_all()
                    self._show_web_batch_results(items)
                elif kind == "web_enrichment_error":
                    self._finish_web_enrichment()
                    self.reread_status.configure(text="Pesquisa web indisponível.")
                    messagebox.showerror(APP_NAME, f"{event[1]}\n\n{event[2][-1200:]}")
                elif kind == "flow_event":
                    self._handle_flow_event(event[1], event[2])
        except queue.Empty:
            pass
        self.after(120, self._poll_events)

    def _finish_worker(self) -> None:
        self.start_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.worker = None

    def cancel_import(self) -> None:
        self.cancel_event.set()
        self.import_status.configure(text="Cancelamento solicitado. A página atual será finalizada com segurança.")

