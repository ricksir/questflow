from __future__ import annotations

from .common import *  # noqa: F401,F403


class QuestionEditorMixin:
    def new_manual_question(self) -> None:
        try:
            uid = self.question_commands.create_manual(self.taxonomy)
            self.study.sync_questions()
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Não foi possível criar a questão manual:\n{error}")
            return
        self.current_question_uid = uid
        self.refresh_all()
        if self.question_tree.exists(uid):
            self.question_tree.selection_set(uid)
            self.question_tree.see(uid)
        self.on_question_select()
        self.statement_text.focus_set()

    def on_question_select(self, _event=None) -> None:
        selection = self.question_tree.selection()
        if not selection:
            return
        uid = selection[0]
        question = self.question_queries.get(uid)
        if not question:
            return
        self.current_question_uid = uid
        self.editor_vars["codigo_origem"].set(question.get("codigo_origem", question.get("id", "")))
        self.editor_vars["materia"].set(question.get("materia", ""))
        self.editor_vars["aula_planilha"].set(question.get("aula_planilha", ""))
        self.editor_vars["assunto"].set(question.get("assunto", ""))
        self.editor_vars["assuntos"].set(" | ".join(question.get("assuntos", [])))
        self.editor_vars["banca"].set(question.get("banca", ""))
        self.editor_vars["ano"].set("" if question.get("ano") is None else str(question.get("ano")))
        self.editor_vars["orgao"].set(question.get("orgao", ""))
        self.editor_vars["prova"].set(question.get("prova", ""))
        self.editor_vars["cargo"].set(question.get("cargo", ""))
        self.editor_vars["area"].set(question.get("area", ""))
        self.editor_vars["especialidade"].set(question.get("especialidade", ""))
        self.editor_vars["turno"].set(question.get("turno", ""))
        self.editor_vars["tipo"].set(question.get("tipo", "multipla_escolha"))
        self.editor_vars["gabarito"].set(question.get("gabarito", ""))
        self._set_text(self.statement_text, question.get("enunciado", ""))
        alternatives = "\n".join(
            f"{item.get('chave','')}|{item.get('texto','')}"
            for item in question.get("alternativas", [])
        )
        self._set_text(self.alternatives_text, alternatives)
        self._set_text(self.explanation_text, question.get("explicacao", ""))
        review = question.get("revisao", {})
        classification = question.get("classificacao_planilha", {})
        alerts = review.get("alertas", [])
        text = (
            f"Revisão: {review.get('status', 'pendente')} • "
            f"Confiança OCR: {float(review.get('confianca', 0))*100:.0f}%\n"
            f"Planilha: {classification.get('status', 'sem classificação')} • "
            f"Confiança: {float(classification.get('confianca', 0))*100:.0f}% • "
            f"Método: {classification.get('metodo', 'manual')}"
        )
        if classification.get("referencia"):
            text += "\nReferência da trilha: " + str(classification.get("referencia"))
        if alerts:
            text += "\nVerifique: " + "; ".join(alerts)
        code_history = question.get("historico_codigos", [])
        if isinstance(code_history, list) and code_history:
            last = code_history[0] if "old_code" in code_history[0] else code_history[-1]
            old = last.get("old_code", last.get("codigo_anterior", ""))
            new_code = last.get("new_code", last.get("codigo_novo", ""))
            changed_at = last.get("changed_at", last.get("alterado_em", ""))
            text += f"\nCódigo alterado: {old} → {new_code} • {changed_at}"
        self.review_alerts.configure(text=text)
        self._render_question_image(question)
        self.update_telegram_selection()

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    def _render_question_image(self, question: dict) -> None:
        image_info = question.get("imagem_questao", {}) if isinstance(question.get("imagem_questao"), dict) else {}
        image_path = str(image_info.get("path", "")).strip()
        if not image_path or not Path(image_path).exists():
            self.question_image_label.configure(image="", text="Sem imagem")
            self.question_image_label.image = None
            self.question_image_info.configure(
                text="O recorte automático aparecerá aqui. Se não ficar correto, anexe manualmente."
            )
            return
        details = []
        origem = str(image_info.get("origem", "")).strip()
        if origem == "extraida_automaticamente":
            details.append("Recorte automático")
        elif origem == "manual":
            details.append("Imagem anexada manualmente")
        pagina = image_info.get("pagina")
        if pagina:
            details.append(f"página {pagina}")
        precisa = image_info.get("precisa_revisao")
        if precisa:
            details.append("confira o enquadramento")
        info_text = " • ".join(details) if details else "Imagem associada à questão"
        self.question_image_info.configure(text=f"{info_text}\n{image_path}")
        try:
            image = Image.open(image_path)
            image.thumbnail((900, 420))
            photo = ImageTk.PhotoImage(image)
            self.question_image_label.configure(image=photo, text="")
            self.question_image_label.image = photo
        except Exception as error:
            self.question_image_label.configure(image="", text="Não foi possível abrir a imagem")
            self.question_image_label.image = None
            self.question_image_info.configure(text=f"Imagem associada, mas houve erro ao abrir: {error}")

    def _current_question(self) -> dict | None:
        if not self.current_question_uid:
            return None
        return self.question_queries.get(self.current_question_uid)

    def _question_image_path(self, question: dict | None) -> str:
        if not question:
            return ""
        image_info = question.get("imagem_questao", {}) if isinstance(question.get("imagem_questao"), dict) else {}
        path = str(image_info.get("path", "")).strip()
        return path if path and Path(path).exists() else ""

    def open_image_preview(self) -> None:
        question = self._current_question()
        if not question:
            messagebox.showinfo(APP_NAME, "Selecione uma questão primeiro.")
            return
        image_path = self._question_image_path(question)
        if not image_path:
            messagebox.showinfo(APP_NAME, "Esta questão ainda não possui imagem associada.")
            return
        top = tk.Toplevel(self)
        top.title("Imagem da questão")
        top.geometry("1100x760")
        top.configure(bg="#FFFFFF")
        header = tk.Label(
            top,
            text=f"{question.get('codigo_origem', '')} • {question.get('materia', '')}",
            bg="#FFFFFF",
            fg=COLORS["navy"],
            font=("Segoe UI Semibold", 12),
        )
        header.pack(anchor="w", padx=16, pady=(14, 6))
        info = tk.Label(
            top,
            text=image_path,
            bg="#FFFFFF",
            fg=COLORS["muted"],
            anchor="w",
            justify="left",
            wraplength=1040,
        )
        info.pack(fill="x", padx=16, pady=(0, 8))
        image_label = tk.Label(top, bg="#F8FAFC", relief="solid", bd=1)
        image_label.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        try:
            image = Image.open(image_path)
            image.thumbnail((1040, 620))
            photo = ImageTk.PhotoImage(image)
            image_label.configure(image=photo)
            image_label.image = photo
        except Exception as error:
            image_label.configure(text=f"Não foi possível abrir a imagem:\n{error}", fg=COLORS["red"])

    def _make_scroll_text_window(self, title: str, body: str, *, width: int = 1100, height: int = 760) -> tk.Toplevel:
        top = tk.Toplevel(self)
        top.title(title)
        top.geometry(f"{width}x{height}")
        top.configure(bg="#FFFFFF")
        container = tk.Frame(top, bg="#FFFFFF")
        container.pack(fill="both", expand=True, padx=12, pady=12)
        text_widget = tk.Text(container, wrap="word", font=("Segoe UI", 10), relief="solid", bd=1)
        scroll = ttk.Scrollbar(container, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scroll.set)
        text_widget.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        text_widget.insert("1.0", body)
        text_widget.configure(state="disabled")
        return top

    def open_full_question_preview(self) -> None:
        question = self._current_question()
        if not question:
            messagebox.showinfo(APP_NAME, "Selecione uma questão primeiro.")
            return
        lines: list[str] = []
        lines.append(f"Código: {question.get('codigo_origem', '')}")
        lines.append(f"Matéria: {question.get('materia', '')}")
        lines.append(f"Aula: {question.get('aula_planilha', '')}")
        lines.append(f"Assunto: {question.get('assunto', '')}")
        lines.append(f"Banca: {question.get('banca', '')}    Ano: {question.get('ano', '')}    Órgão: {question.get('orgao', '')}")
        lines.append(f"Prova: {question.get('prova', '')}")
        lines.append(f"Tipo: {question.get('tipo', '')}    Gabarito: {question.get('gabarito', '')}")
        image_path = self._question_image_path(question)
        if image_path:
            lines.append(f"Imagem associada: {image_path}")
        lines.append("\nENUNCIADO\n")
        lines.append(str(question.get('enunciado', '')).strip())
        lines.append("\nALTERNATIVAS\n")
        for item in question.get('alternativas', []):
            lines.append(f"{item.get('chave', '')}) {item.get('texto', '')}")
        explanation = str(question.get('explicacao', '')).strip()
        if explanation:
            lines.append("\nEXPLICAÇÃO\n")
            lines.append(explanation)
        body = "\n".join(lines)
        top = self._make_scroll_text_window("Questão completa", body)
        if image_path:
            preview = tk.Toplevel(top)
            preview.title("Imagem da questão")
            preview.geometry("1000x420")
            preview.configure(bg="#FFFFFF")
            label = tk.Label(preview, bg="#F8FAFC", relief="solid", bd=1)
            label.pack(fill="both", expand=True, padx=12, pady=12)
            try:
                image = Image.open(image_path)
                image.thumbnail((960, 360))
                photo = ImageTk.PhotoImage(image)
                label.configure(image=photo)
                label.image = photo
            except Exception:
                label.configure(text="Não foi possível abrir a imagem associada.", fg=COLORS["red"])

    def open_telegram_preview(
        self,
        question_override: dict | None = None,
        *,
        on_confirm=None,
        on_cancel=None,
        preview_title: str = "Prévia Telegram — QuestFlow",
    ) -> None:
        question = question_override or self._current_question()
        if not question:
            messagebox.showinfo(APP_NAME, "Selecione uma questão primeiro.")
            return
        try:
            payload = telegram_payload(
                question,
                str(self.config_data.get("telegram_chat_id", "preview") or "preview"),
            )
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Não foi possível montar a prévia do Telegram:\n{error}")
            return

        image_path = self._question_image_path(question)
        direct_poll = bool(payload.get("_direct_poll", False))
        context_text = str(payload.get("_context", "")).strip()
        explanation = str(question.get("explicacao", "")).strip()
        try:
            import json as _json
            options = [
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in _json.loads(payload.get("options", "[]"))
            ]
            correct_ids = _json.loads(payload.get("correct_option_ids", "[]"))
        except Exception:
            options = []
            correct_ids = []

        top = tk.Toplevel(self)
        top.title(preview_title)
        top.geometry("980x860")
        top.minsize(760, 620)
        top.configure(bg="#DCE5EC")
        top._telegram_preview_images = []

        header = tk.Frame(top, bg="#2879A7", height=72)
        header.pack(fill="x")
        header.pack_propagate(False)
        avatar = tk.Label(
            header,
            text="Q",
            bg=COLORS["orange"],
            fg="#FFFFFF",
            font=("Segoe UI Semibold", 18),
            width=2,
            height=1,
        )
        avatar.pack(side="left", padx=(18, 10), pady=12)
        name_box = tk.Frame(header, bg="#2879A7")
        name_box.pack(side="left", fill="y", pady=10)
        tk.Label(
            name_box,
            text="QuestFlow Bot",
            bg="#2879A7",
            fg="#FFFFFF",
            font=("Segoe UI Semibold", 13),
        ).pack(anchor="w")
        tk.Label(
            name_box,
            text="prévia local — confirme antes de alterar a base" if on_confirm else "prévia local — nada será enviado",
            bg="#2879A7",
            fg="#D7ECF8",
            font=("Segoe UI", 9),
        ).pack(anchor="w")
        if on_confirm is None:
            ttk.Button(header, text="Enviar agora", command=self.send_selected_to_telegram).pack(
                side="right", padx=18, pady=18
            )

        canvas_container = tk.Frame(top, bg="#DCE5EC")
        canvas_container.pack(fill="both", expand=True)
        canvas = tk.Canvas(canvas_container, bg="#DCE5EC", highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_container, orient="vertical", command=canvas.yview)
        chat = tk.Frame(canvas, bg="#DCE5EC")
        chat_window = canvas.create_window((0, 0), window=chat, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        chat.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(chat_window, width=e.width))

        info_bar = tk.Frame(chat, bg="#B9D8E8")
        info_bar.pack(pady=(12, 8))
        summary = (
            f"Imagem: {'sim' if image_path else 'não'}  •  "
            f"Enquete direta: {'sim' if direct_poll else 'não'}  •  "
            f"{len(options)} opções  •  explicação em mensagem separada"
        )
        tk.Label(
            info_bar,
            text=summary,
            bg="#B9D8E8",
            fg="#355B70",
            font=("Segoe UI", 8),
            padx=12,
            pady=4,
        ).pack()

        def bubble(parent: tk.Widget, *, width: int = 700) -> tk.Frame:
            outer = tk.Frame(parent, bg="#DCE5EC")
            outer.pack(fill="x", padx=24, pady=5)
            frame = tk.Frame(
                outer,
                bg="#FFFFFF",
                highlightbackground="#C7D2DA",
                highlightthickness=1,
                padx=14,
                pady=10,
            )
            frame.pack(anchor="w")
            frame.configure(width=width)
            return frame

        if image_path:
            image_bubble = bubble(chat)
            try:
                image = Image.open(image_path)
                image.thumbnail((660, 390))
                photo = ImageTk.PhotoImage(image)
                top._telegram_preview_images.append(photo)
                tk.Label(image_bubble, image=photo, bg="#FFFFFF").pack(anchor="w")
                tk.Label(
                    image_bubble,
                    text="Imagem da questão",
                    bg="#FFFFFF",
                    fg="#6B7F8D",
                    font=("Segoe UI", 8),
                ).pack(anchor="w", pady=(6, 0))
            except Exception as error:
                tk.Label(
                    image_bubble,
                    text=f"Não foi possível abrir a imagem:\n{error}",
                    bg="#FFFFFF",
                    fg=COLORS["red"],
                    justify="left",
                ).pack(anchor="w")

        if context_text:
            context_bubble = bubble(chat)
            tk.Label(
                context_bubble,
                text=context_text,
                bg="#FFFFFF",
                fg="#1F2937",
                font=("Segoe UI", 10),
                justify="left",
                anchor="w",
                wraplength=650,
            ).pack(anchor="w")
            tk.Label(
                context_bubble,
                text="agora",
                bg="#FFFFFF",
                fg="#8797A4",
                font=("Segoe UI", 7),
            ).pack(anchor="e", pady=(5, 0))

        poll_bubble = bubble(chat)
        tk.Label(
            poll_bubble,
            text="QUIZ",
            bg="#FFFFFF",
            fg="#2879A7",
            font=("Segoe UI Semibold", 8),
        ).pack(anchor="w")
        tk.Label(
            poll_bubble,
            text=str(payload.get("question", "")),
            bg="#FFFFFF",
            fg="#172033",
            font=("Segoe UI Semibold", 11),
            justify="left",
            anchor="w",
            wraplength=650,
        ).pack(anchor="w", pady=(4, 10))

        option_buttons: list[tk.Button] = []
        result_label = tk.Label(
            poll_bubble,
            text="",
            bg="#FFFFFF",
            fg="#172033",
            font=("Segoe UI Semibold", 9),
            justify="left",
            anchor="w",
            wraplength=650,
        )
        explanation_label = tk.Label(
            poll_bubble,
            text="",
            bg="#FFFFFF",
            fg="#4B5563",
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
            wraplength=650,
        )

        def choose_option(selected_index: int) -> None:
            correct_index = correct_ids[0] if correct_ids else -1
            for index, button in enumerate(option_buttons):
                button.configure(state="disabled", cursor="arrow")
                if index == correct_index:
                    button.configure(bg="#DDF5E8", fg="#116A42", activebackground="#DDF5E8")
                elif index == selected_index:
                    button.configure(bg="#FBE2E2", fg="#A72E2E", activebackground="#FBE2E2")
            if selected_index == correct_index:
                result_label.configure(text="✓ Resposta correta", fg="#178A54")
            else:
                result_label.configure(text="✕ Resposta incorreta — a alternativa correta foi destacada", fg="#C03A3A")
            result_label.pack(fill="x", pady=(10, 0))
            if explanation:
                explanation_label.configure(
                    text="📘 A explicação completa será enviada abaixo do quiz, em uma mensagem separada e legível:\n\n" + explanation
                )
                explanation_label.pack(fill="x", pady=(8, 0))

        for index, option in enumerate(options):
            option_row = tk.Frame(poll_bubble, bg="#FFFFFF")
            option_row.pack(fill="x", pady=3)
            button = tk.Button(
                option_row,
                text=f"○  {option}",
                command=lambda i=index: choose_option(i),
                bg="#F7FAFC",
                fg="#243647",
                activebackground="#EAF3F8",
                activeforeground="#172033",
                relief="solid",
                bd=1,
                anchor="w",
                justify="left",
                wraplength=610,
                padx=10,
                pady=7,
                cursor="hand2",
                font=("Segoe UI", 9),
            )
            button.pack(fill="x")
            option_buttons.append(button)

        tk.Label(
            poll_bubble,
            text="Toque em uma alternativa para simular a resposta.",
            bg="#FFFFFF",
            fg="#8797A4",
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(9, 0))
        tk.Label(
            poll_bubble,
            text="agora",
            bg="#FFFFFF",
            fg="#8797A4",
            font=("Segoe UI", 7),
        ).pack(anchor="e", pady=(4, 0))

        footer = tk.Frame(top, bg="#FFFFFF", height=54)
        footer.pack(fill="x")
        footer.pack_propagate(False)
        tk.Label(
            footer,
            text="Esta é uma simulação visual aproximada do Telegram. O conteúdo e a ordem do envio são os mesmos.",
            bg="#FFFFFF",
            fg="#6B7280",
            font=("Segoe UI", 8),
        ).pack(side="left", padx=18)
        def cancel_preview() -> None:
            if on_cancel is not None:
                on_cancel()
            top.destroy()

        def confirm_preview() -> None:
            if on_confirm is not None:
                try:
                    on_confirm()
                except Exception as error:
                    messagebox.showerror(APP_NAME, f"Não foi possível atualizar a base:\n{error}", parent=top)
                    return
            top.destroy()

        if on_confirm is not None:
            ttk.Button(footer, text="Cancelar", command=cancel_preview).pack(side="right", padx=(8, 18), pady=10)
            ttk.Button(
                footer,
                text="OK — atualizar base",
                style="Success.TButton",
                command=confirm_preview,
            ).pack(side="right", pady=10)
            top.protocol("WM_DELETE_WINDOW", cancel_preview)
        else:
            ttk.Button(footer, text="Fechar", command=top.destroy).pack(side="right", padx=18, pady=10)

        top.after(100, lambda: canvas.yview_moveto(0.0))

    def attach_manual_image(self) -> None:
        uid = self.current_question_uid
        if not uid:
            messagebox.showinfo(APP_NAME, "Selecione uma questão primeiro.")
            return
        question = self.question_queries.get(uid)
        if not question:
            return
        source = filedialog.askopenfilename(
            title="Selecionar imagem da questão",
            filetypes=[("Imagens", "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff"), ("Todos os arquivos", "*.*")],
        )
        if not source:
            return
        target = QUESTION_IMAGE_DIR / f"manual_{uid}{Path(source).suffix.lower() or '.png'}"
        shutil.copy2(source, target)
        question["imagem_questao"] = {
            "path": str(target),
            "origem": "manual",
            "recorte_automatico": False,
            "precisa_revisao": False,
        }
        review = question.setdefault("revisao", {})
        alerts = [item for item in review.get("alertas", []) if "Imagem não recortada automaticamente" not in item]
        review["alertas"] = alerts
        self.question_commands.update(uid, question)
        self.on_question_select()
        self.refresh_all()

    def remove_current_image(self) -> None:
        uid = self.current_question_uid
        if not uid:
            messagebox.showinfo(APP_NAME, "Selecione uma questão primeiro.")
            return
        question = self.question_queries.get(uid)
        if not question:
            return
        if not messagebox.askyesno(APP_NAME, "Remover a imagem associada a esta questão?"):
            return
        image_info = question.pop("imagem_questao", None)
        path = str(image_info.get("path", "")).strip() if isinstance(image_info, dict) else ""
        if path:
            try:
                image_path = Path(path)
                if image_path.exists() and image_path.is_file() and QUESTION_IMAGE_DIR in image_path.parents:
                    image_path.unlink()
            except Exception:
                pass
        review = question.setdefault("revisao", {})
        alerts = list(review.get("alertas", []))
        if re.search(r"\b(?:imagem|figura|gráfico|grafico|diagrama)\b", str(question.get("enunciado", "")), re.I):
            note = "Questão com imagem sem anexo: adicione manualmente se necessário"
            if note not in alerts:
                alerts.append(note)
                review["status"] = "pendente"
        review["alertas"] = alerts
        self.question_commands.update(uid, question)
        self.on_question_select()
        self.refresh_all()

    def save_current_question(self, approve: bool = False) -> None:
        uid = self.current_question_uid
        if not uid:
            messagebox.showinfo(APP_NAME, "Selecione uma questão.")
            return
        question = self.question_queries.get(uid)
        if not question:
            return
        old_code = str(question.get("codigo_origem", question.get("id", ""))).strip()
        new_code = self.editor_vars["codigo_origem"].get().strip()
        if not new_code:
            messagebox.showerror(APP_NAME, "O código da questão não pode ficar vazio.")
            return
        if len(new_code) > 240 or any(ord(char) < 32 for char in new_code):
            messagebox.showerror(APP_NAME, "O código da questão é inválido.")
            return
        if new_code != old_code:
            if not messagebox.askyesno(
                APP_NAME,
                (
                    f"Alterar o código de {old_code} para {new_code}?\n\n"
                    "O QuestFlow atualizará as referências no banco e registrará a troca no histórico."
                ),
            ):
                return
        try:
            year_text = self.editor_vars["ano"].get().strip()
            year = int(year_text) if year_text else None
        except ValueError:
            messagebox.showerror(APP_NAME, "O ano deve ser um número de quatro dígitos.")
            return
        alternatives: list[dict] = []
        for line in self.alternatives_text.get("1.0", "end").splitlines():
            if not line.strip():
                continue
            if "|" not in line:
                messagebox.showerror(APP_NAME, f"Alternativa inválida: {line}\nUse o formato A|texto.")
                return
            key, text = line.split("|", 1)
            alternatives.append({"chave": key.strip().upper(), "texto": text.strip()})
        answer = self.editor_vars["gabarito"].get().strip().upper()
        keys = [item["chave"] for item in alternatives]
        if answer and answer not in keys:
            messagebox.showerror(APP_NAME, "O gabarito não corresponde a nenhuma chave das alternativas.")
            return

        matter = self.editor_vars["materia"].get().strip()
        lesson = self.editor_vars["aula_planilha"].get().strip()
        primary_topic = self.editor_vars["assunto"].get().strip()
        topics = [
            item.strip()
            for item in self.editor_vars["assuntos"].get().split("|")
            if item.strip()
        ]
        if primary_topic and primary_topic not in topics:
            topics.insert(0, primary_topic)
        question.update(
            {
                "codigo_origem": new_code,
                "materia": matter,
                "aula_planilha": lesson,
                "assunto": primary_topic,
                "assuntos": topics,
                "trilha_assuntos": [item for item in [matter, lesson, primary_topic] if item],
                "banca": self.editor_vars["banca"].get().strip(),
                "ano": year,
                "orgao": self.editor_vars["orgao"].get().strip(),
                "prova": self.editor_vars["prova"].get().strip(),
                "cargo": self.editor_vars["cargo"].get().strip(),
                "area": self.editor_vars["area"].get().strip(),
                "especialidade": self.editor_vars["especialidade"].get().strip(),
                "turno": self.editor_vars["turno"].get().strip(),
                "tipo": self.editor_vars["tipo"].get().strip(),
                "gabarito": answer,
                "enunciado": self.statement_text.get("1.0", "end").strip(),
                "alternativas": alternatives,
                "explicacao": self.explanation_text.get("1.0", "end").strip(),
            }
        )
        classification = question.setdefault("classificacao_planilha", {})
        classification.update(
            {
                "status": "classificado" if matter and primary_topic else "revisar",
                "confianca": 1.0 if matter and primary_topic else 0.5,
                "metodo": "revisao_manual",
                "fonte": self.taxonomy.source_name if self.taxonomy else "Edição manual",
            }
        )
        correct_index = keys.index(answer) if answer in keys else None
        question["telegram"] = {
            "modo": "quiz",
            "pergunta": question["enunciado"],
            "opcoes": [item["texto"] for item in alternatives],
            "indice_correto": correct_index,
        }
        review = question.setdefault("revisao", {})
        if approve:
            review.update({"status": "aprovado", "confianca": 1.0, "alertas": []})
        else:
            review["status"] = review.get("status", "pendente")
        try:
            code_change = self.question_commands.update(
                uid, question, change_source="interface_classica"
            )
        except ValueError as error:
            messagebox.showerror(APP_NAME, str(error))
            return
        if approve:
            self.study.resolve_review_requests_for_question(uid)
        self.refresh_all()
        if self.question_tree.exists(uid):
            self.question_tree.selection_set(uid)
        self.on_question_select()
        if code_change.get("code_changed"):
            messagebox.showinfo(
                APP_NAME,
                (
                    f"Código alterado de {code_change.get('old_code')} para {code_change.get('new_code')}.\n"
                    "As referências foram sincronizadas e a troca ficou registrada."
                ),
            )

    def mark_current_question_annulled(self) -> None:
        if not self.current_question_uid:
            messagebox.showinfo(APP_NAME, "Selecione uma questão para marcar como anulada.")
            return
        question = self.question_queries.get(self.current_question_uid)
        if not question:
            return
        code = str(question.get("codigo_origem", "")).strip()
        reason = simpledialog.askstring(
            APP_NAME,
            (
                f"Informe o motivo da anulação de {code or 'esta questão'} (opcional).\n\n"
                "Ela sairá da base ativa, não será enviada ao Telegram e não voltará em novas importações do mesmo arquivo."
            ),
            initialvalue="Questão anulada pela banca",
            parent=self,
        )
        if reason is None:
            return
        if not messagebox.askyesno(
            APP_NAME,
            f"Confirmar a anulação de {code or 'esta questão'} e retirá-la da base ativa?",
        ):
            return
        uid = self.current_question_uid
        if not self.question_commands.archive(uid, kind="anulada", reason=reason.strip()):
            messagebox.showerror(APP_NAME, "Não foi possível localizar a questão para arquivamento.")
            return
        self.current_question_uid = None
        self.refresh_all()
        self._clear_editor()
        messagebox.showinfo(
            APP_NAME,
            "Questão marcada como anulada e retirada da base ativa. Uma cópia de auditoria foi preservada localmente.",
        )

    def delete_current_question(self) -> None:
        if not self.current_question_uid:
            messagebox.showinfo(APP_NAME, "Selecione uma questão para excluir.")
            return
        question = self.question_queries.get(self.current_question_uid)
        code = str((question or {}).get("codigo_origem", ""))
        if not messagebox.askyesno(
            APP_NAME,
            f"Excluir definitivamente a questão {code or 'selecionada'}?\n\nEla será removida da base, do ciclo de estudos e das estatísticas associadas. Esta ação não pode ser desfeita.",
        ):
            return
        uid = self.current_question_uid
        image_info = (question or {}).get("imagem_questao", {})
        image_path = str(image_info.get("path", "")).strip() if isinstance(image_info, dict) else ""
        self.question_commands.delete(uid)
        if image_path:
            try:
                candidate = Path(image_path)
                if candidate.exists() and QUESTION_IMAGE_DIR in candidate.parents:
                    candidate.unlink()
            except OSError:
                pass
        self.current_question_uid = None
        self.refresh_all()
        self._clear_editor()

    def _clear_editor(self) -> None:
        for variable in self.editor_vars.values():
            variable.set("")
        for widget in (self.statement_text, self.alternatives_text, self.explanation_text):
            self._set_text(widget, "")
        self.review_alerts.configure(text="Selecione uma questão.")
        if hasattr(self, "question_image_label"):
            self.question_image_label.configure(image="", text="Sem imagem")
            self.question_image_label.image = None
        if hasattr(self, "question_image_info"):
            self.question_image_info.configure(text="O recorte automático aparecerá aqui. Se não ficar correto, anexe manualmente.")

