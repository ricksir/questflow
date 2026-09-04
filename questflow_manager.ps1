param(
    [switch]$Install,
    [string]$UpdateZip
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$StableRoot = Join-Path $env:USERPROFILE 'QuestFlow'
$Downloads = Join-Path $env:USERPROFILE 'Downloads'
$RuntimeRoot = if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA 'QFS' } else { Join-Path $env:TEMP 'QFS' }
$ManagerState = Join-Path $RuntimeRoot 'manager'
New-Item -ItemType Directory -Path $ManagerState -Force | Out-Null

function Write-Title([string]$text) {
    Clear-Host
    Write-Host '============================================================' -ForegroundColor DarkCyan
    Write-Host '                    QUESTFLOW MANAGER V2.7' -ForegroundColor Cyan
    Write-Host '============================================================' -ForegroundColor DarkCyan
    if ($text) { Write-Host $text -ForegroundColor White; Write-Host '' }
}

function Read-VersionFile([string]$folder) {
    $file = Join-Path $folder 'VERSION.txt'
    if (Test-Path $file) { return (Get-Content $file -Raw).Trim() }
    return '0.0.0'
}

function Parse-Version([string]$text) {
    try { return [version]$text }
    catch {
        $m = [regex]::Match($text, '\d+\.\d+\.\d+')
        if ($m.Success) { return [version]$m.Value }
        return [version]'0.0.0'
    }
}

function Get-ZipVersion([string]$zipPath) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        $entry = $zip.Entries | Where-Object { $_.FullName -match '(^|/)VERSION\.txt$' } | Select-Object -First 1
        if (-not $entry) { return $null }
        $reader = New-Object System.IO.StreamReader($entry.Open())
        try { return ($reader.ReadToEnd()).Trim() } finally { $reader.Dispose() }
    } finally { $zip.Dispose() }
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

function Invoke-Python([string[]]$python, [string[]]$arguments) {
    if (-not $python) { throw 'Python 3.11 ou superior nao foi encontrado.' }
    $python = @($python)
    $exe = [string]$python[0]
    $prefix = @()
    if ($python.Count -gt 1) { $prefix = @($python[1..($python.Count - 1)]) }
    if (-not (Test-Path $exe) -and -not (Get-Command $exe -ErrorAction SilentlyContinue)) {
        throw "Executavel Python nao encontrado: $exe"
    }

    # IMPORTANTE: nao deixe a saida textual do Python virar parte do valor
    # retornado pela funcao. No PowerShell, toda saida no pipeline tambem e
    # retorno da funcao; isso fazia $rc receber [INFO] + [OK] + 0 e a migracao
    # concluida ser interpretada como erro.
    $output = & $exe @prefix @arguments 2>&1
    $exitCode = $LASTEXITCODE
    foreach ($line in @($output)) { Write-Host $line }
    if ($null -eq $exitCode) { $exitCode = 0 }
    return [int]$exitCode
}

function Select-Folder([string]$description) {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = $description
    $dialog.ShowNewFolderButton = $false
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { return $dialog.SelectedPath }
    return $null
}

function Select-Zip {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = 'Selecione o ZIP da nova versao do QuestFlow'
    $dialog.Filter = 'QuestFlow ZIP (*.zip)|*.zip|Todos os arquivos (*.*)|*.*'
    if (Test-Path $Downloads) { $dialog.InitialDirectory = $Downloads }
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { return $dialog.FileName }
    return $null
}

function Select-DataZip {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = 'Selecione o ZIP da pasta data antiga do QuestFlow'
    $dialog.Filter = 'ZIP de dados (*.zip)|*.zip|Todos os arquivos (*.*)|*.*'
    if (Test-Path $Downloads) { $dialog.InitialDirectory = $Downloads }
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { return $dialog.FileName }
    return $null
}

