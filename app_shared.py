from __future__ import annotations

import json
from pathlib import Path

# Keep the composition root lightweight. Importing the taxonomy module here
# caused every startup path (including the tiny pywebview launcher) to load a
# comparatively large parsing module before the first window could be drawn.
# The value is stable application configuration, so it belongs in this shared
# module rather than behind an eager core import.
DEFAULT_SPREADSHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1lT6I_8fgNiBSt7wlfGH7eXfubkupbAsH03gkxJ7jBd4/edit?usp=sharing"
)

BASE_DIR = Path(__file__).resolve().parent
APP_NAME = "QuestFlow Studio"

def _read_app_version() -> str:
    try:
        value = (BASE_DIR / "VERSION.txt").read_text(encoding="utf-8").strip()
        return value or "0.0.0"
    except OSError:
        return "0.0.0"

APP_VERSION = _read_app_version()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = DATA_DIR / "config.json"
DATABASE_PATH = DATA_DIR / "questflow_questions.sqlite"
TAXONOMY_PATH = DATA_DIR / "taxonomia_afrfb.json"
TRAIL_GUIDES_PATH = DATA_DIR / "trail_guides.json"
QUESTION_IMAGE_DIR = DATA_DIR / "question_images"
QUESTION_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
MARKDOWN_CACHE_DIR = DATA_DIR / "markdown_cache"
MARKDOWN_CACHE_DIR.mkdir(parents=True, exist_ok=True)

COLORS = {
    "navy": "#0F2744",
    "navy_2": "#173A63",
    "orange": "#F28C28",
    "orange_dark": "#D9730D",
    "background": "#F3F6FA",
    "surface": "#FFFFFF",
    "text": "#172033",
    "muted": "#6B7280",
    "border": "#DCE3EC",
    "green": "#178A54",
    "red": "#C03A3A",
    "yellow": "#B7791F",
}

THEME_PRESETS = {
    "claro": {
        "navy": "#102A43", "navy_2": "#1F4E79", "background": "#F4F7FB",
        "surface": "#FFFFFF", "text": "#102133", "muted": "#66788A", "border": "#D8E2EC",
    },
    "escuro": {
        "navy": "#0B1725", "navy_2": "#173A5E", "background": "#101923",
        "surface": "#182431", "text": "#EDF4FA", "muted": "#A9BAC8", "border": "#304255",
    },
    "alto_contraste": {
        "navy": "#000000", "navy_2": "#222222", "background": "#F8F8F8",
        "surface": "#FFFFFF", "text": "#000000", "muted": "#333333", "border": "#000000",
    },
}
ACCENT_PRESETS = {
    "laranja": ("#F28C28", "#D9730D"),
    "azul": ("#2878D0", "#165DA8"),
    "verde": ("#1D9A6C", "#137351"),
    "roxo": ("#7C5CFC", "#5A3FDB"),
    "vermelho": ("#D94B4B", "#B52E2E"),
}

