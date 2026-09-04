@echo off
setlocal
cd /d "%~dp0mobile"
echo.
echo ============================================================
echo  QUESTFLOW MOBILE 0.13.0 - APK PREVIEW SEM OVERLAYS DEV
echo ============================================================
echo.
echo Esta build inclui a Reserva Offline estrita, o novo estado sem spinner
echo e o destaque reforcado de alternativas eliminadas.
echo Requer internet e login EAS apenas para gerar o APK.
echo.
call npx eas-cli build --platform android --profile preview
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo Falha ao solicitar a build EAS.
pause
exit /b %RC%
