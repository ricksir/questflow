from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


def stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def quick_check(db: Path) -> tuple[bool, str]:
    try:
        con = sqlite3.connect(str(db), timeout=8)
        try:
            row = con.execute('PRAGMA quick_check').fetchone()
        finally:
            con.close()
        msg = str(row[0] if row else '')
        return msg.lower() == 'ok', msg
    except Exception as exc:
        return False, str(exc)


def table_count(db: Path, table: str) -> int | None:
    try:
        con = sqlite3.connect(str(db), timeout=8)
        try:
            exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if not exists:
                return None
            return int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] or 0)
        finally:
            con.close()
    except Exception:
        return None


def find_data_prefix(zf: zipfile.ZipFile) -> str:
    candidates = []
    for name in zf.namelist():
        normalized = name.replace('\\', '/')
        if normalized.endswith('/questflow_questions.sqlite'):
            prefix = normalized[: -len('questflow_questions.sqlite')]
            if prefix.endswith('/'):
                candidates.append(prefix)
    if not candidates:
        raise RuntimeError('O ZIP não contém questflow_questions.sqlite.')
    # Prefer a literal data/ folder, then the shallowest candidate.
    candidates.sort(key=lambda p: (0 if p.rstrip('/').endswith('data') else 1, p.count('/'), len(p)))
    return candidates[0]


SKIP_TOP_DIRS = {
    'backups', '__pycache__', 'pip_cache', 'diagnostico_archive', 'diagnostico_architecture',
    'chrome_runtime_5_4_0', 'google_browser_profile',
}
SKIP_TOP_FILES = {
    'questflow_instance.lock', 'last_clean_shutdown.json', 'runtime_watchdog.jsonl',
    'startup_performance.log', 'dashboard_cache.json', 'migration_last.json',
}


def safe_rel(name: str, prefix: str) -> PurePosixPath | None:
    normalized = name.replace('\\', '/')
    if not normalized.startswith(prefix):
        return None
    rel = normalized[len(prefix):].lstrip('/')
    if not rel:
        return None
    p = PurePosixPath(rel)
    if p.is_absolute() or '..' in p.parts:
        return None
    return p


def extract_durable_data(zf: zipfile.ZipFile, prefix: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for info in zf.infolist():
        rel = safe_rel(info.filename, prefix)
        if rel is None:
            continue
        top = rel.parts[0]
        if top in SKIP_TOP_DIRS or (len(rel.parts) == 1 and top in SKIP_TOP_FILES):
            continue
        target = destination.joinpath(*rel.parts)
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info, 'r') as src, target.open('wb') as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)


