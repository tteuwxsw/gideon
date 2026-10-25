"""Gerencia o ciclo de vida da Gideon e a integracao visual com o Windows."""

from __future__ import annotations

import ctypes
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DADOS_DIR = ROOT_DIR / "dados"
AVATAR_DIR = ROOT_DIR / "gideon_avatar"
UE5_DIR = ROOT_DIR / "gideon_ue5"
RUNTIME_FILE = DADOS_DIR / "runtime.json"
TOKEN_FILE = DADOS_DIR / "auth_token.txt"
RESTART_FILE = DADOS_DIR / "reiniciar.solicitado"
UPDATE_FILE = DADOS_DIR / "atualizar.solicitado"
LOG_FILE = DADOS_DIR / "gideon_supervisor.log"
COMPONENT_LOG_FILE = DADOS_DIR / "gideon_background.log"

MUTEX_NAME = "Local\\GideonSupervisor"
STOP_EVENT_NAME = "Local\\GideonStop"
ERROR_ALREADY_EXISTS = 183
WAIT_OBJECT_0 = 0
SAIR_REINICIANDO = 20
SAIR_BACKEND_FALHOU = 21

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
WM_CLOSE = 0x0010
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4


def calcular_estilo_overlay(estilo_atual: int) -> int:
    """Transforma uma janela comum em tool window que nao recebe foco."""
    return (estilo_atual | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW


def _log(mensagem: str) -> None:
    DADOS_DIR.mkdir(parents=True, exist_ok=True)
    instante = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as arquivo:
        arquivo.write(f"[{instante}] {mensagem}\n")


def _kernel32():
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _user32():
    return ctypes.WinDLL("user32", use_last_error=True)


def _criar_mutex_unico():
    kernel32 = _kernel32()
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
    kernel32 = _kernel32()
    kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    handle = kernel32.CreateEventW(None, True, False, STOP_EVENT_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def sinalizar_parada() -> bool:
    """Solicita que a instancia ativa encerre seus filhos e finalize."""
    if os.name != "nt":
        return False
    kernel32 = _kernel32()
    event_modify_state = 0x0002
    kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenEventW.restype = wintypes.HANDLE
    handle = kernel32.OpenEventW(event_modify_state, False, STOP_EVENT_NAME)
    if not handle:
        return False
    try:
        return bool(kernel32.SetEvent(handle))
    finally:
        kernel32.CloseHandle(handle)


def supervisor_ativo() -> bool:
    """Informa se existe uma instancia dona do evento de parada."""
    if os.name != "nt":
        return False
    kernel32 = _kernel32()
    synchronize = 0x00100000
    kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenEventW.restype = wintypes.HANDLE
    handle = kernel32.OpenEventW(synchronize, False, STOP_EVENT_NAME)
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def sinalizar_reinicio() -> bool:
    """Solicita parada e nova inicializacao depois que uma atualizacao termina."""
    DADOS_DIR.mkdir(parents=True, exist_ok=True)
    RESTART_FILE.write_text("1", encoding="ascii")
    if sinalizar_parada():
        return True
    RESTART_FILE.unlink(missing_ok=True)
    return False


def sinalizar_atualizacao() -> bool:
    """Agenda a atualizacao para depois que backend e avatar forem encerrados."""
    DADOS_DIR.mkdir(parents=True, exist_ok=True)
    UPDATE_FILE.write_text("1", encoding="ascii")
    if sinalizar_parada():
        return True
    UPDATE_FILE.unlink(missing_ok=True)
    return False


def _backend_ativo(timeout: float = 0.4) -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=timeout) as resposta:
            return resposta.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _localizar_ue5() -> Path | None:
    """Localiza o executavel empacotado do Unreal Engine 5 para o holograma da Gideon."""
    configurado = os.environ.get("GIDEON_UE5_EXE")
    candidatos = [
        Path(configurado) if configurado else None,
        UE5_DIR / "Build" / "Windows" / "GideonUE5.exe",
        UE5_DIR / "Build" / "Windows" / "GideonUE5" / "Binaries" / "Win64" / "GideonUE5-Win64-Shipping.exe",
        UE5_DIR / "Binaries" / "Win64" / "GideonUE5.exe",
    ]
    for candidato in candidatos:
        if candidato and candidato.is_file():
            return candidato
    return None


def _localizar_godot() -> tuple[Path | None, bool]:
    """Retorna (executavel, exportado) para o avatar Godot (fallback preservado)."""
    configurado = os.environ.get("GIDEON_AVATAR_EXE")
    candidatos_exportados = [
        Path(configurado) if configurado else None,
        AVATAR_DIR / "build" / "Gideon.exe",
    ]
    for candidato in candidatos_exportados:
        if candidato and candidato.is_file():
            return candidato, True

    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    pacote = local_app_data / "Microsoft" / "WinGet" / "Packages"
    candidatos = sorted(
        pacote.glob("GodotEngine.GodotEngine_*/*Godot_v*-stable_win64.exe"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    return (candidatos[0], False) if candidatos else (None, False)


def localizar_renderizador_avatar(preferencia: str | None = None) -> tuple[str, list[str]]:
    """Seleciona o motor grafico do avatar ('ue5' prioritario ou 'godot' para rollback/fallback).

    Respeita a variavel de ambiente GIDEON_RENDERER ('ue5', 'godot' ou 'auto').
    """
    modo = (preferencia or os.environ.get("GIDEON_RENDERER", "auto")).strip().lower()

    if modo in {"ue5", "unreal", "auto"}:
        exe_ue5 = _localizar_ue5()
        if exe_ue5:
            return (
                "ue5",
                [
                    str(exe_ue5),
                    "-dx11",
                    "-WINDOWED",
                    "-ResX=450",
                    "-ResY=650",
                    "-NoSplash",
                    "-NoVSync",
                ],
            )
        if modo in {"ue5", "unreal"}:
            raise FileNotFoundError(
                "Executavel Unreal Engine 5 (GideonUE5.exe) ainda nao foi compilado em gideon_ue5/Build/Windows/."
            )

    executavel_godot, exportado = _localizar_godot()
    if executavel_godot:
        cmd = [str(executavel_godot)]
        if not exportado:
            cmd.extend(["--path", str(AVATAR_DIR)])
        return ("godot", cmd)

    raise FileNotFoundError("Nenhum renderizador de avatar (Unreal Engine 5 ou Godot) foi encontrado.")


def _janelas_do_processo(pid: int) -> list[int]:
    user32 = _user32()
    encontradas: list[int] = []
    callback_tipo = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_tipo
    def callback(hwnd, _lparam):
        pid_janela = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_janela))
        if pid_janela.value == pid and user32.IsWindowVisible(hwnd):
            encontradas.append(int(hwnd))
        return True

    user32.EnumWindows(callback, 0)
    return encontradas


def aplicar_estilo_overlay(pid: int) -> bool:
    """Remove as janelas do avatar da barra de tarefas e do Alt+Tab."""
    if os.name != "nt":
        return False
    user32 = _user32()
    get_style = user32.GetWindowLongPtrW
    set_style = user32.SetWindowLongPtrW
    get_style.argtypes = [wintypes.HWND, ctypes.c_int]
    get_style.restype = ctypes.c_ssize_t
    set_style.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    set_style.restype = ctypes.c_ssize_t

    alterou = False
    for hwnd in _janelas_do_processo(pid):
        estilo_atual = int(get_style(hwnd, GWL_EXSTYLE))
        novo_estilo = calcular_estilo_overlay(estilo_atual)
        if estilo_atual == novo_estilo:
            alterou = True
            continue
        user32.ShowWindow(hwnd, SW_HIDE)
        set_style(hwnd, GWL_EXSTYLE, novo_estilo)
        user32.SetWindowPos(
            hwnd,
            None,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )
        user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        alterou = True
    return alterou


def _fechar_janelas(pid: int) -> None:
    user32 = _user32()
    for hwnd in _janelas_do_processo(pid):
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def _encerrar_processo(processo: subprocess.Popen | None, fechar_janela: bool = False) -> None:
    if not processo or processo.poll() is not None:
        return
    if fechar_janela:
        _fechar_janelas(processo.pid)
        try:
            processo.wait(timeout=4)
            return
        except subprocess.TimeoutExpired:
            pass
    processo.terminate()
    try:
        processo.wait(timeout=4)
    except subprocess.TimeoutExpired:
        processo.kill()


def _solicitar_parada_backend(token_runtime: str) -> None:
    requisicao = urllib.request.Request(
        "http://127.0.0.1:8000/api/runtime/shutdown",
        method="POST",
        headers={"X-Gideon-Runtime": token_runtime},
    )
    try:
        urllib.request.urlopen(requisicao, timeout=2).close()
    except (OSError, urllib.error.URLError):
        pass


def executar() -> int:
    if os.name != "nt":
        print("O supervisor da Gideon requer Windows.")
        return 1

    mutex = _criar_mutex_unico()
    if mutex is None:
        _log("Inicializacao ignorada: a Gideon ja esta ativa.")
        return 0

    kernel32 = _kernel32()
    evento_parada = _criar_evento_parada()
    token_runtime = secrets.token_urlsafe(32)
    backend: subprocess.Popen | None = None
    avatar: subprocess.Popen | None = None
    log_handle = None

    try:
        DADOS_DIR.mkdir(parents=True, exist_ok=True)
        RUNTIME_FILE.unlink(missing_ok=True)
        # Trunca logs antigos para nao preservar tokens que versões anteriores
        # colocavam acidentalmente em URLs.
        log_handle = COMPONENT_LOG_FILE.open("w", encoding="utf-8", buffering=1)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        if _backend_ativo():
            raise RuntimeError("A porta 8000 ja esta ocupada; o backend externo nao sera adotado.")

        ambiente = os.environ.copy()
        ambiente["GIDEON_RUNTIME_TOKEN"] = token_runtime
        backend = subprocess.Popen(
            [sys.executable, "-m", "gideon", "--voz"],
            cwd=ROOT_DIR,
            env=ambiente,
            stdout=log_handle,
            stderr=log_handle,
            creationflags=flags,
        )
        limite = time.monotonic() + 90
        while time.monotonic() < limite and not _backend_ativo():
            if backend.poll() is not None:
                raise RuntimeError("O backend da Gideon encerrou durante a inicializacao.")
            time.sleep(0.25)
        if not _backend_ativo():
            raise RuntimeError("O backend nao respondeu ao health check em 90 segundos.")

        motor_avatar, comando_avatar = localizar_renderizador_avatar()
        if motor_avatar == "ue5" and TOKEN_FILE.exists():
            try:
                token_txt = TOKEN_FILE.read_text(encoding="utf-8").strip()
                if token_txt:
                    comando_avatar.append(f"-token={token_txt}")
            except OSError:
                pass

        avatar = subprocess.Popen(
            comando_avatar,
            cwd=ROOT_DIR,
            env=ambiente,
            stdout=log_handle,
            stderr=log_handle,
        )

        limite_estilo = time.monotonic() + 35
        estabilizado_desde: float | None = None
        while time.monotonic() < limite_estilo and avatar.poll() is None:
            if aplicar_estilo_overlay(avatar.pid):
                if estabilizado_desde is None:
                    estabilizado_desde = time.monotonic()
                elif time.monotonic() - estabilizado_desde >= 5:
                    _log("Overlay integrado: removido da barra de tarefas e do Alt+Tab.")
                    break
            else:
                estabilizado_desde = None
            time.sleep(0.25)

        RUNTIME_FILE.write_text(
            json.dumps(
                {
                    "supervisor_pid": os.getpid(),
                    "backend_pid": backend.pid if backend else None,
                    "avatar_pid": avatar.pid,
                    "motor_avatar": motor_avatar,
                    "iniciado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        _log(f"Gideon iniciada sob supervisao (motor_avatar={motor_avatar}).")

        componente_falhou = False
        inicio_estavel = time.monotonic()
        while kernel32.WaitForSingleObject(evento_parada, 500) != WAIT_OBJECT_0:
            if backend.poll() is not None:
                componente_falhou = True
                _log("Backend encerrou inesperadamente; encerrando o avatar.")
                break
            if avatar.poll() is not None:
                componente_falhou = True
                _log("Avatar encerrou inesperadamente; reiniciando o conjunto.")
                break
            if time.monotonic() - inicio_estavel >= 60:
                os.environ["GIDEON_RESTART_COUNT"] = "0"

        reiniciar = RESTART_FILE.exists()
        atualizar = UPDATE_FILE.exists()
        RESTART_FILE.unlink(missing_ok=True)
        UPDATE_FILE.unlink(missing_ok=True)
        if atualizar:
            _log("Atualizacao solicitada; encerrando componentes antes de alterar arquivos.")
        elif reiniciar:
            _log("Reinicio solicitado.")
        elif not componente_falhou:
            _log("Parada solicitada; encerrando componentes.")
        _fechar_janelas(avatar.pid) if avatar and avatar.poll() is None else None
        if backend:
            _solicitar_parada_backend(token_runtime)
            try:
                backend.wait(timeout=6)
            except subprocess.TimeoutExpired:
                _encerrar_processo(backend)
        _encerrar_processo(avatar, fechar_janela=True)
        if atualizar:
            try:
                resultado_update = subprocess.run(
                    [sys.executable, "-m", "gideon.atualizador"],
                    cwd=ROOT_DIR,
                    stdout=log_handle,
                    stderr=log_handle,
                    timeout=1800,
                )
                atualizou = resultado_update.returncode == 0
            except subprocess.TimeoutExpired:
                atualizou = False
                _log("Atualizacao excedeu 30 minutos e foi interrompida.")
            _log(
                "Atualizacao concluida; reiniciando."
                if atualizou
                else "Atualizacao recusada ou falhou; reiniciando a versao disponivel."
            )
            return SAIR_REINICIANDO
        if componente_falhou:
            return SAIR_BACKEND_FALHOU
        return SAIR_REINICIANDO if reiniciar else 0
    except Exception as erro:
        _log(f"Falha no supervisor: {erro}")
        _encerrar_processo(avatar, fechar_janela=True)
        if backend:
            _solicitar_parada_backend(token_runtime)
            _encerrar_processo(backend)
        if backend is not None and not isinstance(erro, FileNotFoundError):
            return SAIR_BACKEND_FALHOU
        return 1
    finally:
        RUNTIME_FILE.unlink(missing_ok=True)
        if log_handle:
            log_handle.close()
        kernel32.CloseHandle(evento_parada)
        kernel32.CloseHandle(mutex)


def main() -> int:
    if "--stop" in sys.argv:
        return 0 if sinalizar_parada() else 1
    if "--restart" in sys.argv:
        return 0 if sinalizar_reinicio() else 1
    if "--update" in sys.argv:
        return 0 if sinalizar_atualizacao() else 1
    if "--health" in sys.argv:
        return 0 if _backend_ativo() else 1
    if "--delayed-start" in sys.argv:
        time.sleep(3)
    resultado = executar()
    if resultado in {SAIR_REINICIANDO, SAIR_BACKEND_FALHOU}:
        reinicios = int(os.environ.get("GIDEON_RESTART_COUNT", "0"))
        if resultado == SAIR_BACKEND_FALHOU and reinicios >= 3:
            _log("Backend falhou repetidamente; reinicio automatico suspenso.")
            return 1
        ambiente = os.environ.copy()
        ambiente["GIDEON_RESTART_COUNT"] = str(reinicios + 1 if resultado == SAIR_BACKEND_FALHOU else 0)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
        subprocess.Popen(
            [sys.executable, "-m", "gideon.supervisor", "--delayed-start"],
            cwd=ROOT_DIR,
            env=ambiente,
            creationflags=flags,
            close_fds=True,
        )
        return 0
    return resultado


if __name__ == "__main__":
    raise SystemExit(main())
