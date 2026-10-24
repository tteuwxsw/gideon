# -*- coding: utf-8 -*-
"""Protocolo de comunicação WebSocket entre o backend Python e o avatar Godot 4."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Enums do protocolo
# ---------------------------------------------------------------------------

class TipoMensagem(str, Enum):
    """Tipos de mensagem trocadas via WebSocket.

    Backend → Avatar:
        fala_inicio, fala_chunk, fala_fim, emocao, modo, olhar,
        gesto, ouvindo, pensando, visibilidade, status

    Avatar → Backend:
        modo_mudou, clique_avatar, janela_moveu, pronto
    """

    # Backend → Avatar
    FALA_INICIO = "fala_inicio"
    FALA_CHUNK = "fala_chunk"
    FALA_FIM = "fala_fim"
    EMOCAO = "emocao"
    MODO = "modo"
    OLHAR = "olhar"
    GESTO = "gesto"
    OUVINDO = "ouvindo"
    PENSANDO = "pensando"
    VISIBILIDADE = "visibilidade"
    STATUS = "status"

    # Avatar → Backend
    MODO_MUDOU = "modo_mudou"
    CLIQUE_AVATAR = "clique_avatar"
    JANELA_MOVEU = "janela_moveu"
    PRONTO = "pronto"


class ModoAvatar(str, Enum):
    """Modos visuais/comportamentais do avatar holográfico."""

    COMPACTO = "compacto"
    CONVERSA = "conversa"
    FOCO = "foco"
    OPERACIONAL = "operacional"
    OCULTO = "oculto"


class Emocao(str, Enum):
    """Emoções que o avatar pode expressar."""

    NEUTRA = "neutra"
    AMIGAVEL = "amigavel"
    CURIOSIDADE = "curiosidade"
    DUVIDA = "duvida"
    SURPRESA = "surpresa"
    CONCENTRACAO = "concentracao"
    SATISFACAO = "satisfacao"
    PREOCUPACAO = "preocupacao"
    HUMOR = "humor"


class Transicao(str, Enum):
    """Tipos de transição visual entre estados do avatar."""

    HOLOGRAFICO = "holografico"
    FADE = "fade"
    INSTANTANEO = "instantaneo"


# ---------------------------------------------------------------------------
# Dataclasses auxiliares
# ---------------------------------------------------------------------------

@dataclass
class Visema:
    """Representa um visema (pose labial) sincronizado com o áudio da fala."""

    visema: str
    tempo: float


@dataclass
class MensagemProtocolo:
    """Mensagem estruturada do protocolo WebSocket."""

    tipo: TipoMensagem
    dados: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Expressão regular para tags de emoção embutidas no texto
# Formato: [EMOCAO:nome]
# ---------------------------------------------------------------------------

_PADRAO_EMOCAO = re.compile(r"\[EMOCAO:(\w+)\]")

# Conjunto dos nomes válidos de emoção para validação rápida
_EMOCOES_VALIDAS = {e.value for e in Emocao}


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

def criar_evento(tipo: str, **dados) -> str:
    """Cria uma string JSON representando um evento do protocolo.

    Args:
        tipo: Nome do tipo de mensagem (deve corresponder a um valor de TipoMensagem).
        **dados: Campos adicionais do evento.

    Returns:
        String JSON pronta para envio via WebSocket.

    Raises:
        ValueError: Se o tipo informado não for um TipoMensagem válido.
    """
    # Valida o tipo contra o enum
    try:
        tipo_validado = TipoMensagem(tipo)
    except ValueError:
        tipos_disponiveis = ", ".join(t.value for t in TipoMensagem)
        raise ValueError(
            f"Tipo de mensagem inválido: '{tipo}'. "
            f"Tipos disponíveis: {tipos_disponiveis}"
        )

    evento = {"tipo": tipo_validado.value, "dados": dados}
    return json.dumps(evento, ensure_ascii=False)


def analisar_evento(json_str: str) -> dict:
    """Analisa uma string JSON recebida via WebSocket e retorna um dicionário validado.

    O JSON deve conter pelo menos a chave ``tipo`` com um valor correspondente
    a um dos membros de ``TipoMensagem``. A chave ``dados`` é opcional e
    assume ``{}`` quando ausente.

    Args:
        json_str: String JSON recebida.

    Returns:
        Dicionário com as chaves ``tipo`` (str) e ``dados`` (dict).

    Raises:
        ValueError: Se o JSON for inválido ou o tipo de mensagem não for reconhecido.
    """
    try:
        evento = json.loads(json_str)
    except json.JSONDecodeError as erro:
        raise ValueError(f"JSON inválido recebido: {erro}") from erro

    if not isinstance(evento, dict):
        raise ValueError("O evento deve ser um objeto JSON (dicionário).")

    tipo_bruto = evento.get("tipo")
    if tipo_bruto is None:
        raise ValueError("O evento não contém a chave obrigatória 'tipo'.")

    # Valida contra o enum
    try:
        tipo_validado = TipoMensagem(tipo_bruto)
    except ValueError:
        raise ValueError(f"Tipo de mensagem desconhecido: '{tipo_bruto}'.")

    dados = evento.get("dados", {})
    if not isinstance(dados, dict):
        raise ValueError("A chave 'dados' deve ser um dicionário.")

    return {"tipo": tipo_validado.value, "dados": dados}


def extrair_emocoes_texto(texto: str) -> list[tuple[int, str]]:
    """Encontra todas as tags [EMOCAO:nome] no texto.

    Retorna uma lista de tuplas ``(posição, nome_da_emoção)`` na ordem em
    que aparecem. Apenas emoções presentes no enum ``Emocao`` são incluídas.

    Args:
        texto: Texto contendo possíveis tags de emoção.

    Returns:
        Lista de tuplas (posição_no_texto, nome_da_emoção).
    """
    resultados: list[tuple[int, str]] = []
    for correspondencia in _PADRAO_EMOCAO.finditer(texto):
        nome_emocao = correspondencia.group(1).lower()
        if nome_emocao in _EMOCOES_VALIDAS:
            resultados.append((correspondencia.start(), nome_emocao))
    return resultados


def limpar_emocoes_texto(texto: str) -> str:
    """Remove todas as tags [EMOCAO:nome] do texto para exibição limpa.

    Args:
        texto: Texto contendo possíveis tags de emoção.

    Returns:
        Texto sem as tags de emoção, com espaços duplicados normalizados.
    """
    texto_limpo = _PADRAO_EMOCAO.sub("", texto)
    # Remove espaços duplicados que podem surgir após a remoção das tags
    texto_limpo = re.sub(r"  +", " ", texto_limpo)
    return texto_limpo.strip()
