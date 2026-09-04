@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call QUESTFLOW_RUNTIME.bat
if errorlevel 1 exit /b %errorlevel%
"%QF_PYTHON%" release_tools.py sbom --output SBOM_6.10.1.cdx.json
pause
