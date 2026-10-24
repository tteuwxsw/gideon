@echo off
chcp 65001 > nul
title Gideon — Encerrando Sistemas

echo.
echo  Encerrando processos da Gideon...
taskkill /F /IM Godot_v4.7.2-stable_win64.exe 2>nul
taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq Gideon*" 2>nul
wmic process where "commandline like '%%gideon.servidor%%'" delete 2>nul

echo  [✓] Gideon encerrada com sucesso.
timeout /t 2 > nul