function Get-NewestUpdate([string]$currentRoot) {
    $currentVersion = Parse-Version (Read-VersionFile $currentRoot)
    $candidates = @()
    foreach ($folder in @($Downloads, (Split-Path $currentRoot -Parent), $currentRoot)) {
        if (-not $folder -or -not (Test-Path $folder)) { continue }
        $candidates += Get-ChildItem -Path $folder -Filter 'QuestFlow_Studio_*.zip' -File -ErrorAction SilentlyContinue
    }
    $best = $null
    foreach ($item in ($candidates | Sort-Object LastWriteTime -Descending -Unique)) {
        try {
            $vText = Get-ZipVersion $item.FullName
            if (-not $vText) { continue }
            $v = Parse-Version $vText
            if ($v -gt $currentVersion) {
                if (-not $best -or $v -gt $best.Version -or ($v -eq $best.Version -and $item.LastWriteTime -gt $best.File.LastWriteTime)) {
                    $best = [pscustomobject]@{ File = $item; Version = $v; VersionText = $vText }
                }
            }
        } catch { }
    }
    return $best
}

function Stop-QuestFlowProcesses([string]$installRoot) {
    $escaped = [regex]::Escape($installRoot)
    $allProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $processes = @($allProcesses | Where-Object {
        $_.CommandLine -and ($_.CommandLine -match $escaped) -and (
            $_.CommandLine -match 'app\.py' -or $_.CommandLine -match 'expo(\.cmd)?\s+start' -or $_.CommandLine -match 'expo-router'
        )
    })

    # Chrome uses an isolated profile inside QuestFlow/data. If Python is killed
    # first during an update, this Chrome may remain orphaned and capture the next
    # --app URL, preventing the new local engine from receiving a heartbeat.
    # Match ONLY the QuestFlow profile; never close the user's normal Chrome.
    $chromeProfile = Join-Path $installRoot 'data\chrome_runtime_5_4_0'
    $escapedChromeProfile = [regex]::Escape($chromeProfile)
    $chromeProcesses = @($allProcesses | Where-Object {
        $_.Name -ieq 'chrome.exe' -and $_.CommandLine -and ($_.CommandLine -match $escapedChromeProfile)
    })

    if ($processes.Count -gt 0 -or $chromeProcesses.Count -gt 0) {
        Write-Host '[INFO] Fechando processos do QuestFlow desta instalacao...' -ForegroundColor Yellow
        foreach ($p in $processes) {
            try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch { }
        }
        foreach ($p in $chromeProcesses) {
            try { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue } catch { }
        }

        # Wait briefly for the private Chrome profile lock to be released before
        # staging/restarting the application. This avoids first-launch races.
        $deadline = (Get-Date).AddSeconds(5)
        do {
            Start-Sleep -Milliseconds 250
            $left = @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue | Where-Object {
                $_.CommandLine -and ($_.CommandLine -match $escapedChromeProfile)
            })
        } while ($left.Count -gt 0 -and (Get-Date) -lt $deadline)
        Start-Sleep -Milliseconds 350
    }
}

function Expand-QuestFlowZip([string]$zipPath, [string]$destination) {
    # Force a short staging root on Windows PowerShell 5.1. Long temp paths can
    # make Expand-Archive report an existing ZIP member as missing.
    $shortBase = Join-Path $RuntimeRoot 'tmp'
    New-Item -ItemType Directory -Path $shortBase -Force | Out-Null
    $destination = Join-Path $shortBase ('m' + [guid]::NewGuid().ToString('N').Substring(0,8))
    if (Test-Path $destination) { Remove-Item $destination -Recurse -Force }
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    Expand-Archive -Path $zipPath -DestinationPath $destination -Force
    $versionFiles = Get-ChildItem -Path $destination -Filter VERSION.txt -Recurse -File -ErrorAction Stop
    if (-not $versionFiles) { throw 'Pacote sem VERSION.txt.' }
    $root = Split-Path -Parent $versionFiles[0].FullName
    if (-not (Test-Path (Join-Path $root 'release_tools.py'))) { throw 'Pacote nao contem release_tools.py.' }
    return $root
}

