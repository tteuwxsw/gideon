param(
    [Parameter(Mandatory = $true)]
    [string]$Referencia,

    [ValidateSet("leve", "qualidade")]
    [string]$Qualidade = "leve",

    [ValidateRange(1, 8)]
    [int]$Threads = 4,

    [ValidateRange(10, 300)]
    [int]$OciosoSegundos = 30,

    [ValidateRange(15, 600)]
    [int]$TimeoutSegundos = 180,

    [switch]$SemQuantizacao,
    [switch]$AceitoTermosModelo,
    [switch]$ConfirmoDireitosDaVoz
)

$ErrorActionPreference = "Stop"

if (-not $AceitoTermosModelo) {
    throw "Leia e aceite os termos em https://huggingface.co/kyutai/pocket-tts e execute novamente com -AceitoTermosModelo."
}
if (-not $ConfirmoDireitosDaVoz) {
    throw "Use somente uma voz propria ou autorizada e confirme com -ConfirmoDireitosDaVoz."
}

$ReferenciaResolvida = (Resolve-Path -LiteralPath $Referencia).Path
if ([IO.Path]::GetExtension($ReferenciaResolvida).ToLowerInvariant() -ne ".wav") {
    throw "A referencia deve ser um arquivo WAV PCM de 16 bits."
}

$BaseDir = Join-Path $env:LOCALAPPDATA "Gideon"
$DadosDir = Join-Path $BaseDir "dados"
$VozDir = Join-Path $DadosDir "voz"
$MotorDir = Join-Path $BaseDir "motores\pockettts"
$VenvDir = Join-Path $MotorDir ".venv"
$Python = Join-Path $VenvDir "Scripts\python.exe"
$CacheDir = Join-Path $MotorDir "cache_huggingface"
$ReferenciaDestino = Join-Path $VozDir "referencia.wav"
$EstadoDestino = Join-Path $VozDir "referencia.safetensors"
$ConfigDestino = Join-Path $DadosDir "voz_local.json"

New-Item -ItemType Directory -Path $VozDir -Force | Out-Null
New-Item -ItemType Directory -Path $MotorDir -Force | Out-Null
New-Item -ItemType Directory -Path $CacheDir -Force | Out-Null

if (-not (Test-Path -LiteralPath $Python)) {
    $PyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($null -eq $PyLauncher) {
        throw "Python 3.12 nao foi encontrado. Instale-o antes de preparar o motor local."
    }
    & $PyLauncher.Source -3.12 -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar o ambiente isolado do PocketTTS." }
}

& $Python -m pip install --disable-pip-version-check --upgrade "pocket-tts==4.0.1"
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar pocket-tts==4.0.1." }

if ($ReferenciaResolvida -ne $ReferenciaDestino) {
    Copy-Item -LiteralPath $ReferenciaResolvida -Destination $ReferenciaDestino -Force
}
$env:HF_HOME = $CacheDir
if (-not $env:HF_TOKEN) {
    $TokenSeguro = Read-Host "Token Hugging Face com acesso ao PocketTTS" -AsSecureString
    $Ponteiro = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($TokenSeguro)
    try {
        $env:HF_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Ponteiro)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Ponteiro)
    }
}
if (-not $env:HF_TOKEN) {
    throw "Token Hugging Face ausente. Ele e usado apenas durante o download e nao sera salvo na configuracao."
}

$Preparador = Join-Path $PSScriptRoot "preparar_pockettts.py"
$Argumentos = @(
    $Preparador,
    "--referencia", $ReferenciaDestino,
    "--saida", $EstadoDestino,
    "--qualidade", $Qualidade,
    "--threads", $Threads
)
if ($SemQuantizacao) {
    $Argumentos += "--sem-quantizacao"
}

try {
    & $Python @Argumentos
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao baixar ou validar o modelo PocketTTS. Confirme o aceite na pagina do modelo e o token."
    }
}
finally {
    Remove-Item Env:HF_TOKEN -ErrorAction SilentlyContinue
}

$Configuracao = [ordered]@{
    ativo = $true
    python = $Python
    referencia = $EstadoDestino
    qualidade = $Qualidade
    quantizar = -not $SemQuantizacao.IsPresent
    threads = $Threads
    ocioso_s = $OciosoSegundos
    timeout_s = $TimeoutSegundos
}
$Json = $Configuracao | ConvertTo-Json
$ConfigTemporaria = "$ConfigDestino.tmp"
$Utf8SemBom = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($ConfigTemporaria, $Json, $Utf8SemBom)
Move-Item -LiteralPath $ConfigTemporaria -Destination $ConfigDestino -Force

Write-Host "PocketTTS local instalado e ativado. Reinicie a Gideon para aplicar a voz."
