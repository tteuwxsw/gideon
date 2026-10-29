"""Testes isolados dos avisos, visão sob demanda e fallback Ollama."""

import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib import error as urllib_error

import numpy as np
from PIL import Image

from gideon import configuracao
from gideon.cerebro import Cerebro
from gideon.gate import Risco
from gideon.tools import visao
from gideon.vigilante import VigilanteProativo, _em_horario_silencioso, _internet_disponivel
from gideon.voz.comandos import detectar_modo_atividade, interpretar_intencao_natural


def _config_avisos(**alteracoes):
    base = configuracao.obter_configuracao_avisos()
    base.update(alteracoes)
    base["cooldown_minutos"] = {chave: 1 for chave in base["cooldown_minutos"]}
    return base


def test_configuracao_tem_chave_individual_e_silencio_cruza_meia_noite():
    cfg = configuracao.obter_configuracao_avisos()
    for chave in ("bateria", "disco", "temperatura", "ram", "cpu", "internet", "pausa", "compromissos"):
        assert isinstance(cfg[chave], bool)
    from datetime import datetime

    assert _em_horario_silencioso(cfg, datetime(2026, 1, 1, 23, 0)) is True
    assert _em_horario_silencioso(cfg, datetime(2026, 1, 1, 12, 0)) is False


def test_vigilante_detecta_recursos_com_cooldown_e_sem_servico_externo():
    eventos = []
    falas = []
    vigilante = VigilanteProativo(eventos.append, falas.append)
    vigilante._inicio_uso_continuo = 1.0
    bateria = SimpleNamespace(percent=12.0, power_plugged=False)
    memoria = SimpleNamespace(percent=96.0)
    disco = SimpleNamespace(free=5 * 1024 ** 3, used=95, total=100)
    temperaturas = {"coretemp": [SimpleNamespace(current=91.0)]}
    cfg = _config_avisos(pausa_minutos=15, horario_silencioso_inicio="23:59", horario_silencioso_fim="00:00")

    with patch("gideon.vigilante.obter_configuracao_avisos", return_value=cfg), patch(
        "gideon.vigilante.obter_modo_atividade", return_value="normal"
    ), patch("gideon.vigilante.obter_modo_personalidade", return_value="direta"), patch(
        "gideon.vigilante._tempo_ocioso_segundos", return_value=0.0
    ), patch("gideon.vigilante._internet_disponivel", return_value=False), patch(
        "gideon.vigilante.time.time", return_value=10_000_000.0
    ), patch("gideon.vigilante.psutil.sensors_battery", return_value=bateria), patch(
        "gideon.vigilante.psutil.virtual_memory", return_value=memoria
    ), patch("gideon.vigilante.psutil.cpu_percent", return_value=99.0), patch(
        "gideon.vigilante.psutil.sensors_temperatures", return_value=temperaturas
    ), patch("gideon.vigilante.shutil.disk_usage", return_value=disco), patch.object(
        vigilante, "_verificar_lembretes"
    ):
        vigilante._executar_ciclo()
        vigilante._executar_ciclo()
        vigilante._executar_ciclo()
        vigilante._executar_ciclo()

    tipos = {evento["subtipo"] for evento in eventos}
    assert {"bateria_baixa", "disco_cheio", "temperatura_alta", "ram_alta", "cpu_alta", "internet_caindo", "pausa_uso"} <= tipos
    assert len([e for e in eventos if e["subtipo"] == "bateria_baixa"]) == 1
    assert falas


def test_foco_cinema_e_horario_silencioso_bloqueiam_so_a_fala():
    eventos = []
    falas = []
    vigilante = VigilanteProativo(eventos.append, falas.append)
    cfg = _config_avisos(horario_silencioso_inicio="00:00", horario_silencioso_fim="23:59")
    with patch("gideon.vigilante.obter_modo_atividade", return_value="foco"), patch(
        "gideon.vigilante.obter_modo_personalidade", return_value="padrao"
    ):
        vigilante._disparar_alerta("teste", "Mensagem curta.", cfg)
    assert len(eventos) == 1
    assert falas == []
    assert detectar_modo_atividade("ativar modo cinema") == "cinema"
    assert detectar_modo_atividade("sair do modo foco") == "normal"


