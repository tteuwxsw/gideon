"""
Processamento de áudio para replicar o estilo da Gideon (The Flash).

Características da voz original:
- Atriz: Morena Baccarin com efeitos de estúdio
- Tom: ligeiramente mais alto (pitch +5% a +8%)
- Reverb: leve, espacial (como em sala de controle)
- EQ: frequências médias aumentadas, graves suaves
- Ritmo: pausado, robótico mas natural

Usa FFmpeg para processar o áudio em tempo real.
"""

import subprocess
from pathlib import Path
import numpy as np
import io
import wave
from gideon.processos_windows import opcoes_processo_oculto


def numpy_para_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    """Converte numpy array para bytes WAV."""
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)   # 16-bit
        wav_file.setframerate(sample_rate)
        
        # Converte float32 [-1, 1] para int16
        audio_int16 = (audio * 32767).astype(np.int16)
        wav_file.writeframes(audio_int16.tobytes())
    
    return buffer.getvalue()


def wav_bytes_para_numpy(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    """Converte bytes WAV para numpy array."""
    buffer = io.BytesIO(wav_bytes)
    with wave.open(buffer, 'rb') as wav_file:
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())
        audio_int16 = np.frombuffer(frames, dtype=np.int16)
        audio_float = audio_int16.astype(np.float32) / 32767.0
    
    return audio_float, sample_rate


def aplicar_efeito_gideon_numpy(audio: np.ndarray, sample_rate: int = 24000) -> np.ndarray:
    """
    Aplica efeitos de áudio para soar como a Gideon da série The Flash.
    
    Args:
        audio: Array numpy float32 [-1, 1]
        sample_rate: Taxa de amostragem (padrão 24kHz)
    
    Returns:
        Audio processado como numpy array
    """
    try:
        # Converte para WAV bytes
        wav_entrada = numpy_para_wav_bytes(audio, sample_rate)
        
        # Aplica efeitos com FFmpeg
        wav_saida = aplicar_efeito_gideon(wav_entrada, sample_rate)
        
        # Converte de volta para numpy
        audio_processado, _ = wav_bytes_para_numpy(wav_saida)
        
        return audio_processado
    
    except Exception:
        # Se falhar, retorna áudio original
        return audio


def aplicar_efeito_gideon(audio_entrada: bytes, sample_rate: int = 24000) -> bytes:
    """
    Aplica efeitos de áudio para soar como a Gideon da série The Flash.
    
    Args:
        audio_entrada: Áudio WAV em bytes
        sample_rate: Taxa de amostragem (padrão 24kHz)
    
    Returns:
        Áudio processado em bytes
    """
    try:
        # Filtros FFmpeg para replicar a voz da Gideon:
        # 1. asetrate: aumenta pitch +6% (1.06x)
        # 2. atempo: mantém velocidade original
        # 3. aecho: reverb suave espacial
        # 4. equalizer: reforça médios, suaviza graves
        # 5. highpass: remove ruído abaixo de 80Hz
        filtros = [
            "asetrate=25440",  # +6% pitch (24000 * 1.06)
            "atempo=0.943",     # Compensar velocidade (1/1.06)
            "aecho=0.8:0.88:60:0.4",  # Reverb leve (delay 60ms, decay 0.4)
            "equalizer=f=1000:width_type=o:width=2:g=3",  # Boost médios +3dB
            "equalizer=f=200:width_type=o:width=2:g=-2",  # Suaviza graves -2dB
            "highpass=f=80",    # Remove ruído de fundo
            "aresample=24000",  # Volta para 24kHz
        ]
        
        filtro_completo = ",".join(filtros)
        
        # Processa com FFmpeg
        cmd = [
            "ffmpeg",
            "-f", "wav",
            "-i", "pipe:0",  # Lê da entrada padrão
            "-af", filtro_completo,
            "-f", "wav",
            "-ar", str(sample_rate),
            "pipe:1",  # Escreve na saída padrão
        ]
        
        processo = subprocess.run(
            cmd,
            input=audio_entrada,
            capture_output=True,
            check=True,
            **opcoes_processo_oculto()
        )
        
        return processo.stdout
    
    except subprocess.CalledProcessError:
        # Se FFmpeg falhar, retorna áudio original sem efeitos
        return audio_entrada
    except FileNotFoundError:
        # FFmpeg não instalado, retorna áudio original
        return audio_entrada


def aplicar_efeito_gideon_arquivo(caminho_entrada: Path, caminho_saida: Path) -> bool:
    """
    Aplica efeitos da Gideon em um arquivo de áudio.
    
    Args:
        caminho_entrada: Arquivo WAV de entrada
        caminho_saida: Arquivo WAV de saída
    
    Returns:
        True se sucesso, False se falhar
    """
    try:
        filtros = [
            "asetrate=25440",
            "atempo=0.943",
            "aecho=0.8:0.88:60:0.4",
            "equalizer=f=1000:width_type=o:width=2:g=3",
            "equalizer=f=200:width_type=o:width=2:g=-2",
            "highpass=f=80",
            "aresample=24000",
        ]
        
        filtro_completo = ",".join(filtros)
        
        cmd = [
            "ffmpeg",
            "-i", str(caminho_entrada),
            "-af", filtro_completo,
            "-y",  # Sobrescreve se existir
            str(caminho_saida),
        ]
        
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            **opcoes_processo_oculto()
        )
        
        return True
    
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def verificar_ffmpeg_disponivel() -> bool:
    """Verifica se FFmpeg está instalado e acessível."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            check=True,
            **opcoes_processo_oculto()
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
