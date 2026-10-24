"""Módulo de síntese de voz (TTS) humanizada da Gideon com suporte a Barge-In (interrupção).

Hierarquia de motores neurais:
1. Neural HD (`edge-tts`: `pt-BR-ThalitaMultilingualNeural` / `pt-BR-FranciscaNeural`) — Voz feminina brasileira ultra-humanizada, com entonação e respiração naturais.
2. Kokoro ONNX (`pf_dora` / `af_bella`) — Motor neural local.
3. Fallback nativo offline do Windows (`Microsoft Maria Desktop`).

Inclui:
- Análise de envelope de amplitude de áudio (RMS) em tempo real para sincronia labial fiel no avatar 3D.
- Sistema de Barge-In anti-eco: permite interromper a fala da Gideon imediatamente quando o usuário fala.
"""

from __future__ import annotations

import asyncio
from collections import deque
import io
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Any

import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
MODELOS_DIR = ROOT_DIR / "dados" / "modelos"
KOKORO_MODEL_PATH = MODELOS_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES_PATH = MODELOS_DIR / "voices-v1.0.bin"

# Vozes neurais brasileiras ultra-realistas
VOZ_NEURAL_PRINCIPAL = "pt-BR-ThalitaMultilingualNeural"
VOZ_NEURAL_SECUNDARIA = "pt-BR-FranciscaNeural"


