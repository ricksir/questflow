from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def quick_check(db: Path) -> tuple[bool, str]:
    try:
        con = sqlite3.connect(str(db))
        try:
            row = con.execute('PRAGMA quick_check').fetchone()
        finally:
            con.close()
        msg = str(row[0] if row else '')
        return msg.lower() == 'ok', msg
    except Exception as exc:
        return False, str(exc)


def copy_data(src: Path, dst: Path) -> None:
    def ignore(directory: str, names: list[str]):
        ignored = {'backups', '__pycache__'}
        return [n for n in names if n in ignored]

    dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=ignore)


def main() -> int:
    parser = argparse.ArgumentParser(description='Migra dados de uma instalação anterior do QuestFlow para esta pasta.')
    parser.add_argument('old_root', help='Pasta raiz da versão anterior do QuestFlow')
    args = parser.parse_args()

    new_root = Path(__file__).resolve().parent
    old_root = Path(args.old_root).expanduser().resolve()
    old_data = old_root / 'data'
    new_data = new_root / 'data'
    old_db = old_data / 'questflow_questions.sqlite'
    new_version_file = new_root / 'VERSION.txt'

    if old_root == new_root:
        print('[ERRO] A pasta anterior não pode ser a mesma pasta da nova versão.')
        return 2
    if not old_data.is_dir() or not old_db.is_file():
        print('[ERRO] Não encontrei data\\questflow_questions.sqlite na pasta anterior.')
        print(f'       Pasta informada: {old_root}')
        return 3
    if not new_version_file.is_file():
        print('[ERRO] Esta ferramenta precisa ser executada dentro da pasta da nova versão do QuestFlow.')
        return 4

    version = new_version_file.read_text(encoding='utf-8').strip()
    print(f'[INFO] Nova versão: {version}')
    print(f'[INFO] Origem dos dados: {old_root}')
    print(f'[INFO] Destino: {new_root}')

    ok, detail = quick_check(old_db)
    if not ok:
        print(f'[ERRO] O banco antigo falhou no PRAGMA quick_check: {detail}')
        return 5
    print('[OK] Banco da versão anterior íntegro.')

    # Backup is intentionally a sibling of the new installation, not nested in
    # data/backups. This avoids recursive copies and Windows path issues.
    backup_root = new_root.parent / f'QuestFlow_DATA_BACKUP_{stamp()}'
    backup_data = backup_root / 'data'
    try:
        copy_data(old_data, backup_data)
    except OSError as exc:
        # Fallback to a short, writable location if the current extraction path
        # is problematic on Windows.
        base = Path(os.environ.get('LOCALAPPDATA') or os.environ.get('TEMP') or str(new_root.parent))
        backup_root = base / 'QuestFlow' / f'DATA_BACKUP_{stamp()}'
        backup_data = backup_root / 'data'
        copy_data(old_data, backup_data)
    print(f'[OK] Backup criado em: {backup_root}')

    backup_db = backup_data / 'questflow_questions.sqlite'
    ok, detail = quick_check(backup_db)
    if not ok:
        print(f'[ERRO] O backup foi criado, mas o SQLite falhou na validação: {detail}')
        return 6
    print('[OK] Backup validado.')

    # Preserve the new package's files, but overlay all user data/settings from
    # the previous installation. Existing package-only files remain available.
    copy_data(old_data, new_data)

    migrated_db = new_data / 'questflow_questions.sqlite'
    ok, detail = quick_check(migrated_db)
    if not ok:
        print(f'[ERRO] O banco migrado falhou na validação: {detail}')
        print('[INFO] A versão antiga permanece intacta e o backup está disponível acima.')
        return 7

    marker = {
        'schema': 'questflow.manual-migration.v1',
        'migrated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
        'from': str(old_root),
        'to': str(new_root),
        'target_version': version,
        'backup': str(backup_root),
    }
    (new_data / 'migration_last.json').write_text(json.dumps(marker, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print('[OK] Dados migrados com sucesso.')
    print('[OK] A pasta antiga NÃO foi alterada e pode ser usada como rollback.')
    print('')
    print('Próximo passo: execute INICIAR_QUESTFLOW_STUDIO.bat nesta pasta nova.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
