"""Opcoes seguras para processos internos que nao devem criar janelas."""

from __future__ import annotations

import os
import subprocess
from typing import Any


def opcoes_processo_oculto() -> dict[str, Any]:
    """Impede flashes de console em subprocessos internos no Windows."""
    if os.name != "nt":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        "startupinfo": startupinfo,
    }


def comando_powershell() -> str:
    """Prefere PowerShell 7 quando disponivel, com fallback nativo."""
    from shutil import which

    return which("pwsh.exe") or which("powershell.exe") or "powershell.exe"
