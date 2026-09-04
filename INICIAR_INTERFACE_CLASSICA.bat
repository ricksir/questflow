@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0QUESTFLOW_RUNTIME.bat"
if exist "%QF_PYTHONW%" (
  start "QuestFlow Studio - Interface Classica" "%QF_PYTHONW%" app_classic.py
) else (
  echo [ERRO] Ambiente do QuestFlow nao encontrado.
  echo Execute INSTALAR_E_DIAGNOSTICAR.bat primeiro.
  pause
)
