"""Testes de validação de todas as 6 melhorias avançadas da Gideon."""

import unittest
from pathlib import Path

from gideon.tools.visao import capturar_tela, FERRAMENTAS_VISAO
from gideon.tools.janelas import organizar_janelas, controlar_som_sistema, FERRAMENTAS_JANELAS
from gideon.voz.sons import obter_wav_bytes, tocar_som_ativacao, tocar_som_conclusao, tocar_som_erro
from gideon.vigilante import VigilanteProativo, _tempo_ocioso_segundos
from gideon.mcp import listar_servidores_mcp, FERRAMENTAS_MCP
from gideon.memoria import Memoria
from gideon.persona import obter_prompt_sistema
from gideon.tools import obter_catalogo_ferramentas


class TestesMelhoriasGideon(unittest.TestCase):
    def test_01_visao_computacional(self):
        res = capturar_tela(salvar_arquivo=False)
        self.assertTrue(res["sucesso"])
        self.assertGreater(res["largura"], 0)
        self.assertGreater(res["altura"], 0)
        self.assertEqual(len(FERRAMENTAS_VISAO), 3)

    def test_02_controle_janelas_multimidia(self):
        res_janelas = organizar_janelas("lado_a_lado")
        self.assertIn("sucesso", res_janelas)
        res_som = controlar_som_sistema("mutar", toques=1)
        self.assertTrue(res_som["sucesso"])
        self.assertEqual(len(FERRAMENTAS_JANELAS), 2)

    def test_03_identidade_sonora_earcons(self):
        wav_ativacao = obter_wav_bytes("ativacao")
        self.assertGreater(len(wav_ativacao), 100)
        wav_conclusao = obter_wav_bytes("conclusao")
        self.assertGreater(len(wav_conclusao), 100)
        wav_erro = obter_wav_bytes("erro")
        self.assertGreater(len(wav_erro), 100)

    def test_04_vigilante_proativo(self):
        eventos = []
        vig = VigilanteProativo(notificador=lambda ev: eventos.append(ev))
        self.assertFalse(vig.ativo)
        vig.iniciar()
        self.assertTrue(vig.ativo)
        vig.parar()
        self.assertFalse(vig.ativo)
        ocioso = _tempo_ocioso_segundos()
        self.assertGreaterEqual(ocioso, 0.0)

    def test_05_protocolo_mcp(self):
        status = listar_servidores_mcp()
        self.assertTrue(status["sucesso"])
        self.assertIn("servidores", status)
        self.assertTrue(Path(status["arquivo_config"]).exists())

    def test_06_loop_auto_cura_memoria(self):
        mem = Memoria()
        mem.salvar_licao("Teste de comando", "Arquivo não encontrado", "Usar caminho absoluto")
        licoes = mem.listar_licoes()
        self.assertGreater(len(licoes), 0)
        texto_prompt = mem.formatar_licoes_para_prompt()
        self.assertIn("Teste de comando", texto_prompt)

        prompt_completo = obter_prompt_sistema(lembrancas="", licoes=texto_prompt)
        self.assertIn("LIÇÕES APRENDIDAS E AUTO-CORREÇÕES DO SISTEMA", prompt_completo)
        self.assertIn("Teste de comando", prompt_completo)

    def test_07_catalogo_completo(self):
        cat = obter_catalogo_ferramentas()
        todas = cat.listar_todas()
        self.assertGreaterEqual(len(todas), 49)


if __name__ == "__main__":
    unittest.main()
