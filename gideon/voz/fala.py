"""Módulo de síntese de voz (TTS) da Gideon.

Suporta:
1. Kokoro ONNX (alta fidelidade neural local).
2. Fallback nativo do Windows (System.Speech - Microsoft Maria Desktop) sem latência.
3. Transmissão de eventos de lip sync via WebSocket para o avatar.
"""

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Any

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
MODELOS_DIR = ROOT_DIR / "dados" / "modelos"
KOKORO_MODEL_PATH = MODELOS_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES_PATH = MODELOS_DIR / "voices-v1.0.bin"


class SintetizadorVoz:
    """Gerenciador de voz da Gideon com suporte a múltiplos motores locais."""

    def __init__(self, callback_evento: Callable[[dict], Any] | None = None):
        self.callback_evento = callback_evento
        self._kokoro = None
        self._motor_ativo = "windows"
        self._inicializar_motores()

    def _inicializar_motores(self) -> None:
        """Verifica se o Kokoro está baixado ou utiliza o motor nativo do Windows."""
        if KOKORO_MODEL_PATH.exists() and KOKORO_VOICES_PATH.exists():
            try:
                from kokoro_onnx import Kokoro
                self._kokoro = Kokoro(str(KOKORO_MODEL_PATH), str(KOKORO_VOICES_PATH))
                self._motor_ativo = "kokoro"
                print("  [Voz] Motor Kokoro ONNX neural carregado com sucesso.")
                return
            except Exception as e:
                print(f"  [Voz] Falha ao carregar Kokoro ONNX: {e}. Usando voz nativa.")

        self._motor_ativo = "windows"
        print("  [Voz] Motor ativo: Microsoft Maria Desktop (Nativo do Windows).")

    def _notificar(self, evento: dict) -> None:
        if self.callback_evento:
            try:
                self.callback_evento(evento)
            except Exception:
                pass

    def falar(self, texto: str, voz_kokoro: str = "af_bella") -> None:
        """Sintetiza e reproduz o texto nos alto-falantes com lip sync em tempo real."""
        texto_limpo = texto.strip()
        if not texto_limpo:
            return

        # Notifica o avatar que a fala começou
        self._notificar({"tipo": "fala_inicio", "texto": texto_limpo})

        # Estima duração com base na contagem de caracteres (~14 caracteres por segundo)
        duracao_estimada = max(1.0, len(texto_limpo) / 14.0)

        # Inicia thread de pulso labial para o avatar durante a fala
        parar_labios = threading.Event()

        def animar_labios():
            inicio = time.time()
            while not parar_labios.is_set():
                if time.time() - inicio > duracao_estimada + 1.0:
                    break
                self._notificar({"tipo": "fala_chunk", "texto": ""})
                time.sleep(0.08)

        thread_labios = threading.Thread(target=animar_labios, daemon=True)
        thread_labios.start()

        try:
            if self._motor_ativo == "kokoro" and self._kokoro is not None:
                self._falar_kokoro(texto_limpo, voz_kokoro)
            else:
                self._falar_windows(texto_limpo)
        finally:
            parar_labios.set()
            thread_labios.join(timeout=0.2)
            self._notificar({"tipo": "fala_fim"})

    def _falar_windows(self, texto: str) -> None:
        """Executa a síntese via System.Speech no PowerShell usando a voz da Microsoft Maria."""
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

    def _falar_kokoro(self, texto: str, voz: str) -> None:
        """Executa a síntese usando Kokoro ONNX e reproduz com sounddevice."""
        try:
            import sounddevice as sd
            amostras, taxa = self._kokoro.create(
                texto,
                voice=voz,
                speed=1.0,
                lang="pt-br",
            )
            sd.play(amostras, taxa)
            sd.wait()
        except Exception as e:
            print(f"  [Voz] Falha na síntese Kokoro: {e}. Usando voz do Windows como fallback.")
            self._falar_windows(texto)
