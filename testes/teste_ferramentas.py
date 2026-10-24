"""Bateria de testes do Portão de Segurança e Ferramentas da Gideon (Fase 4)."""

import json
from pathlib import Path
from gideon.gate import RegistroFerramentas, Risco, LOG_AUDITORIA, obter_historico_auditoria
from gideon.tools.sistema import obter_status_pc, listar_programas_usuario, FERRAMENTAS_SISTEMA
from gideon.tools.arquivos import ler_arquivo, listar_arquivos, FERRAMENTAS_ARQUIVOS
from gideon.tools import obter_catalogo_ferramentas


def test_catalogo_e_portao():
    print("[1/4] Testando catálogo de ferramentas e portão de segurança...")
    catalogo = obter_catalogo_ferramentas()
    todas = catalogo.listar_todas()
    assert len(todas) >= 5, f"Esperava pelo menos 5 ferramentas, encontrou {len(todas)}"
    nomes = [f.nome for f in todas]
    assert "obter_status_pc" in nomes
    assert "listar_programas_usuario" in nomes
    assert "listar_arquivos" in nomes
    assert "ler_arquivo" in nomes
    print(f"  -> Catálogo contém {len(todas)} ferramentas validadas.")


def test_ferramentas_sistema():
    print("[2/4] Testando ferramentas reais do sistema Windows...")
    # 1. Status do PC
    status = obter_status_pc()
    assert "cpu_percent" in status
    assert "memoria_ram" in status
    assert "disco_c" in status
    print(f"  -> Telemetria do PC: CPU {status['cpu_percent']}, RAM {status['memoria_ram']['percentual']}, Disco Livre {status['disco_c']['livre_gb']}")

    # 2. Programas do usuário
    programas = listar_programas_usuario()
    assert isinstance(programas, list)
    print(f"  -> Programas ativos detectados ({len(programas)}): {programas[:6]}...")


def test_segurança_sandbox_arquivos():
    print("[3/4] Testando proteção de segurança de arquivos sensíveis...")
    # 1. Tentativa de ler arquivo protegido (.env)
    res_bloqueado = ler_arquivo(".env")
    assert "erro" in res_bloqueado
    assert "Acesso negado" in res_bloqueado["erro"]
    print("  -> Bloqueio de arquivos com credenciais (.env): OK")

    # 2. Leitura segura de arquivo do projeto (README.md)
    res_seguro = ler_arquivo("README.md")
    assert "caminho" in res_seguro
    print("  -> Leitura de arquivo permitido: OK")


def test_auditoria_portao():
    print("[4/4] Testando gravação no log de auditoria...")
    catalogo = obter_catalogo_ferramentas()

    # Executa ferramenta pelo portão
    res = catalogo.executar("obter_status_pc", {})
    assert res["ok"] is True

    # Verifica se o log foi gravado
    historico = obter_historico_auditoria(limite=5)
    assert len(historico) > 0
    ultimo = historico[-1]
    assert ultimo["ferramenta"] == "obter_status_pc"
    assert ultimo["risco"] == "V"
    assert ultimo["resultado"] == "ok"
    print(f"  -> Registro de auditoria gravado com sucesso em dados/auditoria.jsonl: {ultimo}")


def principal():
    test_catalogo_e_portao()
    test_ferramentas_sistema()
    test_segurança_sandbox_arquivos()
    test_auditoria_portao()
    print("\n=======================================================")
    print("  PORTÃO DE FERRAMENTAS DA GIDEON APROVADO COM SUCESSO!")
    print("=======================================================\n")


if __name__ == "__main__":
    principal()
