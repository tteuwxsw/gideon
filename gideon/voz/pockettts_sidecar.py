"""Processo isolado do PocketTTS; carregado somente enquanto a Gideon fala."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import struct
import sys
import traceback


MAX_FRAME_BYTES = 64 * 1024 * 1024


def _enviar(stream, payload: dict) -> None:
    corpo = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(corpo) > MAX_FRAME_BYTES:
        raise ValueError("Resposta excedeu o limite seguro.")
    stream.write(struct.pack("!I", len(corpo)))
    stream.write(corpo)
    stream.flush()


def _receber(stream) -> dict | None:
    cabecalho = stream.read(4)
    if not cabecalho:
        return None
    if len(cabecalho) != 4:
        raise RuntimeError("Cabecalho incompleto.")
    (tamanho,) = struct.unpack("!I", cabecalho)
    if tamanho > MAX_FRAME_BYTES:
        raise RuntimeError("Mensagem excedeu o limite seguro.")
    corpo = bytearray()
    while len(corpo) < tamanho:
        parte = stream.read(tamanho - len(corpo))
        if not parte:
            raise RuntimeError("Mensagem incompleta.")
        corpo.extend(parte)
    return json.loads(bytes(corpo).decode("utf-8"))


def main() -> int:
    entrada = sys.stdin.buffer
    canal_fd = os.dup(1)
    os.dup2(2, 1)
    saida = os.fdopen(canal_fd, "wb")
    modelo = None
    estado_voz = None
    assinatura = None

    _enviar(saida, {"op": "ready", "sample_rate": 24000})
    while True:
        mensagem = _receber(entrada)
        if mensagem is None or mensagem.get("op") == "shutdown":
            return 0
        if mensagem.get("op") != "synthesize":
            _enviar(saida, {"op": "error", "message": "Operacao desconhecida."})
            continue
        try:
            texto = str(mensagem.get("text") or "").strip()
            referencia = Path(str(mensagem.get("reference") or ""))
            if not texto or not referencia.is_file():
                raise ValueError("Texto ou referencia de voz ausente.")

            qualidade = mensagem.get("quality") == "qualidade"
            quantizar = bool(mensagem.get("quantize", True))
            threads = max(1, min(8, int(mensagem.get("threads", 4))))
            atual = (
                qualidade,
                quantizar,
                str(referencia.resolve()),
                referencia.stat().st_mtime_ns,
                referencia.stat().st_size,
            )

            if modelo is None or assinatura != atual:
                _enviar(saida, {"op": "progress", "stage": "loading_model"})
                import torch
                from pocket_tts import TTSModel

                torch.set_num_threads(threads)
                try:
                    torch.set_num_interop_threads(1)
                except RuntimeError:
                    pass
                idioma = "portuguese_24l" if qualidade else "portuguese"
                modelo = TTSModel.load_model(language=idioma, quantize=quantizar)
                try:
                    estado_voz = modelo.get_state_for_audio_prompt(str(referencia), truncate=True)
                except TypeError:
                    estado_voz = modelo.get_state_for_audio_prompt(str(referencia))
                assinatura = atual

            audio = modelo.generate_audio(estado_voz, texto)
            import numpy as np

            dados = np.asarray(audio.detach().cpu(), dtype=np.float32).squeeze()
            pcm = (np.clip(dados, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
            _enviar(
                saida,
                {
                    "op": "audio",
                    "audio_pcm_b64": base64.b64encode(pcm).decode("ascii"),
                    "sample_rate": int(getattr(modelo, "sample_rate", 24000)),
                },
            )
        except Exception as erro:
            traceback.print_exc(file=sys.stderr)
            _enviar(saida, {"op": "error", "message": f"{type(erro).__name__}: {erro}"})


if __name__ == "__main__":
    raise SystemExit(main())
