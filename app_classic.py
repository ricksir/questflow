from __future__ import annotations

import queue
import threading
import tkinter as tk
import tkinter.font as tkfont

from app_shared import *  # noqa: F401,F403
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from core.flow import CyclicStudyEngine
from core.background_runtime import BackgroundRuntime
from core.question_services import QuestionQueryService, QuestionCommandService

from ui.shell_mixin import ShellMixin
from ui.dashboard_mixin import DashboardMixin
from ui.import_mixin import ImportMixin
from ui.review_layout_mixin import ReviewLayoutMixin
from ui.review_enrichment_mixin import ReviewEnrichmentMixin
from ui.deep_analysis_mixin import DeepAnalysisMixin
from ui.question_editor_mixin import QuestionEditorMixin
from ui.corrections_coverage_mixin import CorrectionsCoverageMixin
from ui.flow_mixin import FlowMixin
from ui.settings_export_mixin import SettingsExportMixin
from ui.catalog_settings_mixin import CatalogSettingsMixin


class QuestFlowApp(
    ShellMixin,
    DashboardMixin,
    ImportMixin,
    ReviewLayoutMixin,
    ReviewEnrichmentMixin,
    DeepAnalysisMixin,
    QuestionEditorMixin,
    CorrectionsCoverageMixin,
    FlowMixin,
    CatalogSettingsMixin,
    SettingsExportMixin,
    tk.Tk,

):
    @property
    def question_queries(self) -> QuestionQueryService:
        service = self.__dict__.get("_question_queries")
        if service is None:
            service = QuestionQueryService(self.database)
            self.__dict__["_question_queries"] = service
        return service

    @question_queries.setter
    def question_queries(self, value: QuestionQueryService) -> None:
        self.__dict__["_question_queries"] = value

    @property
    def question_commands(self) -> QuestionCommandService:
        service = self.__dict__.get("_question_commands")
        if service is None:
            service = QuestionCommandService(self.database)
            self.__dict__["_question_commands"] = service
        return service

    @question_commands.setter
    def question_commands(self, value: QuestionCommandService) -> None:
        self.__dict__["_question_commands"] = value

    def __init__(self) -> None:
        super().__init__()
        self.config_data = load_config()
        self._enable_high_dpi()
        self._apply_theme_values()
        self.title(f"{APP_NAME} {APP_VERSION}")
        try:
            classic_theme = str(self.config_data.get("ui_theme", "claro")).strip().lower()
            icon_name = "questflow_logo_dark_64.png" if classic_theme in {"escuro", "alto_contraste"} else "questflow_logo_light_64.png"
            icon_path = BASE_DIR / "web" / "assets" / icon_name
            if icon_path.is_file():
                self._questflow_icon = tk.PhotoImage(file=str(icon_path))
                self.iconphoto(True, self._questflow_icon)
        except Exception:
            self._questflow_icon = None
        self.geometry(str(self.config_data.get("window_geometry", "1360x850")))
        self.minsize(1050, 650)
        self.configure(bg=COLORS["background"])
        try:
            self.tk.call("tk", "scaling", float(self.config_data.get("ui_scale", 1.0)) * self.winfo_fpixels("1i") / 72.0)
        except Exception:
            pass

        self.taxonomy = self._load_taxonomy()
        self.database = QuestFlowDatabase(DATABASE_PATH)
        self.question_queries = QuestionQueryService(self.database)
        self.question_commands = QuestionCommandService(self.database)
        self.background_runtime = BackgroundRuntime(max_concurrency=4)
        self.study = StudyRepository(self.database)
        self.study.set_learning_preferences(
            target_retention=float(self.config_data.get("flow_target_retention", 0.88) or 0.88),
            retention_mode=str(self.config_data.get("flow_target_retention_mode", "optimized") or "optimized"),
            exam_date=str(self.config_data.get("flow_exam_date", "") or ""),
            daily_minutes=int(self.config_data.get("flow_daily_study_minutes", 45) or 45),
            maximum_interval_days=int(self.config_data.get("flow_fsrs_max_interval_days", 365) or 365),
            relearning_minutes=int(self.config_data.get("flow_relearning_minutes", 10) or 10),
            studied_only=bool(self.config_data.get("flow_studied_only", True)),
            early_review_enabled=bool(self.config_data.get("flow_early_review_enabled", False)),
        )
        if self.taxonomy is not None:
            self.study.refresh_studied_scope(self.taxonomy.tasks)
        self.flow_engine = CyclicStudyEngine(
            self.database, self.study, lambda: dict(self.config_data), self._on_flow_engine_event
        )
        self.import_files: list[str] = []
        self.event_queue: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.reread_worker: threading.Thread | None = None
        self.reread_cancel_event = threading.Event()
        self.deep_process_worker: threading.Thread | None = None
        self.deep_process_cancel_event = threading.Event()
        self.web_enrichment_worker: threading.Thread | None = None
        self.current_question_uid: str | None = None
        self.review_layout_orientation = "horizontal"
        self.review_layout_mode = "both"
        self.review_layout_swapped = False
        self.current_page = "import"
        self.page_frames: dict[str, tk.Frame] = {}
        self.stat_groups: list[dict[str, tk.Label]] = []
        self._tree_sort_state: dict[int, tuple[str, bool]] = {}
        self._tree_heading_labels: dict[int, dict[str, str]] = {}
        self._tree_column_types: dict[int, dict[str, str]] = {}
        self._font_base_cache: dict[str, dict] = {}
        self._live_fonts: dict[str, tkfont.Font] = {}

        self._configure_styles()
        self._configure_text_selection()
        self._build_shell()
        self.after_idle(self._apply_live_ui_scale)
        self.show_page("dashboard")
        self.refresh_all()
        self.after(120, self._poll_events)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind_all("<Control-r>", lambda _event: self.reread_current_question())
        self.bind_all("<Control-Delete>", lambda _event: self.delete_current_question())
        self.bind_all("<MouseWheel>", self._route_review_mousewheel, add="+")
        self.bind_all("<Button-4>", self._route_review_mousewheel, add="+")
        self.bind_all("<Button-5>", self._route_review_mousewheel, add="+")
        if self.config_data.get("telegram_bot_token") and self.config_data.get("telegram_chat_id"):
            # O motor de manutenção permanece ativo mesmo com o ciclo diário desativado:
            # recupera cliques de correção, reenvia falhas e questões sem resposta.
            self.after(800, lambda: self.flow_engine.start(start_listener=True))
        self.after(1200, self.offer_legacy_database_migration)

    def on_close(self) -> None:
        try:
            self.config_data["window_geometry"] = self.geometry()
            if hasattr(self, "review_split") and self.review_layout_mode == "both":
                size = self.review_split.winfo_width() if self.review_layout_orientation == "horizontal" else self.review_split.winfo_height()
                if size > 10:
                    sash = self.review_split.sash_coord(0)[0 if self.review_layout_orientation == "horizontal" else 1]
                    self.config_data["review_sash_ratio"] = max(0.2, min(0.8, sash / size))
            if hasattr(self, "flow_split"):
                size = self.flow_split.winfo_width()
                if size > 10:
                    self.config_data["flow_sash_ratio"] = max(0.25, min(0.75, self.flow_split.sash_coord(0)[0] / size))
            save_config(self.config_data)
        except Exception:
            pass
        try:
            self.flow_engine.stop()
        except Exception:
            pass
        try:
            self.save_flow_settings(silent=True)
            self.save_settings(silent=True)
        except Exception:
            pass
        try:
            self.background_runtime.shutdown()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = QuestFlowApp()
    app.mainloop()
