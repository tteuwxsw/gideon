param(
    [switch]$ApagarMemoria
)

$ErrorActionPreference = "Stop"
$DiretorioInstalacao = Join-Path $env:LOCALAPPDATA "Programs\Gideon"
$NomeTarefa = "Gideon"

if (Test-Path -LiteralPath (Join-Path $DiretorioInstalacao ".venv\Scripts\python.exe")) {
    & (Join-Path $DiretorioInstalacao ".venv\Scripts\python.exe") -m gideon.supervisor --stop
    $Runtime = Join-Path $DiretorioInstalacao "dados\runtime.json"
    $LimiteParada = (Get-Date).AddSeconds(20)
    while ((Test-Path -LiteralPath $Runtime) -and (Get-Date) -lt $LimiteParada) {
        Start-Sleep -Milliseconds 250
    }
    if (Test-Path -LiteralPath $Runtime) {
        throw "A Gideon ainda esta ativa. A remocao foi cancelada para evitar dados parciais."
    }
}

Unregister-ScheduledTask -TaskName $NomeTarefa -Confirm:$false -ErrorAction SilentlyContinue

if ($ApagarMemoria) {
    if (Test-Path -LiteralPath $DiretorioInstalacao) {
        Remove-Item -LiteralPath $DiretorioInstalacao -Recurse -Force
    }
    Write-Host "Gideon e dados locais removidos. A credencial da API deve ser revogada separadamente."
} else {
    Write-Host "Inicializacao automatica removida. Codigo e memoria foram preservados em $DiretorioInstalacao"
    Write-Host "Use -ApagarMemoria somente depois de exportar o que deseja guardar."
}
