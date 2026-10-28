"""Catálogo centralizado de ferramentas da Gideon."""

from gideon.gate import RegistroFerramentas
from gideon.tools.sistema import FERRAMENTAS_SISTEMA
from gideon.tools.arquivos import FERRAMENTAS_ARQUIVOS
from gideon.tools.automacoes_tools import FERRAMENTAS_INTELIGENCIA
from gideon.tools.visao import FERRAMENTAS_VISAO
from gideon.tools.janelas import FERRAMENTAS_JANELAS
from gideon.mcp import FERRAMENTAS_MCP, obter_gerenciador_mcp

_registro_global = None


def obter_catalogo_ferramentas() -> RegistroFerramentas:
    """Retorna a instância única do registro com todas as ferramentas carregadas."""
    global _registro_global
    if _registro_global is None:
        _registro_global = RegistroFerramentas()
        for f in FERRAMENTAS_SISTEMA:
            _registro_global.registrar(f)
        for f in FERRAMENTAS_ARQUIVOS:
            _registro_global.registrar(f)
        for f in FERRAMENTAS_INTELIGENCIA:
            _registro_global.registrar(f)
        for f in FERRAMENTAS_VISAO:
            _registro_global.registrar(f)
        for f in FERRAMENTAS_JANELAS:
            _registro_global.registrar(f)
        for f in FERRAMENTAS_MCP:
            _registro_global.registrar(f)

        # Registra ferramentas dinâmicas de servidores MCP ativos
        try:
            mcp_tools = obter_gerenciador_mcp().carregar_e_registrar()
            for f in mcp_tools:
                _registro_global.registrar(f)
        except Exception:
            pass

    return _registro_global
