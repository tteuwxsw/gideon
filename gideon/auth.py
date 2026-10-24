"""Autenticacao local compartilhada pelos clientes da Gideon."""

import os
import secrets
from pathlib import Path


TOKEN_PREFIX = "gdn2_"


def obter_ou_criar_token(caminho: Path) -> str:
    """Retorna um token atual e substitui automaticamente o formato antigo."""
    if caminho.exists():
        token = caminho.read_text(encoding="utf-8").strip()
        if token.startswith(TOKEN_PREFIX) and len(token) >= 40:
            return token

    caminho.parent.mkdir(parents=True, exist_ok=True)
    novo_token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    caminho.write_text(novo_token, encoding="utf-8")
    try:
        os.chmod(caminho, 0o600)
    except OSError:
        pass
    return novo_token


def token_valido(token_fornecido: str | None, token_esperado: str) -> bool:
    """Compara tokens sem expor diferencas de tempo relevantes."""
    return bool(
        token_fornecido
        and secrets.compare_digest(token_fornecido, token_esperado)
    )
