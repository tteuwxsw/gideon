"""Módulo de síntese de voz (TTS) humanizada da Gideon.

Hierarquia de motores neurais:
1. Neural HD (`edge-tts`: `pt-BR-ThalitaMultilingualNeural` / `pt-BR-FranciscaNeural`) — Voz feminina brasileira ultra-humanizada, com entonação e respiração naturais.
2. Kokoro ONNX (`pf_dora` / `af_bella`) — Motor neural local.
3. Fallback nativo offline do Windows (`Microsoft Maria Desktop`).

Inclui análise de envelope de amplitude de áudio (RMS) em tempo real para
sincronia labial (lip-sync) fiel no avatar 3D em Godot 4.
"""

import asyncio
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
    """Gerenciador de voz neural humanizada da Gideon com lip-sync reativo a áudio."""

    def __init__(self, callback_evento: Callable[[dict], Any] | None = None):
        self.callback_evento = callback_evento
        self._kokoro = None
        self._edge_disponivel = False
        self._motor_ativo = "neural_hd"
        self._inicializar_motores()

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

    def falar(self, texto: str, voz_kokoro: str = "pf_dora") -> None:
        """Sintetiza e reproduz o texto com voz neural humanizada e lip-sync reativo."""
        texto_limpo = limpar_texto_para_fala(texto)
        if not texto_limpo:
            return

        self._notificar({"tipo": "fala_inicio", "texto": texto_limpo})

        try:
            if self._edge_disponivel:
                sucesso = self._falar_neural_hd(texto_limpo)
                if sucesso:
                    return

            if self._kokoro is not None:
                self._falar_kokoro(texto_limpo, voz_kokoro)
            else:
                self._falar_windows_com_lipsync(texto_limpo)
        finally:
            self._notificar({"tipo": "fala_fim"})

    def _falar_neural_hd(self, texto: str) -> bool:
        """Sintetiza áudio 24kHz usando Microsoft Neural HD e anima os lábios pela onda sonora."""
        for voz in (VOZ_NEURAL_PRINCIPAL, VOZ_NEURAL_SECUNDARIA):
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

        # Executa em thread dedicada para nunca conflitar com o event loop do FastAPI
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
        """Reproduz o áudio nos alto-falantes e envia a energia RMS real de cada sílaba ao avatar."""
        import sounddevice as sd

        parar_labios = threading.Event()
        passo_segundos = 0.055  # Atualiza a boca ~18 vezes por segundo
        tamanho_janela = max(1, int(taxa * passo_segundos))
        total_amostras = len(amostras)

        def _loop_envelope_labial():
            inicio = time.perf_counter()
            while not parar_labios.is_set():
                decorrido = time.perf_counter() - inicio
                idx_atual = int(decorrido * taxa)
                if idx_atual >= total_amostras:
                    break

                fatia = amostras[idx_atual : min(total_amostras, idx_atual + tamanho_janela)]
                if len(fatia) > 0:
                    rms = float(np.sqrt(np.mean(np.square(fatia))))
                    # Normaliza o RMS de fala humana (geralmente 0.02 a 0.25) para [0.0, 1.0]
                    intensidade = min(1.0, max(0.0, (rms - 0.008) * 5.2))
                else:
                    intensidade = 0.0

                self._notificar({
                    "tipo": "fala_chunk",
                    "texto": "",
                    "intensidade": round(intensidade, 3),
                })
                time.sleep(passo_segundos)

        thread_labios = threading.Thread(target=_loop_envelope_labial, daemon=True)
        thread_labios.start()

        try:
            sd.play(amostras, taxa)
            sd.wait()
        finally:
            parar_labios.set()
            thread_labios.join(timeout=0.2)

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
        """Fallback offline via System.Speech com estimativa de pulso labial."""
        duracao_estimada = max(1.0, len(texto) / 14.0)
        parar_labios = threading.Event()

        def _animar_estimado():
            inicio = time.time()
            while not parar_labios.is_set():
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
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", comando_ps],
                capture_output=True,
                text=True,
            )
        finally:
            parar_labios.set()
            thread_labios.join(timeout=0.2)
