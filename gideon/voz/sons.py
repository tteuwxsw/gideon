"""Identidade Sonora e Earcons Procedurais da Gideon (Estilo Apple / S.T.A.R. Labs).

Gera tons harmônicos matemáticos puros e reproduz em segundo plano sem bloquear a IA.
Não requer arquivos de áudio externos em disco.
"""

from __future__ import annotations

import io
import threading
import wave
from typing import Literal

import numpy as np

TAXA_AMOSTRAGEM = 24000

# Cache de buffers pré-sintetizados para latência ultrabaixa (0ms de overhead)
_CACHE_SONS: dict[str, np.ndarray] = {}
_CACHE_WAV_BYTES: dict[str, bytes] = {}
_lock = threading.RLock()


def _gerar_envelope_hann(num_amostras: int) -> np.ndarray:
    return (np.sin(np.pi * np.linspace(0, 1, num_amostras)) ** 2).astype(np.float32)


def _sintetizar_som(tipo: str) -> np.ndarray:
    """Gera o áudio float32 normalizado para o earcon solicitado."""
    if tipo == "ativacao":
        # Despertar: Glissando harmônico D5 (587 Hz) -> A5 (880 Hz) (130ms)
        duracao = 0.13
        t = np.linspace(0, duracao, int(TAXA_AMOSTRAGEM * duracao), endpoint=False)
        freq = np.linspace(587.33, 880.0, len(t))
        env = _gerar_envelope_hann(len(t))
        onda = 0.22 * np.sin(2 * np.pi * freq * t) + 0.08 * np.sin(4 * np.pi * freq * t)
        return (onda * env).astype(np.float32)

    elif tipo == "conclusao":
        # Confirmação / Sucesso: Cristal C6 (1046.5 Hz) com sobretom C7 (80ms)
        duracao = 0.08
        t = np.linspace(0, duracao, int(TAXA_AMOSTRAGEM * duracao), endpoint=False)
        env = np.exp(-t * 35.0).astype(np.float32)  # Decaimento percussivo suave
        onda = 0.18 * np.sin(2 * np.pi * 1046.5 * t) + 0.06 * np.sin(2 * np.pi * 2093.0 * t)
        return (onda * env).astype(np.float32)

    elif tipo == "erro":
        # Alerta sutil / Falha: Intervalo menor descendente A4 (440 Hz) -> E4 (329.6 Hz) (150ms)
        duracao = 0.15
        t = np.linspace(0, duracao, int(TAXA_AMOSTRAGEM * duracao), endpoint=False)
        freq = np.linspace(440.0, 329.63, len(t))
        env = _gerar_envelope_hann(len(t))
        onda = 0.20 * np.sin(2 * np.pi * freq * t)
        return (onda * env).astype(np.float32)

    elif tipo == "pensando":
        # Pulso sutil de processamento: C5 (523.25 Hz) ultraleve (70ms)
        duracao = 0.07
        t = np.linspace(0, duracao, int(TAXA_AMOSTRAGEM * duracao), endpoint=False)
        env = _gerar_envelope_hann(len(t))
        onda = 0.08 * np.sin(2 * np.pi * 523.25 * t)
        return (onda * env).astype(np.float32)

    # Padrão: clique neutro
    duracao = 0.04
    t = np.linspace(0, duracao, int(TAXA_AMOSTRAGEM * duracao), endpoint=False)
    env = _gerar_envelope_hann(len(t))
    return (0.10 * np.sin(2 * np.pi * 800.0 * t) * env).astype(np.float32)


def _obter_array(tipo: str) -> np.ndarray:
    with _lock:
        if tipo not in _CACHE_SONS:
            _CACHE_SONS[tipo] = _sintetizar_som(tipo)
        return _CACHE_SONS[tipo]


def obter_wav_bytes(tipo: str) -> bytes:
    """Retorna o earcon em formato WAV (PCM 16-bit) para transmissão HTTP/WebSocket."""
    with _lock:
        if tipo in _CACHE_WAV_BYTES:
            return _CACHE_WAV_BYTES[tipo]

        audio = _obter_array(tipo)
        pcm = (audio * 32767.0).clip(-32768, 32767).astype(np.int16)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(TAXA_AMOSTRAGEM)
            wf.writeframes(pcm.tobytes())

        dados = buf.getvalue()
        _CACHE_WAV_BYTES[tipo] = dados
        return dados


def tocar_som(tipo: Literal["ativacao", "conclusao", "erro", "pensando"] | str) -> None:
    """Toca o earcon em segundo plano sem bloquear a execução principal."""
    def _reproduzir():
        try:
            import sounddevice as sd
            audio = _obter_array(tipo)
            sd.play(audio, samplerate=TAXA_AMOSTRAGEM, blocking=False)
        except Exception:
            # Não interrompe se a máquina não tiver dispositivo de áudio ativo
            pass

    threading.Thread(target=_reproduzir, daemon=True, name=f"earcon_{tipo}").start()


def tocar_som_ativacao() -> None:
    """Earcon ao detectar wake-word ('Gideon')."""
    tocar_som("ativacao")


def tocar_som_conclusao() -> None:
    """Earcon ao finalizar comando com sucesso."""
    tocar_som("conclusao")


def tocar_som_erro() -> None:
    """Earcon em caso de falha de comando ou bloqueio."""
    tocar_som("erro")


def tocar_som_pensando() -> None:
    """Earcon discreto ao iniciar processamento longo."""
    tocar_som("pensando")
