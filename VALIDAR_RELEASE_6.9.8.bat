@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call QUESTFLOW_RUNTIME.bat
if errorlevel 1 exit /b %errorlevel%
"%QF_PYTHON%" release_tools.py lock-check --json
if errorlevel 1 goto :fail
"%QF_PYTHON%" -m unittest tests.test_production_hardening_673 tests.test_mobile_cloud_bridge_696 tests.test_mobile_study_triage_697
if errorlevel 1 goto :fail
echo [OK] Validacao critica da release 6.9.8 concluida.
exit /b 0
:fail
echo [FALHA] A validacao da release 6.9.8 encontrou problemas.
exit /b 1
