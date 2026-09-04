@echo off
setlocal EnableExtensions
cd /d "%~dp0mobile"
where node >nul 2>nul || goto :nonode
where npm >nul 2>nul || goto :nonode

echo [QuestFlow Mobile] Instalando/atualizando dependencias...
call npm install
if errorlevel 1 goto :fail

if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "QF_READY=%LOCALAPPDATA%\QFS\ready"
if not exist "%QF_READY%" mkdir "%QF_READY%" >nul 2>nul
for /f "tokens=*" %%H in ('powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 '%CD%\package.json').Hash"') do >"%QF_READY%\mobile-package.sha256" echo %%H

echo.
echo [OK] Dependencias do Mobile atualizadas.
exit /b 0

:nonode
echo [FALHA] Node.js/npm nao encontrado. Instale uma versao LTS atual do Node.js e execute novamente.
pause
exit /b 1

:fail
echo [FALHA] npm install nao concluiu. Verifique rede/proxy e tente novamente.
pause
exit /b 1
