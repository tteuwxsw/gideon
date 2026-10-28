"""Testes isolados da CLI e dos processos invisiveis do Windows."""

from __future__ import annotations

import os

from gideon.cli import _comando_app, _comando_autostart, construir_parser, main
from gideon.processos_windows import opcoes_processo_oculto


def testar_parser() -> None:
    parser = construir_parser()
    comandos = {
        acao.dest
        for acao in parser._actions
    }
    assert "command" in comandos
    for comando in ("open", "start", "stop", "restart", "status", "update", "logs", "version"):
        args = parser.parse_args([comando])
        assert args.command == comando
        assert callable(args.handler)
    args = parser.parse_args(["autostart", "status"])
    assert args.command == "autostart"
    assert callable(args.handler)
    print("[OK] CLI expoe comandos explicitos sem iniciar o runtime durante o parse.")


def testar_comando_background() -> None:
    comando = _comando_app("--background")
    assert "--background" in comando
    assert any("gideon.supervisor" in parte or "Gideon.exe" in parte for parte in comando)
    print("[OK] CLI inicia o supervisor grafico em modo background.")


def testar_opcoes_ocultas() -> None:
    opcoes = opcoes_processo_oculto()
    if os.name == "nt":
        assert opcoes.get("creationflags", 0) != 0
        assert opcoes.get("startupinfo") is not None
    else:
        assert opcoes == {}
    print("[OK] Subprocessos internos usam configuracao sem janela no Windows.")

def testar_autostart_silencioso() -> None:
    comando = _comando_autostart()
    assert "headless" in comando or "wscript.exe" in comando.lower()
    print("[OK] Autostart usa launcher grafico sem console ou interface visivel.")



def testar_version(capsys=None) -> None:
    assert main(["version"]) == 0
    print("[OK] Comando version termina sem abrir a interface.")


if __name__ == "__main__":
    testar_parser()
    testar_comando_background()
    testar_opcoes_ocultas()
    testar_version()
    testar_autostart_silencioso()
