from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.course_catalog import CourseCatalogService, stable_lesson_key
from core.cloud_sync import CloudSyncEngine
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


def task(trail: int, task_no: int | str, lesson: str, subject: str, title: str, *, studied=False, minutes=0, questions=0, hits=0, row=1):
    return {
        "row": row,
        "trilha": f"TRILHA {trail:02d}",
        "tarefa": str(task_no),
        "data": "20/08/2026" if studied else "",
        "materia": subject,
        "aula": lesson,
        "tipo": "teoria",
        "descricao": title,
        "segmentos": [],
        "ch_planejada_min": 60,
        "ch_planejada": "01:00",
        "ch_efetiva_min": minutes,
        "ch_efetiva": "01:00" if minutes else "",
        "questoes_feitas": questions,
        "acertos": hits,
        "desempenho": (hits / questions * 100.0) if questions else 0.0,
        "meta_questoes": 20,
        "meta_origem": "descricao",
        "estudado": studied,
        "evidencias_estudo": ["data", "ch_efetiva"] if studied else [],
    }


def payload(tasks, url="https://docs.google.com/spreadsheets/d/TEST/edit"):
    materias = sorted({t["materia"] for t in tasks})
    return {
        "schema": "questflow.taxonomy.v1",
        "schema_version": 1,
        "generated_at": "2026-08-20T12:00:00+00:00",
        "source": {"title": "Planilha teste", "spreadsheet_id": "TEST", "url": url},
        "materias": materias,
        "aliases": {},
        "regras_manuais": {},
        "tarefas_referencia": tasks,
        "spreadsheet_logic": {"mapa_sheet": "MAPA_AF", "ciclo_sheet": "CICLO_REG"},
    }


@pytest.fixture
def env(tmp_path: Path):
    db = QuestFlowDatabase(tmp_path / "data" / "questflow_questions.sqlite")
    taxonomy_path = tmp_path / "data" / "taxonomia_afrfb.json"
    config_path = tmp_path / "data" / "config.json"
    config_path.write_text(json.dumps({"taxonomy_spreadsheet_url": "old-url"}), encoding="utf-8")
    return db, CourseCatalogService(db, taxonomy_path, config_path), taxonomy_path, config_path


def test_a_new_trails_keep_old_progress_when_new_sheet_is_blank(env):
    db, service, _, _ = env
    old = payload([
        task(0, 1, "Aula 01", "TRIBUTÁRIO", "Crédito Tributário", studied=True, minutes=75, questions=30, hits=24),
        task(18, 2, "Aula 02", "CONTABILIDADE", "Balanço", studied=True, minutes=50),
    ], "old-url")
    new = payload([
        task(0, 1, "Aula 01", "TRIBUTÁRIO", "Crédito Tributário"),
        task(18, 2, "Aula 02", "CONTABILIDADE", "Balanço"),
        task(19, 1, "Aula 01", "TI", "Redes"),
        task(27, 1, "Aula 01", "AUDITORIA", "Evidência"),
    ], "new-url")
    result = service.apply(new, old, new_url="new-url")
    merged = result["payload"]["tarefas_referencia"]
    first = merged[0]
    assert first["estudado"] is True
    assert first["ch_efetiva_min"] == 75
    assert first["questoes_feitas"] == 30
    assert first["acertos"] == 24
    assert merged[2]["estudado"] is False
    assert merged[3]["estudado"] is False
    assert result["summary"]["personal_fields_overwritten_by_blank"] == 0


def test_b_title_changes_but_progress_survives(env):
    _, service, _, _ = env
    old = payload([task(12, 3, "Aula 03", "TRIBUTÁRIO", "Crédito Tributário", studied=True, minutes=40)], "old-url")
    new = payload([task(12, 3, "Aula 03", "TRIBUTÁRIO", "Crédito tributário e lançamento")], "new-url")
    pre = service.preflight(new, old)
    assert pre["counts"]["updated"] == 1
    result = service.apply(new, old, new_url="new-url")
    merged = result["payload"]["tarefas_referencia"][0]
    assert merged["descricao"] == "Crédito tributário e lançamento"
    assert merged["estudado"] is True
    assert merged["ch_efetiva_min"] == 40


def test_c_inserted_lesson_is_new_and_not_studied(env):
    _, service, _, _ = env
    old = payload([
        task(7, 1, "Aula 01", "TI", "Um", studied=True, minutes=20),
        task(7, 3, "Aula 03", "TI", "Três", studied=True, minutes=25),
    ], "old-url")
    new = payload([
        task(7, 1, "Aula 01", "TI", "Um"),
        task(7, "2.1", "Aula 02.1", "TI", "Nova aula"),
        task(7, 3, "Aula 03", "TI", "Três"),
    ], "new-url")
    result = service.apply(new, old, new_url="new-url")
    rows = result["payload"]["tarefas_referencia"]
    assert rows[0]["estudado"] is True
    assert rows[1]["estudado"] is False
    assert rows[2]["estudado"] is True
    assert result["summary"]["new"] == 1


