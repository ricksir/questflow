from __future__ import annotations

import hashlib
import tempfile
import time
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from core.storage import QuestFlowDatabase
from core.study import SelectionFilters, StudyRepository


def question(index: int) -> dict:
    code = f"BENCH-{index:05d}"
    subject = f"MATÉRIA {index % 25:02d}"
    lesson = f"Aula {index % 20:02d}"
    statement = f"Questão sintética número {index} para teste de desempenho."
    return {
        "id": code,
        "codigo_origem": code,
        "fingerprint": hashlib.sha256(code.encode()).hexdigest(),
        "materia": subject,
        "aula_planilha": lesson,
        "assunto": f"Assunto {index % 80}",
        "assuntos": [f"Assunto {index % 80}"],
        "banca": "BENCH",
        "ano": 2026,
        "orgao": "TESTE",
        "tipo": "multipla_escolha",
        "enunciado": statement,
        "alternativas": [
            {"chave": "A", "texto": "Alternativa A"},
            {"chave": "B", "texto": "Alternativa B"},
        ],
        "gabarito": "A",
        "revisao": {"status": "aprovado", "confianca": 1.0, "alertas": []},
        "fonte": {"arquivo": "benchmark.pdf", "codigo": code},
    }


def main() -> int:
    count = 5000
    with tempfile.TemporaryDirectory() as folder:
        db = QuestFlowDatabase(Path(folder) / "benchmark.sqlite")
        started = time.perf_counter()
        result = db.import_extraction({"source_file": "benchmark.pdf", "questions": [question(i) for i in range(count)]})
        import_seconds = time.perf_counter() - started
        study = StudyRepository(db)
        started = time.perf_counter()
        selected = study.select_questions(
            SelectionFilters(subjects=[], approved_only=True, strategy="adaptativo"),
            20,
        )
        selection_seconds = time.perf_counter() - started
        started = time.perf_counter()
        dashboard = study.adaptive_dashboard()
        dashboard_seconds = time.perf_counter() - started
        print(f"Questões importadas: {result['inserted']}")
        print(f"Importação: {import_seconds:.3f}s")
        print(f"Seleção adaptativa de 20/5000: {selection_seconds:.3f}s")
        print(f"Painel agregado: {dashboard_seconds:.3f}s")
        print(f"Matérias no painel: {len(dashboard['subjects'])}")
        print(f"Questões selecionadas: {len(selected)}")
        if len(selected) != 20:
            raise AssertionError("seleção não retornou 20 questões")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
