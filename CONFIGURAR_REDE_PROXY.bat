@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title QuestFlow Studio - Rede e Proxy
set "PYTHONUTF8=1"
set "PYTHON_CMD="
where py >nul 2>nul && set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD where python >nul 2>nul && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
  echo [ERRO] Python 3.11 ou superior nao foi encontrado.
  pause
  exit /b 1
)
%PYTHON_CMD% proxy_setup.py
endlocal