def test_d_removed_lesson_is_archived_without_deleting_learner_history(env):
    db, service, _, _ = env
    removed = task(9, 4, "Aula 04", "AUDITORIA", "Antiga", studied=True, minutes=33)
    old = payload([removed, task(9, 5, "Aula 05", "AUDITORIA", "Mantida")], "old-url")
    new = payload([task(9, 5, "Aula 05", "AUDITORIA", "Mantida")], "new-url")
    result = service.apply(new, old, new_url="new-url")
    assert result["summary"]["archived"] == 1
    key = stable_lesson_key(removed)
    with db.connect() as con:
        catalog = con.execute("SELECT active FROM course_catalog_lessons WHERE lesson_key=?", (key,)).fetchone()
        learner = con.execute("SELECT studied,effective_minutes FROM course_learner_state WHERE lesson_key=?", (key,)).fetchone()
    assert int(catalog[0]) == 0
    assert int(learner[0]) == 1 and int(learner[1]) == 33


def test_e_incompatible_payload_does_not_change_source(env):
    _, service, taxonomy_path, config_path = env
    config_before = config_path.read_bytes()
    with pytest.raises(Exception):
        service.apply({"schema": "bad", "tarefas_referencia": None}, {}, new_url="bad-url")
    assert config_path.read_bytes() == config_before
    assert not taxonomy_path.exists()


def test_f_failure_after_database_commit_restores_database_and_source(env, monkeypatch):
    db, service, taxonomy_path, config_path = env
    old = payload([task(1, 1, "Aula 01", "TI", "Antiga", studied=True, minutes=10)], "old-url")
    taxonomy_path.write_text(json.dumps(old), encoding="utf-8")
    before_config = config_path.read_bytes()
    before_taxonomy = taxonomy_path.read_bytes()
    with db.connect() as con:
        before_imports = int(con.execute("SELECT COUNT(*) FROM course_catalog_imports").fetchone()[0])

    def boom(*_a, **_kw):
        raise OSError("simulated taxonomy write failure")

    monkeypatch.setattr("core.course_catalog.save_taxonomy", boom)
    new = payload([task(1, 1, "Aula 01", "TI", "Nova")], "new-url")
    with pytest.raises(OSError):
        service.apply(new, old, new_url="new-url")
    assert taxonomy_path.read_bytes() == before_taxonomy
    assert config_path.read_bytes() == before_config
    with db.connect() as con:
        after_imports = int(con.execute("SELECT COUNT(*) FROM course_catalog_imports").fetchone()[0])
        quick = con.execute("PRAGMA quick_check(1)").fetchone()[0]
    assert after_imports == before_imports
    assert str(quick).lower() == "ok"


def test_g_same_sheet_twice_is_idempotent(env):
    db, service, _, _ = env
    old = payload([task(1, 1, "Aula 01", "TI", "Um", studied=True, minutes=10)], "old-url")
    new = payload([task(1, 1, "Aula 01", "TI", "Um"), task(2, 1, "Aula 01", "AFO", "Dois")], "new-url")
    first = service.apply(new, old, new_url="new-url")
    with db.connect() as con:
        counts_before = (
            int(con.execute("SELECT COUNT(*) FROM course_catalog_lessons").fetchone()[0]),
            int(con.execute("SELECT COUNT(*) FROM course_learner_state").fetchone()[0]),
            int(con.execute("SELECT COUNT(*) FROM course_catalog_imports").fetchone()[0]),
        )
    second = service.apply(new, first["payload"], new_url="new-url")
    with db.connect() as con:
        counts_after = (
            int(con.execute("SELECT COUNT(*) FROM course_catalog_lessons").fetchone()[0]),
            int(con.execute("SELECT COUNT(*) FROM course_learner_state").fetchone()[0]),
            int(con.execute("SELECT COUNT(*) FROM course_catalog_imports").fetchone()[0]),
        )
    assert second["noop"] is True
    assert counts_after == counts_before


def test_g2_equivalent_duration_formats_do_not_recreate_cloud_outbox(env):
    db, service, _, config_path = env
    CloudSyncEngine(
        db.path,
        config={"cloud_sync_enabled": False},
        config_path=config_path,
    )
    sheet = payload([
        task(1, 44, "Aula 01", "FLUÊNCIA EM DADOS", "Banco de dados", studied=True, minutes=90, questions=20, hits=16),
        task(1, 49, "Aula 01", "CONTABILIDADE", "Contabilidade", studied=True, minutes=90, questions=16, hits=10),
    ], "new-url")
    for item in sheet["tarefas_referencia"]:
        item["ch_efetiva"] = "1h30"
    first = service.apply(sheet, {}, new_url="new-url")
    with db.connect() as connection:
        connection.execute("DELETE FROM qf_sync_outbox")
    second = service.apply(sheet, first["payload"], new_url="new-url")
    assert second["noop"] is True
    with db.connect() as connection:
        assert int(connection.execute("SELECT COUNT(*) FROM qf_sync_outbox").fetchone()[0]) == 0
        assert int(connection.execute("SELECT COUNT(*) FROM course_catalog_imports").fetchone()[0]) == 1