function Invoke-SafeUpdate([string]$zipPath, [string]$installRoot) {
    if (-not (Test-Path $zipPath)) { throw "ZIP nao encontrado: $zipPath" }
    $zipVersion = Get-ZipVersion $zipPath
    if (-not $zipVersion) { throw 'Nao foi possivel identificar a versao do ZIP.' }
    $current = Read-VersionFile $installRoot
    if ((Parse-Version $zipVersion) -le (Parse-Version $current)) {
        Write-Title "QuestFlow $current ja esta instalado"
        Write-Host '[OK] O pacote selecionado nao e mais novo que a instalacao atual.' -ForegroundColor Green
        Write-Host '[INFO] Nenhuma atualizacao sera executada e seus dados permanecem intactos.' -ForegroundColor Gray
        return $true
    }

    Write-Title "Atualizacao: $current -> $zipVersion"
    Write-Host 'O Manager vai:' -ForegroundColor White
    Write-Host '  1. abrir um atualizador externo em uma nova janela;' -ForegroundColor Gray
    Write-Host '  2. criar e validar backup do banco;' -ForegroundColor Gray
    Write-Host '  3. validar o pacote em staging;' -ForegroundColor Gray
    Write-Host '  4. atualizar Studio + Mobile preservando /data;' -ForegroundColor Gray
    Write-Host '  5. mostrar progresso e gravar um log permanente.' -ForegroundColor Gray
    Write-Host ''
    $answer = Read-Host 'Continuar? [S/n]'
    if ($answer -and $answer.ToLowerInvariant() -notin @('s','sim','y','yes')) { return $false }

    Stop-QuestFlowProcesses $installRoot
    $template = Join-Path $Root 'questflow_external_updater.ps1'
    if (-not (Test-Path $template)) { throw 'Atualizador externo do Manager V2.7 nao foi encontrado.' }
    $external = Join-Path $ManagerState 'questflow_external_updater.ps1'
    Copy-Item $template $external -Force

    Write-Host ''
    Write-Host '[INFO] Abrindo o atualizador externo...' -ForegroundColor Cyan
    Write-Host '[INFO] Uma segunda janela permanecera visivel durante toda a atualizacao.' -ForegroundColor Gray
    $args = @(
        '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', ('"' + $external + '"'),
        '-Zip', ('"' + $zipPath + '"'),
        '-InstallRoot', ('"' + $installRoot + '"'),
        '-RuntimeRoot', ('"' + $RuntimeRoot + '"')
    )
    $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList ($args -join ' ') -PassThru -Wait
    if ($proc.ExitCode -ne 0) {
        throw "Atualizacao nao concluida pelo Manager V2.7 (codigo $($proc.ExitCode)). Consulte %LOCALAPPDATA%\QFS\logs."
    }
    return $true
}

function Find-PreviousQuestFlow([string]$excludeRoot) {
    $found = @()
    foreach ($base in @($Downloads, $env:USERPROFILE, (Split-Path $excludeRoot -Parent))) {
        if (-not $base -or -not (Test-Path $base)) { continue }
        $dirs = Get-ChildItem $base -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'QuestFlow*' }
        foreach ($dir in $dirs) {
            $db = Join-Path $dir.FullName 'data\questflow_questions.sqlite'
            if ((Test-Path $db) -and ($dir.FullName -ne $excludeRoot)) {
                $found += $dir
            } else {
                # Detecta o caso comum ZIP\pasta\pasta real.
                $nested = Get-ChildItem $dir.FullName -Directory -ErrorAction SilentlyContinue | Where-Object { ($_.FullName -ne $excludeRoot) -and (Test-Path (Join-Path $_.FullName 'data\questflow_questions.sqlite')) }
                $found += $nested
            }
        }
    }
    # Prefira a instalação com o banco mais completo, não simplesmente a pasta
    # mais recente. Pastas *_ANTERIOR_* criadas pelo próprio Manager podem ser
    # mais novas, porém conter um banco vazio/intermediário.
    $unique = $found | Sort-Object FullName -Unique
    return $unique | Sort-Object `
        @{ Expression = { try { (Get-Item (Join-Path $_.FullName 'data\questflow_questions.sqlite')).Length } catch { 0 } }; Descending = $true }, `
        @{ Expression = { $_.LastWriteTime }; Descending = $true }
}

