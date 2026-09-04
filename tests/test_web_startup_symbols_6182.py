from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')


def test_startup_trail_guide_symbols_are_defined():
    # These symbols are referenced during bindEvents()/startup. If one is removed,
    # the Web UI crashes before bridge.startHeartbeat(), making the desktop runtime
    # report "interface não respondeu" even though the shell HTML is visible.
    required = [
        'trailLabel',
        'renderTrailGuideStatus',
        'notifyMissingTrailGuides',
        'addTrailGuidePdfs',
        'checkStudyGuideWatch',
        'startStudyGuideWatch',
    ]
    for name in required:
        assert re.search(rf'\b(?:async\s+)?function\s+{re.escape(name)}\s*\(', APP_JS), f'{name} is referenced but not defined'


def test_bind_events_reference_has_matching_definition():
    assert "$('#addTrailGuide')?.addEventListener('click', addTrailGuidePdfs);" in APP_JS
    assert 'function addTrailGuidePdfs' in APP_JS or 'async function addTrailGuidePdfs' in APP_JS


def test_startup_watch_reference_has_matching_definition():
    assert 'startStudyGuideWatch();' in APP_JS
    assert 'function startStudyGuideWatch()' in APP_JS
