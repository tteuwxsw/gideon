param(
    [string]$CaminhoUE5 = ""
)

$ErrorActionPreference = "Stop"
$ProjetoDir = $PSScriptRoot
$UProject = Join-Path $ProjetoDir "GideonUE5.uproject"
$PastaSaida = Join-Path $ProjetoDir "Build"

if (-not $CaminhoUE5) {
    $Candidatos = @(
        "C:\Program Files\Epic Games\UE_5.5",
        "C:\Program Files\Epic Games\UE_5.4",
        "C:\Program Files\Epic Games\UE_5.3",
        "D:\Epic Games\UE_5.5",
        "D:\Epic Games\UE_5.4"
    )
    foreach ($c in $Candidatos) {
        if (Test-Path (Join-Path $c "Engine\Build\BatchFiles\RunUAT.bat")) {
            $CaminhoUE5 = $c
            break
        }
    }
}

if (-not $CaminhoUE5 -or -not (Test-Path (Join-Path $CaminhoUE5 "Engine\Build\BatchFiles\RunUAT.bat"))) {
    Write-Host "[AVISO] Unreal Engine 5 nao foi localizado automaticamente." -ForegroundColor Yellow
    Write-Host "Instale o Unreal Engine 5.4+ pelo Epic Games Launcher (com Visual Studio 2022 C++) e execute:"
    Write-Host "  .\gideon_ue5\compilar_ue5.ps1 -CaminhoUE5 'C:\Program Files\Epic Games\UE_5.4'"
    exit 1
}

$RunUAT = Join-Path $CaminhoUE5 "Engine\Build\BatchFiles\RunUAT.bat"
Write-Host "[Gideon UE5] Compilando e empacotando projeto com $RunUAT ..." -ForegroundColor Cyan

& $RunUAT BuildCookRun `
    -project="$UProject" `
    -noP4 `
    -platform=Win64 `
    -clientconfig=Shipping `
    -cook `
    -allmaps `
    -build `
    -stage `
    -pak `
    -archive `
    -archivedirectory="$PastaSaida"

if ($LASTEXITCODE -ne 0) {
    throw "Falha ao compilar o pacote Unreal Engine 5 da Gideon."
}

Write-Host "[OK] Executavel Unreal Engine 5 gerado em: $PastaSaida\Windows\GideonUE5.exe" -ForegroundColor Green
