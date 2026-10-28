"""Testes isolados do atualizador empacotado."""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import gideon.updater_exe as updater


def testar_reinicio_apos_atualizacao() -> None:
    with tempfile.TemporaryDirectory() as temporario:
        raiz = Path(temporario)
        instalador = raiz / "GideonSetup.exe"
        instalador.write_bytes(b"setup-verificado")
        hash_instalador = hashlib.sha256(instalador.read_bytes()).hexdigest()
        reinicios: list[tuple[str, bool]] = []

        run_original = updater.subprocess.run
        reiniciar_original = updater._reiniciar
        log_original = updater._log
        argv_original = sys.argv
        try:
            updater.subprocess.run = lambda *_args, **_kwargs: SimpleNamespace(returncode=0)
            updater._reiniciar = lambda caminho, *, background: reinicios.append((caminho, background))
            updater._log = lambda _mensagem: None
            argumentos = [
                "GideonUpdater.exe",
                "--installer",
                str(instalador),
                "--sha256",
                hash_instalador,
                "--restart",
                str(raiz / "Gideon.exe"),
                "--background",
                "--from-temp",
            ]
            sys.argv = argumentos
            assert updater.main() == 0
            assert reinicios == [(str(raiz / "Gideon.exe"), True)]

            reinicios.clear()
            argumentos[4] = "0" * 64
            sys.argv = argumentos
            assert updater.main() == 1
            assert reinicios == [(str(raiz / "Gideon.exe"), True)]
        finally:
            updater.subprocess.run = run_original
            updater._reiniciar = reiniciar_original
            updater._log = log_original
            sys.argv = argv_original

    print("[OK] Atualizador reinicia uma unica vez apos sucesso ou recusa.")


if __name__ == "__main__":
    testar_reinicio_apos_atualizacao()
