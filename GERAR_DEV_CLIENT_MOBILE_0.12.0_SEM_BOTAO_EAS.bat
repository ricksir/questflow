@echo off
setlocal
cd /d "%~dp0mobile"
echo.
echo ============================================================
echo  QUESTFLOW MOBILE 0.12.0 - DEV CLIENT COM INTERFACE LIMPA
echo ============================================================
echo.
echo Mantem o Dev Client para desenvolvimento, mas a nova configuracao
echo desabilita o botao flutuante. O banner Refreshing e ocultado pelo app.
echo Requer internet e login EAS para gerar a nova build nativa.
echo.
call npx eas-cli build --platform android --profile development
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo Falha ao solicitar a build EAS.
pause
exit /b %RC%
