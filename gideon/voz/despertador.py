"""Escuta offline e restrita usada somente quando o nucleo da Gideon esta parado."""

from __future__ import annotations

import json
import queue
import threading
import time
import unicodedata
import re
from pathlib import Path
from typing import Callable

import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel

from gideon.caminhos import MODELOS_DIR

MODELO_NOME = "vosk-model-small-pt-0.3"
MODELO_URL = f"https://alphacephei.com/vosk/models/{MODELO_NOME}.zip"
MODELO_ZIP_SHA256 = "6e1ce909032e1afa7a88e68a3d628ecafff302bdf195befab308826c395e93b7"
MODELO_PADRAO = MODELOS_DIR / MODELO_NOME
TAXA_AMOSTRAGEM = 16000

SAUDACOES_CANONICAS = {
    "bom dia gideon": "bom dia",
    "boa tarde gideon": "boa tarde",
    "boa noite gideon": "boa noite",
}

# O modelo Vosk portugues nao possui "Gideon" no lexico. Estes resultados
# foneticos foram medidos com a voz pt-BR do Windows e so valem apos a saudacao.
_ALIASES_VOSK = {
    "bom dia de o": "bom dia",
    "bom dia gente viu": "bom dia",
    "bom dia video": "bom dia",
    "bom dia genio": "bom dia",
    "boa tarde de o": "boa tarde",
    "boa tarde gente viu": "boa tarde",
    "boa tarde video": "boa tarde",
    "boa tarde genio": "boa tarde",
    "boa noite de o": "boa noite",
    "boa noite gente viu": "boa noite",
    "boa noite video": "boa noite",
    "boa noite genio": "boa noite",
}


def normalizar(texto: str) -> str:
    sem_acentos = unicodedata.normalize("NFKD", texto.lower())
    ascii_texto = "".join(c for c in sem_acentos if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", ascii_texto).split())


def identificar_saudacao(texto: str, *, aceitar_alias_vosk: bool = False) -> str | None:
    """Aceita somente uma das tres saudacoes completas, sem comando adicional."""
    texto_norm = normalizar(texto)
    saudacao = SAUDACOES_CANONICAS.get(texto_norm)
    if saudacao:
        return saudacao
    if aceitar_alias_vosk:
        return _ALIASES_VOSK.get(texto_norm)
    return None


def interpretar_resultado_vosk(payload: str, confianca_minima: float = 0.55) -> str | None:
    try:
        resultado = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        return None
    palavras = resultado.get("result") or []
    texto = str(resultado.get("text") or "")
    if not palavras or not texto:
        return None
    confiancas = [float(item.get("conf", 0.0)) for item in palavras]
    if min(confiancas, default=0.0) < confianca_minima:
        return None
    return identificar_saudacao(texto, aceitar_alias_vosk=True)


def gramatica_vosk() -> list[str]:
    frases = sorted(set(SAUDACOES_CANONICAS) | set(_ALIASES_VOSK))
    return [*frases, "[unk]"]


class DespertadorOffline:
    """Mantem uma escuta de baixo custo e devolve apos uma saudacao valida."""

    def __init__(
        self,
        callback: Callable[[str], None],
        modelo_path: Path = MODELO_PADRAO,
        debounce_s: float = 12.0,
    ):
        self.callback = callback
        self.modelo_path = Path(modelo_path)
        self.debounce_s = debounce_s
        self._ultimo_disparo = 0.0

    def executar(self, parar_evento: threading.Event) -> bool:
        if not self.modelo_path.is_dir():
            raise FileNotFoundError(f"Modelo de despertar ausente: {self.modelo_path}")

        SetLogLevel(-1)
        modelo = Model(str(self.modelo_path))
        reconhecedor = KaldiRecognizer(
            modelo,
            TAXA_AMOSTRAGEM,
            json.dumps(gramatica_vosk(), ensure_ascii=False),
        )
        reconhecedor.SetWords(True)
        audio: queue.Queue[bytes] = queue.Queue(maxsize=12)

        def receber(indata, _frames, _tempo, _status) -> None:
            try:
                audio.put_nowait(bytes(indata))
            except queue.Full:
                pass

        with sd.RawInputStream(
            samplerate=TAXA_AMOSTRAGEM,
            blocksize=4000,
            dtype="int16",
            channels=1,
            callback=receber,
        ):
            while not parar_evento.is_set():
                try:
                    bloco = audio.get(timeout=0.25)
                except queue.Empty:
                    continue
                if not reconhecedor.AcceptWaveform(bloco):
                    continue
                saudacao = interpretar_resultado_vosk(reconhecedor.Result())
                agora = time.monotonic()
                if saudacao and agora - self._ultimo_disparo >= self.debounce_s:
                    self._ultimo_disparo = agora
                    self.callback(saudacao)
                    return True
                reconhecedor.Reset()
        return False