def test_checagem_de_internet_faz_apenas_handshake_curto():
    conexao = MagicMock()
    conexao.__enter__.return_value = conexao
    with patch("gideon.vigilante.socket.create_connection", return_value=conexao) as conectar:
        assert _internet_disponivel() is True
    conectar.assert_called_once_with(("1.1.1.1", 53), timeout=1.5)


def test_lembrete_local_proximo_gera_aviso_sem_agenda_externa():
    eventos = []
    vigilante = VigilanteProativo(eventos.append, None)
    momento = __import__("datetime").datetime(2026, 1, 1, 10, 0)
    item = {"id": "1", "nome": "Lembrete: reunião", "ativa": True, "gatilho": {"tipo": "uma_vez"}}
    cfg = _config_avisos()
    with patch("gideon.automacoes.listar", return_value=[item]), patch(
        "gideon.automacoes.agora", return_value=momento
    ), patch("gideon.automacoes.proxima_execucao", return_value=momento + __import__("datetime").timedelta(minutes=10)), patch(
        "gideon.vigilante.obter_modo_personalidade", return_value="padrao"
    ), patch("gideon.vigilante.obter_modo_atividade", return_value="normal"):
        vigilante._verificar_lembretes(cfg, 10_000_000.0)
    assert eventos[0]["subtipo"] == "compromisso_proximo"
    assert "10 minutos" in eventos[0]["mensagem"]


def test_comandos_visuais_sao_explicitos_e_override_e_vermelho():
    for frase in ("o que tem na minha tela?", "explica esse erro", "resume o que estou lendo"):
        intencao = interpretar_intencao_natural(frase)
        assert intencao and intencao["acao"] == "analisar_tela"
        assert intencao["parametros"]["permitir_conteudo_sensivel"] is False
    assert interpretar_intencao_natural("qual janela está ativa")["acao"] == "inspecionar_contexto_tela"
    override = interpretar_intencao_natural("analise mesmo assim")
    assert override["parametros"]["permitir_conteudo_sensivel"] is True
    ferramenta = next(f for f in visao.FERRAMENTAS_VISAO if f.nome == "analisar_tela")
    assert ferramenta.risco_para(override["parametros"]) is Risco.VERMELHO
    assert ferramenta.expor_ao_modelo is False


def test_tela_sensivel_nao_e_enviada_sem_confirmacao():
    imagem = Image.new("RGB", (100, 80), "black")
    with patch("gideon.tools.visao.capturar_tela_imagem", return_value=imagem), patch(
        "gideon.tools.visao._parece_conteudo_sensivel", return_value=True
    ), patch("google.genai.Client") as cliente:
        resultado = visao.analisar_tela("explique")
    assert resultado["sucesso"] is False
    assert resultado["requer_confirmacao"] is True
    cliente.assert_not_called()


def test_wayland_usa_grim_e_falha_amigavel():
    buffer = io.BytesIO()
    Image.new("RGB", (20, 10), "blue").save(buffer, format="PNG")
    processo = SimpleNamespace(stdout=buffer.getvalue())
    with patch.dict("os.environ", {"XDG_SESSION_TYPE": "wayland"}), patch(
        "gideon.tools.visao.shutil.which", side_effect=lambda nome: "/usr/bin/grim" if nome == "grim" else None
    ), patch("gideon.tools.visao.subprocess.run", return_value=processo):
        imagem = visao.capturar_tela_imagem()
    assert imagem.size == (20, 10)

    with patch.dict("os.environ", {"XDG_SESSION_TYPE": "wayland"}), patch(
        "gideon.tools.visao.shutil.which", return_value=None
    ), patch("gideon.tools.visao.ImageGrab.grab", side_effect=OSError("sem portal")):
        resultado = visao.capturar_tela(salvar_arquivo=False)
    assert resultado["sucesso"] is False
    assert "Wayland" in resultado["mensagem_humana"]


