"""Bateria de testes de execução real no Windows 10, verificação pós-condição e anti-alucinação da Gideon."""

from __future__ import annotations

import asyncio
from pathlib import Path
import time
import httpx
import psutil

from gideon.executor import EstadoExecucao, ExecutorConfiavel, LOG_EXECUCOES
from gideon.servidor import app, TOKEN_LOCAL
from gideon.tools import obter_catalogo_ferramentas
from gideon.tools.arquivos import criar_arquivo, ler_arquivo, mover_para_lixeira, pesquisar_arquivos
from gideon.tools.sistema import CATALOGO_APPS_WINDOWS, fechar_programa
from gideon.voz.comandos import interpretar_intencao_natural, interpretar_plano_multietapas
from gideon.voz.orquestrador import ModoEscuta, OrquestradorVoz


def _criar_orquestrador_teste() -> OrquestradorVoz:
    orc = object.__new__(OrquestradorVoz)
    orc._catalogo = obter_catalogo_ferramentas()
    orc._executor = ExecutorConfiavel(orc._catalogo)
    orc.ultima_execucao = None
    orc._confirmacao_pendente = None
    orc._parametros_pendentes = {}
    orc._confirmacao_expira_em = 0.0
    orc._em_conversa_ativa = True
    orc._ultimo_contato = time.time()
    orc.modo_escuta = ModoEscuta.CONVERSA_CONTINUA
    orc.duracao_sessao = 30.0
    orc.historico_sessao = []
    orc.contexto_conversa = {}
    orc.callback_ws = None
    orc.memoria = type("MemDummy", (), {
        "processar_comando_explicito": lambda self, _: None,
        "gravar_mensagem": lambda self, *_: None,
    })()
    return orc


def test_proibicao_falsa_confirmacao_e_recuperacao():
    print("[1/5] Testando proibição absoluta de falsa confirmação e recuperação automática...")
    orc = _criar_orquestrador_teste()

    # 1. Tenta abrir um aplicativo que NÃO existe no computador
    resp = orc.processar_fala_local_rapida("Abre o aplicativo SuperAppFantasma999")
    assert resp is not None
    assert orc.ultima_execucao is not None
    assert orc.ultima_execucao.estado == EstadoExecucao.FAILED
    assert orc.ultima_execucao.verificado is False
    assert "Não consegui encontrar" in resp
    assert "Pronto" not in resp and "aberto" not in resp.lower()
    print(f"  -> App inexistente bloqueado com resposta honesta: '{resp}'")

    # 2. Testa sugestão de versão web quando app com fallback_web não está instalado localmente
    CATALOGO_APPS_WINDOWS["app_teste_web"] = {
        "nome_exibicao": "AppTesteWeb",
        "executaveis": ["AppTesteWebInexistente.exe"],
        "processos": ["apptesteweb.exe"],
        "palavras_titulo": ["apptesteweb"],
        "caminhos_extras": [],
        "fallback_web": "https://www.google.com",
    }
    try:
        res_rec = orc._executor.executar("abrir_programa", {"nome": "app_teste_web"})
        assert res_rec.estado == EstadoExecucao.FAILED
        assert res_rec.verificado is False
        assert res_rec.sugestao_recuperacao == "versao_web"
        assert "Quer que eu abra a versão web?" in res_rec.mensagem_humana
        print(f"  -> Recuperação inteligente (sugestão web) validada: '{res_rec.mensagem_humana}'")
    finally:
        CATALOGO_APPS_WINDOWS.pop("app_teste_web", None)


def test_ciclo_completo_janela_e_digitacao_windows():
    print("[2/5] Testando abertura real no Windows, digitação, minimizar/maximizar ('minimiza ele') e fechar...")
    orc = _criar_orquestrador_teste()

    # Garante estado limpo antes de começar
    fechar_programa("bloco de notas")
    time.sleep(0.2)

    # 1. Abre o Bloco de Notas e exige evidência real (PID/HWND)
    resp_abrir = orc.processar_fala_local_rapida("Abre o Bloco de Notas")
    assert resp_abrir is not None
    exec_abrir = orc.ultima_execucao
    assert exec_abrir is not None
    assert exec_abrir.estado == EstadoExecucao.SUCCESS, f"Falha ao abrir Bloco de Notas: {exec_abrir}"
    assert exec_abrir.verificado is True
    pid = exec_abrir.evidencias.get("pid")
    assert pid is not None and psutil.pid_exists(pid), f"PID {pid} não existe no Windows!"
    print(f"  -> Bloco de Notas aberto e verificado (PID={pid}, HWND={exec_abrir.evidencias.get('hwnd')})")

    try:
        # 2. Minimiza usando pronome contextual ("Agora minimiza ele")
        resp_min = orc.processar_fala_local_rapida("Agora minimiza ele")
        assert resp_min is not None
        exec_min = orc.ultima_execucao
        assert exec_min is not None and exec_min.estado == EstadoExecucao.SUCCESS
        assert exec_min.verificado is True
        assert exec_min.evidencias.get("minimizada") is True
        print(f"  -> Minimização contextual ('Agora minimiza ele') verificada via Win32 IsIconic: {exec_min.evidencias}")

        # 3. Maximiza usando pronome contextual ("Maximiza ele")
        resp_max = orc.processar_fala_local_rapida("Maximiza ele")
        assert resp_max is not None
        exec_max = orc.ultima_execucao
        assert exec_max is not None and exec_max.estado == EstadoExecucao.SUCCESS
        assert exec_max.verificado is True
        assert exec_max.evidencias.get("maximizada") is True
        print(f"  -> Maximização contextual ('Maximiza ele') verificada via Win32 IsZoomed: {exec_max.evidencias}")

        # 4. Restaura a janela
        resp_rest = orc.processar_fala_local_rapida("Restaura ele")
        assert resp_rest is not None
        assert orc.ultima_execucao.estado == EstadoExecucao.SUCCESS

    finally:
        # 5. Fecha o Bloco de Notas e verifica encerramento real
        resp_fechar = orc.processar_fala_local_rapida("Fecha o Bloco de Notas")
        assert resp_fechar is not None
        exec_fechar = orc.ultima_execucao
        assert exec_fechar is not None and exec_fechar.estado == EstadoExecucao.SUCCESS
        assert exec_fechar.verificado is True
        print(f"  -> Fechamento real do Bloco de Notas verificado: {exec_fechar.evidencias}")


