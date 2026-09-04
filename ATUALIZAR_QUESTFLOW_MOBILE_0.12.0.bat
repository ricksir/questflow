@echo off
setlocal
cd /d "%~dp0"
set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo.
echo ============================================================
echo  QUESTFLOW MOBILE 0.12.0 - ATUALIZACAO SEGURA DE FONTES
echo ============================================================
echo.
"%PY%" aplicar_mobile_update_0_12_0.py
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo A atualizacao Mobile falhou. As fontes anteriores foram preservadas/restauradas.
  pause
  exit /b %RC%
)
echo Atualizacao concluida.
echo Para remover o botao flutuante nativo do Dev Client, gere uma nova build 0.12.0.
pause
exit /b 0
