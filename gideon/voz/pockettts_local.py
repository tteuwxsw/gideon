"""Cliente leve para o PocketTTS executado em um processo isolado sob demanda."""

from __future__ import annotations

import atexit
import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import struct
import subprocess
import threading
import time
from typing import BinaryIO

import numpy as np

from gideon.caminhos import DADOS_DIR, FROZEN, RESOURCE_DIR


CONFIG_VOZ_LOCAL = DADOS_DIR / "voz_local.json"
MOTOR_DIR = DADOS_DIR.parent / "motores" / "pockettts"
PYTHON_PADRAO = MOTOR_DIR / ".venv" / "Scripts" / "python.exe"
CACHE_MODELOS_DIR = MOTOR_DIR / "cache_huggingface"
REFERENCIA_PADRAO = DADOS_DIR / "voz" / "referencia.wav"
MAX_FRAME_BYTES = 64 * 1024 * 1024
TIMEOUT_INICIALIZACAO_S = 10.0


@dataclass(frozen=True)
class ConfiguracaoPocketTTS:
    python: Path
    referencia: Path
    qualidade: str = "leve"
    quantizar: bool = True
    threads: int = 4
    ocioso_s: float = 30.0
    timeout_s: float = 180.0

    @property
    def identidade_cache(self) -> str:
        stat = self.referencia.stat()
        return (
            f"pockettts|{self.qualidade}|q{int(self.quantizar)}|"
            f"{stat.st_size}|{stat.st_mtime_ns}"
        )


def carregar_configuracao(
    caminho: Path = CONFIG_VOZ_LOCAL,
) -> ConfiguracaoPocketTTS | None:
    """Carrega o motor local somente quando foi explicitamente habilitado."""
    if os.environ.get("GIDEON_TTS_LOCAL", "").strip().lower() in {"0", "false", "off"}:
        return None
    if not caminho.is_file():
        return None
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(dados, dict) or not _como_bool(dados.get("ativo", False)):
        return None

    try:
        python = Path(dados.get("python") or PYTHON_PADRAO).expanduser()
        referencia = Path(dados.get("referencia") or REFERENCIA_PADRAO).expanduser()
        qualidade = str(dados.get("qualidade") or "leve").strip().lower()
        if qualidade not in {"leve", "qualidade"}:
            qualidade = "leve"
        if not python.is_file() or not referencia.is_file():
            return None

        threads = max(1, min(8, int(dados.get("threads", 4))))
        ocioso_s = max(10.0, min(300.0, float(dados.get("ocioso_s", 30.0))))
        timeout_s = max(15.0, min(600.0, float(dados.get("timeout_s", 180.0))))
    except (OSError, TypeError, ValueError):
        return None

    return ConfiguracaoPocketTTS(
        python=python,
        referencia=referencia,
        qualidade=qualidade,
        quantizar=_como_bool(dados.get("quantizar", True)),
        threads=threads,
        ocioso_s=ocioso_s,
        timeout_s=timeout_s,
    )


def _como_bool(valor: object) -> bool:
    if isinstance(valor, str):
        return valor.strip().lower() not in {"", "0", "false", "nao", "não", "off"}
    return bool(valor)


def _sidecar_path() -> Path:
    if FROZEN:
        return RESOURCE_DIR / "gideon" / "voz" / "pockettts_sidecar.py"
    return Path(__file__).with_name("pockettts_sidecar.py")


def _enviar(stream: BinaryIO, payload: dict) -> None:
    corpo = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(corpo) > MAX_FRAME_BYTES:
        raise ValueError("Mensagem para o motor local excedeu o limite seguro.")
    stream.write(struct.pack("!I", len(corpo)))
    stream.write(corpo)
    stream.flush()


def _receber(stream: BinaryIO) -> dict:
    cabecalho = stream.read(4)
    if len(cabecalho) != 4:
        raise RuntimeError("O processo local de voz encerrou inesperadamente.")
    (tamanho,) = struct.unpack("!I", cabecalho)
    if tamanho > MAX_FRAME_BYTES:
        raise RuntimeError("Resposta do motor local excedeu o limite seguro.")
    corpo = bytearray()
    while len(corpo) < tamanho:
        parte = stream.read(tamanho - len(corpo))
        if not parte:
            raise RuntimeError("Resposta incompleta do motor local de voz.")
        corpo.extend(parte)
    mensagem = json.loads(bytes(corpo).decode("utf-8"))
    if not isinstance(mensagem, dict):
        raise RuntimeError("Resposta invalida do motor local de voz.")
    return mensagem


