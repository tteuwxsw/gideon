"""Controle fino de janelas, layout de tela e multimídia do Windows 10 para a Gideon."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import time
from typing import Any

from gideon.gate import Ferramenta, Risco

user32 = ctypes.windll.user32


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

SW_RESTORE = 9
SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SWP_NOZORDER = 0x0004
SWP_SHOWWINDOW = 0x0040

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3


def _obter_area_trabalho() -> tuple[int, int, int, int]:
    """Retorna (x, y, largura, altura) da área de trabalho útil (excluindo barra de tarefas)."""
    rect = RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
    largura = rect.right - rect.left
    altura = rect.bottom - rect.top
    return rect.left, rect.top, largura, altura


def _obter_janelas_ativas() -> list[dict[str, Any]]:
    """Lista janelas visíveis de aplicativos de usuário com seus identificadores (HWND) e títulos."""
    try:
        hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass

    janelas: list[dict[str, Any]] = []

    def enum_cb(hwnd: int, lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        tamanho = user32.GetWindowTextLengthW(hwnd)
        if tamanho <= 0:
            return True
        buf = ctypes.create_unicode_buffer(tamanho + 1)
        user32.GetWindowTextW(hwnd, buf, tamanho + 1)
        titulo = buf.value.strip()

        # Ignora janelas utilitárias ou do sistema
        ignorados = ["Program Manager", "Settings", "Configurações", "Calculadora", "Default IME", "MSCTFIME UI"]
        if not titulo or titulo in ignorados:
            return True

        # Verifica se não é janela de ferramenta/invisível
        estilo = user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
        if estilo & 0x00000080:  # WS_EX_TOOLWINDOW
            return True

        janelas.append({"hwnd": hwnd, "titulo": titulo})
        return True

    cb = WNDENUMPROC(enum_cb)
    user32.EnumWindows(cb, 0)
    return janelas


def organizar_janelas(disposicao: str = "lado_a_lado") -> dict[str, Any]:
    """Organiza as janelas abertas na tela (lado_a_lado, grade, cascata, minimizar_outras)."""
    orig_x, orig_y, largura_total, altura_total = _obter_area_trabalho()
    janelas = _obter_janelas_ativas()

    if not janelas:
        return {
            "sucesso": False,
            "mensagem_humana": "Senhor Henry, não encontrei janelas abertas para organizar.",
        }

    disp = disposicao.lower().strip()

    if disp in ["lado_a_lado", "dividir_tela", "split"]:
        # Divide entre as 2 janelas principais
        alvos = janelas[:2]
        if len(alvos) == 1:
            # Apenas 1 janela: centraliza em 80% da tela
            w = int(largura_total * 0.8)
            h = int(altura_total * 0.9)
            x = orig_x + (largura_total - w) // 2
            y = orig_y + (altura_total - h) // 2
            hwnd = alvos[0]["hwnd"]
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetWindowPos(hwnd, 0, x, y, w, h, SWP_NOZORDER | SWP_SHOWWINDOW)
            return {
                "sucesso": True,
                "layout": "centralizada",
                "janelas": [alvos[0]["titulo"]],
                "mensagem_humana": f"Centralizei a janela '{alvos[0]['titulo']}' na tela, Senhor Henry.",
            }

        meia_largura = largura_total // 2
        # Janela 1: Esquerda
        user32.ShowWindow(alvos[0]["hwnd"], SW_RESTORE)
        user32.SetWindowPos(alvos[0]["hwnd"], 0, orig_x, orig_y, meia_largura, altura_total, SWP_NOZORDER | SWP_SHOWWINDOW)
        # Janela 2: Direita
        user32.ShowWindow(alvos[1]["hwnd"], SW_RESTORE)
        user32.SetWindowPos(alvos[1]["hwnd"], 0, orig_x + meia_largura, orig_y, meia_largura, altura_total, SWP_NOZORDER | SWP_SHOWWINDOW)

        titulos = [alvos[0]["titulo"], alvos[1]["titulo"]]
        return {
            "sucesso": True,
            "layout": "lado_a_lado",
            "janelas": titulos,
            "mensagem_humana": f"Organizei lado a lado as janelas '{titulos[0]}' e '{titulos[1]}', Senhor Henry.",
        }

    elif disp in ["grade", "quatro_cantos", "grid"]:
        alvos = janelas[:4]
        meia_l = largura_total // 2
        meia_a = altura_total // 2

        posicoes = [
            (orig_x, orig_y, meia_l, meia_a),  # Superior Esquerdo
            (orig_x + meia_l, orig_y, meia_l, meia_a),  # Superior Direito
            (orig_x, orig_y + meia_a, meia_l, meia_a),  # Inferior Esquerdo
            (orig_x + meia_l, orig_y + meia_a, meia_l, meia_a),  # Inferior Direito
        ]

        nomes = []
        for i, item in enumerate(alvos):
            hwnd = item["hwnd"]
            px, py, pw, ph = posicoes[i]
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetWindowPos(hwnd, 0, px, py, pw, ph, SWP_NOZORDER | SWP_SHOWWINDOW)
            nomes.append(item["titulo"])

        return {
            "sucesso": True,
            "layout": "grade",
            "janelas": nomes,
            "mensagem_humana": f"Organizei {len(nomes)} janelas em grade de 4 cantos, Senhor Henry.",
        }

    elif disp in ["cascata", "cascade"]:
        alvos = janelas[:6]
        offset = 40
        w = int(largura_total * 0.7)
        h = int(altura_total * 0.7)
        nomes = []
        for i, item in enumerate(alvos):
            hwnd = item["hwnd"]
            px = orig_x + 30 + (i * offset)
            py = orig_y + 30 + (i * offset)
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetWindowPos(hwnd, 0, px, py, w, h, SWP_NOZORDER | SWP_SHOWWINDOW)
            nomes.append(item["titulo"])

        return {
            "sucesso": True,
            "layout": "cascata",
            "janelas": nomes,
            "mensagem_humana": f"Organizei as janelas em cascata, Senhor Henry.",
        }

    elif disp in ["minimizar_outras", "focar_unica"]:
        ativo_hwnd = user32.GetForegroundWindow()
        minimizadas = 0
        titulo_foco = ""
        for item in janelas:
            if item["hwnd"] == ativo_hwnd:
                titulo_foco = item["titulo"]
            else:
                user32.ShowWindow(item["hwnd"], SW_MINIMIZE)
                minimizadas += 1

        return {
            "sucesso": True,
            "layout": "minimizar_outras",
            "janela_em_foco": titulo_foco,
            "minimizadas": minimizadas,
            "mensagem_humana": f"Mantive apenas '{titulo_foco}' na tela e recolhi as demais janelas, Senhor Henry.",
        }

    return {
        "sucesso": False,
        "erro": f"Disposição '{disposicao}' não reconhecida.",
        "mensagem_humana": "As disposições válidas são 'lado_a_lado', 'grade', 'cascata' ou 'minimizar_outras', Senhor.",
    }


def controlar_som_sistema(acao: str = "mutar", toques: int = 2) -> dict[str, Any]:
    """Controla o som e multimídia do Windows (mutar, desmutar, aumentar, diminuir, play_pause, proxima)."""
    acao_norm = acao.lower().strip()
    toques = max(1, min(15, toques))

    def apertar_tecla(vk: int, vezes: int = 1):
        for _ in range(vezes):
            user32.keybd_event(vk, 0, 0, 0)
            user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP = 2
            time.sleep(0.04)

    if acao_norm in ["mutar", "desmutar", "mudo"]:
        apertar_tecla(VK_VOLUME_MUTE)
        msg = "Alternado o estado de mudo do sistema."
    elif acao_norm in ["aumentar", "subir"]:
        apertar_tecla(VK_VOLUME_UP, toques)
        msg = f"Aumentei o volume do sistema ({toques} níveis)."
    elif acao_norm in ["diminuir", "abaixar", "baixar"]:
        apertar_tecla(VK_VOLUME_DOWN, toques)
        msg = f"Diminui o volume do sistema ({toques} níveis)."
    elif acao_norm in ["play", "pause", "play_pause", "pausar"]:
        apertar_tecla(VK_MEDIA_PLAY_PAUSE)
        msg = "Comando de reproduzir/pausar enviado ao reprodutor de mídia."
    elif acao_norm in ["proxima", "next"]:
        apertar_tecla(VK_MEDIA_NEXT_TRACK)
        msg = "Avançado para a próxima faixa."
    elif acao_norm in ["anterior", "prev"]:
        apertar_tecla(VK_MEDIA_PREV_TRACK)
        msg = "Retornado para a faixa anterior."
    else:
        return {"sucesso": False, "erro": f"Ação de mídia '{acao}' desconhecida."}

    return {"sucesso": True, "acao": acao_norm, "mensagem_humana": msg}


FERRAMENTAS_JANELAS: list[Ferramenta] = [
    Ferramenta(
        nome="organizar_janelas",
        descricao="Organiza e divide as janelas abertas na tela (lado_a_lado, grade, cascata, minimizar_outras).",
        risco=Risco.AMARELO,
        executar=organizar_janelas,
        frase=lambda disposicao="lado_a_lado", **kwargs: f"organizar as janelas na tela em formato '{disposicao}'",
        parametros={
            "type": "object",
            "properties": {
                "disposicao": {
                    "type": "string",
                    "description": "Formato de organização: 'lado_a_lado', 'grade', 'cascata' ou 'minimizar_outras'.",
                    "enum": ["lado_a_lado", "grade", "cascata", "minimizar_outras"],
                },
            },
        },
    ),
    Ferramenta(
        nome="controlar_som_sistema",
        descricao="Controla o volume e reprodução de mídia do Windows (mutar, aumentar, diminuir, play_pause, proxima).",
        risco=Risco.AMARELO,
        executar=controlar_som_sistema,
        frase=lambda acao="mutar", **kwargs: f"controlar som/mídia do sistema: {acao}",
        parametros={
            "type": "object",
            "properties": {
                "acao": {
                    "type": "string",
                    "description": "Comando de som/mídia: 'mutar', 'aumentar', 'diminuir', 'play_pause', 'proxima', 'anterior'.",
                    "enum": ["mutar", "aumentar", "diminuir", "play_pause", "proxima", "anterior"],
                },
                "toques": {
                    "type": "integer",
                    "description": "Número de passos para aumento ou diminuição de volume (padrão 2).",
                },
            },
            "required": ["acao"],
        },
    ),
]
