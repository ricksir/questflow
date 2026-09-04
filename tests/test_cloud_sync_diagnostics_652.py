from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from core.cloud_sync import CloudSyncEngine
from web_server import ALLOWED_API_METHODS


class _Remote:
    def __init__(self) -> None:
        self.events = []
        self.generation = 1

    def ensure_schema(self):
        return None

    def get_generation(self):
        return self.generation

    def set_generation(self, value):
        self.generation = int(value)

    def touch_device(self, *_args):
        return None

    def fetch_events(self, *_args, **_kwargs):
        return []

    def append_events(self, events):
        self.events.extend(list(events))
        return len(events)


class CloudSyncDiagnostics652Tests(unittest.TestCase):
    def _engine(self, root: Path, remote=None) -> CloudSyncEngine:
        db = root / 'db.sqlite'
        with closing(sqlite3.connect(db)) as con:
            con.execute('CREATE TABLE questions(uid TEXT PRIMARY KEY,codigo_origem TEXT,materia TEXT,aula_planilha TEXT)')
            con.execute("INSERT INTO questions VALUES('u1','Q1','TRIBUTÁRIO','Aula 01')")
            con.commit()
        return CloudSyncEngine(
            db,
            config={'cloud_sync_enabled': True, 'cloud_device_name': 'TESTE'},
            config_path=root / 'config.json',
            remote_client=remote or _Remote(),
            auth_token='x',
        )

    def test_pending_details_identify_exact_local_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engine = self._engine(root)
            with closing(sqlite3.connect(engine.database_path)) as con:
                con.execute("UPDATE questions SET materia='AUDITORIA' WHERE uid='u1'")
                con.commit()
            queue = engine.pending_details()
            self.assertEqual(queue['total'], 1)
            self.assertEqual(queue['groups'][0]['label'], 'Questões')
            self.assertIn('Q1', queue['items'][0]['row'])
            self.assertEqual(queue['items'][0]['operation'], 'upsert')

    def test_legacy_unsupported_event_is_quarantined_not_left_stuck(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engine = self._engine(root)
            with closing(sqlite3.connect(engine.database_path)) as con:
                con.execute(
                    "INSERT INTO qf_sync_outbox(event_id,generation,table_name,row_key,operation,changed_at,attempts,last_error) VALUES(?,?,?,?,?,?,?,?)",
                    ('legacy', 1, 'tabela_antiga_removida', '[\"x\"]', 'upsert', '2026-08-13T10:00:00Z', 0, ''),
                )
                con.commit()
            self.assertEqual(engine.pending_count(), 1)
            repaired = engine.repair_pending_outbox()
            self.assertEqual(repaired['repaired'], 1)
            self.assertEqual(engine.pending_count(), 0)
            queue = engine.pending_details()
            self.assertEqual(queue['deadletter'], 1)

    def test_sync_until_idle_drains_supported_outbox(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remote = _Remote()
            engine = self._engine(root, remote=remote)
            with closing(sqlite3.connect(engine.database_path)) as con:
                con.execute("UPDATE questions SET materia='AUDITORIA' WHERE uid='u1'")
                con.commit()
            result = engine.sync_until_idle()
            self.assertTrue(result['ok'])
            self.assertEqual(result['pending'], 0)
            self.assertEqual(result['pushed'], 1)
            self.assertEqual(len(remote.events), 1)

    def test_pending_diagnostics_are_reachable_over_real_local_http(self):
        import json
        import urllib.request
        from web_server import QuestFlowLocalServer

        class DummyApi:
            def get_cloud_sync_pending(self, limit=60):
                return {"ok": True, "queue": {"total": 2, "groups": [{"label": "Questões", "count": 2}], "items": []}}

        root = Path(__file__).resolve().parents[1]
        server = QuestFlowLocalServer(DummyApi(), root / "web", preferred_port=0)
        server.start()
        try:
            body = json.dumps({"method": "get_cloud_sync_pending", "args": [60]}).encode("utf-8")
            request = urllib.request.Request(
                f"{server.base_url}/api/call", data=body,
                headers={"Content-Type": "application/json", "X-QuestFlow-Token": server.token}, method="POST"
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
            self.assertTrue(result["ok"])
            self.assertEqual(result["result"]["queue"]["total"], 2)
        finally:
            server.stop()

    def test_ui_and_http_allowlist_expose_pending_diagnostics(self):
        root = Path(__file__).resolve().parents[1]
        app_js = (root / 'web' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('get_cloud_sync_pending', ALLOWED_API_METHODS)
        self.assertIn('Alterações locais pendentes', app_js)
        self.assertIn('Último erro de sincronização', app_js)
        self.assertIn('Sincronizar agora', app_js)


if __name__ == '__main__':
    unittest.main()
