"""Testes isolados de configuração, risco e tolerância a falhas MCP."""

from io import StringIO
import time
from unittest.mock import MagicMock, patch

from gideon.executor import EstadoExecucao, ExecutorConfiavel
from gideon.gate import RegistroFerramentas
from gideon.gate import Risco
from gideon.mcp import (
    CONFIG_PADRAO,
    GerenciadorMCP,
    SessaoServidorMCP,
    _risco_ferramenta_mcp,
    _servidor_habilitado,
)


def test_configuracao_padrao_nasce_desativada_e_documentada():
    servidores = CONFIG_PADRAO["mcpServers"]
    assert {"fetch", "sistema_arquivos", "notas"} <= set(servidores)
    for config in servidores.values():
        assert config["enabled"] is False
        assert config["como_ativar"]

    assert servidores["fetch"]["args"] == ["mcp-server-fetch"]
    assert servidores["sistema_arquivos"]["args"][1] == "@modelcontextprotocol/server-filesystem"
    assert servidores["notas"]["args"][1] == "@modelcontextprotocol/server-memory"


def test_enabled_tem_precedencia_e_ativo_antigo_continua_compativel():
    assert _servidor_habilitado({"enabled": True, "ativo": False}) is True
    assert _servidor_habilitado({"enabled": False, "ativo": True}) is False
    assert _servidor_habilitado({"ativo": True}) is True


def test_risco_mcp_libera_leitura_e_confirma_escrita_ou_remocao():
    assert _risco_ferramenta_mcp({"name": "read_text_file"}) is Risco.VERDE
    assert _risco_ferramenta_mcp({"name": "fetch"}) is Risco.VERDE
    assert _risco_ferramenta_mcp({"name": "qualquer_nome", "annotations": {"readOnlyHint": True}}) is Risco.VERDE
    assert _risco_ferramenta_mcp({"name": "read_disfarcado", "annotations": {"readOnlyHint": False}}) is Risco.VERMELHO
    assert _risco_ferramenta_mcp({"name": "read_perigoso", "annotations": {"readOnlyHint": True, "destructiveHint": True}}) is Risco.VERMELHO
    assert _risco_ferramenta_mcp({"name": "write_file"}) is Risco.VERMELHO
    assert _risco_ferramenta_mcp({"name": "delete_entities"}) is Risco.VERMELHO
    assert _risco_ferramenta_mcp({"name": "ferramenta_desconhecida"}) is Risco.VERMELHO


def test_servidor_ausente_nao_impede_carregar_os_demais():
    config = {
        "mcpServers": {
            "ausente": {"command": "inexistente", "args": [], "enabled": True},
            "saudavel": {"command": "servidor-ok", "args": [], "enabled": True},
        }
    }
    sessao_ausente = MagicMock()
    sessao_ausente.iniciar.return_value = False
    sessao_saudavel = MagicMock()
    sessao_saudavel.iniciar.return_value = True
    sessao_saudavel.ferramentas_descobertas = [{"name": "read_note", "inputSchema": {"type": "object"}}]

    with patch("gideon.mcp._garantir_config_mcp", return_value=config), patch(
        "gideon.mcp.SessaoServidorMCP", side_effect=[sessao_ausente, sessao_saudavel]
    ):
        ferramentas = GerenciadorMCP().carregar_e_registrar()

    assert [f.nome for f in ferramentas] == ["mcp_saudavel_read_note"]


def test_escrita_mcp_exige_confirmacao_mesmo_com_auto_amarelo():
    config = {"mcpServers": {"notas": {"command": "npx", "args": [], "enabled": True}}}
    sessao = MagicMock()
    sessao.iniciar.return_value = True
    sessao.ferramentas_descobertas = [
        {"name": "read_note", "inputSchema": {"type": "object"}},
        {"name": "write_note", "inputSchema": {"type": "object"}},
    ]
    sessao.executar_ferramenta.return_value = {
        "sucesso": True,
        "verificado": True,
        "evidencias": {"servidor_mcp": "notas"},
        "mensagem_humana": "ok",
    }

    with patch("gideon.mcp._garantir_config_mcp", return_value=config), patch(
        "gideon.mcp.SessaoServidorMCP", return_value=sessao
    ):
        ferramentas = GerenciadorMCP().carregar_e_registrar()

    catalogo = RegistroFerramentas()
    for ferramenta in ferramentas:
        catalogo.registrar(ferramenta)
    executor = ExecutorConfiavel(catalogo)

    with patch("gideon.executor.gravar_log_execucao"), patch("gideon.executor.registrar_auditoria"):
        leitura = executor.executar("mcp_notas_read_note", {}, auto_amarelo=True)
        escrita = executor.executar("mcp_notas_write_note", {}, auto_amarelo=True)

    assert leitura.estado is EstadoExecucao.SUCCESS
    assert escrita.estado is EstadoExecucao.NEEDS_CONFIRMATION
    assert sessao.executar_ferramenta.call_count == 1


def test_timeout_na_leitura_nao_fica_bloqueado():
    sessao = SessaoServidorMCP("travado", "comando", [])
    processo = MagicMock()
    processo.poll.return_value = None
    processo.stdin = StringIO()
    processo.stdout = StringIO()
    sessao.processo = processo

    inicio = time.monotonic()
    resposta = sessao._enviar_e_aguardar({"jsonrpc": "2.0", "id": 1, "method": "ping"}, timeout_s=0.05)

    assert resposta is None
    assert time.monotonic() - inicio < 0.5


def test_timeout_de_ferramenta_encerra_servidor_travado():
    sessao = SessaoServidorMCP("travado", "comando", [])
    processo = MagicMock()
    processo.poll.return_value = None
    sessao.processo = processo

    with patch.object(sessao, "_enviar_e_aguardar", return_value=None), patch.object(sessao, "encerrar") as encerrar:
        resultado = sessao.executar_ferramenta("read_note", {}, timeout_s=0.01)

    assert resultado["sucesso"] is False
    assert "Tempo esgotado" in resultado["erro"]
    encerrar.assert_called_once_with()


if __name__ == "__main__":
    test_configuracao_padrao_nasce_desativada_e_documentada()
    test_enabled_tem_precedencia_e_ativo_antigo_continua_compativel()
    test_risco_mcp_libera_leitura_e_confirma_escrita_ou_remocao()
    test_servidor_ausente_nao_impede_carregar_os_demais()
    test_escrita_mcp_exige_confirmacao_mesmo_com_auto_amarelo()
    test_timeout_na_leitura_nao_fica_bloqueado()
    test_timeout_de_ferramenta_encerra_servidor_travado()
    print("[OK] Segurança e tolerância a falhas MCP validadas.")
