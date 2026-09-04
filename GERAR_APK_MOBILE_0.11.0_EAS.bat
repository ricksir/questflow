@echo off
setlocal
cd /d "%~dp0\mobile"
echo ============================================================
echo QuestFlow Mobile 0.11.0 - Build Preview Android
ECHO Este passo requer internet apenas para GERAR o aplicativo.
echo Depois de instalado, a Reserva Offline funciona sem internet.
echo ============================================================
call npx eas build --platform android --profile preview
if errorlevel 1 (
  echo.
  echo O build nao foi concluido. Verifique login EAS, internet e mensagens acima.
  pause
  exit /b 1
)
echo.
echo Build solicitado com sucesso. Instale o APK disponibilizado pelo EAS no celular.
pause
