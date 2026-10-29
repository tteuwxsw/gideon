"""Gerencia o ciclo de vida da Gideon no Windows e no Linux."""

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
import shutil
from ctypes import wintypes
from pathlib import Path

import psutil

from gideon.caminhos import DADOS_DIR, FROZEN, INSTALL_DIR, ROOT_DIR

RUNTIME_FILE = DADOS_DIR / "runtime.json"
RESTART_FILE = DADOS_DIR / "reiniciar.solicitado"
UPDATE_FILE = DADOS_DIR / "atualizar.solicitado"
LOG_FILE = DADOS_DIR / "gideon_supervisor.log"
COMPONENT_LOG_FILE = DADOS_DIR / "gideon_background.log"

MUTEX_NAME = "Local\\GideonSupervisor"
STOP_EVENT_NAME = "Local\\GideonStop"
OPEN_EVENT_NAME = "Local\\GideonOpenOrFocus"
LOCK_FILE = DADOS_DIR / "supervisor.lock"
STOP_SIGNAL_FILE = DADOS_DIR / "parar.sinal"
OPEN_SIGNAL_FILE = DADOS_DIR / "abrir.sinal"
ERROR_ALREADY_EXISTS = 183
WAIT_OBJECT_0 = 0
SAIR_REINICIANDO = 20
SAIR_BACKEND_FALHOU = 21

WM_CLOSE = 0x0010
SW_RESTORE = 9


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
    if os.name != "nt":
        import fcntl

        DADOS_DIR.mkdir(parents=True, exist_ok=True)
        handle = LOCK_FILE.open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return None
        return handle
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


def _criar_evento(nome: str, *, manual_reset: bool):
    if os.name != "nt":
        caminho = STOP_SIGNAL_FILE if nome == STOP_EVENT_NAME else OPEN_SIGNAL_FILE
        caminho.unlink(missing_ok=True)
        return caminho
    kernel32 = _kernel32()
    kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.ResetEvent.argtypes = [wintypes.HANDLE]
    kernel32.ResetEvent.restype = wintypes.BOOL
    handle = kernel32.CreateEventW(None, manual_reset, False, nome)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    kernel32.ResetEvent(handle)
    return handle


def _criar_evento_parada():
    return _criar_evento(STOP_EVENT_NAME, manual_reset=True)


def _criar_evento_abertura():
    return _criar_evento(OPEN_EVENT_NAME, manual_reset=False)


def _evento_disparado(evento, timeout_ms: int) -> bool:
    """Espera um evento Win32 ou um arquivo de sinal no Linux."""
    if os.name == "nt":
        return _kernel32().WaitForSingleObject(evento, timeout_ms) == WAIT_OBJECT_0
    limite = time.monotonic() + (timeout_ms / 1000)
    while True:
        if evento.exists():
            if evento == OPEN_SIGNAL_FILE:
                try:
                    dados = json.loads(evento.read_text(encoding="utf-8"))
                    for nome in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS"):
                        if dados.get(nome):
                            os.environ[nome] = str(dados[nome])
                except (OSError, ValueError):
                    pass
            evento.unlink(missing_ok=True)
            return True
        if timeout_ms == 0 or time.monotonic() >= limite:
            return False
        time.sleep(min(0.05, max(0.0, limite - time.monotonic())))


def _sinalizar_evento(nome: str) -> bool:
    if os.name != "nt":
        if not supervisor_ativo():
            return False
        DADOS_DIR.mkdir(parents=True, exist_ok=True)
        caminho = STOP_SIGNAL_FILE if nome == STOP_EVENT_NAME else OPEN_SIGNAL_FILE
        if nome == OPEN_EVENT_NAME:
            ambiente = {
                chave: os.environ.get(chave, "")
                for chave in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS")
            }
            caminho.write_text(json.dumps(ambiente), encoding="utf-8")
        else:
            caminho.write_text("1", encoding="ascii")
        return True
    kernel32 = _kernel32()
    event_modify_state = 0x0002
    kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenEventW.restype = wintypes.HANDLE
    handle = kernel32.OpenEventW(event_modify_state, False, nome)
    if not handle:
        return False
    try:
        return bool(kernel32.SetEvent(handle))
    finally:
        kernel32.CloseHandle(handle)


def sinalizar_parada() -> bool:
    """Solicita que a instancia ativa encerre seus filhos e finalize."""
    return _sinalizar_evento(STOP_EVENT_NAME)


