@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call QUESTFLOW_RUNTIME.bat
if errorlevel 1 exit /b %errorlevel%
"%QF_PYTHON%" release_tools.py lock-check
if errorlevel 1 goto :fail
"%QF_PYTHON%" -m unittest tests.test_mobile_study_session_6100 tests.test_mobile_professional_ux_699 tests.test_mobile_study_triage_697 tests.test_mobile_device_lifecycle_695 tests.test_runtime_watchdog_668
if errorlevel 1 goto :fail
node --check web\app.js
if errorlevel 1 goto :fail
pushd mobile
call npm run test:core
if errorlevel 1 (popd & goto :fail)
popd
"%QF_PYTHON%" release_tools.py smoke
if errorlevel 1 goto :fail
echo [OK] Validacao critica da release 6.10.0 concluida.
exit /b 0
:fail
echo [FALHA] A validacao da release 6.10.0 encontrou problemas.
exit /b 1
