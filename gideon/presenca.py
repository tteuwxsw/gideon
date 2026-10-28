"""Inspeção sob demanda da janela ativa com proteção de privacidade."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from typing import Any

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


def inspecionar_janela_ativa_segura(apps_excluidos: list[str] | None = None) -> dict[str, Any]:
    """Obtém metadados da janela ativa somente quando chamada, aplicando filtros de privacidade."""
    if os.name != "nt":
        return {
            "hwnd": 0,
            "titulo": "Ambiente de Teste",
            "processo": "python",
            "protegida_privacidade": False,
        }

    user32 = ctypes.windll.user32
    hwnd = int(user32.GetForegroundWindow())
    exclusoes = list(PADROES_PRIVACIDADE_EXCLUIDOS) + [e.lower() for e in (apps_excluidos or []) if e]

    if hwnd == 0:
        protegida_zero = any(padrao in "área de trabalho explorer.exe" for padrao in exclusoes)
        return {
            "hwnd": 0,
            "titulo": "[Janela Protegida por Privacidade]" if protegida_zero else "Área de Trabalho",
            "processo": "[Processo Protegido]" if protegida_zero else "explorer.exe",
            "protegida_privacidade": protegida_zero,
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

    rect = wintypes.RECT()
    largura, altura = _obter_resolucao_tela()
    dimensoes = {"esquerda": 0, "topo": 0, "largura": largura, "altura": altura}
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        w_jan = max(1, rect.right - rect.left)
        h_jan = max(1, rect.bottom - rect.top)
        dimensoes = {
            "esquerda": int(rect.left),
            "topo": int(rect.top),
            "largura": int(w_jan),
            "altura": int(h_jan),
        }

    texto_verificacao = f"{titulo_bruto} {nome_proc}".lower()
    protegida = any(padrao in texto_verificacao for padrao in exclusoes)

    return {
        "hwnd": hwnd,
        "pid": pid_val,
        "titulo": "[Janela Protegida por Privacidade]" if protegida else titulo_bruto,
        "processo": "[Processo Protegido]" if protegida else nome_proc,
        "protegida_privacidade": protegida,
        "dimensoes": dimensoes,
    }
