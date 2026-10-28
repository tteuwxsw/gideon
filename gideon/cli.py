"""CLI de controle do subsistema Gideon para Windows."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from gideon.caminhos import DADOS_DIR, FROZEN, INSTALL_DIR, ROOT_DIR
from gideon.supervisor import (
    RUNTIME_FILE,
    _backend_ativo,
    sinalizar_abertura,
    sinalizar_atualizacao,
    sinalizar_parada,
    sinalizar_reinicio,
    supervisor_ativo,
)
from gideon.versao import VERSAO


def _emitir(mensagem: str, *, json_output: bool = False, **dados) -> None:
    if json_output:
        print(json.dumps({"mensagem": mensagem, **dados}, ensure_ascii=False))
    else:
        print(mensagem)


def _comando_app(*argumentos: str) -> list[str]:
    if FROZEN:
        return [str(INSTALL_DIR / "Gideon.exe"), *argumentos]
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    executavel = pythonw if os.name == "nt" and pythonw.is_file() else Path(sys.executable)
    return [str(executavel), "-m", "gideon.supervisor", *argumentos]


def _iniciar_app(*argumentos: str) -> None:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        _comando_app(*argumentos),
        cwd=INSTALL_DIR if FROZEN else ROOT_DIR,
        creationflags=flags,
        close_fds=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _aguardar(condicao, *, timeout: float) -> bool:
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if condicao():
            return True
        time.sleep(0.15)
    return bool(condicao())


def _estado() -> dict:
    runtime = {}
    try:
        runtime = json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {
        "versao": VERSAO,
        "supervisor": supervisor_ativo(),
        "backend": _backend_ativo(),
        "interface": runtime.get("interface", "desconhecida"),
        "supervisor_pid": runtime.get("supervisor_pid"),
        "backend_pid": runtime.get("backend_pid"),
        "app_pid": runtime.get("app_pid"),
    }


def _cmd_open(args) -> int:
    if not sinalizar_abertura():
        _iniciar_app("--open")
    pronto = not args.wait or _aguardar(_backend_ativo, timeout=args.timeout)
    _emitir("Gideon aberta." if pronto else "O nucleo nao respondeu a tempo.", json_output=args.json, ok=pronto)
    return 0 if pronto else 1


def _cmd_start(args) -> int:
    if supervisor_ativo():
        pronto = not args.wait or _aguardar(_backend_ativo, timeout=args.timeout)
        mensagem = "O nucleo Gideon ja esta ativo." if pronto else "O nucleo ainda nao respondeu."
        _emitir(mensagem, json_output=args.json, ok=pronto)
        return 0 if pronto else 1
    _iniciar_app("--background")
    pronto = not args.wait or _aguardar(_backend_ativo, timeout=args.timeout)
    _emitir("Nucleo iniciado em segundo plano." if pronto else "O nucleo nao respondeu a tempo.", json_output=args.json, ok=pronto)
    return 0 if pronto else 1


def _cmd_stop(args) -> int:
    if not supervisor_ativo():
        _emitir("O nucleo Gideon ja esta parado.", json_output=args.json, ok=True)
        return 0
    if not sinalizar_parada():
        _emitir("Nao foi possivel solicitar a parada.", json_output=args.json, ok=False)
        return 1
    parado = not args.wait or _aguardar(lambda: not supervisor_ativo() and not _backend_ativo(), timeout=args.timeout)
    _emitir("Nucleo encerrado." if parado else "A parada excedeu o tempo limite.", json_output=args.json, ok=parado)
    return 0 if parado else 1


def _cmd_restart(args) -> int:
    estado_anterior = _estado()
    pid_anterior = estado_anterior["supervisor_pid"] if estado_anterior["supervisor"] else None
    if estado_anterior["supervisor"]:
        solicitado = sinalizar_reinicio()
    else:
        _iniciar_app("--background" if args.background else "--open")
        solicitado = True
    pronto = solicitado
    if pronto and args.wait:
        if pid_anterior:
            pronto = _aguardar(
                lambda: _estado()["supervisor_pid"] not in {None, pid_anterior} and _backend_ativo(),
                timeout=args.timeout,
            )
        else:
            pronto = _aguardar(_backend_ativo, timeout=args.timeout)
    _emitir("Reinicio solicitado." if pronto else "Nao foi possivel reiniciar.", json_output=args.json, ok=pronto)
    return 0 if pronto else 1


def _cmd_status(args) -> int:
    estado = _estado()
    if args.json:
        print(json.dumps(estado, ensure_ascii=False))
    else:
        print(f"Gideon {estado['versao']}")
        print(f"  Supervisor: {'ativo' if estado['supervisor'] else 'parado'}")
        print(f"  Backend:    {'online' if estado['backend'] else 'offline'}")
        print(f"  Interface:  {estado['interface']}")
    return 0 if estado["backend"] else 1


def _cmd_update(args) -> int:
    if args.manifest and not args.manifest.lower().startswith("https://"):
        _emitir("O manifesto de atualizacao deve usar HTTPS.", json_output=args.json, ok=False)
        return 1
    solicitado = (
        sinalizar_atualizacao(args.manifest or None) if supervisor_ativo() else False
    )
    _emitir(
        "Atualizacao agendada." if solicitado else "Inicie a Gideon antes de solicitar atualizacao.",
        json_output=args.json,
        ok=solicitado,
    )
    return 0 if solicitado else 1


def _cmd_logs(args) -> int:
    arquivo = DADOS_DIR / ("gideon_background.log" if args.component == "backend" else "gideon_supervisor.log")
    if args.path:
        print(arquivo)
        return 0
    try:
        linhas = arquivo.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        print(f"Log ainda nao existe: {arquivo}", file=sys.stderr)
        return 1
    print("\n".join(linhas[-args.tail:]))
    return 0


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "Gideon"


def _comando_autostart() -> str:
    if FROZEN:
        return f'"{INSTALL_DIR / "GideonWake.exe"}" --headless'
    return f'wscript.exe "{ROOT_DIR / "iniciar_gideon_silencioso.vbs"}"'


def _cmd_autostart(args) -> int:
    if os.name != "nt":
        _emitir("A inicializacao automatica requer Windows.", json_output=args.json, ok=False)
        return 1

    import winreg

    comando = _comando_autostart()
    if args.action == "enable":
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as chave:
            winreg.SetValueEx(chave, RUN_VALUE, 0, winreg.REG_SZ, comando)
    elif args.action == "disable":
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as chave:
                winreg.DeleteValue(chave, RUN_VALUE)
        except FileNotFoundError:
            pass

    ativo = False
    valor = ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as chave:
            valor = str(winreg.QueryValueEx(chave, RUN_VALUE)[0])
            ativo = bool(valor)
    except FileNotFoundError:
        pass

    if args.action == "status":
        mensagem = "Inicializacao automatica ativa." if ativo else "Inicializacao automatica desativada."
    elif args.action == "enable":
        mensagem = "Gideon sera iniciada silenciosamente no proximo login."
    else:
        mensagem = "Inicializacao automatica removida."
    _emitir(mensagem, json_output=args.json, ok=True, ativo=ativo, comando=valor)
    return 0


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gideon", description="Controle do subsistema pessoal Gideon")
    parser.add_argument("--version", action="version", version=f"Gideon {VERSAO}")
    sub = parser.add_subparsers(dest="command")

    def comando(nome: str, ajuda: str, handler):
        item = sub.add_parser(nome, help=ajuda)
        item.set_defaults(handler=handler)
        return item

    def espera(item):
        item.add_argument("--wait", action=argparse.BooleanOptionalAction, default=True)
        item.add_argument("--timeout", type=float, default=30.0)
        item.add_argument("--json", action="store_true")

    abrir = comando("open", "abre ou foca a interface", _cmd_open)
    espera(abrir)
    iniciar = comando("start", "inicia o nucleo silenciosamente", _cmd_start)
    espera(iniciar)
    parar = comando("stop", "encerra todo o nucleo", _cmd_stop)
    espera(parar)
    reiniciar = comando("restart", "reinicia o nucleo", _cmd_restart)
    espera(reiniciar)
    reiniciar.add_argument("--background", action="store_true")
    status = comando("status", "mostra processos e saude", _cmd_status)
    status.add_argument("--json", action="store_true")
    update = comando("update", "agenda uma atualizacao segura", _cmd_update)
    update.add_argument("--json", action="store_true")
    update.add_argument("--manifest")
    logs = comando("logs", "mostra os logs recentes", _cmd_logs)
    logs.add_argument("--tail", type=int, default=80)
    logs.add_argument("--path", action="store_true")
    logs.add_argument("--component", choices=("supervisor", "backend"), default="supervisor")
    comando("version", "mostra a versao", lambda _args: print(VERSAO) or 0)
    autostart = comando("autostart", "controla a inicializacao silenciosa no login", _cmd_autostart)
    autostart.add_argument("action", choices=("enable", "disable", "status"))
    autostart.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    if not args.command:
        args = parser.parse_args(["open"])
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
