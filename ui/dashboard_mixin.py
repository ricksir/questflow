from __future__ import annotations

from .common import *  # noqa: F401,F403


class DashboardMixin:
    def _build_dashboard_page(self) -> tk.Frame:
        page = self._page()
        container = tk.Frame(page, bg=COLORS["background"])
        container.pack(fill="both", expand=True, padx=24, pady=20)
        self._section_title(
            container,
            "Painel adaptativo — Mission Control",
            "Visão do aprendizado, risco de esquecimento, cobertura e estado do modelo local.",
        )

        cards = tk.Frame(container, bg=COLORS["background"])
        cards.pack(fill="x", pady=(0, 14))
        self.dashboard_stat_labels: dict[str, tk.Label] = {}
        for key, label, color in [
            ("retention", "Retenção prevista", COLORS["green"]),
            ("due", "Revisões vencidas", COLORS["red"]),
            ("new", "Questões novas", COLORS["orange_dark"]),
            ("accuracy", "Acurácia histórica", COLORS["navy_2"]),
            ("samples", "Amostras do modelo", COLORS["yellow"]),
            ("level", "Nível de estudo", COLORS["orange"]),
            ("health", "Saúde do sistema", COLORS["green"]),
        ]:
            card = tk.Frame(cards, bg=COLORS["surface"], highlightbackground=COLORS["border"], highlightthickness=1)
            card.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Frame(card, bg=color, height=4).pack(fill="x")
            value = tk.Label(card, text="0", bg=COLORS["surface"], fg=color, font=("Segoe UI Semibold", 18))
            value.pack(anchor="w", padx=12, pady=(10, 0))
            tk.Label(card, text=label, bg=COLORS["surface"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w", padx=12, pady=(0, 10))
            self.dashboard_stat_labels[key] = value

        split = tk.PanedWindow(
            container,
            orient="horizontal",
            bg=COLORS["background"],
            sashwidth=8,
            sashrelief="raised",
            relief="flat",
        )
        split.pack(fill="both", expand=True)
        left = tk.Frame(split, bg=COLORS["surface"], highlightbackground=COLORS["border"], highlightthickness=1)
        right = tk.Frame(split, bg=COLORS["surface"], highlightbackground=COLORS["border"], highlightthickness=1)
        split.add(left, minsize=340, width=470, stretch="always")
        split.add(right, minsize=500, stretch="always")

        tk.Label(left, text="Estado do motor adaptativo", bg=COLORS["surface"], fg=COLORS["navy"], font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=18, pady=(18, 6))
        self.dashboard_model_label = tk.Label(
            left,
            text="Carregando modelo...",
            bg="#EEF5FB",
            fg=COLORS["navy"],
            justify="left",
            anchor="nw",
            wraplength=410,
            padx=14,
            pady=12,
        )
        self.dashboard_model_label.pack(fill="x", padx=18, pady=(0, 12))

        tk.Label(left, text="Recomendação do próximo ciclo", bg=COLORS["surface"], fg=COLORS["navy"], font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=18, pady=(8, 6))
        self.dashboard_recommendation_label = tk.Label(
            left,
            text="Aguardando dados suficientes.",
            bg="#FFF8E8",
            fg=COLORS["yellow"],
            justify="left",
            anchor="nw",
            wraplength=410,
            padx=14,
            pady=12,
        )
        self.dashboard_recommendation_label.pack(fill="x", padx=18, pady=(0, 14))

        actions = tk.Frame(left, bg=COLORS["surface"])
        actions.pack(fill="x", padx=18, pady=(0, 18))
        ttk.Button(actions, text="Atualizar painel", command=self.refresh_adaptive_dashboard).pack(side="left")
        ttk.Button(actions, text="Abrir ciclo Telegram", style="Primary.TButton", command=lambda: self.show_page("flow")).pack(side="left", padx=8)
        ttk.Button(actions, text="Reiniciar ciclo", command=self.reset_study_cycle).pack(side="left")

        tk.Label(right, text="Prioridade por matéria", bg=COLORS["surface"], fg=COLORS["navy"], font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=16, pady=(16, 8))
        table = tk.Frame(right, bg=COLORS["surface"])
        table.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        columns = ("subject", "questions", "due", "prediction", "priority")
        self.dashboard_subject_tree = ttk.Treeview(table, columns=columns, show="headings")
        headings = {
            "subject": "Matéria",
            "questions": "Questões",
            "due": "Vencidas",
            "prediction": "Retenção",
            "priority": "Prioridade",
        }
        widths = {"subject": 260, "questions": 90, "due": 90, "prediction": 100, "priority": 100}
        for key, title in headings.items():
            self.dashboard_subject_tree.heading(key, text=title)
            self.dashboard_subject_tree.column(key, width=widths[key], anchor="w" if key == "subject" else "center")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.dashboard_subject_tree.yview)
        self.dashboard_subject_tree.configure(yscrollcommand=scroll.set)
        self.dashboard_subject_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.make_tree_sortable(
            self.dashboard_subject_tree,
            headings,
            {"questions": "int", "due": "int", "prediction": "float", "priority": "float"},
        )
        return page

    def refresh_adaptive_dashboard(self) -> None:
        if not hasattr(self, "dashboard_stat_labels"):
            return
        try:
            data = self.study.adaptive_dashboard()
            analytics_rows = self.study.subject_stats(limit=12)
        except Exception as error:
            self.dashboard_model_label.configure(text=f"Não foi possível carregar o modelo:\n{error}", bg="#FFF1F1", fg=COLORS["red"])
            return
        retention_weight = sum(int(row.get("retention_sample") or 0) for row in analytics_rows)
        retention_value = (
            sum(float(row.get("retention") or 0.0) * int(row.get("retention_sample") or 0) for row in analytics_rows) / retention_weight
            if retention_weight else 0.0
        )
        self.dashboard_stat_labels["retention"].configure(text=f"{retention_value:.0f}%" if retention_weight else "—")
        self.dashboard_stat_labels["due"].configure(text=str(data["due_count"]))
        self.dashboard_stat_labels["new"].configure(text=str(data["new_count"]))
        self.dashboard_stat_labels["accuracy"].configure(text=f"{data['accuracy']*100:.1f}%")
        self.dashboard_stat_labels["samples"].configure(text=str(data["model"]["samples"]))
        profile = data.get("profile", {})
        self.dashboard_stat_labels["level"].configure(text=str(profile.get("level", 1)))
        health = collect_health(DATABASE_PATH).to_dict()
        health_text = "OK" if health.get("status") == "operacional" else str(health.get("status", "atenção")).upper()
        self.dashboard_stat_labels["health"].configure(text=health_text)

        target = float(self.config_data.get("flow_target_retention", 0.88) or 0.88)
        model = data["model"]
        calibration = data.get("calibration", {})
        calibration_samples = int(calibration.get("samples", 0) or 0)
        calibration_text = (
            f"Brier {float(calibration.get('brier', 0.0)):.3f} · "
            f"ECE {float(calibration.get('expected_calibration_error', 0.0)):.3f}"
            if calibration_samples else "aguardando respostas"
        )
        self.dashboard_model_label.configure(
            text=(
                f"Motor: {model['version']}\n"
                f"Retenção-alvo: {target*100:.0f}%\n"
                f"Estabilidade média: {data['avg_stability']:.1f} dia(s)\n"
                f"Dificuldade média: {data['avg_difficulty']:.1f}/10\n"
                f"Melhor sequência: {data['best_streak']}\n"
                f"Scheduler: {'FSRS oficial' if data.get('fsrs_available') else 'DSR local (fallback seguro)'}\n"
                f"Bandit de assuntos: {data.get('topic_bandit_version', 'não disponível')}\n"
                f"Calibração ({calibration_samples}): {calibration_text}\n"
                f"XP total: {profile.get('total_xp', 0)} · Nível {profile.get('level', 1)}\n"
                f"Banco: {health.get('database_latency_ms', 0):.1f} ms · "
                f"Falhas pendentes: {health.get('failed_deliveries', 0)}"
            ),
            bg="#EEF5FB",
            fg=COLORS["navy"],
        )
        if data["due_count"]:
            recommendation = (
                f"Priorize as {data['due_count']} revisões vencidas antes de ampliar o volume. "
                "O motor distribuirá as questões entre matérias e assuntos para reduzir repetição excessiva."
            )
            bg, fg = "#FFF1F1", COLORS["red"]
        elif data["new_count"]:
            recommendation = (
                f"Não há revisão vencida. Há {data['new_count']} questão(ões) nova(s); "
                "um ciclo misto entre novas e conteúdos de menor retenção é o mais equilibrado."
            )
            bg, fg = "#FFF8E8", COLORS["yellow"]
        else:
            recommendation = "Banco em dia. Mantenha ciclos menores e regulares para preservar a retenção-alvo."
            bg, fg = "#EAF7F0", COLORS["green"]
        self.dashboard_recommendation_label.configure(text=recommendation, bg=bg, fg=fg)

        for item in self.dashboard_subject_tree.get_children():
            self.dashboard_subject_tree.delete(item)
        for row in analytics_rows:
            retention = row.get("retention")
            priority_label = str(row.get("priority_label") or "")
            priority_score = float(row.get("priority_score") or 0.0)
            self.dashboard_subject_tree.insert(
                "", "end",
                values=(
                    row.get("subject") or "SEM MATÉRIA",
                    int(row.get("questions") or 0),
                    int(row.get("due_count") or 0),
                    "—" if retention is None else f"{float(retention):.0f}%",
                    priority_label if priority_label == "Aguardando estudo" else f"{priority_score:.0f} · {priority_label}",
                ),
            )

    def refresh_stats(self) -> None:
        stats = self.question_queries.stats()
        for group in self.stat_groups:
            for key in ("total", "approved", "pending", "duplicates"):
                if key in group:
                    group[key].configure(text=str(stats[key]))
        self.header_status.configure(text=f"{stats['total']} questões • {stats['pending']} pendentes")

