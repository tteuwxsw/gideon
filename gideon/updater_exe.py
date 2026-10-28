"""Atualizador independente para instaladores assinados da Gideon."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from gideon.caminhos import DADOS_DIR, INSTALL_DIR

LOG_FILE = DADOS_DIR / "gideon_updater.log"


def _log(mensagem: str) -> None:
    DADOS_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as arquivo:
        arquivo.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {mensagem}\n")


def _esperar_pid(pid: int | None, timeout_s: float = 60.0) -> None:
    if not pid:
        return
    limite = time.monotonic() + timeout_s
    while time.monotonic() < limite:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.25)
    raise TimeoutError("O processo da Gideon nao encerrou para a atualizacao.")


def _sha256(caminho: Path) -> str:
    hash_obj = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            hash_obj.update(bloco)
    return hash_obj.hexdigest()


def _baixar(url: str, destino: Path) -> None:
    if not url.lower().startswith("https://"):
        raise ValueError("A atualizacao exige HTTPS.")
    with urllib.request.urlopen(url, timeout=30) as resposta, destino.open("wb") as arquivo:
        shutil.copyfileobj(resposta, arquivo)


def _carregar_manifesto(origem: str) -> dict:
    if origem.lower().startswith("https://"):
        with urllib.request.urlopen(origem, timeout=15) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    return json.loads(Path(origem).read_text(encoding="utf-8"))


def _copiar_para_temporario(args: list[str]) -> int:
    if not getattr(sys, "frozen", False) or "--from-temp" in args:
        return -1
    destino = Path(tempfile.gettempdir()) / f"GideonUpdater-{os.getpid()}.exe"
    shutil.copy2(sys.executable, destino)
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    argumentos = [arg for arg in args if arg != "--from-temp"]
    subprocess.Popen([str(destino), "--from-temp", *argumentos], creationflags=flags, close_fds=True)
    return 0


def _reiniciar(caminho: str, *, background: bool) -> None:
    executavel = Path(caminho)
    if not executavel.is_file():
        return
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    modo = "--background" if background else "--open"
    subprocess.Popen([str(executavel), modo], creationflags=flags, close_fds=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=os.environ.get("GIDEON_UPDATE_MANIFEST", ""))
    parser.add_argument("--installer")
    parser.add_argument("--sha256")
    parser.add_argument("--wait-pid", type=int)
    parser.add_argument("--restart", default=str(INSTALL_DIR / "Gideon.exe"))
    parser.add_argument("--from-temp", action="store_true")
    parser.add_argument("--background", action="store_true")
    args = parser.parse_args()

    copia = _copiar_para_temporario(sys.argv[1:])
    if copia >= 0:
        return copia

    try:
        _esperar_pid(args.wait_pid)
        instalador: Path
        hash_esperado = args.sha256 or ""
        if args.installer:
            instalador = Path(args.installer).resolve()
        elif args.manifest:
            manifesto = _carregar_manifesto(args.manifest)
            hash_esperado = str(manifesto["installer_sha256"]).lower()
            instalador = Path(tempfile.gettempdir()) / "GideonSetup-update.exe"
            _baixar(str(manifesto["installer_url"]), instalador)
        else:
            raise RuntimeError("Nenhuma fonte de atualizacao foi configurada.")

        if not instalador.is_file():
            raise FileNotFoundError("Instalador de atualizacao nao encontrado.")
        if not hash_esperado:
            raise RuntimeError("O SHA-256 do instalador e obrigatorio.")
        if _sha256(instalador).lower() != hash_esperado.lower():
            raise RuntimeError("O instalador baixado falhou na verificacao SHA-256.")

        resultado = subprocess.run(
            [str(instalador), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
            timeout=900,
        )
        if resultado.returncode != 0:
            raise RuntimeError(f"O instalador retornou o codigo {resultado.returncode}.")
        _log("Atualizacao instalada com sucesso.")
        _reiniciar(args.restart, background=args.background)
        return 0
    except Exception as erro:
        _reiniciar(args.restart, background=args.background)
        _log(f"Atualizacao recusada: {erro}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
