@echo off
setlocal
cd /d "%~dp0"
set "PY=%CD%\.venv\Scripts\python.exe"
if exist "%PY%" goto run
where py >nul 2>nul && set "PY=py" && goto run
where python >nul 2>nul && set "PY=python" && goto run
echo Python nao encontrado.
pause
exit /b 2
:run
"%PY%" "%CD%\aplicar_mobile_update_0_11_0.py"
set RC=%ERRORLEVEL%
if not "%RC%"=="0" (
  echo.
  echo A atualizacao do Mobile terminou com erro %RC%.
  pause
  exit /b %RC%
)
echo.
echo Codigo do Mobile 0.11.0 atualizado com sucesso.
echo Se voce usa Expo Dev Client, inicie o Mobile normalmente para testar conectado.
echo Para abrir e estudar sem Studio/Metro, instale um build Preview/Production usando GERAR_APK_MOBILE_0.11.0_EAS.bat.
pause
