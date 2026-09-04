@echo off
setlocal
cd /d "%~dp0"
call QUESTFLOW_RUNTIME.bat
if errorlevel 1 exit /b %errorlevel%

"%QF_PYTHON%" release_tools.py lock-check
if errorlevel 1 goto :fail

"%QF_PYTHON%" -m unittest -q ^
 tests.test_mobile_integration_foundation_690 ^
 tests.test_adaptive_engine ^
 tests.test_learning_analytics_570 ^
 tests.test_fsrs6_integration_560 ^
 tests.test_schema_migrations ^
 tests.test_mobile_access_5_4_0 ^
 tests.test_web_api ^
 tests.test_local_http_engine ^
 tests.test_hardening_monitor_641 ^
 tests.test_runtime_watchdog_668 ^
 tests.test_tutor_scaffolding_670 ^
 tests.test_evidence_benchmark_671 ^
 tests.test_google_commentary_672 ^
 tests.test_production_hardening_673 ^
 tests.test_retrieval_observability_683 ^
 tests.test_retrieval_quality_gates_684
if errorlevel 1 goto :fail

"%QF_PYTHON%" release_tools.py smoke --root .
if errorlevel 1 goto :fail

echo.
echo [OK] Validacao critica da release 6.9.0 concluida.
pause
exit /b 0

:fail
echo.
echo [FALHA] A validacao da release 6.9.0 encontrou problemas.
pause
exit /b 1
