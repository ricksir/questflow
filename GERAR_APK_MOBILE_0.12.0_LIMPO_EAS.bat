@echo off
setlocal
cd /d "%~dp0mobile"
echo.
echo ============================================================
echo  QUESTFLOW MOBILE 0.12.0 - APK PREVIEW SEM OVERLAYS DEV
echo ============================================================
echo.
echo Esta build e recomendada para uso diario e offline.
echo Nao exibe barra Refreshing nem botao flutuante de desenvolvimento.
echo Requer internet e login EAS apenas para gerar o APK.
echo.
call npx eas-cli build --platform android --profile preview
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo Falha ao solicitar a build EAS.
pause
exit /b %RC%
