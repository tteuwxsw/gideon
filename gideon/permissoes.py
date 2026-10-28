"""Permissões aprendidas: quais ações amarelas o Henry liberou para rodar sem perguntar.

Regra da especificação (seção 6): amarelo confirma na 1ª vez; depois pode virar
"sempre" para aquele tipo. Vermelho NUNCA entra nesta lista.
"""

from __future__ import annotations

import json
import threading
from typing import Iterable

from gideon import caminhos

# Ações amarelas que já rodavam sem perguntar pelo caminho de voz/regex, mais
# ações locais e inofensivas que o próprio Henry pede (lembrete, anotar fato).
AMARELOS_LIBERADOS_PADRAO = frozenset({
    "abrir_programa",
    "fechar_programa",
    "gerenciar_janela",
    "abrir_pasta",
    "pesquisar_navegador",
    "tocar_ou_pesquisar_midia",
    "memoria_guardar_fato",
    "criar_lembrete",
    "automacao_criar",
    "automacao_desligar",
})

# Ações que exigem confirmação toda vez, mesmo sendo amarelas.
NUNCA_LIBERAR = frozenset({
    "automacao_ligar",
    "automacao_apagar",
    "memoria_esquecer_fato",
    "mover_para_lixeira",
})

_lock = threading.Lock()


def _ler_arquivo() -> dict:
    try:
        return json.loads(caminhos.PERMISSOES_ARQUIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _gravar_arquivo(dados: dict) -> None:
    caminhos.PERMISSOES_ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminhos.PERMISSOES_ARQUIVO.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(caminhos.PERMISSOES_ARQUIVO)


def amarelos_liberados() -> set[str]:
    with _lock:
        dados = _ler_arquivo()
    liberados = set(AMARELOS_LIBERADOS_PADRAO) | set(dados.get("amarelos_liberados", []))
    liberados -= set(dados.get("amarelos_bloqueados", []))
    return liberados - set(NUNCA_LIBERAR)


def amarelo_liberado(nome_ferramenta: str) -> bool:
    return nome_ferramenta in amarelos_liberados()


def liberar_amarelo(nome_ferramenta: str) -> bool:
    """Marca uma ação amarela como 'sempre pode'. Retorna False se ela não pode ser liberada."""
    if nome_ferramenta in NUNCA_LIBERAR:
        return False
    with _lock:
        dados = _ler_arquivo()
        lista = set(dados.get("amarelos_liberados", []))
        lista.add(nome_ferramenta)
        dados["amarelos_liberados"] = sorted(lista)
        dados["amarelos_bloqueados"] = sorted(set(dados.get("amarelos_bloqueados", [])) - {nome_ferramenta})
        _gravar_arquivo(dados)
    return True


def bloquear_amarelo(nome_ferramenta: str) -> None:
    """Volta a exigir confirmação para uma ação amarela."""
    with _lock:
        dados = _ler_arquivo()
        dados["amarelos_liberados"] = sorted(set(dados.get("amarelos_liberados", [])) - {nome_ferramenta})
        bloqueados = set(dados.get("amarelos_bloqueados", []))
        bloqueados.add(nome_ferramenta)
        dados["amarelos_bloqueados"] = sorted(bloqueados)
        _gravar_arquivo(dados)


def resumo(nomes: Iterable[str] | None = None) -> list[str]:
    liberados = amarelos_liberados()
    if nomes is None:
        return sorted(liberados)
    return sorted(n for n in nomes if n in liberados)
