"""Sensor de Consciência de Desktop da Gideon (Movimento do Mouse, Janela Ativa e Atenção Contextual).

Opera sem capturas constantes de tela (zero screenshots em background), utilizando exclusivamente
eventos leves da API Win32 (`GetCursorPos`, `GetForegroundWindow`, `GetWindowRect`) com proteção de privacidade.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import threading
import time
from typing import Any, Callable

import psutil


# Aplicativos e palavras-chave excluídos por privacidade (nunca expõem título detalhado)
PADROES_PRIVACIDADE_EXCLUIDOS = (
    "keepass",
    "1password",
    "bitwarden",
    "lastpass",
    "credwiz",
    "senha",
    "password",
    "banco",
    "internet banking",
    "metamask",
    "anonima",
    "incognito",
    "inprivate",
)


def _obter_resolucao_tela() -> tuple[int, int]:
    if os.name != "nt":
        return (1920, 1080)
    try:
        user32 = ctypes.windll.user32
        largura = int(user32.GetSystemMetrics(0)) or 1920
        altura = int(user32.GetSystemMetrics(1)) or 1080
        return (largura, altura)
    except Exception:
        return (1920, 1080)


def obter_posicao_cursor_normalizada(
    ancora_avatar_x: float = 0.80,
    ancora_avatar_y: float = 0.55,
) -> dict[str, Any]:
    """Lê a posição real do cursor do mouse no Windows e calcula o vetor de olhar suave da Gideon."""
    largura, altura = _obter_resolucao_tela()
    if os.name != "nt":
        return {"x_px": largura // 2, "y_px": altura // 2, "x_olhar": 0.0, "y_olhar": 0.0}

    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))

    # Normaliza posição do mouse em [0.0, 1.0]
    norm_x = max(0.0, min(1.0, pt.x / float(largura)))
    norm_y = max(0.0, min(1.0, pt.y / float(altura)))

    # Calcula direção relativa ao rosto da Gideon na tela:
    # Quando o usuário move o mouse para a esquerda da tela, a Gideon olha discretamente para a esquerda (da câmera)
    dx = norm_x - ancora_avatar_x
    dy = ancora_avatar_y - norm_y  # Y invertido: topo da tela = olhar para cima (+Y)

    # Limita a amplitude para movimento ocular humano sutil e natural
    x_olhar = round(max(-0.14, min(0.14, dx * 0.22)), 4)
    y_olhar = round(max(-0.10, min(0.10, dy * 0.18)), 4)

    return {
        "x_px": int(pt.x),
        "y_px": int(pt.y),
        "x_olhar": x_olhar,
        "y_olhar": y_olhar,
    }


def inspecionar_janela_ativa_segura(apps_excluidos: list[str] | None = None) -> dict[str, Any]:
    """Obtém informações reais da janela ativa no Windows respeitando filtros de privacidade."""
    if os.name != "nt":
        return {
            "hwnd": 0,
            "titulo": "Ambiente de Teste",
            "processo": "python",
            "protegida_privacidade": False,
            "x_olhar": 0.0,
            "y_olhar": 0.0,
        }

    user32 = ctypes.windll.user32
    hwnd = int(user32.GetForegroundWindow())
    exclusoes = list(PADROES_PRIVACIDADE_EXCLUIDOS) + [e.lower() for e in (apps_excluidos or []) if e]

    if hwnd == 0:
        protegida_zero = any(padrao in "área de trabalho explorer.exe" for padrao in exclusoes)
        return {
            "hwnd": 0,
            "titulo": "[Janela Protegida por Privacidade]" if protegida_zero else "Área de Trabalho",
            "processo": "explorer.exe",
            "protegida_privacidade": protegida_zero,
            "x_olhar": 0.0,
            "y_olhar": 0.0,
        }

    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    titulo_bruto = buf.value.strip() or "Área de Trabalho"

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    pid_val = int(pid.value)
    nome_proc = ""
    try:
        nome_proc = psutil.Process(pid_val).name()
    except Exception:
        pass

    # Calcula o centro da janela na tela para direcionar o olhar contextual
    rect = wintypes.RECT()
    largura, altura = _obter_resolucao_tela()
    cx_norm, cy_norm = 0.5, 0.5
    dimensoes = {"esquerda": 0, "topo": 0, "largura": largura, "altura": altura}
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        w_jan = max(1, rect.right - rect.left)
        h_jan = max(1, rect.bottom - rect.top)
        cx_norm = ((rect.left + rect.right) / 2.0) / float(largura)
        cy_norm = ((rect.top + rect.bottom) / 2.0) / float(altura)
        dimensoes = {
            "esquerda": int(rect.left),
            "topo": int(rect.top),
            "largura": int(w_jan),
            "altura": int(h_jan),
        }

    x_olhar = round(max(-0.14, min(0.14, (cx_norm - 0.80) * 0.22)), 4)
    y_olhar = round(max(-0.10, min(0.10, (0.55 - cy_norm) * 0.18)), 4)

    exclusoes = list(PADROES_PRIVACIDADE_EXCLUIDOS) + [e.lower() for e in (apps_excluidos or [])]
    texto_verificacao = f"{titulo_bruto} {nome_proc}".lower()
    protegida = any(padrao in texto_verificacao for padrao in exclusoes)

    return {
        "hwnd": hwnd,
        "pid": pid_val,
        "titulo": "[Janela Protegida por Privacidade]" if protegida else titulo_bruto,
        "processo": nome_proc,
        "protegida_privacidade": protegida,
        "dimensoes": dimensoes,
        "x_olhar": x_olhar,
        "y_olhar": y_olhar,
    }


class MonitorPresencaDesktop:
    """Monitora suavemente cursor e janelas ativas para dar consciência espacial ao holograma da Gideon."""

    def __init__(self, callback_evento: Callable[[dict[str, Any]], Any] | None = None):
        self.callback_evento = callback_evento
        self.ativo = False
        self.em_conversa_direta = False
        self.ancora_avatar_x = 0.80
        self.ancora_avatar_y = 0.55
        self.apps_excluidos: list[str] = []

        self._parar_evento = threading.Event()
        self._thread: threading.Thread | None = None
        self._ultimo_hwnd: int = 0
        self._ultimo_x_olhar: float = 0.0
        self._ultimo_y_olhar: float = 0.0
        self._ultimo_envio_cursor: float = 0.0

    def iniciar(self) -> None:
        if self.ativo:
            return
        self.ativo = True
        self._parar_evento.clear()
        self._thread = threading.Thread(target=self._loop_monitoramento, daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self.ativo = False
        self._parar_evento.set()
        if self._thread:
            self._thread.join(timeout=0.8)

    def definir_foco_conversa(self, em_conversa: bool) -> None:
        """Quando o Henry fala com a Gideon, ela volta o olhar imediatamente para ele (câmera 0,0)."""
        mudou = self.em_conversa_direta != em_conversa
        self.em_conversa_direta = em_conversa
        if em_conversa and mudou:
            self._emitir({
                "tipo": "olhar",
                "alvo": "usuario",
                "x": 0.0,
                "y": 0.0,
            })

    def _emitir(self, evento: dict[str, Any]) -> None:
        if self.callback_evento:
            try:
                self.callback_evento(evento)
            except Exception:
                pass

    def _loop_monitoramento(self) -> None:
        contador_ciclos = 0
        while not self._parar_evento.is_set():
            try:
                agora = time.time()
                contador_ciclos += 1

                # 1. A cada ~450ms verifica se houve mudança na janela ativa do Windows
                if contador_ciclos % 3 == 0:
                    jan = inspecionar_janela_ativa_segura(self.apps_excluidos)
                    hwnd_atual = jan.get("hwnd", 0)
                    proc_lower = (jan.get("processo") or "").lower()
                    if hwnd_atual and hwnd_atual != self._ultimo_hwnd and "godot" not in proc_lower:
                        self._ultimo_hwnd = hwnd_atual
                        if not self.em_conversa_direta:
                            self._emitir({
                                "tipo": "atencao_desktop",
                                "evento": "janela_ativa",
                                "titulo": jan["titulo"],
                                "processo": jan["processo"],
                                "x": jan["x_olhar"],
                                "y": jan["y_olhar"],
                            })

                # 2. Se não estiver em conversa direta, acompanha discretamente o cursor do mouse
                if not self.em_conversa_direta:
                    cur = obter_posicao_cursor_normalizada(self.ancora_avatar_x, self.ancora_avatar_y)
                    dx = abs(cur["x_olhar"] - self._ultimo_x_olhar)
                    dy = abs(cur["y_olhar"] - self._ultimo_y_olhar)
                    if (dx >= 0.012 or dy >= 0.010) and (agora - self._ultimo_envio_cursor) >= 0.14:
                        self._ultimo_x_olhar = cur["x_olhar"]
                        self._ultimo_y_olhar = cur["y_olhar"]
                        self._ultimo_envio_cursor = agora
                        self._emitir({
                            "tipo": "olhar",
                            "alvo": "cursor",
                            "x": cur["x_olhar"],
                            "y": cur["y_olhar"],
                        })

                time.sleep(0.15)
            except Exception:
                time.sleep(0.4)
