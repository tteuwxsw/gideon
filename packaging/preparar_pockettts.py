"""Baixa, valida e prepara o estado de voz usado pelo sidecar PocketTTS."""

from __future__ import annotations

import argparse
from pathlib import Path
import wave


def validar_referencia(caminho: Path) -> None:
    if caminho.suffix.lower() != ".wav":
        raise ValueError("A referencia deve ser um arquivo WAV PCM de 16 bits.")
    with wave.open(str(caminho), "rb") as audio:
        if audio.getsampwidth() != 2:
            raise ValueError("A referencia WAV precisa usar PCM de 16 bits.")
        if audio.getnchannels() not in {1, 2}:
            raise ValueError("A referencia WAV precisa ser mono ou estereo.")
        duracao = audio.getnframes() / float(audio.getframerate())
        if duracao < 3.0:
            raise ValueError("A referencia de voz precisa ter pelo menos 3 segundos.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--referencia", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--qualidade", choices=("leve", "qualidade"), default="leve")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--sem-quantizacao", action="store_true")
    args = parser.parse_args()

    referencia = args.referencia.resolve()
    saida = args.saida.resolve()
    validar_referencia(referencia)
    saida.parent.mkdir(parents=True, exist_ok=True)

    import torch
    from pocket_tts import TTSModel, export_model_state

    torch.set_num_threads(max(1, min(8, args.threads)))
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass

    idioma = "portuguese_24l" if args.qualidade == "qualidade" else "portuguese"
    print(f"Preparando PocketTTS ({idioma})...")
    modelo = TTSModel.load_model(language=idioma, quantize=not args.sem_quantizacao)
    try:
        estado = modelo.get_state_for_audio_prompt(str(referencia), truncate=True)
    except TypeError:
        estado = modelo.get_state_for_audio_prompt(str(referencia))

    temporario = saida.with_name(f"{saida.stem}.tmp{saida.suffix}")
    export_model_state(estado, str(temporario))
    temporario.replace(saida)

    audio = modelo.generate_audio(estado, "Ola. Sistemas de voz local prontos.")
    if audio.numel() == 0:
        raise RuntimeError("O PocketTTS retornou audio vazio no teste de instalacao.")
    print(f"PocketTTS validado em 24 kHz; estado salvo em {saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
