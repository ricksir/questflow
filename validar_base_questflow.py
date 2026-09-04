from __future__ import annotations

import json
import sys
from pathlib import Path
from tkinter import Tk, filedialog, messagebox

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
from core.exporter import validate_questflow_question_bank  # noqa: E402


def main() -> int:
    root = Tk(); root.withdraw(); root.update()
    path = filedialog.askopenfilename(
        title="Selecione a base JSON do QuestFlow",
        filetypes=[("Base QuestFlow JSON", "*.json"), ("Todos os arquivos", "*.*")],
    )
    if not path:
        return 0
    try:
        raw = Path(path).read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise ValueError("O arquivo possui BOM UTF-8. Gere novamente pelo Importer 1.2.0.")
        payload = json.loads(raw.decode("utf-8"))
        errors = validate_questflow_question_bank(payload)
        if errors:
            raise ValueError("Base incompatível:\n- " + "\n- ".join(errors[:30]))
    except Exception as error:
        messagebox.showerror("Validador QuestFlow", str(error))
        return 1
    messagebox.showinfo(
        "Validador QuestFlow",
        f"Base compatível com o formato questflow-question-bank.\n\nQuestões: {payload['question_count']}\nArquivo: {path}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
