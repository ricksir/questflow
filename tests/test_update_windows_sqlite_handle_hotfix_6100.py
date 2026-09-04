from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from core.production_hardening import create_backup, test_restore as restore_self_test, verify_backup


class WindowsSqliteHandleHotfixTests(unittest.TestCase):
    def test_restore_self_test_with_multiple_sqlite_databases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / 'data'
            data.mkdir()
            for name in ('questflow_questions.sqlite', 'mobile_control_plane.sqlite'):
                with closing(sqlite3.connect(data / name)) as conn:
                    conn.execute('create table sample(id integer primary key, value text)')
                    conn.execute('insert into sample(value) values (?)', (name,))
                    conn.commit()
            backup = create_backup(data_dir=data, backup_root=root / 'backups', label='sqlite-close')
            self.assertTrue(backup.quick_check_ok)
            self.assertEqual(backup.databases, 2)
            self.assertTrue(verify_backup(backup.path)['ok'])
            restored = restore_self_test(backup.path)
            self.assertTrue(restored['ok'])
            self.assertEqual(len(restored['sqlite_checks']), 2)

    def test_external_runner_contains_windows_handle_patch(self) -> None:
        runner = Path(__file__).resolve().parents[1] / 'questflow_update_runner.py'
        text = runner.read_text(encoding='utf-8')
        self.assertIn('connection.close()', text)
        self.assertIn('ph.test_restore = robust_test_restore', text)
        self.assertIn('ph._backup_sqlite = backup_sqlite_closed', text)


if __name__ == '__main__':
    unittest.main()
