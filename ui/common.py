from __future__ import annotations

import csv
import json
from difflib import SequenceMatcher
import os
import queue
import re
import shutil
import sys
import threading
import traceback
import tempfile
import webbrowser
import urllib.parse
import ctypes
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
import tkinter.font as tkfont
from PIL import Image, ImageTk

from app_shared import *  # noqa: F401,F403
from core.exporter import (
    export_csv, export_json, convert_legacy_qflow, export_qflow_bundle,
    export_qflow_package, import_qflow_bundle, count_exportable_questions,
    validate_questflow_question_bank,
)
from core.extractor import (
    ExtractorConfig, ExtractionCancelled, configure_tesseract, extract_pdf,
    deep_repair_question,
)
from core.spreadsheet_taxonomy import (
    DEFAULT_SPREADSHEET_URL, SpreadsheetTaxonomy, build_taxonomy_from_xlsx,
    download_public_spreadsheet, save_taxonomy,
)
from core.course_catalog import CourseCatalogService, MERGE_STRATEGY
from core.trail_guides import (
    ensure_registry, guide_status_for_tasks, import_guide_pdfs, trail_label, trail_number,
)
from core.telegram import (
    send_quiz, send_quiz_with_retry, classify_exception, get_me,
    get_webhook_info, delete_webhook, get_updates, telegram_payload,
)
from core.enrichment import (
    enrich_question, apply_safe_suggestions, enrichment_from_candidate,
    enrich_selected_url, WebEnrichmentError,
)
from core.google_browser import close_google_browser_session
from core.health import collect_health
