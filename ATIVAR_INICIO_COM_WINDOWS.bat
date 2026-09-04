@echo off
setlocal EnableExtensions
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS=%STARTUP%\QuestFlow_Studio.vbs"
set "LAUNCHER=%~dp0INICIAR_QUESTFLOW_STUDIO.bat"

if not exist "%LAUNCHER%" (
  echo [ERRO] Inicializador do Studio nao encontrado: %LAUNCHER%
  echo.
  pause
  exit /b 1
)
if not exist "%STARTUP%" mkdir "%STARTUP%" >nul 2>nul

> "%VBS%" echo Set shell = CreateObject("WScript.Shell")
>> "%VBS%" echo WScript.Sleep 10000
>> "%VBS%" echo shell.Run Chr(34) ^& "%LAUNCHER%" ^& Chr(34), 0, False

if not exist "%VBS%" (
  echo [ERRO] O Windows nao permitiu criar a entrada de inicializacao.
  echo.
  pause
  exit /b 1
)

echo.
echo QuestFlow Studio configurado para iniciar com o Windows.
echo A abertura ocorrera 10 segundos depois de entrar na sua conta.
echo O fluxo so enviara automaticamente se estiver ativado dentro do programa.
echo Se o horario for perdido, o QuestFlow tentara recuperar o ciclo ao abrir.
echo.
pause
exit /b 0
