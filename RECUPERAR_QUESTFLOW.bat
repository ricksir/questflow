@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title QuestFlow Studio - Recuperacao

echo.
echo ============================================================
echo   QuestFlow Studio - Recuperar processo preso em segundo plano
echo ============================================================
echo.
echo Este utilitario encerra SOMENTE processos Python cujo comando aponta
 echo para o app.py desta pasta do QuestFlow. Outros programas Python nao
 echo sao encerrados.
echo.

set "APPFILE=%CD%\app.py"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$target=[IO.Path]::GetFullPath('%APPFILE%');" ^
  "$found=Get-CimInstance Win32_Process ^| Where-Object { ($_.Name -in @('python.exe','pythonw.exe')) -and $_.CommandLine -and ($_.CommandLine -like ('*'+$target+'*') -or $_.CommandLine -like '* app.py*') };" ^
  "if(-not $found){ Write-Host 'Nenhum processo QuestFlow preso foi encontrado.' -ForegroundColor Green; exit 0 };" ^
  "$found ^| ForEach-Object { Write-Host ('Encerrando QuestFlow PID '+$_.ProcessId+' ...') -ForegroundColor Yellow; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Start-Sleep -Milliseconds 500"

if exist "data\questflow_instance.lock" del /q "data\questflow_instance.lock" >nul 2>nul

echo.
echo Recuperacao concluida. Agora execute INICIAR_QUESTFLOW_STUDIO.bat.
echo.
pause
