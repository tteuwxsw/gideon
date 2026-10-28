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
        "voz_edge": "pt-BR-ThalitaMultilingualNeural",
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

CONFIG_PADRAO: dict[str, Any] = {
    "idioma": "pt-BR",
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


def obter_voz_para_idioma(idioma: str | None = None) -> str:
    """Retorna a voz correspondente ao idioma."""
    idioma_ativo = idioma or obter_idioma()
    info = IDIOMAS_SUPORTADOS.get(idioma_ativo, IDIOMAS_SUPORTADOS["pt-BR"])
    return info["voz_edge"]
