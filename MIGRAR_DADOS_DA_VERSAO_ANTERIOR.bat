@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title QuestFlow - Migracao Segura de Dados

echo ============================================================
echo   QUESTFLOW - MIGRACAO SEGURA PARA A NOVA VERSAO
echo ============================================================
echo.
if "%~1"=="" (
  echo Arraste a PASTA da versao anterior do QuestFlow para cima
  echo deste arquivo MIGRAR_DADOS_DA_VERSAO_ANTERIOR.bat.
  echo.
  echo Exemplo de origem:
  echo C:\QuestFlow\QuestFlow_Studio_6.9.5_MOBILE_DEVICE_LIFECYCLE
  echo.
  pause
  exit /b 2
)

call QUESTFLOW_RUNTIME.bat
if errorlevel 1 (
  echo.
  echo [ERRO] Nao foi possivel localizar o runtime Python do QuestFlow.
  pause
  exit /b %errorlevel%
)

"%QF_PYTHON%" migrar_dados_versao_anterior.py "%~f1"
set "QF_RC=%ERRORLEVEL%"
echo.
if "%QF_RC%"=="0" (
  echo ============================================================
  echo   MIGRACAO CONCLUIDA. AGORA INICIE O QUESTFLOW NESTA PASTA.
  echo ============================================================
) else (
  echo ============================================================
  echo   MIGRACAO NAO CONCLUIDA. A VERSAO ANTIGA FOI PRESERVADA.
  echo ============================================================
)
pause
exit /b %QF_RC%
