"""Deteccao deterministica de comandos locais sensiveis da Gideon."""

import re
import unicodedata


def normalizar(texto: str) -> str:
    sem_acentos = unicodedata.normalize("NFKD", texto.lower())
    return " ".join(
        "".join(c for c in sem_acentos if not unicodedata.combining(c)).split()
    )


def detectar_comando_sistema(texto: str) -> str | None:
    texto = normalizar(texto)
    if re.search(r"\b(atualize|atualiza|atualizar|verifique)\b", texto) and re.search(
        r"\b(sistema|sistemas|atualizacao|atualizacoes|novidades|versao)\b", texto
    ):
        return "atualizar_sistemas"
    if any(
        frase in texto
        for frase in (
            "pode fechar",
            "pode encerrar",
            "encerre a gideon",
            "encerrar gideon",
            "desligue a gideon",
        )
    ):
        return "encerrar_gideon"
    return None


def resposta_confirmacao(texto: str) -> bool | None:
    texto = re.sub(r"[^a-z0-9 ]", "", normalizar(texto)).strip()
    if texto in {
        "sim",
        "sim confirmo",
        "sim pode",
        "sim pode fazer",
        "confirmo",
        "pode",
        "pode fazer",
        "pode atualizar",
        "confirmado",
    }:
        return True
    if texto in {"nao", "cancelar", "cancela", "deixa", "agora nao"}:
        return False
    return None
