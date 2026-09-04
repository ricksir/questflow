@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Instalacao e Diagnostico - QuestFlow Studio

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PYTHONOPTIMIZE=1"

call "%~dp0QUESTFLOW_RUNTIME.bat"
if errorlevel 1 goto :falha

set "APP_VERSION=desconhecida"
if exist "VERSION.txt" set /p APP_VERSION=<"VERSION.txt"
set "READY_MARKER=%QF_READY_DIR%\questflow-ready-%APP_VERSION%.txt"

echo =============================================================
echo  QUESTFLOW STUDIO %APP_VERSION% - INSTALACAO E DIAGNOSTICO
echo =============================================================
echo.
echo Ambiente Python compartilhado: %QF_VENV%
echo O caminho curto evita o limite de caminhos do Windows em pacotes grandes.
echo.
echo Se esta maquina usa proxy corporativo e ele nao estiver configurado no Windows,
echo execute primeiro CONFIGURAR_REDE_PROXY.bat.
echo.

set "PYTHON_CMD="
where py >nul 2>nul && set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD where python >nul 2>nul && set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
  echo [FALHA] Python nao encontrado.
  echo Instale Python 3.11 ou superior e marque "Add Python to PATH".
  goto :fim
)

echo [OK] Python encontrado: %PYTHON_CMD%
if not exist "%QF_RUNTIME_ROOT%" mkdir "%QF_RUNTIME_ROOT%" >nul 2>nul
if not exist "%QF_READY_DIR%" mkdir "%QF_READY_DIR%" >nul 2>nul
if not exist "%PIP_CACHE_DIR%" mkdir "%PIP_CACHE_DIR%" >nul 2>nul

if exist "%QF_PYTHON%" (
  "%QF_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
  if errorlevel 1 (
    echo [INFO] Runtime Python anterior invalido. Recriando ambiente...
    rmdir /s /q "%QF_VENV%" >nul 2>nul
  )
)

if not exist "%QF_PYTHON%" (
  echo [1/4] Criando o ambiente compartilhado em caminho curto...
  %PYTHON_CMD% -m venv "%QF_VENV%"
  if errorlevel 1 goto :falha
) else (
  echo [1/4] Ambiente compartilhado encontrado.
)

echo [2/4] Instalando e verificando dependencias...
"%QF_PYTHON%" installer.py
if errorlevel 1 goto :falha

echo [3/4] Otimizando os modulos Python para inicializacao...
"%QF_PYTHON%" -m compileall -q app.py app_shared.py desktop_runtime.py web_api.py web_server.py core ui
if errorlevel 1 goto :falha

echo [4/4] Executando diagnostico completo...
"%QF_PYTHON%" diagnostico.py
if errorlevel 1 goto :falha

>"%READY_MARKER%" echo QuestFlow Studio %APP_VERSION% preparado em %date% %time%
echo.
echo [SUCESSO] O QuestFlow Studio esta pronto.
echo Runtime reutilizavel: %QF_VENV%
echo Execute INICIAR_QUESTFLOW_STUDIO.bat.
goto :fim

:falha
if exist "%READY_MARKER%" del /q "%READY_MARKER%" >nul 2>nul
echo.
echo [FALHA] A instalacao nao foi concluida. Leia a mensagem acima.
echo Runtime utilizado: %QF_VENV%
echo Se a mensagem citar Internet, proxy, TLS ou HTTP 407, execute
echo CONFIGURAR_REDE_PROXY.bat e repita esta instalacao.
echo Se a mensagem citar caminho longo/Long Path, envie o trecho do erro:
echo esta versao ja usa um runtime curto para evitar esse problema.

:fim
echo.
pause
