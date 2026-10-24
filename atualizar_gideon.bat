@echo off
set "PROJECT_DIR=%~dp0"
set "PYTHON=%PROJECT_DIR%.venv\Scripts\python.exe"

"%PYTHON%" -m gideon.supervisor --update
if not errorlevel 1 exit /b 0

"%PYTHON%" -m gideon.supervisor --health
if not errorlevel 1 (
    echo [ERRO] Existe um backend da Gideon sem supervisor. Encerre-o antes de atualizar.
    exit /b 1
)

"%PYTHON%" -m gideon.atualizador
if errorlevel 1 exit /b 1
start "" "%PROJECT_DIR%.venv\Scripts\pythonw.exe" -m gideon.supervisor
exit /b 0