def limpar_texto_para_fala(texto: str) -> str:
    """Remove marcações Markdown e tags internas para leitura limpa e fluida."""
    texto = re.sub(r"\[EMOCAO:[^\]]+\]", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"```[\s\S]*?```", " código exibido na tela ", texto)
    texto = re.sub(r"`([^`]+)`", r"\1", texto)
    texto = re.sub(r"\*\*([^*]+)\*\*", r"\1", texto)
    texto = re.sub(r"\*([^*]+)\*", r"\1", texto)
    texto = re.sub(r"^#+\s*", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


class SintetizadorVoz:
    """Gerenciador de voz neural humanizada da Gideon com lip-sync reativo e Barge-In."""

    def __init__(
        self,
        callback_evento: Callable[[dict], Any] | None = None,
        barge_in_ativo: bool = True,
        limiar_barge_in: float = 0.055,
    ):
        self.callback_evento = callback_evento
        self.barge_in_ativo = barge_in_ativo
        self.limiar_barge_in = limiar_barge_in
        self.fator_rejeicao_eco = 1.95

        self._kokoro = None
        self._edge_disponivel = False
        self._motor_ativo = "neural_hd"

        self._falando = False
        self._evento_interromper = threading.Event()
        self._processo_windows: subprocess.Popen | None = None
        self.rms_saida_atual: float = 0.0
        self.foi_interrompida: bool = False
        self.audio_barge_in: np.ndarray | None = None

        self._inicializar_motores()

    @property
    def falando(self) -> bool:
        return self._falando

    def interromper(self) -> bool:
        """Interrompe imediatamente qualquer reprodução de voz em andamento (Barge-In)."""
        estava_falando = self._falando
        self._evento_interromper.set()
        self.foi_interrompida = True

        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass

        if self._processo_windows and self._processo_windows.poll() is None:
            try:
                self._processo_windows.terminate()
            except Exception:
                pass

        return estava_falando

    def _inicializar_motores(self) -> None:
        """Configura o motor neural HD como principal e prepara fallbacks."""
        try:
            import edge_tts  # noqa: F401
            import av  # noqa: F401
            self._edge_disponivel = True
            self._motor_ativo = "neural_hd"
            print(f"  [Voz] Motor Neural HD ativo: {VOZ_NEURAL_PRINCIPAL} (Voz Feminina Humanizada).")
        except Exception as e:
            print(f"  [Voz] Aviso ao carregar motor Neural HD: {e}")

        if KOKORO_MODEL_PATH.exists() and KOKORO_VOICES_PATH.exists():
            try:
                from kokoro_onnx import Kokoro
                self._kokoro = Kokoro(str(KOKORO_MODEL_PATH), str(KOKORO_VOICES_PATH))
                if not self._edge_disponivel:
                    self._motor_ativo = "kokoro"
                print("  [Voz] Motor Kokoro ONNX neural disponível.")
            except Exception:
                pass

        if not self._edge_disponivel and self._kokoro is None:
            self._motor_ativo = "windows"
            print("  [Voz] Motor ativo: Microsoft Maria Desktop (Fallback Offline).")

    def _notificar(self, evento: dict) -> None:
        if self.callback_evento:
            try:
                self.callback_evento(evento)
            except Exception:
                pass

    def falar(self, texto: str, voz_kokoro: str = "pf_dora") -> bool:
        """Sintetiza e reproduz o texto com voz neural humanizada, lip-sync e suporte a interrupção.

        Retorna True se falou até o fim, ou False se foi interrompida por barge-in.
        """
        texto_limpo = limpar_texto_para_fala(texto)
        if not texto_limpo:
            return True

        self._evento_interromper.clear()
        self.foi_interrompida = False
        self.audio_barge_in = None
        self._falando = True
        self._notificar({"tipo": "fala_inicio", "texto": texto_limpo})

        try:
            if self._edge_disponivel:
                sucesso = self._falar_neural_hd(texto_limpo)
                if sucesso:
                    return not self.foi_interrompida

            if self._kokoro is not None:
                self._falar_kokoro(texto_limpo, voz_kokoro)
            else:
                self._falar_windows_com_lipsync(texto_limpo)
            return not self.foi_interrompida
        finally:
            self._falando = False
            self.rms_saida_atual = 0.0
            self._notificar({"tipo": "fala_fim"})

    def _falar_neural_hd(self, texto: str) -> bool:
        """Sintetiza áudio 24kHz usando Microsoft Neural HD e anima os lábios pela onda sonora."""
        for voz in (VOZ_NEURAL_PRINCIPAL, VOZ_NEURAL_SECUNDARIA):
            if self._evento_interromper.is_set():
                return True
            try:
                amostras, taxa = self._gerar_audio_edge_tts(texto, voz)
                if amostras is not None and len(amostras) > 0:
                    self._reproduzir_com_lipsync_real(amostras, taxa)
                    return True
            except Exception as e:
                print(f"  [Voz] Aviso na voz {voz}: {e}")
        return False

    def _gerar_audio_edge_tts(self, texto: str, voz: str) -> tuple[np.ndarray, int]:
        """Gera e decodifica o stream MP3 neural em memória para array float32."""
        import av
        import edge_tts

        async def _baixar_stream() -> bytes:
            comunicador = edge_tts.Communicate(texto, voz)
            buffer = io.BytesIO()
            async for pacote in comunicador.stream():
                if pacote["type"] == "audio":
                    buffer.write(pacote["data"])
            return buffer.getvalue()

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            futuro = executor.submit(asyncio.run, _baixar_stream())
            dados_mp3 = futuro.result(timeout=15.0)

        if not dados_mp3:
            raise ValueError("Stream de áudio vazio")

        container = av.open(io.BytesIO(dados_mp3), format="mp3")
        quadros = [frame.to_ndarray() for frame in container.decode(audio=0)]
        if not quadros:
            raise ValueError("Nenhum quadro de áudio decodificado")

        taxa = container.streams.audio[0].rate
        audio = np.concatenate(quadros, axis=1).T.astype(np.float32)
        if audio.ndim > 1 and audio.shape[1] == 1:
            audio = audio[:, 0]
        return audio, taxa

    def _reproduzir_com_lipsync_real(self, amostras: np.ndarray, taxa: int) -> None:
        """Reproduz o áudio nos alto-falantes, envia RMS labial e monitora Barge-In do usuário."""
        import sounddevice as sd

        parar_labios = threading.Event()
        passo_segundos = 0.033  # Atualiza a mandíbula ~30 vezes por segundo
        tamanho_janela = max(1, int(taxa * passo_segundos))
        total_amostras = len(amostras)
        duracao_total = total_amostras / float(taxa)

        def _loop_envelope_labial():
            inicio = time.perf_counter()
            while not parar_labios.is_set() and not self._evento_interromper.is_set():
                decorrido = time.perf_counter() - inicio
                idx_atual = int(decorrido * taxa)
                if idx_atual >= total_amostras:
                    break

                fatia = amostras[idx_atual : min(total_amostras, idx_atual + tamanho_janela)]
                if len(fatia) > 0:
                    rms = float(np.sqrt(np.mean(np.square(fatia))))
                    self.rms_saida_atual = rms
                    # Evita saturar a mandíbula em sílabas comuns.
                    intensidade = min(1.0, max(0.0, (rms - 0.015) * 3.0))
                else:
                    self.rms_saida_atual = 0.0
                    intensidade = 0.0

                self._notificar({
                    "tipo": "fala_chunk",
                    "texto": "",
                    "intensidade": round(intensidade, 3),
                })
                time.sleep(passo_segundos)

        def _loop_barge_in():
            """Monitora o microfone durante a fala rejeitando o próprio eco da Gideon."""
            if not self.barge_in_ativo or duracao_total < 0.9:
                return
            taxa_mic = 16000
            chunk_mic = int(taxa_mic * 0.06)
            quadros_acima = 0
            pre_buffer: deque[np.ndarray] = deque(maxlen=8)
            capturados: list[np.ndarray] = []

            try:
                # Pequeno atraso inicial (200ms) para estabilizar o stream de saída
                time.sleep(0.2)
                with sd.InputStream(samplerate=taxa_mic, channels=1, dtype="float32") as mic:
                    while not parar_labios.is_set() and not self._evento_interromper.is_set():
                        dados, _ = mic.read(chunk_mic)
                        bloco = dados - np.mean(dados)
                        rms_mic = float(np.sqrt(np.mean(bloco ** 2)))

                        # Limiar anti-eco: exige energia significativamente superior à saída atual
                        limiar_eco = max(self.limiar_barge_in, self.rms_saida_atual * self.fator_rejeicao_eco)

                        if rms_mic > limiar_eco:
                            quadros_acima += 1
                            capturados.append(bloco)
                            # Exige ~240ms contínuos de voz forte para evitar falsos positivos por cliques
                            if quadros_acima >= 4:
                                self.audio_barge_in = np.concatenate(list(pre_buffer) + capturados, axis=0).flatten()
                                self.interromper()
                                break
                        else:
                            quadros_acima = max(0, quadros_acima - 1)
                            capturados.clear()
                            pre_buffer.append(bloco)
            except Exception:
                pass

        thread_labios = threading.Thread(target=_loop_envelope_labial, daemon=True)
        thread_barge = threading.Thread(target=_loop_barge_in, daemon=True)
        thread_labios.start()
        thread_barge.start()

        try:
            sd.play(amostras, taxa)
            inicio_play = time.perf_counter()
            while (time.perf_counter() - inicio_play) < duracao_total:
                if self._evento_interromper.is_set():
                    sd.stop()
                    break
                time.sleep(0.03)
        finally:
            parar_labios.set()
            thread_labios.join(timeout=0.2)
            thread_barge.join(timeout=0.2)

    def _falar_kokoro(self, texto: str, voz: str) -> None:
        """Executa a síntese usando Kokoro ONNX e reproduz com envelope labial."""
        try:
            amostras, taxa = self._kokoro.create(
                texto,
                voice=voz,
                speed=1.0,
                lang="pt-br",
            )
            self._reproduzir_com_lipsync_real(np.asarray(amostras, dtype=np.float32), taxa)
        except Exception as e:
            print(f"  [Voz] Falha na síntese Kokoro: {e}. Usando fallback do Windows.")
            self._falar_windows_com_lipsync(texto)

    def _falar_windows_com_lipsync(self, texto: str) -> None:
        """Fallback offline via System.Speech com estimativa de pulso labial e suporte a interrupção."""
        duracao_estimada = max(1.0, len(texto) / 14.0)
        parar_labios = threading.Event()

        def _animar_estimado():
            inicio = time.time()
            while not parar_labios.is_set() and not self._evento_interromper.is_set():
                if time.time() - inicio > duracao_estimada + 1.0:
                    break
                self._notificar({"tipo": "fala_chunk", "texto": "", "intensidade": 0.6})
                time.sleep(0.08)

        thread_labios = threading.Thread(target=_animar_estimado, daemon=True)
        thread_labios.start()

        try:
            texto_escapado = texto.replace("'", "''").replace('"', '`"')
            comando_ps = f"""
            Add-Type -AssemblyName System.Speech;
            $speak = New-Object System.Speech.Synthesis.SpeechSynthesizer;
            try {{
                $speak.SelectVoice('Microsoft Maria Desktop');
            }} catch {{}}
            $speak.Rate = 1;
            $speak.Speak('{texto_escapado}');
            """
            self._processo_windows = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", comando_ps],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            while self._processo_windows.poll() is None:
                if self._evento_interromper.is_set():
                    self._processo_windows.terminate()
                    break
                time.sleep(0.05)
        finally:
            self._processo_windows = None
            parar_labios.set()
            thread_labios.join(timeout=0.2)
