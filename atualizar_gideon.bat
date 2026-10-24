@echo off
title Gideon - Atualizacao de Sistemas

echo ========================================================
echo           GIDEON - Atualizacao de Sistemas
echo ========================================================
echo.

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo [1/3] Verificando atualizacoes no repositorio...
git pull

echo.
echo [2/3] Atualizando dependencias e pacotes...
uv sync

echo.
echo [3/3] Validando testes de seguranca...
uv run python testes/teste_gideon.py

echo.
echo ========================================================
echo   [OK] Gideon atualizada e pronta com sucesso!
echo ========================================================
echo.
pause
