"""Catálogo centralizado de ferramentas da Gideon."""

from gideon.gate import RegistroFerramentas
from gideon.tools.sistema import FERRAMENTAS_SISTEMA
from gideon.tools.arquivos import FERRAMENTAS_ARQUIVOS

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
    return _registro_global
