param(
    [switch]$PularSetup
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Iscc = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
$Modelo = Join-Path $Root "dados\modelos\vosk-model-small-pt-0.3"

if (-not (Test-Path -LiteralPath $Modelo)) {
    throw "Modelo Vosk ausente em $Modelo"
}

$FrontendDir = Join-Path $Root "frontend"
if (Test-Path (Join-Path $FrontendDir "package.json")) {
    Write-Host "Compilando frontend moderno React + TypeScript..."
    Push-Location $FrontendDir
    & npm.cmd run build
    Pop-Location
    if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar frontend React" }
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"

& $Python -m PyInstaller --noconfirm --clean (Join-Path $PSScriptRoot "gideon.spec")
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar Gideon.exe" }

& $Python -m PyInstaller --noconfirm --clean (Join-Path $PSScriptRoot "gideon-wake.spec")
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar GideonWake.exe" }

& $Python -m PyInstaller --noconfirm --clean (Join-Path $PSScriptRoot "gideon-updater.spec")
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar GideonUpdater.exe" }

& $Python -m PyInstaller --noconfirm --clean (Join-Path $PSScriptRoot "gideon-cli.spec")
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar GideonCtl.exe" }

if (-not $PularSetup) {
    if (-not (Test-Path -LiteralPath $Iscc)) {
        throw "Inno Setup nao encontrado em $Iscc"
    }
    & $Iscc (Join-Path $Root "installer\Gideon.iss")
    if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar GideonSetup.exe" }
}
