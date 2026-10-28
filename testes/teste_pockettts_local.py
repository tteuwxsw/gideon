"""Testes isolados do cliente PocketTTS, sem baixar ou carregar o modelo real."""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

from gideon.voz.fala import SintetizadorVoz
from gideon.voz.pockettts_local import (
    ConfiguracaoPocketTTS,
    PocketTTSLocal,
    _enviar,
    _receber,
    _receber_com_timeout,
    carregar_configuracao,
)


SIDECAR_FALSO = r'''
import base64
import json
import struct
import sys
import time


def enviar(payload):
    corpo = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("!I", len(corpo)) + corpo)
    sys.stdout.buffer.flush()


def receber():
    cabecalho = sys.stdin.buffer.read(4)
    if not cabecalho:
        return None
    tamanho = struct.unpack("!I", cabecalho)[0]
    corpo = sys.stdin.buffer.read(tamanho)
    return json.loads(corpo.decode("utf-8"))


enviar({"op": "ready", "sample_rate": 24000})
while True:
    mensagem = receber()
    if mensagem is None or mensagem.get("op") == "shutdown":
        raise SystemExit(0)
    if mensagem.get("text") == "travar":
        time.sleep(10)
        continue
    enviar({"op": "progress", "stage": "fake"})
    pcm = struct.pack("<hhh", -32767, 0, 32767)
    enviar({
        "op": "audio",
        "audio_pcm_b64": base64.b64encode(pcm).decode("ascii"),
        "sample_rate": 24000,
    })
'''


class StreamBloqueado:
    def read(self, _tamanho):
        time.sleep(1)
        return b""


class TestePocketTTSLocal(unittest.TestCase):
    def test_protocolo_enquadrado(self):
        stream = io.BytesIO()
        _enviar(stream, {"op": "ready", "texto": "olá"})
        stream.seek(0)
        self.assertEqual(_receber(stream), {"op": "ready", "texto": "olá"})

    def test_leitura_tem_timeout(self):
        inicio = time.monotonic()
        with self.assertRaises(TimeoutError):
            _receber_com_timeout(StreamBloqueado(), 0.05)
        self.assertLess(time.monotonic() - inicio, 0.5)

    def test_configuracao_invalida_desativa_sem_quebrar_a_voz(self):
        with tempfile.TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            config = raiz / "voz_local.json"
            config.write_text(
                json.dumps({"ativo": True, "threads": "invalido"}),
                encoding="utf-8",
            )
            self.assertIsNone(carregar_configuracao(config))

    def test_configuracao_valida_normaliza_limites_e_booleanos(self):
        with tempfile.TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            referencia = raiz / "referencia.wav"
            referencia.write_bytes(b"RIFF-falso")
            config = raiz / "voz_local.json"
            config.write_text(
                json.dumps(
                    {
                        "ativo": "true",
                        "python": sys.executable,
                        "referencia": str(referencia),
                        "qualidade": "desconhecida",
                        "quantizar": "false",
                        "threads": 99,
                        "ocioso_s": 1,
                        "timeout_s": 999,
                    }
                ),
                encoding="utf-8",
            )

            resultado = carregar_configuracao(config)
            self.assertIsNotNone(resultado)
            assert resultado is not None
            self.assertEqual(resultado.qualidade, "leve")
            self.assertFalse(resultado.quantizar)
            self.assertEqual(resultado.threads, 8)
            self.assertEqual(resultado.ocioso_s, 10.0)
            self.assertEqual(resultado.timeout_s, 600.0)

    def test_sintese_progresso_timeout_reinicio_e_ociosidade(self):
        with tempfile.TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            referencia = raiz / "referencia.wav"
            referencia.write_bytes(b"RIFF-falso")
            sidecar = raiz / "sidecar_falso.py"
            sidecar.write_text(SIDECAR_FALSO, encoding="utf-8")
            config = ConfiguracaoPocketTTS(
                python=Path(sys.executable),
                referencia=referencia,
                ocioso_s=0.15,
                timeout_s=0.1,
            )
            motor = PocketTTSLocal(config)

            with (
                patch("gideon.voz.pockettts_local._sidecar_path", return_value=sidecar),
                patch("gideon.voz.pockettts_local.DADOS_DIR", raiz),
            ):
                audio, taxa = motor.sintetizar("teste")
                self.assertEqual(taxa, 24000)
                np.testing.assert_allclose(audio, [-1.0, 0.0, 1.0], atol=1e-4)

                with self.assertRaises(TimeoutError):
                    motor.sintetizar("travar")
                self.assertIsNone(motor._processo)

                audio, _ = motor.sintetizar("reiniciado")
                self.assertEqual(len(audio), 3)
                time.sleep(0.5)
                self.assertIsNone(motor._processo)

            motor.encerrar()

    def test_fallback_nao_contamina_cache_da_voz_local(self):
        sintetizador = object.__new__(SintetizadorVoz)
        sintetizador._identidade_cache = "pockettts|referencia"
        sintetizador._cache_memoria = {}
        sintetizador._obter_do_cache = lambda _chave: None
        sintetizador._salvar_no_cache = (
            lambda chave, audio, taxa: sintetizador._cache_memoria.__setitem__(chave, (audio, taxa))
        )
        sintetizador._gerar_audio_voz_fixa = lambda _texto: self._simular_fallback(sintetizador)

        audio, taxa, em_cache = sintetizador.sintetizar_para_memoria("Teste")

        self.assertFalse(em_cache)
        self.assertEqual(taxa, 24000)
        self.assertEqual(len(audio), 2)
        self.assertEqual(len(sintetizador._cache_memoria), 1)
        chave_salva = next(iter(sintetizador._cache_memoria))
        self.assertEqual(chave_salva, sintetizador._chave_cache("Teste"))

    @staticmethod
    def _simular_fallback(sintetizador):
        sintetizador._identidade_cache = "pt-BR-ThalitaMultilingualNeural"
        return np.zeros(2, dtype=np.float32), 24000


if __name__ == "__main__":
    unittest.main()
