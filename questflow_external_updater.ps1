param(
    [Parameter(Mandatory=$true)][string]$Zip,
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [string]$RuntimeRoot
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if (-not $RuntimeRoot) {
    $RuntimeRoot = if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA 'QFS' } else { Join-Path $env:TEMP 'QFS' }
}
$LogRoot = Join-Path $RuntimeRoot 'logs'
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$log = Join-Path $LogRoot "update-$stamp.log"
$holdRoot = Join-Path $RuntimeRoot ("hold-$stamp")

function Say([string]$text, [ConsoleColor]$color = [ConsoleColor]::Gray) {
    Write-Host $text -ForegroundColor $color
    Add-Content -Path $log -Value ("[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $text) -Encoding UTF8
}
function Quote-Arg([string]$value) {
    if ($null -eq $value) { return '""' }
    return '"' + ($value -replace '"','\"') + '"'
}
function Find-Python {
    $qfPython = Join-Path $RuntimeRoot 'venv\Scripts\python.exe'
    if (Test-Path $qfPython) { return @($qfPython) }
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) { return @($py.Source, '-3') }
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) { return @($python.Source) }
    return $null
}
function Get-VersionFromFolder([string]$folder) {
    $vf = Join-Path $folder 'VERSION.txt'
    if (Test-Path $vf) { return (Get-Content $vf -Raw).Trim() }
    return 'desconhecida'
}
function Assert-SafeZipEntries([string]$zipPath) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        foreach ($entry in $archive.Entries) {
            $name = [string]$entry.FullName
            $normalized = $name.Replace('\\','/')
            if (-not $normalized -or $normalized.StartsWith('/') -or $normalized.StartsWith('../') -or $normalized.Contains('/../') -or $normalized -match '^[A-Za-z]:') {
                throw "Pacote contem caminho inseguro/invalido: $name"
            }
        }
    } finally { $archive.Dispose() }
}

function Get-ZipVersion([string]$zipPath) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        $entry = $archive.Entries | Where-Object { $_.FullName -match '(^|/)VERSION\.txt$' } | Select-Object -First 1
        if (-not $entry) { return $null }
        $reader = New-Object System.IO.StreamReader($entry.Open())
        try { return ($reader.ReadToEnd()).Trim() } finally { $reader.Dispose() }
    } finally { $archive.Dispose() }
}
function Move-OptionalDir([string]$source, [string]$name) {
    if (-not (Test-Path $source)) { return $null }
    New-Item -ItemType Directory -Path $holdRoot -Force | Out-Null
    $dest = Join-Path $holdRoot $name
    if (Test-Path $dest) { Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue }
    Move-Item -Path $source -Destination $dest -Force
    return $dest
}
function Restore-OptionalDir([string]$held, [string]$destination) {
    if (-not $held -or -not (Test-Path $held)) { return }
    $parent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    if (Test-Path $destination) { Remove-Item $destination -Recurse -Force -ErrorAction SilentlyContinue }
    Move-Item -Path $held -Destination $destination -Force
}

