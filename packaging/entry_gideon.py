"""Entrada do executavel congelado principal da Gideon."""

from __future__ import annotations

import sys

from gideon.caminhos import DADOS_DIR


def _configurar_log() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    DADOS_DIR.mkdir(parents=True, exist_ok=True)
    arquivo = open(DADOS_DIR / "gideon_background.log", "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = arquivo
    if sys.stderr is None:
        sys.stderr = arquivo


def _remover_papel(papel: str) -> None:
    if papel in sys.argv:
        sys.argv.remove(papel)


def _self_test() -> int:
    import sqlite3
    import tempfile
    from pathlib import Path

    import av
    import ctranslate2
    import keyring
    import sounddevice
    import vosk

    from gideon.caminhos import WEB_DIR

    if not (WEB_DIR / "index.html").is_file():
        raise RuntimeError("Interface web ausente no pacote.")
    with tempfile.TemporaryDirectory(prefix="gideon-self-test-") as temporario:
        banco = sqlite3.connect(Path(temporario) / "teste.db")
        banco.execute("CREATE VIRTUAL TABLE busca USING fts5(texto)")
        banco.close()
    keyring.get_keyring()
    sounddevice.query_devices()
    vosk.SetLogLevel(-1)
    av.library_versions
    ctranslate2.get_supported_compute_types("cpu")
    return 0


def main() -> int:
    _configurar_log()
    if "--self-test" in sys.argv:
        return _self_test()
    if "--internal-server" in sys.argv:
        _remover_papel("--internal-server")
        from gideon.servidor import main as servidor_main

        servidor_main()
        return 0
    if "--internal-updater" in sys.argv:
        _remover_papel("--internal-updater")
        from gideon.atualizador import main as atualizador_main

        return atualizador_main()
    if "--internal-supervisor" in sys.argv:
        _remover_papel("--internal-supervisor")
    from gideon.supervisor import main as supervisor_main

    return supervisor_main()


if __name__ == "__main__":
    raise SystemExit(main())
