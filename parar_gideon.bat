@echo off
set "PROJECT_DIR=%~dp0"
set "PYTHON=%PROJECT_DIR%.venv\Scripts\python.exe"

"%PYTHON%" -m gideon.supervisor --stop
if errorlevel 1 (
    echo [AVISO] Nenhum supervisor da Gideon estava ativo.
    exit /b 1
)
echo [OK] Encerramento cooperativo solicitado.
exit /b 0
