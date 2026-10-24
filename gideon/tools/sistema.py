"""Ferramentas de inspeção e controle do sistema operacional Windows para a Gideon."""

import os
import subprocess
import time
import psutil
from typing import Any

from gideon.gate import Ferramenta, Risco

# Processos comuns de sistema que filtramos da lista de programas do usuário
PROCESSOS_IGNORADOS = {
    "svchost.exe", "csrss.exe", "smss.exe", "lsass.exe", "services.exe",
    "wininit.exe", "winlogon.exe", "sihost.exe", "taskhostw.exe", "dwm.exe",
    "runtimebroker.exe", "dllhost.exe", "shellexperiencehost.exe",
    "startmenuexperiencehost.exe", "searchapp.exe", "textinputhost.exe",
    "ctfmon.exe", "fontdrvhost.exe", "conhost.exe", "system", "idle",
}


def obter_status_pc() -> dict[str, Any]:
    """Coleta métricas em tempo real de CPU, memória RAM, disco e tempo ligado."""
    cpu = psutil.cpu_percent(interval=0.3)
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

    return {
        "cpu_percent": f"{cpu}%",
        "memoria_ram": {
            "percentual": f"{mem.percent}%",
            "usado_gb": f"{mem.used / 1024**3:.2f} GB",
            "total_gb": f"{mem.total / 1024**3:.2f} GB",
            "livre_gb": f"{mem.available / 1024**3:.2f} GB",
        },
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
                # Remove extensão .exe para fala natural
                nome_limpo = os.path.splitext(nome)[0]
                programas.add(nome_limpo)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Ordena alfabeticamente
    return sorted(list(programas))


def abrir_programa(nome: str) -> str:
    """Inicia um programa ou aplicativo do Windows."""
    nome_limpo = nome.strip()

    # Mapeamento de apelidos comuns
    apelidos = {
        "spotify": "spotify",
        "chrome": "chrome",
        "google chrome": "chrome",
        "navegador": "chrome",
        "vscode": "code",
        "vs code": "code",
        "bloco de notas": "notepad",
        "notepad": "notepad",
        "calculadora": "calc",
        "discord": "discord",
        "steam": "steam",
        "terminal": "powershell",
    }

    comando = apelidos.get(nome_limpo.lower(), nome_limpo)

    try:
        subprocess.Popen(comando, shell=True)
        return f"Programa '{nome_limpo}' iniciado com sucesso."
    except Exception as e:
        return f"Falha ao iniciar '{nome_limpo}': {str(e)}"


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
        descricao="Obtém informações em tempo real de CPU, memória RAM, disco C e tempo ligado do PC.",
        risco=Risco.VERDE,
        executar=obter_status_pc,
        frase=lambda **kwargs: "consultar o uso de recursos de CPU, RAM e disco do computador",
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
        descricao="Abre um programa ou aplicativo no Windows (ex: spotify, chrome, notepad, code, calc).",
        risco=Risco.AMARELO,
        executar=abrir_programa,
        frase=lambda nome, **kwargs: f"abrir o programa '{nome}'",
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