DEFAULT_CONFIG = {
    "dpi": 180,
    "languages": "por+eng",
    "tesseract_cmd": "",
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "taxonomy_spreadsheet_url": DEFAULT_SPREADSHEET_URL,
    "approved_only_export": False,
    "flow_enabled": False,
    "flow_questions_per_cycle": 20,
    "flow_extra_questions_count": 5,
    "flow_daily_time": "19:00",
    "flow_delay_seconds": 5,
    "flow_reminder_minutes": 15,
    "flow_retry_minutes": 10,
    "flow_question_retry_attempts": 3,
    "flow_auto_retry_failed": True,
    "flow_unanswered_resend_enabled": True,
    "flow_unanswered_resend_hours": 24,
    "flow_unanswered_max_resends": 2,
    "flow_unanswered_batch_limit": 1,
    "flow_unanswered_daily_cap": 3,
    "flow_unanswered_session_cap": 3,
    "flow_background_startup_grace_minutes": 5,
    "flow_failed_retry_batch_limit": 1,
    "flow_failed_retry_session_cap": 5,
    "flow_send_pre_reminder": True,
    "flow_catch_up_missed": True,
    "flow_send_completion_menu": True,
    "flow_explanation_mode": "automatico",
    "flow_question_card_enabled": True,
    "flow_native_quiz_explanation": False,
    "flow_weekdays": [0, 1, 2, 3, 4, 5, 6],
    "flow_subjects": [],
    "flow_topic": "",
    "flow_strategy": "adaptativo",
    "flow_target_retention": 0.88,
    "flow_target_retention_mode": "optimized",
    "flow_fsrs_auto_optimize": True,
    "flow_studied_only": True,
    "flow_early_review_enabled": False,
    "flow_relearning_enabled": True,
    "flow_relearning_minutes": 10,
    "flow_relearning_daily_cap": 6,
    "flow_fsrs_max_interval_days": 365,
    "flow_exam_date": "",
    "flow_daily_study_minutes": 45,
    "flow_dynamic_cycle_size": True,
    "flow_approved_only": True,
    "flow_recycle_when_empty": True,
    "imports_table_font_size": 10,
    "imports_table_row_height": 32,
    "imports_recent_pane_height": 210,
    "ui_theme": "claro",
    "ui_accent": "laranja",
    "ui_scale": 1.0,
    "ui_density": "confortavel",
    "ui_sidebar_width": 210,
    "ui_sidebar_collapsed": False,
    "window_geometry": "1360x850",
    "review_sash_ratio": 0.47,
    "flow_sash_ratio": 0.52,
    "ai_active_provider": "local",
    "ai_openai_model": "",
    "ai_gemini_model": "gemini-3.6-flash",
    "ai_anthropic_model": "",
    # AI Gateway 6.5.1: privacidade por minimização de dados. O modo equilibrado
    # compartilha apenas o necessário para a tarefa; perfil do aluno e notas pessoais ficam fora por padrão.
    "ai_privacy_mode": "balanced",
    "share_taxonomy": True,
    "share_statement": True,
    "share_alternatives": True,
    "share_official_answer": True,
    "share_rag": True,
    # 6.8.0: binários (imagem/PDF) exigem opt-in explícito no modo Personalizado.
    "share_binary_media": False,
    "share_learner_summary": False,
    "share_user_prompt": True,
    "share_personal_notes": False,
    "confirm_before_external": True,
    "ai_cost_openai_input_per_million": 0.0,
    "ai_cost_openai_output_per_million": 0.0,
    "ai_cost_gemini_input_per_million": 0.0,
    "ai_cost_gemini_output_per_million": 0.0,
    "ai_cost_anthropic_input_per_million": 0.0,
    "ai_cost_anthropic_output_per_million": 0.0,
    # Monitor quinzenal consent-first (6.4.1). O agendador local nunca acessa
    # a internet sozinho; ele apenas pergunta ao usuário nos dias configurados.
    "update_monitor_enabled": True,
    "update_monitor_days": [1, 15],
    "web_enrichment_enabled": False,
    "web_enrichment_max_per_run": 10,
    "markdown_force_ocr_pending": True,
    "source_pdf_directories": [],
    "deep_analysis_dpi": 300,
    # Rede corporativa / proxy (5.3+). O canal local 127.0.0.1 nunca usa proxy.
    "network_mode": "auto",
    "network_proxy_host": "",
    "network_proxy_port": "",
    "network_pac_url": "",
    "network_proxy_bypass": "localhost;127.0.0.1;::1;<local>",
    "network_proxy_auth": "none",
    "network_proxy_username": "",
    # Turso Cloud Sync (5.5.0). O banco principal continua local/SQLite.
    "cloud_sync_enabled": False,
    "cloud_turso_url": "",
    "cloud_device_name": "",
    "cloud_sync_interval_seconds": 30,
    "cloud_sync_timeout_seconds": 15,
    "cloud_sync_on_start": True,
    "cloud_sync_on_shutdown": True,
    # 6.14.1: a primeira escrita no Turso só ocorre após preflight + backup + dry-run.
    "cloud_sync_safe_activation_required": True,
    "cloud_sync_retry_base_seconds": 5,
    "cloud_sync_retry_max_seconds": 300,
    # Acesso opcional pelo celular na mesma LAN enquanto esta instância estiver aberta.
    # Runtime Watchdog & Self-Healing (6.6.8). Serviço transversal do
    # monólito modular; novos módulos podem ser registrados livremente.
    "watchdog_enabled": True,
    "watchdog_auto_recover": True,
    "watchdog_interval_seconds": 5,
    "watchdog_max_restarts_per_window": 3,
    "watchdog_restart_window_seconds": 600,
    "watchdog_history_limit": 300,
    "watchdog_journal_max_mb": 2,
    "watchdog_task_stall_seconds": 240,
    "runtime_io_max_concurrency": 4,
    "runtime_task_history_limit": 160,
    # Limites locais de admissão. Os limites reais dos provedores continuam
    # sendo autoridade; estes valores apenas evitam rajadas acidentais.
    "ai_rate_limit_per_minute": 30,
    "cloud_rate_limit_per_minute": 120,
    "update_monitor_rate_limit_per_minute": 30,
    "telegram_rate_limit_per_minute": 3000,
    "mobile_lan_enabled": False,
    # QuestFlow Mobile Cloud Bridge (6.9.6). Separate from the full Turso DB sync:
    # publishes only mobile-safe projections/study packs to an always-on gateway.
    "mobile_cloud_bridge_enabled": False,
    "mobile_cloud_bridge_url": "",
    "mobile_cloud_bridge_interval_seconds": 30,
    "mobile_cloud_bridge_pack_size": 40,
    # Catálogo de questões (monólito modular). O padrão local preserva todo o
    # comportamento existente; ``api_das_questoes`` habilita o adapter externo.
    "question_source_provider": "local",
    "api_das_questoes_base_url": "https://api.apidasquestoes.com.br/api/v1",
    "api_das_questoes_timeout_seconds": 20,
    "api_das_questoes_default_review_status": "pendente",
}


def load_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    legacy_telegram = False
    if CONFIG_PATH.exists():
        try:
            loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            config.update(loaded)
            legacy_telegram = bool(str(loaded.get("telegram_bot_token") or "").strip())
            # Migração automática do agendador por intervalo (2.0.x) para o ciclo diário (2.1.x).
            if "flow_daily_time" not in loaded:
                config["flow_daily_time"] = "19:00"
                config["flow_questions_per_cycle"] = 20
                config["flow_extra_questions_count"] = 5
                config["flow_strategy"] = "auditor_inteligente"
                config["flow_send_pre_reminder"] = True
                config["flow_catch_up_missed"] = True
                config["flow_send_completion_menu"] = True
        except (OSError, json.JSONDecodeError):
            pass
    try:
        from core.telegram_secrets import hydrate_and_migrate
        hydrate_and_migrate(config, CONFIG_PATH)
    except Exception:
        pass
    if legacy_telegram:
        # Remove a cópia antiga em texto claro imediatamente após a migração.
        save_config(config)
    return config


def save_config(config: dict) -> None:
    payload = dict(config)
    payload.pop("telegram_bot_token", None)
    CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
