@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Turso CLI - instalacao opcional no WSL

echo =============================================================
echo  TURSO CLI - INSTALACAO OPCIONAL PARA CRIAR O BANCO
 echo =============================================================
echo.
echo O QuestFlow NAO precisa do CLI para funcionar depois de configurado.
echo Este utilitario serve apenas para criar/administrar o banco Turso.
echo.
where wsl.exe >nul 2>nul
if errorlevel 1 (
  echo [FALHA] WSL nao foi encontrado.
  echo Abra PowerShell como Administrador e execute: wsl --install
  echo Reinicie o Windows se solicitado e execute este arquivo novamente.
  goto :fim
)

wsl.exe --status >nul 2>nul
if errorlevel 1 (
  echo [AVISO] O WSL existe, mas ainda nao esta pronto.
  echo Abra PowerShell como Administrador e execute: wsl --install
  goto :fim
)

echo [1/2] Instalando/atualizando Turso CLI dentro do WSL...
wsl.exe sh -lc "command -v curl >/dev/null 2>&1 || { echo 'curl nao encontrado no WSL'; exit 3; }; curl -sSfL https://get.tur.so/install.sh | bash"
if errorlevel 1 goto :falha

echo [2/2] Verificando o comando...
wsl.exe sh -lc "export PATH=\"$HOME/.turso:$HOME/.local/bin:$HOME/.cargo/bin:$PATH\"; command -v turso >/dev/null 2>&1 && turso --version || turso"
if errorlevel 1 (
  echo [AVISO] A instalacao terminou, mas talvez seja necessario abrir um novo terminal WSL.
)
echo.
echo Proximos comandos dentro do WSL:
echo   turso auth login
echo   turso db create questflow
echo   turso db show questflow --http-url
echo   turso db tokens create questflow
echo.
echo Depois execute CONFIGURAR_TURSO_CLOUD.bat e cole a URL e o token.
goto :fim

:falha
echo.
echo [FALHA] Nao foi possivel instalar o CLI no WSL.
echo Se a rede usa proxy, configure a conectividade do WSL ou crie o banco pelo painel web do Turso.

:fim
echo.
pause
endlocal
