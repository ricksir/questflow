from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from core.production_hardening import create_backup, test_restore as validate_restore, verify_backup


class UpdateTransientCacheHotfix6100Tests(unittest.TestCase):
    def test_chrome_runtime_and_browser_profile_are_not_backed_up(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / 'data'
            data.mkdir()
            db = data / 'questflow_questions.sqlite'
            with closing(sqlite3.connect(db)) as conn:
                conn.execute('create table q(id integer primary key, text varchar)')
                conn.execute("insert into q(text) values ('preserve')")
                conn.commit()

            transient = data / 'chrome_runtime_5_4_0' / 'Default'
            transient.mkdir(parents=True)
            with closing(sqlite3.connect(transient / 'declarative_performance_observer.db')) as conn:
                conn.execute('create table cache(x integer)')
                conn.commit()
            profile = data / 'google_browser_profile'
            profile.mkdir()
            (profile / 'Lockfile').write_text('runtime-only', encoding='utf-8')
            (data / 'config.json').write_text('{"ok": true}', encoding='utf-8')

            result = create_backup(data_dir=data, backup_root=root / 'backups', label='transient-filter')
            manifest = json.loads((Path(result.path) / 'manifest.json').read_text(encoding='utf-8'))
            paths = {item['path'] for item in manifest['files']}
            self.assertIn('questflow_questions.sqlite', paths)
            self.assertIn('config.json', paths)
            self.assertFalse(any(path.startswith('chrome_runtime_') for path in paths))
            self.assertFalse(any(path.startswith('google_browser_profile/') for path in paths))
            self.assertTrue(verify_backup(result.path)['ok'])
            restored = validate_restore(result.path)
            self.assertTrue(restored['ok'], restored)


if __name__ == '__main__':
    unittest.main()
