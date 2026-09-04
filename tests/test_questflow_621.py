import json
import os
import re
import stat
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.exam_projects import ExamProjectService
from core.mobile_foundation import MobileFoundationService
from core.production_hardening import _remove_tree, _snapshot_application
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_release_versions_and_mobile_payload_policy():
    assert read("VERSION.txt").strip() == "6.23.2"
    assert 'version = "6.23.2"' in read("pyproject.toml")
    package = json.loads(read("mobile/package.json"))
    app = json.loads(read("mobile/app.json"))
    manifest = json.loads(read("MANIFEST_UPDATE_6.23.2.json"))
    assert package["version"] == "0.15.6"
    assert app["expo"]["version"] == "0.15.6"
    assert app["expo"]["android"]["versionCode"] == 21
    assert package["dependencies"]["react-native-svg"]
    assert manifest["mobile_changed"] is False
    assert "mobile" not in manifest["preserves"]
    assert "mobile" not in manifest["excludes"]


def test_mobile_studio_source_version_tracks_the_current_mobile_release():
    enhancement = read("web/questflow621.js")
    release = read("web/questflow622.js")
    assert '<strong data-mobile-source-version>${sourceVersion}</strong>' in enhancement
    assert "const MOBILE_RELEASE = '0.15.6'" in release
    assert "node.textContent = MOBILE_RELEASE" in release


def test_all_studio_routes_use_the_621_layout_layer():
    html = read("web/index.html")
    css = read("web/questflow621.css")
    script = read("web/questflow621.js")
    assert len(re.findall(r'<section class="page(?: [^"]*)?" data-page="', html)) == 15
    assert "questflow621.css" in html
    assert "questflow621.js" in html
    for route in (
        "dashboard", "visualanalytics", "examproject", "import", "curation", "review",
        "bankfix", "tutor", "recommend", "stage5", "corrections", "coverage",
        "flow", "mobile", "settings",
    ):
        assert f"{route}:" in script
    for selector in (
        'data-page="dashboard"', 'data-page="curation"', 'page--tutor',
        'page--recommend', 'page--stage5', 'data-page="flow"',
    ):
        assert selector in css
    assert ".panel--wide" in css
    assert "grid-template-areas" in css
    assert "questflow622.css" in html
    assert "questflow622.js" in html
    visual_css = read("web/questflow622.css")
    visual_js = read("web/questflow622.js")
    assert "editorial dark canvas" in visual_css
    assert "editorial-bento" in visual_js


def test_analytics_v2_contract_and_bridge_are_declared():
    foundation = read("core/mobile_foundation.py")
    server = read("web_server.py")
    api = read("web_api.py")
    mobile_types = read("mobile/src/lib/types.ts")
    mobile_api = read("mobile/src/lib/api.ts")
    for key in (
        "summary", "timeline", "subjects", "priority_breakdown", "projection_band",
        "review_queue", "sample_size", "generated_at", "source_freshness",
    ):
        assert f'"{key}"' in foundation or f"{key}:" in mobile_types
    assert "/api/v1/mobile/analytics" in foundation
    assert "get_learning_analytics_v2" in api
    assert '"get_learning_analytics_v2"' in server
    assert "AnalyticsSnapshotV2" in mobile_types
    assert "analytics:" in mobile_api


def test_new_panels_use_delegated_events_and_accessible_chart_fallbacks():
    script = read("web/questflow621.js")
    mobile_chart = read("mobile/src/components/analytics.tsx")
    for event in (
        "questflow:filter-change", "questflow:data-refreshed",
        "questflow:panel-state", "questflow:action-complete",
    ):
        assert event in script
    assert "data-action" in script
    assert "replaceChildren" in script
    assert "histórico ainda vazio" in mobile_chart.lower()
    assert "accessibilityLabel" in mobile_chart
    assert "Svg" in mobile_chart


def test_raw_history_renders_from_the_first_real_response():
    studio = read("web/questflow621.js")
    mobile = read("mobile/src/components/analytics.tsx")
    css = read("web/questflow622.css")
    assert "observed.length === 1" in studio
    assert "Percurso completo" in studio
    assert "Desde a primeira resposta" in mobile
    assert "raw-dot" in css
    assert "n=${" not in studio
    assert "confiança baixa" not in mobile


