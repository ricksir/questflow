from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_feedback_returns_in_same_sync_round_trip():
    server = read("core/mobile_foundation.py")
    api = read("mobile/src/lib/api.ts")
    sync = read("mobile/src/lib/sync.ts")
    questions = read("mobile/app/(tabs)/questions.tsx")
    assert 'feedback_attempt_id = str(body.get("feedback_attempt_id")' in server
    assert '"feedback": feedback' in server
    assert "refreshOfflinePack: false" in sync
    assert "feedbackAttemptId: attemptId" in sync
    assert "await runAnswerSync(" in questions
    assert "syncNow().catch(() => undefined)" in questions
    assert "feedback_attempt_id: options.feedbackAttemptId" in api


def test_question_actions_have_the_requested_vertical_order():
    questions = read("mobile/app/(tabs)/questions.tsx")
    labels = [
        'title="Continuar"',
        'title="Pular Questão"',
        'title="Assunto ainda não Estudado"',
        'title="CORRIGIR QUESTÃO"',
    ]
    positions = [questions.index(label) for label in labels]
    assert positions == sorted(positions)


def test_analytics_summary_wraps_and_explains_the_delta():
    analytics = read("mobile/src/components/analytics.tsx")
    assert "flexWrap: 'wrap'" in analytics
    assert "p.p. desde o início" in analytics
    assert "sampleValueBox" in analytics


def test_no_active_studio_copy_mentions_mobile_014():
    app = read("web/app.js")
    enhancement = read("web/questflow621.js")
    html = read("web/index.html")
    assert "Mobile 0.14.0" not in app
    assert "build 0.14" not in enhancement
    assert "currentMobileRelease()" in app
    assert "app.js?v=6.23.2" in html
