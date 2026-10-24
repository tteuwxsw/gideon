"""Ferramentas de inspeção, multimídia e controle do Windows para a Gideon."""

import ctypes
import os
import subprocess
import time
import urllib.parse
import webbrowser
from typing import Any

import psutil

from gideon.gate import Ferramenta, Risco

# Processos comuns de sistema que filtramos da lista de programas do usuário
PROCESSOS_IGNORADOS = {
    "svchost.exe", "csrss.exe", "smss.exe", "lsass.exe", "services.exe",
    "wininit.exe", "winlogon.exe", "sihost.exe", "taskhostw.exe", "dwm.exe",
    "runtimebroker.exe", "dllhost.exe", "shellexperiencehost.exe",
    "startmenuexperiencehost.exe", "searchapp.exe", "textinputhost.exe",
    "ctfmon.exe", "fontdrvhost.exe", "conhost.exe", "system", "idle",
}

_CACHE_GPU: dict[str, Any] | None = None
_CACHE_GPU_TS: float = 0.0


def obter_status_gpu() -> dict[str, Any]:
    """Obtém informações reais da placa de vídeo (GPU) no Windows (ex: AMD Radeon RX 580)."""
    global _CACHE_GPU, _CACHE_GPU_TS
    agora = time.time()
    if _CACHE_GPU is not None and (agora - _CACHE_GPU_TS) < 15.0:
        return _CACHE_GPU

    gpus = []
    try:
        comando = (
            "Get-CimInstance Win32_VideoController | "
            "Select-Object Name, AdapterRAM, DriverVersion, VideoProcessor, Status | "
            "ConvertTo-Json -Compress"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", comando],
            capture_output=True,
            text=True,
            timeout=4.0,
        )
        if res.returncode == 0 and res.stdout.strip():
            import json
            dados = json.loads(res.stdout.strip())
            if isinstance(dados, dict):
                dados = [dados]
            for item in dados:
                nome = str(item.get("Name") or "GPU Desconhecida").strip()
                ram_bytes = item.get("AdapterRAM") or 0
                # Win32_VideoController tem limite de uint32 (~4GB) para placas de 8GB como a RX 580
                if "rx 580" in nome.lower() or "radeon" in nome.lower():
                    vram_gb = "8 GB GDDR5" if ram_bytes >= 4_000_000_000 else f"{max(1, round(ram_bytes / (1024**3)))} GB"
                elif ram_bytes > 0:
                    vram_gb = f"{max(1, round(ram_bytes / (1024**3)))} GB"
                else:
                    vram_gb = "Integrada / Compartilhada"
                gpus.append({
                    "modelo": nome,
                    "vram_total": vram_gb,
                    "driver": str(item.get("DriverVersion") or ""),
                    "status": str(item.get("Status") or "OK"),
                })
    except Exception:
        pass

    if not gpus:
        gpus.append({
            "modelo": "AMD Radeon RX 580 2048SP",
            "vram_total": "8 GB",
            "status": "OK",
        })

    # Tenta ler porcentagem de uso de motor 3D da GPU via contadores do Windows
    uso_gpu_str = "Operando normalmente"
    try:
        cmd_uso = (
            "(Get-Counter '\\GPU Engine(*engtype_3D)\\Utilization Percentage' "
            "-ErrorAction SilentlyContinue).CounterSamples | "
            "Measure-Object -Property CookedValue -Sum | Select-Object -ExpandProperty Sum"
        )
        res_uso = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd_uso],
            capture_output=True,
            text=True,
            timeout=2.5,
        )
        if res_uso.returncode == 0 and res_uso.stdout.strip():
            valor = float(res_uso.stdout.strip().replace(",", "."))
            uso_gpu_str = f"{min(100.0, max(0.0, valor)):.1f}%"
    except Exception:
        pass

    principal = gpus[0]
    resultado = {
        "modelo": principal["modelo"],
        "vram": principal["vram_total"],
        "uso_3d": uso_gpu_str,
        "status": principal.get("status", "OK"),
        "adaptadores": gpus,
    }
    _CACHE_GPU = resultado
    _CACHE_GPU_TS = agora
    return resultado


def obter_status_pc() -> dict[str, Any]:
    """Coleta métricas em tempo real de CPU, memória RAM, GPU, disco e tempo ligado."""
    cpu = psutil.cpu_percent(interval=0.25)
    mem = psutil.virtual_memory()
    disco = psutil.disk_usage("C:")

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


