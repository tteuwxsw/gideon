"""Testes dos modos de personalidade, persistência e comandos locais de voz."""

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from gideon import configuracao, persona
from gideon.voz.comandos import detectar_modo_personalidade, eh_pergunta_modo_personalidade
from gideon.voz.orquestrador import OrquestradorVoz


def test_comandos_de_voz_reconhecem_os_quatro_modos_e_consulta():
    assert detectar_modo_personalidade("Gideon, modo padrão") == "padrao"
    assert detectar_modo_personalidade("modo formal") == "formal"
    assert detectar_modo_personalidade("modo direta") == "direta"
    assert detectar_modo_personalidade("ative o modo sarcástica") == "sarcastica"
    assert detectar_modo_personalidade("modo de escuta livre") is None
    assert eh_pergunta_modo_personalidade("qual seu modo?") is True
    assert eh_pergunta_modo_personalidade("qual seu nome?") is False


def test_modo_persiste_e_configuracao_invalida_volta_ao_padrao():
    with TemporaryDirectory() as pasta:
        arquivo = Path(pasta) / "config.json"
        with patch.object(configuracao, "CONFIG_ARQUIVO", arquivo):
            assert configuracao.obter_modo_personalidade() == "padrao"
            assert configuracao.definir_modo_personalidade("formal") == "formal"
            assert configuracao.obter_modo_personalidade() == "formal"

            dados = configuracao.carregar_configuracao()
            dados["modo_personalidade"] = "inexistente"
            configuracao.salvar_configuracao(dados)
            assert configuracao.obter_modo_personalidade() == "padrao"


def test_modo_padrao_preserva_literalmente_o_estilo_atual():
    esperado = """1. Você se comunica com elegância, calma, clareza cirúrgica e calorosa serenidade, como uma pessoa presente — nunca como um robô lendo um relatório.
2. Na voz, mantenha respostas curtas e objetivas (1 a 3 frases fluidas), com pontuação própria para pausas naturais, contrações comuns do português e sem listas ou markdown. No chat, use formatação clara.
3. Seus olhos e ouvidos estão atentos ao computador: você inspeciona telas, organiza janelas, controla som e executa ações reais no Linux (Zorin OS)."""
    with patch("gideon.persona.obter_modo_personalidade", return_value="padrao"):
        prompt = persona.obter_prompt_sistema()
    assert esperado in prompt


def test_modos_trocam_so_bloco_de_estilo_e_mantem_seguranca():
    prompts = {}
    instante = datetime(2026, 10, 29, 12, 0)
    with patch("gideon.persona.datetime") as datetime_mock, patch(
        "gideon.persona.perfil.para_prompt", return_value="perfil"
    ), patch("gideon.persona.habilidades.indice_para_prompt", return_value="habilidades"):
        datetime_mock.now.return_value = instante
        for modo in ("padrao", "formal", "direta", "sarcastica"):
            with patch("gideon.persona.obter_modo_personalidade", return_value=modo):
                prompts[modo] = persona.obter_prompt_sistema(lembrancas="lembranças", licoes="lições")

    marcador_estilo = "  POSTURA E COMUNICAÇÃO DE VOZ E CHAT"
    marcador_seguranca = "  DIRETRIZES OPERACIONAIS E ÉTICA"
    prefixos = {texto.split(marcador_estilo, 1)[0] for texto in prompts.values()}
    blocos_seguros = {texto.split(marcador_seguranca, 1)[1] for texto in prompts.values()}

    assert len(prefixos) == 1
    assert len(blocos_seguros) == 1
    assert len(set(prompts.values())) == 4
    assert all("1 a 3 frases" in texto for texto in prompts.values())
    assert "sem ofender" in prompts["sarcastica"]


def test_orquestrador_troca_e_informa_modo_sem_chamar_llm():
    orquestrador = object.__new__(OrquestradorVoz)
    orquestrador._evento_interno = MagicMock()

    with patch("gideon.voz.orquestrador.definir_modo_personalidade", return_value="direta") as definir:
        resposta = orquestrador.processar_fala_local_rapida("modo direta")
    assert resposta == "Modo direta ativado."
    definir.assert_called_once_with("direta")
    assert orquestrador.ultima_origem_resposta == "comando_local"

    with patch("gideon.voz.orquestrador.obter_modo_personalidade", return_value="sarcastica"):
        resposta_consulta = orquestrador.processar_fala_local_rapida("qual seu modo?")
    assert resposta_consulta == "Meu modo atual é sarcástica."


if __name__ == "__main__":
    test_comandos_de_voz_reconhecem_os_quatro_modos_e_consulta()
    test_modo_persiste_e_configuracao_invalida_volta_ao_padrao()
    test_modo_padrao_preserva_literalmente_o_estilo_atual()
    test_modos_trocam_so_bloco_de_estilo_e_mantem_seguranca()
    test_orquestrador_troca_e_informa_modo_sem_chamar_llm()
    print("[OK] Modos de personalidade e comandos de voz validados com mocks.")