$heldNodeModules = $null
$heldExpo = $null
$heldCoreBuild = $null
try {
    Clear-Host
    Say '============================================================' DarkCyan
    Say '        QUESTFLOW - ATUALIZADOR EXTERNO (MANAGER V2.7)' Cyan
    Say '============================================================' DarkCyan
    Say ''
    Say ("Instalacao: {0}" -f $InstallRoot) White
    Say ("Pacote:     {0}" -f $Zip) White
    Say ("Log:        {0}" -f $log) DarkGray
    Say ''

    if (-not (Test-Path $Zip)) { throw "ZIP nao encontrado: $Zip" }
    if (-not (Test-Path $InstallRoot)) { throw "Instalacao nao encontrada: $InstallRoot" }

    Say '[1/5] Validando e lendo o pacote sem extrair pelo PowerShell...' Cyan
    Assert-SafeZipEntries $Zip
    $targetVersion = Get-ZipVersion $Zip
    if (-not $targetVersion) { throw 'O pacote nao possui VERSION.txt legivel.' }
    $currentVersion = Get-VersionFromFolder $InstallRoot
    Say ("      Versao atual: {0}" -f $currentVersion) DarkGray
    Say ("      Nova versao:   {0}" -f $targetVersion) Green
    try { $cv = [version]$currentVersion; $tv = [version]$targetVersion } catch { $cv = $null; $tv = $null }
    if ($cv -and $tv -and $tv -le $cv) {
        Say '[OK] Esta versao ja esta instalada. Nenhum arquivo sera substituido.' Green
        Say 'Pode fechar esta janela.' White
        Start-Sleep -Seconds 1
        exit 0
    }

    Say '[2/5] Verificando o Python e o atualizador seguro instalado...' Cyan
    $python = @(Find-Python)
    if (-not $python -or $python.Count -eq 0) { throw 'Python 3.11+ nao foi encontrado.' }
    $exe = [string]$python[0]
    $prefix = @()
    if ($python.Count -gt 1) { $prefix = @($python[1..($python.Count - 1)]) }
    if (-not (Test-Path $exe) -and -not (Get-Command $exe -ErrorAction SilentlyContinue)) {
        throw "Executavel Python nao encontrado: $exe"
    }
    Say ("      Python selecionado: {0}" -f $exe) DarkGray
    if ($prefix.Count -gt 0) { Say ("      Prefixo do launcher: {0}" -f ($prefix -join ' ')) DarkGray }
    $runner = Join-Path $InstallRoot 'questflow_update_runner.py'
    if (-not (Test-Path $runner)) {
        $fallbackRunner = Join-Path $RuntimeRoot 'updater\questflow_update_runner.py'
        if (Test-Path $fallbackRunner) { $runner = $fallbackRunner }
        else { throw "Runner seguro do QuestFlow nao encontrado: $runner" }
    }
    Say ("      Motor de atualizacao: {0}" -f $runner) DarkGray

    Say '      Preservando cache/dependencias grandes do Mobile fora da atualizacao...' DarkGray
    $heldNodeModules = Move-OptionalDir (Join-Path $InstallRoot 'mobile\node_modules') 'node_modules'
    $heldExpo = Move-OptionalDir (Join-Path $InstallRoot 'mobile\.expo') 'expo'
    $heldCoreBuild = Move-OptionalDir (Join-Path $InstallRoot 'mobile\.core-test-build') 'core-test-build'

    Say '[3/5] Criando backup e aplicando a atualizacao segura...' Cyan
    Say '      Esta etapa pode levar alguns minutos. NAO feche esta janela.' Yellow
    $stdout = Join-Path $LogRoot "update-$stamp.stdout.log"
    $stderr = Join-Path $LogRoot "update-$stamp.stderr.log"
    $allArgs = @()
    $allArgs += $prefix
    $allArgs += @($runner, '--package', $Zip, '--install-root', $InstallRoot)
    $argLine = ($allArgs | ForEach-Object { Quote-Arg $_ }) -join ' '
    $proc = Start-Process -FilePath $exe -ArgumentList $argLine -NoNewWindow -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $started = Get-Date
    $lastSize = 0
    while (-not $proc.HasExited) {
        Start-Sleep -Seconds 3
        $elapsed = [int]((Get-Date) - $started).TotalSeconds
        $msg = "      Atualizacao em andamento... ${elapsed}s"
        if (Test-Path $stdout) {
            $size = (Get-Item $stdout).Length
            if ($size -ne $lastSize) { $lastSize = $size; $msg += ' • atividade detectada' }
        }
        Write-Host $msg -ForegroundColor DarkGray
        Add-Content -Path $log -Value ("[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $msg) -Encoding UTF8
        $proc.Refresh()
    }
    $proc.WaitForExit()
    $proc.Refresh()
    $stdoutText = if (Test-Path $stdout) { Get-Content $stdout -Raw } else { '' }
    $stderrText = if (Test-Path $stderr) { Get-Content $stderr -Raw } else { '' }
    if ($stdoutText) { $stdoutText -split "`r?`n" | ForEach-Object { if ($_ -ne '') { Add-Content -Path $log -Value $_ -Encoding UTF8 } } }
    if ($stderrText) { $stderrText -split "`r?`n" | ForEach-Object { if ($_ -ne '') { Add-Content -Path $log -Value $_ -Encoding UTF8 } } }

    $runnerOk = $false
    $runnerResult = $null
    if ($stdoutText) {
        try {
            $runnerResult = $stdoutText | ConvertFrom-Json
            $runnerOk = ($runnerResult.ok -eq $true)
        } catch { }
    }
    $exitCode = $proc.ExitCode
    if ($runnerOk) {
        Say '      Atualizador seguro confirmou: OK.' Green
    } elseif ($null -eq $exitCode -or $exitCode -ne 0) {
        Say ''
        Say '[ERRO] O atualizador seguro retornou falha.' Red
        if ($stderrText) { $stderrText -split "`r?`n" | Select-Object -Last 30 | ForEach-Object { Write-Host $_ -ForegroundColor Red } }
        if ($stdoutText) { $stdoutText -split "`r?`n" | Select-Object -Last 30 | ForEach-Object { Write-Host $_ -ForegroundColor Gray } }
        $shownCode = if ($null -eq $exitCode) { 'indisponivel' } else { [string]$exitCode }
        throw "Codigo de retorno: $shownCode. Consulte o log: $log"
    }

    Say '[4/5] Restaurando dependencias do Mobile e confirmando os dados...' Cyan
    Restore-OptionalDir $heldNodeModules (Join-Path $InstallRoot 'mobile\node_modules'); $heldNodeModules = $null
    Restore-OptionalDir $heldExpo (Join-Path $InstallRoot 'mobile\.expo'); $heldExpo = $null
    Restore-OptionalDir $heldCoreBuild (Join-Path $InstallRoot 'mobile\.core-test-build'); $heldCoreBuild = $null
    $installedVersion = Get-VersionFromFolder $InstallRoot
    if ($installedVersion -ne $targetVersion) { throw "Versao final inesperada: $installedVersion (esperado $targetVersion)." }
    $db = Join-Path $InstallRoot 'data\questflow_questions.sqlite'
    if (-not (Test-Path $db)) { throw 'O banco principal nao foi encontrado depois da atualizacao.' }
    Say '      Banco local preservado.' Green

    Say '[5/5] Atualizacao concluida.' Green
    Say ("      QuestFlow {0} instalado com sucesso." -f $installedVersion) Green
    Say '      Cloud Sync/Turso permanece exatamente no estado do seu banco atual.' DarkGray
    Say ''
    Say 'Pode fechar esta janela. O Manager voltara ao menu automaticamente.' White
    if (Test-Path $holdRoot) { Remove-Item $holdRoot -Recurse -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
    exit 0
}
catch {
    try {
        Restore-OptionalDir $heldNodeModules (Join-Path $InstallRoot 'mobile\node_modules')
        Restore-OptionalDir $heldExpo (Join-Path $InstallRoot 'mobile\.expo')
        Restore-OptionalDir $heldCoreBuild (Join-Path $InstallRoot 'mobile\.core-test-build')
    } catch { }
    Say ''
    Say ("[ERRO] {0}" -f $_.Exception.Message) Red
    Say 'A instalacao e os backups anteriores nao sao apagados pelo atualizador.' Yellow
    Say ("Log: {0}" -f $log) Yellow
    Read-Host 'Pressione ENTER para fechar'
    exit 1
}
finally {
    if (Test-Path $holdRoot) { Remove-Item $holdRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
