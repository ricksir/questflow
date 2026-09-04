from __future__ import annotations

from .common import *  # noqa: F401,F403


class ReviewEnrichmentMixin:
    @staticmethod
    def _normalized_statement(value: str) -> str:
        value = str(value or "").lower()
        value = re.sub(r"\s+", " ", value)
        value = re.sub(r"[^a-z0-9áàâãéêíóôõúç ]+", "", value)
        return value.strip()

    def _find_reread_match(self, current: dict, candidates: list[dict]) -> dict | None:
        current_code = str(current.get("codigo_origem", "")).strip()
        current_number = current.get("numero_origem")
        for candidate in candidates:
            if current_code and str(candidate.get("codigo_origem", "")).strip() == current_code:
                return candidate
        numbered = [candidate for candidate in candidates if current_number is not None and candidate.get("numero_origem") == current_number]
        if len(numbered) == 1:
            return numbered[0]
        current_text = self._normalized_statement(current.get("enunciado", ""))
        if not current_text:
            return numbered[0] if numbered else None
        pool = numbered or candidates
        best = None
        best_score = 0.0
        for candidate in pool:
            score = SequenceMatcher(None, current_text, self._normalized_statement(candidate.get("enunciado", ""))).ratio()
            if score > best_score:
                best = candidate
                best_score = score
        return best if best_score >= 0.38 else None

    def _start_web_enrichment(self, uids: list[str], *, description: str) -> None:
        if self.web_enrichment_worker and self.web_enrichment_worker.is_alive():
            messagebox.showinfo(APP_NAME, "Já existe uma pesquisa web em andamento.")
            return
        uids = list(dict.fromkeys(uid for uid in uids if uid))
        if not uids:
            messagebox.showinfo(APP_NAME, "Nenhuma questão pendente foi selecionada para pesquisa.")
            return
        if not messagebox.askyesno(
            APP_NAME,
            f"Serão pesquisadas {len(uids)} questão(ões) {description}.\n\n"
            "A pesquisa abrirá primeiro a página do Google e tentará confirmar a questão pelo código, "
            "banca, ano e enunciado. Se a página carregada confirmar a questão, os dados exibidos nela serão "
            "transcritos imediatamente e nenhum outro link será aberto automaticamente. Somente quando a "
            "página do Google não confirmar a questão o programa tentará resultados adicionais e, depois, "
            "a busca pelo enunciado. Continuar?",
        ):
            return
        for button_name in ("web_enrichment_button", "web_batch_button"):
            button = getattr(self, button_name, None)
            if button is not None:
                button.configure(state="disabled")
        self.reread_status.configure(text=f"0% • Preparando pesquisa de {len(uids)} questão(ões)...")
        self.web_enrichment_worker = threading.Thread(
            target=self._web_enrichment_batch_worker,
            args=(uids,),
            daemon=True,
            name="questflow-web-enrichment",
        )
        self.web_enrichment_worker.start()

    def enrich_current_question_web(self) -> None:
        uid = self.current_question_uid
        if not uid:
            messagebox.showinfo(APP_NAME, "Selecione uma questão primeiro.")
            return
        self._start_web_enrichment([uid], description="da seleção atual")

    def enrich_pending_questions_web(self) -> None:
        selected: list[str] = []
        if hasattr(self, "question_tree"):
            for uid in self.question_tree.selection():
                question = self.question_queries.get(uid)
                if question and question.get("revisao", {}).get("status") == "pendente":
                    selected.append(uid)
        if selected:
            use_selected = messagebox.askyesnocancel(
                APP_NAME,
                f"Há {len(selected)} questão(ões) pendente(s) selecionada(s).\n\n"
                "Sim: pesquisar somente as selecionadas.\n"
                "Não: escolher uma quantidade entre todas as pendentes.",
            )
            if use_selected is None:
                return
            if use_selected:
                self._start_web_enrichment(selected, description="selecionadas")
                return
        pending_rows = self.question_queries.list(status="pendente", limit=100000)
        if not pending_rows:
            messagebox.showinfo(APP_NAME, "Não há questões pendentes para pesquisar.")
            return
        default_limit = min(len(pending_rows), max(1, int(self.config_data.get("web_enrichment_max_per_run", 10) or 10)))
        limit = simpledialog.askinteger(
            APP_NAME,
            f"Quantas questões pendentes deseja pesquisar?\nDisponíveis: {len(pending_rows)}",
            initialvalue=default_limit,
            minvalue=1,
            maxvalue=min(100, len(pending_rows)),
            parent=self,
        )
        if limit is None:
            return
        self._start_web_enrichment([row["uid"] for row in pending_rows[:limit]], description="pendentes")

    def _web_enrichment_batch_worker(self, uids: list[str]) -> None:
        try:
            items: list[dict] = []
            total = max(1, len(uids))
            for index, uid in enumerate(uids):
                question = self.question_queries.get(uid)
                if not question:
                    continue
                code = str(question.get("codigo_origem", ""))
                self.event_queue.put((
                    "web_enrichment_progress",
                    f"{index * 100 / total:.0f}% • Pesquisando {code} ({index + 1}/{len(uids)})",
                ))
                try:
                    enrichment = enrich_question(question, max_results=12)
                    enrichment["question_uid"] = uid
                    enrichment["question_code"] = code
                    proposed = apply_safe_suggestions(question, enrichment)
                    proposed = deep_repair_question(
                        proposed,
                        self.taxonomy,
                        allow_auto_approve=True,
                        method="pesquisa_google_modo_ia_previa",
                    )
                    proposed["database_uid"] = uid
                    proposed["id"] = question.get("id", proposed.get("id"))
                    proposed["codigo_origem"] = question.get("codigo_origem", proposed.get("codigo_origem"))
                    proposed["fingerprint"] = question.get("fingerprint", proposed.get("fingerprint"))
                    enrichment["proposed_question"] = proposed
                    items.append({
                        "uid": uid,
                        "code": code,
                        "results": len(enrichment.get("results", [])),
                        "confidence": float(enrichment.get("confidence", 0) or 0),
                        "verified": bool(enrichment.get("verified_match")),
                        "answer": str(enrichment.get("structured_question", {}).get("gabarito", "")),
                        "applied_fields": list(enrichment.get("applied_fields", [])),
                        "enrichment": enrichment,
                        "error": "",
                    })
                except Exception as error:
                    items.append({
                        "uid": uid,
                        "code": code,
                        "results": 0,
                        "confidence": 0.0,
                        "enrichment": {"results": [], "errors": [str(error)]},
                        "error": str(error),
                    })
                self.event_queue.put((
                    "web_enrichment_progress",
                    f"{(index + 1) * 100 / total:.0f}% • Pesquisa concluída para {code}",
                ))
            self.event_queue.put(("web_enrichment_batch_done", items))
        except Exception as error:
            self.event_queue.put(("web_enrichment_error", str(error), traceback.format_exc()))

    def _finish_web_enrichment(self) -> None:
        self.web_enrichment_worker = None
        for button_name in ("web_enrichment_button", "web_batch_button"):
            button = getattr(self, button_name, None)
            if button is not None:
                button.configure(state="normal")

    def _show_web_results(self, enrichment: dict) -> None:
        results = enrichment.get("results", []) if isinstance(enrichment, dict) else []
        queries = enrichment.get("queries", []) if isinstance(enrichment, dict) else []
        errors = enrichment.get("errors", []) if isinstance(enrichment, dict) else []
        candidates = enrichment.get("candidates", []) if isinstance(enrichment, dict) else []
        candidate_by_url: dict[str, dict] = {}
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            url = str(candidate.get("url", "")).strip()
            if not url:
                continue
            current = candidate_by_url.get(url)
            if current is None or float(candidate.get("score", 0) or 0) > float(current.get("score", 0) or 0):
                candidate_by_url[url] = candidate
        row_sources: list[dict] = []
        top = tk.Toplevel(self)
        top.title("Pesquisa no Modo IA do Google")
        top.geometry("1040x690")
        top.configure(bg=COLORS["surface"])
        tk.Label(
            top,
            text="Resposta encontrada no Modo IA",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 16),
        ).pack(anchor="w", padx=18, pady=(16, 4))
        stage_used = str(enrichment.get("search_stage_used", "")).strip()
        stage_label = "código isolado" if stage_used == "codigo" else "enunciado isolado" if stage_used == "enunciado" else "sem confirmação"
        attempted_links = enrichment.get("attempted_links", []) if isinstance(enrichment, dict) else []
        opened_count = sum(1 for item in attempted_links if item.get("opened"))
        google_page_read = bool(enrichment.get("google_search_page_read"))
        google_expanded = bool(enrichment.get("google_answer_expanded"))
        expand_clicks = int(enrichment.get("google_expand_clicks", 0) or 0)
        captcha_detected = bool(enrichment.get("captcha_detected"))
        captcha_resolved = bool(enrichment.get("captcha_resolved"))
        captcha_waited = int(float(enrichment.get("captcha_waited_seconds", 0) or 0))
        ai_mode = bool(enrichment.get("ai_mode_activated"))
        ai_stable = bool(enrichment.get("ai_answer_stable"))
        browser_reused = bool(enrichment.get("browser_reused"))
        google_load_seconds = float(enrichment.get("google_load_seconds", 0) or 0)
        capture_method = str(enrichment.get("capture_method", "")).strip()
        captured_chars = int(enrichment.get("captured_chars", 0) or 0)
        summary = (
            f"{len(results)} resposta(s). O navegador abriu somente o Modo IA do Google: "
            f"{'SIM' if ai_mode else 'NÃO'}. A página renderizada foi lida pelo programa: "
            f"{'SIM' if google_page_read else 'NÃO'}. A resposta ficou estável: "
            f"{'SIM' if ai_stable else 'NÃO'}. Sessão do navegador reutilizada: "
            f"{'SIM' if browser_reused else 'NÃO'}. Tempo total: {google_load_seconds:.1f}s. "
            f"Captura: {capture_method or 'padrão'} ({captured_chars} caracteres). "
            "O controle Mostrar mais foi acionado: "
            f"{'SIM' if google_expanded else 'NÃO'}"
            + (f" ({expand_clicks} clique(s)). " if google_expanded else ". ")
            + f"Foram usadas {len(queries)} consulta(s) em sequência. Nenhum link de resultado foi aberto. "
            f"Etapa confirmada: {stage_label}. A correspondência exige banca e ano compatíveis, "
            "além do código exato ou do enunciado. A base ainda não foi alterada."
        )
        if captcha_detected:
            summary += (
                f" Verificação do Google detectada e {'concluída' if captcha_resolved else 'não concluída'}; "
                f"o navegador permaneceu aberto por {captcha_waited} segundo(s)."
            )
        if not results:
            summary += " Nenhum resultado foi localizado; você pode abrir a consulta no navegador pelo botão abaixo."
        tk.Label(
            top,
            text=summary,
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            wraplength=980,
            justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 10))
        structured = enrichment.get("structured_question", {}) if isinstance(enrichment, dict) else {}
        applied_fields = enrichment.get("applied_fields", []) if isinstance(enrichment, dict) else []
        verification_parts = [
            f"Correspondência confirmada: {'SIM' if enrichment.get('verified_match') else 'NÃO'}",
            f"Código exato: {'SIM' if enrichment.get('exact_code_match') else 'NÃO'}",
            f"Banca confirmada: {'SIM' if enrichment.get('board_confirmed') else 'NÃO'}",
            f"Ano confirmado: {'SIM' if enrichment.get('year_confirmed') else 'NÃO'}",
            f"Página do Google lida: {'SIM' if enrichment.get('google_search_page_read') else 'NÃO'}",
            f"Modo IA confirmado: {'SIM' if enrichment.get('ai_mode_activated') else 'NÃO'}",
            f"Resposta estabilizada: {'SIM' if enrichment.get('ai_answer_stable') else 'NÃO'}",
            f"Sessão reutilizada: {'SIM' if enrichment.get('browser_reused') else 'NÃO'}",
            f"Tempo Google: {float(enrichment.get('google_load_seconds', 0) or 0):.1f}s",
            f"Método de captura: {str(enrichment.get('capture_method', '') or 'padrão')}",
            f"Texto capturado: {int(enrichment.get('captured_chars', 0) or 0)} caracteres",
            f"Mostrar mais expandido: {'SIM' if enrichment.get('google_answer_expanded') else 'NÃO'}",
            f"Verificação do Google resolvida: {'SIM' if enrichment.get('captcha_resolved') else 'NÃO' if enrichment.get('captcha_detected') else 'NÃO NECESSÁRIA'}",
            f"Gabarito lido no site: {'SIM' if enrichment.get('answer_confirmed') else 'NÃO'}",
            f"Justificativa lida no site: {'SIM' if enrichment.get('justification_confirmed') else 'NÃO'}",
        ]
        if structured.get("gabarito"):
            verification_parts.append(f"Gabarito localizado: {structured.get('gabarito')}")
            answer_stage = str(enrichment.get("answer_search_stage", "")).strip()
            if answer_stage:
                verification_parts.append(
                    "Gabarito encontrado pela busca do " + ("código" if answer_stage == "codigo" else "enunciado")
                )
        if structured.get("explicacao"):
            verification_parts.append("Justificativa localizada")
        if applied_fields:
            verification_parts.append("Campos transcritos: " + ", ".join(str(item) for item in applied_fields))
        tk.Label(
            top,
            text=" • ".join(verification_parts),
            bg="#EAF7F0" if enrichment.get("verified_match") else "#FFF8E8",
            fg=COLORS["green"] if enrichment.get("verified_match") else COLORS["yellow"],
            wraplength=980,
            justify="left",
            padx=8,
            pady=7,
        ).pack(fill="x", padx=18, pady=(0, 8))
        if errors:
            tk.Label(
                top,
                text="Avisos: " + " | ".join(str(item) for item in errors[:3]),
                bg="#FFF8E8",
                fg=COLORS["yellow"],
                wraplength=980,
                justify="left",
                padx=8,
                pady=6,
            ).pack(fill="x", padx=18, pady=(0, 8))
        tree = ttk.Treeview(top, columns=("score", "provider", "title", "url"), show="headings")
        for key, title, width in [
            ("score", "Conf.", 65),
            ("provider", "Busca", 120),
            ("title", "Título", 360),
            ("url", "Endereço", 430),
        ]:
            tree.heading(key, text=title)
            tree.column(key, width=width, anchor="center" if key == "score" else "w")
        for index, item in enumerate(results):
            url = str(item.get("url", "")).strip()
            row_sources.append({"result": item, "candidate": candidate_by_url.get(url)})
            tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    f"{float(item.get('score', 0))*100:.0f}%",
                    item.get("provider", ""),
                    item.get("title", ""),
                    url,
                ),
            )
        tree.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        if results:
            tree.selection_set("0")
            tree.focus("0")

        manual_status = tk.Label(
            top,
            text="Selecione a resposta do Modo IA e clique em Preparar prévia e atualizar. Nenhum dado será salvo antes do seu OK.",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            anchor="w",
            justify="left",
            wraplength=980,
        )
        manual_status.pack(fill="x", padx=18, pady=(0, 8))

        def open_selected(_event=None):
            # A busca é realizada exclusivamente no Modo IA. Este botão apenas
            # reabre a consulta do Google, sem navegar para links externos.
            if queries:
                webbrowser.open("https://www.google.com/ai")

        manual_queue: queue.Queue = queue.Queue()

        def finish_manual_update(payload: dict) -> None:
            extract_button.configure(state="normal")
            if payload.get("error"):
                manual_status.configure(text="Falha: " + str(payload["error"]), fg=COLORS["red"])
                messagebox.showerror(APP_NAME, str(payload["error"]), parent=top)
                return
            uid = str(payload.get("uid", ""))
            fields = list(payload.get("fields", []))
            proposed = payload.get("proposed")
            if not isinstance(proposed, dict):
                messagebox.showerror(APP_NAME, "A prévia da questão não foi gerada.", parent=top)
                return
            manual_status.configure(
                text="Prévia preparada. Confira o conteúdo do Telegram e clique em OK para atualizar a base.",
                fg=COLORS["green"],
            )

            def commit_update() -> None:
                self.question_commands.update(uid, proposed)
                self.study.sync_questions()
                self.refresh_all()
                if uid and self.question_tree.exists(uid):
                    self.question_tree.selection_set(uid)
                    self.question_tree.see(uid)
                    self.current_question_uid = uid
                    self.on_question_select()
                manual_status.configure(
                    text="Base atualizada. Campos transcritos: " + (", ".join(fields) if fields else "dados confirmados"),
                    fg=COLORS["green"],
                )
                messagebox.showinfo(
                    APP_NAME,
                    "A questão foi atualizada após a sua confirmação.\n\n"
                    + ("Campos preenchidos: " + ", ".join(fields) if fields else "Os dados confirmados foram mantidos."),
                    parent=top,
                )

            def cancel_update() -> None:
                manual_status.configure(
                    text="Atualização cancelada. A base permaneceu sem alterações; você pode fazer outra busca.",
                    fg=COLORS["yellow"],
                )

            self.open_telegram_preview(
                proposed,
                on_confirm=commit_update,
                on_cancel=cancel_update,
                preview_title="Prévia Telegram — confirmar atualização da base",
            )

        def poll_manual_queue() -> None:
            try:
                payload = manual_queue.get_nowait()
            except queue.Empty:
                if top.winfo_exists():
                    top.after(120, poll_manual_queue)
                return
            finish_manual_update(payload)

        def extract_selected_and_update() -> None:
            selection = tree.selection()
            if not selection:
                messagebox.showinfo(APP_NAME, "Selecione uma linha da tabela.", parent=top)
                return
            index = int(selection[0])
            if index < 0 or index >= len(row_sources):
                return
            source = row_sources[index]
            result_item = source.get("result", {})
            candidate = source.get("candidate")
            url = str(result_item.get("url", "")).strip()
            uid = str(enrichment.get("question_uid", "") or self.current_question_uid or "")
            question = self.question_queries.get(uid) if uid else None
            if not question:
                messagebox.showerror(APP_NAME, "Não foi possível localizar a questão correspondente no banco.", parent=top)
                return
            extract_button.configure(state="disabled")
            manual_status.configure(text="Preparando a prévia com os dados confirmados do Modo IA...", fg=COLORS["muted"])

            def worker() -> None:
                try:
                    if not isinstance(candidate, dict) or not candidate.get("page_opened"):
                        raise WebEnrichmentError(
                            "A resposta do Modo IA não foi capturada. Faça uma nova pesquisa e aguarde a página terminar de carregar."
                        )
                    selected_enrichment = enrichment_from_candidate(
                        candidate,
                        query=url,
                        question_uid=uid,
                    )
                    if not selected_enrichment.get("verified_match"):
                        raise WebEnrichmentError(
                            "O Modo IA não confirmou simultaneamente a questão, a banca e o ano. Nenhum dado foi alterado."
                        )
                    proposed = apply_safe_suggestions(question, selected_enrichment)
                    proposed = deep_repair_question(
                        proposed,
                        self.taxonomy,
                        allow_auto_approve=True,
                        method="google_modo_ia_confirmado",
                    )
                    proposed["database_uid"] = uid
                    proposed["id"] = question.get("id", proposed.get("id"))
                    proposed["codigo_origem"] = question.get("codigo_origem", proposed.get("codigo_origem"))
                    proposed["fingerprint"] = question.get("fingerprint", proposed.get("fingerprint"))
                    manual_queue.put({
                        "uid": uid,
                        "fields": list(selected_enrichment.get("applied_fields", [])),
                        "proposed": proposed,
                    })
                except Exception as error:
                    manual_queue.put({"error": str(error)})

            threading.Thread(target=worker, daemon=True, name="questflow-selected-web-source").start()
            top.after(120, poll_manual_queue)

        tree.bind("<Double-1>", open_selected)
        actions = tk.Frame(top, bg=COLORS["surface"])
        actions.pack(fill="x", padx=18, pady=(0, 16))
        extract_button = ttk.Button(
            actions,
            text="Preparar prévia e atualizar base",
            style="Primary.TButton",
            command=extract_selected_and_update,
        )
        extract_button.pack(side="left")
        ttk.Button(actions, text="Nova consulta no Modo IA", command=open_selected).pack(side="left", padx=8)
        ttk.Button(
            actions,
            text="Fechar sessão Google",
            command=lambda: (close_google_browser_session(), manual_status.configure(text="Sessão do Google encerrada. A próxima pesquisa abrirá uma nova janela.", fg=COLORS["muted"])),
        ).pack(side="left")
        ttk.Button(actions, text="Fechar", command=top.destroy).pack(side="right")

    def _show_web_batch_results(self, items: list[dict]) -> None:
        if len(items) == 1:
            self._show_web_results(items[0].get("enrichment", {}))
            return
        top = tk.Toplevel(self)
        top.title("Pesquisa web das questões pendentes")
        top.geometry("900x620")
        top.configure(bg=COLORS["surface"])
        tk.Label(
            top,
            text=f"Pesquisa concluída para {len(items)} questão(ões)",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 16),
        ).pack(anchor="w", padx=18, pady=(16, 10))
        tree = ttk.Treeview(top, columns=("code", "results", "confidence", "status"), show="headings")
        for key, title, width in [
            ("code", "Código", 160),
            ("results", "Resultados", 100),
            ("confidence", "Confiança", 100),
            ("status", "Situação", 470),
        ]:
            tree.heading(key, text=title)
            tree.column(key, width=width, anchor="center" if key in {"results", "confidence"} else "w")
        for index, item in enumerate(items):
            if item.get("error"):
                status = item.get("error")
            elif item.get("verified"):
                fields = ", ".join(item.get("applied_fields", [])) or "nenhum campo novo"
                answer = f" • gabarito {item.get('answer')}" if item.get("answer") else ""
                status = f"Questão confirmada • {fields}{answer}"
            else:
                status = "Resultados sem confirmação suficiente" if item.get("results") else "Nenhum resultado"
            tree.insert(
                "", "end", iid=str(index),
                values=(item.get("code", ""), item.get("results", 0), f"{float(item.get('confidence', 0))*100:.0f}%", status),
            )
        tree.pack(fill="both", expand=True, padx=18, pady=(0, 12))

        def show_selected(_event=None):
            selection = tree.selection()
            if selection:
                self._show_web_results(items[int(selection[0])].get("enrichment", {}))

        tree.bind("<Double-1>", show_selected)
        actions = tk.Frame(top, bg=COLORS["surface"])
        actions.pack(fill="x", padx=18, pady=(0, 16))
        ttk.Button(actions, text="Ver resultados da selecionada", command=show_selected).pack(side="left")
        ttk.Button(actions, text="Fechar", command=top.destroy).pack(side="right")

