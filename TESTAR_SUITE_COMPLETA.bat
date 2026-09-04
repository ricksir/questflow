@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0QUESTFLOW_RUNTIME.bat"
if not exist "%QF_PYTHON%" (
  echo Execute INSTALAR_E_DIAGNOSTICAR.bat primeiro.
  pause
  exit /b 1
)
"%QF_PYTHON%" run_tests.py
pause
