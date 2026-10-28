"""Iniciador leve em bandeja que desperta a Gideon por saudacao offline."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes

from PIL import Image, ImageDraw
import pystray

from gideon.caminhos import DADOS_DIR, FROZEN, INSTALL_DIR, ROOT_DIR
from gideon.supervisor import _backend_ativo, sinalizar_abertura, sinalizar_parada, supervisor_ativo
from gideon.voz.despertador import DespertadorOffline

MUTEX_NAME = "Local\\GideonWake"
STOP_EVENT_NAME = "Local\\GideonWakeStop"
ERROR_ALREADY_EXISTS = 183
WAIT_OBJECT_0 = 0
LOG_FILE = DADOS_DIR / "gideon_wake.log"


def _log(mensagem: str) -> None:
    DADOS_DIR.mkdir(parents=True, exist_ok=True)
    instante = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as arquivo:
        arquivo.write(f"[{instante}] {mensagem}\n")


def _criar_mutex():
    if os.name != "nt":
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return handle


def _criar_evento_parada():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    handle = kernel32.CreateEventW(None, True, False, STOP_EVENT_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def sinalizar_parada_wake() -> bool:
    if os.name != "nt":
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenEventW.restype = wintypes.HANDLE
    handle = kernel32.OpenEventW(0x0002, False, STOP_EVENT_NAME)
    if not handle:
        return False
    try:
        return bool(kernel32.SetEvent(handle))
    finally:
        kernel32.CloseHandle(handle)


def _comando_gideon(*argumentos: str) -> list[str]:
    if FROZEN:
        return [str(INSTALL_DIR / "Gideon.exe"), *argumentos]
    return [sys.executable, "-m", "gideon.supervisor", *argumentos]


def _iniciar_gideon(*argumentos: str) -> None:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        _comando_gideon(*argumentos),
        cwd=INSTALL_DIR if FROZEN else ROOT_DIR,
        creationflags=flags,
        close_fds=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def iniciar_nucleo() -> None:
    if not supervisor_ativo():
        _iniciar_gideon("--background")


def abrir_gideon() -> None:
    if not sinalizar_abertura():
        _iniciar_gideon("--open")


def _icone() -> Image.Image:
    imagem = Image.new("RGBA", (64, 64), (4, 8, 13, 255))
    desenho = ImageDraw.Draw(imagem)
    desenho.ellipse((10, 10, 54, 54), outline=(88, 210, 255, 255), width=4)
    desenho.ellipse((23, 23, 41, 41), fill=(88, 210, 255, 210))
    return imagem


class WakeLauncher:
    def __init__(self, evento_parada, *, mostrar_icone: bool = True):
        self.parar_evento = threading.Event()
        self.evento_parada = evento_parada
        self.icone = None
        if mostrar_icone:
            self.icone = pystray.Icon(
                "GideonWake",
                _icone(),
                "Gideon - ativacao por saudacao",
                menu=pystray.Menu(
                    pystray.MenuItem("Abrir Gideon", self._abrir, default=True),
                    pystray.MenuItem("Encerrar nucleo", self._encerrar_nucleo),
                    pystray.MenuItem("Sair completamente", self._sair),
                ),
            )

    def _abrir(self, _icone=None, _item=None) -> None:
        abrir_gideon()

    def _encerrar_nucleo(self, _icone=None, _item=None) -> None:
        sinalizar_parada()

    def _sair(self, _icone=None, _item=None) -> None:
        self.parar_evento.set()
        sinalizar_parada()
        if self.icone is not None:
            self.icone.stop()

    def _ao_despertar(self, saudacao: str) -> None:
        _log(f"Saudacao reconhecida: {saudacao}; abrindo Gideon.")
        abrir_gideon()

    def _loop_escuta(self) -> None:
        detector = DespertadorOffline(self._ao_despertar)
        while not self.parar_evento.is_set():
            if supervisor_ativo() or _backend_ativo(timeout=0.25):
                self.parar_evento.wait(1.0)
                continue
            try:
                disparou = detector.executar(self.parar_evento)
                if disparou:
                    limite = time.monotonic() + 90
                    while not self.parar_evento.is_set() and time.monotonic() < limite:
                        if _backend_ativo(timeout=0.4):
                            break
                        self.parar_evento.wait(0.5)
            except Exception as erro:
                _log(f"Escuta de despertar indisponivel: {erro}")
                self.parar_evento.wait(10.0)

    def _monitorar_parada_externa(self) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        if kernel32.WaitForSingleObject(self.evento_parada, 0xFFFFFFFF) == WAIT_OBJECT_0:
            self._sair()

    def executar(self) -> None:
        iniciar_nucleo()
        threading.Thread(target=self._loop_escuta, name="gideon-wake-listener", daemon=True).start()
        threading.Thread(target=self._monitorar_parada_externa, name="gideon-wake-stop", daemon=True).start()
        _log("Gideon Wake iniciado; nucleo solicitado em segundo plano.")
        if self.icone is not None:
            self.icone.run()
        else:
            self.parar_evento.wait()


def main() -> int:
    if os.name != "nt":
        return 1
    if "--stop" in sys.argv:
        sinalizou = sinalizar_parada_wake()
        sinalizar_parada()
        return 0 if sinalizou else 1
    mutex = _criar_mutex()
    if mutex is None:
        return 0
    evento_parada = _criar_evento_parada()
    try:
        WakeLauncher(evento_parada, mostrar_icone="--headless" not in sys.argv).executar()
        return 0
    finally:
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.CloseHandle(evento_parada)
        kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    raise SystemExit(main())
