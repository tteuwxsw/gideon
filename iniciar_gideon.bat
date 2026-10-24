@echo off
chcp 65001 > nul
title Gideon — Inicializando Sistemas

set "PROJECT_DIR=%~dp0"
set "PYTHONW=%PROJECT_DIR%.venv\Scripts\pythonw.exe"
set "GODOT_EXE=%LOCALAPPDATA%\Microsoft\WinGet\Packages\GodotEngine.GodotEngine_Microsoft.Winget.Source_8wekyb3d8bbwe\Godot_v4.7.2-stable_win64.exe"

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║           GIDEON — Assistente Pessoal                ║
echo  ╠══════════════════════════════════════════════════════╣
echo  ║  Iniciando Cérebro, Voz e Holograma 3D...            ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

:: 1. Inicia o servidor Python com voz em segundo plano (sem janela preta)
start "" "%PYTHONW%" -m gideon.servidor --voz

:: 2. Aguarda 1.5s para o servidor subir
timeout /t 2 /nobreak > nul

:: 3. Inicia o Holograma no Godot 4
if exist "%GODOT_EXE%" (
    start "" "%GODOT_EXE%" --path "%PROJECT_DIR%gideon_avatar"
    echo  [✓] Holograma 3D e Cérebro ativos!
    echo  [✓] Fale "Gideon" para conversar.
) else (
    echo  [!] Executável do Godot não encontrado em: %GODOT_EXE%
    echo  [✓] Cérebro e voz continuam ativos em segundo plano.
)

timeout /t 3 > nul