def test_ciclo_arquivos_e_lixeira_verificado():
    print("[3/5] Testando criação, busca, leitura e envio à Lixeira com verificação pós-condição...")
    orc = _criar_orquestrador_teste()
    nome_arq = "teste_verificado_gideon_exec.txt"
    conteudo_esperado = "Execução real verificada pela Gideon no Windows 10."

    # 1. Cria o arquivo e verifica no disco
    res_criar = orc._executor.executar(
        "criar_arquivo",
        {"caminho": nome_arq, "conteudo": conteudo_esperado, "pasta": "documentos"},
    )
    assert res_criar.estado == EstadoExecucao.SUCCESS
    assert res_criar.verificado is True
    caminho_criado = Path(res_criar.evidencias["caminho"])
    assert caminho_criado.exists() and caminho_criado.is_file()
    print(f"  -> Arquivo criado e verificado no disco: {caminho_criado}")

    # 2. Pesquisa o arquivo pelo comando natural de voz
    resp_busca = orc.processar_fala_local_rapida(f"Procura o arquivo {nome_arq}")
    assert resp_busca is not None
    assert orc.ultima_execucao.estado == EstadoExecucao.SUCCESS
    assert orc.ultima_execucao.evidencias["total_encontrados"] >= 1
    print(f"  -> Busca de arquivo verificada: '{resp_busca}'")

    # 3. Lê o conteúdo e verifica
    res_ler = orc._executor.executar("ler_arquivo", {"caminho": str(caminho_criado)})
    assert res_ler.estado == EstadoExecucao.SUCCESS
    assert res_ler.resultado["conteudo"] == conteudo_esperado

    # 4. Move para a Lixeira do Windows e verifica que saiu do diretório
    res_lixeira = orc._executor.executar("mover_para_lixeira", {"caminho": str(caminho_criado)})
    assert res_lixeira.estado == EstadoExecucao.SUCCESS
    assert res_lixeira.verificado is True
    assert not caminho_criado.exists()
    print("  -> Envio para a Lixeira do Windows verificado (arquivo removido do diretório original): OK")


def test_tarefas_multietapas_verificadas():
    print("[4/5] Testando decomposição e execução verificada de tarefas com múltiplas etapas...")
    # 1. Decomposição de "Abre o navegador e pesquisa sobre inteligência artificial"
    plano_nav = interpretar_plano_multietapas("Abre o navegador e pesquisa sobre inteligência artificial")
    assert plano_nav is not None and len(plano_nav) == 2
    assert plano_nav[0]["acao"] == "abrir_programa"
    assert plano_nav[1]["acao"] == "pesquisar_navegador"
    assert "inteligência artificial" in plano_nav[1]["parametros"]["consulta"].lower()
    print(f"  -> Plano multietapas de navegador decomposto: {[p['acao'] for p in plano_nav]}")

    # 2. Execução real multietapas: "Abre o Bloco de Notas e verifica o consumo de memória"
    orc = _criar_orquestrador_teste()
    try:
        resp_multi = orc.processar_fala_local_rapida("Abre o Bloco de Notas e verifica o consumo de memória")
        assert resp_multi is not None
        assert orc.ultima_origem_resposta == "plano_multietapas"
        assert "Bloco de Notas aberto" in resp_multi
        assert "memória RAM" in resp_multi
        print(f"  -> Plano multietapas executado e verificado: '{resp_multi}'")
    finally:
        fechar_programa("bloco de notas")


async def test_log_estruturado_execucoes_e_api():
    print("[5/5] Testando persistência de auditoria estruturada (dados/execucoes.jsonl e API)...")
    assert LOG_EXECUCOES.exists(), "Arquivo dados/execucoes.jsonl deveria existir!"

    transport = httpx.ASGITransport(app=app)
    headers = {
        "x-gideon-token": TOKEN_LOCAL,
        "x-gideon-csrf": "1",
        "origin": "http://127.0.0.1:8000",
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        res = await client.get("/api/execucoes/historico?limite=10", headers=headers)
        assert res.status_code == 200
        dados = res.json()
        assert dados["status"] == "ok"
        assert len(dados["execucoes"]) >= 3
        ultima = dados["execucoes"][-1]
        for campo in ("id_acao", "ferramenta", "parametros", "estado", "verificado", "evidencias", "duracao_ms"):
            assert campo in ultima, f"Campo '{campo}' ausente no log estruturado!"
        print(f"  -> Último registro estruturado validado via API: {ultima['id_acao']} ({ultima['ferramenta']} -> {ultima['estado']})")


async def principal():
    test_proibicao_falsa_confirmacao_e_recuperacao()
    test_ciclo_completo_janela_e_digitacao_windows()
    test_ciclo_arquivos_e_lixeira_verificado()
    test_tarefas_multietapas_verificadas()
    await test_log_estruturado_execucoes_e_api()
    print("\n=======================================================")
    print("  EXECUCAO REAL E VERIFICACAO WINDOWS 10 APROVADAS!    ")
    print("=======================================================\n")


if __name__ == "__main__":
    asyncio.run(principal())
