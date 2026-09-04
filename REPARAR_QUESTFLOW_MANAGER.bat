@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "TARGET=%USERPROFILE%\QuestFlow"
set "RUNTIME=%LOCALAPPDATA%\QFS\updater"
cd /d "%~dp0"
title QuestFlow - Reparar Manager V2.6

echo ============================================================
echo              QUESTFLOW - REPARAR MANAGER V2.6
echo ============================================================
echo.
if not exist "%TARGET%\VERSION.txt" (
    echo [ERRO] A instalacao principal nao foi encontrada em:
    echo        %TARGET%
    echo.
    echo Este reparo nao mexe no banco. Confirme primeiro onde esta sua instalacao ativa.
    pause
    exit /b 1
)

echo Instalacao encontrada: %TARGET%
set /p CONF="Instalar o Manager V2.6 e o motor de atualizacao sem alterar a pasta data? [S/n]: "
if defined CONF if /I not "%CONF%"=="S" if /I not "%CONF%"=="SIM" if /I not "%CONF%"=="Y" if /I not "%CONF%"=="YES" exit /b 0

echo.
echo [INFO] Copiando somente arquivos do gerenciador/atualizador...
copy /Y "%~dp0QUESTFLOW.bat" "%TARGET%\QUESTFLOW.bat" >nul || goto :fail
copy /Y "%~dp0questflow_manager.ps1" "%TARGET%\questflow_manager.ps1" >nul || goto :fail
copy /Y "%~dp0questflow_external_updater.ps1" "%TARGET%\questflow_external_updater.ps1" >nul || goto :fail
copy /Y "%~dp0questflow_update_runner.py" "%TARGET%\questflow_update_runner.py" >nul || goto :fail
if exist "%~dp0MANAGER_VERSION.txt" copy /Y "%~dp0MANAGER_VERSION.txt" "%TARGET%\MANAGER_VERSION.txt" >nul

if not exist "%RUNTIME%" mkdir "%RUNTIME%" >nul 2>&1
copy /Y "%~dp0questflow_update_runner.py" "%RUNTIME%\questflow_update_runner.py" >nul || goto :fail

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $p=Join-Path $d 'QuestFlow.lnk'; $s=New-Object -ComObject WScript.Shell; $l=$s.CreateShortcut($p); $l.TargetPath='%TARGET%\QUESTFLOW.bat'; $l.WorkingDirectory='%TARGET%'; $l.Description='QuestFlow Manager V2.6'; $l.Save()" >nul 2>&1

echo [OK] Manager V2.6 instalado.
echo [OK] Motor externo de atualizacao instalado em %%LOCALAPPDATA%%\QFS\updater.
echo [OK] Nenhum arquivo da pasta data foi copiado, removido ou alterado.
echo [INFO] O novo motor ignora caches/runtimes do Chrome no backup de seguranca.
echo [INFO] Agora abra C:\Users\%USERNAME%\QuestFlow\QUESTFLOW.bat e atualize normalmente.
echo.
pause
exit /b 0

:fail
echo.
echo [ERRO] Nao foi possivel copiar os arquivos do Manager V2.6.
echo Feche todas as janelas do QuestFlow e tente novamente.
pause
exit /b 1
