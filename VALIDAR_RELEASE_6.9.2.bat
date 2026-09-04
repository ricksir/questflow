@echo off
setlocal
cd /d "%~dp0"
if not defined QF_PYTHON set "QF_PYTHON=python"

"%QF_PYTHON%" -m compileall -q core app.py web_api.py web_server.py || goto :fail
node --check web\app.js || goto :fail
"%QF_PYTHON%" -m unittest tests.test_dynamic_mobile_network_692 tests.test_mobile_alpha_691 tests.test_mobile_integration_foundation_690 tests.test_schema_migrations || goto :fail
"%QF_PYTHON%" release_tools.py lock-check || goto :fail
"%QF_PYTHON%" release_tools.py smoke || goto :fail

echo [OK] Validacao critica da release 6.9.2 concluida.
exit /b 0

:fail
echo [FALHA] A validacao da release 6.9.2 encontrou problemas.
exit /b 1
