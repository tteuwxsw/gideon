@echo off
title Gideon - Inicializando Sistemas

set "PROJECT_DIR=%~dp0"
set "PYTHONW=%PROJECT_DIR%.venv\Scripts\pythonw.exe"
set "GODOT_EXE=%LOCALAPPDATA%\Microsoft\WinGet\Packages\GodotEngine.GodotEngine_Microsoft.Winget.Source_8wekyb3d8bbwe\Godot_v4.7.2-stable_win64.exe"

echo ========================================================
echo           GIDEON - Assistente Pessoal
echo ========================================================
echo   Iniciando Cerebro, Voz e Holograma 3D...
echo ========================================================
echo.

:: 1. Inicia o servidor Python com voz em segundo plano (sem janela preta)
start "" "%PYTHONW%" -m gideon.servidor --voz

:: 2. Inicia o Holograma no Godot 4
if exist "%GODOT_EXE%" (
    start "" "%GODOT_EXE%" --path "%PROJECT_DIR%gideon_avatar"
    echo   [OK] Holograma 3D e Cerebro iniciados com sucesso!
    echo   [OK] Fale "Gideon" para conversar.
) else (
    echo   [!] Executavel do Godot nao encontrado em: %GODOT_EXE%
    echo   [OK] Cerebro e voz continuam ativos em segundo plano.
)

echo.
