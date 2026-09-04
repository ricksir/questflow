@echo off
rem Runtime compartilhado e de caminho curto do QuestFlow Studio.
rem Nao use SETLOCAL aqui: as variaveis precisam voltar ao BAT chamador.
if defined QF_RUNTIME_INITIALIZED exit /b 0

if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "QF_RUNTIME_ROOT=%LOCALAPPDATA%\QFS"
set "QF_VENV=%QF_RUNTIME_ROOT%\venv"
set "QF_PYTHON=%QF_VENV%\Scripts\python.exe"
set "QF_PYTHONW=%QF_VENV%\Scripts\pythonw.exe"
set "QF_READY_DIR=%QF_RUNTIME_ROOT%\ready"
set "PIP_CACHE_DIR=%QF_RUNTIME_ROOT%\pip-cache"
set "QF_RUNTIME_INITIALIZED=1"
exit /b 0
