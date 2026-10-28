"""Perfil vivo do Henry (seção 15 da especificação).

Um arquivo Markdown local (`dados/perfil.md`) com o jeito de falar, preferências,
regras aprovadas e coisas a evitar. Ele é relido a cada resposta e entra no prompt.
Nada entra aqui sem passar pelo Henry: a ferramenta que escreve é amarela.
"""

from __future__ import annotations

import re
import threading
from datetime import datetime

from gideon import caminhos

SECOES = (
    "Jeito de falar",
    "Preferências",
    "Regras aprovadas",
    "Pessoas importantes",
    "Rotina e horários",
    "Trabalho e projetos",
    "Coisas que o Henry não gosta",
)

MODELO_INICIAL = """# Perfil vivo do Henry

Arquivo local da Gideon. O Henry pode editar ou apagar qualquer linha.
Cada linha nova traz a data e a origem.

## Jeito de falar
- Português do Brasil, direto, formal e respeitoso.
- Dirigir-se ao Henry sempre como "Senhor", "Senhor Henry" ou "Senhor:".

## Preferências
- Usa Windows.

## Regras aprovadas

## Pessoas importantes

## Rotina e horários

## Trabalho e projetos
- Por enquanto uso pessoal, para tarefas diárias; no futuro quer integrar com projetos de empresas e projetos próprios.

## Coisas que o Henry não gosta
"""

_lock = threading.Lock()


def _garantir_arquivo() -> None:
    if not caminhos.PERFIL_ARQUIVO.exists():
        caminhos.PERFIL_ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
        caminhos.PERFIL_ARQUIVO.write_text(MODELO_INICIAL, encoding="utf-8")


def ler() -> str:
    with _lock:
        _garantir_arquivo()
        return caminhos.PERFIL_ARQUIVO.read_text(encoding="utf-8")


def _normalizar_secao(secao: str) -> str:
    alvo = (secao or "").strip().lower()
    for s in SECOES:
        if s.lower() == alvo or s.lower().startswith(alvo[:6]) and alvo:
            return s
    return "Regras aprovadas"


def adicionar(secao: str, texto: str, origem: str = "conversa") -> dict:
    """Acrescenta uma linha datada a uma seção do perfil e confere a gravação."""
    linha_texto = re.sub(r"\s+", " ", (texto or "")).strip(" -")
    if not linha_texto:
        raise ValueError("O texto da regra está vazio.")
    if len(linha_texto) > 400:
        raise ValueError("A regra deve ser curta (até 400 caracteres).")
    secao_ok = _normalizar_secao(secao)
    data = datetime.now().strftime("%d/%m/%Y")
    linha = f"- {linha_texto} ({data}, {origem})"

    with _lock:
        _garantir_arquivo()
        conteudo = caminhos.PERFIL_ARQUIVO.read_text(encoding="utf-8")
        cabecalho = f"## {secao_ok}"
        if cabecalho not in conteudo:
            conteudo = conteudo.rstrip() + f"\n\n{cabecalho}\n"
        partes = conteudo.split(cabecalho, 1)
        resto = partes[1]
        prox = re.search(r"\n## ", resto)
        if prox:
            bloco, depois = resto[: prox.start()], resto[prox.start():]
        else:
            bloco, depois = resto, ""
        bloco = bloco.rstrip() + "\n" + linha + "\n"
        novo = partes[0] + cabecalho + bloco + depois
        caminhos.PERFIL_ARQUIVO.write_text(novo, encoding="utf-8")
        confere = caminhos.PERFIL_ARQUIVO.read_text(encoding="utf-8")
    return {"secao": secao_ok, "linha": linha, "gravado": linha in confere}


def remover(trecho: str) -> bool:
    """Remove a primeira linha de item que contém o trecho informado."""
    alvo = (trecho or "").strip().lower()
    if len(alvo) < 3:
        return False
    with _lock:
        _garantir_arquivo()
        linhas = caminhos.PERFIL_ARQUIVO.read_text(encoding="utf-8").splitlines()
        for i, l in enumerate(linhas):
            if l.startswith("- ") and alvo in l.lower():
                del linhas[i]
                caminhos.PERFIL_ARQUIVO.write_text("\n".join(linhas) + "\n", encoding="utf-8")
                return True
    return False


def para_prompt(max_caracteres: int = 2500) -> str:
    """Versão enxuta do perfil para o prompt (sem títulos vazios)."""
    try:
        texto = ler()
    except OSError:
        return ""
    blocos: list[str] = []
    secao_atual = ""
    itens: list[str] = []
    for linha in texto.splitlines():
        if linha.startswith("## "):
            if secao_atual and itens:
                blocos.append(f"{secao_atual}:\n" + "\n".join(itens))
            secao_atual, itens = linha[3:].strip(), []
        elif linha.startswith("- ") and secao_atual:
            itens.append(linha)
    if secao_atual and itens:
        blocos.append(f"{secao_atual}:\n" + "\n".join(itens))
    resultado = "\n\n".join(blocos)
    if len(resultado) > max_caracteres:
        resultado = resultado[:max_caracteres].rsplit("\n", 1)[0] + "\n(...perfil truncado)"
    return resultado