def _receber_com_timeout(stream: BinaryIO, timeout_s: float) -> dict:
    resultado: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

    def _ler() -> None:
        try:
            resultado.put((True, _receber(stream)))
        except BaseException as erro:
            resultado.put((False, erro))

    leitor = threading.Thread(target=_ler, daemon=True, name="gideon-pockettts-pipe")
    leitor.start()
    try:
        sucesso, valor = resultado.get(timeout=timeout_s)
    except queue.Empty as erro:
        raise TimeoutError(f"PocketTTS nao respondeu em {timeout_s:.0f} segundos.") from erro
    if not sucesso:
        assert isinstance(valor, BaseException)
        raise valor
    assert isinstance(valor, dict)
    return valor


class PocketTTSLocal:
    """Mantem o modelo apenas durante uma janela curta de conversacao."""

    def __init__(self, config: ConfiguracaoPocketTTS):
        self.config = config
        self._processo: subprocess.Popen | None = None
        self._log = None
        self._lock = threading.RLock()
        self._timer: threading.Timer | None = None
        atexit.register(self.encerrar)

    @property
    def identidade_cache(self) -> str:
        return self.config.identidade_cache

    def _iniciar(self) -> None:
        if self._processo is not None and self._processo.poll() is None:
            return
        sidecar = _sidecar_path()
        if not sidecar.is_file():
            raise FileNotFoundError(f"Sidecar PocketTTS ausente: {sidecar}")

        log_path = DADOS_DIR / "gideon_pockettts.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = open(log_path, "a", encoding="utf-8", buffering=1)
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
        try:
            ambiente = os.environ.copy()
            ambiente["HF_HOME"] = str(CACHE_MODELOS_DIR)
            ambiente["HF_HUB_OFFLINE"] = "1"
            self._processo = subprocess.Popen(
                [str(self.config.python), str(sidecar)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._log,
                creationflags=flags,
                env=ambiente,
            )
            assert self._processo.stdout is not None
            pronto = _receber_com_timeout(self._processo.stdout, TIMEOUT_INICIALIZACAO_S)
            if pronto.get("op") != "ready":
                raise RuntimeError("O PocketTTS nao concluiu a inicializacao.")
        except Exception:
            self._encerrar_sem_lock(forcar=True)
            raise

    def sintetizar(self, texto: str) -> tuple[np.ndarray, int]:
        with self._lock:
            self._iniciar()
            assert self._processo is not None
            assert self._processo.stdin is not None
            assert self._processo.stdout is not None
            try:
                _enviar(
                    self._processo.stdin,
                    {
                        "op": "synthesize",
                        "text": texto,
                        "reference": str(self.config.referencia),
                        "quality": self.config.qualidade,
                        "quantize": self.config.quantizar,
                        "threads": self.config.threads,
                    },
                )
                prazo = time.monotonic() + self.config.timeout_s
                while True:
                    restante = prazo - time.monotonic()
                    if restante <= 0:
                        raise TimeoutError(
                            f"PocketTTS nao sintetizou em {self.config.timeout_s:.0f} segundos."
                        )
                    resposta = _receber_com_timeout(self._processo.stdout, restante)
                    op = resposta.get("op")
                    if op == "progress":
                        continue
                    if op == "error":
                        raise RuntimeError(str(resposta.get("message") or "Falha no PocketTTS."))
                    if op != "audio":
                        raise RuntimeError(f"Resposta inesperada do PocketTTS: {op!r}")
                    pcm = base64.b64decode(resposta["audio_pcm_b64"], validate=True)
                    if not pcm or len(pcm) % 2:
                        raise RuntimeError("PocketTTS retornou audio PCM invalido.")
                    taxa = int(resposta.get("sample_rate") or 24000)
                    if not 8000 <= taxa <= 192000:
                        raise RuntimeError(f"PocketTTS retornou taxa de amostragem invalida: {taxa}.")
                    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32767.0
                    self._agendar_encerramento()
                    return audio, taxa
            except Exception:
                self._encerrar_sem_lock(forcar=True)
                raise

    def _agendar_encerramento(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(self.config.ocioso_s, self.encerrar)
        self._timer.daemon = True
        self._timer.start()

    def _encerrar_sem_lock(self, forcar: bool = False) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        processo = self._processo
        self._processo = None
        if processo is not None and processo.poll() is None:
            if not forcar:
                try:
                    if processo.stdin is not None:
                        _enviar(processo.stdin, {"op": "shutdown"})
                    processo.wait(timeout=3)
                except Exception:
                    pass
            if processo.poll() is None:
                processo.terminate()
                try:
                    processo.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    processo.kill()
                    try:
                        processo.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
        if processo is not None:
            for stream in (processo.stdin, processo.stdout):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
        if self._log is not None:
            self._log.close()
            self._log = None

    def encerrar(self) -> None:
        with self._lock:
            self._encerrar_sem_lock()


def criar_motor_local() -> PocketTTSLocal | None:
    config = carregar_configuracao()
    return PocketTTSLocal(config) if config else None