function Invoke-Migration([string]$oldRoot, [string]$newRoot) {
    $python = Find-Python
    if (-not $python) { throw 'Python nao encontrado para validar/migrar o banco.' }
    $script = Join-Path $newRoot 'migrar_dados_versao_anterior.py'
    if (-not (Test-Path $script)) { throw 'Ferramenta de migracao nao encontrada na nova versao.' }
    Write-Host ''
    Write-Host '[INFO] Validando, criando backup e migrando seus dados...' -ForegroundColor Cyan
    $rc = Invoke-Python $python @($script, $oldRoot)
    if ($rc -ne 0) { throw "Migracao nao concluida (codigo $rc). A versao antiga foi preservada." }
}

function Copy-NewInstall([string]$source, [string]$target) {
    if ($source.TrimEnd('\') -ieq $target.TrimEnd('\')) { return }
    if (Test-Path $target) {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $old = "${target}_ANTERIOR_$stamp"
        Write-Host "[INFO] Preservando instalacao existente em $old" -ForegroundColor Yellow
        Move-Item $target $old
    }
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    Write-Host "[INFO] Instalando em caminho estavel: $target" -ForegroundColor Cyan
    $null = robocopy $source $target /E /XD node_modules __pycache__ .git /XF '*.pyc' /R:1 /W:1 /NFL /NDL /NJH /NJS
    if ($LASTEXITCODE -ge 8) { throw "Falha ao copiar a nova instalacao (robocopy $LASTEXITCODE)." }
}

function Create-DesktopShortcut([string]$installRoot) {
    try {
        $desktop = [Environment]::GetFolderPath('Desktop')
        $shortcutPath = Join-Path $desktop 'QuestFlow.lnk'
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = Join-Path $installRoot 'QUESTFLOW.bat'
        $shortcut.WorkingDirectory = $installRoot
        $shortcut.Description = 'QuestFlow Studio + Mobile Manager'
        $shortcut.Save()
        Write-Host "[OK] Atalho criado na Area de Trabalho: QuestFlow" -ForegroundColor Green
    } catch {
        Write-Host '[AVISO] Nao foi possivel criar o atalho automaticamente.' -ForegroundColor Yellow
    }
}

function Install-Easy {
    Write-Title 'Instalacao/atualizacao simplificada'

    # Recuperacao automatica do caso em que uma execucao anterior conseguiu
    # copiar a versao e migrar o banco, mas parou antes de criar o atalho.
    $packageVersion = Read-VersionFile $Root
    $stableVersion = if (Test-Path $StableRoot) { Read-VersionFile $StableRoot } else { '0.0.0' }
    $stableReady = (
        (Test-Path (Join-Path $StableRoot 'data\questflow_questions.sqlite')) -and
        (Test-Path (Join-Path $StableRoot 'QUESTFLOW.bat')) -and
        (Test-Path (Join-Path $StableRoot 'app.py')) -and
        (Test-Path (Join-Path $StableRoot 'mobile\package.json')) -and
        ((Parse-Version $stableVersion) -eq (Parse-Version $packageVersion))
    )
    if ($stableReady) {
        Write-Host "[OK] QuestFlow $stableVersion ja esta instalado em $StableRoot." -ForegroundColor Green
        Write-Host '[INFO] A execucao anterior ja copiou a versao e migrou o banco.' -ForegroundColor Cyan
        Write-Host '[INFO] Vou apenas concluir o Manager/atalho; seus dados nao serao migrados novamente.' -ForegroundColor Gray
        Create-DesktopShortcut $StableRoot
        Write-Host ''
        Write-Host '[OK] Instalacao recuperada e pronta.' -ForegroundColor Green
        $start = Read-Host 'Iniciar Studio + Mobile agora? [S/n]'
        if (-not $start -or $start.ToLowerInvariant() -in @('s','sim','y','yes')) {
            Start-Process -FilePath (Join-Path $StableRoot 'INICIAR_QUESTFLOW_STUDIO.bat') -WorkingDirectory $StableRoot
            Start-Sleep -Seconds 2
            Start-Process -FilePath (Join-Path $StableRoot 'INICIAR_QUESTFLOW_MOBILE_ALPHA.bat') -WorkingDirectory $StableRoot
        } else {
            Start-Process (Join-Path $StableRoot 'QUESTFLOW.bat')
        }
        return
    }

    Write-Host "A instalacao principal ficara em:" -ForegroundColor White
    Write-Host "  $StableRoot" -ForegroundColor Cyan
    Write-Host ''
    Write-Host 'Isso evita caminhos longos dentro de Downloads e passa a ser a pasta fixa do QuestFlow.' -ForegroundColor Gray
    $answer = Read-Host 'Continuar? [S/n]'
    if ($answer -and $answer.ToLowerInvariant() -notin @('s','sim','y','yes')) { return }

    $previous = $null
    if (Test-Path (Join-Path $StableRoot 'data\questflow_questions.sqlite')) {
        $previous = $StableRoot
    } else {
        $candidates = @(Find-PreviousQuestFlow $Root)
        if ($candidates.Count -gt 0) {
            Write-Host ''
            Write-Host 'Encontrei uma instalação anterior com o maior banco de dados entre as candidatas:' -ForegroundColor White
            Write-Host "  $($candidates[0].FullName)" -ForegroundColor Cyan
            try {
                $dbInfo = Get-Item (Join-Path $candidates[0].FullName 'data\questflow_questions.sqlite')
                Write-Host ("  Banco: {0:N1} MB" -f ($dbInfo.Length / 1MB)) -ForegroundColor Gray
                if (Test-Path (Join-Path $candidates[0].FullName 'data\config.json')) { Write-Host '  Configurações: encontradas' -ForegroundColor Gray }
                if (Test-Path (Join-Path $candidates[0].FullName 'data\turso_credentials.dat')) { Write-Host '  Credencial Turso protegida: encontrada' -ForegroundColor Gray }
                if (Test-Path (Join-Path $candidates[0].FullName 'data\telegram_credentials.dat')) { Write-Host '  Credencial Telegram protegida: encontrada' -ForegroundColor Gray }
            } catch { }
            Write-Host 'Confira o caminho acima. O Manager não escolherá mais uma pasta apenas por ser a mais recente.' -ForegroundColor Yellow
            $use = Read-Host 'Usar esta instalação para trazer seus dados? [S/n]'
            if (-not $use -or $use.ToLowerInvariant() -in @('s','sim','y','yes')) { $previous = $candidates[0].FullName }
        }
        if (-not $previous) {
            $choose = Read-Host 'Deseja selecionar manualmente a pasta da versao anterior? [S/n]'
            if (-not $choose -or $choose.ToLowerInvariant() -in @('s','sim','y','yes')) {
                $previous = Select-Folder 'Selecione a pasta da versao anterior do QuestFlow (a que contem data, mobile, core e app.py)'
            }
        }
    }

    # Se a instalacao anterior ja era o StableRoot, preserva antes da copia.
    $oldStable = $null
    if ($previous -and ($previous.TrimEnd('\') -ieq $StableRoot.TrimEnd('\')) -and (Test-Path $StableRoot)) {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $oldStable = "${StableRoot}_ANTERIOR_$stamp"
        Stop-QuestFlowProcesses $StableRoot
        Move-Item $StableRoot $oldStable
        $previous = $oldStable
    }

    Copy-NewInstall $Root $StableRoot
    if ($previous -and (Test-Path (Join-Path $previous 'data\questflow_questions.sqlite'))) {
        Invoke-Migration $previous $StableRoot
    }
    Create-DesktopShortcut $StableRoot
    Write-Host ''
    Write-Host '[OK] Instalacao pronta.' -ForegroundColor Green
    Write-Host 'Daqui para frente use apenas o atalho QuestFlow da Area de Trabalho.' -ForegroundColor White
    Write-Host ''
    $start = Read-Host 'Iniciar Studio + Mobile agora? [S/n]'
    if (-not $start -or $start.ToLowerInvariant() -in @('s','sim','y','yes')) {
        Start-Process -FilePath (Join-Path $StableRoot 'INICIAR_QUESTFLOW_STUDIO.bat') -WorkingDirectory $StableRoot
        Start-Sleep -Seconds 2
        Start-Process -FilePath (Join-Path $StableRoot 'INICIAR_QUESTFLOW_MOBILE_ALPHA.bat') -WorkingDirectory $StableRoot
    } else {
        Start-Process (Join-Path $StableRoot 'QUESTFLOW.bat')
    }
}

function Start-Studio([string]$installRoot) {
    Start-Process -FilePath (Join-Path $installRoot 'INICIAR_QUESTFLOW_STUDIO.bat') -WorkingDirectory $installRoot
}

function Start-Mobile([string]$installRoot) {
    Start-Process -FilePath (Join-Path $installRoot 'INICIAR_QUESTFLOW_MOBILE_ALPHA.bat') -WorkingDirectory $installRoot
}

function Start-All([string]$installRoot) {
    Start-Studio $installRoot
    Start-Sleep -Seconds 2
    Start-Mobile $installRoot
}

function Run-Diagnostics([string]$installRoot) {
    Start-Process -FilePath (Join-Path $installRoot 'INSTALAR_E_DIAGNOSTICAR.bat') -WorkingDirectory $installRoot
}

function Recover-DataFromZip([string]$installRoot) {
    $zip = Select-DataZip
    if (-not $zip) { return }
    $python = Find-Python
    if (-not $python) { throw 'Python não encontrado para recuperar os dados.' }
    $tool = Join-Path $installRoot 'recuperar_dados_completos.py'
    if (-not (Test-Path $tool)) { throw 'Ferramenta RECUPERAR_DADOS_COMPLETOS não encontrada neste hotfix.' }
    Stop-QuestFlowProcesses $installRoot
    Write-Host '[INFO] Validando o ZIP, criando backup do estado atual e recuperando os dados...' -ForegroundColor Cyan
    $rc = Invoke-Python $python @($tool, $zip, '--target-root', $installRoot)
    if ($rc -ne 0) { throw "Recuperação não concluída (código $rc)." }
    Write-Host '[OK] Recuperação concluída.' -ForegroundColor Green
    Read-Host 'Pressione ENTER para continuar'
}

if ($Install) {
    try { Install-Easy }
    catch {
        Write-Host ''
        Write-Host "[ERRO] $($_.Exception.Message)" -ForegroundColor Red
        Write-Host 'Nenhum dado da versao anterior deve ser apagado automaticamente.' -ForegroundColor Yellow
        Read-Host 'Pressione ENTER para fechar'
        exit 1
    }
    exit 0
}

if ($UpdateZip) {
    try {
        if (Invoke-SafeUpdate $UpdateZip $Root) { Start-Process (Join-Path $Root 'QUESTFLOW.bat') }
    } catch {
        Write-Host "[ERRO] $($_.Exception.Message)" -ForegroundColor Red
        Read-Host 'Pressione ENTER para continuar'
    }
    exit 0
}

$offeredUpdate = $false
while ($true) {
    $version = Read-VersionFile $Root
    $mobileVersion = '—'
    $pkg = Join-Path $Root 'mobile\package.json'
    if (Test-Path $pkg) {
        try { $mobileVersion = (Get-Content $pkg -Raw | ConvertFrom-Json).version } catch { }
    }
    $update = Get-NewestUpdate $Root
    if ($update -and -not $offeredUpdate) {
        Write-Title "Nova versao encontrada: $($update.VersionText)"
        Write-Host "ZIP: $($update.File.Name)" -ForegroundColor Cyan
        Write-Host 'O QuestFlow pode atualizar Studio + Mobile automaticamente e preservar seus dados.' -ForegroundColor White
        $auto = Read-Host 'Atualizar agora? [S/n]'
        $offeredUpdate = $true
        if (-not $auto -or $auto.ToLowerInvariant() -in @('s','sim','y','yes')) {
            if (Invoke-SafeUpdate $update.File.FullName $Root) {
                $go = Read-Host 'Atualizacao concluida. Iniciar Studio + Mobile agora? [S/n]'
                if (-not $go -or $go.ToLowerInvariant() -in @('s','sim','y','yes')) { Start-All $Root; exit 0 }
                Start-Process (Join-Path $Root 'QUESTFLOW.bat')
                exit 0
            }
        }
    }

    Write-Title "Studio $version   |   Mobile $mobileVersion"
    if ($update) {
        Write-Host "Atualizacao disponivel: $($update.VersionText) - $($update.File.Name)" -ForegroundColor Green
        Write-Host ''
    } else {
        Write-Host 'Tudo certo: nenhum ZIP mais novo foi encontrado em Downloads.' -ForegroundColor DarkGray
        Write-Host ''
    }
    Write-Host '[1] Iniciar QuestFlow (Studio + Mobile)' -ForegroundColor Cyan
    Write-Host '[2] Iniciar somente o Studio' -ForegroundColor White
    if ($update) { Write-Host '[3] Atualizar QuestFlow automaticamente' -ForegroundColor Green } else { Write-Host '[3] Procurar atualizacao em Downloads' -ForegroundColor White }
    Write-Host '[4] Selecionar um ZIP de atualizacao' -ForegroundColor White
    Write-Host '[5] Migrar dados de uma versao anterior' -ForegroundColor White
    Write-Host '[6] Diagnostico / reparar dependencias' -ForegroundColor White
    Write-Host '[7] Recuperar dados completos de um ZIP/pasta data' -ForegroundColor Yellow
    Write-Host '[8] Ativar inicio automatico do Studio com o Windows' -ForegroundColor White
    Write-Host '[9] Remover inicio automatico do Studio' -ForegroundColor White
    Write-Host '[0] Sair' -ForegroundColor Gray
    Write-Host ''
    $choice = Read-Host 'Escolha'

    try {
        switch ($choice) {
            '1' { Start-All $Root; break }
            '2' { Start-Studio $Root; break }
            '3' {
                if (-not $update) {
                    Write-Host '[INFO] Nao encontrei um ZIP mais novo em Downloads.' -ForegroundColor Yellow
                    Start-Sleep -Seconds 2
                } elseif (Invoke-SafeUpdate $update.File.FullName $Root) {
                    Start-Process (Join-Path $Root 'QUESTFLOW.bat')
                    exit 0
                }
            }
            '4' {
                $zip = Select-Zip
                if ($zip -and (Invoke-SafeUpdate $zip $Root)) {
                    Start-Process (Join-Path $Root 'QUESTFLOW.bat')
                    exit 0
                }
            }
            '5' {
                $old = Select-Folder 'Selecione a pasta da versao anterior do QuestFlow'
                if ($old) { Invoke-Migration $old $Root; Read-Host 'Pressione ENTER para continuar' }
            }
            '6' { Run-Diagnostics $Root; break }
            '7' { Recover-DataFromZip $Root }
            '8' { Start-Process -FilePath (Join-Path $Root 'ATIVAR_INICIO_COM_WINDOWS.bat') -WorkingDirectory $Root; break }
            '9' { Start-Process -FilePath (Join-Path $Root 'REMOVER_INICIO_COM_WINDOWS.bat') -WorkingDirectory $Root; break }
            '0' { exit 0 }
            default { }
        }
    } catch {
        Write-Host ''
        Write-Host "[ERRO] $($_.Exception.Message)" -ForegroundColor Red
        Write-Host 'A instalacao anterior e os backups nao sao removidos pelo Manager.' -ForegroundColor Yellow
        Read-Host 'Pressione ENTER para continuar'
    }
}
