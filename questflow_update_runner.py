from __future__ import annotations

import argparse
import gc
import json
import shutil
import sqlite3
import stat
import sys
import tempfile
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description='QuestFlow external safe-update runner')
    parser.add_argument('--package', required=True)
    parser.add_argument('--install-root', required=True)
    args = parser.parse_args()

    install_root = Path(args.install_root).resolve()
    sys.path.insert(0, str(install_root))

    from core import production_hardening as ph  # type: ignore

    # The installed Mobile source can contain a nested .git whose object files
    # are read-only. Patch the old installed hardening module in memory before
    # it snapshots, replaces or rolls back the application tree.
    original_rmtree = shutil.rmtree

    def rmtree_writable(path, ignore_errors=False, *args, **kwargs):
        def make_writable_and_retry(function, filename, _exc_info):
            try:
                Path(filename).chmod(stat.S_IREAD | stat.S_IWRITE)
                function(filename)
            except FileNotFoundError:
                return
            except Exception:
                if not ignore_errors:
                    raise

        kwargs.pop('onerror', None)
        kwargs.pop('onexc', None)
        return original_rmtree(path, ignore_errors=ignore_errors, onerror=make_writable_and_retry, *args, **kwargs)

    ph.shutil.rmtree = rmtree_writable

    # --- Windows-safe SQLite helpers -------------------------------------------------
    # Older installed releases used sqlite3.Connection as a context manager. That
    # commits/rolls back but does NOT close the handle. Windows then keeps files in the
    # restore-test directory locked and TemporaryDirectory cleanup can fail with
    # WinError 32 even when the backup itself is valid.
    def sqlite_quick_check_closed(path):
        target = Path(path)
        if not target.exists():
            return {'path': str(target), 'ok': False, 'detail': 'arquivo ausente'}
        connection = None
        try:
            uri = target.resolve().as_uri() + '?mode=ro'
            connection = sqlite3.connect(uri, uri=True, timeout=15)
            row = connection.execute('PRAGMA quick_check(1)').fetchone()
            result = str(row[0] if row else 'sem resultado')
            fk = connection.execute('PRAGMA foreign_key_check').fetchall()
            return {
                'path': str(target),
                'ok': result.lower() == 'ok' and not fk,
                'detail': result,
                'foreign_key_violations': len(fk),
            }
        except Exception as error:
            return {'path': str(target), 'ok': False, 'detail': str(error), 'foreign_key_violations': -1}
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

    def backup_sqlite_closed(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        src = None
        dst = None
        try:
            src = sqlite3.connect(source, timeout=30)
            dst = sqlite3.connect(destination, timeout=30)
            src.execute('PRAGMA busy_timeout=30000')
            src.backup(dst)
            dst.commit()
        finally:
            if dst is not None:
                try:
                    dst.close()
                except Exception:
                    pass
            if src is not None:
                try:
                    src.close()
                except Exception:
                    pass

    original_candidates = ph._backup_candidates

    def persistent_candidates(data_dir: Path):
        root = Path(data_dir).resolve()
        filtered = []
        for candidate in original_candidates(root):
            try:
                rel = Path(candidate).resolve().relative_to(root)
            except Exception:
                continue
            parts = tuple(part.lower() for part in rel.parts)
            if any(part.startswith(('chrome_runtime_', 'browser_runtime_')) for part in parts):
                continue
            if parts and parts[0] in {'google_browser_profile', 'runtime', 'tmp', 'temp', 'logs', 'backups'}:
                continue
            filtered.append(Path(candidate))
        return filtered

    def robust_test_restore(backup_dir):
        temp_root = Path(tempfile.mkdtemp(prefix='qf-restore-test-'))
        try:
            result = ph.restore_backup(backup_dir, temp_root / 'data')
            return {**result, 'tested_at': ph.utc_now(), 'temporary': True}
        finally:
            gc.collect()
            for attempt in range(6):
                try:
                    shutil.rmtree(temp_root)
                    break
                except FileNotFoundError:
                    break
                except PermissionError:
                    # Antivirus/indexing/SQLite teardown on Windows may hold a just-
                    # closed file very briefly. The restore validation result is still
                    # valid; retry cleanup instead of rolling back a healthy update.
                    if attempt == 5:
                        break
                    time.sleep(0.25 * (attempt + 1))

    # Patch the currently installed release in memory. /data is never edited here.
    ph.sqlite_quick_check = sqlite_quick_check_closed
    ph._backup_sqlite = backup_sqlite_closed
    ph._backup_candidates = persistent_candidates
    ph.test_restore = robust_test_restore

    result = ph.safe_apply_update(args.package, install_root=install_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
