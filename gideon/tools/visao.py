"""Módulo de Visão Computacional e Percepção Multimodal da Gideon.

Permite à Gideon 'enxergar' a tela do computador do Senhor Henry usando captura
direta de hardware (Win32 BitBlt GDI) e raciocínio visual via Gemini Vision.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime
import io
import os
from pathlib import Path
import time
from typing import Any

from PIL import Image

from gideon.caminhos import DADOS_DIR
from gideon.gate import Ferramenta, Risco

PASTA_CAPTURAS = DADOS_DIR / "capturas"
PASTA_CAPTURAS.mkdir(parents=True, exist_ok=True)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def capturar_tela_imagem() -> Image.Image:
    """Captura a tela inteira via Win32 BitBlt com velocidade ultrarrápida (0-2ms)."""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    # Acopla a thread ao desktop interativo ativo do Windows
    hdesk_ativo = None
    try:
        hdesk_ativo = user32.OpenInputDesktop(0, False, 0x01FF)
        if hdesk_ativo:
            user32.SetThreadDesktop(hdesk_ativo)
    except Exception:
        pass

    largura = user32.GetSystemMetrics(0)
    altura = user32.GetSystemMetrics(1)
    hwnd_desktop = user32.GetDesktopWindow()

    hdc_screen = user32.GetDC(hwnd_desktop)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbitmap = gdi32.CreateCompatibleBitmap(hdc_screen, largura, altura)
    h_antigo = gdi32.SelectObject(hdc_mem, hbitmap)

    try:
        # SRCCOPY = 0x00CC0020
        gdi32.BitBlt(hdc_mem, 0, 0, largura, altura, hdc_screen, 0, 0, 0x00CC0020)

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = largura
        bmi.biHeight = -altura  # Top-down DIB
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        tamanho_buffer = largura * altura * 4
        buffer = (ctypes.c_char * tamanho_buffer)()
        gdi32.GetDIBits(hdc_mem, hbitmap, 0, altura, buffer, ctypes.byref(bmi), 0)

        imagem = Image.frombuffer("RGBA", (largura, altura), buffer, "raw", "BGRA", 0, 1).convert("RGB")
        return imagem
    except Exception:
        # Fallback via Pillow ImageGrab se BitBlt falhar
        from PIL import ImageGrab
        return ImageGrab.grab()
    finally:
        gdi32.SelectObject(hdc_mem, h_antigo)
        gdi32.DeleteObject(hbitmap)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(hwnd_desktop, hdc_screen)


def capturar_tela(salvar_arquivo: bool = True) -> dict[str, Any]:
    """Captura a tela atual do computador do Henry e salva a imagem."""
    imagem = capturar_tela_imagem()
    agora = datetime.now()
    timestamp = agora.strftime("%Y%m%d_%H%M%S")
    caminho_arquivo = PASTA_CAPTURAS / f"tela_{timestamp}.jpg"

    if salvar_arquivo:
        imagem.save(str(caminho_arquivo), format="JPEG", quality=85)
        arquivo_str = str(caminho_arquivo)
    else:
        arquivo_str = ""

    return {
        "sucesso": True,
        "largura": imagem.width,
        "altura": imagem.height,
        "arquivo": arquivo_str,
        "timestamp": agora.strftime("%d/%m/%Y %H:%M:%S"),
        "mensagem_humana": f"Capturei a tela do seu computador com sucesso ({imagem.width}x{imagem.height}).",
    }


def analisar_tela(pergunta: str = "O que está visível na tela no momento?") -> dict[str, Any]:
    """Captura a tela do computador e analisa visualmente com o Gemini Vision em tempo real."""
    import keyring
    from google import genai
    from google.genai import types
    from gideon.configuracao import obter_idioma

    imagem = capturar_tela_imagem()
    buffer = io.BytesIO()
    # Redimensiona proporcionalmente para no máximo 1600px se necessário para otimizar tokens
    if imagem.width > 1600:
        fator = 1600 / imagem.width
        img_redim = imagem.resize((1600, int(imagem.height * fator)), Image.Resampling.LANCZOS)
    else:
        img_redim = imagem

    img_redim.save(buffer, format="JPEG", quality=80)
    bytes_imagem = buffer.getvalue()

    chave = keyring.get_password("gideon", "gemini_api_key") or keyring.get_password("alfred", "gemini_api_key")
    if not chave:
        return {
            "sucesso": False,
            "erro": "Chave da API Gemini não configurada.",
            "mensagem_humana": "Senhor Henry, não consegui analisar a tela pois a chave de API não foi encontrada no cofre.",
        }

    idioma = obter_idioma()
    prompt_visao = (
        f"Você é a Gideon, inteligência artificial do Henry. Analise a captura de tela do computador dele.\n"
        f"Pergunta do Senhor Henry: '{pergunta}'.\n"
        f"Responda diretamente e com elegância em Português do Brasil (pt-BR). "
        f"Destaque janelas ativas, mensagens de erro, abas abertas, conteúdos em foco ou qualquer detalhe relevante."
    )

    try:
        cliente = genai.Client(api_key=chave)
        parte_imagem = types.Part.from_bytes(data=bytes_imagem, mime_type="image/jpeg")

        modelos = ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-flash-latest"]
        resposta_texto = ""
        for mod in modelos:
            try:
                resp = cliente.models.generate_content(
                    model=mod,
                    contents=[prompt_visao, parte_imagem],
                )
                if resp.text:
                    resposta_texto = resp.text.strip()
                    break
            except Exception:
                continue

        if not resposta_texto:
            resposta_texto = "Consegui capturar a tela, mas não obtive análise textual no momento."

        return {
            "sucesso": True,
            "analise": resposta_texto,
            "resolucao": f"{imagem.width}x{imagem.height}",
            "mensagem_humana": resposta_texto,
        }
    except Exception as e:
        return {
            "sucesso": False,
            "erro": str(e),
            "mensagem_humana": f"Senhor Henry, ocorreu uma falha ao processar a visão de tela: {str(e)}",
        }


def localizar_elemento_na_tela(elemento: str) -> dict[str, Any]:
    """Localiza visualmente um elemento, botão ou ícone na tela e retorna suas coordenadas estimadas."""
    import keyring
    import json
    import re
    from google import genai
    from google.genai import types

    imagem = capturar_tela_imagem()
    buffer = io.BytesIO()
    imagem.save(buffer, format="JPEG", quality=85)
    bytes_imagem = buffer.getvalue()

    chave = keyring.get_password("gideon", "gemini_api_key") or keyring.get_password("alfred", "gemini_api_key")
    if not chave:
        return {"sucesso": False, "erro": "Chave não configurada."}

    prompt = (
        f"Identifique o elemento '{elemento}' na tela.\n"
        f"A resolução da imagem é {imagem.width}x{imagem.height}.\n"
        f"Responda ESTRITAMENTE em formato JSON com os campos:\n"
        f'{{"encontrado": true/false, "x": <coordenada_x_pixel>, "y": <coordenada_y_pixel>, "descricao": "breve descricao"}}'
    )

    try:
        cliente = genai.Client(api_key=chave)
        parte_img = types.Part.from_bytes(data=bytes_imagem, mime_type="image/jpeg")
        resp = cliente.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=[prompt, parte_img],
        )
        texto = resp.text or ""
        match = re.search(r"\{.*\}", texto, re.DOTALL)
        if match:
            dados = json.loads(match.group(0))
            return {
                "sucesso": dados.get("encontrado", False),
                "coordenadas": {"x": dados.get("x", 0), "y": dados.get("y", 0)},
                "descricao": dados.get("descricao", ""),
                "resolucao": f"{imagem.width}x{imagem.height}",
                "mensagem_humana": f"Elemento '{elemento}' localizado em X={dados.get('x')} e Y={dados.get('y')}." if dados.get("encontrado") else f"Não consegui localizar '{elemento}' na tela.",
            }
        return {"sucesso": False, "erro": "Resposta não interpretável."}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}


FERRAMENTAS_VISAO: list[Ferramenta] = [
    Ferramenta(
        nome="capturar_tela",
        descricao="Captura uma foto em alta definição da tela atual do computador do Henry.",
        risco=Risco.VERDE,
        executar=capturar_tela,
        frase=lambda **kwargs: "capturar a imagem da tela do computador",
        parametros={
            "type": "object",
            "properties": {
                "salvar_arquivo": {"type": "boolean", "description": "Se deve salvar a captura em disco."},
            },
        },
    ),
    Ferramenta(
        nome="analisar_tela",
        descricao="Enxerga e analisa visualmente o que está na tela do computador do Henry (leitura de código, telas de erro, abas, documentos, imagens).",
        risco=Risco.VERDE,
        executar=analisar_tela,
        frase=lambda pergunta="...", **kwargs: f"analisar visualmente a tela do computador ({pergunta})",
        parametros={
            "type": "object",
            "properties": {
                "pergunta": {"type": "string", "description": "O que você deseja verificar ou perguntar sobre o que está na tela."},
            },
        },
    ),
    Ferramenta(
        nome="localizar_elemento_na_tela",
        descricao="Localiza visualmente botões, ícones ou campos na tela e retorna suas coordenadas na tela.",
        risco=Risco.VERDE,
        executar=localizar_elemento_na_tela,
        frase=lambda elemento="", **kwargs: f"localizar '{elemento}' na tela",
        parametros={
            "type": "object",
            "properties": {
                "elemento": {"type": "string", "description": "Nome ou descrição do botão/ícone a localizar."},
            },
            "required": ["elemento"],
        },
    ),
]
