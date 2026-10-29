"""Monitoramento proativo local, com cooldown, silêncio e privacidade."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime
import os
import shutil
import socket
import subprocess
import threading
import time
from typing import Any, Callable

import psutil

from gideon.configuracao import (
    obter_configuracao_avisos,
    obter_modo_atividade,
    obter_modo_personalidade,
)

user32 = ctypes.windll.user32 if os.name == "nt" else None
kernel32 = ctypes.windll.kernel32 if os.name == "nt" else None


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def _tempo_ocioso_segundos() -> float:
    """Retorna o tempo sem teclado/mouse, com fallback conservador no Linux."""
    try:
        if os.name != "nt":
            xprintidle = shutil.which("xprintidle")
            if not xprintidle:
                return 0.0
            resultado = subprocess.run([xprintidle], capture_output=True, text=True, timeout=1)
            return max(0.0, float(resultado.stdout.strip()) / 1000.0)
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if user32.GetLastInputInfo(ctypes.byref(lii)):
            return max(0.0, (kernel32.GetTickCount() - lii.dwTime) / 1000.0)
    except Exception:
        pass
    return 0.0


def _internet_disponivel() -> bool:
    """Faz somente um handshake TCP curto; nenhum dado do sistema é enviado."""
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=1.5):
            return True
    except OSError:
        return False


def _em_horario_silencioso(config: dict[str, Any], momento: datetime | None = None) -> bool:
    momento = momento or datetime.now()
    try:
        inicio_h, inicio_m = map(int, str(config["horario_silencioso_inicio"]).split(":"))
        fim_h, fim_m = map(int, str(config["horario_silencioso_fim"]).split(":"))
    except (KeyError, TypeError, ValueError):
        return False
    atual = momento.hour * 60 + momento.minute
    inicio = inicio_h * 60 + inicio_m
    fim = fim_h * 60 + fim_m
    return inicio <= atual < fim if inicio < fim else atual >= inicio or atual < fim


class VigilanteProativo:
    """Thread sentinela que observa recursos locais e lembretes persistentes."""

    def __init__(
        self,
        notificador: Callable[[dict[str, Any]], None] | None = None,
        fala_callback: Callable[[str], None] | None = None,
    ):
        self.notificador = notificador
        self.fala_callback = fala_callback
        self.ativo = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._cooldowns: dict[str, float] = {}
        self._contagem_ram_alta = 0
        self._contagem_cpu_alta = 0
        self._falhas_internet = 0
        self._estava_ausente = False
        self._inicio_uso_continuo = time.time()

    def iniciar(self) -> None:
        with self._lock:
            if self.ativo:
                return
            self.ativo = True
            self._thread = threading.Thread(target=self._loop_vigilante, daemon=True, name="vigilante_gideon")
            self._thread.start()
            print("  [Vigilante] Sistema de monitoramento proativo ATIVADO.")

    def parar(self) -> None:
        with self._lock:
            self.ativo = False
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)
        print("  [Vigilante] Sistema de monitoramento proativo DESATIVADO.")

    @staticmethod
    def _mensagem_personalizada(mensagem: str) -> str:
        modo = obter_modo_personalidade()
        if modo == "direta":
            return mensagem.replace("Senhor Henry, ", "")
        if modo == "formal" and not mensagem.startswith("Senhor"):
            return f"Senhor Henry, {mensagem[0].lower()}{mensagem[1:]}"
        if modo == "sarcastica":
            complemento = " Até máquinas agradecem uma pausa." if "pausa" in mensagem.lower() else " Convém não testar a sorte."
            return mensagem + complemento
        return mensagem

    def _cooldown_liberado(self, tipo: str, config: dict[str, Any], agora: float) -> bool:
        base = tipo.split(":", 1)[0]
        minutos = float(config.get("cooldown_minutos", {}).get(base, 30))
        if agora - self._cooldowns.get(tipo, 0.0) < minutos * 60:
            return False
        self._cooldowns[tipo] = agora
        return True

    def _disparar_alerta(
        self,
        tipo: str,
        mensagem: str,
        config: dict[str, Any],
        nivel: str = "aviso",
        pode_falar: bool = True,
    ) -> None:
        mensagem = self._mensagem_personalizada(mensagem)
        evento = {
            "tipo": "alerta_vigilante",
            "subtipo": tipo.split(":", 1)[0],
            "nivel": nivel,
            "mensagem": mensagem,
            "timestamp": time.strftime("%H:%M:%S"),
        }
        if self.notificador:
            try:
                self.notificador(evento)
            except Exception:
                pass

        pode_falar = (
            pode_falar
            and obter_modo_atividade() not in {"foco", "cinema"}
            and not _em_horario_silencioso(config)
        )
        if pode_falar and self.fala_callback:
            try:
                self.fala_callback(mensagem)
            except Exception:
                pass

    def _verificar_lembretes(self, config: dict[str, Any], agora_ts: float) -> None:
        if not config.get("compromissos", True):
            return
        try:
            from gideon import automacoes

            momento = automacoes.agora()
            antecedencia = max(1, int(config.get("antecedencia_compromisso_minutos", 15)))
            for item in automacoes.listar():
                if not item.get("ativa") or not str(item.get("nome", "")).lower().startswith("lembrete:"):
                    continue
                proxima = automacoes.proxima_execucao(item, momento)
                minutos = (proxima - momento).total_seconds() / 60 if proxima else -1
                chave = f"compromisso_proximo:{item.get('id', item.get('nome'))}"
                if 0 < minutos <= antecedencia and self._cooldown_liberado(chave, config, agora_ts):
                    msg = f"Lembrete próximo em {max(1, round(minutos))} minutos: {item['nome'].removeprefix('Lembrete:').strip()}."
                    self._disparar_alerta(chave, msg, config, nivel="info")
        except Exception:
            pass

    def _executar_ciclo(self) -> None:
        config = obter_configuracao_avisos()
        agora_ts = time.time()
        ocioso_s = _tempo_ocioso_segundos()

        if ocioso_s >= 40 * 60:
            self._estava_ausente = True
        elif self._estava_ausente and ocioso_s < 15:
            self._estava_ausente = False
            if config.get("retorno", True) and self._cooldown_liberado("retorno_ausente", config, agora_ts):
                self._disparar_alerta("retorno_ausente", "Bem-vindo de volta, Senhor Henry.", config, nivel="info")

        if config.get("bateria", True):
            try:
                bateria = psutil.sensors_battery()
            except Exception:
                bateria = None
            if bateria and not bateria.power_plugged and bateria.percent <= 20:
                if self._cooldown_liberado("bateria_baixa", config, agora_ts):
                    self._disparar_alerta("bateria_baixa", f"Bateria em {bateria.percent:.0f}%. Conecte o carregador.", config, nivel="alerta")

        if config.get("ram", True):
            mem = psutil.virtual_memory()
            self._contagem_ram_alta = self._contagem_ram_alta + 1 if mem.percent >= 91 else 0
            if self._contagem_ram_alta >= 2 and self._cooldown_liberado("ram_alta", config, agora_ts):
                self._disparar_alerta("ram_alta", f"RAM em {mem.percent:.0f}%. Há pressão de memória.", config, nivel="alerta")

        if config.get("cpu", True):
            cpu = psutil.cpu_percent(interval=None)
            self._contagem_cpu_alta = self._contagem_cpu_alta + 1 if cpu >= 94 else 0
            if self._contagem_cpu_alta >= 3 and self._cooldown_liberado("cpu_alta", config, agora_ts):
                self._disparar_alerta("cpu_alta", f"CPU sustentada em {cpu:.0f}%.", config, nivel="alerta")

        if config.get("disco", True):
            disco = shutil.disk_usage("C:\\" if os.name == "nt" else "/")
            gb_livres = disco.free / (1024 ** 3)
            percentual = disco.used / disco.total * 100 if disco.total else 0
            if (gb_livres < 15 or percentual >= 90) and self._cooldown_liberado("disco_cheio", config, agora_ts):
                self._disparar_alerta("disco_cheio", f"Disco quase cheio: {gb_livres:.1f} GB livres.", config)

        if config.get("temperatura", True):
            try:
                temperaturas = psutil.sensors_temperatures() if hasattr(psutil, "sensors_temperatures") else {}
            except Exception:
                temperaturas = {}
            valores = [float(e.current) for entradas in temperaturas.values() for e in entradas if e.current is not None]
            maxima = max(valores, default=0.0)
            if maxima >= 85 and self._cooldown_liberado("temperatura_alta", config, agora_ts):
                self._disparar_alerta("temperatura_alta", f"Temperatura alta detectada: {maxima:.0f} graus.", config, nivel="alerta")

        if config.get("internet", True):
            self._falhas_internet = self._falhas_internet + 1 if not _internet_disponivel() else 0
            if self._falhas_internet >= 2 and self._cooldown_liberado("internet_caindo", config, agora_ts):
                self._disparar_alerta("internet_caindo", "A conexão com a internet parece instável.", config)

        if config.get("pausa", True):
            if ocioso_s > 5 * 60:
                self._inicio_uso_continuo = agora_ts
            limite = max(15, int(config.get("pausa_minutos", 90))) * 60
            if agora_ts - self._inicio_uso_continuo >= limite and self._cooldown_liberado("pausa_uso", config, agora_ts):
                self._inicio_uso_continuo = agora_ts
                self._disparar_alerta("pausa_uso", "Você está em uso contínuo. Faça uma pausa breve.", config, nivel="info")

        self._verificar_lembretes(config, agora_ts)

    def _loop_vigilante(self) -> None:
        while self.ativo:
            try:
                self._executar_ciclo()
            except Exception as erro:
                print(f"  [Vigilante] Erro no ciclo de checagem: {erro}")
            for _ in range(50):
                if not self.ativo:
                    break
                time.sleep(0.5)


_instancia_vigilante: VigilanteProativo | None = None


def obter_vigilante(
    notificador: Callable[[dict[str, Any]], None] | None = None,
    fala_callback: Callable[[str], None] | None = None,
) -> VigilanteProativo:
    global _instancia_vigilante
    if _instancia_vigilante is None:
        _instancia_vigilante = VigilanteProativo(notificador=notificador, fala_callback=fala_callback)
    elif notificador is not None:
        _instancia_vigilante.notificador = notificador
        _instancia_vigilante.fala_callback = fala_callback
    return _instancia_vigilante
