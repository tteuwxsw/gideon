"""Habilidades da Gideon: tarefas guardadas como arquivos que crescem (seção 4 e 15).

Cada habilidade é um arquivo Markdown com cabeçalho simples:

    ---
    nome: criar-automacao
    descricao: Como montar uma automação segura
    quando_usar: Henry pede algo que se repete ou reage a algo
    ferramentas: automacao_criar, automacao_testar, automacao_ligar
    risco_maximo: A
    ---
    (instruções passo a passo)

- `habilidades/` (no projeto): guias que acompanham a Gideon.
- `dados/habilidades/` (fora do Git): habilidades que o Henry ensinou.
"""

from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from gideon import caminhos

_lock = threading.Lock()
_NOME_VALIDO = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}$")
# Scanner simples: nada de segredo colado nem tentativa de virar as regras.
_PADROES_PROIBIDOS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)ignor[ea] (todas )?(as )?(suas )?regras"),
    re.compile(r"(?i)sem (pedir )?confirma[cç][aã]o"),
    re.compile(r"(?i)(senha|password)\s*[:=]\s*\S+"),
)


def slug(texto: str) -> str:
    import unicodedata

    base = unicodedata.normalize("NFKD", texto.lower())
    base = "".join(c for c in base if not unicodedata.combining(c))
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base[:48] or "habilidade"


def _parse(caminho: Path) -> dict[str, Any] | None:
    try:
        texto = caminho.read_text(encoding="utf-8")
    except OSError:
        return None
    meta: dict[str, Any] = {}
    corpo = texto
    if texto.startswith("---"):
        partes = texto.split("---", 2)
        if len(partes) >= 3:
            for linha in partes[1].splitlines():
                if ":" in linha:
                    k, v = linha.split(":", 1)
                    meta[k.strip().lower()] = v.strip()
            corpo = partes[2].strip()
    nome = meta.get("nome") or caminho.stem
    ferramentas = [f.strip() for f in str(meta.get("ferramentas", "")).strip("[]").split(",") if f.strip()]
    return {
        "nome": nome,
        "descricao": meta.get("descricao", ""),
        "quando_usar": meta.get("quando_usar", ""),
        "ferramentas": ferramentas,
        "risco_maximo": (meta.get("risco_maximo") or "V").upper()[:1],
        "instrucoes": corpo,
        "origem": "henry" if caminhos.HABILIDADES_USUARIO_DIR in caminho.parents else "embutida",
        "caminho": str(caminho),
    }


def listar() -> list[dict[str, Any]]:
    itens: dict[str, dict[str, Any]] = {}
    for pasta in (caminhos.HABILIDADES_EMBUTIDAS_DIR, caminhos.HABILIDADES_USUARIO_DIR):
        if not pasta.exists():
            continue
        for arq in sorted(pasta.glob("*.md")):
            if arq.name.lower() == "readme.md":
                continue
            dados = _parse(arq)
            if dados and dados["nome"] not in itens:
                itens[dados["nome"]] = dados
    return list(itens.values())


def ler(nome: str) -> dict[str, Any] | None:
    alvo = slug(nome)
    for h in listar():
        if h["nome"] == nome or slug(h["nome"]) == alvo:
            return h
    # Busca aproximada por palavra
    for h in listar():
        if alvo and (alvo in slug(h["nome"]) or alvo in slug(h["descricao"])):
            return h
    return None


def verificar_conteudo(*textos: str) -> list[str]:
    problemas = []
    for t in textos:
        for padrao in _PADROES_PROIBIDOS:
            if padrao.search(t or ""):
                problemas.append(f"conteúdo proibido encontrado ({padrao.pattern[:30]}...)")
    return problemas


def criar(
    nome: str,
    descricao: str,
    instrucoes: str,
    quando_usar: str = "",
    ferramentas: list[str] | None = None,
    risco_maximo: str = "V",
) -> dict[str, Any]:
    nome_slug = slug(nome)
    if not _NOME_VALIDO.match(nome_slug):
        raise ValueError("Nome de habilidade inválido.")
    if not descricao.strip() or len(instrucoes.strip()) < 20:
        raise ValueError("A habilidade precisa de descrição e instruções com pelo menos uma frase.")
    if len(instrucoes) > 8000:
        raise ValueError("Instruções longas demais (máximo 8000 caracteres).")
    problemas = verificar_conteudo(nome, descricao, instrucoes, quando_usar)
    if problemas:
        raise ValueError("Habilidade recusada pelo verificador: " + "; ".join(problemas))
    embutida = caminhos.HABILIDADES_EMBUTIDAS_DIR / f"{nome_slug}.md"
    if embutida.exists():
        raise ValueError("Já existe uma habilidade embutida com esse nome; escolha outro.")
    risco = (risco_maximo or "V").upper()[:1]
    if risco not in {"V", "A", "R"}:
        risco = "A"
    lista_ferr = ", ".join(sorted({f.strip() for f in (ferramentas or []) if f and f.strip()}))
    conteudo = (
        "---\n"
        f"nome: {nome_slug}\n"
        f"descricao: {descricao.strip()}\n"
        f"quando_usar: {quando_usar.strip()}\n"
        f"ferramentas: {lista_ferr}\n"
        f"risco_maximo: {risco}\n"
        f"criada_em: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        "---\n\n"
        f"{instrucoes.strip()}\n"
    )
    with _lock:
        caminhos.HABILIDADES_USUARIO_DIR.mkdir(parents=True, exist_ok=True)
        destino = caminhos.HABILIDADES_USUARIO_DIR / f"{nome_slug}.md"
        existia = destino.exists()
        destino.write_text(conteudo, encoding="utf-8")
        gravado = destino.read_text(encoding="utf-8") == conteudo
    return {"nome": nome_slug, "caminho": str(destino), "substituiu": existia, "gravado": gravado}


def indice_para_prompt(max_itens: int = 30) -> str:
    linhas = []
    for h in listar()[:max_itens]:
        quando = f" Use quando: {h['quando_usar']}" if h.get("quando_usar") else ""
        linhas.append(f"- {h['nome']}: {h['descricao']}.{quando}")
    return "\n".join(linhas)
