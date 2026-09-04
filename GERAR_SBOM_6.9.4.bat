@echo off
setlocal
cd /d "%~dp0"
if not defined QF_PYTHON set "QF_PYTHON=python"
"%QF_PYTHON%" release_tools.py sbom --output SBOM_6.9.4.cdx.json --json
