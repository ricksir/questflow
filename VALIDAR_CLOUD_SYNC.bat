@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title QuestFlow - Validacao Cloud Sync
call "%~dp0QUESTFLOW_RUNTIME.bat"
if not exist "%QF_PYTHON%" (
  echo Execute INSTALAR_E_DIAGNOSTICAR.bat primeiro.
  pause
  exit /b 1
)
"%QF_PYTHON%" -m unittest -v tests.test_cloud_sync_5_4_0 tests.test_mobile_access_5_4_0
pause
endlocal
