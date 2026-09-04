from __future__ import annotations

from .common import *  # noqa: F401,F403


class DeepAnalysisMixin:
    def _selected_pending_uids(self) -> list[str]:
        output: list[str] = []
        if not hasattr(self, "question_tree"):
            return output
        for uid in self.question_tree.selection():
            question = self.question_queries.get(uid)
            if question and question.get("revisao", {}).get("status") == "pendente":
                output.append(uid)
        return output

    def _known_source_directories(self) -> list[str]:
        candidates = list(self.config_data.get("source_pdf_directories", []) or [])
        candidates.extend([
            str(BASE_DIR.parent),
            str(Path.home() / "Downloads"),
            str(Path.home() / "Documents"),
        ])
        output: list[str] = []
        for candidate in candidates:
            try:
                path = str(Path(candidate).resolve())
            except Exception:
                continue
            if Path(path).is_dir() and path not in output:
                output.append(path)
        return output

    def _prepare_deep_source_directories(self, uids: list[str]) -> list[str]:
        missing = 0
        for uid in uids:
            question = self.question_queries.get(uid)
            if not question:
                continue
            source = question.get("fonte", {}) if isinstance(question.get("fonte"), dict) else {}
            path = str(source.get("caminho_arquivo", "")).strip()
            if not path or not Path(path).exists():
                missing += 1
        directories = self._known_source_directories()
        if missing and messagebox.askyesno(
            APP_NAME,
            f"{missing} questão(ões) não possuem um caminho válido para o PDF original.\n\n"
            "Deseja selecionar a pasta onde estão os PDFs para que a análise apurada realmente os releia?",
        ):
            directory = filedialog.askdirectory(title="Selecione a pasta raiz dos PDFs originais")
            if directory:
                resolved = str(Path(directory).resolve())
                if resolved not in directories:
                    directories.insert(0, resolved)
                saved = list(self.config_data.get("source_pdf_directories", []) or [])
                if resolved not in saved:
                    saved.insert(0, resolved)
                    self.config_data["source_pdf_directories"] = saved[:10]
                    save_config(self.config_data)
        return directories

    def _start_deep_processing(self, uids: list[str], *, selected_only: bool) -> None:
        if self.deep_process_worker and self.deep_process_worker.is_alive():
            messagebox.showinfo(APP_NAME, "O processamento apurado já está em andamento.")
            return
        uids = list(dict.fromkeys(uid for uid in uids if uid))
        if not uids:
            messagebox.showinfo(APP_NAME, "Não há questões pendentes para processar.")
            return
        scope = "selecionadas" if selected_only else "pendentes"
        if not messagebox.askyesno(
            APP_NAME,
            f"Serão analisadas {len(uids)} questões {scope}.\n\n"
            "A análise fará reparo estrutural, localizará o PDF original, reconstruirá o documento em Markdown, "
            "executará OCR em alta resolução, relerá as imagens e comparará a questão pelo código, número e enunciado.\n\n"
            "A aprovação automática ocorrerá somente quando enunciado, alternativas e gabarito estiverem coerentes. Continuar?",
        ):
            return
        source_directories = self._prepare_deep_source_directories(uids)
        self.deep_process_cancel_event.clear()
        for name in ("deep_process_button", "deep_selected_button", "reread_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(state="disabled")
        self.reread_cancel_button.configure(state="normal", command=self.cancel_deep_process)
        self.reread_status.configure(text=f"0% • Preparando análise apurada de {len(uids)} questões...")
        self.deep_process_worker = threading.Thread(
            target=self._deep_process_worker,
            args=(uids, source_directories),
            daemon=True,
            name="questflow-deep-process",
        )
        self.deep_process_worker.start()

    def process_pending_questions(self) -> None:
        pending_rows = self.question_queries.list(status="pendente", limit=100000)
        self._start_deep_processing([row["uid"] for row in pending_rows], selected_only=False)

    def process_selected_pending_questions(self) -> None:
        selected = self._selected_pending_uids()
        if not selected:
            messagebox.showinfo(
                APP_NAME,
                "Selecione uma ou várias questões pendentes na tabela. Use Ctrl ou Shift para selecionar várias.",
            )
            return
        self._start_deep_processing(selected, selected_only=True)

    @staticmethod
    def _resolve_question_source(question: dict, directories: list[str], filename_cache: dict[str, str]) -> str:
        source = question.get("fonte", {}) if isinstance(question.get("fonte"), dict) else {}
        existing = str(source.get("caminho_arquivo", "")).strip()
        if existing and Path(existing).exists():
            return str(Path(existing).resolve())
        filename = str(source.get("arquivo", "")).strip()
        if not filename:
            return ""
        if filename in filename_cache:
            return filename_cache[filename]
        for directory in directories:
            root = Path(directory)
            direct = root / filename
            if direct.exists():
                filename_cache[filename] = str(direct.resolve())
                return filename_cache[filename]
        for directory in directories:
            root = Path(directory)
            try:
                match = next(root.rglob(filename), None)
            except (OSError, PermissionError):
                match = None
            if match and match.is_file():
                filename_cache[filename] = str(match.resolve())
                return filename_cache[filename]
        filename_cache[filename] = ""
        return ""

    @staticmethod
    def _append_review_alert(question: dict, message: str) -> None:
        review = question.setdefault("revisao", {})
        alerts = list(review.get("alertas", []))
        if message not in alerts:
            alerts.append(message)
        review["alertas"] = alerts
        review["status"] = "pendente"

    def _deep_process_worker(self, uids: list[str], source_directories: list[str]) -> None:
        try:
            processed = approved = pending = reread_count = web_count = 0
            source_missing = reread_failed = candidate_missing = 0
            extraction_cache: dict[str, list[dict]] = {}
            filename_cache: dict[str, str] = {}
            web_enabled = bool(self.config_data.get("web_enrichment_enabled", False))
            web_limit = max(0, min(100, int(self.config_data.get("web_enrichment_max_per_run", 10) or 10)))
            deep_dpi = max(260, min(400, int(self.config_data.get("deep_analysis_dpi", 300) or 300)))
            total = max(1, len(uids))
            for index, uid in enumerate(uids):
                if self.deep_process_cancel_event.is_set():
                    raise ExtractionCancelled("Processamento apurado cancelado.")
                question = self.question_queries.get(uid)
                if not question:
                    continue
                percent = index * 100 / total
                code = str(question.get("codigo_origem", ""))
                self.event_queue.put(("deep_progress", f"{percent:.0f}% • Reparando {code} ({index + 1}/{len(uids)})"))

                repaired = deep_repair_question(
                    question,
                    self.taxonomy,
                    allow_auto_approve=False,
                    method="reparo_local_pre_releitura",
                )
                source_path = self._resolve_question_source(question, source_directories, filename_cache)
                if source_path:
                    repaired.setdefault("fonte", {})["caminho_arquivo"] = source_path
                    if source_path not in extraction_cache:
                        config = ExtractorConfig(
                            dpi=deep_dpi,
                            languages=str(self.config_data.get("languages", "por+eng")),
                            tesseract_cmd=str(self.config_data.get("tesseract_cmd", "")),
                        )

                        def report_pdf(value: float, message: str, *, _index=index, _code=code, _source=source_path) -> None:
                            overall = ((_index + max(0.0, min(1.0, value))) / total) * 100
                            self.event_queue.put((
                                "deep_progress",
                                f"{overall:.0f}% • Markdown/OCR {_code} em {Path(_source).name}: {message}",
                            ))

                        try:
                            extraction = extract_pdf(
                                source_path,
                                config=config,
                                progress=report_pdf,
                                cancel_event=self.deep_process_cancel_event,
                                taxonomy=self.taxonomy,
                                asset_dir=QUESTION_IMAGE_DIR,
                                markdown_cache_dir=MARKDOWN_CACHE_DIR,
                                force_markdown_ocr=True,
                            )
                            extraction_cache[source_path] = list(extraction.get("questions", []))
                        except ExtractionCancelled:
                            raise
                        except Exception as error:
                            extraction_cache[source_path] = []
                            reread_failed += 1
                            self._append_review_alert(repaired, f"Falha na releitura apurada de {Path(source_path).name}: {error}")
                    candidates = extraction_cache.get(source_path, [])
                    candidate = self._find_reread_match(question, candidates)
                    if candidate:
                        candidate = json.loads(json.dumps(candidate, ensure_ascii=False))
                        candidate["id"] = question.get("id", candidate.get("id"))
                        candidate["codigo_origem"] = question.get("codigo_origem", candidate.get("codigo_origem"))
                        candidate["database_uid"] = uid
                        candidate.setdefault("fonte", {})["caminho_arquivo"] = source_path
                        old_classification = question.get("classificacao_planilha", {})
                        if isinstance(old_classification, dict) and old_classification.get("metodo") == "revisao_manual":
                            for key in ("materia", "aula_planilha", "assunto", "assuntos", "trilha_assuntos"):
                                candidate[key] = question.get(key, candidate.get(key))
                            candidate["classificacao_planilha"] = old_classification
                        old_image = question.get("imagem_questao", {})
                        if isinstance(old_image, dict) and old_image.get("origem") == "manual":
                            candidate["imagem_questao"] = old_image
                        if str(question.get("explicacao", "")).strip():
                            candidate["explicacao"] = question.get("explicacao", "")
                        repaired = deep_repair_question(
                            candidate,
                            self.taxonomy,
                            allow_auto_approve=True,
                            method=f"markdown_ocr_apurado_{deep_dpi}dpi",
                        )
                        reread_count += 1
                    elif candidates:
                        candidate_missing += 1
                        self._append_review_alert(
                            repaired,
                            f"PDF relido, mas a questão {code} não foi localizada com segurança no arquivo {Path(source_path).name}",
                        )
                else:
                    source_missing += 1
                    self._append_review_alert(
                        repaired,
                        "PDF original não localizado; selecione a pasta dos PDFs e processe novamente para executar a releitura apurada",
                    )

                if (
                    repaired.get("revisao", {}).get("status") == "pendente"
                    and web_enabled
                    and web_count < web_limit
                ):
                    try:
                        self.event_queue.put(("deep_progress", f"{percent:.0f}% • Pesquisa web assistida para {code}"))
                        enrichment = enrich_question(repaired, max_results=10)
                        repaired = apply_safe_suggestions(repaired, enrichment)
                        repaired = deep_repair_question(
                            repaired,
                            self.taxonomy,
                            allow_auto_approve=True,
                            method="reparo_apurado_com_pesquisa_web",
                        )
                        web_count += 1
                    except Exception as web_error:
                        self._append_review_alert(repaired, f"Pesquisa web não concluída: {web_error}")

                repaired["database_uid"] = uid
                repaired["id"] = question.get("id", repaired.get("id"))
                repaired["codigo_origem"] = question.get("codigo_origem", repaired.get("codigo_origem"))
                repaired["fingerprint"] = question.get("fingerprint", repaired.get("fingerprint"))
                self.question_commands.update(uid, repaired)
                processed += 1
                if repaired.get("revisao", {}).get("status") == "aprovado_automaticamente":
                    approved += 1
                else:
                    pending += 1
                self.event_queue.put((
                    "deep_progress",
                    f"{(index + 1) * 100 / total:.0f}% • Concluída {code} ({index + 1}/{len(uids)})",
                ))
            self.event_queue.put(("deep_done", {
                "processed": processed,
                "approved": approved,
                "pending": pending,
                "reread": reread_count,
                "web": web_count,
                "source_missing": source_missing,
                "reread_failed": reread_failed,
                "candidate_missing": candidate_missing,
            }))
        except ExtractionCancelled:
            self.event_queue.put(("deep_cancelled",))
        except Exception as error:
            self.event_queue.put(("deep_error", str(error), traceback.format_exc()))

    def cancel_deep_process(self) -> None:
        if self.deep_process_worker and self.deep_process_worker.is_alive():
            self.deep_process_cancel_event.set()
            self.reread_status.configure(text="Cancelando processamento apurado...")
            self.reread_cancel_button.configure(state="disabled")

    def _finish_deep_process(self) -> None:
        self.deep_process_worker = None
        self.deep_process_button.configure(state="normal")
        if hasattr(self, "deep_selected_button"):
            self.deep_selected_button.configure(state="normal")
        self.reread_button.configure(state="normal")
        self.reread_cancel_button.configure(state="disabled", command=self.cancel_reread)

    def reread_current_question(self) -> None:
        if self.reread_worker and self.reread_worker.is_alive():
            messagebox.showinfo(APP_NAME, "A releitura de uma questão já está em andamento.")
            return
        uid = self.current_question_uid
        if not uid:
            messagebox.showinfo(APP_NAME, "Selecione uma questão para reler.")
            return
        current = self.question_queries.get(uid)
        if not current:
            return
        source = current.get("fonte", {}) if isinstance(current.get("fonte"), dict) else {}
        source_path = str(source.get("caminho_arquivo", "")).strip()
        if not source_path or not Path(source_path).exists():
            source_path = filedialog.askopenfilename(
                title="Localize o PDF original desta questão",
                initialfile=str(source.get("arquivo", "")),
                filetypes=[
                    ("PDFs e imagens", "*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp"),
                    ("Todos os arquivos", "*.*"),
                ],
            )
        if not source_path:
            return
        if not messagebox.askyesno(
            APP_NAME,
            "O programa relerá o arquivo original e tentará reconstruir o enunciado, as alternativas, o gabarito e os metadados.\n\nAs classificações que você editou manualmente e a imagem manual serão preservadas. Continuar?",
        ):
            return
        self.reread_cancel_event.clear()
        self.reread_button.configure(state="disabled")
        self.reread_cancel_button.configure(state="normal")
        self.reread_status.configure(text=f"0% • Preparando releitura de {Path(source_path).name}...")
        self.reread_worker = threading.Thread(
            target=self._reread_question_worker,
            args=(uid, source_path, current),
            daemon=True,
            name="questflow-reread-question",
        )
        self.reread_worker.start()

    def _reread_question_worker(self, uid: str, source_path: str, current: dict) -> None:
        try:
            config = ExtractorConfig(
                dpi=max(260, int(self.config_data.get("dpi", 180))),
                languages=str(self.config_data.get("languages", "por+eng")),
                tesseract_cmd=str(self.config_data.get("tesseract_cmd", "")),
            )

            def report(value: float, message: str) -> None:
                self.event_queue.put(("reread_progress", f"{value * 100:.0f}% • {message}"))

            extraction = extract_pdf(
                source_path,
                config=config,
                progress=report,
                cancel_event=self.reread_cancel_event,
                taxonomy=self.taxonomy,
                asset_dir=QUESTION_IMAGE_DIR,
                markdown_cache_dir=MARKDOWN_CACHE_DIR,
                force_markdown_ocr=True,
            )
            refreshed = self._find_reread_match(current, list(extraction.get("questions", [])))
            if not refreshed:
                raise RuntimeError("A questão selecionada não foi localizada no arquivo informado.")

            refreshed = json.loads(json.dumps(refreshed, ensure_ascii=False))
            refreshed["id"] = current.get("id", refreshed.get("id"))
            refreshed["codigo_origem"] = current.get("codigo_origem", refreshed.get("codigo_origem"))
            refreshed["fingerprint"] = current.get("fingerprint", refreshed.get("fingerprint"))
            refreshed["database_uid"] = uid
            refreshed.setdefault("fonte", {})["caminho_arquivo"] = str(Path(source_path).resolve())

            old_classification = current.get("classificacao_planilha", {})
            if isinstance(old_classification, dict) and old_classification.get("metodo") == "revisao_manual":
                for key in ("materia", "aula_planilha", "assunto", "assuntos", "trilha_assuntos"):
                    refreshed[key] = current.get(key, refreshed.get(key))
                refreshed["classificacao_planilha"] = old_classification

            old_image = current.get("imagem_questao", {})
            if isinstance(old_image, dict) and old_image.get("origem") == "manual":
                refreshed["imagem_questao"] = old_image
            if str(current.get("explicacao", "")).strip():
                refreshed["explicacao"] = current.get("explicacao", "")

            refreshed = deep_repair_question(
                refreshed,
                self.taxonomy,
                allow_auto_approve=True,
                method="releitura_pdf_260dpi",
            )
            refreshed["database_uid"] = uid
            refreshed["id"] = current.get("id", refreshed.get("id"))
            refreshed["codigo_origem"] = current.get("codigo_origem", refreshed.get("codigo_origem"))
            refreshed["fingerprint"] = current.get("fingerprint", refreshed.get("fingerprint"))
            refreshed.setdefault("fonte", {})["caminho_arquivo"] = str(Path(source_path).resolve())

            keys = [str(item.get("chave", "")).upper() for item in refreshed.get("alternativas", [])]
            answer = str(refreshed.get("gabarito", "")).upper()
            refreshed["telegram"] = {
                "modo": "quiz",
                "pergunta": refreshed.get("enunciado", ""),
                "opcoes": [item.get("texto", "") for item in refreshed.get("alternativas", [])],
                "indice_correto": keys.index(answer) if answer in keys else None,
            }
            review = refreshed.setdefault("revisao", {})
            if review.get("status") != "aprovado_automaticamente":
                alerts = list(review.get("alertas", []))
                notice = "Questão relida do arquivo original; confira os pontos ainda pendentes"
                if notice not in alerts:
                    alerts.insert(0, notice)
                review.update({"status": "pendente", "alertas": alerts})
            self.question_commands.update(uid, refreshed)
            self.event_queue.put((
                "reread_done",
                uid,
                f"Questão relida com sucesso a partir de:\n{source_path}\n\nConfira o enunciado, as alternativas, o gabarito e a imagem antes de aprovar.",
            ))
        except ExtractionCancelled:
            self.event_queue.put(("reread_cancelled",))
        except Exception as error:
            self.event_queue.put(("reread_error", str(error), traceback.format_exc()))

    def cancel_reread(self) -> None:
        if self.reread_worker and self.reread_worker.is_alive():
            self.reread_cancel_event.set()
            self.reread_status.configure(text="Cancelando releitura...")
            self.reread_cancel_button.configure(state="disabled")

    def _finish_reread(self) -> None:
        self.reread_worker = None
        self.reread_button.configure(state="normal")
        self.reread_cancel_button.configure(state="disabled")

