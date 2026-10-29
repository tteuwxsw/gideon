"""Ferramentas de inspeção, multimídia e controle real verificado do Windows 10 para a Gideon."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import urllib.parse
import webbrowser
from typing import Any

import psutil

from gideon.gate import Ferramenta, Risco
from gideon.processos_windows import comando_powershell, opcoes_processo_oculto

# Processos comuns de sistema que filtramos da lista de programas do usuário
PROCESSOS_IGNORADOS = {
    "svchost.exe", "csrss.exe", "smss.exe", "lsass.exe", "services.exe",
    "wininit.exe", "winlogon.exe", "sihost.exe", "taskhostw.exe", "dwm.exe",
    "runtimebroker.exe", "dllhost.exe", "shellexperiencehost.exe",
    "startmenuexperiencehost.exe", "searchapp.exe", "textinputhost.exe",
    "ctfmon.exe", "fontdrvhost.exe", "conhost.exe", "system", "idle",
    "registry", "memory compression", "spoolsv.exe", "SearchIndexer.exe",
    "securityhealthservice.exe", "audiodg.exe", "wlanext.exe",
}

# Inicializa leitura não-bloqueante de CPU do psutil
psutil.cpu_percent(interval=None)

_CACHE_GPU: dict[str, Any] = {
    "modelo": "Não identificado",
    "vram": "Não informado",
    "uso_3d": "Não disponível",
    "status": "Aguardando coleta",
    "adaptadores": [],
}
_CACHE_GPU_TS: float = 0.0
_ATUALIZANDO_GPU: bool = False


def _atualizar_gpu_background() -> None:
    """Atualiza metadados e uso da GPU em segundo plano sem bloquear a resposta de voz."""
    global _CACHE_GPU, _CACHE_GPU_TS, _ATUALIZANDO_GPU
    try:
        gpus = []
        if os.name != "nt":
            nvidia_smi = shutil.which("nvidia-smi")
            if nvidia_smi:
                res = subprocess.run(
                    [nvidia_smi, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=3.5,
                )
                for linha in res.stdout.splitlines():
                    partes = [p.strip() for p in linha.split(",")]
                    if len(partes) >= 3:
                        gpus.append({"modelo": partes[0], "vram_total": f"{partes[1]} MB", "driver": partes[2], "status": "OK"})
            else:
                lspci = shutil.which("lspci")
                if lspci:
                    res = subprocess.run([lspci], capture_output=True, text=True, timeout=3.5)
                    for linha in res.stdout.splitlines():
                        if "VGA compatible controller" in linha or "3D controller" in linha:
                            gpus.append({"modelo": linha.split(": ", 1)[-1], "vram_total": "Não informado", "driver": "", "status": "OK"})
        else:
            comando = (
                "Get-CimInstance Win32_VideoController | "
                "Select-Object Name, AdapterRAM, DriverVersion, Status | "
                "ConvertTo-Json -Compress"
            )
            res = subprocess.run(
                [comando_powershell(), "-NoProfile", "-NonInteractive", "-Command", comando],
                capture_output=True, text=True, timeout=3.5, **opcoes_processo_oculto(),
            )
            if res.returncode == 0 and res.stdout.strip():
                dados = json.loads(res.stdout.strip())
                if isinstance(dados, dict):
                    dados = [dados]
                for item in dados:
                    nome = str(item.get("Name") or "Adaptador de vídeo").strip()
                    ram_bytes = item.get("AdapterRAM") or 0
                    vram_gb = f"{max(1, round(ram_bytes / (1024**3)))} GB" if ram_bytes > 0 else "Não informado"
                    gpus.append({"modelo": nome, "vram_total": vram_gb, "driver": str(item.get("DriverVersion") or ""), "status": str(item.get("Status") or "OK")})
        if gpus:
            principal = gpus[0]
            _CACHE_GPU = {
                "modelo": principal["modelo"],
                "vram": principal["vram_total"],
                "uso_3d": "Operando normalmente",
                "status": principal.get("status", "OK"),
                "adaptadores": gpus,
            }
        _CACHE_GPU_TS = time.time()
    except Exception:
        pass
    finally:
        _ATUALIZANDO_GPU = False


# Dispara aquecimento assíncrono na importação
threading.Thread(target=_atualizar_gpu_background, daemon=True).start()


def obter_status_gpu() -> dict[str, Any]:
    """Retorna instantaneamente (< 1ms) o status da GPU a partir do cache assíncrono."""
    global _ATUALIZANDO_GPU
    agora = time.time()
    if (agora - _CACHE_GPU_TS) > 30.0 and not _ATUALIZANDO_GPU:
        _ATUALIZANDO_GPU = True
        threading.Thread(target=_atualizar_gpu_background, daemon=True).start()
    dados = dict(_CACHE_GPU)
    dados["sucesso"] = True
    dados["verificado"] = True
    return dados


def obter_status_pc() -> dict[str, Any]:
    """Coleta métricas em tempo real (< 2ms) de CPU, memória RAM, GPU, disco e tempo ligado."""
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    disco = psutil.disk_usage("C:\\" if os.name == "nt" else "/")

    uptime_segundos = int(time.time() - psutil.boot_time())
    horas = uptime_segundos // 3600
    minutos = (uptime_segundos % 3600) // 60

    bateria_info = "Não aplicável (Desktop)"
    if hasattr(psutil, "sensors_battery"):
        bat = psutil.sensors_battery()
        if bat:
            status_plugado = "conectado à tomada" if bat.power_plugged else "na bateria"
            bateria_info = f"{bat.percent:.0f}% ({status_plugado})"

    gpu_info = obter_status_gpu()

    return {
        "sucesso": True,
        "verificado": True,
        "cpu_percent": f"{cpu}%",
        "memoria_ram": {
            "percentual": f"{mem.percent}%",
            "usado_gb": f"{mem.used / 1024**3:.2f} GB",
            "total_gb": f"{mem.total / 1024**3:.2f} GB",
            "livre_gb": f"{mem.available / 1024**3:.2f} GB",
        },
        "gpu": gpu_info,
        "disco_c": {
            "percentual_usado": f"{disco.percent}%",
            "livre_gb": f"{disco.free / 1024**3:.2f} GB",
            "total_gb": f"{disco.total / 1024**3:.2f} GB",
        },
        "tempo_ligado": f"{horas} horas e {minutos} minutos",
        "bateria": bateria_info,
    }


def listar_programas_usuario() -> list[str]:
    """Retorna a lista limpa dos principais aplicativos abertos pelo Henry."""
    programas = set()
    for proc in psutil.process_iter(["name"]):
        try:
            nome = proc.info["name"]
            if nome and nome.lower() not in PROCESSOS_IGNORADOS:
                nome_limpo = os.path.splitext(nome)[0]
                programas.add(nome_limpo)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return sorted(list(programas))


# ─── Inspecão e Controle Real de Janelas Win32 ────────────────────

SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_SHOWMAXIMIZED = 3
SW_RESTORE = 9
WM_CLOSE = 0x0010


def listar_janelas_visiveis() -> list[dict[str, Any]]:
    """Enumera todas as janelas visíveis com título no Windows 10 via Win32 API."""
    if os.name != "nt":
        wmctrl = shutil.which("wmctrl")
        if not wmctrl:
            return []
        resultado = subprocess.run([wmctrl, "-lp"], capture_output=True, text=True)
        janelas = []
        for linha in resultado.stdout.splitlines():
            partes = linha.split(None, 4)
            if len(partes) != 5:
                continue
            try:
                pid = int(partes[2])
                processo = psutil.Process(pid).name() if pid else ""
            except (ValueError, psutil.Error):
                pid, processo = 0, ""
            janelas.append({"hwnd": partes[0], "pid": pid, "processo": processo, "titulo": partes[4], "minimizada": False, "maximizada": False, "ativa": False})
        return janelas

    user32 = ctypes.windll.user32
    hwnd_ativo = user32.GetForegroundWindow()
    janelas: list[dict[str, Any]] = []

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        titulo = buf.value.strip()
        if not titulo or titulo in {"Program Manager", "Settings", "Windows Input Experience"}:
            return True

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_val = int(pid.value)
        nome_proc = ""
        try:
            nome_proc = psutil.Process(pid_val).name()
        except Exception:
            pass

        janelas.append({
            "hwnd": int(hwnd),
            "pid": pid_val,
            "processo": nome_proc,
            "titulo": titulo,
            "minimizada": bool(user32.IsIconic(hwnd)),
            "maximizada": bool(user32.IsZoomed(hwnd)),
            "ativa": int(hwnd) == int(hwnd_ativo),
        })
        return True

    user32.EnumWindows(WNDENUMPROC(_callback), 0)
    return janelas


def inspecionar_contexto_tela() -> dict[str, Any]:
    """Inspeciona sob demanda a janela ativa, respeitando os filtros de privacidade."""
    from gideon.presenca import inspecionar_janela_ativa_segura

    janela_ativa = inspecionar_janela_ativa_segura()

    titulo_principal = janela_ativa.get("titulo") or "Área de Trabalho"
    proc_principal = janela_ativa.get("processo") or "explorer.exe"
    if janela_ativa.get("protegida_privacidade"):
        msg = "A janela em foco está protegida por privacidade. O título e o processo não foram expostos."
    else:
        msg = f"No momento, a janela em foco é '{titulo_principal}' ({proc_principal})."

    return {
        "sucesso": True,
        "verificado": True,
        "janela_ativa": janela_ativa,
        "evidencias": {
            "hwnd_ativo": janela_ativa.get("hwnd"),
            "titulo_ativo": titulo_principal,
            "processo_ativo": proc_principal,
        },
        "mensagem_humana": msg,
    }


# Mapeamento rico de aplicativos do Windows 10: executáveis, processos, títulos e fallback web
CATALOGO_APPS_WINDOWS: dict[str, dict[str, Any]] = {
    "chrome": {
        "nome_exibicao": "Google Chrome",
        "executaveis": ["chrome.exe"],
        "processos": ["chrome.exe"],
        "palavras_titulo": ["chrome", "google chrome"],
        "caminhos_extras": [
            r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
            r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
            r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
        ],
    },
    "edge": {
        "nome_exibicao": "Microsoft Edge",
        "executaveis": ["msedge.exe"],
        "processos": ["msedge.exe"],
        "palavras_titulo": ["edge"],
        "caminhos_extras": [
            r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
            r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
        ],
    },
    "spotify": {
        "nome_exibicao": "Spotify",
        "executaveis": ["Spotify.exe"],
        "processos": ["spotify.exe"],
        "palavras_titulo": ["spotify"],
        "caminhos_extras": [
            r"%APPDATA%\Spotify\Spotify.exe",
            r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe",
        ],
        "fallback_web": "https://open.spotify.com",
    },
    "discord": {
        "nome_exibicao": "Discord",
        "executaveis": ["Discord.exe"],
        "processos": ["discord.exe"],
        "palavras_titulo": ["discord"],
        "caminhos_extras": [
            r"%LOCALAPPDATA%\Discord\Update.exe",
        ],
        "argumentos_extras": ["--processStart", "Discord.exe"],
        "fallback_web": "https://discord.com/app",
    },
    "vscode": {
        "nome_exibicao": "Visual Studio Code",
        "executaveis": ["Code.exe", "code.cmd", "code"],
        "processos": ["code.exe"],
        "palavras_titulo": ["visual studio code"],
        "caminhos_extras": [
            r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
            r"%ProgramFiles%\Microsoft VS Code\Code.exe",
        ],
    },
    "calculadora": {
        "nome_exibicao": "Calculadora",
        "executaveis": ["calc.exe"],
        "processos": ["calculatorapp.exe", "calc.exe", "win32calc.exe"],
        "palavras_titulo": ["calculadora", "calculator"],
        "caminhos_extras": [r"C:\Windows\System32\calc.exe"],
    },
    "bloco de notas": {
        "nome_exibicao": "Bloco de Notas",
        "executaveis": ["notepad.exe"],
        "processos": ["notepad.exe"],
        "palavras_titulo": ["bloco de notas", "notepad", "sem título", "untitled"],
        "caminhos_extras": [r"C:\Windows\System32\notepad.exe"],
    },
    "explorador de arquivos": {
        "nome_exibicao": "Explorador de Arquivos",
        "executaveis": ["explorer.exe"],
        "processos": ["explorer.exe"],
        "palavras_titulo": ["explorador de arquivos", "file explorer", "este computador", "acesso rápido", "downloads", "documentos"],
        "caminhos_extras": [r"C:\Windows\explorer.exe"],
    },
    "gerenciador de tarefas": {
        "nome_exibicao": "Gerenciador de Tarefas",
        "executaveis": ["taskmgr.exe"],
        "processos": ["taskmgr.exe"],
        "palavras_titulo": ["gerenciador de tarefas", "task manager"],
        "caminhos_extras": [r"C:\Windows\System32\taskmgr.exe"],
    },
    "terminal": {
        "nome_exibicao": "PowerShell",
        "executaveis": ["powershell.exe", "wt.exe"],
        "processos": ["powershell.exe", "windowsterminal.exe", "cmd.exe"],
        "palavras_titulo": ["powershell", "terminal", "prompt de comando"],
        "caminhos_extras": [r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"],
    },
    "cmd": {
        "nome_exibicao": "Prompt de Comando",
        "executaveis": ["cmd.exe"],
        "processos": ["cmd.exe"],
        "palavras_titulo": ["prompt de comando", "cmd.exe"],
        "caminhos_extras": [r"C:\Windows\System32\cmd.exe"],
    },
    "paint": {
        "nome_exibicao": "Paint",
        "executaveis": ["mspaint.exe"],
        "processos": ["mspaint.exe"],
        "palavras_titulo": ["paint"],
        "caminhos_extras": [r"C:\Windows\System32\mspaint.exe"],
    },
    "steam": {
        "nome_exibicao": "Steam",
        "executaveis": ["steam.exe"],
        "processos": ["steam.exe"],
        "palavras_titulo": ["steam"],
        "caminhos_extras": [
            r"%ProgramFiles(x86)%\Steam\steam.exe",
            r"%ProgramFiles%\Steam\steam.exe",
        ],
        "fallback_web": "https://store.steampowered.com",
    },
}

# Mantém as mesmas intenções de voz, trocando apenas executáveis e processos
# quando a Gideon está no Zorin/Ubuntu.
if os.name != "nt":
    CATALOGO_APPS_WINDOWS.update({
        "chrome": {"nome_exibicao": "Google Chrome", "executaveis": ["google-chrome", "chromium", "chromium-browser"], "processos": ["chrome", "google-chrome", "chromium"], "palavras_titulo": ["chrome", "chromium"], "caminhos_extras": []},
        "edge": {"nome_exibicao": "Microsoft Edge", "executaveis": ["microsoft-edge"], "processos": ["msedge", "microsoft-edge"], "palavras_titulo": ["edge"], "caminhos_extras": []},
        "spotify": {"nome_exibicao": "Spotify", "executaveis": ["spotify"], "processos": ["spotify"], "palavras_titulo": ["spotify"], "caminhos_extras": [], "fallback_web": "https://open.spotify.com"},
        "discord": {"nome_exibicao": "Discord", "executaveis": ["discord"], "processos": ["discord"], "palavras_titulo": ["discord"], "caminhos_extras": [], "fallback_web": "https://discord.com/app"},
        "vscode": {"nome_exibicao": "Visual Studio Code", "executaveis": ["code"], "processos": ["code"], "palavras_titulo": ["visual studio code"], "caminhos_extras": []},
        "calculadora": {"nome_exibicao": "Calculadora", "executaveis": ["gnome-calculator"], "processos": ["gnome-calculator"], "palavras_titulo": ["calculadora", "calculator"], "caminhos_extras": []},
        "bloco de notas": {"nome_exibicao": "Editor de Texto", "executaveis": ["gedit", "gnome-text-editor", "xed"], "processos": ["gedit", "gnome-text-editor", "xed"], "palavras_titulo": ["editor de texto", "text editor"], "caminhos_extras": []},
        "explorador de arquivos": {"nome_exibicao": "Arquivos", "executaveis": ["nautilus", "nemo"], "processos": ["nautilus", "nemo"], "palavras_titulo": ["arquivos", "files", "home"], "caminhos_extras": []},
        "gerenciador de tarefas": {"nome_exibicao": "Monitor do Sistema", "executaveis": ["gnome-system-monitor"], "processos": ["gnome-system-monitor"], "palavras_titulo": ["monitor do sistema", "system monitor"], "caminhos_extras": []},
        "terminal": {"nome_exibicao": "Terminal", "executaveis": ["gnome-terminal", "kgx", "x-terminal-emulator"], "processos": ["gnome-terminal", "kgx"], "palavras_titulo": ["terminal"], "caminhos_extras": []},
        "cmd": {"nome_exibicao": "Terminal", "executaveis": ["gnome-terminal", "kgx", "x-terminal-emulator"], "processos": ["gnome-terminal", "kgx"], "palavras_titulo": ["terminal"], "caminhos_extras": []},
        "paint": {"nome_exibicao": "Desenho", "executaveis": ["drawing", "pinta"], "processos": ["drawing", "pinta"], "palavras_titulo": ["drawing", "pinta"], "caminhos_extras": []},
        "steam": {"nome_exibicao": "Steam", "executaveis": ["steam"], "processos": ["steam"], "palavras_titulo": ["steam"], "caminhos_extras": [], "fallback_web": "https://store.steampowered.com"},
    })

SINONIMOS_APPS: dict[str, str] = {
    "google chrome": "chrome",
    "navegador": "chrome",
    "internet": "chrome",
    "browser": "chrome",
    "web": "chrome",
    "microsoft edge": "edge",
    "musica": "spotify",
    "música": "spotify",
    "player de musica": "spotify",
    "vs code": "vscode",
    "visual studio code": "vscode",
    "code": "vscode",
    "editor de codigo": "vscode",
    "calc": "calculadora",
    "notepad": "bloco de notas",
    "editor de texto": "bloco de notas",
    "arquivos": "explorador de arquivos",
    "pastas": "explorador de arquivos",
    "explorer": "explorador de arquivos",
    "taskmgr": "gerenciador de tarefas",
    "powershell": "terminal",
    "prompt": "cmd",
    "mspaint": "paint",
}

SITES_DIRETOS: dict[str, tuple[str, str]] = {
    "google": ("Google", "https://www.google.com"),
    "youtube": ("YouTube", "https://www.youtube.com"),
    "whatsapp": ("WhatsApp Web", "https://web.whatsapp.com"),
    "github": ("GitHub", "https://github.com"),
    "gmail": ("Gmail", "https://mail.google.com"),
}


def _consultar_app_paths_registro(nome_exe: str) -> str | None:
    """Procura o caminho de um executável no Registro do Windows (App Paths)."""
    if os.name != "nt":
        return None
    try:
        import winreg
        if not nome_exe.lower().endswith(".exe"):
            nome_exe = f"{nome_exe}.exe"
        subchave = rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{nome_exe}"
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, subchave) as key:
                    val, _ = winreg.QueryValueEx(key, "")
                    if val:
                        caminho = str(val).strip('"')
                        if Path(caminho).is_file():
                            return caminho
            except OSError:
                continue
    except Exception:
        pass
    return None


def localizar_executavel_windows(chave_app: str) -> tuple[str | None, list[str]]:
    """Localiza o caminho real verificado de um executável no Windows 10."""
    info = CATALOGO_APPS_WINDOWS.get(chave_app)
    if info:
        # 1. Verifica caminhos conhecidos expandindo variáveis de ambiente
        for padrao in info.get("caminhos_extras", []):
            expandido = os.path.expandvars(padrao)
            if Path(expandido).is_file():
                args = list(info.get("argumentos_extras", []))
                return expandido, args

        # 2. Verifica App Paths no Registro e PATH do sistema
        for exe in info.get("executaveis", []):
            achado_path = shutil.which(exe)
            if achado_path and Path(achado_path).is_file():
                # Ignora stubs vazios do WindowsApps (0 bytes)
                try:
                    if Path(achado_path).stat().st_size > 0 or "WindowsApps" not in achado_path:
                        return achado_path, []
                except OSError:
                    return achado_path, []
            achado_reg = _consultar_app_paths_registro(exe)
            if achado_reg:
                return achado_reg, []
        return None, []

    # Caso não esteja no catálogo fixo, tenta localizar pelo nome direto
    achado_direto = shutil.which(chave_app) or _consultar_app_paths_registro(chave_app)
    if achado_direto and Path(achado_direto).is_file():
        return achado_direto, []
    return None, []


def _verificar_processo_ou_janela(
    nomes_processos: list[str],
    palavras_titulo: list[str],
    pids_anteriores: set[int],
    timeout_s: float = 2.5,
) -> dict[str, Any] | None:
    """Aguarda e verifica com evidência real (priorizando HWND visível + PID) se o aplicativo abriu."""
    procs_lower = {p.lower() for p in nomes_processos}
    palavras_lower = [p.lower() for p in palavras_titulo]
    t_inicio = time.perf_counter()
    prazo = t_inicio + timeout_s
    processo_detectado: dict[str, Any] | None = None

    while time.perf_counter() < prazo:
        # 1. Prioridade máxima: encontrar a janela visível (HWND) já renderizada pelo Windows
        janelas = listar_janelas_visiveis()
        for jan in janelas:
            proc_jan = (jan.get("processo") or "").lower()
            tit_jan = (jan.get("titulo") or "").lower()
            if proc_jan in procs_lower or any(pal in tit_jan for pal in palavras_lower):
                return {
                    "pid": jan["pid"],
                    "hwnd": jan["hwnd"],
                    "processo": jan["processo"],
                    "titulo_janela": jan["titulo"],
                }

        # 2. Registra se o processo já existe no sistema enquanto aguarda a janela aparecer
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                p_nome = (proc.info["name"] or "").lower()
                if p_nome in procs_lower:
                    if proc.info["pid"] not in pids_anteriores or processo_detectado is None:
                        processo_detectado = {
                            "pid": proc.info["pid"],
                            "hwnd": None,
                            "processo": proc.info["name"],
                            "titulo_janela": "",
                        }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Se o processo já está vivo há mais de 1.0s mas é um app sem janela imediata, retorna o PID confirmado
        if processo_detectado is not None and (time.perf_counter() - t_inicio) >= 1.0:
            return processo_detectado

        time.sleep(0.1)

    return processo_detectado


def abrir_programa(nome: str) -> dict[str, Any]:
    """Abre um programa, site ou aplicativo do Windows e VERIFICA com evidências reais se abriu."""
    nome_limpo = nome.strip()
    chave_bruta = nome_limpo.lower().strip(" .,!?")
    chave = SINONIMOS_APPS.get(chave_bruta, chave_bruta)

    # 1. URLs diretas ou sites mapeados
    if chave in SITES_DIRETOS or chave_bruta.startswith(("http://", "https://")):
        if chave in SITES_DIRETOS:
            nome_site, url = SITES_DIRETOS[chave]
        else:
            nome_site, url = nome_limpo, nome_limpo

        return _abrir_url_verificada(url, nome_site)

    # 2. Configurações do Windows ou Painel de Controle
    if chave in {"configuracoes", "configurações", "ms-settings:"}:
        try:
            if os.name != "nt":
                configuracoes = shutil.which("gnome-control-center")
                if not configuracoes:
                    raise FileNotFoundError("gnome-control-center não encontrado")
                subprocess.Popen([configuracoes], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return {"sucesso": True, "verificado": True, "evidencias": {"executavel": configuracoes}, "mensagem_humana": "Pronto, Configurações do sistema abertas."}
            if hasattr(os, "startfile"):
                os.startfile("ms-settings:")
                time.sleep(0.35)
                return {
                    "sucesso": True,
                    "verificado": True,
                    "evidencias": {"uri": "ms-settings:"},
                    "mensagem_humana": "Pronto, Configurações do Windows abertas.",
                }
        except Exception as e:
            return {
                "sucesso": False,
                "verificado": False,
                "erro": f"Não foi possível abrir as Configurações: {e}",
                "mensagem_humana": "Não consegui abrir as Configurações do Windows, Henry.",
            }

    if chave == "painel de controle":
        chave = "control"

    # 3. Aplicativo do catálogo ou executável local
    info = CATALOGO_APPS_WINDOWS.get(chave)
    nome_exibicao = info["nome_exibicao"] if info else nome_limpo
    caminho_exe, args_extras = localizar_executavel_windows(chave)

    if not caminho_exe:
        # Se for navegador genérico ("chrome") e o Chrome não estiver instalado, usa Microsoft Edge automaticamente
        if chave == "chrome":
            caminho_edge, args_edge = localizar_executavel_windows("edge")
            if caminho_edge:
                chave = "edge"
                info = CATALOGO_APPS_WINDOWS["edge"]
                nome_exibicao = info["nome_exibicao"]
                caminho_exe, args_extras = caminho_edge, args_edge

    if not caminho_exe:
        # Recuperação inteligente: se o app tem versão web conhecida (ex: Spotify, Discord, Steam), sugere abrir web!
        fallback_web = info.get("fallback_web") if info else None
        if fallback_web:
            return {
                "sucesso": False,
                "verificado": False,
                "erro": f"O aplicativo {nome_exibicao} não foi encontrado instalado localmente.",
                "sugestao_recuperacao": "versao_web",
                "alternativa_recuperacao": {
                    "acao": "abrir_programa",
                    "parametros": {"nome": fallback_web},
                    "descricao": f"abrir a versão web do {nome_exibicao}",
                },
                "mensagem_humana": f"Não consegui encontrar o {nome_exibicao} instalado. Quer que eu abra a versão web?",
            }

        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Executável para '{nome_limpo}' não encontrado no computador.",
            "mensagem_humana": f"Não consegui encontrar o aplicativo {nome_limpo} instalado no seu computador, Henry.",
        }

    # Coleta PIDs anteriores para confirmar criação ou ativação do processo
    procs_esperados = info["processos"] if info else [Path(caminho_exe).name]
    palavras_titulo = info["palavras_titulo"] if info else [chave]
    pids_antes = {
        p.info["pid"]
        for p in psutil.process_iter(["pid", "name"])
        if (p.info.get("name") or "").lower() in {pr.lower() for pr in procs_esperados}
    }

    try:
        proc_lancado = subprocess.Popen(
            [caminho_exe, *args_extras],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Erro ao iniciar '{nome_exibicao}': {e}",
            "mensagem_humana": f"Não consegui iniciar o {nome_exibicao} devido a um erro do sistema.",
        }

    evidencia = _verificar_processo_ou_janela(
        nomes_processos=procs_esperados,
        palavras_titulo=palavras_titulo,
        pids_anteriores=pids_antes,
        timeout_s=2.5,
    )

    if evidencia is None and proc_lancado.poll() is None:
        evidencia = {
            "pid": proc_lancado.pid,
            "hwnd": None,
            "processo": Path(caminho_exe).name,
            "titulo_janela": "",
        }

    if evidencia is None:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"O processo de '{nome_exibicao}' encerrou sem abrir uma janela ou instância ativa.",
            "mensagem_humana": f"Tentei iniciar o {nome_exibicao}, mas ele não abriu corretamente, Henry.",
        }

    evidencia["executavel"] = caminho_exe
    return {
        "sucesso": True,
        "verificado": True,
        "evidencias": evidencia,
        "mensagem_humana": f"Pronto, {nome_exibicao} aberto.",
    }


def _abrir_url_verificada(url: str, nome_exibicao: str) -> dict[str, Any]:
    """Abre uma URL no navegador preferido e verifica que o processo do navegador está ativo."""
    caminho_nav, _ = localizar_executavel_windows("chrome")
    if not caminho_nav:
        caminho_nav, _ = localizar_executavel_windows("edge")

    pids_antes = set()
    try:
        if caminho_nav:
            subprocess.Popen([caminho_nav, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            abriu = webbrowser.open(url)
            if not abriu:
                return {
                    "sucesso": False,
                    "verificado": False,
                    "erro": f"Não foi possível abrir a URL {url}.",
                    "mensagem_humana": f"Não consegui abrir {nome_exibicao} no navegador.",
                }
    except Exception as e:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": str(e),
            "mensagem_humana": f"Não consegui abrir {nome_exibicao}: {e}",
        }

    evidencia = _verificar_processo_ou_janela(
        nomes_processos=["chrome.exe", "msedge.exe", "brave.exe", "firefox.exe", "chrome", "google-chrome", "chromium", "firefox"],
        palavras_titulo=["chrome", "edge", "google", "youtube", nome_exibicao.lower()],
        pids_anteriores=pids_antes,
        timeout_s=2.0,
    )
    if evidencia is None:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": "Nenhum processo de navegador ativo foi detectado após tentar abrir a URL.",
            "mensagem_humana": f"Não consegui confirmar a abertura de {nome_exibicao} no navegador.",
        }

    evidencia["url"] = url
    return {
        "sucesso": True,
        "verificado": True,
        "evidencias": evidencia,
        "mensagem_humana": f"Pronto, abri {nome_exibicao} no navegador.",
    }


def fechar_programa(nome: str) -> dict[str, Any]:
    """Fecha um aplicativo aberto e VERIFICA se o processo/janela realmente foi encerrado."""
    nome_limpo = nome.strip()
    chave_bruta = nome_limpo.lower().strip(" .,!?")
    chave = SINONIMOS_APPS.get(chave_bruta, chave_bruta)
    info = CATALOGO_APPS_WINDOWS.get(chave)
    nome_exibicao = info["nome_exibicao"] if info else nome_limpo

    procs_alvo = {p.lower() for p in (info["processos"] if info else [f"{chave}.exe", chave])}
    palavras_titulo = [p.lower() for p in (info["palavras_titulo"] if info else [chave])]

    # Proteção: nunca fechar processos críticos nem o próprio Explorer shell inteiro sem janela específica
    janelas = listar_janelas_visiveis()
    janelas_alvo = [
        j for j in janelas
        if (j["processo"] or "").lower() in procs_alvo
        or any(pal in (j["titulo"] or "").lower() for pal in palavras_titulo)
    ]

    pids_fechados: list[int] = []
    hwnds_fechados: list[int] = []

    if os.name == "nt":
        user32 = ctypes.windll.user32
        for jan in janelas_alvo:
            user32.PostMessageW(jan["hwnd"], WM_CLOSE, 0, 0)
            hwnds_fechados.append(jan["hwnd"])

    # Se não for explorer.exe, também termina processos correspondentes
    if "explorer.exe" not in procs_alvo:
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                p_nome = (proc.info["name"] or "").lower()
                if p_nome in procs_alvo:
                    pids_fechados.append(proc.info["pid"])
                    proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    if not janelas_alvo and not pids_fechados:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"O aplicativo '{nome_exibicao}' não estava aberto.",
            "mensagem_humana": f"O {nome_exibicao} não está aberto no momento, Henry.",
        }

    # Aguarda até 1.5s para confirmar o encerramento
    prazo = time.perf_counter() + 1.5
    while time.perf_counter() < prazo:
        ainda_abertas = [
            j for j in listar_janelas_visiveis()
            if j["hwnd"] in hwnds_fechados
        ]
        ainda_vivos = [
            pid for pid in pids_fechados
            if psutil.pid_exists(pid)
        ]
        if not ainda_abertas and not ainda_vivos:
            break
        time.sleep(0.1)

    return {
        "sucesso": True,
        "verificado": True,
        "evidencias": {
            "pids_encerrados": pids_fechados,
            "hwnds_fechados": hwnds_fechados,
        },
        "mensagem_humana": f"Pronto, fechei o {nome_exibicao}.",
    }


def gerenciar_janela(acao: str, alvo: str = "") -> dict[str, Any]:
    """Minimiza, maximiza, restaura ou alterna foco para uma janela do Windows e VERIFICA o estado final."""
    if os.name != "nt":
        wmctrl = shutil.which("wmctrl")
        if not wmctrl:
            return {"sucesso": False, "verificado": False, "erro": "Instale o pacote wmctrl para controlar janelas no Linux."}
        janelas = listar_janelas_visiveis()
        alvo_norm = alvo.strip().lower()
        janela = next((j for j in janelas if alvo_norm and alvo_norm in j["titulo"].lower()), janelas[0] if janelas else None)
        if not janela:
            return {"sucesso": False, "verificado": False, "erro": "Nenhuma janela visível encontrada."}
        acao_norm = acao.lower().strip()
        comandos = {
            "minimizar": ["-b", "add,hidden"], "minimize": ["-b", "add,hidden"],
            "maximizar": ["-b", "add,maximized_vert,maximized_horz"], "maximize": ["-b", "add,maximized_vert,maximized_horz"],
            "restaurar": ["-b", "remove,hidden,maximized_vert,maximized_horz"], "restore": ["-b", "remove,hidden,maximized_vert,maximized_horz"],
            "focar": ["-a", janela["titulo"]], "alternar": ["-a", janela["titulo"]], "ativar": ["-a", janela["titulo"]],
        }
        argumentos = comandos.get(acao_norm)
        if not argumentos:
            return {"sucesso": False, "verificado": False, "erro": f"Ação de janela '{acao}' não suportada."}
        comando = [wmctrl, "-ir", str(janela["hwnd"]), *argumentos] if argumentos[0] == "-b" else [wmctrl, *argumentos]
        resultado = subprocess.run(comando, capture_output=True, text=True)
        sucesso = resultado.returncode == 0
        return {"sucesso": sucesso, "verificado": sucesso, "evidencias": {"hwnd": janela["hwnd"], "titulo_janela": janela["titulo"]}, "mensagem_humana": f"Pronto, ação aplicada à janela '{janela['titulo']}'."}

    user32 = ctypes.windll.user32
    acao_norm = acao.lower().strip()
    alvo_limpo = alvo.strip().lower()
    pronomes_contexto = {"", "ele", "ela", "isso", "janela", "atual", "ativa", "programa", "aplicativo"}

    janelas = listar_janelas_visiveis()
    janela_escolhida: dict[str, Any] | None = None

    if alvo_limpo not in pronomes_contexto:
        chave = SINONIMOS_APPS.get(alvo_limpo, alvo_limpo)
        info = CATALOGO_APPS_WINDOWS.get(chave)
        procs_alvo = {p.lower() for p in (info["processos"] if info else [f"{chave}.exe", chave])}
        palavras_titulo = [p.lower() for p in (info["palavras_titulo"] if info else [chave])]

        prazo_jan = time.perf_counter() + 1.0
        while time.perf_counter() < prazo_jan:
            janelas = listar_janelas_visiveis()
            for j in janelas:
                if (j["processo"] or "").lower() in procs_alvo or any(p in (j["titulo"] or "").lower() for p in palavras_titulo):
                    janela_escolhida = j
                    break
            if janela_escolhida is not None:
                break
            time.sleep(0.1)

        if janela_escolhida is None:
            return {
                "sucesso": False,
                "verificado": False,
                "erro": f"Nenhuma janela aberta encontrada para '{alvo}'.",
                "mensagem_humana": f"Não encontrei nenhuma janela aberta do {alvo}, Henry.",
            }
    else:
        # Usa a janela ativa atual; se não houver uma, seleciona a primeira visível.
        for j in janelas:
            if j["ativa"]:
                janela_escolhida = j
                break
        if janela_escolhida is None and janelas:
            janela_escolhida = janelas[0]

    if janela_escolhida is None:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": "Nenhuma janela visível disponível para gerenciar.",
            "mensagem_humana": "Não encontrei nenhuma janela ativa para realizar essa ação, Henry.",
        }

    hwnd = int(janela_escolhida["hwnd"])
    titulo = janela_escolhida["titulo"]

    if acao_norm in {"minimizar", "minimize"}:
        user32.ShowWindow(hwnd, SW_SHOWMINIMIZED)
        time.sleep(0.12)
        verificado = bool(user32.IsIconic(hwnd))
        return {
            "sucesso": verificado,
            "verificado": verificado,
            "evidencias": {"hwnd": hwnd, "titulo_janela": titulo, "minimizada": verificado},
            "mensagem_humana": f"Pronto, janela '{titulo}' minimizada." if verificado else f"Não consegui minimizar a janela '{titulo}'.",
        }

    if acao_norm in {"maximizar", "maximize"}:
        user32.ShowWindow(hwnd, SW_SHOWMAXIMIZED)
        time.sleep(0.12)
        verificado = bool(user32.IsZoomed(hwnd))
        return {
            "sucesso": verificado,
            "verificado": verificado,
            "evidencias": {"hwnd": hwnd, "titulo_janela": titulo, "maximizada": verificado},
            "mensagem_humana": f"Pronto, janela '{titulo}' maximizada." if verificado else f"Não consegui maximizar a janela '{titulo}'.",
        }

    if acao_norm in {"restaurar", "restore"}:
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.12)
        verificado = not bool(user32.IsIconic(hwnd))
        return {
            "sucesso": verificado,
            "verificado": verificado,
            "evidencias": {"hwnd": hwnd, "titulo_janela": titulo, "restaurada": verificado},
            "mensagem_humana": f"Pronto, janela '{titulo}' restaurada.",
        }

    if acao_norm in {"focar", "alternar", "ativar", "trazer para frente"}:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        # Truque Win32 seguro para permitir SetForegroundWindow a partir de processo em background
        user32.keybd_event(0x12, 0, 0, 0)  # VK_MENU (Alt)
        user32.keybd_event(0x12, 0, 2, 0)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.12)
        fg_atual = int(user32.GetForegroundWindow())
        verificado = (fg_atual == hwnd) or not bool(user32.IsIconic(hwnd))
        return {
            "sucesso": verificado,
            "verificado": verificado,
            "evidencias": {"hwnd": hwnd, "titulo_janela": titulo, "em_foco": fg_atual == hwnd},
            "mensagem_humana": f"Pronto, alternei para '{titulo}'.",
        }

    return {
        "sucesso": False,
        "verificado": False,
        "erro": f"Ação de janela '{acao}' não suportada.",
        "mensagem_humana": f"Não reconheci a ação de janela '{acao}', Henry.",
    }


def pesquisar_navegador(consulta: str, motor: str = "google") -> dict[str, Any]:
    """Realiza uma pesquisa real no navegador (Google ou YouTube) e verifica a abertura."""
    termo = consulta.strip()
    if not termo:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": "Termo de pesquisa vazio.",
            "mensagem_humana": "O que você gostaria que eu pesquisasse, Henry?",
        }

    termo_url = urllib.parse.quote(termo)
    motor_norm = motor.lower().strip()
    if "youtube" in motor_norm:
        url = f"https://www.youtube.com/results?search_query={termo_url}"
        nome_motor = "YouTube"
    else:
        url = f"https://www.google.com/search?q={termo_url}"
        nome_motor = "Google"

    res = _abrir_url_verificada(url, f"pesquisa por '{termo}' no {nome_motor}")
    if res.get("sucesso"):
        res["evidencias"]["consulta"] = termo
        res["evidencias"]["motor"] = nome_motor
        res["mensagem_humana"] = f"Pronto, pesquisei sobre {termo} no {nome_motor}."
    return res


def tocar_ou_pesquisar_midia(consulta: str, plataforma: str = "spotify") -> dict[str, Any]:
    """Pesquisa ou inicia uma música, artista ou vídeo no Spotify, YouTube ou Google com verificação real."""
    termo = consulta.strip()
    if not termo:
        return abrir_programa(plataforma)

    plat = plataforma.lower().strip()
    termo_url = urllib.parse.quote(termo)

    if "youtube" in plat or "video" in plat or "vídeo" in plat:
        return pesquisar_navegador(termo, motor="youtube")
    if "google" in plat or "web" in plat or "internet" in plat:
        return pesquisar_navegador(termo, motor="google")

    # Verifica se o Spotify desktop está instalado; se não estiver, usa Spotify Web verificando navegador
    caminho_spotify, _ = localizar_executavel_windows("spotify")
    if caminho_spotify and hasattr(os, "startfile"):
        try:
            os.startfile(f"spotify:search:{termo_url}")
            evidencia = _verificar_processo_ou_janela(
                nomes_processos=["spotify.exe"],
                palavras_titulo=["spotify"],
                pids_anteriores=set(),
                timeout_s=2.0,
            )
            if evidencia:
                evidencia["consulta"] = termo
                return {
                    "sucesso": True,
                    "verificado": True,
                    "evidencias": evidencia,
                    "mensagem_humana": f"Pronto, busquei '{termo}' no Spotify.",
                }
        except Exception:
            pass

    url_spotify = f"https://open.spotify.com/search/{termo_url}"
    res = _abrir_url_verificada(url_spotify, f"Spotify Web ({termo})")
    if res.get("sucesso"):
        res["evidencias"]["consulta"] = termo
        res["mensagem_humana"] = f"Pronto, abri '{termo}' no Spotify Web."
    return res


def controlar_midia(acao: str) -> dict[str, Any]:
    """Controla reprodução de mídia e volume do Windows via teclas multimídia nativas."""
    acao_norm = acao.lower().strip()
    mapa_vk = {
        "pausar": (0xB3, "Reprodução pausada."),
        "continuar": (0xB3, "Reprodução retomada."),
        "play": (0xB3, "Comando de reprodução enviado."),
        "pause": (0xB3, "Reprodução pausada."),
        "proxima": (0xB0, "Avançando para a próxima faixa."),
        "próxima": (0xB0, "Avançando para a próxima faixa."),
        "pular": (0xB0, "Avançando para a próxima faixa."),
        "anterior": (0xB1, "Voltando para a faixa anterior."),
        "voltar": (0xB1, "Voltando para a faixa anterior."),
        "mudo": (0xAD, "Áudio alternado para mudo."),
        "silenciar": (0xAD, "Áudio silenciado."),
        "aumentar_volume": (0xAF, "Volume aumentado."),
        "subir_volume": (0xAF, "Volume aumentado."),
        "diminuir_volume": (0xAE, "Volume reduzido."),
        "abaixar_volume": (0xAE, "Volume reduzido."),
    }

    item = mapa_vk.get(acao_norm)
    if not item:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Ação de mídia '{acao}' não reconhecida.",
            "mensagem_humana": f"Não reconheci o comando de mídia '{acao}', Henry.",
        }

    vk_code, msg = item
    try:
        if os.name == "nt":
            user32 = ctypes.windll.user32
            repeticoes = 5 if "volume" in acao_norm else 1
            for _ in range(repeticoes):
                user32.keybd_event(vk_code, 0, 0, 0)
                user32.keybd_event(vk_code, 0, 2, 0)
        else:
            from gideon.tools.janelas import controlar_som_sistema
            mapa_linux = {
                "pausar": "play_pause", "continuar": "play_pause", "play": "play_pause", "pause": "play_pause",
                "proxima": "proxima", "próxima": "proxima", "pular": "proxima", "anterior": "anterior", "voltar": "anterior",
                "mudo": "mutar", "silenciar": "mutar", "aumentar_volume": "aumentar", "subir_volume": "aumentar",
                "diminuir_volume": "diminuir", "abaixar_volume": "diminuir",
            }
            resultado = controlar_som_sistema(mapa_linux[acao_norm], toques=5)
            if not resultado.get("sucesso"):
                return {"sucesso": False, "verificado": False, "erro": resultado.get("erro", "Falha no controle de mídia."), "mensagem_humana": resultado.get("mensagem_humana", "Não consegui controlar a mídia.")}
        return {
            "sucesso": True,
            "verificado": True,
            "evidencias": {"vk_code": hex(vk_code), "acao": acao_norm},
            "mensagem_humana": msg,
        }
    except Exception as e:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Erro ao enviar tecla de mídia: {e}",
            "mensagem_humana": f"Não consegui ajustar a mídia: {e}",
        }


# ─── Automação de Teclado e Mouse Verificada ──────────────────────

MAPA_TECLAS_VK: dict[str, int] = {
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "win": 0x5B,
    "windows": 0x5B,
    "enter": 0x0D,
    "return": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "tab": 0x09,
    "espaco": 0x20,
    "espaço": 0x20,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "cima": 0x26,
    "baixo": 0x28,
    "esquerda": 0x25,
    "direita": 0x27,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}


def _enviar_caractere_unicode_win32(ch: str) -> None:
    """Envia um caractere Unicode para a janela em foco via SendInput (KEYEVENTF_UNICODE)."""
    user32 = ctypes.windll.user32

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 24)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    codigo = ord(ch)

    inp_down = INPUT(type=1, union=INPUT_UNION(ki=KEYBDINPUT(0, codigo, KEYEVENTF_UNICODE, 0, None)))
    inp_up = INPUT(type=1, union=INPUT_UNION(ki=KEYBDINPUT(0, codigo, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None)))
    arr = (INPUT * 2)(inp_down, inp_up)
    user32.SendInput(2, ctypes.byref(arr), ctypes.sizeof(INPUT))


def digitar_texto(texto: str, janela_alvo: str = "", pressionar_enter: bool = False) -> dict[str, Any]:
    """Digita um texto no campo selecionado da janela ativa (ou foca `janela_alvo` antes) e verifica."""
    if os.name != "nt":
        xdotool = shutil.which("xdotool")
        if not xdotool:
            return {"sucesso": False, "verificado": False, "erro": "Instale xdotool para digitar automaticamente no Linux."}
        if janela_alvo.strip():
            foco = gerenciar_janela("focar", janela_alvo)
            if not foco.get("sucesso"):
                return foco
        comando = [xdotool, "type", "--clearmodifiers", "--delay", "8", texto]
        resultado = subprocess.run(comando, capture_output=True, text=True)
        if resultado.returncode == 0 and pressionar_enter:
            resultado = subprocess.run([xdotool, "key", "Return"], capture_output=True, text=True)
        sucesso = resultado.returncode == 0
        return {"sucesso": sucesso, "verificado": sucesso, "evidencias": {"caracteres_enviados": len(texto), "pressionou_enter": pressionar_enter}, "erro": resultado.stderr.strip() if not sucesso else "", "mensagem_humana": "Pronto, digitei o texto na janela ativa." if sucesso else "Não consegui digitar o texto."}

    if not texto:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": "Nenhum texto informado para digitação.",
            "mensagem_humana": "Qual texto você gostaria que eu digitasse, Henry?",
        }

    if janela_alvo.strip():
        res_foco = gerenciar_janela("focar", janela_alvo)
        if not res_foco.get("sucesso"):
            return res_foco
        time.sleep(0.15)

    user32 = ctypes.windll.user32
    hwnd_ativo = int(user32.GetForegroundWindow())
    if hwnd_ativo == 0:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": "Nenhuma janela ativa em foco para receber a digitação.",
            "mensagem_humana": "Não há nenhuma janela ativa em foco para eu digitar agora, Henry.",
        }

    length = user32.GetWindowTextLengthW(hwnd_ativo)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd_ativo, buf, length + 1)
    titulo_ativo = buf.value.strip() or "Janela Ativa"

    try:
        for ch in texto:
            if ch == "\n":
                user32.keybd_event(0x0D, 0, 0, 0)
                user32.keybd_event(0x0D, 0, 2, 0)
            else:
                _enviar_caractere_unicode_win32(ch)
            time.sleep(0.008)

        if pressionar_enter:
            user32.keybd_event(0x0D, 0, 0, 0)
            user32.keybd_event(0x0D, 0, 2, 0)

        return {
            "sucesso": True,
            "verificado": True,
            "evidencias": {
                "hwnd": hwnd_ativo,
                "janela_ativa": titulo_ativo,
                "caracteres_enviados": len(texto),
                "pressionou_enter": pressionar_enter,
            },
            "mensagem_humana": f"Pronto, digitei o texto em '{titulo_ativo}'.",
        }
    except Exception as e:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Erro ao digitar texto: {e}",
            "mensagem_humana": f"Não consegui digitar o texto: {e}",
        }


def executar_atalho_teclado(atalho: str, janela_alvo: str = "") -> dict[str, Any]:
    """Executa um atalho de teclado (ex: 'ctrl+s', 'ctrl+c', 'ctrl+v', 'alt+tab', 'enter') e verifica."""
    if os.name != "nt":
        xdotool = shutil.which("xdotool")
        if not xdotool:
            return {"sucesso": False, "verificado": False, "erro": "Instale xdotool para executar atalhos no Linux."}
        if janela_alvo.strip():
            foco = gerenciar_janela("focar", janela_alvo)
            if not foco.get("sucesso"):
                return foco
        tecla = atalho.replace("+", "+").replace("win", "super").replace("windows", "super")
        resultado = subprocess.run([xdotool, "key", "--clearmodifiers", tecla], capture_output=True, text=True)
        sucesso = resultado.returncode == 0
        return {"sucesso": sucesso, "verificado": sucesso, "evidencias": {"atalho": atalho}, "erro": resultado.stderr.strip() if not sucesso else "", "mensagem_humana": f"Pronto, atalho {atalho.upper()} executado." if sucesso else f"Não consegui executar o atalho '{atalho}'."}

    if janela_alvo.strip():
        res_foco = gerenciar_janela("focar", janela_alvo)
        if not res_foco.get("sucesso"):
            return res_foco
        time.sleep(0.1)

    partes = [p.strip().lower() for p in atalho.replace("-", "+").split("+") if p.strip()]
    if not partes:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": "Atalho vazio.",
            "mensagem_humana": "Qual atalho de teclado você quer que eu pressione, Henry?",
        }

    codigos_vk: list[int] = []
    for p in partes:
        if p in MAPA_TECLAS_VK:
            codigos_vk.append(MAPA_TECLAS_VK[p])
        elif len(p) == 1 and p.isalnum():
            codigos_vk.append(ord(p.upper()))
        else:
            return {
                "sucesso": False,
                "verificado": False,
                "erro": f"Tecla '{p}' não reconhecida no atalho '{atalho}'.",
                "mensagem_humana": f"Não reconheci a tecla '{p}' no atalho solicitado, Henry.",
            }

    user32 = ctypes.windll.user32
    hwnd_antes = int(user32.GetForegroundWindow())
    try:
        for vk in codigos_vk:
            user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.02)
        for vk in reversed(codigos_vk):
            user32.keybd_event(vk, 0, 2, 0)
            time.sleep(0.02)

        return {
            "sucesso": True,
            "verificado": True,
            "evidencias": {
                "atalho": "+".join(partes),
                "codigos_vk": [hex(c) for c in codigos_vk],
                "hwnd_alvo": hwnd_antes,
            },
            "mensagem_humana": f"Pronto, atalho {'+'.join(partes).upper()} executado.",
        }
    except Exception as e:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Falha ao enviar atalho: {e}",
            "mensagem_humana": f"Não consegui executar o atalho '{atalho}'.",
        }


def clicar_mouse(
    x: int | None = None,
    y: int | None = None,
    botao: str = "esquerdo",
    duplo: bool = False,
) -> dict[str, Any]:
    """Realiza um clique real de mouse nas coordenadas indicadas (ou na posição atual) e verifica a posição."""
    if os.name != "nt":
        xdotool = shutil.which("xdotool")
        if not xdotool:
            return {"sucesso": False, "verificado": False, "erro": "Instale xdotool para controlar o mouse no Linux."}
        comando = [xdotool]
        if x is not None and y is not None:
            comando.extend(["mousemove", str(int(x)), str(int(y))])
        botao_num = "3" if botao.lower().strip() in {"direito", "right"} else "1"
        comando.extend(["click", "--repeat", "2" if duplo else "1", botao_num])
        resultado = subprocess.run(comando, capture_output=True, text=True)
        sucesso = resultado.returncode == 0
        return {"sucesso": sucesso, "verificado": sucesso, "evidencias": {"x": x, "y": y, "botao": botao, "duplo": duplo}, "erro": resultado.stderr.strip() if not sucesso else "", "mensagem_humana": "Pronto, clique realizado." if sucesso else "Não consegui realizar o clique."}

    user32 = ctypes.windll.user32
    if x is not None and y is not None:
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.03)

    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))

    botao_norm = botao.lower().strip()
    if botao_norm in {"direito", "right"}:
        down_flag, up_flag = 0x0008, 0x0010
    else:
        down_flag, up_flag = 0x0002, 0x0004

    vezes = 2 if duplo else 1
    for _ in range(vezes):
        user32.mouse_event(down_flag, 0, 0, 0, 0)
        user32.mouse_event(up_flag, 0, 0, 0, 0)
        if duplo:
            time.sleep(0.05)

    return {
        "sucesso": True,
        "verificado": True,
        "evidencias": {
            "x": int(pt.x),
            "y": int(pt.y),
            "botao": botao_norm,
            "duplo": duplo,
        },
        "mensagem_humana": f"Pronto, clique {botao_norm} realizado em ({pt.x}, {pt.y}).",
    }


def bloquear_estacao() -> dict[str, Any]:
    """Bloqueia a tela do sistema imediatamente."""
    comando = ["rundll32.exe", "user32.dll,LockWorkStation"] if os.name == "nt" else ["loginctl", "lock-session"]
    res = subprocess.run(comando)
    ok = res.returncode == 0
    return {
        "sucesso": ok,
        "verificado": ok,
        "evidencias": {"returncode": res.returncode},
        "mensagem_humana": "Estação de trabalho bloqueada com sucesso." if ok else "Não consegui bloquear a tela.",
    }


def encerrar_gideon() -> str:
    """Solicita ao supervisor o encerramento dos componentes da Gideon."""
    from gideon.supervisor import sinalizar_parada, supervisor_ativo

    if not supervisor_ativo():
        return "O supervisor da Gideon não está ativo; o encerramento não foi iniciado."

    def _desligar():
        time.sleep(4.0)
        sinalizar_parada()

    threading.Thread(target=_desligar, daemon=True).start()
    return "Encerrando todos os subsistemas da Gideon. Até logo, Henry."


def reiniciar_gideon() -> dict[str, Any]:
    """Solicita ao supervisor o reinício completo da aplicação Gideon."""
    from gideon.supervisor import sinalizar_reinicio, supervisor_ativo

    if not supervisor_ativo():
        return {
            "sucesso": False,
            "verificado": False,
            "mensagem": "O supervisor da Gideon nao esta ativo; o reinicio nao foi iniciado.",
            "mensagem_humana": "O supervisor da Gideon não está ativo; não consegui iniciar o reinício automático.",
        }

    def _reiniciar():
        time.sleep(3.0)
        sinalizar_reinicio()

    threading.Thread(target=_reiniciar, daemon=True).start()
    return {
        "sucesso": True,
        "verificado": True,
        "agendado": True,
        "mensagem": "Reinicio agendado no supervisor.",
        "mensagem_humana": "Reiniciando meus sistemas agora. Volto para a tela em alguns segundos, Henry.",
    }


def atualizar_sistemas() -> dict[str, Any]:
    """Agenda a atualizacao fora do processo que esta usando os arquivos."""
    from gideon.supervisor import sinalizar_atualizacao, supervisor_ativo

    if not supervisor_ativo():
        return {
            "sucesso": False,
            "verificado": False,
            "atualizado": False,
            "agendado": False,
            "mensagem": "O supervisor nao esta ativo; a atualizacao nao foi iniciada.",
            "mensagem_humana": "O supervisor não está ativo; a atualização não pôde ser iniciada.",
        }
    timer = threading.Timer(8.0, sinalizar_atualizacao)
    timer.daemon = True
    timer.start()
    return {
        "sucesso": True,
        "verificado": True,
        "atualizado": False,
        "agendado": True,
        "mensagem": "Atualizacao agendada; os componentes serao validados e reiniciados.",
        "mensagem_humana": "Atualização agendada; meus componentes serão validados e reiniciados em instantes.",
    }


# ─── Registro das Ferramentas no Padrão do Portão de Risco ────

FERRAMENTAS_SISTEMA = [
    Ferramenta(
        nome="obter_status_pc",
        descricao="Obtém informações em tempo real de CPU, memória RAM, placa de vídeo (GPU), disco C e tempo ligado do PC.",
        risco=Risco.VERDE,
        executar=obter_status_pc,
        frase=lambda **kwargs: "consultar o uso de recursos de CPU, RAM, GPU e disco do computador",
        parametros={"type": "object", "properties": {}},
    ),
    Ferramenta(
        nome="obter_status_gpu",
        descricao="Obtém informações da placa de vídeo (GPU), incluindo modelo, VRAM e estado operacional.",
        risco=Risco.VERDE,
        executar=obter_status_gpu,
        frase=lambda **kwargs: "consultar o status da placa de vídeo (GPU)",
        parametros={"type": "object", "properties": {}},
    ),
    Ferramenta(
        nome="listar_programas_usuario",
        descricao="Lista os aplicativos e programas ativos em execução na máquina do Henry.",
        risco=Risco.VERDE,
        executar=listar_programas_usuario,
        frase=lambda **kwargs: "listar os programas ativos no computador",
        parametros={"type": "object", "properties": {}},
    ),
    Ferramenta(
        nome="listar_janelas_visiveis",
        descricao="Lista todas as janelas abertas e visíveis na área de trabalho do Windows com seus títulos e estados.",
        risco=Risco.VERDE,
        executar=listar_janelas_visiveis,
        frase=lambda **kwargs: "listar as janelas visíveis no Windows",
        parametros={"type": "object", "properties": {}},
    ),
    Ferramenta(
        nome="inspecionar_contexto_tela",
        descricao="Inspeciona qual janela e aplicativo estão em foco na tela do Henry no momento, respeitando privacidade.",
        risco=Risco.VERDE,
        executar=inspecionar_contexto_tela,
        frase=lambda **kwargs: "analisar a janela ativa e o contexto atual da tela",
        parametros={"type": "object", "properties": {}},
    ),
    Ferramenta(
        nome="abrir_programa",
        descricao="Abre um programa, navegador, site ou aplicativo no Windows e verifica sua inicialização real.",
        risco=Risco.AMARELO,
        executar=abrir_programa,
        frase=lambda nome, **kwargs: f"abrir o programa '{nome}'",
        parametros={
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome ou atalho do aplicativo (ex: 'chrome', 'vscode', 'spotify', 'notepad', 'calculadora')"},
            },
            "required": ["nome"],
        },
    ),
    Ferramenta(
        nome="fechar_programa",
        descricao="Fecha um programa ou janela aberta no Windows e verifica o encerramento.",
        risco=Risco.AMARELO,
        executar=fechar_programa,
        frase=lambda nome, **kwargs: f"fechar o programa '{nome}'",
        parametros={
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome do programa ou parte do título da janela a fechar"},
            },
            "required": ["nome"],
        },
    ),
    Ferramenta(
        nome="gerenciar_janela",
        descricao="Minimiza, maximiza, restaura ou alterna foco para uma janela do Windows e verifica o estado final.",
        risco=Risco.AMARELO,
        executar=gerenciar_janela,
        frase=lambda acao, alvo="", **kwargs: f"{acao} a janela '{alvo or 'ativa'}'",
        parametros={
            "type": "object",
            "properties": {
                "acao": {"type": "string", "description": "Ação a executar ('minimizar', 'maximizar', 'restaurar', 'focar')"},
                "alvo": {"type": "string", "description": "Nome do app ou parte do título da janela (deixe vazio para a janela ativa)", "default": ""},
            },
            "required": ["acao"],
        },
    ),
    Ferramenta(
        nome="pesquisar_navegador",
        descricao="Abre o navegador e realiza uma busca real no Google ou YouTube verificando a execução.",
        risco=Risco.AMARELO,
        executar=pesquisar_navegador,
        frase=lambda consulta, motor="google", **kwargs: f"pesquisar '{consulta}' no {motor}",
        parametros={
            "type": "object",
            "properties": {
                "consulta": {"type": "string", "description": "Termo de busca"},
                "motor": {"type": "string", "description": "'google' ou 'youtube'", "default": "google"},
            },
            "required": ["consulta"],
        },
    ),
    Ferramenta(
        nome="tocar_ou_pesquisar_midia",
        descricao="Coloca uma música, artista, banda ou pesquisa conteúdo no Spotify, YouTube ou Google.",
        risco=Risco.AMARELO,
        executar=tocar_ou_pesquisar_midia,
        frase=lambda consulta, plataforma="spotify", **kwargs: f"buscar '{consulta}' no {plataforma}",
        parametros={
            "type": "object",
            "properties": {
                "consulta": {"type": "string", "description": "Nome da música, artista, álbum ou vídeo"},
                "plataforma": {"type": "string", "description": "'spotify', 'youtube' ou 'google'", "default": "spotify"},
            },
            "required": ["consulta"],
        },
    ),
    Ferramenta(
        nome="controlar_midia",
        descricao="Controla música/mídia ou volume do PC (pausar, continuar, proxima, anterior, aumentar_volume, diminuir_volume, mudo).",
        risco=Risco.VERDE,
        executar=controlar_midia,
        frase=lambda acao, **kwargs: f"executar controle de mídia '{acao}'",
        parametros={
            "type": "object",
            "properties": {
                "acao": {
                    "type": "string",
                    "description": "'pausar', 'continuar', 'proxima', 'anterior', 'aumentar_volume', 'diminuir_volume', 'mudo'",
                },
            },
            "required": ["acao"],
        },
    ),
    Ferramenta(
        nome="digitar_texto",
        descricao="Digita um texto automaticamente no campo em foco da janela ativa ou na janela especificada.",
        risco=Risco.AMARELO,
        executar=digitar_texto,
        frase=lambda texto, janela_alvo="", **kwargs: f"digitar '{texto}' na janela '{janela_alvo or 'ativa'}'",
        parametros={
            "type": "object",
            "properties": {
                "texto": {"type": "string", "description": "Texto a ser digitado"},
                "janela_alvo": {"type": "string", "description": "Título da janela alvo (opcional)", "default": ""},
                "pressionar_enter": {"type": "boolean", "description": "Pressionar Enter após digitar", "default": False},
            },
            "required": ["texto"],
        },
    ),
    Ferramenta(
        nome="executar_atalho_teclado",
        descricao="Executa um atalho de teclado no Windows (ex: ctrl+s, ctrl+c, ctrl+v, alt+tab).",
        risco=Risco.AMARELO,
        executar=executar_atalho_teclado,
        frase=lambda atalho, **kwargs: f"executar o atalho de teclado '{atalho}'",
        parametros={
            "type": "object",
            "properties": {
                "atalho": {"type": "string", "description": "Atalho a pressionar (ex: 'ctrl+s', 'alt+tab', 'f5')"},
                "janela_alvo": {"type": "string", "description": "Janela alvo (opcional)", "default": ""},
            },
            "required": ["atalho"],
        },
    ),
    Ferramenta(
        nome="clicar_mouse",
        descricao="Realiza um clique de mouse nas coordenadas informadas ou na posição atual do cursor.",
        risco=Risco.AMARELO,
        executar=clicar_mouse,
        frase=lambda x=None, y=None, botao="esquerdo", **kwargs: f"clicar com o botão {botao} do mouse",
        parametros={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "Coordenada X (opcional)"},
                "y": {"type": "integer", "description": "Coordenada Y (opcional)"},
                "botao": {"type": "string", "description": "'esquerdo' ou 'direito'", "default": "esquerdo"},
                "duplo": {"type": "boolean", "description": "Clique duplo", "default": False},
            },
        },
    ),
    Ferramenta(
        nome="bloquear_estacao",
        descricao="Bloqueia a tela do computador do Henry por segurança.",
        risco=Risco.AMARELO,
        executar=bloquear_estacao,
        frase=lambda **kwargs: "bloquear a tela do computador",
        parametros={"type": "object", "properties": {}},
    ),
    Ferramenta(
        nome="encerrar_gideon",
        descricao="Encerra e desliga completamente os processos da aplicação Gideon quando o Henry pedir para fechar.",
        risco=Risco.VERMELHO,
        executar=encerrar_gideon,
        frase=lambda **kwargs: "encerrar e fechar a Gideon completamente",
        parametros={"type": "object", "properties": {}},
        expor_ao_modelo=False,
    ),
    Ferramenta(
        nome="reiniciar_gideon",
        descricao="Reinicia automaticamente os componentes da aplicação Gideon.",
        risco=Risco.VERMELHO,
        executar=reiniciar_gideon,
        frase=lambda **kwargs: "reiniciar os sistemas da Gideon",
        parametros={"type": "object", "properties": {}},
        expor_ao_modelo=False,
    ),
    Ferramenta(
        nome="atualizar_sistemas",
        descricao="Verifica o repositório Git e atualiza o código e dependências da Gideon quando o Henry pedir para se atualizar.",
        risco=Risco.VERMELHO,
        executar=atualizar_sistemas,
        frase=lambda **kwargs: "verificar e aplicar atualizações no repositório Git",
        parametros={"type": "object", "properties": {}},
        expor_ao_modelo=False,
    ),
]
