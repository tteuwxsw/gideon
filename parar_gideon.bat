@echo off
title Gideon - Encerrando Sistemas

echo ========================================================
echo   Encerrando processos da Gideon...
echo ========================================================

taskkill /F /IM Godot_v4.7.2-stable_win64.exe 2>nul
wmic process where "commandline like '%%gideon.servidor%%'" delete 2>nul

echo   [OK] Processos da Gideon encerrados.
echo.
