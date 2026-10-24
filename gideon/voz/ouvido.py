"""Módulo de captura de áudio, detecção de palavra de ativação e transcrição da Gideon."""

import io
import re
import time
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from typing import Callable, Any

TAXA_AMOSTRAGEM = 16000  # 16 kHz mono padrão para o Whisper
CANAIS = 1
VARIACOES_GIDEON = [
    r"\bgideon\b",
    r"\bguideon\b",
    r"\bgidion\b",
    r"\bgidiom\b",
    r"\bgideão\b",
    r"\bgideao\b",
]


class OuvinteVoz:
    """Gerencia a escuta de microfone, detecção de silêncio e transcrição local."""

    def __init__(
        self,
        modelo_whisper: str = "base",
        callback_evento: Callable[[dict], Any] | None = None,
    ):
        self.callback_evento = callback_evento
        self.modelo = WhisperModel(modelo_whisper, device="cpu", compute_type="int8")
        self._limiar_energia = 0.02  # Sensibilidade de detecção de fala
        print(f"  [Ouvido] Faster-Whisper ({modelo_whisper}) pronto para transcrição.")

    def _notificar(self, evento: dict) -> None:
        if self.callback_evento:
            try:
                self.callback_evento(evento)
            except Exception:
                pass

    def extrair_wake_word(self, texto: str) -> tuple[bool, str]:
        """Verifica se o texto contém a palavra de ativação Gideon e extrai o comando."""
        texto_limpo = texto.strip()
        padrao = r"^(?:.*?\b)?(?:gideon|guideon|gidion|gideão|gideao)\b[, !?:]*\s*(.*)$"
        match = re.search(padrao, texto_limpo, re.IGNORECASE)
        if match:
            comando = match.group(1).strip()
            return True, comando
        return False, texto_limpo

    def gravar_fala(
        self,
        limite_silencio: float = 1.2,
        timeout: float = 8.0,
        parar_evento: Any = None,
    ) -> np.ndarray | None:
        """Grava áudio do microfone até detectar silêncio contínuo."""
        buffer_audio = []
        falando = False
        tempo_silencio = 0.0
        inicio = time.time()
        chunk_tamanho = int(TAXA_AMOSTRAGEM * 0.1)  # Chunks de 100ms

        with sd.InputStream(samplerate=TAXA_AMOSTRAGEM, channels=CANAIS, dtype="float32") as stream:
            while True:
                if parar_evento and parar_evento.is_set():
                    break
                dados, _ = stream.read(chunk_tamanho)
                energia = float(np.sqrt(np.mean(dados**2)))

                if energia > self._limiar_energia:
                    if not falando:
                        falando = True
                        self._notificar({"tipo": "ouvindo", "ativo": True})
                    tempo_silencio = 0.0
                    buffer_audio.append(dados)
                elif falando:
                    tempo_silencio += 0.1
                    buffer_audio.append(dados)
                    if tempo_silencio >= limite_silencio:
                        break
                elif time.time() - inicio > timeout:
                    # Timeout sem detecção de fala
                    break

        if not buffer_audio:
            self._notificar({"tipo": "ouvindo", "ativo": False})
            return None

        self._notificar({"tipo": "ouvindo", "ativo": False})
        return np.concatenate(buffer_audio, axis=0).flatten()

    def transcrever_audio(self, audio: np.ndarray) -> str:
        """Converte o vetor de áudio em texto em português do Brasil."""
        if audio is None or len(audio) == 0:
            return ""

        segmentos, _ = self.modelo.transcribe(
            audio,
            language="pt",
            beam_size=2,
            vad_filter=True,
        )
        texto = " ".join([seg.text.strip() for seg in segmentos]).strip()
        return texto

    def ouvir_e_transcrever(self, timeout: float = 8.0) -> str:
        """Aguarda a fala do Henry e retorna o texto transcrito."""
        audio = self.gravar_fala(timeout=timeout)
        if audio is None:
            return ""
        return self.transcrever_audio(audio)
