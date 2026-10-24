"""Atualizacao conservadora da instalacao da Gideon pelo repositorio privado."""

from __future__ import annotations

import ctypes
import os
import subprocess
import tempfile
from ctypes import wintypes
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
MUTEX_NAME = "Local\\GideonUpdater"
ERROR_ALREADY_EXISTS = 183


def _executar(
    comando: list[str],
    cwd: Path = ROOT_DIR,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        comando,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _adquirir_mutex():
    if os.name != "nt":
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle or ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        if handle:
            kernel32.CloseHandle(handle)
        return None
    return handle


def _liberar_mutex(handle) -> None:
    if os.name == "nt" and handle not in {None, True}:
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle(handle)


def _sincronizar_e_testar(diretorio: Path) -> str | None:
    sync = _executar(["uv", "sync", "--frozen"], cwd=diretorio, timeout=600)
    if sync.returncode != 0:
        return sync.stderr.strip() or "Falha ao sincronizar dependencias."

    teste = _executar(
        ["uv", "run", "python", "testes/teste_runtime.py"],
        cwd=diretorio,
        timeout=180,
    )
    if teste.returncode != 0:
        return teste.stdout.strip() or teste.stderr.strip() or "Falha no portao do runtime."
    teste_api = _executar(
        ["uv", "run", "python", "testes/teste_api_runtime.py"],
        cwd=diretorio,
        timeout=180,
    )
    if teste_api.returncode != 0:
        return (
            teste_api.stdout.strip()
            or teste_api.stderr.strip()
            or "Falha no portao HTTP do runtime."
        )
    return None


def atualizar() -> dict[str, Any]:
    """Aplica somente fast-forward e interrompe na primeira falha."""
    mutex = _adquirir_mutex()
    if mutex is None:
        return {"atualizado": False, "erro": "Outra atualizacao ja esta em andamento."}
    try:
        status = _executar(["git", "status", "--porcelain"])
        if status.returncode != 0:
            return {"atualizado": False, "erro": "Nao foi possivel verificar o repositorio."}
        if status.stdout.strip():
            return {
                "atualizado": False,
                "erro": "Existem modificacoes locais. A atualizacao foi cancelada para nao sobrescreve-las.",
            }

        fetch = _executar(["git", "fetch", "origin", "master"])
        if fetch.returncode != 0:
            return {"atualizado": False, "erro": fetch.stderr.strip() or "Falha no git fetch."}

        local = _executar(["git", "rev-parse", "HEAD"])
        remoto = _executar(["git", "rev-parse", "origin/master"])
        if local.returncode != 0 or remoto.returncode != 0:
            return {"atualizado": False, "erro": "Nao foi possivel comparar as versoes."}

        if local.stdout.strip() == remoto.stdout.strip():
            erro = _sincronizar_e_testar(ROOT_DIR)
            if erro:
                return {"atualizado": False, "erro": erro}
            return {"atualizado": False, "mensagem": "A Gideon ja esta atualizada e validada."}

        with tempfile.TemporaryDirectory(prefix="gideon-update-") as temporario:
            candidato = Path(temporario) / "candidato"
            clone = _executar(
                ["git", "clone", "--shared", "--no-checkout", str(ROOT_DIR), str(candidato)],
                timeout=300,
            )
            if clone.returncode != 0:
                return {"atualizado": False, "erro": "Falha ao preparar a versao candidata."}
            checkout = _executar(
                ["git", "checkout", "--detach", remoto.stdout.strip()],
                cwd=candidato,
            )
            if checkout.returncode != 0:
                return {"atualizado": False, "erro": "Falha ao abrir a versao candidata."}
            erro = _sincronizar_e_testar(candidato)
            if erro:
                return {"atualizado": False, "erro": f"Versao candidata recusada: {erro}"}

        merge = _executar(["git", "merge", "--ff-only", "origin/master"])
        if merge.returncode != 0:
            return {"atualizado": False, "erro": "A atualizacao nao e fast-forward e foi recusada."}

        erro = _sincronizar_e_testar(ROOT_DIR)
        if erro:
            rollback = _executar(["git", "reset", "--hard", local.stdout.strip()])
            reparo = _sincronizar_e_testar(ROOT_DIR) if rollback.returncode == 0 else "rollback falhou"
            return {
                "atualizado": False,
                "erro": (
                    f"A candidata passou, mas a instalacao falhou e foi restaurada: {erro}"
                    if reparo is None
                    else f"Falha pos-merge e restauracao incompleta: {erro}; {reparo}"
                ),
            }
        return {"atualizado": True, "mensagem": "Atualizacao instalada e validada."}
    finally:
        _liberar_mutex(mutex)


def main() -> int:
    resultado = atualizar()
    print(resultado.get("mensagem") or resultado.get("erro"))
    return 0 if resultado.get("mensagem") else 1


if __name__ == "__main__":
    raise SystemExit(main())
