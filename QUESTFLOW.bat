@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title QuestFlow Manager
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0questflow_manager.ps1"
set "QF_RC=%ERRORLEVEL%"
if not "%QF_RC%"=="0" (
    echo.
    echo [ERRO] O QuestFlow Manager foi encerrado com codigo %QF_RC%.
    echo O arquivo de log de atualizacao, quando houver, fica em %%LOCALAPPDATA%%\QFS\logs.
    pause
)
exit /b %QF_RC%
