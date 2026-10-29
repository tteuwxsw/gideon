"""Testes dos earcons procedurais, configuração e bloqueio durante captura."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import sys

import numpy as np

from gideon import configuracao
from gideon import servidor
from gideon.voz import sons
from gideon.voz.ouvido import OuvinteVoz


def test_earcons_sao_curto_suave_e_erro_grave():
    ativacao = sons._sintetizar_som("ativacao")
    conclusao = sons._sintetizar_som("conclusao")
    erro = sons._sintetizar_som("erro")

    assert 0 < len(ativacao) < sons.TAXA_AMOSTRAGEM
    assert 0 < len(conclusao) < sons.TAXA_AMOSTRAGEM
    assert 0 < len(erro) < sons.TAXA_AMOSTRAGEM
    assert max(float(np.max(np.abs(audio))) for audio in (ativacao, conclusao, erro)) < 0.35

    frequencias = np.fft.rfftfreq(len(erro), 1 / sons.TAXA_AMOSTRAGEM)
    pico_erro = float(frequencias[np.argmax(np.abs(np.fft.rfft(erro)))])
    assert pico_erro < 300.0
    assert sons.obter_wav_bytes("ativacao")[:4] == b"RIFF"


def test_configuracao_de_som_persiste_e_limita_volume(tmp_path):
    arquivo = tmp_path / "config.json"
    with patch.object(configuracao, "CONFIG_ARQUIVO", arquivo):
        assert configuracao.obter_configuracao_sons() == {"ativo": True, "volume": 0.18}
        assert configuracao.definir_configuracao_sons(False, 0.9) == {"ativo": False, "volume": 0.5}
        assert configuracao.obter_configuracao_sons() == {"ativo": False, "volume": 0.5}


def test_reproducao_respeita_desligado_e_volume_com_mocks():
    sounddevice = MagicMock()
    with patch.dict(sys.modules, {"sounddevice": sounddevice}), patch(
        "gideon.voz.sons.threading.Thread"
    ) as thread_cls, patch(
        "gideon.configuracao.obter_configuracao_sons",
        return_value={"ativo": False, "volume": 0.2},
    ):
        sons.tocar_som("ativacao")
        thread_cls.call_args.kwargs["target"]()
    sounddevice.play.assert_not_called()

    sounddevice.reset_mock()
    with patch.dict(sys.modules, {"sounddevice": sounddevice}), patch(
        "gideon.voz.sons.threading.Thread"
    ) as thread_cls, patch(
        "gideon.configuracao.obter_configuracao_sons",
        return_value={"ativo": True, "volume": 0.2},
    ):
        sons.tocar_som("ativacao")
        thread_cls.call_args.kwargs["target"]()
    audio_tocado = sounddevice.play.call_args.args[0]
    assert np.max(np.abs(audio_tocado)) <= np.max(np.abs(sons._obter_array("ativacao"))) * 0.21


def test_evento_sonoro_e_suprimido_enquanto_microfone_grava():
    original = servidor.orquestrador_voz
    servidor.orquestrador_voz = SimpleNamespace(ouvinte=SimpleNamespace(gravando=True))
    try:
        with patch("gideon.configuracao.obter_configuracao_sons", return_value={"ativo": True, "volume": 0.2}), patch(
            "gideon.servidor.json.dumps"
        ) as serializar:
            asyncio.run(servidor.broadcast_ws({"tipo": "som", "som": "conclusao"}))
        serializar.assert_not_called()
    finally:
        servidor.orquestrador_voz = original


def test_flag_de_gravacao_e_liberada_apos_falha_de_microfone():
    ouvinte = object.__new__(OuvinteVoz)
    ouvinte._gravando = False
    ouvinte._silero_vad = None
    ouvinte._limite_silencio_padrao = 0.7
    ouvinte._notificar = MagicMock()

    stream = MagicMock()
    stream.__enter__.side_effect = RuntimeError("microfone indisponível")
    with patch("gideon.voz.ouvido.sd.InputStream", return_value=stream):
        assert ouvinte.gravar_fala(timeout=0.01) is None
    assert ouvinte.gravando is False


def test_tela_de_boot_e_rapida_pulavel_e_independente_de_webgl():
    fonte = Path("frontend/src/components/BootScreen.tsx").read_text(encoding="utf-8")
    assert "2100" in fonte
    assert "Pular" in fonte
    assert "Gideon online" in fonte
    assert "WebGL" not in fonte and "THREE" not in fonte


if __name__ == "__main__":
    test_earcons_sao_curto_suave_e_erro_grave()
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as pasta:
        test_configuracao_de_som_persiste_e_limita_volume(Path(pasta))
    test_reproducao_respeita_desligado_e_volume_com_mocks()
    test_evento_sonoro_e_suprimido_enquanto_microfone_grava()
    test_flag_de_gravacao_e_liberada_apos_falha_de_microfone()
    test_tela_de_boot_e_rapida_pulavel_e_independente_de_webgl()
    print("[OK] Sons procedurais, configuração, captura e boot validados com mocks.")
