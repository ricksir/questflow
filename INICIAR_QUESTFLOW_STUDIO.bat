@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title QuestFlow Studio

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PYTHONOPTIMIZE=1"

call "%~dp0QUESTFLOW_RUNTIME.bat"
if errorlevel 1 goto :erro

set "APP_VERSION=desconhecida"
if exist "VERSION.txt" set /p APP_VERSION=<"VERSION.txt"
set "READY_MARKER=%QF_READY_DIR%\questflow-ready-%APP_VERSION%.txt"

set "PYTHON_CMD="
where py >nul 2>nul && set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD where python >nul 2>nul && set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
  echo.
  echo [ERRO] Python nao foi encontrado.
  echo Instale o Python 3.11 ou superior e marque "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

if not exist "%QF_RUNTIME_ROOT%" mkdir "%QF_RUNTIME_ROOT%" >nul 2>nul
if not exist "%QF_READY_DIR%" mkdir "%QF_READY_DIR%" >nul 2>nul
if not exist "%PIP_CACHE_DIR%" mkdir "%PIP_CACHE_DIR%" >nul 2>nul

if exist "%QF_PYTHON%" (
  "%QF_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
  if errorlevel 1 (
    echo [INFO] Runtime Python anterior invalido. Recriando ambiente curto...
    rmdir /s /q "%QF_VENV%" >nul 2>nul
  )
)

if not exist "%QF_PYTHON%" (
  echo Criando o ambiente compartilhado do QuestFlow em caminho curto...
  echo [INFO] Runtime: %QF_VENV%
  %PYTHON_CMD% -m venv "%QF_VENV%"
  if errorlevel 1 goto :erro
)

rem A verificacao completa de pacotes ocorre somente quando esta versao
rem ainda nao possui marcador. O marcador de dependencias dentro do runtime
rem continua validando mudancas no requirements.txt.
if not exist "%READY_MARKER%" (
  echo Preparando o QuestFlow Studio %APP_VERSION%...
  echo [INFO] Ambiente Python curto: %QF_VENV%
  "%QF_PYTHON%" installer.py
  if errorlevel 1 goto :erro
  "%QF_PYTHON%" -m compileall -q app.py app_shared.py desktop_runtime.py web_api.py web_server.py core ui >nul 2>nul
  >"%READY_MARKER%" echo QuestFlow Studio %APP_VERSION% preparado em %date% %time%
)

start "QuestFlow Studio" "%QF_PYTHONW%" app.py
exit /b 0

:erro
echo.
echo [ERRO] Nao foi possivel preparar o programa.
echo Execute INSTALAR_E_DIAGNOSTICAR.bat e leia a mensagem apresentada.
echo O ambiente desta versao fica em: %QF_VENV%
echo Se a mensagem citar Internet, proxy, TLS ou HTTP 407, use CONFIGURAR_REDE_PROXY.bat.
echo.
pause
exit /b 1
