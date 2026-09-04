@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title QuestFlow - Instalacao Facil
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0questflow_manager.ps1" -Install
exit /b %ERRORLEVEL%
