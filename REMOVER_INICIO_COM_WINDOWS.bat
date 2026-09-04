@echo off
setlocal
set "VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\QuestFlow_Studio.vbs"
if exist "%VBS%" del /q "%VBS%"
echo.
echo Inicializacao automatica do QuestFlow Studio removida.
echo.
pause