def test_g3_progress_change_does_not_requeue_unchanged_catalog(env):
    db, service, _, config_path = env
    CloudSyncEngine(
        db.path,
        config={"cloud_sync_enabled": False},
        config_path=config_path,
    )
    initial = payload([
        task(1, 1, "Aula 01", "TI", "Um"),
        task(1, 2, "Aula 02", "TI", "Dois"),
        task(1, 3, "Aula 03", "TI", "Três"),
    ], "new-url")
    first = service.apply(initial, {}, new_url="new-url")
    with db.connect() as connection:
        connection.execute("DELETE FROM qf_sync_outbox")
    changed = json.loads(json.dumps(first["payload"]))
    changed["tarefas_referencia"][0].update(
        {"estudado": True, "ch_efetiva_min": 30, "ch_efetiva": "30 min", "questoes_feitas": 5, "acertos": 4}
    )
    result = service.apply(changed, first["payload"], new_url="new-url")
    assert result["noop"] is False
    with db.connect() as connection:
        groups = {
            str(row[0]): int(row[1])
            for row in connection.execute(
                "SELECT table_name,COUNT(*) FROM qf_sync_outbox GROUP BY table_name"
            ).fetchall()
        }
    assert groups.get("course_catalog_lessons", 0) == 0
    assert groups.get("course_learner_state", 0) == 1
    assert groups.get("course_catalog_imports", 0) == 1


def test_h_ambiguous_match_blocks_automatic_merge(env):
    _, service, _, _ = env
    old = payload([
        task(9, 4, "Aula 04", "TI", "Parte A", studied=True, minutes=20),
        task(9, 5, "Aula 04", "TI", "Parte B", studied=True, minutes=30),
    ], "old-url")
    new = payload([task(9, "4A", "Aula 04", "TI", "Nova consolidação")], "new-url")
    pre = service.preflight(new, old)
    assert pre["ok"] is False
    assert pre["counts"]["uncertain"] == 1
    with pytest.raises(ValueError):
        service.apply(new, old, new_url="new-url")


def test_i_study_scope_and_learning_tables_survive_catalog_swap(env):
    db, service, _, _ = env
    old = payload([task(3, 1, "Aula 01", "TI", "Redes", studied=True, minutes=60)], "old-url")
    new = payload([task(3, 1, "Aula 01", "TI", "Redes"), task(20, 1, "Aula 01", "TI", "Cloud")], "new-url")
    result = service.apply(new, old, new_url="new-url")
    study = StudyRepository(db)
    scope = study.refresh_studied_scope(result["payload"]["tarefas_referencia"])
    assert scope["groups"] >= 1
    with db.connect() as con:
        studied = con.execute("SELECT COUNT(*) FROM studied_scope").fetchone()[0]
        quick = con.execute("PRAGMA quick_check(1)").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
    assert int(studied) >= 1
    assert str(quick).lower() == "ok"
    assert fk == []


def test_h_manual_resolution_can_preserve_selected_old_progress(env):
    db, service, _, _ = env
    first = task(9, 4, "Aula 04", "TI", "Parte A", studied=True, minutes=20)
    second = task(9, 5, "Aula 04", "TI", "Parte B", studied=True, minutes=30)
    old = payload([first, second], "old-url")
    incoming = task(9, "4A", "Aula 04", "TI", "Nova consolidação")
    new = payload([incoming], "new-url")
    pre = service.preflight(new, old)
    uncertain = next(item for item in pre["diffs"] if item["change_type"] == "uncertain")
    selected_key = stable_lesson_key(second)
    assert selected_key in {candidate["lesson_key"] for candidate in uncertain["candidates"]}
    resolutions = {stable_lesson_key(incoming): {"action": "same", "old_key": selected_key}}
    resolved = service.preflight(new, old, resolutions=resolutions)
    assert resolved["ok"] is True
    assert resolved["counts"]["uncertain"] == 0
    result = service.apply(new, old, new_url="new-url", resolutions=resolutions)
    merged = result["payload"]["tarefas_referencia"][0]
    assert merged["estudado"] is True
    assert merged["ch_efetiva_min"] == 30
    with db.connect() as con:
        assert int(con.execute("SELECT COUNT(*) FROM course_learner_state WHERE studied=1").fetchone()[0]) >= 1
