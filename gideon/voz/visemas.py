"""Motor de visemas fonéticos em português brasileiro e coarticulação labial sincronizada ao áudio.

Converte texto em português e janelas de áudio PCM em poses labiais (15 visemas Oculus + blendshapes ARKit)
para que a boca da Gideon acompanhe com precisão os fonemas reais e a onda sonora reproduzida.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Any

import numpy as np


# Mapeamento dos 15 visemas presentes no modelo 3D `gideon.glb`
VISEMAS_MODELO = (
    "viseme_sil",
    "viseme_PP",
    "viseme_FF",
    "viseme_TH",
    "viseme_DD",
    "viseme_kk",
    "viseme_CH",
    "viseme_SS",
    "viseme_nn",
    "viseme_RR",
    "viseme_aa",
    "viseme_E",
    "viseme_I",
    "viseme_O",
    "viseme_U",
)

# Fator de abertura mandibular natural para cada visema (evita deformação exagerada)
ABERTURA_MANDIBULA_POR_VISEMA: dict[str, float] = {
    "viseme_sil": 0.00,
    "viseme_PP": 0.00,  # Bilabiais fecham os lábios (p, b, m)
    "viseme_FF": 0.04,  # Labiodentais (f, v)
    "viseme_TH": 0.07,
    "viseme_DD": 0.09,  # Alveolares (t, d)
    "viseme_nn": 0.08,  # Nasais/laterais (n, l, nh, lh)
    "viseme_SS": 0.05,  # Sibilantes (s, z, c, ç, x)
    "viseme_CH": 0.08,  # Palatais (ch, j, g+e/i)
    "viseme_kk": 0.12,  # Velares (k, c+a/o/u, g+a/o/u)
    "viseme_RR": 0.10,  # Vibrantes (r, rr)
    "viseme_I": 0.13,   # Vogal fechada anterior (i, y)
    "viseme_U": 0.14,   # Vogal fechada arredondada (u, w)
    "viseme_E": 0.20,   # Vogal média anterior (e, é, ê)
    "viseme_O": 0.22,   # Vogal média arredondada (o, ó, ô)
    "viseme_aa": 0.28,  # Vogal aberta central (a, á, â, ã)
}


@dataclass
class QuadroVisema:
    """Representa o estado labial completo em um instante de tempo."""

    tempo_inicio: float
    tempo_fim: float
    visema_principal: str
    visema_secundario: str
    peso_principal: float
    peso_secundario: float
    abertura_mandibula: float
    arredondamento_labios: float  # mouthFunnel / mouthPucker para O / U / CH


def _normalizar_letras(texto: str) -> str:
    sem_acentos = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sem_acentos if not unicodedata.combining(c))


def converter_texto_em_sequencia_visemas(texto: str, duracao_audio_s: float) -> list[QuadroVisema]:
    """Gera uma linha do tempo fonética de visemas distribuída na duração real do áudio."""
    limpo = _normalizar_letras(texto)
    # Substitui dígrafos do português por símbolos únicos para mapeamento fonético fiel
    limpo = (
        limpo.replace("ch", "ʃ")
        .replace("lh", "ʎ")
        .replace("nh", "ɲ")
        .replace("rr", "ʁ")
        .replace("ss", "s")
        .replace("qu", "k")
        .replace("gu", "g")
    )

    tokens_foneticos: list[tuple[str, float]] = []
    for ch in limpo:
        if ch == "a":
            tokens_foneticos.append(("viseme_aa", 1.25))
        elif ch == "e":
            tokens_foneticos.append(("viseme_E", 1.15))
        elif ch in ("i", "y"):
            tokens_foneticos.append(("viseme_I", 1.05))
        elif ch == "o":
            tokens_foneticos.append(("viseme_O", 1.20))
        elif ch in ("u", "w"):
            tokens_foneticos.append(("viseme_U", 1.10))
        elif ch in ("p", "b", "m"):
            tokens_foneticos.append(("viseme_PP", 0.75))
        elif ch in ("f", "v"):
            tokens_foneticos.append(("viseme_FF", 0.80))
        elif ch in ("t", "d"):
            tokens_foneticos.append(("viseme_DD", 0.75))
        elif ch in ("s", "z", "c", "x"):
            tokens_foneticos.append(("viseme_SS", 0.85))
        elif ch in ("ʃ", "j"):
            tokens_foneticos.append(("viseme_CH", 0.85))
        elif ch in ("k", "g", "q"):
            tokens_foneticos.append(("viseme_kk", 0.75))
        elif ch in ("n", "l", "ʎ", "ɲ"):
            tokens_foneticos.append(("viseme_nn", 0.75))
        elif ch in ("r", "ʁ"):
            tokens_foneticos.append(("viseme_RR", 0.75))
        elif ch in (",", ";", ":"):
            tokens_foneticos.append(("viseme_sil", 1.40))
        elif ch in (".", "!", "?", "…"):
            tokens_foneticos.append(("viseme_sil", 1.80))
        elif ch == " ":
            if tokens_foneticos and tokens_foneticos[-1][0] != "viseme_sil":
                tokens_foneticos.append(("viseme_sil", 0.30))

    if not tokens_foneticos or duracao_audio_s <= 0.02:
        return [
            QuadroVisema(
                tempo_inicio=0.0,
                tempo_fim=max(0.05, duracao_audio_s),
                visema_principal="viseme_sil",
                visema_secundario="viseme_sil",
                peso_principal=0.0,
                peso_secundario=0.0,
                abertura_mandibula=0.0,
                arredondamento_labios=0.0,
            )
        ]

    # Compacta fonemas idênticos consecutivos
    compactados: list[tuple[str, float]] = []
    for vis, peso_dur in tokens_foneticos:
        if compactados and compactados[-1][0] == vis:
            compactados[-1] = (vis, min(2.2, compactados[-1][1] + peso_dur * 0.5))
        else:
            compactados.append((vis, peso_dur))

    soma_pesos = sum(p for _, p in compactados) or 1.0
    quadros: list[QuadroVisema] = []
    t_cursor = 0.0

    for idx, (vis, peso_dur) in enumerate(compactados):
        fatia_s = (peso_dur / soma_pesos) * duracao_audio_s
        t_fim = t_cursor + fatia_s
        prox_vis = compactados[idx + 1][0] if (idx + 1) < len(compactados) else "viseme_sil"

        abertura = ABERTURA_MANDIBULA_POR_VISEMA.get(vis, 0.10)
        arredondamento = 0.26 if vis in ("viseme_O", "viseme_U", "viseme_CH") else 0.0

        quadros.append(
            QuadroVisema(
                tempo_inicio=t_cursor,
                tempo_fim=t_fim,
                visema_principal=vis,
                visema_secundario=prox_vis,
                peso_principal=0.0 if vis == "viseme_sil" else 0.65,
                peso_secundario=0.0 if prox_vis == "viseme_sil" else 0.22,
                abertura_mandibula=abertura,
                arredondamento_labios=arredondamento,
            )
        )
        t_cursor = t_fim

    return quadros


def calcular_frame_lipsync_audio(
    fatia_pcm: np.ndarray,
    taxa_amostragem: int,
    tempo_decorrido_s: float,
    sequencia_visemas: list[QuadroVisema],
) -> dict[str, Any]:
    """Combina o envelope acústico real (RMS + ZCR) com a linha do tempo fonética para sincronia labial."""
    if len(fatia_pcm) == 0:
        return {
            "intensidade": 0.0,
            "visema": "viseme_sil",
            "visema_secundario": "viseme_sil",
            "peso_visema": 0.0,
            "peso_secundario": 0.0,
            "abertura_mandibula": 0.0,
            "arredondamento": 0.0,
            "enfase_sobrancelha": 0.0,
        }

    sinal = fatia_pcm.astype(np.float32).flatten()
    rms = float(np.sqrt(np.mean(np.square(sinal))))

    # Se o áudio real estiver em silêncio (pausa entre palavras/frases), fecha a boca imediatamente!
    if rms < 0.012:
        return {
            "intensidade": 0.0,
            "visema": "viseme_sil",
            "visema_secundario": "viseme_sil",
            "peso_visema": 0.0,
            "peso_secundario": 0.0,
            "abertura_mandibula": 0.0,
            "arredondamento": 0.0,
            "enfase_sobrancelha": 0.0,
        }

    intensidade = min(1.0, max(0.0, (rms - 0.012) * 3.2))

    # Taxa de cruzamento por zero (ZCR): alta em fricativas/sibilantes (S, F, CH), baixa em vogais abertas (A, O)
    mudancas_sinal = np.diff(np.signbit(sinal))
    zcr = float(np.sum(mudancas_sinal)) / max(1.0, float(len(sinal)))

    # Localiza o quadro fonético correspondente ao instante atual
    quadro_atual = sequencia_visemas[-1] if sequencia_visemas else None
    for q in sequencia_visemas:
        if q.tempo_inicio <= tempo_decorrido_s <= q.tempo_fim:
            quadro_atual = q
            break

    if quadro_atual is None or quadro_atual.visema_principal == "viseme_sil":
        # Fallback acústico baseado no ZCR e energia quando o texto indicava pausa mas ainda há som residual
        if zcr > 0.22:
            vis_p = "viseme_SS"
            abertura_base = 0.06
            arred = 0.0
        elif intensidade > 0.55:
            vis_p = "viseme_aa"
            abertura_base = 0.24
            arred = 0.05
        else:
            vis_p = "viseme_E"
            abertura_base = 0.16
            arred = 0.08
        vis_s = "viseme_O"
        peso_p = round(intensidade * 0.58, 3)
        peso_s = round(intensidade * 0.18, 3)
    else:
        vis_p = quadro_atual.visema_principal
        vis_s = quadro_atual.visema_secundario
        # Se a acústica detectar fricativa forte (ZCR alto), reforça sibilante
        if zcr > 0.26 and vis_p not in ("viseme_SS", "viseme_FF", "viseme_CH"):
            vis_s = "viseme_SS"
        fator_energia = 0.45 + 0.55 * intensidade
        peso_p = round(min(0.82, quadro_atual.peso_principal * fator_energia), 3)
        peso_s = round(min(0.35, quadro_atual.peso_secundario * fator_energia), 3)
        abertura_base = quadro_atual.abertura_mandibula
        arred = quadro_atual.arredondamento_labios * fator_energia

    # Em visemas bilabiais (P, B, M), os lábios se tocam mesmo com energia vocal
    if vis_p == "viseme_PP":
        abertura_final = 0.0
    else:
        abertura_final = round(min(0.30, abertura_base * (0.4 + 0.6 * intensidade)), 3)

    enfase_sobrancelha = round(max(0.0, (intensidade - 0.55) * 0.35), 3)

    return {
        "intensidade": round(intensidade, 3),
        "visema": vis_p,
        "visema_secundario": vis_s,
        "peso_visema": peso_p,
        "peso_secundario": peso_s,
        "abertura_mandibula": abertura_final,
        "arredondamento": round(arred, 3),
        "enfase_sobrancelha": enfase_sobrancelha,
    }
