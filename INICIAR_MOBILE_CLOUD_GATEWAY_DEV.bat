@echo off
setlocal
cd /d "%~dp0"
if "%QUESTFLOW_BRIDGE_KEY%"=="" (
  echo Defina QUESTFLOW_BRIDGE_KEY antes de iniciar o Gateway.
  echo Exemplo no Prompt: set QUESTFLOW_BRIDGE_KEY=uma-chave-longa-e-aleatoria
  pause
  exit /b 1
)
python mobile_cloud_gateway.py --host 127.0.0.1 --port 8787 --db data\mobile-cloud-gateway.sqlite
endlocal
