"""Testes isolados da interrupção da fala por wake word, sem microfone ou caixa de som."""

import threading
from unittest.mock import MagicMock, patch

import numpy as np

from gideon import configuracao
from gideon.voz.fala import SintetizadorVoz
from gideon.voz.orquestrador import OrquestradorVoz


def _orquestrador_minimo(texto: str, tem_wake: bool = True) -> OrquestradorVoz:
    orquestrador = object.__new__(OrquestradorVoz)
    orquestrador.sintetizador = MagicMock(barge_in_ativo=True, falando=True)
    orquestrador.ouvinte = MagicMock()
    orquestrador.ouvinte.transcrever_audio.return_value = texto
    orquestrador.ouvinte.extrair_wake_word.return_value = (tem_wake, "")
    orquestrador._cancelar_geracao = threading.Event()
    orquestrador._em_conversa_ativa = False
    orquestrador._ultimo_contato = 0.0
    orquestrador._evento_interno = MagicMock()
    return orquestrador


def test_wake_word_durante_fala_cancela_geracao_e_abre_escuta():
    orquestrador = _orquestrador_minimo("Gideon", tem_wake=True)

    confirmou = orquestrador._detectar_interrupcao_por_voz(np.ones(1600, dtype=np.float32))

    assert confirmou is True
    assert orquestrador._cancelar_geracao.is_set()
    assert orquestrador._em_conversa_ativa is True
    orquestrador._evento_interno.assert_called_once_with({"tipo": "interrupcao_voz", "texto": "Gideon"})


def test_voz_generica_e_opcao_desligada_nao_interrompem():
    voz_generica = _orquestrador_minimo("conversa ao fundo", tem_wake=False)
    assert voz_generica._detectar_interrupcao_por_voz(np.ones(1600, dtype=np.float32)) is False
    assert not voz_generica._cancelar_geracao.is_set()

    desligado = _orquestrador_minimo("Gideon", tem_wake=True)
    desligado.sintetizador.barge_in_ativo = False
    assert desligado._detectar_interrupcao_por_voz(np.ones(1600, dtype=np.float32)) is False
    desligado.ouvinte.transcrever_audio.assert_not_called()


def test_interrupcao_manual_tambem_sinaliza_cancelamento():
    orquestrador = _orquestrador_minimo("", tem_wake=False)
    orquestrador.sintetizador.interromper.return_value = True

    assert orquestrador.interromper_fala() is True
    assert orquestrador._cancelar_geracao.is_set()


def test_cancelamento_descarta_resposta_parcial_do_stream():
    orquestrador = object.__new__(OrquestradorVoz)
    orquestrador._cancelar_geracao = threading.Event()
    orquestrador.contexto_conversa = {}
    orquestrador.historico_sessao = []
    orquestrador.ultimo_llm_ttft_ms = 0.0
    orquestrador.memoria = MagicMock()
    orquestrador.memoria.recuperar_lembrancas_para_prompt.return_value = ""
    orquestrador._evento_interno = MagicMock()
    orquestrador._registrar_turno_sessao = MagicMock()

    class StreamFalso:
        def __init__(self):
            self.eventos = iter([
                {"tipo": "chunk", "texto": "Primeira frase. Segunda frase. "},
                {"tipo": "chunk", "texto": "Terceira frase."},
            ])
            self.fechado = False

        def __iter__(self):
            return self

        def __next__(self):
            return next(self.eventos)

        def close(self):
            self.fechado = True

    stream = StreamFalso()
    orquestrador.cerebro = MagicMock()
    orquestrador.cerebro.pensar_stream.return_value = stream
    orquestrador.sintetizador = MagicMock(foi_interrompida=False)

    def consumir_e_interromper(sentencas):
        iterador = iter(sentencas)
        assert next(iterador) == "Primeira frase."
        orquestrador._cancelar_geracao.set()
        assert list(iterador) == []
        return False

    orquestrador.sintetizador.falar_stream.side_effect = consumir_e_interromper

    orquestrador._responder_com_llm_streaming("pergunta")

    assert stream.fechado is True
    orquestrador.memoria.gravar_mensagem.assert_not_called()
    orquestrador._registrar_turno_sessao.assert_not_called()


def test_estado_final_da_fala_interrompida_e_ouvindo():
    sintetizador = object.__new__(SintetizadorVoz)
    sintetizador._lock_fala = threading.Lock()
    sintetizador._evento_interromper = threading.Event()
    sintetizador._pockettts = object()
    sintetizador._edge_disponivel = False
    sintetizador.voz_id = "teste"
    sintetizador._falando = False
    sintetizador.rms_saida_atual = 0.0
    sintetizador.foi_interrompida = False
    sintetizador.audio_barge_in = None
    eventos: list[dict] = []
    sintetizador.callback_evento = eventos.append
    sintetizador.sintetizar_para_memoria = MagicMock(
        return_value=(np.ones(100, dtype=np.float32), 16000, True)
    )

    def interromper_reproducao(_amostras, _taxa):
        sintetizador.foi_interrompida = True
        sintetizador._barge_in_confirmado = True
        sintetizador._evento_interromper.set()

    sintetizador._reproduzir_audio = interromper_reproducao

    assert sintetizador.falar("Resposta em andamento") is False
    assert eventos[-2] == {"tipo": "fala_fim", "interrompida_por_voz": True}
    assert eventos[-1] == {"tipo": "estado_ia", "estado": "listening"}
    assert sintetizador.falando is False


def test_preferencia_de_interrupcao_e_persistente(tmp_path):
    arquivo = tmp_path / "config.json"
    with patch.object(configuracao, "CONFIG_ARQUIVO", arquivo):
        assert configuracao.obter_interrupcao_voz_ativa() is True
        assert configuracao.definir_interrupcao_voz_ativa(False) is False
        assert configuracao.obter_interrupcao_voz_ativa() is False
        assert configuracao.carregar_configuracao()["idioma"] == "pt-BR"


if __name__ == "__main__":
    test_wake_word_durante_fala_cancela_geracao_e_abre_escuta()
    test_voz_generica_e_opcao_desligada_nao_interrompem()
    test_interrupcao_manual_tambem_sinaliza_cancelamento()
    test_cancelamento_descarta_resposta_parcial_do_stream()
    test_estado_final_da_fala_interrompida_e_ouvindo()
    from tempfile import TemporaryDirectory
    from pathlib import Path

    with TemporaryDirectory() as pasta:
        test_preferencia_de_interrupcao_e_persistente(Path(pasta))
    print("[OK] Interrupção por voz e transições de estado validadas com mocks.")
