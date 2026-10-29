"""Módulo de baixa latência para captura de áudio, VAD adaptativo, Wake Word e STT da Gideon."""

from __future__ import annotations

from collections import deque
from difflib import SequenceMatcher
import re
import time
import unicodedata
from typing import Callable, Any

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

TAXA_AMOSTRAGEM = 16000  # 16 kHz mono padrão para o Whisper
CANAIS = 1

# Variações fonéticas comuns geradas pelo Whisper em português ao falar rápido ou baixo
VARIACOES_GIDEON = [
    "gideon",
    "guideon",
    "gidion",
    "gidiom",
    "gideão",
    "gideao",
    "guidião",
    "guidiao",
    "gidião",
    "gidiao",
    "gidean",
    "guidian",
    "guidiom",
    "jideon",
    "djideon",
    "dideon",
    "gideom",
    "gidiam",
    "kidion",
    "guiden",
]

SAUDACOES_INICIAIS = {
    "oi", "ola", "ei", "hey", "e", "ai", "eaí", "eai",
    "fala", "escuta", "ouve", "opa", "bom", "dia", "boa", "tarde", "noite",
}

PERGUNTAS_PRESENCA = (
    "voce esta ai",
    "vc esta ai",
    "voce ta ai",
    "ta ai",
    "esta ai",
    "esta me ouvindo",
    "ta me ouvindo",
    "me ouve",
    "pode me ouvir",
    "acordada",
    "online",
)

# Alucinações clássicas do Whisper em trechos de silêncio ou ruído de fundo
ALUCINACOES_WHISPER = {
    "legendas pela comunidade amara org",
    "legendas pela comunidade",
    "obrigado por assistir",
    "obrigada por assistir",
    "inscreva se no canal",
    "deixe seu like",
    "ate o proximo video",
    "tchau",
    "you",
    "thank you",
    "thanks for watching",
    "subtitles by",
}

PROMPT_INICIAL_WHISPER = (
    "Gideon, Olá Gideon, Ei Gideon, Oi Gideon, Gideon você está aí? "
    "Henry, abre o Chrome, abre a internet, entra no navegador, Spotify, Chase Atlantic, "
    "YouTube, VS Code, Discord, Steam, memória RAM, processador CPU, placa de vídeo RX 580."
)


def _normalizar_simples(texto: str) -> str:
    sem_acentos = unicodedata.normalize("NFKD", texto.lower())
    limpo = "".join(c for c in sem_acentos if not unicodedata.combining(c))
    limpo = re.sub(r"[^a-z0-9 ]", " ", limpo)
    return " ".join(limpo.split())


def corrigir_erros_transcricao(texto: str) -> str:
    """Corrige erros fonéticos frequentes do STT em português brasileiro."""
    if not texto:
        return ""
    t = texto.strip()
    correcoes = [
        (r"\b(?:abro|abri)\s+(navegador|chrome|internet|spotify|youtube|google|calculadora)\b", r"abre o \1"),
        (r"^\s*(?:abro|abri)\s+(o|a|os|as)?\s*", lambda m: f"abre {m.group(1) + ' ' if m.group(1) else ''}"),
        (r"\b(?:espotifai|spotfy|sportfy|spootify)\b", "Spotify"),
        (r"\b(?:crome|crôme|gugol crome)\b", "Chrome"),
        (r"\b(?:mem[oó]ria\s+r[aã]|de\s+r[aã])\b", "memória RAM"),
        (r"\b(?:placa\s+de\s+v[ií]deo|placa\s+de\s+video)\b", "placa de vídeo"),
    ]
    for padrao, subst in correcoes:
        t = re.sub(padrao, subst, t, flags=re.IGNORECASE)
    return t.strip()


