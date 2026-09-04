from __future__ import annotations

import sys
from pathlib import Path
from tkinter import Tk, filedialog, messagebox

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from core.exporter import convert_legacy_qflow, import_qflow_file, validate_questflow_question_bank  # noqa: E402


def main() -> int:
    root = Tk()
    root.withdraw()
    root.update()
    source = filedialog.askopenfilename(
        title="Selecione a base antiga ou incompatível",
        filetypes=[("Bases QuestFlow", "*.json *.qflow *.qflowpkg"), ("Todos os arquivos", "*.*")],
    )
    if not source:
        return 0
    destination = filedialog.asksaveasfilename(
        title="Salvar base nativa do QuestFlow 0.7.0",
        defaultextension=".json",
        initialfile="QuestFlow-base-de-questoes-COMPATIVEL.json",
        filetypes=[("Base nativa do QuestFlow", "*.json")],
    )
    if not destination:
        return 0
    try:
        output = convert_legacy_qflow(source, destination)
        converted = import_qflow_file(output)
        import json
        payload = json.loads(Path(output).read_text(encoding="utf-8-sig"))
        errors = validate_questflow_question_bank(payload)
        if errors:
            raise ValueError("Falha na validação:\n- " + "\n- ".join(errors[:20]))
    except Exception as error:
        messagebox.showerror("Conversor QuestFlow", str(error))
        return 1
    messagebox.showinfo(
        "Conversor QuestFlow",
        f"Conversão concluída.\n\nQuestões exportadas: {len(converted.get('questions', []))}\nArquivo: {output}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
