@echo off
setlocal
cd /d "%~dp0"
call QUESTFLOW_RUNTIME.bat
if errorlevel 1 exit /b %errorlevel%
"%QF_PYTHON%" release_tools.py sbom --output SBOM_6.9.0.cdx.json
pause
