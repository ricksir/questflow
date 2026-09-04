@echo off
setlocal EnableExtensions
cd /d "%~dp0mobile"
title QuestFlow Mobile
where node >nul 2>nul || goto :nonode
where npm >nul 2>nul || goto :nonode

if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "QF_READY=%LOCALAPPDATA%\QFS\ready"
if not exist "%QF_READY%" mkdir "%QF_READY%" >nul 2>nul
set "QF_MOBILE_HASH=%QF_READY%\mobile-package.sha256"

for /f "tokens=*" %%H in ('powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 '%CD%\package.json').Hash"') do set "CURRENT_HASH=%%H"
set "SAVED_HASH="
if exist "%QF_MOBILE_HASH%" set /p SAVED_HASH=<"%QF_MOBILE_HASH%"

if not exist node_modules goto :install
if /i not "%CURRENT_HASH%"=="%SAVED_HASH%" goto :install
goto :start

:install
echo [QuestFlow Mobile] Preparando dependencias automaticamente...
call npm install
if errorlevel 1 goto :fail
>"%QF_MOBILE_HASH%" echo %CURRENT_HASH%
echo [OK] Mobile preparado.

:start
echo.
echo [QuestFlow Mobile] Iniciando Expo em modo LAN...
echo O Studio e o celular devem estar na mesma rede local nesta fase.
call npx expo start --lan
exit /b %errorlevel%

:nonode
echo [FALHA] Node.js/npm nao encontrado.
echo Instale uma versao LTS atual do Node.js e tente novamente.
pause
exit /b 1

:fail
echo [FALHA] Nao foi possivel preparar o cliente mobile.
echo Verifique rede/proxy e tente novamente pelo QUESTFLOW.bat.
pause
exit /b 1
