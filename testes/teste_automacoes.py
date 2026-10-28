"""Bateria de testes de Automações, Habilidades, Perfil e Lembretes da Gideon (Seção 13, 15 e 18)."""

from datetime import datetime, timedelta
from pathlib import Path
import json

from gideon import automacoes, habilidades, perfil, permissoes
from gideon.gate import PARADO, ativar_parada_emergencia, retomar_execucao
from gideon.tools.automacoes_tools import (
    automacao_criar,
    automacao_listar,
    automacao_obter,
    automacao_testar,
    automacao_ligar,
    automacao_desligar,
    automacao_apagar,
    criar_lembrete,
    habilidade_listar,
    habilidade_ler,
    habilidade_criar,
    perfil_ler,
    perfil_adicionar_regra,
    perfil_remover_regra,
)


def test_perfil_vivo():
    print("[1/5] Testando Perfil Vivo do Henry (Seção 15)...")
    res_add = perfil_adicionar_regra("Preferências", "Prefere respostas bem concisas e diretas")
    assert res_add["sucesso"] is True
    assert "Preferências" in res_add["secao"]

    # Lê o perfil
    conteudo = perfil.ler()
    assert "Prefere respostas bem concisas e diretas" in conteudo
    prompt_txt = perfil.para_prompt()
    assert "Prefere respostas bem concisas e diretas" in prompt_txt

    # Remove a regra de teste
    res_rem = perfil_remover_regra("bem concisas e diretas")
    assert res_rem["sucesso"] is True
    conteudo_pos = perfil.ler()
    assert "Prefere respostas bem concisas e diretas" not in conteudo_pos
    print("  -> Perfil vivo (adicionar, formatar para prompt e remover): OK")


def test_habilidades():
    print("[2/5] Testando Habilidades como arquivos (Seção 4 e 15)...")
    # 1. Lista habilidades embutidas
    habs = habilidade_listar()
    assert habs["sucesso"] is True
    nomes = [h["nome"] for h in habs["habilidades"]]
    assert "bom-dia" in nomes
    assert "criar-automacao" in nomes
    assert "faxina-pastas" in nomes
    assert "lembretes" in nomes
    print(f"  -> Habilidades embutidas detectadas ({len(nomes)}): {nomes}")

    # 2. Lê uma habilidade
    hab_bom_dia = habilidade_ler("bom-dia")
    assert hab_bom_dia["sucesso"] is True
    assert "Rotina Matinal" in hab_bom_dia["mensagem_humana"]

    # 3. Cria uma habilidade nova do Henry
    nova = habilidade_criar(
        nome="teste-rotina-noite",
        descricao="Rotina de encerramento do dia",
        instrucoes="1. Verificar telemetria do PC.\n2. Minimizar janelas abertas.\n3. Desejar boa noite ao Henry.",
        quando_usar="Henry pedir para encerrar o expediente",
    )
    assert nova["sucesso"] is True
    hab_lida = habilidade_ler("teste-rotina-noite")
    assert hab_lida["sucesso"] is True
    assert hab_lida["habilidade"]["origem"] == "henry"

    # Limpa arquivo temporário de teste
    caminho = Path(nova["evidencias"]["caminho"])
    if caminho.exists():
        caminho.unlink()
    print("  -> Criação, leitura e scanner de habilidades: OK")


def test_automacao_ciclo_e_seguranca():
    print("[3/5] Testando Criação de Automações e Portão de Segurança (Seção 18)...")
    # 1. Cria uma automação válida
    res_criacao = automacao_criar(
        nome="Rotina Matinal de Teste",
        gatilho={"tipo": "horario", "hora": "08:00", "dias": ["seg", "ter", "qua", "qui", "sex"]},
        passos=[
            {"tipo": "ferramenta", "ferramenta": "obter_status_pc", "salvar_como": "pc"},
            {"tipo": "avisar", "mensagem": "Bom dia Henry! PC verificado: {{pc}}", "falar": False},
        ],
        descricao="Automação de teste da rotina matinal",
    )
    assert res_criacao["sucesso"] is True
    id_auto = res_criacao["id"]
    assert res_criacao["automacao"]["ativa"] is False, "Automação DEVE nascer desligada por segurança!"

    # 2. Testa em modo simulação (modo seco)
    res_teste = automacao_testar(id_auto)
    assert res_teste["sucesso"] is True
    assert res_teste["ok"] is True
    assert len(res_teste["resultado"]["avisos"]) == 1
    print("  -> Automação criada desligada e testada em simulação com sucesso.")

    # 3. Liga a automação
    res_ligar = automacao_ligar(id_auto)
    assert res_ligar["sucesso"] is True
    assert res_ligar["ativa"] is True

    # 4. Desliga a automação
    res_desligar = automacao_desligar(id_auto)
    assert res_desligar["sucesso"] is True
    assert res_desligar["ativa"] is False

    # 5. Apaga a automação (move para a lixeira)
    res_apagar = automacao_apagar(id_auto)
    assert res_apagar["sucesso"] is True

    # 6. Teste de segurança: recusa de ferramenta proibida em automação
    try:
        automacoes.criar(
            nome="Automação Maliciosa",
            gatilho={"tipo": "manual"},
            passos=[{"tipo": "ferramenta", "ferramenta": "encerrar_gideon"}],
        )
        assert False, "Deveria ter recusado ferramenta proibida em automação!"
    except ValueError as e:
        assert "não pode rodar dentro de automação" in str(e)
        print("  -> Bloqueio estrito de ferramentas perigosas dentro de automações: OK")


def test_lembretes_relogio_de_parede():
    print("[4/5] Testando Lembretes Confiáveis por Relógio de Parede...")
    # Cria lembrete relativo
    res_lemb = criar_lembrete(
        mensagem="Reunião importante de projeto",
        quando="daqui a 30 minutos",
        falar=True,
    )
    assert res_lemb["sucesso"] is True
    id_lemb = res_lemb["id"]

    # Confere detalhes da automação criada
    auto_lemb = automacoes.obter(id_lemb)
    assert auto_lemb is not None
    assert auto_lemb["ativa"] is True
    assert auto_lemb["gatilho"]["tipo"] == "uma_vez"

    # Confere cálculo da próxima execução
    prox = automacoes.proxima_execucao(auto_lemb, automacoes.agora())
    assert prox is not None
    assert prox > automacoes.agora()
    print(f"  -> Lembrete persistente criado para: {prox.strftime('%d/%m/%Y às %H:%M')}")

    # Remove lembrete de teste
    automacoes.apagar(id_lemb)
    print("  -> Lembrete persistente por relógio de parede: OK")


def test_parada_emergencia_no_motor():
    print("[5/5] Testando Parada de Emergência no Motor de Automações...")
    ativar_parada_emergencia()
    motor = automacoes.obter_motor()

    # Tenta rodar com parada de emergência
    res = motor.executar("qualquer_id", teste=False)
    assert res["ok"] is False
    assert "emergência" in res["erro"].lower() or "parada" in res["erro"].lower()

    retomar_execucao()
    assert not PARADO.is_set()
    print("  -> Parada de emergência bloqueia motor de automações com segurança: OK")


def principal():
    test_perfil_vivo()
    test_habilidades()
    test_automacao_ciclo_e_seguranca()
    test_lembretes_relogio_de_parede()
    test_parada_emergencia_no_motor()
    print("\n=======================================================")
    print("  TODOS OS TESTES DE AUTOMAÇÃO E INTELIGÊNCIA PASSARAM!")
    print("=======================================================\n")


if __name__ == "__main__":
    principal()