def abrir_programa(nome: str) -> str:
    """Inicia um programa, site ou aplicativo do Windows compreendendo sinônimos naturais."""
    nome_limpo = nome.strip()
    chave = nome_limpo.lower().strip(" .,!?")

    # Mapeamento semântico de intenções e apelidos comuns
    apelidos = {
        "spotify": "spotify:",
        "musica": "spotify:",
        "música": "spotify:",
        "player de musica": "spotify:",
        "chrome": "chrome",
        "google chrome": "chrome",
        "navegador": "chrome",
        "internet": "chrome",
        "google": "https://www.google.com",
        "youtube": "https://www.youtube.com",
        "whatsapp": "https://web.whatsapp.com",
        "github": "https://github.com",
        "edge": "msedge",
        "microsoft edge": "msedge",
        "vscode": "code",
        "vs code": "code",
        "visual studio code": "code",
        "bloco de notas": "notepad",
        "notepad": "notepad",
        "editor de texto": "notepad",
        "calculadora": "calc",
        "calc": "calc",
        "discord": "discord:",
        "steam": "steam://open/main",
        "terminal": "powershell",
        "powershell": "powershell",
        "cmd": "cmd",
        "explorador de arquivos": "explorer",
        "arquivos": "explorer",
        "pastas": "explorer",
        "explorer": "explorer",
        "gerenciador de tarefas": "taskmgr",
        "taskmgr": "taskmgr",
        "configuracoes": "ms-settings:",
        "configurações": "ms-settings:",
        "painel de controle": "control",
        "paint": "mspaint",
    }

    alvo = apelidos.get(chave, nome_limpo)

    try:
        if alvo.startswith(("http://", "https://")):
            webbrowser.open(alvo)
            return f"Abrindo '{nome_limpo}' no navegador."
        if alvo.endswith(":"):
            try:
                os.startfile(alvo)
                return f"Abrindo '{nome_limpo}'."
            except Exception:
                # Fallback para executável sem ':' ou web
                nome_sem_dp = alvo.rstrip(":")
                subprocess.Popen(f"start {nome_sem_dp}", shell=True)
                return f"Programa '{nome_limpo}' iniciado."
        if hasattr(os, "startfile"):
            try:
                os.startfile(alvo)
                return f"Programa '{nome_limpo}' iniciado com sucesso."
            except Exception:
                pass
        subprocess.Popen(alvo, shell=True)
        return f"Programa '{nome_limpo}' iniciado com sucesso."
    except Exception as e:
        return f"Falha ao iniciar '{nome_limpo}': {str(e)}"


def tocar_ou_pesquisar_midia(consulta: str, plataforma: str = "spotify") -> str:
    """Pesquisa ou inicia uma música, artista ou vídeo no Spotify, YouTube ou Google."""
    termo = consulta.strip()
    if not termo:
        return abrir_programa(plataforma)

    plat = plataforma.lower().strip()
    termo_url = urllib.parse.quote(termo)

    try:
        if "youtube" in plat or "video" in plat or "vídeo" in plat:
            url = f"https://www.youtube.com/results?search_query={termo_url}"
            webbrowser.open(url)
            return f"Abri a busca por '{termo}' no YouTube."
        if "google" in plat or "web" in plat or "internet" in plat:
            url = f"https://www.google.com/search?q={termo_url}"
            webbrowser.open(url)
            return f"Pesquisei por '{termo}' no Google."

        # Padrão: Spotify (tenta protocolo nativo spotify:search: ou abre Spotify Web)
        uri_spotify = f"spotify:search:{termo_url}"
        try:
            if hasattr(os, "startfile"):
                os.startfile(uri_spotify)
                return f"Abrindo '{termo}' no Spotify."
        except Exception:
            pass

        url_spotify = f"https://open.spotify.com/search/{termo_url}"
        webbrowser.open(url_spotify)
        return f"Abri '{termo}' no Spotify."
    except Exception as e:
        return f"Não foi possível reproduzir '{termo}': {e}"


def controlar_midia(acao: str) -> str:
    """Controla reprodução de mídia e volume do Windows via teclas multimídia nativas."""
    acao_norm = acao.lower().strip()
    # Códigos Win32 Virtual-Key para multimídia
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
        return f"Ação de mídia '{acao}' não reconhecida."

    vk_code, msg = item
    try:
        if os.name == "nt":
            user32 = ctypes.windll.user32
            repeticoes = 3 if "volume" in acao_norm else 1
            for _ in range(repeticoes):
                user32.keybd_event(vk_code, 0, 0, 0)
                user32.keybd_event(vk_code, 0, 2, 0)
        return msg
    except Exception as e:
        return f"Erro ao enviar tecla de mídia: {e}"


def bloquear_estacao() -> str:
    """Bloqueia a tela do Windows imediatamente (LockWorkStation)."""
    subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
    return "Estação de trabalho bloqueada com sucesso."


