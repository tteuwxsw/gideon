"""Caminhos compartilhados da Gideon (dados pessoais ficam sempre em `dados/`, fora do Git)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
INSTALL_DIR = Path(sys.executable).resolve().parent if FROZEN else RESOURCE_DIR
ROOT_DIR = RESOURCE_DIR

if os.environ.get("GIDEON_DATA_DIR"):
    DADOS_DIR = Path(os.environ["GIDEON_DATA_DIR"])
elif os.name != "nt":
    # No Linux, desenvolvimento, CLI e serviço systemd precisam compartilhar
    # exatamente o mesmo runtime. Isso também segue o padrão XDG do sistema.
    DADOS_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "gideon"
elif FROZEN:
    DADOS_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Gideon" / "dados"
else:
    DADOS_DIR = ROOT_DIR / "dados"

WEB_DIR = RESOURCE_DIR / "gideon" / "web"
MODELOS_DIR = DADOS_DIR / "modelos"
LOG_DIR = DADOS_DIR

# Habilidades que acompanham o projeto (guias de como fazer as coisas)
HABILIDADES_EMBUTIDAS_DIR = RESOURCE_DIR / "habilidades"
# Habilidades que o Henry ensinou (pessoais, fora do Git)
HABILIDADES_USUARIO_DIR = DADOS_DIR / "habilidades"

AUTOMACOES_DIR = DADOS_DIR / "automacoes"
AUTOMACOES_HISTORICO = DADOS_DIR / "automacoes_historico.jsonl"
PERFIL_ARQUIVO = DADOS_DIR / "perfil.md"
PERMISSOES_ARQUIVO = DADOS_DIR / "permissoes.json"