def load_config(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description='Recupera a pasta data do QuestFlow a partir de um ZIP validado.')
    parser.add_argument('source_zip')
    parser.add_argument('--target-root', default=str(Path.home() / 'QuestFlow'))
    args = parser.parse_args()

    source_zip = Path(args.source_zip).expanduser().resolve()
    target_root = Path(args.target_root).expanduser().resolve()
    target_data = target_root / 'data'
    target_db = target_data / 'questflow_questions.sqlite'

    if not source_zip.is_file():
        print(f'[ERRO] ZIP não encontrado: {source_zip}')
        return 2
    if not target_root.is_dir() or not (target_root / 'app.py').is_file():
        print(f'[ERRO] Não encontrei uma instalação válida em: {target_root}')
        return 3

    print('[INFO] Analisando o ZIP de dados antes de alterar a instalação...')
    with tempfile.TemporaryDirectory(prefix='QuestFlowRecovery_') as td:
        stage = Path(td)
        restored = stage / 'data'
        try:
            with zipfile.ZipFile(source_zip, 'r') as zf:
                bad = zf.testzip()
                if bad:
                    print(f'[ERRO] O ZIP falhou na verificação CRC: {bad}')
                    return 4
                prefix = find_data_prefix(zf)
                extract_durable_data(zf, prefix, restored)
        except zipfile.BadZipFile as exc:
            print(f'[ERRO] ZIP inválido: {exc}')
            return 4

        staged_db = restored / 'questflow_questions.sqlite'
        if not staged_db.is_file():
            print('[ERRO] O banco não foi extraído do ZIP.')
            return 5
        ok, detail = quick_check(staged_db)
        if not ok:
            print(f'[ERRO] O SQLite do ZIP falhou no quick_check: {detail}')
            return 6

        counts = {name: table_count(staged_db, name) for name in (
            'questions', 'imports', 'study_state', 'studied_scope', 'telegram_attempts',
            'qf_learning_events', 'qf_mobile_devices', 'qf_mobile_sessions', 'qf_exam_projects'
        )}
        config = load_config(restored / 'config.json')
        print('[OK] Backup de dados íntegro.')
        print(f"[INFO] Questões encontradas: {counts.get('questions') if counts.get('questions') is not None else '—'}")
        print(f"[INFO] Importações: {counts.get('imports') if counts.get('imports') is not None else '—'}")
        print(f"[INFO] Registros de conteúdo estudado: {counts.get('studied_scope') if counts.get('studied_scope') is not None else '—'}")
        print(f"[INFO] Eventos de aprendizagem: {counts.get('qf_learning_events') if counts.get('qf_learning_events') is not None else '—'}")
        print(f"[INFO] Aparelhos Mobile no histórico: {counts.get('qf_mobile_devices') if counts.get('qf_mobile_devices') is not None else '—'}")
        print(f"[INFO] Configurações carregadas: {len(config)} chave(s)")
        print(f"[INFO] Credencial Turso protegida: {'presente' if (restored / 'turso_credentials.dat').is_file() else 'não encontrada'}")
        print(f"[INFO] Credencial Telegram protegida: {'presente' if (restored / 'telegram_credentials.dat').is_file() else 'não encontrada'}")

        # Complete safety copy of the CURRENT installation before replacement.
        backup_root = target_root.parent / f'QuestFlow_DATA_ANTES_RECUPERACAO_{stamp()}'
        try:
            if target_data.exists():
                shutil.copytree(target_data, backup_root / 'data', dirs_exist_ok=False, ignore=shutil.ignore_patterns('backups', '__pycache__'))
            else:
                (backup_root / 'data').mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            fallback = Path(os.environ.get('LOCALAPPDATA') or os.environ.get('TEMP') or str(target_root.parent)) / 'QuestFlow' / f'DATA_ANTES_RECUPERACAO_{stamp()}'
            shutil.copytree(target_data, fallback / 'data', dirs_exist_ok=False, ignore=shutil.ignore_patterns('backups', '__pycache__')) if target_data.exists() else (fallback / 'data').mkdir(parents=True, exist_ok=True)
            backup_root = fallback
        print(f'[OK] Estado atual preservado em: {backup_root}')

        # If QuestFlow is still running, Windows normally refuses this rename;
        # fail safely instead of partially overwriting SQLite files.
        old_tmp = target_root / f'.data_before_recovery_{stamp()}'
        try:
            if target_data.exists():
                target_data.rename(old_tmp)
            shutil.copytree(restored, target_data, dirs_exist_ok=False)
        except PermissionError:
            if target_data.exists() and not old_tmp.exists():
                pass
            elif old_tmp.exists() and not target_data.exists():
                old_tmp.rename(target_data)
            print('[ERRO] A pasta data está em uso. Feche completamente o QuestFlow Studio e o Mobile/Expo e tente novamente.')
            return 7
        except Exception as exc:
            if target_data.exists():
                shutil.rmtree(target_data, ignore_errors=True)
            if old_tmp.exists():
                old_tmp.rename(target_data)
            print(f'[ERRO] A recuperação foi desfeita: {exc}')
            return 8

        try:
            # Apply any schema migrations from the currently installed code.
            sys.path.insert(0, str(target_root))
            from core.storage import QuestFlowDatabase  # type: ignore
            QuestFlowDatabase(target_db)
        except Exception as exc:
            shutil.rmtree(target_data, ignore_errors=True)
            old_tmp.rename(target_data)
            print(f'[ERRO] A nova versão não conseguiu abrir/migrar o banco recuperado: {exc}')
            return 9

        ok, detail = quick_check(target_db)
        final_questions = table_count(target_db, 'questions')
        if not ok:
            shutil.rmtree(target_data, ignore_errors=True)
            old_tmp.rename(target_data)
            print(f'[ERRO] Validação final falhou; o estado anterior foi restaurado: {detail}')
            return 10

        # RECOVERY GUARD: a configuração recuperada pode trazer Cloud Sync/Turso
        # habilitado e sincronização automática no início. Após uma recuperação,
        # o banco local é a fonte comprovadamente íntegra. Pause a nuvem até uma
        # reconciliação explícita para impedir que um estado remoto antigo/incompleto
        # sobrescreva novamente a base recém-restaurada.
        config_path = target_data / 'config.json'
        recovered_config = load_config(config_path)
        previous_cloud = {
            'cloud_sync_enabled': bool(recovered_config.get('cloud_sync_enabled', False)),
            'cloud_sync_on_start': bool(recovered_config.get('cloud_sync_on_start', True)),
            'cloud_sync_on_shutdown': bool(recovered_config.get('cloud_sync_on_shutdown', True)),
            'cloud_turso_url': str(recovered_config.get('cloud_turso_url', '') or ''),
        }
        recovered_config['cloud_sync_enabled'] = False
        recovered_config['cloud_sync_on_start'] = False
        recovered_config['cloud_sync_on_shutdown'] = False
        config_path.write_text(json.dumps(recovered_config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

        guard = {
            'schema': 'questflow.recovery-guard.v1',
            'created_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
            'reason': 'Proteção pós-recuperação: Cloud Sync/Turso pausado até reconciliação explícita.',
            'source_zip': str(source_zip),
            'questions_expected': final_questions,
            'previous_cloud_settings': previous_cloud,
        }
        (target_data / 'RECOVERY_GUARD.json').write_text(json.dumps(guard, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

        marker = {
            'schema': 'questflow.data-recovery.v1',
            'recovered_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
            'source_zip': str(source_zip),
            'backup_before_recovery': str(backup_root),
            'questions_after_recovery': final_questions,
        }
        (target_data / 'recovery_last.json').write_text(json.dumps(marker, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

        shutil.rmtree(old_tmp, ignore_errors=True)
        print('[OK] Dados completos restaurados.')
        print(f'[OK] Banco final íntegro. Questões disponíveis: {final_questions}.')
        if (target_data / 'turso_credentials.dat').is_file():
            print('[OK] Configuração protegida do Turso restaurada.')
        if (target_data / 'telegram_credentials.dat').is_file():
            print('[OK] Configuração protegida do Telegram restaurada.')
        print('[OK] Modo Protegido ativado: Cloud Sync/Turso foi pausado temporariamente.')
        print('[INFO] Caches e perfis temporários do navegador não foram restaurados; serão recriados automaticamente.')
        print('[INFO] Agora abra o QuestFlow novamente e confira Visão geral, Telegram, Estudos e Mobile antes de reconciliar o Turso.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
