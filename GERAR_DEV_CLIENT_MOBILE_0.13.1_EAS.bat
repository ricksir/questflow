@echo off
setlocal
cd /d "%~dp0mobile"
echo.
echo ============================================================
echo  QUESTFLOW MOBILE 0.13.1 - DEVELOPMENT BUILD
echo ============================================================
echo.
call npx eas-cli build --platform android --profile development
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo Falha ao solicitar a build EAS.
pause
exit /b %RC%
