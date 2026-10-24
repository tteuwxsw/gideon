"""Ferramentas de gerenciamento e leitura de arquivos para a Gideon."""

import os
import subprocess
from pathlib import Path
from typing import Any

from gideon.gate import Ferramenta, Risco

PASTAS_COMUNS = {
    "downloads": Path.home() / "Downloads",
    "documentos": Path.home() / "Documents",
    "desktop": Path.home() / "Desktop",
    "area de trabalho": Path.home() / "Desktop",
    "projeto": Path(__file__).resolve().parent.parent.parent,
}

ARQUIVOS_PROTEGIDOS = [".env", "id_rsa", "id_ed25519", "auth_token.txt", "chave", "password", "token"]


def listar_arquivos(pasta: str = "downloads", limite: int = 20) -> dict[str, Any]:
    """Lista os arquivos recentes dentro de uma pasta permitida do usuário."""
    caminho = PASTAS_COMUNS.get(pasta.lower().strip(), Path(pasta))

    if not caminho.exists() or not caminho.is_dir():
        return {"erro": f"A pasta '{pasta}' não foi encontrada ou não é um diretório válido."}

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
        return {
            "pasta": str(caminho),
            "total_encontrados": len(entradas),
            "arquivos": itens,
        }
    except Exception as e:
        return {"erro": f"Erro ao acessar '{pasta}': {str(e)}"}


def ler_arquivo(caminho: str, max_linhas: int = 150) -> dict[str, Any]:
    """Lê o conteúdo textual de um arquivo com proteção a arquivos secretos."""
    p = Path(caminho).resolve()

    # Proteção de segurança obrigatória (Regra 2 da especificação)
    nome_lower = p.name.lower()
    if any(prot in nome_lower for prot in ARQUIVOS_PROTEGIDOS):
        return {"erro": "Acesso negado: este arquivo contém credenciais ou segredos protegidos."}

    if not p.exists() or not p.is_file():
        return {"erro": f"Arquivo '{caminho}' não encontrado."}

    try:
        linhas = p.read_text(encoding="utf-8", errors="replace").splitlines()
        conteudo = "\n".join(linhas[:max_linhas])
        truncado = len(linhas) > max_linhas
        return {
            "caminho": str(p),
            "total_linhas": len(linhas),
            "truncado": truncado,
            "conteudo": conteudo,
        }
    except Exception as e:
        return {"erro": f"Erro ao ler arquivo: {str(e)}"}


def mover_para_lixeira(caminho: str) -> dict[str, Any]:
    """Move um arquivo para a Lixeira do Windows (ação reversível)."""
    p = Path(caminho).resolve()
    if not p.exists():
        return {"erro": f"Arquivo '{caminho}' não encontrado para mover para a lixeira."}

    # Usa a API nativa do Windows para enviar à lixeira (reciclável)
    caminho_escapado = str(p).replace("'", "''")
    ps_cmd = f"""
    Add-Type -AssemblyName Microsoft.VisualBasic;
    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile('{caminho_escapado}', 'OnlyErrorDialogs', 'SendToRecycleBin');
    """
    try:
        res = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True)
        if res.returncode == 0:
            return {"sucesso": True, "mensagem": f"'{p.name}' foi movido para a Lixeira do Windows com segurança."}
        return {"erro": f"Falha ao mover para a lixeira: {res.stderr}"}
    except Exception as e:
        return {"erro": f"Erro: {str(e)}"}


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
        nome="ler_arquivo",
        descricao="Lê o conteúdo de um arquivo de texto, código ou documento legível.",
        risco=Risco.VERDE,
        executar=ler_arquivo,
        frase=lambda caminho, **kwargs: f"ler o conteúdo do arquivo '{caminho}'",
    ),
    Ferramenta(
        nome="mover_para_lixeira",
        descricao="Move um arquivo para a Lixeira do Windows (ação reversível, nunca apaga definitivamente).",
        risco=Risco.AMARELO,
        executar=mover_para_lixeira,
        frase=lambda caminho, **kwargs: f"mover o arquivo '{caminho}' para a Lixeira do Windows",
    ),
]