def test_ollama_local_reutiliza_eventos_e_recebe_memoria_sem_ferramentas():
    linhas = [
        json.dumps({"message": {"content": "Resposta local."}, "done": False}).encode() + b"\n",
        json.dumps({"message": {"content": ""}, "done": True, "prompt_eval_count": 12, "eval_count": 4}).encode() + b"\n",
    ]

    class RespostaFalsa:
        def __enter__(self): return iter(linhas)
        def __exit__(self, *args): return False

    requisicoes = []
    with patch("gideon.cerebro.obter_modelo_ollama", return_value="modelo-local"), patch(
        "gideon.cerebro.obter_prompt_sistema", return_value="PROMPT COM MEMÓRIA"
    ), patch("gideon.cerebro.urllib_request.urlopen", side_effect=lambda req, timeout: requisicoes.append(req) or RespostaFalsa()):
        eventos = list(Cerebro()._pensar_ollama([{"role": "user", "content": "oi"}], "segredo local", ""))

    payload = json.loads(requisicoes[0].data.decode())
    assert requisicoes[0].full_url == "http://127.0.0.1:11434/api/chat"
    assert payload["messages"][0]["content"] == "PROMPT COM MEMÓRIA"
    assert "tools" not in payload
    assert eventos[0] == {"tipo": "chunk", "texto": "Estou em modo offline. "}
    assert eventos[-1]["tipo"] == "fim"
    assert eventos[-1]["modelo"] == "ollama/modelo-local"
    assert eventos[-1]["custo_estimado"] == 0.0
    assert not any(evento["tipo"] == "ferramenta" for evento in eventos)


def test_ollama_ausente_falha_com_mensagem_amigavel():
    with patch("gideon.cerebro.urllib_request.urlopen", side_effect=urllib_error.URLError("recusado")):
        eventos = list(Cerebro()._pensar_ollama([{"role": "user", "content": "oi"}], "", ""))
    assert eventos == [{
        "tipo": "erro",
        "mensagem": "Sem internet e o Ollama local não está instalado ou não está rodando em localhost.",
    }]


def test_cerebro_aciona_terceiro_fallback_em_erro_de_conexao():
    cerebro = Cerebro()
    cliente = MagicMock()
    cliente.models.generate_content_stream.side_effect = ConnectionError("connection refused")
    cerebro._cliente = cliente
    eventos_locais = iter([
        {"tipo": "chunk", "texto": "Estou em modo offline. "},
        {"tipo": "fim", "prompt_tokens": 1, "resposta_tokens": 1, "total_tokens": 2, "custo_estimado": 0.0, "modelo": "ollama/local"},
    ])
    with patch("gideon.cerebro.gasto_diario_atual", return_value=0.0), patch.object(
        cerebro, "_pensar_ollama", return_value=eventos_locais
    ) as fallback:
        eventos = list(cerebro.pensar_stream([{"role": "user", "content": "oi"}]))
    fallback.assert_called_once()
    assert eventos[-1]["modelo"] == "ollama/local"


if __name__ == "__main__":
    test_configuracao_tem_chave_individual_e_silencio_cruza_meia_noite()
    test_vigilante_detecta_recursos_com_cooldown_e_sem_servico_externo()
    test_foco_cinema_e_horario_silencioso_bloqueiam_so_a_fala()
    test_checagem_de_internet_faz_apenas_handshake_curto()
    test_lembrete_local_proximo_gera_aviso_sem_agenda_externa()
    test_comandos_visuais_sao_explicitos_e_override_e_vermelho()
    test_tela_sensivel_nao_e_enviada_sem_confirmacao()
    test_wayland_usa_grim_e_falha_amigavel()
    test_ollama_local_reutiliza_eventos_e_recebe_memoria_sem_ferramentas()
    test_ollama_ausente_falha_com_mensagem_amigavel()
    test_cerebro_aciona_terceiro_fallback_em_erro_de_conexao()
    print("[OK] Avisos, visão sob demanda e Ollama validados com mocks.")
