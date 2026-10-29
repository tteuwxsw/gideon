"""Módulo de configuração persistente da Gideon.

Gerencia preferências de usuário como idioma, voz e comportamento,
armazenadas em `dados/config.json`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gideon.caminhos import DADOS_DIR

CONFIG_ARQUIVO = DADOS_DIR / "config.json"

IDIOMAS_SUPORTADOS = {
    "pt-BR": {
        "nome": "Português (Brasil)",
        "voz_edge": "pt-BR-FranciscaNeural",
        "descricao": "Português do Brasil - Tom calmo e elegante",
    },
    "en-US": {
        "nome": "English (US)",
        "voz_edge": "en-US-AvaNeural",
        "descricao": "English (United States) - Elegant and composed",
    },
    "es-ES": {
        "nome": "Español",
        "voz_edge": "es-ES-ElviraNeural",
        "descricao": "Español - Tono formal y refinado",
    },
}

MODOS_PERSONALIDADE = frozenset({"padrao", "formal", "direta", "sarcastica"})

CONFIG_PADRAO: dict[str, Any] = {
    "idioma": "pt-BR",
    "interrupcao_voz_ativa": True,
    "modo_personalidade": "padrao",
    "sons_interface_ativos": True,
    "volume_sons_interface": 0.18,
}


def carregar_configuracao() -> dict[str, Any]:
    """Carrega as configurações salvas em disco ou retorna os padrões."""
    if not CONFIG_ARQUIVO.exists():
        salvar_configuracao(CONFIG_PADRAO)
        return dict(CONFIG_PADRAO)

    try:
        conteudo = CONFIG_ARQUIVO.read_text(encoding="utf-8")
        dados = json.loads(conteudo)
        if not isinstance(dados, dict):
            return dict(CONFIG_PADRAO)
        config = dict(CONFIG_PADRAO)
        config.update(dados)
        return config
    except Exception:
        return dict(CONFIG_PADRAO)


def salvar_configuracao(config: dict[str, Any]) -> dict[str, Any]:
    """Salva o dicionário de configurações em `dados/config.json`."""
    CONFIG_ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_ARQUIVO.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    return config


def obter_idioma() -> str:
    """Retorna o código do idioma ativo (ex: 'pt-BR')."""
    config = carregar_configuracao()
    idioma = config.get("idioma", "pt-BR")
    return idioma if idioma in IDIOMAS_SUPORTADOS else "pt-BR"


def definir_idioma(novo_idioma: str) -> str:
    """Atualiza e salva o idioma ativo."""
    if novo_idioma not in IDIOMAS_SUPORTADOS:
        raise ValueError(f"Idioma '{novo_idioma}' não suportado. Opções: {list(IDIOMAS_SUPORTADOS.keys())}")
    config = carregar_configuracao()
    config["idioma"] = novo_idioma
    salvar_configuracao(config)
    return novo_idioma


def obter_interrupcao_voz_ativa() -> bool:
    """Indica se dizer "Gideon" pode interromper uma fala em andamento."""
    return carregar_configuracao().get("interrupcao_voz_ativa", True) is True


def definir_interrupcao_voz_ativa(ativa: bool) -> bool:
    """Persiste a preferência de interrupção da fala por palavra de ativação."""
    config = carregar_configuracao()
    config["interrupcao_voz_ativa"] = bool(ativa)
    salvar_configuracao(config)
    return bool(ativa)


def obter_modo_personalidade() -> str:
    """Retorna o modo de personalidade persistido ou o padrão seguro."""
    modo = str(carregar_configuracao().get("modo_personalidade", "padrao")).strip().lower()
    return modo if modo in MODOS_PERSONALIDADE else "padrao"


def definir_modo_personalidade(modo: str) -> str:
    """Valida e persiste o modo de personalidade da Gideon."""
    modo_normalizado = str(modo or "").strip().lower()
    if modo_normalizado not in MODOS_PERSONALIDADE:
        raise ValueError(f"Modo de personalidade inválido: {modo}")
    config = carregar_configuracao()
    config["modo_personalidade"] = modo_normalizado
    salvar_configuracao(config)
    return modo_normalizado


def obter_configuracao_sons() -> dict[str, Any]:
    """Retorna preferência e volume seguro dos earcons da interface."""
    config = carregar_configuracao()
    try:
        volume = float(config.get("volume_sons_interface", 0.18))
    except (TypeError, ValueError):
        volume = 0.18
    return {
        "ativo": config.get("sons_interface_ativos", True) is True,
        "volume": max(0.0, min(0.5, volume)),
    }


def definir_configuracao_sons(ativo: bool, volume: float) -> dict[str, Any]:
    """Persiste earcons ligados/desligados e limita o volume a 50%."""
    volume_seguro = max(0.0, min(0.5, float(volume)))
    config = carregar_configuracao()
    config["sons_interface_ativos"] = bool(ativo)
    config["volume_sons_interface"] = volume_seguro
    salvar_configuracao(config)
    return {"ativo": bool(ativo), "volume": volume_seguro}


def obter_voz_para_idioma(idioma: str | None = None) -> str:
    """Retorna a voz correspondente ao idioma."""
    idioma_ativo = idioma or obter_idioma()
    info = IDIOMAS_SUPORTADOS.get(idioma_ativo, IDIOMAS_SUPORTADOS["pt-BR"])
    return info["voz_edge"]
