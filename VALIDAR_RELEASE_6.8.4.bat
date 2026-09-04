@echo off
setlocal
cd /d "%~dp0"
call QUESTFLOW_RUNTIME.bat
if errorlevel 1 exit /b %errorlevel%
"%QF_PYTHON%" release_tools.py ci
set "QF_RC=%ERRORLEVEL%"
echo.
if "%QF_RC%"=="0" (
  echo [OK] Validacao de release 6.8.4 concluida.
) else (
  echo [FALHA] A validacao de release encontrou problemas. Codigo: %QF_RC%
)
pause
exit /b %QF_RC%