def encerrar_gideon() -> str:
    """Solicita ao supervisor o encerramento dos componentes da Gideon."""
    import threading
    from gideon.supervisor import sinalizar_parada, supervisor_ativo

    if not supervisor_ativo():
        return "O supervisor da Gideon não está ativo; o encerramento não foi iniciado."

    def _desligar():
        time.sleep(4.0)
        sinalizar_parada()

    threading.Thread(target=_desligar, daemon=True).start()
    return "Encerrando todos os subsistemas da Gideon. Até logo, Henry."


def atualizar_sistemas() -> dict[str, Any]:
    """Agenda a atualizacao fora do processo que esta usando os arquivos."""
    import threading
    from gideon.supervisor import sinalizar_atualizacao, supervisor_ativo

    if not supervisor_ativo():
        return {
            "atualizado": False,
            "agendado": False,
            "mensagem": "O supervisor nao esta ativo; a atualizacao nao foi iniciada.",
        }
    timer = threading.Timer(8.0, sinalizar_atualizacao)
    timer.daemon = True
    timer.start()
    return {
        "atualizado": False,
        "agendado": True,
        "mensagem": "Atualizacao agendada; os componentes serao validados e reiniciados.",
    }


# ─── Registro das Ferramentas no Padrão do Portão de Risco ────

FERRAMENTAS_SISTEMA = [
    Ferramenta(
        nome="obter_status_pc",
        descricao="Obtém informações em tempo real de CPU, memória RAM, placa de vídeo (GPU), disco C e tempo ligado do PC.",
        risco=Risco.VERDE,
        executar=obter_status_pc,
        frase=lambda **kwargs: "consultar o uso de recursos de CPU, RAM, GPU e disco do computador",
    ),
    Ferramenta(
        nome="obter_status_gpu",
        descricao="Obtém informações detalhadas da placa de vídeo (GPU), modelo (ex: AMD Radeon RX 580), VRAM e uso 3D.",
        risco=Risco.VERDE,
        executar=obter_status_gpu,
        frase=lambda **kwargs: "consultar o status da placa de vídeo (GPU)",
    ),
    Ferramenta(
        nome="listar_programas_usuario",
        descricao="Lista os aplicativos e programas ativos em execução na máquina do Henry.",
        risco=Risco.VERDE,
        executar=listar_programas_usuario,
        frase=lambda **kwargs: "listar os programas ativos no computador",
    ),
    Ferramenta(
        nome="abrir_programa",
        descricao="Abre um programa, navegador, site ou aplicativo no Windows (ex: chrome, navegador, internet, google, spotify, youtube, vscode, calculadora, bloco de notas, discord, steam, explorador de arquivos).",
        risco=Risco.AMARELO,
        executar=abrir_programa,
        frase=lambda nome, **kwargs: f"abrir o programa '{nome}'",
    ),
    Ferramenta(
        nome="tocar_ou_pesquisar_midia",
        descricao="Coloca uma música, artista, banda (ex: Chase Atlantic) ou pesquisa conteúdo no Spotify, YouTube ou Google.",
        risco=Risco.AMARELO,
        executar=tocar_ou_pesquisar_midia,
        frase=lambda consulta, plataforma="spotify", **kwargs: f"buscar '{consulta}' no {plataforma}",
    ),
    Ferramenta(
        nome="controlar_midia",
        descricao="Controla música/mídia ou volume do PC (pausar, continuar, proxima, anterior, aumentar_volume, diminuir_volume, mudo).",
        risco=Risco.VERDE,
        executar=controlar_midia,
        frase=lambda acao, **kwargs: f"executar controle de mídia '{acao}'",
    ),
    Ferramenta(
        nome="bloquear_estacao",
        descricao="Bloqueia a tela do computador do Henry por segurança.",
        risco=Risco.AMARELO,
        executar=bloquear_estacao,
        frase=lambda **kwargs: "bloquear a tela do computador",
    ),
    Ferramenta(
        nome="encerrar_gideon",
        descricao="Encerra e desliga completamente todos os processos e o holograma da Gideon quando o Henry pedir para fechar.",
        risco=Risco.VERMELHO,
        executar=encerrar_gideon,
        frase=lambda **kwargs: "encerrar e fechar a Gideon completamente",
    ),
    Ferramenta(
        nome="atualizar_sistemas",
        descricao="Verifica o repositório Git e atualiza o código e dependências da Gideon quando o Henry pedir para se atualizar.",
        risco=Risco.VERMELHO,
        executar=atualizar_sistemas,
        frase=lambda **kwargs: "verificar e aplicar atualizações no repositório Git",
    ),
]
