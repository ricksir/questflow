@echo off
setlocal EnableExtensions
set "ROOT=%USERPROFILE%\QuestFlow"
set "DB=%ROOT%\data\questflow_questions.sqlite"
set "CFG=%ROOT%\data\config.json"
echo ============================================================
echo       QUESTFLOW - VERIFICACAO DOS DADOS PERSISTENTES
echo ============================================================
echo.
echo Pasta: %ROOT%\data
if not exist "%DB%" (
  echo [ERRO] Banco nao encontrado: %DB%
  pause
  exit /b 2
)
set "PY="
if exist "%LOCALAPPDATA%\QFS\venv\Scripts\python.exe" set "PY=%LOCALAPPDATA%\QFS\venv\Scripts\python.exe"
if not defined PY where py.exe >nul 2>&1 && set "PY=py -3"
if not defined PY where python.exe >nul 2>&1 && set "PY=python"
%PY% -c "import sqlite3,json,pathlib; db=pathlib.Path(r'%DB%'); c=sqlite3.connect(db); print('[OK] quick_check:',c.execute('pragma quick_check').fetchone()[0]); print('[INFO] Questoes:',c.execute('select count(*) from questions').fetchone()[0] if c.execute(\"select 1 from sqlite_master where type='table' and name='questions'\").fetchone() else '—'); c.close(); p=pathlib.Path(r'%CFG%'); cfg=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}; print('[INFO] Cloud Sync habilitado:',bool(cfg.get('cloud_sync_enabled',False))); print('[INFO] Cloud Sync no inicio:',bool(cfg.get('cloud_sync_on_start',False))); print('[INFO] Recovery Guard:',(pathlib.Path(r'%ROOT%')/'data'/'RECOVERY_GUARD.json').exists())"
echo.
pause
