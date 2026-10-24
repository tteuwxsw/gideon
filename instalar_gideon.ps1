param(
    [switch]$NaoIniciar
)

$ErrorActionPreference = "Stop"
$Repositorio = "https://github.com/tteuwxsw/gideon.git"
$DiretorioPai = Join-Path $env:LOCALAPPDATA "Programs"
$DiretorioInstalacao = Join-Path $DiretorioPai "Gideon"
$NomeTarefa = "Gideon"

function Exigir-Comando([string]$Nome) {
    if (-not (Get-Command $Nome -ErrorAction SilentlyContinue)) {
        throw "O comando '$Nome' nao foi encontrado. Instale-o antes de continuar."
    }
}

if ($env:OS -ne "Windows_NT") {
    throw "A integracao da Gideon requer Windows."
}

Exigir-Comando "git"
Exigir-Comando "uv"
$ReiniciarSeFalhar = $false
$PythonWAnterior = $null

try {
if (-not (Test-Path -LiteralPath $DiretorioPai)) {
    New-Item -ItemType Directory -Path $DiretorioPai | Out-Null
}

if (Test-Path -LiteralPath (Join-Path $DiretorioInstalacao ".git")) {
    $EstadoGit = & git -C $DiretorioInstalacao status --porcelain
    if ($LASTEXITCODE -ne 0) {
        throw "Nao foi possivel verificar a instalacao existente."
    }
    if ($EstadoGit) {
        throw "A instalacao possui modificacoes locais e nao sera sobrescrita."
    }

    $PythonInstalado = Join-Path $DiretorioInstalacao ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $PythonInstalado) {
        & $PythonInstalado -m gideon.supervisor --stop 2>$null
        if ($LASTEXITCODE -eq 0) {
            $ReiniciarSeFalhar = $true
            $PythonWAnterior = Join-Path $DiretorioInstalacao ".venv\Scripts\pythonw.exe"
        }
        $LimiteParada = (Get-Date).AddSeconds(20)
        $Runtime = Join-Path $DiretorioInstalacao "dados\runtime.json"
        while ((Test-Path -LiteralPath $Runtime) -and (Get-Date) -lt $LimiteParada) {
            Start-Sleep -Milliseconds 250
        }
        if (Test-Path -LiteralPath $Runtime) {
            throw "A instancia instalada da Gideon nao encerrou; atualizacao cancelada."
        }
    }

    & git -C $DiretorioInstalacao pull --ff-only
    if ($LASTEXITCODE -ne 0) {
        throw "A instalacao existente possui divergencias e nao foi alterada."
    }
} elseif (Test-Path -LiteralPath $DiretorioInstalacao) {
    throw "A pasta $DiretorioInstalacao existe, mas nao e uma instalacao Git da Gideon."
} else {
    & git clone --branch master --single-branch $Repositorio $DiretorioInstalacao
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao clonar o repositorio privado. Confirme seu login no GitHub."
    }
}

& uv sync --frozen --project $DiretorioInstalacao
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao sincronizar as dependencias da Gideon."
}

& uv run --project $DiretorioInstalacao python (Join-Path $DiretorioInstalacao "testes\teste_runtime.py")
if ($LASTEXITCODE -ne 0) {
    throw "A instalacao falhou no portao isolado do runtime."
}

$PythonW = Join-Path $DiretorioInstalacao ".venv\Scripts\pythonw.exe"
if (-not (Test-Path -LiteralPath $PythonW)) {
    throw "pythonw.exe nao foi criado no ambiente da Gideon."
}

$Usuario = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Acao = New-ScheduledTaskAction `
    -Execute $PythonW `
    -Argument "-m gideon.supervisor" `
    -WorkingDirectory $DiretorioInstalacao
$Gatilho = New-ScheduledTaskTrigger -AtLogOn -User $Usuario
$Principal = New-ScheduledTaskPrincipal `
    -UserId $Usuario `
    -LogonType Interactive `
    -RunLevel Limited
$Configuracoes = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $NomeTarefa `
    -Action $Acao `
    -Trigger $Gatilho `
    -Principal $Principal `
    -Settings $Configuracoes `
    -Description "Gideon - assistente pessoal local" `
    -Force | Out-Null

if (-not $NaoIniciar) {
    Start-ScheduledTask -TaskName $NomeTarefa
}
$ReiniciarSeFalhar = $false

Write-Host "Gideon instalada em $DiretorioInstalacao"
Write-Host "Inicializacao silenciosa registrada na tarefa '$NomeTarefa'."
} catch {
    if ($ReiniciarSeFalhar -and $PythonWAnterior -and (Test-Path -LiteralPath $PythonWAnterior)) {
        Start-Process -FilePath $PythonWAnterior -ArgumentList "-m", "gideon.supervisor" -WorkingDirectory $DiretorioInstalacao
    }
    throw
}
