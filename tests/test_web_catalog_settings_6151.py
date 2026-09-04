from __future__ import annotations

import json
from pathlib import Path

from core.spreadsheet_taxonomy import SpreadsheetTaxonomy
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from web_api import QuestFlowWebApi
from web_server import ALLOWED_API_METHODS


def _task(trail: int, task_no: str, lesson: str, subject: str, title: str, *, studied: bool = False) -> dict:
    return {
        "row": 2,
        "trilha": f"TRILHA {trail:02d}",
        "tarefa": task_no,
        "data": "20/08/2026" if studied else "",
        "materia": subject,
        "aula": lesson,
        "tipo": "teoria",
        "descricao": title,
        "segmentos": [],
        "ch_planejada_min": 60,
        "ch_planejada": "01:00",
        "ch_efetiva_min": 45 if studied else 0,
        "ch_efetiva": "00:45" if studied else "",
        "questoes_feitas": 20 if studied else 0,
        "acertos": 16 if studied else 0,
        "desempenho": 80.0 if studied else 0.0,
        "meta_questoes": 20,
        "meta_origem": "descricao",
        "estudado": studied,
        "evidencias_estudo": ["data"] if studied else [],
    }


def _payload(tasks: list[dict], url: str, title: str) -> dict:
    return {
        "schema": "questflow.taxonomy.v1",
        "schema_version": 1,
        "generated_at": "2026-08-20T15:00:00+00:00",
        "source": {"title": title, "spreadsheet_id": title, "url": url},
        "materias": sorted({item["materia"] for item in tasks}),
        "aliases": {},
        "regras_manuais": {},
        "tarefas_referencia": tasks,
        "spreadsheet_logic": {"mapa_sheet": "MAPA_AF", "ciclo_sheet": "CICLO_REG"},
    }


def _api(tmp_path: Path, current: dict) -> QuestFlowWebApi:
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    db_path = data / "questflow_questions.sqlite"
    taxonomy_path = data / "taxonomia_afrfb.json"
    config_path = data / "config.json"
    taxonomy_path.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
    config = {"taxonomy_spreadsheet_url": current["source"]["url"]}
    config_path.write_text(json.dumps(config), encoding="utf-8")
    api = QuestFlowWebApi(db_path, config=config, config_path=config_path, taxonomy_path=taxonomy_path)
    api.database = QuestFlowDatabase(db_path)
    api.taxonomy = SpreadsheetTaxonomy(current, taxonomy_path)
    api.study = StudyRepository(api.database)
    api._core_started = True
    api._core_ready.set()
    return api


def test_web_settings_exposes_course_catalog_controls() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    js = (root / "web" / "app.js").read_text(encoding="utf-8")
    assert "Estudos e Trilhas" in html
    assert 'id="courseCatalogUrl"' in html
    assert 'id="testCourseCatalog"' in html
    assert 'id="updateCourseCatalog"' in html
    assert "preflight_course_catalog" in js
    assert "apply_course_catalog" in js
    assert "Campos vazios da nova planilha NÃO apagarão" in js


def test_web_server_allows_catalog_preflight_and_apply() -> None:
    assert {"get_course_catalog_settings", "preflight_course_catalog", "apply_course_catalog"} <= ALLOWED_API_METHODS


def test_web_api_preflight_is_read_only_and_apply_preserves_progress(tmp_path: Path, monkeypatch) -> None:
    old = _payload([_task(0, "1", "Aula 01", "TRIBUTÁRIO", "Crédito", studied=True)], "old-url", "Antiga")
    new = _payload([
        _task(0, "1", "Aula 01", "TRIBUTÁRIO", "Crédito atualizado"),
        _task(19, "1", "Aula 01", "TI", "Redes novas"),
    ], "new-url", "Nova")
    api = _api(tmp_path, old)
    before_config = api.config_path.read_bytes()
    before_taxonomy = api.taxonomy_path.read_bytes()

    def fake_download(_url, target):
        path = Path(target)
        path.write_bytes(b"xlsx")
        return path

    monkeypatch.setattr("core.spreadsheet_taxonomy.download_public_spreadsheet", fake_download)
    monkeypatch.setattr("core.spreadsheet_taxonomy.build_taxonomy_from_xlsx", lambda _path, source_url="": new)

    status = api.get_course_catalog_settings()
    assert status["ok"] is True
    assert status["trail_range"] == "Trilhas 00 a 00"
    assert status["sheets"] == ["MAPA_AF", "CICLO_REG"]

    dry = api.preflight_course_catalog("new-url")
    assert dry["ok"] is True
    assert dry["preflight"]["counts"]["new"] == 1
    assert api.config_path.read_bytes() == before_config
    assert api.taxonomy_path.read_bytes() == before_taxonomy

    merged = api.apply_course_catalog("new-url", {})
    assert merged["ok"] is True
    assert merged["summary"]["personal_fields_overwritten_by_blank"] == 0
    first = api.taxonomy.tasks[0]
    assert first["estudado"] is True
    assert first["ch_efetiva_min"] == 45
    assert api.taxonomy.tasks[1]["estudado"] is False
    assert api.config["taxonomy_spreadsheet_url"] == "new-url"
