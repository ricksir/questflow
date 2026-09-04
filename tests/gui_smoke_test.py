from __future__ import annotations

import tkinter.font as tkfont
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from app import CONFIG_PATH, DATABASE_PATH, QuestFlowApp


def main() -> int:
    config_existed = CONFIG_PATH.exists()
    config_bytes = CONFIG_PATH.read_bytes() if config_existed else b""
    db_existed = DATABASE_PATH.exists()
    app = None
    try:
        app = QuestFlowApp()
        app.update_idletasks()
        app.update()
        before = int(tkfont.Font(font=app.statement_text.cget("font")).actual()["size"])
        app.adjust_ui_scale(0.2)
        app.update_idletasks()
        app.update()
        after = int(tkfont.Font(font=app.statement_text.cget("font")).actual()["size"])
        if after <= before:
            raise AssertionError(f"fonte não aumentou: {before} -> {after}")
        if str(app.question_tree.cget("selectmode")) != "extended":
            raise AssertionError("a tabela de revisão não permite seleção múltipla")
        if not hasattr(app, "web_batch_button") or not hasattr(app, "deep_selected_button"):
            raise AssertionError("controles de processamento em lote ausentes")
        if int(app.reread_status.cget("wraplength")) <= 0:
            raise AssertionError("status da revisão não quebra linhas")
        if "corrections" not in app.page_frames or not hasattr(app, "corrections_tree"):
            raise AssertionError("aba Correções Telegram não foi criada")
        if "coverage" not in app.page_frames or not hasattr(app, "coverage_tree"):
            raise AssertionError("aba Mapa de aulas não foi criada")
        if "dashboard" not in app.page_frames or not hasattr(app, "dashboard_subject_tree"):
            raise AssertionError("aba Painel adaptativo não foi criada")
        app.show_page("corrections")
        app.update_idletasks()
        if app.current_page != "corrections":
            raise AssertionError("não foi possível abrir a aba Correções Telegram")
        print(f"[OK] Escala ao vivo: {before} -> {after}")
        print("[OK] Seleção múltipla, análise selecionada e pesquisa web em lote")
        app.show_page("coverage")
        app.update_idletasks()
        if app.current_page != "coverage":
            raise AssertionError("não foi possível abrir a aba Mapa de aulas")
        print("[OK] Abas Correções Telegram e Mapa de aulas criadas sem erro")
        app.show_page("dashboard")
        app.refresh_adaptive_dashboard()
        app.update_idletasks()
        if app.current_page != "dashboard":
            raise AssertionError("não foi possível abrir o Painel adaptativo")
        print("[OK] Painel adaptativo Mission Control criado e atualizado")
        return 0
    finally:
        if app is not None:
            app.destroy()
        if config_existed:
            CONFIG_PATH.write_bytes(config_bytes)
        else:
            CONFIG_PATH.unlink(missing_ok=True)
        if not db_existed:
            for suffix in ("", "-wal", "-shm"):
                Path(str(DATABASE_PATH) + suffix).unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
