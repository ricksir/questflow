@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title QuestFlow - Recuperacao de Dados

set "TARGET=%USERPROFILE%\QuestFlow"
set "SOURCE=%~1"

if not exist "%TARGET%\app.py" (
  echo [ERRO] Nao encontrei o QuestFlow instalado em:
  echo        %TARGET%
  echo.
  pause
  exit /b 2
)

if "%SOURCE%"=="" (
  for /f "usebackq delims=" %%I in (`powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Title='Selecione o ZIP da pasta data antiga do QuestFlow'; $d.Filter='Arquivo ZIP (*.zip)|*.zip'; $d.InitialDirectory=[Environment]::GetFolderPath('UserProfile')+'\Downloads'; if($d.ShowDialog() -eq 'OK'){ $d.FileName }"`) do set "SOURCE=%%I"
)

if "%SOURCE%"=="" (
  echo [INFO] Operacao cancelada.
  exit /b 0
)

cls
echo ============================================================
echo             QUESTFLOW - RECUPERACAO SEGURA
echo ============================================================
echo.
echo IMPORTANTE: feche completamente o QuestFlow Studio e o Expo/Mobile.
echo.
echo ZIP selecionado:
echo   %SOURCE%
echo.
echo Instalacao que sera recuperada:
echo   %TARGET%
echo.
choice /C SN /N /M "Continuar? [S/N]: "
if errorlevel 2 exit /b 0

set "PY="
if exist "%LOCALAPPDATA%\QFS\venv\Scripts\python.exe" set "PY=%LOCALAPPDATA%\QFS\venv\Scripts\python.exe"
if not defined PY (
  where py.exe >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
  where python.exe >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [ERRO] Python nao encontrado.
  pause
  exit /b 3
)

%PY% "%~dp0recuperar_dados_completos.py" "%SOURCE%" --target-root "%TARGET%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo [ERRO] Recuperacao nao concluida. Codigo: %RC%
  echo O estado anterior foi preservado.
  pause
  exit /b %RC%
)

rem Atualiza o Manager instalado com as correcoes deste hotfix.
copy /Y "%~dp0questflow_manager.ps1" "%TARGET%\questflow_manager.ps1" >nul
copy /Y "%~dp0QUESTFLOW.bat" "%TARGET%\QUESTFLOW.bat" >nul
copy /Y "%~dp0recuperar_dados_completos.py" "%TARGET%\recuperar_dados_completos.py" >nul
copy /Y "%~dp0RECUPERAR_DADOS_COMPLETOS.bat" "%TARGET%\RECUPERAR_DADOS_COMPLETOS.bat" >nul
if exist "%~dp0core\cloud_sync.py" copy /Y "%~dp0core\cloud_sync.py" "%TARGET%\core\cloud_sync.py" >nul
if exist "%~dp0VERIFICAR_DADOS_PERSISTENTES.bat" copy /Y "%~dp0VERIFICAR_DADOS_PERSISTENTES.bat" "%TARGET%\VERIFICAR_DADOS_PERSISTENTES.bat" >nul

if exist "%USERPROFILE%\Desktop\QuestFlow.lnk" (
  rem shortcut already points to the stable installation
) else (
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Desktop'),'QuestFlow.lnk')); $s.TargetPath='%TARGET%\QUESTFLOW.bat'; $s.WorkingDirectory='%TARGET%'; $s.Description='QuestFlow Studio + Mobile Manager'; $s.Save()" >nul 2>&1
)

echo.
echo [OK] Recuperacao finalizada e Manager corrigido.
choice /C SN /N /M "Abrir o QuestFlow agora? [S/N]: "
if errorlevel 2 exit /b 0
start "" "%TARGET%\QUESTFLOW.bat"
exit /b 0
