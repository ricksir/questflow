from __future__ import annotations

from .common import *  # noqa: F401,F403


class ShellMixin:
    def _enable_high_dpi(self) -> None:
        if not sys.platform.startswith("win"):
            return
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    def _apply_theme_values(self) -> None:
        theme = str(self.config_data.get("ui_theme", "claro"))
        preset = THEME_PRESETS.get(theme, THEME_PRESETS["claro"])
        COLORS.update(preset)
        accent = ACCENT_PRESETS.get(str(self.config_data.get("ui_accent", "laranja")), ACCENT_PRESETS["laranja"])
        COLORS["orange"], COLORS["orange_dark"] = accent

    def _load_taxonomy(self) -> SpreadsheetTaxonomy | None:
        try:
            if TAXONOMY_PATH.exists():
                return SpreadsheetTaxonomy.load(TAXONOMY_PATH)
        except Exception:
            traceback.print_exc()
        return None

    def _configure_text_selection(self) -> None:
        def select_all(event):
            widget = event.widget
            try:
                if isinstance(widget, tk.Text):
                    widget.tag_add("sel", "1.0", "end-1c")
                    widget.mark_set("insert", "1.0")
                else:
                    widget.selection_range(0, "end")
                    widget.icursor("end")
                return "break"
            except tk.TclError:
                return None

        self.bind_class("TEntry", "<Control-a>", select_all, add="+")
        self.bind_class("TCombobox", "<Control-a>", select_all, add="+")
        self.bind_class("Text", "<Control-a>", select_all, add="+")

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        scale = float(self.config_data.get("ui_scale", 1.0) or 1.0)
        font_size = lambda value: max(7, int(round(value * scale)))
        density = str(self.config_data.get("ui_density", "confortavel"))
        density_map = {
            "compacta": {"row": 25, "button_y": 6, "entry": 5, "heading_y": 6},
            "compacto": {"row": 25, "button_y": 6, "entry": 5, "heading_y": 6},
            "confortavel": {"row": 30, "button_y": 8, "entry": 7, "heading_y": 8},
            "ampla": {"row": 37, "button_y": 11, "entry": 9, "heading_y": 10},
        }
        metrics = dict(density_map.get(density, density_map["confortavel"]))
        metrics["row"] = max(22, int(round(metrics["row"] * scale)))
        metrics["button_y"] = max(4, int(round(metrics["button_y"] * scale)))
        metrics["entry"] = max(4, int(round(metrics["entry"] * scale)))
        metrics["heading_y"] = max(4, int(round(metrics["heading_y"] * scale)))
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "TButton",
            font=("Segoe UI", font_size(10)),
            padding=(max(8, int(round(12 * scale))), metrics["button_y"]),
            background=COLORS["surface"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border"],
        )
        style.map("TButton", background=[("active", "#E9EEF5")])
        style.configure(
            "Primary.TButton",
            background=COLORS["orange"],
            foreground="#FFFFFF",
            bordercolor=COLORS["orange"],
            font=("Segoe UI Semibold", font_size(10)),
        )
        style.map(
            "Primary.TButton",
            background=[("active", COLORS["orange_dark"]), ("disabled", "#F3C99F")],
        )
        style.configure(
            "Danger.TButton",
            background="#FFF1F1",
            foreground=COLORS["red"],
            bordercolor="#F5CACA",
        )
        style.configure(
            "Success.TButton",
            background="#EAF7F0",
            foreground=COLORS["green"],
            bordercolor="#BFE6D0",
        )
        style.configure(
            "Treeview",
            font=("Segoe UI", font_size(9)),
            rowheight=metrics["row"],
            background=COLORS["surface"],
            fieldbackground=COLORS["surface"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border"],
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI Semibold", font_size(9)),
            background="#EAF0F7",
            foreground=COLORS["navy"],
            padding=(6, metrics["heading_y"]),
        )
        style.map("Treeview", background=[("selected", "#DCEBFA")], foreground=[("selected", COLORS["text"])])
        self._configure_imports_tree_style(style)
        style.configure(
            "TEntry", padding=metrics["entry"], fieldbackground=COLORS["surface"], bordercolor=COLORS["border"], foreground=COLORS["text"]
        )
        style.configure("TCombobox", padding=max(5, metrics["entry"] - 1), fieldbackground=COLORS["surface"], foreground=COLORS["text"])
        style.configure(
            "Horizontal.TProgressbar",
            background=COLORS["orange"],
            troughcolor="#E6EBF2",
            bordercolor="#E6EBF2",
        )

    def _build_shell(self) -> None:
        header = tk.Frame(self, bg=COLORS["navy"], height=72)
        header.pack(fill="x")
        header.pack_propagate(False)
        logo = tk.Label(
            header,
            text="Q",
            bg=COLORS["navy"],
            fg=COLORS["orange"],
            font=("Segoe UI Black", 30),
        )
        logo.pack(side="left", padx=(22, 8))
        title_box = tk.Frame(header, bg=COLORS["navy"])
        title_box.pack(side="left", pady=12)
        tk.Label(
            title_box,
            text="QuestFlow Studio",
            bg=COLORS["navy"],
            fg="#FFFFFF",
            font=("Segoe UI Semibold", 17),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="Importação inteligente, banco de questões e fluxo cíclico no Telegram",
            bg=COLORS["navy"],
            fg="#BFD0E4",
            font=("Segoe UI", 9),
        ).pack(anchor="w")
        self.header_status = tk.Label(
            header,
            text="Banco local ativo",
            bg="#163C62",
            fg="#D8E8F7",
            font=("Segoe UI", 9),
            padx=13,
            pady=7,
        )
        self.header_status.pack(side="right", padx=(8, 22))
        header_tools = tk.Frame(header, bg=COLORS["navy"])
        header_tools.pack(side="right")
        tk.Button(
            header_tools,
            text="A−",
            command=lambda: self.adjust_ui_scale(-0.1),
            bg=COLORS["navy_2"], fg="#FFFFFF", activebackground=COLORS["orange"],
            relief="flat", bd=0, padx=9, pady=5, cursor="hand2",
        ).pack(side="left", padx=2)
        self.ui_scale_label = tk.Label(
            header_tools,
            text=f"{float(self.config_data.get('ui_scale', 1.0))*100:.0f}%",
            bg=COLORS["navy"], fg="#D8E8F7", padx=5,
        )
        self.ui_scale_label.pack(side="left")
        tk.Button(
            header_tools,
            text="A+",
            command=lambda: self.adjust_ui_scale(0.1),
            bg=COLORS["navy_2"], fg="#FFFFFF", activebackground=COLORS["orange"],
            relief="flat", bd=0, padx=9, pady=5, cursor="hand2",
        ).pack(side="left", padx=2)
        tk.Button(
            header_tools,
            text="☰",
            command=self.toggle_sidebar,
            bg=COLORS["navy_2"], fg="#FFFFFF", activebackground=COLORS["orange"],
            relief="flat", bd=0, padx=11, pady=5, cursor="hand2",
        ).pack(side="left", padx=(6, 0))

        body = tk.Frame(self, bg=COLORS["background"])
        body.pack(fill="both", expand=True)

        sidebar_width = int(self.config_data.get("ui_sidebar_width", 210) or 210)
        sidebar = tk.Frame(body, bg=COLORS["navy"], width=sidebar_width)
        self.sidebar = sidebar
        self.sidebar_collapsed = bool(self.config_data.get("ui_sidebar_collapsed", False))
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self.nav_buttons: dict[str, tk.Button] = {}
        self.nav_meta: dict[str, tuple[str, str]] = {}
        for page, label, icon in [
            ("dashboard", "Painel adaptativo", "01"),
            ("import", "Importar arquivos", "02"),
            ("review", "Revisar banco", "03"),
            ("flow", "Fluxo Telegram", "04"),
            ("corrections", "Correções Telegram", "05"),
            ("coverage", "Estudos e questões", "06"),
            ("export", "Backup e exportação", "07"),
            ("settings", "Configurações", "08"),
        ]:
            button = tk.Button(
                sidebar,
                text=f"{icon}   {label}",
                command=lambda name=page: self.show_page(name),
                anchor="w",
                relief="flat",
                bd=0,
                bg=COLORS["navy"],
                fg="#D3DFEC",
                activebackground=COLORS["navy_2"],
                activeforeground="#FFFFFF",
                font=("Segoe UI Semibold", 10),
                padx=20,
                pady=13,
                cursor="hand2",
            )
            button.pack(fill="x", padx=10, pady=3)
            self.nav_buttons[page] = button
            self.nav_meta[page] = (label, icon)

        self.sidebar_footer = tk.Label(
            sidebar,
            text=f"Versão {APP_VERSION}\nDados salvos localmente",
            bg=COLORS["navy"],
            fg="#8299B2",
            font=("Segoe UI", 8),
            justify="left",
        )
        self.sidebar_footer.pack(side="bottom", anchor="w", padx=22, pady=22)

        self.content = tk.Frame(body, bg=COLORS["background"])
        self.content.pack(side="left", fill="both", expand=True)

        self.page_frames["dashboard"] = self._build_dashboard_page()
        self.page_frames["import"] = self._build_import_page()
        self.page_frames["review"] = self._build_review_page()
        self.page_frames["flow"] = self._build_flow_page()
        self.page_frames["corrections"] = self._build_corrections_page()
        self.page_frames["coverage"] = self._build_coverage_page()
        self.page_frames["export"] = self._build_export_page()
        self.page_frames["settings"] = self._build_settings_page()
        self._apply_sidebar_state()

    def _walk_widget_tree(self, widget: tk.Widget):
        yield widget
        for child in widget.winfo_children():
            yield from self._walk_widget_tree(child)

    def _apply_live_ui_scale(self) -> None:
        """Atualiza fontes explícitas e estilos sem exigir reinicialização.

        O comando ``tk scaling`` não redimensiona fontes definidas explicitamente
        em cada Label/Text. Por isso preservamos o tamanho-base de cada widget e
        reaplicamos a escala escolhida, evitando crescimento acumulativo.
        """
        scale = float(self.config_data.get("ui_scale", 1.0) or 1.0)
        for widget in self._walk_widget_tree(self):
            try:
                options = widget.keys()
            except Exception:
                continue
            if "font" not in options:
                continue
            key = str(widget)
            try:
                font_spec = widget.cget("font")
                if not font_spec:
                    continue
                if key not in self._font_base_cache:
                    actual = tkfont.Font(font=font_spec).actual()
                    size = int(actual.get("size", 10) or 10)
                    actual["size"] = abs(size) or 10
                    self._font_base_cache[key] = actual
                base = dict(self._font_base_cache[key])
                base["size"] = max(7, int(round(int(base.get("size", 10)) * scale)))
                live_font = tkfont.Font(**base)
                self._live_fonts[key] = live_font
                widget.configure(font=live_font)
                if "wraplength" in options:
                    current_wrap = int(float(widget.cget("wraplength") or 0))
                    if current_wrap > 0 and not hasattr(widget, "_qf_base_wraplength"):
                        widget._qf_base_wraplength = current_wrap
                    base_wrap = int(getattr(widget, "_qf_base_wraplength", 0) or 0)
                    if base_wrap:
                        widget.configure(wraplength=max(120, int(round(base_wrap * scale))))
            except Exception:
                continue
        self._configure_styles()
        self.update_idletasks()

    def adjust_ui_scale(self, delta: float) -> None:
        current = float(self.config_data.get("ui_scale", 1.0) or 1.0)
        new_value = round(max(0.75, min(1.6, current + delta)), 2)
        if new_value == current:
            return
        self.config_data["ui_scale"] = new_value
        save_config(self.config_data)
        try:
            self.tk.call("tk", "scaling", new_value * self.winfo_fpixels("1i") / 72.0)
        except Exception:
            pass
        if hasattr(self, "ui_scale_label"):
            self.ui_scale_label.configure(text=f"{new_value*100:.0f}%")
        if hasattr(self, "appearance_vars") and "ui_scale" in self.appearance_vars:
            self.appearance_vars["ui_scale"].set(f"{new_value:.2f}")
        self._apply_live_ui_scale()

    def toggle_sidebar(self) -> None:
        self.sidebar_collapsed = not bool(getattr(self, "sidebar_collapsed", False))
        self.config_data["ui_sidebar_collapsed"] = self.sidebar_collapsed
        save_config(self.config_data)
        self._apply_sidebar_state()

    def _apply_sidebar_state(self) -> None:
        if not hasattr(self, "sidebar"):
            return
        width = 64 if self.sidebar_collapsed else int(self.config_data.get("ui_sidebar_width", 210) or 210)
        self.sidebar.configure(width=width)
        for page, button in self.nav_buttons.items():
            label, icon = self.nav_meta[page]
            button.configure(text=icon if self.sidebar_collapsed else f"{icon}   {label}", anchor="center" if self.sidebar_collapsed else "w", padx=6 if self.sidebar_collapsed else 20)
        if hasattr(self, "sidebar_footer"):
            self.sidebar_footer.configure(text=f"v{APP_VERSION}" if self.sidebar_collapsed else f"Versão {APP_VERSION}\nDados salvos localmente")
            self.sidebar_footer.pack_configure(anchor="center" if self.sidebar_collapsed else "w", padx=6 if self.sidebar_collapsed else 22)
        if hasattr(self, "study"):
            self.refresh_correction_badge()

    def _page(self) -> tk.Frame:
        return tk.Frame(self.content, bg=COLORS["background"])

    def _section_title(self, parent: tk.Widget, title: str, subtitle: str) -> None:
        tk.Label(
            parent,
            text=title,
            bg=COLORS["background"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 20),
        ).pack(anchor="w")
        tk.Label(
            parent,
            text=subtitle,
            bg=COLORS["background"],
            fg=COLORS["muted"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(2, 16))

    def _surface(self, parent: tk.Widget, **pack_kwargs) -> tk.Frame:
        frame = tk.Frame(
            parent,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            bd=0,
        )
        frame.pack(**pack_kwargs)
        return frame

    def _build_stat_cards(self, parent: tk.Widget) -> tk.Frame:
        row = tk.Frame(parent, bg=COLORS["background"])
        row.pack(fill="x", pady=(0, 15))
        stat_labels: dict[str, tk.Label] = {}
        cards = [
            ("total", "Questões no banco", COLORS["navy"]),
            ("approved", "Aprovadas", COLORS["green"]),
            ("pending", "Pendentes", COLORS["yellow"]),
            ("duplicates", "Duplicatas evitadas", COLORS["red"]),
        ]
        for key, label, color in cards:
            card = tk.Frame(
                row,
                bg="#FFFFFF",
                highlightbackground=COLORS["border"],
                highlightthickness=1,
            )
            card.pack(side="left", fill="x", expand=True, padx=(0, 10))
            tk.Frame(card, bg=color, width=5).pack(side="left", fill="y")
            text = tk.Frame(card, bg="#FFFFFF")
            text.pack(side="left", padx=14, pady=12)
            value = tk.Label(
                text,
                text="0",
                bg="#FFFFFF",
                fg=color,
                font=("Segoe UI Semibold", 20),
            )
            value.pack(anchor="w")
            tk.Label(
                text,
                text=label,
                bg="#FFFFFF",
                fg=COLORS["muted"],
                font=("Segoe UI", 9),
            ).pack(anchor="w")
            stat_labels[key] = value
        self.stat_groups.append(stat_labels)
        return row

    def _configure_imports_tree_style(self, style: ttk.Style | None = None) -> None:
        style = style or ttk.Style(self)
        scale = float(self.config_data.get("ui_scale", 1.0) or 1.0)
        font_size = max(8, min(24, int(round(int(self.config_data.get("imports_table_font_size", 10)) * scale))))
        row_height = max(24, min(72, int(round(int(self.config_data.get("imports_table_row_height", 32)) * scale))))
        style.configure(
            "Imports.Treeview",
            font=("Segoe UI", font_size),
            rowheight=row_height,
            background=COLORS["surface"],
            fieldbackground=COLORS["surface"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border"],
        )
        style.configure(
            "Imports.Treeview.Heading",
            font=("Segoe UI Semibold", font_size),
            background="#EAF0F7",
            foreground=COLORS["navy"],
            padding=(7, max(7, font_size - 2)),
        )

    def change_imports_table_zoom(self, delta: int) -> None:
        current = int(self.config_data.get("imports_table_font_size", 10))
        new_size = max(8, min(16, current + int(delta)))
        if new_size == current:
            return
        self.config_data["imports_table_font_size"] = new_size
        self.config_data["imports_table_row_height"] = max(26, min(52, new_size * 3 + 2))
        save_config(self.config_data)
        self._configure_imports_tree_style()
        if hasattr(self, "imports_zoom_label"):
            self.imports_zoom_label.configure(text=f"{new_size} pt")

    def reset_imports_table_view(self) -> None:
        self.config_data["imports_table_font_size"] = 10
        self.config_data["imports_table_row_height"] = 32
        self.config_data["imports_recent_pane_height"] = 210
        save_config(self.config_data)
        self._configure_imports_tree_style()
        if hasattr(self, "imports_zoom_label"):
            self.imports_zoom_label.configure(text="10 pt")
        self.after(30, self._restore_import_split)

    def _save_import_split(self, _event=None) -> None:
        if not hasattr(self, "import_split"):
            return
        try:
            total = self.import_split.winfo_height()
            sash_y = self.import_split.sash_coord(0)[1]
            recent_height = max(140, min(520, total - sash_y - 8))
            self.config_data["imports_recent_pane_height"] = recent_height
            save_config(self.config_data)
        except (tk.TclError, IndexError, OSError, ValueError):
            pass

    def _restore_import_split(self) -> None:
        if not hasattr(self, "import_split"):
            return
        try:
            self.import_split.update_idletasks()
            total = self.import_split.winfo_height()
            if total <= 1:
                self.after(120, self._restore_import_split)
                return
            recent_height = max(140, min(520, int(self.config_data.get("imports_recent_pane_height", 210))))
            sash_y = max(260, total - recent_height - 8)
            self.import_split.sash_place(0, 0, sash_y)
        except (tk.TclError, IndexError, ValueError):
            pass

    @staticmethod
    def _tree_sort_value(value: str, kind: str):
        value = (value or "").strip()
        if kind == "int":
            try:
                return int(value.replace(".", "").replace(",", "."))
            except ValueError:
                return -1
        if kind == "float":
            try:
                return float(value.replace("%", "").replace(".", "").replace(",", "."))
            except ValueError:
                return float("-inf")
        return value.casefold()

    def make_tree_sortable(
        self,
        tree: ttk.Treeview,
        headings: dict[str, str],
        column_types: dict[str, str] | None = None,
    ) -> None:
        tree_id = id(tree)
        self._tree_heading_labels[tree_id] = dict(headings)
        self._tree_column_types[tree_id] = dict(column_types or {})
        for column, title in headings.items():
            tree.heading(
                column,
                text=title,
                command=lambda col=column, target=tree: self.sort_treeview(target, col),
            )

    def sort_treeview(self, tree: ttk.Treeview, column: str) -> None:
        tree_id = id(tree)
        current = self._tree_sort_state.get(tree_id)
        reverse = (not current[1]) if current and current[0] == column else False
        self._tree_sort_state[tree_id] = (column, reverse)
        self._apply_tree_sort(tree, column, reverse)

    def _apply_tree_sort(self, tree: ttk.Treeview, column: str, reverse: bool) -> None:
        tree_id = id(tree)
        kind = self._tree_column_types.get(tree_id, {}).get(column, "text")
        items = list(tree.get_children(""))
        decorated = [
            (self._tree_sort_value(tree.set(item, column), kind), index, item)
            for index, item in enumerate(items)
        ]
        decorated.sort(key=lambda row: (row[0], row[1]), reverse=reverse)
        for position, (_value, _index, item) in enumerate(decorated):
            tree.move(item, "", position)
        headings = self._tree_heading_labels.get(tree_id, {})
        for key, title in headings.items():
            arrow = " ▼" if reverse else " ▲"
            tree.heading(key, text=title + (arrow if key == column else ""))

    def _reapply_tree_sort(self, tree: ttk.Treeview) -> None:
        current = self._tree_sort_state.get(id(tree))
        if current:
            self._apply_tree_sort(tree, current[0], current[1])

    def show_page(self, name: str) -> None:
        self.current_page = name
        for page_name, frame in self.page_frames.items():
            if page_name == name:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        for page_name, button in self.nav_buttons.items():
            active = page_name == name
            button.configure(
                bg=COLORS["navy_2"] if active else COLORS["navy"],
                fg="#FFFFFF" if active else "#D3DFEC",
            )
        if name == "dashboard":
            self.refresh_adaptive_dashboard()
        elif name == "review":
            self.refresh_question_list()
        elif name == "flow":
            self.refresh_flow_dashboard()
        elif name == "corrections":
            self.refresh_corrections_list()
        elif name == "coverage":
            self.refresh_coverage_map()
        elif name == "export":
            self.refresh_stats()
            self.update_telegram_selection()

    def refresh_all(self) -> None:
        self.refresh_adaptive_dashboard()
        self.refresh_stats()
        self.refresh_recent_imports()
        self.refresh_question_list()
        self.update_telegram_selection()
        self.refresh_flow_dashboard()
        self.refresh_corrections_list()
        self.refresh_correction_badge()
        self.refresh_coverage_map()

    def _walk_widgets(self, widget: tk.Widget):
        for child in widget.winfo_children():
            yield child
            yield from self._walk_widgets(child)

