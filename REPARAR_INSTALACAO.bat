@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Reparar Instalacao - QuestFlow Studio

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_NO_CACHE_DIR=1"
call "%~dp0QUESTFLOW_RUNTIME.bat"

if not exist "%QF_PYTHON%" (
  echo [ERRO] O ambiente compartilhado ainda nao existe.
  echo Execute primeiro INSTALAR_E_DIAGNOSTICAR.bat.
  echo Caminho esperado: %QF_VENV%
  echo.
  pause
  exit /b 1
)

echo Reinstalando as dependencias sem utilizar o cache do pip...
"%QF_PYTHON%" installer.py --force
if errorlevel 1 (
  echo.
  echo [FALHA] O reparo nao foi concluido.
  pause
  exit /b 1
)

echo.
echo [OK] Reparo concluido. Execute INSTALAR_E_DIAGNOSTICAR.bat.
pause