def test_dead_space_routes_have_explicit_companion_rails():
    studio = read("web/questflow621.js")
    css = read("web/questflow621.css")
    for marker in ("qf621-flow-insights", "qf621-stage5-evidence", "qf621-settings-rail"):
        assert marker in studio
        assert marker in css
    assert 'grid-template-areas: "service config" "fsrs telegram" "history insights"' in css
    assert 'grid-template-areas: "generator draft" "generator evidence" "legislation legislation" "gold gold"' in css
    assert ".qf621-stage5-evidence { grid-area: evidence; position: static" in css


def test_empty_analytics_snapshot_is_honest_and_bounded():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        database = QuestFlowDatabase(root / "analytics.sqlite")
        study = StudyRepository(database)
        ExamProjectService(database)
        service = MobileFoundationService(
            database,
            study,
            control_plane_path=root / "mobile-control.sqlite",
        )
        snapshot = service.analytics_projection(range_value="12w", grain="week")
        assert snapshot["contract"] == "questflow.analytics.v2"
        assert snapshot["sample_size"] == 0
        assert snapshot["summary"]["accuracy"] is None
        assert snapshot["projection_band"]["low"] is None
        assert snapshot["source_freshness"]["retention_history"] == "not_collected"
        assert 12 <= len(snapshot["timeline"]) <= 14


def test_full_history_attempt_grain_uses_every_real_answer_from_the_start():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        database = QuestFlowDatabase(root / "analytics.sqlite")
        study = StudyRepository(database)
        ExamProjectService(database)
        uid = database.create_manual_question(None)
        question = database.get_question(uid)
        assert question
        question.update({
            "materia": "AUDITORIA", "assunto": "Histórico bruto", "enunciado": "Teste",
            "alternativas": [{"chave": "A", "texto": "A"}, {"chave": "B", "texto": "B"}],
            "gabarito": "A", "revisao": {"status": "aprovado"},
        })
        database.update_question(uid, question)
        study.sync_questions()
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with database.connect() as connection:
            for index, correct in enumerate((1, 0, 1), start=1):
                delivery_id = str(uuid.uuid4())
                attempt_id = str(uuid.uuid4())
                answered = (start + timedelta(days=index)).isoformat()
                connection.execute(
                    "INSERT INTO telegram_deliveries(id,cycle_id,question_uid,poll_id,chat_id,sent_at,status) VALUES(?,?,?,?,?,?,?)",
                    (delivery_id, "raw-history", uid, f"poll-{index}", "1", answered, "respondido"),
                )
                connection.execute(
                    "INSERT INTO telegram_attempts(id,delivery_id,question_uid,poll_id,user_id,selected_indices_json,is_correct,answered_at,response_seconds,timing_quality) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (attempt_id, delivery_id, uid, f"poll-{index}", "1", "[0]", correct, answered, 20, "valid"),
                )
        service = MobileFoundationService(database, study, control_plane_path=root / "mobile-control.sqlite")
        snapshot = service.analytics_projection(range_value="all", grain="attempt")
        assert snapshot["range"] == "all"
        assert snapshot["grain"] == "attempt"
        assert snapshot["sample_size"] == 3
        assert [point["accuracy"] for point in snapshot["timeline"]] == [1.0, 0.0, 1.0]
        assert [point["cumulative_accuracy"] for point in snapshot["timeline"]] == [1.0, 0.5, 0.6667]


def test_safe_update_removes_readonly_nested_git_and_excludes_it_from_snapshot():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        installed = root / "installed"
        mobile = installed / "mobile"
        git_object = mobile / ".git" / "objects" / "08" / "object"
        git_object.parent.mkdir(parents=True)
        git_object.write_bytes(b"readonly")
        os.chmod(git_object, stat.S_IREAD)
        (mobile / "package.json").write_text("{}", encoding="utf-8")

        snapshot = root / "snapshot"
        _snapshot_application(installed, snapshot)
        assert (snapshot / "mobile" / "package.json").exists()
        assert not (snapshot / "mobile" / ".git").exists()

        _remove_tree(mobile)
        assert not mobile.exists()
