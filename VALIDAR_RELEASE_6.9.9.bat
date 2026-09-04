@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call QUESTFLOW_RUNTIME.bat
if errorlevel 1 exit /b %errorlevel%
"%QF_PYTHON%" release_tools.py lock-check --json
if errorlevel 1 goto :fail
"%QF_PYTHON%" -m unittest tests.test_mobile_professional_ux_699 tests.test_mobile_study_triage_697 tests.test_mobile_device_lifecycle_695 tests.test_runtime_watchdog_668
if errorlevel 1 goto :fail
node --check web\app.js
if errorlevel 1 goto :fail
pushd mobile
call npm run test:core
if errorlevel 1 (popd & goto :fail)
popd
echo [OK] Validacao critica da release 6.9.9 concluida.
exit /b 0
:fail
echo [FALHA] A validacao da release 6.9.9 encontrou problemas.
exit /b 1
