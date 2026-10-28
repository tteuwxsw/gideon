"""Ferramentas de Automação, Habilidades, Perfil e Lembretes da Gideon.

Conforme especificação ALFRED-PARA-O-CLAUDE.md:
- Automações com gatilhos de relógio de parede (horário, intervalo, uma_vez, data, evento, manual).
- Habilidades salvas como arquivos que crescem.
- Perfil vivo do Henry com preferências e regras aprovadas.
- Lembretes persistentes que sobrevivem a reinício e suspensão do computador.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any

from gideon import automacoes, caminhos, habilidades, perfil, permissoes
from gideon.gate import Ferramenta, Risco


# ─── Automações ──────────────────────────────────────────────────


def automacao_listar() -> dict[str, Any]:
    """Lista todas as automações registradas, status e próximas execuções."""
    itens = automacoes.listar()
    resumo_lista = []
    agora_dt = automacoes.agora()
    for a in itens:
        prox = automacoes.proxima_execucao(a, agora_dt) if a.get("ativa") else None
        resumo_lista.append({
            "id": a["id"],
            "nome": a["nome"],
            "descricao": a.get("descricao", ""),
            "ativa": bool(a.get("ativa")),
            "gatilho": automacoes.descrever_gatilho(a["gatilho"]),
            "proxima_execucao": prox.strftime("%d/%m/%Y às %H:%M") if prox else None,
            "permite_vermelho": a.get("permite", []),
            "total_passos": len(a.get("passos", [])),
        })

    if not resumo_lista:
        msg = "O senhor ainda não possui nenhuma automação cadastrada, Senhor Henry."
    else:
        ligadas = sum(1 for x in resumo_lista if x["ativa"])
        msg = f"O senhor tem {len(resumo_lista)} automação(ões) cadastrada(s), sendo {ligadas} ativa(s)."

    return {
        "sucesso": True,
        "verificado": True,
        "total": len(resumo_lista),
        "automacoes": resumo_lista,
        "evidencias": {"total": len(resumo_lista)},
        "mensagem_humana": msg,
    }


def automacao_obter(id: str) -> dict[str, Any]:
    """Obtém detalhes completos de uma automação pelo seu identificador."""
    a = automacoes.obter(id)
    if not a:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Automação '{id}' não encontrada.",
            "mensagem_humana": f"Não encontrei a automação '{id}', Senhor Henry.",
        }

    return {
        "sucesso": True,
        "verificado": True,
        "automacao": a,
        "descricao_completa": automacoes.descrever(a),
        "evidencias": {"id": a["id"], "ativa": a.get("ativa")},
        "mensagem_humana": f"Aqui estão os detalhes da automação '{a['nome']}':\n{automacoes.descrever(a)}",
    }


def automacao_criar(
    nome: str,
    gatilho: dict[str, Any],
    passos: list[dict[str, Any]],
    descricao: str = "",
    permite: list[str] | None = None,
    limite_por_hora: int = 6,
    substituir_id: str | None = None,
) -> dict[str, Any]:
    """Cria uma nova automação (sempre desligada por segurança) ou atualiza uma existente."""
    try:
        nova = automacoes.criar(
            nome=nome,
            gatilho=gatilho,
            passos=passos,
            descricao=descricao,
            permite=permite,
            limite_por_hora=limite_por_hora,
            substituir_id=substituir_id,
            ativa=False,
        )
    except Exception as e:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": str(e),
            "mensagem_humana": f"Não foi possível criar a automação: {str(e)}",
        }

    detalhes = automacoes.descrever(nova)
    return {
        "sucesso": True,
        "verificado": True,
        "id": nova["id"],
        "automacao": nova,
        "evidencias": {"id": nova["id"], "ativa": False},
        "mensagem_humana": f"Automação '{nova['nome']}' criada, Senhor Henry. Permanece desligada por segurança.",
    }


def automacao_testar(id: str) -> dict[str, Any]:
    """Testa a automação em modo seco (passos modificadores são simulados)."""
    a = automacoes.obter(id)
    if not a:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Automação '{id}' não encontrada.",
            "mensagem_humana": f"Não encontrei a automação '{id}' para testar.",
        }

    motor = automacoes.obter_motor()
    resultado = motor.executar(id, teste=True, motivo="teste_simulado")
    ok = bool(resultado.get("ok"))

    relato_passos = []
    for p in resultado.get("passos", []):
        status = "✓" if p["ok"] else "✗"
        relato_passos.append(f"Passo {p['passo']} ({p['tipo']}): {status} {p['resumo']}")

    resumo_texto = "\n".join(relato_passos)
    if ok:
        msg = f"Teste da automação '{a['nome']}' concluído com sucesso:\n{resumo_texto}"
        if resultado.get("avisos"):
            msg += "\n\nAvisos que seriam gerados:\n" + "\n".join(f"• {av}" for av in resultado["avisos"])
    else:
        msg = f"O teste da automação '{a['nome']}' falhou: {resultado.get('erro')}\n{resumo_texto}"

    return {
        "sucesso": ok,
        "verificado": True,
        "ok": ok,
        "resultado": resultado,
        "evidencias": {"id": id, "teste": True, "ok": ok},
        "mensagem_humana": msg,
    }


def _risco_ligar_automacao(id: str, **kwargs) -> Risco:
    a = automacoes.obter(id)
    if not a:
        return Risco.AMARELO
    return Risco.VERMELHO if a.get("permite") else Risco.AMARELO


def automacao_ligar(id: str) -> dict[str, Any]:
    """Ativa uma automação para que passe a rodar no relógio do sistema."""
    try:
        a = automacoes.ligar(id)
    except Exception as e:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": str(e),
            "mensagem_humana": f"Não foi possível ligar a automação: {str(e)}",
        }

    prox = automacoes.proxima_execucao(a, automacoes.agora())
    prox_txt = prox.strftime("%d/%m/%Y às %H:%M") if prox else "no próximo gatilho"
    msg = f"Automação '{a['nome']}' ligada com sucesso. Ela está ativa e a próxima execução será {prox_txt}."

    return {
        "sucesso": True,
        "verificado": True,
        "id": a["id"],
        "ativa": True,
        "evidencias": {"id": a["id"], "ativa": True},
        "mensagem_humana": msg,
    }


def automacao_desligar(id: str) -> dict[str, Any]:
    """Desativa uma automação sem apagá-la."""
    try:
        a = automacoes.desligar(id)
    except Exception as e:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": str(e),
            "mensagem_humana": f"Não foi possível desligar a automação: {str(e)}",
        }

    return {
        "sucesso": True,
        "verificado": True,
        "id": a["id"],
        "ativa": False,
        "evidencias": {"id": a["id"], "ativa": False},
        "mensagem_humana": f"Automação '{a['nome']}' pausada/desligada.",
    }


def automacao_apagar(id: str) -> dict[str, Any]:
    """Move uma automação para a lixeira (ação reversível)."""
    try:
        caminho_lixeira = automacoes.apagar(id)
    except Exception as e:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": str(e),
            "mensagem_humana": f"Não foi possível remover a automação: {str(e)}",
        }

    return {
        "sucesso": True,
        "verificado": True,
        "evidencias": {"id": id, "lixeira": caminho_lixeira},
        "mensagem_humana": f"A automação '{id}' foi movida para a lixeira com data e desativada.",
    }


def automacao_historico(id: str = "", limite: int = 10, apenas_falhas: bool = False) -> dict[str, Any]:
    """Consulta o histórico de execuções das automações."""
    itens = automacoes.ler_historico(id_=(id or None), so_falhas=apenas_falhas, limite=limite)
    return {
        "sucesso": True,
        "verificado": True,
        "total": len(itens),
        "historico": itens,
        "evidencias": {"total": len(itens)},
        "mensagem_humana": (
            f"Encontrei {len(itens)} registro(s) de execução no histórico de automações."
            if itens else "Nenhuma execução registrada no histórico ainda."
        ),
    }


def criar_lembrete(
    mensagem: str,
    quando: str,
    falar: bool = True,
) -> dict[str, Any]:
    """Cria um lembrete persistente por relógio de parede que sobrevive ao computador dormir."""
    msg_limpa = mensagem.strip()
    if not msg_limpa:
        return {"sucesso": False, "verificado": False, "erro": "Mensagem do lembrete vazia."}

    quando_str = quando.strip().lower()
    agora_dt = automacoes.agora()
    gatilho: dict[str, Any]

    # Interpreta 'em X minutos', 'em X horas', ou horário 'HH:MM'
    m_minutos = re.search(r"\b(?:em|daqui\s+a)\s+(\d+)\s+(?:minuto|minutos|min)\b", quando_str)
    m_horas = re.search(r"\b(?:em|daqui\s+a)\s+(\d+)\s+(?:hora|horas|h)\b", quando_str)
    m_hora_fixa = re.search(r"\b(?:às|as|para\s+as|para\s+às)?\s*(\d{1,2})[:hH](\d{2})\b", quando_str)

    if m_minutos:
        minutos = int(m_minutos.group(1))
        alvo_dt = agora_dt + timedelta(minutes=minutos)
        gatilho = {"tipo": "uma_vez", "quando": alvo_dt.strftime("%Y-%m-%dT%H:%M:%S")}
        desc_quando = f"daqui a {minutos} minutos ({alvo_dt.strftime('%H:%M')})"
    elif m_horas:
        horas = int(m_horas.group(1))
        alvo_dt = agora_dt + timedelta(hours=horas)
        gatilho = {"tipo": "uma_vez", "quando": alvo_dt.strftime("%Y-%m-%dT%H:%M:%S")}
        desc_quando = f"daqui a {horas} hora(s) ({alvo_dt.strftime('%H:%M')})"
    elif m_hora_fixa:
        h, m = int(m_hora_fixa.group(1)), int(m_hora_fixa.group(2))
        alvo_dt = agora_dt.replace(hour=h, minute=m, second=0)
        if alvo_dt <= agora_dt:
            alvo_dt += timedelta(days=1)
        gatilho = {"tipo": "uma_vez", "quando": alvo_dt.strftime("%Y-%m-%dT%H:%M:%S")}
        desc_quando = f"às {alvo_dt.strftime('%H:%M de %d/%m')}"
    else:
        dt_parsed = automacoes._parse_dt(quando_str)
        if dt_parsed:
            gatilho = {"tipo": "uma_vez", "quando": dt_parsed.strftime("%Y-%m-%dT%H:%M:%S")}
            desc_quando = f"em {dt_parsed.strftime('%d/%m às %H:%M')}"
        else:
            return {
                "sucesso": False,
                "verificado": False,
                "erro": f"Não consegui compreender o horário '{quando}'. Informe algo como 'daqui a 15 minutos' ou 'às 16:30'.",
                "mensagem_humana": f"Não compreendi o horário do lembrete, Senhor Henry. Pode dizer algo como 'daqui a 20 minutos' ou 'às 15:30'?",
            }

    passos = [
        {
            "tipo": "avisar",
            "mensagem": f"Lembrete para o Senhor Henry: {msg_limpa}",
            "falar": bool(falar),
        }
    ]

    nome_lembrete = f"Lembrete: {msg_limpa[:35]}"
    nova = automacoes.criar(
        nome=nome_lembrete,
        gatilho=gatilho,
        passos=passos,
        descricao=f"Lembrete pessoal: {msg_limpa}",
        ativa=True,
    )

    return {
        "sucesso": True,
        "verificado": True,
        "id": nova["id"],
        "evidencias": {"id": nova["id"], "gatilho": gatilho, "ativa": True},
        "mensagem_humana": f"Anotado, Senhor Henry. Lembrete criado para {desc_quando}: '{msg_limpa}'.",
    }


# ─── Habilidades ─────────────────────────────────────────────────


def habilidade_listar() -> dict[str, Any]:
    """Lista todas as habilidades da Gideon (embutidas e ensinadas pelo Henry)."""
    itens = habilidades.listar()
    resumo_habs = [
        {
            "nome": h["nome"],
            "descricao": h["descricao"],
            "quando_usar": h.get("quando_usar", ""),
            "origem": h.get("origem", "embutida"),
            "risco_maximo": h.get("risco_maximo", "V"),
        }
        for h in itens
    ]
    return {
        "sucesso": True,
        "verificado": True,
        "total": len(resumo_habs),
        "habilidades": resumo_habs,
        "evidencias": {"total": len(resumo_habs)},
        "mensagem_humana": f"Possuo {len(resumo_habs)} habilidade(s) registrada(s) em meus guias.",
    }


def habilidade_ler(nome: str) -> dict[str, Any]:
    """Lê as instruções completas de uma habilidade cadastrada."""
    h = habilidades.ler(nome)
    if not h:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Habilidade '{nome}' não encontrada.",
            "mensagem_humana": f"Não encontrei a habilidade '{nome}', Senhor Henry.",
        }

    return {
        "sucesso": True,
        "verificado": True,
        "habilidade": h,
        "evidencias": {"nome": h["nome"], "origem": h["origem"]},
        "mensagem_humana": f"Instruções da habilidade '{h['nome']}':\n\n{h['instrucoes']}",
    }


def habilidade_criar(
    nome: str,
    descricao: str,
    instrucoes: str,
    quando_usar: str = "",
    ferramentas: list[str] | None = None,
    risco_maximo: str = "A",
) -> dict[str, Any]:
    """Ensina uma nova habilidade à Gideon, salvando em arquivo Markdown pessoal."""
    try:
        resultado = habilidades.criar(
            nome=nome,
            descricao=descricao,
            instrucoes=instrucoes,
            quando_usar=quando_usar,
            ferramentas=ferramentas,
            risco_maximo=risco_maximo,
        )
    except Exception as e:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": str(e),
            "mensagem_humana": f"Não foi possível salvar a nova habilidade: {str(e)}",
        }

    return {
        "sucesso": True,
        "verificado": True,
        "nome": resultado["nome"],
        "evidencias": resultado,
        "mensagem_humana": f"Habilidade '{resultado['nome']}' aprendida e salva com sucesso em seus arquivos pessoais, Senhor Henry.",
    }


def ajuda_criar(assunto: str = "automacao") -> dict[str, Any]:
    """Guia rápido de como estruturar automações, habilidades e receitas da Gideon."""
    assunto_norm = assunto.lower().strip()
    if "hab" in assunto_norm:
        guia = (
            "GUIA PARA CRIAR HABILIDADE:\n"
            "1. Dê um nome curto em minúsculas (ex: relatorio-semanal, triagem-downloads).\n"
            "2. Descreva em uma frase o objetivo e quando usá-la.\n"
            "3. Liste as ferramentas que ela pode usar.\n"
            "4. Escreva as instruções passo a passo claras e objetivas."
        )
    elif "lembrete" in assunto_norm:
        guia = (
            "GUIA PARA CRIAR LEMBRETES:\n"
            "Use a ferramenta `criar_lembrete(mensagem, quando)`.\n"
            "Formatos aceitos de 'quando': 'daqui a 10 minutos', 'às 17:00', '2026-10-25T18:00'.\n"
            "Os lembretes usam relógio de parede e sobrevivem se o computador for suspenso."
        )
    else:
        guia = (
            "GUIA PARA CRIAR AUTOMAÇÕES (seção 18):\n"
            "1. Defina o gatilho:\n"
            "   - 'horario': {'tipo': 'horario', 'hora': '08:00', 'dias': ['seg','ter','qua','qui','sex']}\n"
            "   - 'intervalo': {'tipo': 'intervalo', 'minutos': 60}\n"
            "   - 'uma_vez': {'tipo': 'uma_vez', 'quando': '2026-10-25T15:30'}\n"
            "2. Liste os passos sequenciais:\n"
            "   - {'tipo': 'ferramenta', 'ferramenta': 'obter_status_pc', 'salvar_como': 'pc'}\n"
            "   - {'tipo': 'pensar', 'instrucao': 'Resuma o status {{pc}}', 'salvar_como': 'resumo'}\n"
            "   - {'tipo': 'avisar', 'mensagem': '{{resumo}}', 'falar': True}\n"
            "3. Ela nasce desligada. Teste em modo simulação antes de pedir confirmação para ligá-la."
        )

    return {
        "sucesso": True,
        "verificado": True,
        "guia": guia,
        "evidencias": {"assunto": assunto_norm},
        "mensagem_humana": guia,
    }


# ─── Perfil Vivo ─────────────────────────────────────────────────


def perfil_ler() -> dict[str, Any]:
    """Lê o perfil vivo do Henry com preferências, rotina e regras aprovadas."""
    conteudo = perfil.ler()
    return {
        "sucesso": True,
        "verificado": True,
        "perfil_markdown": conteudo,
        "evidencias": {"tamanho": len(conteudo)},
        "mensagem_humana": f"Aqui está o seu perfil atual, Senhor Henry:\n\n{conteudo}",
    }


def perfil_adicionar_regra(secao: str, regra: str) -> dict[str, Any]:
    """Acrescenta uma regra aprovada ou preferência ao perfil vivo do Henry."""
    try:
        res = perfil.adicionar(secao=secao, texto=regra, origem="conversa")
    except Exception as e:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": str(e),
            "mensagem_humana": f"Não foi possível adicionar ao perfil: {str(e)}",
        }

    return {
        "sucesso": True,
        "verificado": True,
        "secao": res["secao"],
        "evidencias": res,
        "mensagem_humana": f"Registrei essa nova regra na seção '{res['secao']}' do seu perfil, Senhor Henry.",
    }


def perfil_remover_regra(trecho: str) -> dict[str, Any]:
    """Remove uma regra do perfil vivo que contenha o trecho especificado."""
    removido = perfil.remover(trecho)
    if not removido:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Nenhuma regra encontrada com o trecho '{trecho}'.",
            "mensagem_humana": f"Não encontrei nenhuma regra no perfil contendo '{trecho}', Senhor Henry.",
        }

    return {
        "sucesso": True,
        "verificado": True,
        "evidencias": {"removido": trecho},
        "mensagem_humana": f"Regra contendo '{trecho}' removida do seu perfil com sucesso.",
    }


# ─── Memória Operacional ─────────────────────────────────────────


def memoria_buscar(termo: str, limite: int = 5) -> dict[str, Any]:
    """Pesquisa conversas passadas na memória permanente usando busca FTS5 (sem acentos)."""
    from gideon.servidor import memoria as memoria_global

    resultados = memoria_global.buscar_historico(termo, limite=limite)
    return {
        "sucesso": True,
        "verificado": True,
        "total": len(resultados),
        "resultados": resultados,
        "evidencias": {"total": len(resultados)},
        "mensagem_humana": (
            f"Encontrei {len(resultados)} trecho(s) relevante(s) na memória sobre '{termo}'."
            if resultados else f"Não encontrei registros na memória sobre '{termo}'."
        ),
    }


def memoria_guardar_fato(chave: str, valor: str) -> dict[str, Any]:
    """Guarda um fato permanente curto (chave -> valor) sobre o Henry ou suas preferências."""
    from gideon.servidor import memoria as memoria_global

    memoria_global.salvar_fato(chave, valor, origem="ferramenta")
    return {
        "sucesso": True,
        "verificado": True,
        "chave": chave,
        "valor": valor,
        "evidencias": {"chave": chave, "valor": valor},
        "mensagem_humana": f"Guardei na minha memória permanente que {chave} é {valor}.",
    }


def memoria_esquecer_fato(chave: str) -> dict[str, Any]:
    """Remove um fato da memória permanente."""
    from gideon.servidor import memoria as memoria_global

    ok = memoria_global.esquecer_fato(chave)
    if not ok:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Fato '{chave}' não encontrado.",
            "mensagem_humana": f"Não encontrei o fato '{chave}' na memória para esquecer.",
        }
    return {
        "sucesso": True,
        "verificado": True,
        "chave": chave,
        "evidencias": {"esquecido": chave},
        "mensagem_humana": f"A informação '{chave}' foi esquecida da memória permanente.",
    }


# ─── Registro das Ferramentas ────────────────────────────────────

FERRAMENTAS_INTELIGENCIA = [
    Ferramenta(
        nome="automacao_listar",
        descricao="Lista todas as automações registradas no computador do Henry, com status, gatilho e próxima execução.",
        risco=Risco.VERDE,
        executar=automacao_listar,
        frase=lambda **kwargs: "listar as automações ativas e cadastradas",
        parametros={"type": "object", "properties": {}},
    ),
    Ferramenta(
        nome="automacao_obter",
        descricao="Obtém os detalhes completos, passos e configurações de uma automação específica pelo ID.",
        risco=Risco.VERDE,
        executar=automacao_obter,
        frase=lambda id, **kwargs: f"consultar os detalhes da automação '{id}'",
        parametros={
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Identificador da automação"}},
            "required": ["id"],
        },
    ),
    Ferramenta(
        nome="automacao_criar",
        descricao=(
            "Cria uma nova automação ou atualiza uma existente. Nasce sempre desligada por segurança. "
            "Gatilhos suportados: horario (hora HH:MM, dias), intervalo (minutos), uma_vez (AAAA-MM-DDTHH:MM), data (dia, mes, hora), manual. "
            "Passos suportados: ferramenta, pensar, avisar, automacao, emitir."
        ),
        risco=Risco.AMARELO,
        executar=automacao_criar,
        frase=lambda nome, **kwargs: f"criar a automação '{nome}' (desligada)",
        parametros={
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome descritivo da automação"},
                "gatilho": {
                    "type": "object",
                    "description": "Configuração do gatilho (ex: {'tipo': 'horario', 'hora': '08:00', 'dias': ['seg','ter','qua','qui','sex']})",
                },
                "passos": {
                    "type": "array",
                    "description": "Lista sequencial de passos a executar",
                    "items": {"type": "object"},
                },
                "descricao": {"type": "string", "description": "Descrição curta do objetivo da automação"},
                "permite": {
                    "type": "array",
                    "description": "Lista de ferramentas vermelhas autorizadas a rodar sozinhas nesta automação",
                    "items": {"type": "string"},
                },
                "limite_por_hora": {"type": "integer", "description": "Limite máximo de disparos por hora (padrão 6)"},
                "substituir_id": {"type": "string", "description": "ID de uma automação existente a ser substituída"},
            },
            "required": ["nome", "gatilho", "passos"],
        },
    ),
    Ferramenta(
        nome="automacao_testar",
        descricao="Testa uma automação em modo seco (simulação). Passos modificadores não têm efeito real.",
        risco=Risco.VERDE,
        executar=automacao_testar,
        frase=lambda id, **kwargs: f"testar a automação '{id}' em modo simulação",
        parametros={
            "type": "object",
            "properties": {"id": {"type": "string", "description": "ID da automação a testar"}},
            "required": ["id"],
        },
    ),
    Ferramenta(
        nome="automacao_ligar",
        descricao="Ativa uma automação no relógio do sistema. Exige confirmação do Henry caso contenha ações em 'permite'.",
        risco=Risco.AMARELO,
        risco_dinamico=_risco_ligar_automacao,
        executar=automacao_ligar,
        frase=lambda id, **kwargs: (
            automacoes.frase_ligar(automacoes.obter(id))
            if automacoes.obter(id)
            else f"ligar a automação '{id}'"
        ),
        parametros={
            "type": "object",
            "properties": {"id": {"type": "string", "description": "ID da automação a ligar"}},
            "required": ["id"],
        },
    ),
    Ferramenta(
        nome="automacao_desligar",
        descricao="Desativa uma automação sem excluí-la.",
        risco=Risco.AMARELO,
        executar=automacao_desligar,
        frase=lambda id, **kwargs: f"desligar a automação '{id}'",
        parametros={
            "type": "object",
            "properties": {"id": {"type": "string", "description": "ID da automação a desligar"}},
            "required": ["id"],
        },
    ),
    Ferramenta(
        nome="automacao_apagar",
        descricao="Move uma automação para a lixeira com data (ação reversível).",
        risco=Risco.AMARELO,
        executar=automacao_apagar,
        frase=lambda id, **kwargs: f"mover a automação '{id}' para a lixeira",
        parametros={
            "type": "object",
            "properties": {"id": {"type": "string", "description": "ID da automação a apagar"}},
            "required": ["id"],
        },
    ),
    Ferramenta(
        nome="automacao_historico",
        descricao="Consulta o log de auditoria e histórico de execuções das automações.",
        risco=Risco.VERDE,
        executar=automacao_historico,
        frase=lambda id="", **kwargs: f"consultar histórico de execuções{f' de {id}' if id else ''}",
        parametros={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Opcional: filtrar por ID de automação"},
                "limite": {"type": "integer", "description": "Máximo de registros a consultar (padrão 10)"},
                "apenas_falhas": {"type": "boolean", "description": "Filtrar apenas execuções que falharam"},
            },
        },
    ),
    Ferramenta(
        nome="criar_lembrete",
        descricao="Cria um lembrete no relógio do sistema com aviso e fala quando chegar o momento (ex: 'daqui a 15 minutos', 'às 17:00').",
        risco=Risco.AMARELO,
        executar=criar_lembrete,
        frase=lambda mensagem, quando, **kwargs: f"criar lembrete '{mensagem}' para {quando}",
        parametros={
            "type": "object",
            "properties": {
                "mensagem": {"type": "string", "description": "O que deve ser lembrado"},
                "quando": {"type": "string", "description": "Quando lembrar (ex: 'daqui a 20 minutos', 'às 16:30', 'amanhã às 09:00')"},
                "falar": {"type": "boolean", "description": "Se a Gideon deve falar em voz alta ao disparar o lembrete (padrão true)"},
            },
            "required": ["mensagem", "quando"],
        },
    ),
    Ferramenta(
        nome="habilidade_listar",
        descricao="Lista as habilidades conhecidas da Gideon (tarefas guardadas como arquivos com instruções).",
        risco=Risco.VERDE,
        executar=habilidade_listar,
        frase=lambda **kwargs: "listar as habilidades cadastradas",
        parametros={"type": "object", "properties": {}},
    ),
    Ferramenta(
        nome="habilidade_ler",
        descricao="Lê o guia e as instruções de uma habilidade cadastrada.",
        risco=Risco.VERDE,
        executar=habilidade_ler,
        frase=lambda nome, **kwargs: f"ler a habilidade '{nome}'",
        parametros={
            "type": "object",
            "properties": {"nome": {"type": "string", "description": "Nome da habilidade"}},
            "required": ["nome"],
        },
    ),
    Ferramenta(
        nome="habilidade_criar",
        descricao="Ensina uma nova habilidade à Gideon salvando como arquivo Markdown com instruções.",
        risco=Risco.AMARELO,
        executar=habilidade_criar,
        frase=lambda nome, **kwargs: f"aprender e salvar a nova habilidade '{nome}'",
        parametros={
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome curto da habilidade (ex: relatorio-semanal)"},
                "descricao": {"type": "string", "description": "Descrição em uma frase"},
                "instrucoes": {"type": "string", "description": "Instruções passo a passo detalhadas"},
                "quando_usar": {"type": "string", "description": "Quando acionar esta habilidade"},
                "ferramentas": {"type": "array", "items": {"type": "string"}, "description": "Ferramentas autorizadas"},
                "risco_maximo": {"type": "string", "description": "'V', 'A' ou 'R'"},
            },
            "required": ["nome", "descricao", "instrucoes"],
        },
    ),
    Ferramenta(
        nome="ajuda_criar",
        descricao="Consulta o manual oficial de como criar automações, habilidades, conectores e lembretes.",
        risco=Risco.VERDE,
        executar=ajuda_criar,
        frase=lambda assunto="automacao", **kwargs: f"consultar guia de criação de {assunto}",
        parametros={
            "type": "object",
            "properties": {
                "assunto": {
                    "type": "string",
                    "description": "'automacao', 'habilidade', 'lembrete'",
                }
            },
        },
    ),
    Ferramenta(
        nome="perfil_ler",
        descricao="Lê o perfil vivo do Henry com seu jeito de falar, preferências e regras aprovadas.",
        risco=Risco.VERDE,
        executar=perfil_ler,
        frase=lambda **kwargs: "consultar o perfil do Henry",
        parametros={"type": "object", "properties": {}},
    ),
    Ferramenta(
        nome="perfil_adicionar_regra",
        descricao="Acrescenta uma regra aprovada ou preferência ao perfil vivo do Henry.",
        risco=Risco.AMARELO,
        executar=perfil_adicionar_regra,
        frase=lambda secao, regra, **kwargs: f"adicionar regra na seção '{secao}' do perfil: '{regra}'",
        parametros={
            "type": "object",
            "properties": {
                "secao": {
                    "type": "string",
                    "description": "Seção do perfil: 'Regras aprovadas', 'Preferências', 'Rotina e horários', etc.",
                },
                "regra": {"type": "string", "description": "Texto da regra ou preferência a registrar"},
            },
            "required": ["secao", "regra"],
        },
    ),
    Ferramenta(
        nome="perfil_remover_regra",
        descricao="Remove uma regra do perfil vivo que contenha o trecho informado.",
        risco=Risco.AMARELO,
        executar=perfil_remover_regra,
        frase=lambda trecho, **kwargs: f"remover regra do perfil contendo '{trecho}'",
        parametros={
            "type": "object",
            "properties": {"trecho": {"type": "string", "description": "Texto contido na regra a remover"}},
            "required": ["trecho"],
        },
    ),
    Ferramenta(
        nome="memoria_buscar",
        descricao="Busca no histórico completo de conversas da Gideon por termos ou frases usando FTS5 sem acento.",
        risco=Risco.VERDE,
        executar=memoria_buscar,
        frase=lambda termo, **kwargs: f"buscar na memória de conversas por '{termo}'",
        parametros={
            "type": "object",
            "properties": {
                "termo": {"type": "string", "description": "Palavra ou termo a pesquisar no histórico"},
                "limite": {"type": "integer", "description": "Máximo de trechos a recuperar (padrão 5)"},
            },
            "required": ["termo"],
        },
    ),
    Ferramenta(
        nome="memoria_guardar_fato",
        descricao="Guarda um fato durável curto (chave -> valor) na memória permanente SQLite.",
        risco=Risco.AMARELO,
        executar=memoria_guardar_fato,
        frase=lambda chave, valor, **kwargs: f"guardar na memória permanente: {chave} = {valor}",
        parametros={
            "type": "object",
            "properties": {
                "chave": {"type": "string", "description": "Identificador do fato (ex: 'restaurante_favorito')"},
                "valor": {"type": "string", "description": "Valor do fato (ex: 'Ostradamus')"},
            },
            "required": ["chave", "valor"],
        },
    ),
    Ferramenta(
        nome="memoria_esquecer_fato",
        descricao="Exclui um fato registrado na memória permanente da Gideon.",
        risco=Risco.AMARELO,
        executar=memoria_esquecer_fato,
        frase=lambda chave, **kwargs: f"excluir da memória o fato '{chave}'",
        parametros={
            "type": "object",
            "properties": {"chave": {"type": "string", "description": "Identificador do fato a excluir"}},
            "required": ["chave"],
        },
    ),
]
