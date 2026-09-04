from __future__ import annotations

from .common import *  # noqa: F401,F403


class CatalogSettingsMixin:
    def refresh_taxonomy_status(self) -> None:
        if not hasattr(self, "taxonomy_status_label"):
            return
        if self.taxonomy is None:
            self.taxonomy_status_label.configure(
                text="Nenhuma planilha ativa. Faça um teste antes de ativar uma nova fonte.", bg="#FFF4E5", fg=COLORS["yellow"]
            )
            return
        source = dict(self.taxonomy.payload.get("source", {}) or {})
        generated = self.taxonomy.payload.get("generated_at", source.get("snapshot_date", ""))
        trails = []
        for task in self.taxonomy.tasks:
            match = re.search(r"(\d+)", str(task.get("trilha", "") or ""))
            if match:
                trails.append(int(match.group(1)))
        trail_text = f"Trilhas {min(trails):02d}–{max(trails):02d}" if trails else "faixa de trilhas não identificada"
        catalog = dict(self.taxonomy.payload.get("course_catalog", {}) or {})
        version = str(catalog.get("version") or self.config_data.get("course_catalog_version") or "snapshot legado")
        active_url = str(self.config_data.get("taxonomy_spreadsheet_url", source.get("url", "")) or "").strip()
        text = (
            f"Planilha atual: {self.taxonomy.source_name}\n"
            f"Fonte: {trail_text} • {len(self.taxonomy.materias)} matérias • {len(self.taxonomy.tasks)} tarefas\n"
            f"Última sincronização: {generated or 'snapshot local'} • Catálogo: {version}\n"
            f"Link ativo: {active_url or 'não informado'}"
        )
        self.taxonomy_status_label.configure(text=text, bg="#EEF5FB", fg=COLORS["navy"])

    def _catalog_service(self) -> CourseCatalogService:
        return CourseCatalogService(self.database, TAXONOMY_PATH, CONFIG_PATH)

    def _current_taxonomy_payload(self) -> dict:
        return dict(self.taxonomy.payload) if self.taxonomy is not None else {}

    def _show_catalog_preflight(self, report: dict, *, allow_apply: bool) -> dict:
        counts = dict(report.get("counts", {}) or {})
        window = tk.Toplevel(self)
        window.title("QuestFlow — análise da nova planilha")
        window.geometry("1080x700")
        window.minsize(900, 560)
        window.transient(self)
        window.grab_set()
        root = tk.Frame(window, bg="#F3F6FA")
        root.pack(fill="both", expand=True)
        header = tk.Frame(root, bg="#FFFFFF")
        header.pack(fill="x", padx=18, pady=(18, 10))
        tk.Label(header, text="NOVA PLANILHA DETECTADA", bg="#FFFFFF", fg=COLORS["navy"], font=("Segoe UI Semibold", 16)).pack(anchor="w", padx=14, pady=(12, 4))
        sheets = ", ".join(str(x) for x in report.get("sheets", []) if str(x).strip()) or "não identificadas"
        summary = (
            f"Abas encontradas: {sheets}\n"
            f"✓ {counts.get('equal', 0)} correspondências iguais   ~ {counts.get('updated', 0)} atualizadas   "
            f"+ {counts.get('new', 0)} novas   ! {counts.get('archived', 0)} arquivadas   ? {counts.get('uncertain', 0)} incertas\n"
            "Progresso pessoal, respostas, FSRS, Knowledge Tracing, IRT, mastery, XP, sessões e histórico Mobile não são zerados. "
            "Campos vazios da nova planilha não sobrescrevem dados pessoais já conhecidos."
        )
        tk.Label(header, text=summary, bg="#FFFFFF", fg=COLORS["text"], justify="left", wraplength=1000).pack(anchor="w", padx=14, pady=(0, 12))

        filters = tk.Frame(root, bg="#F3F6FA")
        filters.pack(fill="x", padx=18, pady=(0, 8))
        selected = tk.StringVar(value="all")
        labels = [("Todas", "all"), ("Novas", "new"), ("Alteradas", "updated"), ("Removidas", "archived"), ("Conflitos", "uncertain")]
        for label, value in labels:
            ttk.Radiobutton(filters, text=label, value=value, variable=selected).pack(side="left", padx=(0, 10))

        columns = ("tipo", "trilha", "aula", "materia", "situacao", "acao")
        tree = ttk.Treeview(root, columns=columns, show="headings", selectmode="browse")
        headings = {"tipo":"TIPO", "trilha":"TRILHA", "aula":"AULA", "materia":"MATÉRIA", "situacao":"SITUAÇÃO", "acao":"AÇÃO"}
        widths = {"tipo":110, "trilha":90, "aula":100, "materia":210, "situacao":180, "acao":340}
        for col in columns:
            tree.heading(col, text=headings[col])
            tree.column(col, width=widths[col], anchor="w")
        tree.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        tags = {"new":"#EAF8F0", "updated":"#FFF6E5", "archived":"#FDECEC", "uncertain":"#FCE8F3", "equal":"#FFFFFF"}
        for tag, color in tags.items():
            tree.tag_configure(tag, background=color)

        result = {"apply": False, "resolutions": {}}
        row_map: dict[str, dict] = {}
        uncertain_keys = {str(item.get("lesson_key")) for item in report.get("diffs", []) if str(item.get("change_type")) == "uncertain"}

        def fill(*_args):
            tree.delete(*tree.get_children())
            row_map.clear()
            wanted = selected.get()
            for index, item in enumerate(report.get("diffs", [])):
                kind = str(item.get("change_type", ""))
                if wanted != "all" and kind != wanted:
                    continue
                key = str(item.get("lesson_key") or "")
                resolution = dict(result["resolutions"].get(key, {}) or {})
                if kind == "uncertain" and resolution.get("action") == "same":
                    situation = "Resolvida: mesma aula"
                    action_text = "Progresso será preservado na correspondência escolhida."
                elif kind == "uncertain" and resolution.get("action") == "new":
                    situation = "Resolvida: aula nova"
                    action_text = "Será criada como nova; progresso antigo não será movido."
                else:
                    situation = {"equal":"Igual / progresso preservado", "updated":"Estrutura atualizada", "new":"Aula nova", "archived":"Removida / arquivada", "uncertain":"Correspondência incerta"}.get(kind, kind)
                    action_text = item.get("action", "")
                iid = f"row_{index}"
                row_map[iid] = item
                tree.insert("", "end", iid=iid, values=(kind, item.get("trail", ""), item.get("lesson", ""), item.get("subject", ""), situation, action_text), tags=(kind,))
            update_apply_state()

        def unresolved_keys() -> set[str]:
            return {key for key in uncertain_keys if str(dict(result["resolutions"].get(key, {}) or {}).get("action") or "") not in {"same", "new"}}

        def update_apply_state():
            if not allow_apply or "apply_button" not in locals_holder:
                return
            button = locals_holder["apply_button"]
            if unresolved_keys():
                button.state(["disabled"])
            else:
                button.state(["!disabled"])

        def resolve_selected():
            selection = tree.selection()
            if not selection:
                messagebox.showinfo(APP_NAME, "Selecione uma linha de correspondência incerta para revisar.", parent=window)
                return
            item = row_map.get(selection[0], {})
            if str(item.get("change_type")) != "uncertain":
                messagebox.showinfo(APP_NAME, "A linha selecionada não possui conflito de correspondência.", parent=window)
                return
            key = str(item.get("lesson_key") or "")
            candidates = list(item.get("candidates") or [])
            dialog = tk.Toplevel(window)
            dialog.title("Resolver correspondência")
            dialog.geometry("760x430")
            dialog.transient(window)
            dialog.grab_set()
            body = tk.Frame(dialog, bg="#FFFFFF", padx=18, pady=18)
            body.pack(fill="both", expand=True)
            tk.Label(body, text="Correspondência incerta", bg="#FFFFFF", fg=COLORS["navy"], font=("Segoe UI Semibold", 14)).pack(anchor="w")
            tk.Label(
                body,
                text=(f"Nova planilha: {item.get('trail','')} / Aula {item.get('lesson','')} / {item.get('subject','')}\n"
                      f"{item.get('current_title','')}\n\nSelecione uma aula antiga apenas se tiver certeza de que é a mesma aula."),
                bg="#FFFFFF", fg=COLORS["text"], justify="left", wraplength=710,
            ).pack(anchor="w", pady=(6, 10))
            listbox = tk.Listbox(body, height=9, exportselection=False)
            listbox.pack(fill="both", expand=True)
            for cand in candidates:
                listbox.insert("end", f"{cand.get('trail','')} | tarefa {cand.get('task_no','')} | aula {cand.get('lesson','')} | {cand.get('subject','')} | {cand.get('title','')}")
            if candidates:
                listbox.selection_set(0)
            buttons = tk.Frame(body, bg="#FFFFFF")
            buttons.pack(fill="x", pady=(12, 0))

            def same_lesson():
                current = listbox.curselection()
                if not current:
                    messagebox.showinfo(APP_NAME, "Selecione a aula antiga correspondente.", parent=dialog)
                    return
                cand = candidates[int(current[0])]
                result["resolutions"][key] = {"action": "same", "old_key": str(cand.get("lesson_key") or "")}
                dialog.destroy()
                fill()

            def new_lesson():
                result["resolutions"][key] = {"action": "new"}
                dialog.destroy()
                fill()

            def ignore_now():
                result["resolutions"].pop(key, None)
                dialog.destroy()
                fill()

            ttk.Button(buttons, text="É a mesma aula", style="Primary.TButton", command=same_lesson).pack(side="left")
            ttk.Button(buttons, text="É uma aula nova", command=new_lesson).pack(side="left", padx=8)
            ttk.Button(buttons, text="Ignorar por enquanto", command=ignore_now).pack(side="right")
            self.wait_window(dialog)

        selected.trace_add("write", fill)
        actions = tk.Frame(root, bg="#F3F6FA")
        actions.pack(fill="x", padx=18, pady=(0, 18))
        locals_holder: dict[str, object] = {}
        ttk.Button(actions, text="Cancelar" if allow_apply else "Fechar", command=window.destroy).pack(side="right")
        if allow_apply:
            apply_button = ttk.Button(actions, text="Mesclar e usar nova planilha", style="Primary.TButton")
            locals_holder["apply_button"] = apply_button
            apply_button.pack(side="right", padx=(0, 8))
            if uncertain_keys:
                ttk.Button(actions, text="Resolver correspondência", command=resolve_selected).pack(side="left")
            def confirm():
                if unresolved_keys():
                    messagebox.showwarning(APP_NAME, "Ainda existem correspondências incertas. Resolva-as ou cancele a operação.", parent=window)
                    return
                result["apply"] = True
                window.destroy()
            apply_button.configure(command=confirm)
        fill()
        self.wait_window(window)
        return result

    def _activate_catalog_result(self, result: dict, new_url: str) -> None:
        payload = dict(result["payload"])
        self.taxonomy = SpreadsheetTaxonomy(payload, TAXONOMY_PATH)
        self.config_data["taxonomy_spreadsheet_url"] = new_url
        self.config_data["course_catalog_version"] = str(result.get("catalog_version", ""))
        self.config_data["course_catalog_last_import_id"] = str(result.get("import_id", ""))
        if "taxonomy_spreadsheet_url" in self.setting_vars:
            self.setting_vars["taxonomy_spreadsheet_url"].set(new_url)
        if hasattr(self, "matter_combo"):
            self.matter_combo.configure(values=self.taxonomy.materias)
        if hasattr(self, "coverage_subject_combo"):
            self.coverage_subject_combo.configure(values=["Todas as matérias"] + self.taxonomy.materias)
            self.coverage_subject_var.set("Todas as matérias")
        if hasattr(self, "study") and self.study is not None:
            self.study.refresh_studied_scope(self.taxonomy.tasks)
        self.refresh_taxonomy_status()
        self.refresh_coverage_map()

    def _show_catalog_post_merge(self, result: dict) -> None:
        summary = dict(result.get("summary", {}) or {})
        window = tk.Toplevel(self)
        window.title("QuestFlow — mesclagem concluída")
        window.geometry("720x560")
        window.minsize(620, 480)
        window.transient(self)
        body = tk.Frame(window, bg="#FFFFFF", padx=22, pady=20)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="MESCLAGEM CONCLUÍDA", bg="#FFFFFF", fg=COLORS["navy"], font=("Segoe UI Semibold", 16)).pack(anchor="w")
        fsrs = summary.get("fsrs_rows_preserved", 0)
        kt = summary.get("knowledge_tracing_rows_preserved", 0)
        fsrs_text = str(fsrs) if isinstance(fsrs, int) and fsrs >= 0 else "verificar relatório"
        kt_text = str(kt) if isinstance(kt, int) and kt >= 0 else "verificar relatório"
        backup = dict(result.get("backup", {}) or {})
        text = (
            f"Aulas preservadas: {summary.get('progress_preserved', 0)}\n"
            f"Aulas atualizadas: {summary.get('updated', 0)}\n"
            f"Aulas novas: {summary.get('new', 0)}\n"
            f"Aulas arquivadas: {summary.get('archived', 0)}\n\n"
            f"Progressos pessoais sobrescritos por vazio: {summary.get('personal_fields_overwritten_by_blank', 0)}\n"
            f"FSRS preservados: {fsrs_text}\n"
            f"Knowledge Tracing preservado: {kt_text}\n\n"
            f"quick_check: {result.get('quick_check', '')}\n"
            f"Foreign keys: {result.get('foreign_key_violations', 0)}\n"
            f"Backup SHA-256: {backup.get('sha256', '')}\n"
            f"Backup: {backup.get('path', '') or 'não necessário (importação idempotente)'}\n\n"
            "A nova planilha agora é a fonte ativa. O Mobile recebe apenas o estado consolidado."
        )
        tk.Label(body, text=text, bg="#FFFFFF", fg=COLORS["text"], justify="left", anchor="nw", wraplength=665).pack(fill="both", expand=True, pady=(12, 14))
        actions = tk.Frame(body, bg="#FFFFFF")
        actions.pack(fill="x")

        def export_report():
            path = filedialog.asksaveasfilename(
                parent=window,
                defaultextension=".json",
                filetypes=[("Relatório JSON", "*.json")],
                initialfile=f"QuestFlow_Catalog_Merge_{result.get('catalog_version','')}.json",
            )
            if not path:
                return
            export_payload = {
                "release": APP_VERSION,
                "mobile_version": "0.12.0",
                "catalog_version": result.get("catalog_version"),
                "import_id": result.get("import_id"),
                "merge_strategy": MERGE_STRATEGY,
                "summary": summary,
                "backup": backup,
                "quick_check": result.get("quick_check"),
                "foreign_key_violations": result.get("foreign_key_violations"),
                "preflight": result.get("preflight"),
            }
            Path(path).write_text(json.dumps(export_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            messagebox.showinfo(APP_NAME, f"Relatório exportado em:\n{path}", parent=window)

        ttk.Button(actions, text="Exportar relatório", command=export_report).pack(side="left")
        ttk.Button(actions, text="Fechar", style="Primary.TButton", command=window.destroy).pack(side="right")
        self.wait_window(window)

    def test_taxonomy_spreadsheet(self) -> None:
        url = self.setting_vars["taxonomy_spreadsheet_url"].get().strip()
        if not url:
            messagebox.showerror(APP_NAME, "Informe o link da nova planilha.")
            return
        try:
            with tempfile.TemporaryDirectory(prefix="questflow_catalog_preflight_") as temp_dir:
                xlsx = download_public_spreadsheet(url, Path(temp_dir) / "trilhas.xlsx")
                payload = build_taxonomy_from_xlsx(xlsx, source_url=url)
            report = self._catalog_service().preflight(payload, self._current_taxonomy_payload())
            self._show_catalog_preflight(report, allow_apply=False)
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Planilha incompatível ou indisponível:\n{error}\n\nA fonte atual não foi alterada.")

    def update_taxonomy_from_internet(self) -> None:
        url = self.setting_vars["taxonomy_spreadsheet_url"].get().strip()
        if not url:
            messagebox.showerror(APP_NAME, "Informe o link da nova planilha.")
            return
        try:
            with tempfile.TemporaryDirectory(prefix="questflow_catalog_merge_") as temp_dir:
                xlsx = download_public_spreadsheet(url, Path(temp_dir) / "trilhas.xlsx")
                payload = build_taxonomy_from_xlsx(xlsx, source_url=url)
            service = self._catalog_service()
            report = service.preflight(payload, self._current_taxonomy_payload())
            decision = self._show_catalog_preflight(report, allow_apply=True)
            if not decision.get("apply"):
                return
            result = service.apply(payload, self._current_taxonomy_payload(), new_url=url, resolutions=decision.get("resolutions"))
            self._activate_catalog_result(result, url)
        except Exception as error:
            messagebox.showerror(APP_NAME, f"A troca da planilha foi cancelada com segurança:\n{error}\n\nA fonte anterior continua ativa.")
            return
        summary = dict(result.get("summary", {}) or {})
        messagebox.showinfo(
            APP_NAME,
            "MESCLAGEM CONCLUÍDA\n\n"
            f"Aulas preservadas: {summary.get('progress_preserved', 0)}\n"
            f"Aulas atualizadas: {summary.get('updated', 0)}\n"
            f"Aulas novas: {summary.get('new', 0)}\n"
            f"Aulas arquivadas: {summary.get('archived', 0)}\n"
            f"Campos pessoais sobrescritos por vazio: {summary.get('personal_fields_overwritten_by_blank', 0)}\n"
            f"Backup: {result.get('backup', {}).get('path', '')}\n"
            f"quick_check: {result.get('quick_check', '')} • foreign keys: {result.get('foreign_key_violations', 0)}\n\n"
            "A nova planilha agora é a fonte ativa."
        )

    def import_taxonomy_xlsx(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecionar a nova planilha de estudos",
            filetypes=[("Planilha Excel", "*.xlsx"), ("Todos os arquivos", "*.*")],
        )
        if not path:
            return
        url = self.setting_vars["taxonomy_spreadsheet_url"].get().strip() or str(self.config_data.get("taxonomy_spreadsheet_url", DEFAULT_SPREADSHEET_URL))
        try:
            payload = build_taxonomy_from_xlsx(path, source_url=url)
            service = self._catalog_service()
            report = service.preflight(payload, self._current_taxonomy_payload())
            decision = self._show_catalog_preflight(report, allow_apply=True)
            if not decision.get("apply"):
                return
            result = service.apply(payload, self._current_taxonomy_payload(), new_url=url, resolutions=decision.get("resolutions"))
            self._activate_catalog_result(result, url)
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Planilha incompatível ou mesclagem bloqueada:\n{error}\n\nNenhum dado foi perdido.")
            return
        self._show_catalog_post_merge(result)

    def reclassify_database(self) -> None:
        if self.taxonomy is None:
            messagebox.showinfo(APP_NAME, "Carregue uma taxonomia antes de reclassificar.")
            return
        stats = self.question_queries.stats()
        if stats["total"] == 0:
            messagebox.showinfo(APP_NAME, "O banco ainda não possui questões.")
            return
        if not messagebox.askyesno(
            APP_NAME,
            f"Reclassificar {stats['total']} questões usando a planilha ativa?\n"
            "As edições de matéria, aula e assunto serão recalculadas.",
        ):
            return
        try:
            result = self.question_commands.reclassify_all(self.taxonomy)
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Falha na reclassificação:\n{error}")
            return
        self.refresh_all()
        messagebox.showinfo(
            APP_NAME,
            f"Reclassificação concluída: {result['updated']} atualizadas e "
            f"{result['review']} marcadas para revisão da taxonomia.",
        )

