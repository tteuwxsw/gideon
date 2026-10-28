# Registra Gideon para iniciar no boot do Windows (invisível, sem ícone)
# Execute como Administrador: Right-click > Run with PowerShell

# Detecta o diretório do script
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VBSScript = "$ProjectDir\iniciar_gideon_invisivel.vbs"
$TaskName = "GideonAutoStart"
$TaskDescription = "Inicia Gideon no boot do Windows - invisível e sem ícone na bandeja"

# Verifica se rodando como Admin
$isAdmin = [bool]([System.Security.Principal.WindowsIdentity]::GetCurrent().Groups -match "S-1-5-32-544")
if (-not $isAdmin) {
    Write-Host "ERRO: Execute como Administrador!" -ForegroundColor Red
    Write-Host "Clique com botão direito e escolha 'Run with PowerShell'" -ForegroundColor Yellow
    exit 1
}

# Verifica se o VBS existe
if (-not (Test-Path $VBSScript)) {
    Write-Host "ERRO: Arquivo $VBSScript não encontrado!" -ForegroundColor Red
    exit 1
}

Write-Host "Registrando Gideon como tarefa de autostart..." -ForegroundColor Cyan

# Remove tarefa anterior se existir
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
}
catch {
    # Ignora erros se a tarefa não existe
}

# Criar ação: rodar o VBS silenciosamente
$Action = New-ScheduledTaskAction `
    -Execute "cscript.exe" `
    -Argument "`"$VBSScript`"" `
    -WorkingDirectory $ProjectDir

# Trigger: no boot do Windows
$Trigger = New-ScheduledTaskTrigger -AtStartup

# Configurações: rodar invisível, mesmo offline, com prioridade normal
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -WakeToRun:$false

# Registra a tarefa (sem necessidade de login do usuário)
Register-ScheduledTask `
    -TaskName $TaskName `
    -Description $TaskDescription `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "✓ Tarefa registrada com sucesso!" -ForegroundColor Green
Write-Host "  Nome: $TaskName" -ForegroundColor Gray
Write-Host "  Acionador: Boot do Windows" -ForegroundColor Gray
Write-Host "  Execução: Invisível, sem ícone, sem trace" -ForegroundColor Gray
Write-Host "" -ForegroundColor White
Write-Host "Gideon iniciará automaticamente no próximo boot." -ForegroundColor Cyan
Write-Host "Ative a audição por voz e fale a palavra-chave para abrir!" -ForegroundColor Cyan