class OuvinteVoz:
    """Gerencia escuta de microfone com VAD rápido, pré-buffer, aquecimento prévio e Faster-Whisper."""

    def __init__(
        self,
        modelo_whisper: str = "base",
        callback_evento: Callable[[dict], Any] | None = None,
        limiar_energia: float = 0.016,
        limite_silencio: float = 0.72,
    ):
        self.callback_evento = callback_evento
        self.nome_modelo = modelo_whisper
        # Configura 6 threads físicas para baixa latência na CPU de 14 núcleos do Henry
        self.modelo = WhisperModel(
            modelo_whisper,
            device="cpu",
            compute_type="int8",
            cpu_threads=6,
        )
        self._limiar_energia = limiar_energia
        self._limite_silencio_padrao = limite_silencio
        self._ruido_ambiente = 0.004
        self._palavras_ativacao_extras: list[str] = []
        self._gravando = False

        self.ultima_latencia_vad_ms: float = 0.0
        self.ultima_latencia_stt_ms: float = 0.0

        try:
            from faster_whisper.vad import get_vad_model
            self._silero_vad = get_vad_model()
            print("  [Ouvido] Silero VAD neural ativado (detecção ultrarrápida de fala).")
        except Exception as erro:
            self._silero_vad = None
            print(f"  [Ouvido] Aviso: Silero VAD indisponível ({erro}); usando VAD por energia.")

        self._aquecer_modelo()
        print(f"  [Ouvido] Faster-Whisper ({modelo_whisper}, int8, 6 threads) aquecido e pronto.")

    def _aquecer_modelo(self) -> None:
        """Executa uma inferência curta na inicialização para eliminar latência de cold-start."""
        try:
            silencio = np.zeros(TAXA_AMOSTRAGEM // 2, dtype=np.float32)
            segs, _ = self.modelo.transcribe(
                silencio,
                language="pt",
                beam_size=1,
                vad_filter=False,
                without_timestamps=True,
            )
            list(segs)
        except Exception:
            pass

    @property
    def sensibilidade(self) -> float:
        return self._limiar_energia

    @property
    def gravando(self) -> bool:
        """Indica captura física ativa, inclusive enquanto aguarda o início da fala."""
        return self._gravando

    @sensibilidade.setter
    def sensibilidade(self, valor: float) -> None:
        self._limiar_energia = max(0.004, min(0.15, float(valor)))

    def configurar(
        self,
        limiar_energia: float | None = None,
        limite_silencio: float | None = None,
        palavras_ativacao: list[str] | None = None,
    ) -> None:
        """Permite ajustar sensibilidade do microfone, tolerância de pausa e wake words em tempo real."""
        if limiar_energia is not None:
            self.sensibilidade = limiar_energia
        if limite_silencio is not None:
            self._limite_silencio_padrao = max(0.4, min(3.5, float(limite_silencio)))
        if palavras_ativacao is not None:
            self._palavras_ativacao_extras = [p.strip().lower() for p in palavras_ativacao if p.strip()]

    def _notificar(self, evento: dict) -> None:
        if self.callback_evento:
            try:
                self.callback_evento(evento)
            except Exception:
                pass

    def _palavra_parece_gideon(self, palavra: str) -> bool:
        """Verifica correspondência exata ou fonética aproximada com 'Gideon'."""
        p = _normalizar_simples(palavra)
        if not p or len(p) < 4:
            return False
        alvos = VARIACOES_GIDEON + self._palavras_ativacao_extras
        for alvo in alvos:
            alvo_norm = _normalizar_simples(alvo)
            if p == alvo_norm:
                return True
            if len(p) >= 5 and SequenceMatcher(None, p, alvo_norm).ratio() >= 0.78:
                return True
        return False

    def extrair_wake_word(self, texto: str) -> tuple[bool, str]:
        """Verifica se o texto contém a palavra de ativação ('Gideon', 'Ei Gideon', etc.) e extrai o comando."""
        texto_limpo = texto.strip()
        if not texto_limpo:
            return False, ""

        alvos_regex = "|".join(re.escape(v) for v in (VARIACOES_GIDEON + self._palavras_ativacao_extras))
        padrao = rf"^(?:.*?\b)?(?:{alvos_regex})\b[, !?:.\-]*\s*(.*)$"
        match = re.search(padrao, texto_limpo, re.IGNORECASE)
        if match:
            comando = match.group(1).strip()
            return True, self._limpar_pergunta_presenca(comando)

        tokens_originais = texto_limpo.split()
        for idx, token in enumerate(tokens_originais[:5]):
            token_sem_pont = token.strip(",.!?:;-'\"")
            if self._palavra_parece_gideon(token_sem_pont):
                anteriores = [_normalizar_simples(t) for t in tokens_originais[:idx]]
                if all(not a or a in SAUDACOES_INICIAIS for a in anteriores):
                    restante = " ".join(tokens_originais[idx + 1 :]).lstrip(",.!?:;- ")
                    return True, self._limpar_pergunta_presenca(restante)

        return False, texto_limpo

    def _limpar_pergunta_presenca(self, comando: str) -> str:
        """Se o usuário disse apenas 'Gideon, você está aí?', trata como chamado de presença."""
        if not comando:
            return ""
        cmd_norm = _normalizar_simples(comando)
        if cmd_norm in PERGUNTAS_PRESENCA:
            return "__PRESENCA__"
        for p in PERGUNTAS_PRESENCA:
            if cmd_norm.startswith(p + " "):
                idx = comando.find("?")
                if idx != -1 and idx + 1 < len(comando):
                    return comando[idx + 1 :].strip(" ,.-")
        return comando

    def gravar_fala(
        self,
        limite_silencio: float | None = None,
        timeout: float = 4.5,
        parar_evento: Any = None,
        duracao_maxima: float = 24.0,
    ) -> np.ndarray | None:
        """Grava áudio do microfone com Silero VAD neural de 32ms, pré-buffer e corte imediato de silêncio."""
        if limite_silencio is not None:
            silencio_alvo = limite_silencio
        elif self._silero_vad is not None:
            silencio_alvo = 0.38  # 380ms para resposta ágil e natural com Silero VAD
        else:
            silencio_alvo = self._limite_silencio_padrao

        # Silero VAD opera nativamente em blocos de 512 amostras a 16kHz (32ms)
        chunk_tamanho = 512
        duracao_chunk = chunk_tamanho / TAXA_AMOSTRAGEM

        # Pré-buffer de ~384ms (12 blocos de 32ms) para nunca cortar o início das frases
        pre_buffer: deque[np.ndarray] = deque(maxlen=12)
        buffer_audio: list[np.ndarray] = []

        falando = False
        tempo_fala_ativa = 0.0
        tempo_silencio = 0.0
        inicio = time.time()

        try:
            self._gravando = True
            with sd.InputStream(samplerate=TAXA_AMOSTRAGEM, channels=CANAIS, dtype="float32") as stream:
                while True:
                    if parar_evento and parar_evento.is_set():
                        break

                    dados, _ = stream.read(chunk_tamanho)
                    bloco = (dados - np.mean(dados)).flatten()
                    energia = float(np.sqrt(np.mean(bloco ** 2)))

                    # 1. Avalia probabilidade neural de fala com Silero VAD
                    eh_fala = False
                    if self._silero_vad is not None:
                        try:
                            prob_fala = float(self._silero_vad(bloco)[0])
                            eh_fala = prob_fala >= 0.45
                        except Exception:
                            limiar_dinamico = max(self._limiar_energia, min(0.045, self._ruido_ambiente * 2.4))
                            eh_fala = energia > limiar_dinamico
                    else:
                        limiar_dinamico = max(self._limiar_energia, min(0.045, self._ruido_ambiente * 2.4))
                        eh_fala = energia > limiar_dinamico

                    if eh_fala:
                        if not falando:
                            falando = True
                            self._notificar({"tipo": "estado_ia", "estado": "listening"})
                            self._notificar({"tipo": "ouvindo", "ativo": True})
                            buffer_audio.extend(pre_buffer)
                            pre_buffer.clear()
                        tempo_silencio = 0.0
                        tempo_fala_ativa += duracao_chunk
                        buffer_audio.append(bloco)
                    elif falando:
                        tempo_silencio += duracao_chunk
                        buffer_audio.append(bloco)

                        # Frases curtas (< 2.0s) encerram ultra-rápido; frases longas toleram breve pausa
                        tolerancia = silencio_alvo * 1.3 if tempo_fala_ativa > 2.0 else silencio_alvo
                        if tempo_silencio >= tolerancia:
                            self.ultima_latencia_vad_ms = tempo_silencio * 1000.0
                            break
                    else:
                        self._ruido_ambiente = (0.94 * self._ruido_ambiente) + (0.06 * energia)
                        pre_buffer.append(bloco)
                        if time.time() - inicio > timeout:
                            break

                    if falando and (time.time() - inicio) > duracao_maxima:
                        break
        except Exception as e:
            print(f"  [Ouvido] Aviso na captura de áudio: {e}")
            self._notificar({"tipo": "ouvindo", "ativo": False})
            return None
        finally:
            self._gravando = False

        self._notificar({"tipo": "ouvindo", "ativo": False})

        if not buffer_audio or tempo_fala_ativa < 0.16:
            return None

        audio_final = np.concatenate(buffer_audio, axis=0).flatten()
        pico = float(np.max(np.abs(audio_final))) if len(audio_final) > 0 else 0.0
        if 0.01 < pico < 0.25:
            audio_final = np.clip(audio_final * (0.35 / pico), -1.0, 1.0)

        return audio_final

    def transcrever_audio(self, audio: np.ndarray) -> str:
        """Converte o vetor de áudio em texto em português do Brasil com baixa latência."""
        if audio is None or len(audio) == 0:
            return ""

        t0 = time.perf_counter()
        segmentos, _ = self.modelo.transcribe(
            audio,
            language="pt",
            beam_size=1,
            best_of=1,
            temperature=0.0,
            without_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 200},
            initial_prompt=PROMPT_INICIAL_WHISPER,
            condition_on_previous_text=False,
        )

        partes = []
        for seg in segmentos:
            if getattr(seg, "no_speech_prob", 0.0) > 0.78:
                continue
            texto_seg = seg.text.strip()
            if texto_seg:
                partes.append(texto_seg)

        self.ultima_latencia_stt_ms = (time.perf_counter() - t0) * 1000.0
        texto = " ".join(partes).strip()
        if not texto:
            return ""

        texto_norm = _normalizar_simples(texto)
        if texto_norm in ALUCINACOES_WHISPER or len(texto_norm) < 2:
            return ""

        return corrigir_erros_transcricao(texto)

    def ouvir_e_transcrever(self, timeout: float = 8.0) -> str:
        """Aguarda a fala do Henry e retorna o texto transcrito."""
        audio = self.gravar_fala(timeout=timeout)
        if audio is None:
            return ""
        return self.transcrever_audio(audio)
