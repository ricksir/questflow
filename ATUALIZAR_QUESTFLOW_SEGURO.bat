@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if "%~1"=="" (
  echo Agora as atualizacoes sao feitas pelo QuestFlow Manager.
  echo.
  echo Abra QUESTFLOW.bat e escolha Atualizar QuestFlow.
  echo O Manager tambem procura automaticamente novos ZIPs em Downloads.
  echo.
  pause
  call "%~dp0QUESTFLOW.bat"
  exit /b %ERRORLEVEL%
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0questflow_manager.ps1" -UpdateZip "%~f1"
exit /b %ERRORLEVEL%
