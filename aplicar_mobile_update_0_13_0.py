from __future__ import annotations
import json, shutil, subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / 'mobile_update_payload_0.13.0' / 'mobile'
TARGET = ROOT / 'mobile'
BACKUPS = ROOT / 'backups'
EXPECTED = '0.13.0'
PROTECTED = {'node_modules', '.expo', '.core-test-build', 'android', 'ios'}


def restore_source(backup: Path) -> None:
    """Restaura somente fontes/config do Mobile; dependências e projetos nativos ficam intactos."""
    for item in TARGET.iterdir():
        if item.name in PROTECTED:
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    for item in backup.iterdir():
        dst = TARGET / item.name
        if item.is_dir():
            shutil.copytree(item, dst)
        else:
            shutil.copy2(item, dst)


def main() -> int:
    if not PAYLOAD.exists() or not TARGET.exists():
        print('ERRO: payload ou pasta mobile nao encontrado.')
        return 2
    pkg = TARGET / 'package.json'
    if not pkg.exists():
        print('ERRO: instalacao Mobile nao encontrada em', TARGET)
        return 3

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = BACKUPS / f'mobile_source_before_0.13.0_{stamp}'
    backup.mkdir(parents=True, exist_ok=False)

    for item in TARGET.iterdir():
        if item.name in PROTECTED:
            continue
        dst = backup / item.name
        if item.is_dir():
            shutil.copytree(item, dst)
        else:
            shutil.copy2(item, dst)

    for src in PAYLOAD.rglob('*'):
        if not src.is_file():
            continue
        rel = src.relative_to(PAYLOAD)
        dst = TARGET / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    version = json.loads(pkg.read_text(encoding='utf-8')).get('version')
    if version != EXPECTED:
        print(f'ERRO: versao Mobile apos copia = {version!r}; esperado {EXPECTED!r}. Restaurando.')
        restore_source(backup)
        return 4

    tsc = TARGET / 'node_modules' / 'typescript' / 'bin' / 'tsc'
    if tsc.exists():
        try:
            check = subprocess.run(['node', str(tsc), '--noEmit'], cwd=TARGET, check=False, timeout=180)
        except subprocess.TimeoutExpired:
            print('ERRO: typecheck do Mobile excedeu 180 segundos. Restaurando fontes anteriores.')
            restore_source(backup)
            return 6
        if check.returncode:
            print('ERRO: typecheck do Mobile falhou. Restaurando fontes anteriores.')
            restore_source(backup)
            return 5

    print('OK: QuestFlow Mobile source atualizado para 0.13.0.')
    print('Backup:', backup)
    print('node_modules, .expo e diretorios nativos foram preservados.')
    print('IMPORTANTE: para remover definitivamente o botao flutuante do Dev Client, gere/instale uma nova build nativa 0.13.0.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
