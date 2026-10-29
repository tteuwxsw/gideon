"""Validação das habilidades embutidas adicionadas em 2026-10-29."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from gideon import caminhos, habilidades
from gideon.tools import obter_catalogo_ferramentas


NOMES = {"modo-foco", "modo-cinema", "resumo-do-dia", "estudos", "dev"}


def test_novas_habilidades_tem_formato_gatilhos_e_desfazer():
    with TemporaryDirectory() as pasta_usuario, patch.object(
        caminhos, "HABILIDADES_USUARIO_DIR", Path(pasta_usuario)
    ):
        encontradas = {h["nome"]: h for h in habilidades.listar() if h["nome"] in NOMES}

    assert set(encontradas) == NOMES
    for habilidade in encontradas.values():
        assert habilidade["descricao"]
        assert habilidade["quando_usar"]
        assert habilidade["risco_maximo"] in {"V", "A", "R"}
        assert "Gatilhos de voz" in habilidade["instrucoes"]
        assert "Como desfazer" in habilidade["instrucoes"]


def test_novas_habilidades_usam_apenas_ferramentas_existentes():
    catalogo = obter_catalogo_ferramentas()
    nomes_catalogo = {f.nome for f in catalogo.listar_todas()}

    with TemporaryDirectory() as pasta_usuario, patch.object(
        caminhos, "HABILIDADES_USUARIO_DIR", Path(pasta_usuario)
    ):
        novas = [h for h in habilidades.listar() if h["nome"] in NOMES]

    declaradas = {ferramenta for habilidade in novas for ferramenta in habilidade["ferramentas"]}
    assert declaradas <= nomes_catalogo
    assert "ajustar_brilho" not in declaradas
    assert "pausar_notificacoes" not in declaradas


if __name__ == "__main__":
    test_novas_habilidades_tem_formato_gatilhos_e_desfazer()
    test_novas_habilidades_usam_apenas_ferramentas_existentes()
    print("[OK] Novas habilidades validadas.")
