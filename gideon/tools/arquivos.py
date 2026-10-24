"""Ferramentas de gerenciamento, busca, abertura de pastas e escrita verificada de arquivos da Gideon."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

import psutil

from gideon.gate import Ferramenta, Risco

PASTAS_COMUNS: dict[str, Path] = {
    "downloads": Path.home() / "Downloads",
    "download": Path.home() / "Downloads",
    "documentos": Path.home() / "Documents",
    "documents": Path.home() / "Documents",
    "meus documentos": Path.home() / "Documents",
    "desktop": Path.home() / "Desktop",
    "area de trabalho": Path.home() / "Desktop",
    "área de trabalho": Path.home() / "Desktop",
    "imagens": Path.home() / "Pictures",
    "fotos": Path.home() / "Pictures",
    "musicas": Path.home() / "Music",
    "músicas": Path.home() / "Music",
    "videos": Path.home() / "Videos",
    "vídeos": Path.home() / "Videos",
    "projeto": Path(__file__).resolve().parent.parent.parent,
    "usuario": Path.home(),
}

ARQUIVOS_PROTEGIDOS = [".env", "id_rsa", "id_ed25519", "auth_token.txt", "chave", "password", "token"]


def _resolver_pasta(pasta: str) -> Path:
    chave = pasta.lower().strip(" .,!?\"'")
    for prefixo in ("pasta ", "a pasta ", "diretorio ", "o diretorio "):
        if chave.startswith(prefixo):
            chave = chave[len(prefixo):].strip()
    if chave in PASTAS_COMUNS:
        return PASTAS_COMUNS[chave]
    candidato = Path(os.path.expandvars(pasta.strip(" \"'")))
    if not candidato.is_absolute():
        # Tenta localizar dentro da home do usuário
        na_home = Path.home() / candidato
        if na_home.exists():
            return na_home
    return candidato


def listar_arquivos(pasta: str = "downloads", limite: int = 20) -> dict[str, Any]:
    """Lista os arquivos recentes dentro de uma pasta permitida do usuário."""
    caminho = _resolver_pasta(pasta)

    if not caminho.exists() or not caminho.is_dir():
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"A pasta '{pasta}' não foi encontrada ou não é um diretório válido.",
            "mensagem_humana": f"Não encontrei a pasta {pasta} no seu computador, Henry.",
        }

    itens = []
    try:
        entradas = sorted(caminho.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in entradas[:limite]:
            tipo = "diretorio" if p.is_dir() else "arquivo"
            tamanho_kb = f"{p.stat().st_size / 1024:.1f} KB" if p.is_file() else "-"
            itens.append({
                "nome": p.name,
                "tipo": tipo,
                "tamanho": tamanho_kb,
            })
        nomes_curtos = ", ".join(i["nome"] for i in itens[:5]) if itens else "nenhum arquivo"
        return {
            "sucesso": True,
            "verificado": True,
            "pasta": str(caminho),
            "total_encontrados": len(entradas),
            "arquivos": itens,
            "evidencias": {"pasta": str(caminho), "total_encontrados": len(entradas)},
            "mensagem_humana": f"Na pasta {caminho.name} encontrei {len(entradas)} itens. Os mais recentes são: {nomes_curtos}.",
        }
    except Exception as e:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Erro ao acessar '{pasta}': {str(e)}",
            "mensagem_humana": f"Não consegui listar os arquivos da pasta {pasta}.",
        }


def abrir_pasta(pasta: str = "downloads") -> dict[str, Any]:
    """Abre uma pasta no Explorador de Arquivos do Windows e VERIFICA se foi aberta."""
    caminho = _resolver_pasta(pasta)
    if not caminho.exists() or not caminho.is_dir():
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"A pasta '{pasta}' ({caminho}) não existe.",
            "mensagem_humana": f"Não encontrei a pasta '{pasta}' no seu computador, Henry.",
        }

    try:
        proc = subprocess.Popen(
            ["explorer.exe", str(caminho.resolve())],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.35)
        explorer_ativo = any(
            (p.info.get("name") or "").lower() == "explorer.exe"
            for p in psutil.process_iter(["name"])
        )
        if not explorer_ativo:
            return {
                "sucesso": False,
                "verificado": False,
                "erro": "O processo explorer.exe não pôde ser confirmado após abrir a pasta.",
                "mensagem_humana": f"Tentei abrir a pasta {caminho.name}, mas o Explorador de Arquivos não respondeu.",
            }

        return {
            "sucesso": True,
            "verificado": True,
            "evidencias": {
                "pasta": str(caminho.resolve()),
                "pid_lancado": proc.pid,
                "explorer_ativo": True,
            },
            "mensagem_humana": f"Pronto, abri a pasta {caminho.name}.",
        }
    except Exception as e:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Erro ao abrir a pasta '{pasta}': {e}",
            "mensagem_humana": f"Não consegui abrir a pasta {pasta}: {e}",
        }


def pesquisar_arquivos(termo: str, pasta: str = "todas", limite: int = 15) -> dict[str, Any]:
    """Pesquisa arquivos pelo nome nas pastas do usuário e verifica a existência de cada resultado."""
    termo_limpo = termo.strip().lower()
    if not termo_limpo:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": "Termo de busca vazio.",
            "mensagem_humana": "Qual arquivo você gostaria que eu procurasse, Henry?",
        }

    if pasta.lower().strip() in {"todas", "tudo", "geral", ""}:
        diretorios_busca = [
            PASTAS_COMUNS["downloads"],
            PASTAS_COMUNS["documentos"],
            PASTAS_COMUNS["desktop"],
            PASTAS_COMUNS["projeto"],
        ]
    else:
        alvo = _resolver_pasta(pasta)
        if not alvo.exists() or not alvo.is_dir():
            return {
                "sucesso": False,
                "verificado": False,
                "erro": f"A pasta '{pasta}' não foi encontrada para pesquisa.",
                "mensagem_humana": f"Não encontrei a pasta {pasta} para pesquisar.",
            }
        diretorios_busca = [alvo]

    encontrados: list[dict[str, Any]] = []
    vistos: set[str] = set()

    for base in diretorios_busca:
        if not base.exists() or not base.is_dir():
            continue
        try:
            for item in base.iterdir():
                if len(encontrados) >= limite:
                    break
                caminho_str = str(item.resolve())
                if caminho_str in vistos:
                    continue
                if termo_limpo in item.name.lower():
                    vistos.add(caminho_str)
                    encontrados.append({
                        "nome": item.name,
                        "caminho": caminho_str,
                        "tipo": "diretorio" if item.is_dir() else "arquivo",
                        "tamanho_bytes": item.stat().st_size if item.is_file() else 0,
                    })
                # Busca até 1 nível de subpasta sem travar em node_modules/.git/.venv
                if item.is_dir() and item.name not in {".git", ".venv", "node_modules", "__pycache__", ".godot"}:
                    try:
                        for sub in item.iterdir():
                            if len(encontrados) >= limite:
                                break
                            sub_str = str(sub.resolve())
                            if sub_str not in vistos and termo_limpo in sub.name.lower():
                                vistos.add(sub_str)
                                encontrados.append({
                                    "nome": sub.name,
                                    "caminho": sub_str,
                                    "tipo": "diretorio" if sub.is_dir() else "arquivo",
                                    "tamanho_bytes": sub.stat().st_size if sub.is_file() else 0,
                                })
                    except Exception:
                        continue
        except Exception:
            continue

    if not encontrados:
        return {
            "sucesso": True,
            "verificado": True,
            "termo": termo,
            "total_encontrados": 0,
            "arquivos": [],
            "evidencias": {"termo": termo, "total_encontrados": 0},
            "mensagem_humana": f"Pesquisei nas suas pastas, mas não encontrei nenhum arquivo com '{termo}', Henry.",
        }

    nomes = ", ".join(a["nome"] for a in encontrados[:4])
    return {
        "sucesso": True,
        "verificado": True,
        "termo": termo,
        "total_encontrados": len(encontrados),
        "arquivos": encontrados,
        "evidencias": {
            "termo": termo,
            "total_encontrados": len(encontrados),
            "primeiro_resultado": encontrados[0]["caminho"],
        },
        "mensagem_humana": f"Encontrei {len(encontrados)} arquivo(s) para '{termo}': {nomes}.",
    }


def ler_arquivo(caminho: str, max_linhas: int = 150) -> dict[str, Any]:
    """Lê o conteúdo textual de um arquivo com proteção a arquivos secretos."""
    p = Path(caminho).resolve()

    # Proteção de segurança obrigatória (Regra 2 da especificação)
    nome_lower = p.name.lower()
    if any(prot in nome_lower for prot in ARQUIVOS_PROTEGIDOS):
        return {
            "sucesso": False,
            "verificado": False,
            "erro": "Acesso negado: este arquivo contém credenciais ou segredos protegidos.",
            "mensagem_humana": "Por segurança, não posso ler arquivos que contenham credenciais ou chaves secretas, Henry.",
        }

    if not p.exists() or not p.is_file():
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Arquivo '{caminho}' não encontrado.",
            "mensagem_humana": f"Não encontrei o arquivo '{p.name}', Henry.",
        }

    try:
        linhas = p.read_text(encoding="utf-8", errors="replace").splitlines()
        conteudo = "\n".join(linhas[:max_linhas])
        truncado = len(linhas) > max_linhas
        return {
            "sucesso": True,
            "verificado": True,
            "caminho": str(p),
            "total_linhas": len(linhas),
            "truncado": truncado,
            "conteudo": conteudo,
            "evidencias": {"caminho": str(p), "total_linhas": len(linhas)},
            "mensagem_humana": f"Li o arquivo {p.name} ({len(linhas)} linhas).",
        }
    except Exception as e:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Erro ao ler arquivo: {str(e)}",
            "mensagem_humana": f"Não consegui ler o arquivo {p.name}: {str(e)}",
        }


def criar_arquivo(caminho: str, conteudo: str = "", pasta: str = "documentos") -> dict[str, Any]:
    """Cria ou escreve um arquivo de texto e VERIFICA no sistema de arquivos se foi gravado."""
    caminho_limpo = caminho.strip().strip("\"'")
    if not caminho_limpo:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": "Nome do arquivo não informado.",
            "mensagem_humana": "Qual nome você gostaria de dar ao arquivo, Henry?",
        }

    p = Path(caminho_limpo)
    if not p.is_absolute():
        dir_base = _resolver_pasta(pasta)
        p = (dir_base / p).resolve()
    else:
        p = p.resolve()

    nome_lower = p.name.lower()
    if any(prot in nome_lower for prot in ARQUIVOS_PROTEGIDOS):
        return {
            "sucesso": False,
            "verificado": False,
            "erro": "Operação bloqueada: não é permitido sobrescrever arquivos de credenciais.",
            "mensagem_humana": "Não posso criar ou sobrescrever arquivos sensíveis de configuração, Henry.",
        }

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(conteudo, encoding="utf-8")

        # Verificação pós-condição real no disco
        existe = p.exists() and p.is_file()
        tamanho = p.stat().st_size if existe else -1
        conteudo_lido = p.read_text(encoding="utf-8") if existe else None
        verificado = existe and (conteudo_lido == conteudo)

        if not verificado:
            return {
                "sucesso": False,
                "verificado": False,
                "erro": f"O arquivo '{p}' não pôde ser verificado no disco após a escrita.",
                "mensagem_humana": f"Tentei criar o arquivo {p.name}, mas não consegui confirmar a gravação no disco.",
            }

        return {
            "sucesso": True,
            "verificado": True,
            "caminho": str(p),
            "evidencias": {
                "caminho": str(p),
                "bytes_gravados": tamanho,
                "existe_no_disco": True,
            },
            "mensagem_humana": f"Pronto, criei o arquivo {p.name} em {p.parent.name}.",
        }
    except Exception as e:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Erro ao criar arquivo '{p.name}': {e}",
            "mensagem_humana": f"Não consegui criar o arquivo {p.name}: {e}",
        }


def mover_para_lixeira(caminho: str) -> dict[str, Any]:
    """Move um arquivo para a Lixeira do Windows (ação reversível) e VERIFICA se saiu do local original."""
    p = Path(caminho).resolve()
    if not p.exists():
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Arquivo '{caminho}' não encontrado para mover para a lixeira.",
            "mensagem_humana": f"Não encontrei o arquivo '{p.name}' para enviar à Lixeira, Henry.",
        }

    caminho_escapado = str(p).replace("'", "''")
    ps_cmd = (
        "Add-Type -AssemblyName Microsoft.VisualBasic; "
        f"[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile('{caminho_escapado}', 'OnlyErrorDialogs', 'SendToRecycleBin');"
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=6.0,
        )
        foi_removido = not p.exists()
        if res.returncode == 0 and foi_removido:
            return {
                "sucesso": True,
                "verificado": True,
                "evidencias": {
                    "caminho_original": str(p),
                    "removido_do_diretorio": True,
                },
                "mensagem": f"'{p.name}' foi movido para a Lixeira do Windows com segurança.",
                "mensagem_humana": f"Pronto, movi '{p.name}' para a Lixeira do Windows.",
            }
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Falha ao mover para a lixeira: {res.stderr.strip() or 'O arquivo permaneceu no diretório.'}",
            "mensagem_humana": f"Não consegui mover '{p.name}' para a Lixeira.",
        }
    except Exception as e:
        return {
            "sucesso": False,
            "verificado": False,
            "erro": f"Erro: {str(e)}",
            "mensagem_humana": f"Ocorreu um erro ao tentar mover '{p.name}' para a Lixeira.",
        }


# ─── Registro das Ferramentas ──────────────────────────────────

FERRAMENTAS_ARQUIVOS = [
    Ferramenta(
        nome="listar_arquivos",
        descricao="Lista os arquivos recentes em uma pasta como 'downloads', 'documentos' ou 'desktop'.",
        risco=Risco.VERDE,
        executar=listar_arquivos,
        frase=lambda pasta="downloads", **kwargs: f"listar os arquivos da pasta '{pasta}'",
    ),
    Ferramenta(
        nome="abrir_pasta",
        descricao="Abre uma pasta do computador no Explorador de Arquivos do Windows (ex: downloads, documentos, desktop, projeto).",
        risco=Risco.AMARELO,
        executar=abrir_pasta,
        frase=lambda pasta="downloads", **kwargs: f"abrir a pasta '{pasta}' no Explorador de Arquivos",
    ),
    Ferramenta(
        nome="pesquisar_arquivos",
        descricao="Pesquisa arquivos ou pastas pelo nome nas pastas do usuário (Downloads, Documentos, Desktop).",
        risco=Risco.VERDE,
        executar=pesquisar_arquivos,
        frase=lambda termo, pasta="todas", **kwargs: f"pesquisar arquivos contendo '{termo}'",
    ),
    Ferramenta(
        nome="ler_arquivo",
        descricao="Lê o conteúdo de um arquivo de texto, código ou documento legível.",
        risco=Risco.VERDE,
        executar=ler_arquivo,
        frase=lambda caminho, **kwargs: f"ler o conteúdo do arquivo '{caminho}'",
    ),
    Ferramenta(
        nome="criar_arquivo",
        descricao="Cria um novo arquivo de texto com o conteúdo informado e verifica a gravação no disco.",
        risco=Risco.AMARELO,
        executar=criar_arquivo,
        frase=lambda caminho, **kwargs: f"criar o arquivo '{caminho}'",
    ),
    Ferramenta(
        nome="mover_para_lixeira",
        descricao="Move um arquivo para a Lixeira do Windows (ação reversível, nunca apaga definitivamente).",
        risco=Risco.AMARELO,
        executar=mover_para_lixeira,
        frase=lambda caminho, **kwargs: f"mover o arquivo '{caminho}' para a Lixeira do Windows",
    ),
]