def sinalizar_abertura() -> bool:
    """Solicita abertura ou foco da interface sem criar outra instancia."""
    return _sinalizar_evento(OPEN_EVENT_NAME)


def supervisor_ativo() -> bool:
    """Informa se existe uma instancia dona do evento de parada."""
    if os.name != "nt":
        import fcntl

        try:
            DADOS_DIR.mkdir(parents=True, exist_ok=True)
            with LOCK_FILE.open("a+") as handle:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    return False
                except BlockingIOError:
                    return True
        except OSError:
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


def sinalizar_atualizacao(manifesto: str | None = None) -> bool:
    """Agenda a atualizacao para depois que backend e aplicativo forem encerrados."""
    DADOS_DIR.mkdir(parents=True, exist_ok=True)
    UPDATE_FILE.write_text(manifesto or "1", encoding="utf-8")
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


def _localizar_navegador_app() -> Path | None:
    """Localiza Edge ou Chrome para abrir a interface como aplicativo desktop."""
    configurado = os.environ.get("GIDEON_BROWSER_EXE")
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    candidatos = [
        Path(configurado) if configurado else None,
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        local_app_data / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        local_app_data / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    if os.name != "nt":
        candidatos = [
            Path(configurado) if configurado else None,
            *(Path(p) for nome in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge") if (p := shutil.which(nome))),
        ]
    return next((candidato for candidato in candidatos if candidato and candidato.is_file()), None)


def _montar_comando_app(navegador: Path, perfil: Path, token_bootstrap: str) -> list[str]:
    """Monta a janela dedicada sem repassar segredos permanentes ao navegador."""
    return [
        str(navegador),
        f"--app=http://127.0.0.1:8000/#token={token_bootstrap}",
        f"--user-data-dir={perfil}",
        "--no-first-run",
        "--disable-background-mode",
        "--disable-session-crashed-bubble",
        "--disable-features=msEdgeSidebarV2",
    ]


def _comando_modulo(modulo: str, *args: str) -> list[str]:
    """Usa papeis internos quando congelado e modulos Python no desenvolvimento."""
    if FROZEN:
        papeis = {
            "gideon.servidor": "--internal-server",
            "gideon.atualizador": "--internal-updater",
            "gideon.supervisor": "--internal-supervisor",
        }
        return [sys.executable, papeis[modulo], *args]
    return [sys.executable, "-m", modulo, *args]


def _pids_do_processo(processo: subprocess.Popen | None) -> set[int]:
    if processo is None:
        return set()
    pids = {processo.pid}
    try:
        pids.update(filho.pid for filho in psutil.Process(processo.pid).children(recursive=True))
    except (psutil.Error, OSError):
        pass
    return pids


def _focar_interface(processo: subprocess.Popen | None) -> bool:
    if os.name != "nt":
        wmctrl = shutil.which("wmctrl")
        if not wmctrl:
            return False
        resultado = subprocess.run([wmctrl, "-a", "Gideon"], capture_output=True)
        return resultado.returncode == 0
    user32 = _user32()
    for pid in _pids_do_processo(processo):
        for hwnd in _janelas_do_processo(pid):
            user32.keybd_event(0x12, 0, 0, 0)
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            user32.keybd_event(0x12, 0, 2, 0)
            return True
    try:
        from gideon.tools.janelas import _obter_janelas_ativas
        for j in _obter_janelas_ativas():
            if j.get("titulo", "").strip() == "Gideon":
                hwnd = j["hwnd"]
                user32.keybd_event(0x12, 0, 0, 0)
                user32.ShowWindow(hwnd, SW_RESTORE)
                user32.SetForegroundWindow(hwnd)
                user32.keybd_event(0x12, 0, 2, 0)
                return True
    except Exception:
        pass
    return False


def _obter_novo_bootstrap(token_runtime: str) -> str:
    requisicao = urllib.request.Request(
        "http://127.0.0.1:8000/api/runtime/bootstrap",
        method="POST",
        headers={"X-Gideon-Runtime": token_runtime},
    )
    with urllib.request.urlopen(requisicao, timeout=3) as resposta:
        payload = json.loads(resposta.read().decode("utf-8"))
    token = str(payload.get("token") or "")
    if not token:
        raise RuntimeError("O backend nao forneceu um token de reabertura.")
    return token


def _abrir_interface(
    navegador: Path,
    perfil: Path,
    token_bootstrap: str,
    log_handle,
) -> subprocess.Popen:
    return subprocess.Popen(
        _montar_comando_app(navegador, perfil, token_bootstrap),
        cwd=INSTALL_DIR if FROZEN else ROOT_DIR,
        env=_ambiente_grafico(),
        stdout=log_handle,
        stderr=log_handle,
    )


def _ambiente_grafico() -> dict[str, str]:
    """Completa o ambiente gráfico mesmo após reinício do systemd --user."""
    ambiente = os.environ.copy()
    if os.name == "nt":
        return ambiente
    runtime = Path(f"/run/user/{os.getuid()}")
    ambiente.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime / 'bus'}")
    if not ambiente.get("WAYLAND_DISPLAY"):
        sockets = sorted(runtime.glob("wayland-*"))
        socket = next((p for p in sockets if not p.name.endswith(".lock")), None)
        if socket:
            ambiente["WAYLAND_DISPLAY"] = socket.name
    ambiente.setdefault("DISPLAY", ":0")
    if not ambiente.get("XAUTHORITY"):
        autoridades = sorted(runtime.glob(".mutter-Xwaylandauth.*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if autoridades:
            ambiente["XAUTHORITY"] = str(autoridades[0])
    return ambiente


def _gravar_runtime(backend: subprocess.Popen | None, app_process: subprocess.Popen | None) -> None:
    payload = {
        "supervisor_pid": os.getpid(),
        "backend_pid": backend.pid if backend and backend.poll() is None else None,
        "app_pid": app_process.pid if app_process and app_process.poll() is None else None,
        "interface": "visivel" if app_process and app_process.poll() is None else "oculta",
        "iniciado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    temporario = RUNTIME_FILE.with_suffix(".tmp")
    temporario.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporario.replace(RUNTIME_FILE)


def _janelas_do_processo(pid: int) -> list[int]:
    if os.name != "nt":
        return []
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


def _fechar_janelas(pid: int) -> None:
    if os.name != "nt":
        return
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


def executar(*, abrir_inicialmente: bool = True) -> int:
    mutex = _criar_mutex_unico()
    if mutex is None:
        if abrir_inicialmente:
            sinalizar_abertura()
        _log("Instancia existente sinalizada para abrir ou receber foco.")
        return 0

    kernel32 = _kernel32() if os.name == "nt" else None
    evento_parada = _criar_evento_parada()
    evento_abertura = _criar_evento_abertura()
    token_runtime = secrets.token_urlsafe(32)
    token_bootstrap = secrets.token_urlsafe(24)
    backend: subprocess.Popen | None = None
    app_process: subprocess.Popen | None = None
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
        ambiente["GIDEON_BOOTSTRAP_TOKEN"] = token_bootstrap
        backend = subprocess.Popen(
            _comando_modulo("gideon.servidor", "--voz"),
            cwd=INSTALL_DIR if FROZEN else ROOT_DIR,
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

        navegador = _localizar_navegador_app()
        if not navegador:
            raise FileNotFoundError("Microsoft Edge ou Google Chrome nao encontrado.")
        perfil_app = DADOS_DIR / "app-profile"
        perfil_app.mkdir(parents=True, exist_ok=True)
        if abrir_inicialmente:
            app_process = _abrir_interface(navegador, perfil_app, token_bootstrap, log_handle)
            _log("Aplicativo da Gideon iniciado em janela dedicada.")

        _gravar_runtime(backend, app_process)
        _log("Nucleo da Gideon iniciado sob supervisao.")

        componente_falhou = False
        inicio_estavel = time.monotonic()
        while not _evento_disparado(evento_parada, 500):
            if backend.poll() is not None:
                componente_falhou = True
                _log("Backend encerrou inesperadamente; encerrando o aplicativo.")
                break
            if app_process is not None and app_process.poll() is not None:
                app_process = None
                _gravar_runtime(backend, app_process)
                _log("Janela fechada; nucleo e voz continuam ativos em segundo plano.")
            if _evento_disparado(evento_abertura, 0):
                if not _focar_interface(app_process):
                    novo_token = _obter_novo_bootstrap(token_runtime)
                    app_process = _abrir_interface(navegador, perfil_app, novo_token, log_handle)
                    _gravar_runtime(backend, app_process)
                    _log("Interface reaberta por solicitacao local.")
            if time.monotonic() - inicio_estavel >= 60:
                os.environ["GIDEON_RESTART_COUNT"] = "0"

        reiniciar = RESTART_FILE.exists()
        atualizar = UPDATE_FILE.exists()
        manifesto_atualizacao = ""
        if atualizar:
            try:
                conteudo_atualizacao = UPDATE_FILE.read_text(encoding="utf-8").strip()
                if conteudo_atualizacao != "1":
                    manifesto_atualizacao = conteudo_atualizacao
            except OSError:
                pass
        RESTART_FILE.unlink(missing_ok=True)
        UPDATE_FILE.unlink(missing_ok=True)
        if atualizar:
            _log("Atualizacao solicitada; encerrando componentes antes de alterar arquivos.")
        elif reiniciar:
            _log("Reinicio solicitado.")
        elif not componente_falhou:
            _log("Parada solicitada; encerrando componentes.")
        _fechar_janelas(app_process.pid) if app_process and app_process.poll() is None else None
        if backend:
            _solicitar_parada_backend(token_runtime)
            try:
                backend.wait(timeout=6)
            except subprocess.TimeoutExpired:
                _encerrar_processo(backend)
        _encerrar_processo(app_process, fechar_janela=True)
        if atualizar:
            if FROZEN:
                updater = INSTALL_DIR / "GideonUpdater.exe"
                if not updater.is_file():
                    _log("GideonUpdater.exe nao encontrado; atualizacao cancelada.")
                    return SAIR_REINICIANDO
                flags_update = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
                    subprocess, "DETACHED_PROCESS", 0
                )
                argumentos_update = [
                    str(updater), "--wait-pid", str(os.getpid()),
                    "--restart", str(INSTALL_DIR / "Gideon.exe"),
                ]
                if manifesto_atualizacao:
                    argumentos_update.extend(["--manifest", manifesto_atualizacao])
                if not abrir_inicialmente:
                    argumentos_update.append("--background")
                subprocess.Popen(
                    argumentos_update,
                    cwd=INSTALL_DIR,
                    creationflags=flags_update,
                    close_fds=True,
                )
                _log("Atualizador externo iniciado.")
                return 0
            try:
                resultado_update = subprocess.run(
                    _comando_modulo("gideon.atualizador"),
                    cwd=INSTALL_DIR if FROZEN else ROOT_DIR,
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
        _encerrar_processo(app_process, fechar_janela=True)
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
        if os.name == "nt":
            kernel32.CloseHandle(evento_parada)
            kernel32.CloseHandle(evento_abertura)
            kernel32.CloseHandle(mutex)
        else:
            STOP_SIGNAL_FILE.unlink(missing_ok=True)
            OPEN_SIGNAL_FILE.unlink(missing_ok=True)
            mutex.close()


def main() -> int:
    if "--stop" in sys.argv:
        return 0 if sinalizar_parada() else 1
    if "--open" in sys.argv and sinalizar_abertura():
        return 0
    if "--restart" in sys.argv:
        return 0 if sinalizar_reinicio() else 1
    if "--update" in sys.argv:
        return 0 if sinalizar_atualizacao() else 1
    if "--health" in sys.argv:
        return 0 if _backend_ativo() else 1
    if "--delayed-start" in sys.argv:
        time.sleep(3)
    abrir_inicialmente = "--background" not in sys.argv
    resultado = executar(abrir_inicialmente=abrir_inicialmente)
    if resultado in {SAIR_REINICIANDO, SAIR_BACKEND_FALHOU}:
        # Sob systemd o processo não deve criar um filho órfão: um código de
        # falha pede ao próprio gerenciador que reinicie a unidade e continue
        # acompanhando o PID correto.
        if os.environ.get("GIDEON_MANAGED_BY_SYSTEMD") == "1":
            return 75 if resultado == SAIR_REINICIANDO else 1
        reinicios = int(os.environ.get("GIDEON_RESTART_COUNT", "0"))
        if resultado == SAIR_BACKEND_FALHOU and reinicios >= 3:
            _log("Backend falhou repetidamente; reinicio automatico suspenso.")
            return 1
        ambiente = os.environ.copy()
        ambiente["GIDEON_RESTART_COUNT"] = str(reinicios + 1 if resultado == SAIR_BACKEND_FALHOU else 0)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
        argumentos_reinicio = ["--delayed-start"]
        if not abrir_inicialmente:
            argumentos_reinicio.append("--background")
        subprocess.Popen(
            _comando_modulo("gideon.supervisor", *argumentos_reinicio),
            cwd=INSTALL_DIR if FROZEN else ROOT_DIR,
            env=ambiente,
            creationflags=flags,
            start_new_session=os.name != "nt",
            close_fds=True,
        )
        return 0
    return resultado


if __name__ == "__main__":
    raise SystemExit(main())
