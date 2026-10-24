@echo off
set "PROJECT_DIR=%~dp0"
set "PYTHONW=%PROJECT_DIR%.venv\Scripts\pythonw.exe"

if not exist "%PYTHONW%" (
    echo [ERRO] Ambiente Python da Gideon nao encontrado.
    exit /b 1
)

start "" "%PYTHONW%" -m gideon.supervisor
exit /b 0
