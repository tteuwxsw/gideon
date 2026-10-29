"""Vigilante Proativo em Segundo Plano da Gideon.

Monitora silenciosamente a saúde do computador (RAM, disco C, CPU travada) e a presença
do Senhor Henry (retorno após inatividade). Gera alertas contextuais e preventivos
respeitando rigorosos períodos de cooldown para jamais interromper o trabalho desnecessariamente.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import shutil
import threading
import time
from typing import Any, Callable

import psutil

from gideon.caminhos import DADOS_DIR

user32 = ctypes.windll.user32 if os.name == "nt" else None
kernel32 = ctypes.windll.kernel32 if os.name == "nt" else None


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def _tempo_ocioso_segundos() -> float:
    """Retorna quanto tempo o teclado e mouse do Windows estão ociosos (sem interação)."""
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
            tick = kernel32.GetTickCount()
            delta_ms = tick - lii.dwTime
            return max(0.0, delta_ms / 1000.0)
    except Exception:
        pass
    return 0.0


class VigilanteProativo:
    """Thread sentinela que observa recursos e interação do usuário."""

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

        # Cooldowns em segundos para evitar alertas repetitivos
        self._cooldowns: dict[str, float] = {
            "ram_alta": 0.0,
            "disco_cheio": 0.0,
            "cpu_alta": 0.0,
            "retorno_ausente": 0.0,
        }

        # Contadores de persistência (evita falsos positivos em picos momentâneos)
        self._contagem_ram_alta = 0
        self._contagem_cpu_alta = 0
        self._estava_ausente = False

    def iniciar(self) -> None:
        """Inicia o monitoramento proativo em segundo plano."""
        with self._lock:
            if self.ativo:
                return
            self.ativo = True
            self._thread = threading.Thread(target=self._loop_vigilante, daemon=True, name="vigilante_gideon")
            self._thread.start()
            print("  [Vigilante] Sistema de monitoramento proativo ATIVADO.")

    def parar(self) -> None:
        """Interrompe o monitoramento silencioso."""
        with self._lock:
            self.ativo = False
            print("  [Vigilante] Sistema de monitoramento proativo DESATIVADO.")

    def _disparar_alerta(self, tipo: str, mensagem: str, nivel: str = "aviso", pode_falar: bool = False) -> None:
        """Dispara evento para WebSocket e opcionalmente fala via TTS."""
        evento = {
            "tipo": "alerta_vigilante",
            "subtipo": tipo,
            "nivel": nivel,
            "mensagem": mensagem,
            "timestamp": time.strftime("%H:%M:%S"),
        }

        if self.notificador:
            try:
                self.notificador(evento)
            except Exception:
                pass

        if pode_falar and self.fala_callback:
            try:
                self.fala_callback(mensagem)
            except Exception:
                pass

    def _loop_vigilante(self) -> None:
        """Ciclo de checagem a cada 25 segundos."""
        while self.ativo:
            try:
                agora = time.time()

                # 1. Detecção de presença / retorno após inatividade
                ocioso_s = _tempo_ocioso_segundos()
                limite_ausencia = 40.0 * 60.0  # 40 minutos

                if ocioso_s >= limite_ausencia:
                    self._estava_ausente = True
                elif self._estava_ausente and ocioso_s < 15.0:
                    # Henry acabou de voltar ao teclado!
                    self._estava_ausente = False
                    if agora - self._cooldowns["retorno_ausente"] > 1800.0:  # 30 min cooldown
                        self._cooldowns["retorno_ausente"] = agora
                        msg = "Bem-vindo de volta, Senhor Henry. Seus sistemas estão operando normalmente. Posso ajudar em algo?"
                        self._disparar_alerta("retorno", msg, nivel="info", pode_falar=True)

                # 2. Verificação de Memória RAM (> 91% por 2 ciclos seguidos)
                mem = psutil.virtual_memory()
                if mem.percent >= 91.0:
                    self._contagem_ram_alta += 1
                    if self._contagem_ram_alta >= 2:
                        if agora - self._cooldowns["ram_alta"] > 2700.0:  # 45 min cooldown
                            self._cooldowns["ram_alta"] = agora
                            msg = f"Senhor Henry, o consumo de memória RAM atingiu {mem.percent:.0f}%. Se desejar, posso fechar abas ou tarefas secundárias para liberar recursos."
                            self._disparar_alerta("ram_alta", msg, nivel="alerta", pode_falar=False)
                else:
                    self._contagem_ram_alta = 0

                # 3. Verificação de Espaço em Disco C: (< 15 GB)
                try:
                    disco_c = shutil.disk_usage("C:\\" if os.name == "nt" else "/")
                    gb_livres = disco_c.free / (1024 ** 3)
                    if gb_livres < 15.0:
                        if agora - self._cooldowns["disco_cheio"] > 7200.0:  # 2 horas cooldown
                            self._cooldowns["disco_cheio"] = agora
                            unidade = "disco C:" if os.name == "nt" else "disco principal"
                            msg = f"Aviso de armazenamento: restam apenas {gb_livres:.1f} GB livres no {unidade}. Recomendo uma limpeza preventiva de arquivos temporários."
                            self._disparar_alerta("disco_cheio", msg, nivel="aviso", pode_falar=False)
                except Exception:
                    pass

                # 4. Verificação de CPU sustentada (> 94% por 3 ciclos seguidos)
                cpu_uso = psutil.cpu_percent(interval=None)
                if cpu_uso >= 94.0:
                    self._contagem_cpu_alta += 1
                    if self._contagem_cpu_alta >= 3:
                        if agora - self._cooldowns["cpu_alta"] > 1800.0:  # 30 min cooldown
                            self._cooldowns["cpu_alta"] = agora
                            msg = f"Detectei uma carga contínua e elevada no processador ({cpu_uso:.0f}%). Deseja que eu liste os processos mais pesados?"
                            self._disparar_alerta("cpu_alta", msg, nivel="alerta", pode_falar=False)
                else:
                    self._contagem_cpu_alta = 0

            except Exception as e:
                print(f"  [Vigilante] Erro no ciclo de checagem: {e}")

            # Dorme 25 segundos entre as verificações sem travar a CPU
            for _ in range(50):
                if not self.ativo:
                    break
                time.sleep(0.5)


_instancia_vigilante: VigilanteProativo | None = None


def obter_vigilante(
    notificador: Callable[[dict[str, Any]], None] | None = None,
    fala_callback: Callable[[str], None] | None = None,
) -> VigilanteProativo:
    """Retorna a instância única do vigilante proativo."""
    global _instancia_vigilante
    if _instancia_vigilante is None:
        _instancia_vigilante = VigilanteProativo(notificador=notificador, fala_callback=fala_callback)
    return _instancia_vigilante
