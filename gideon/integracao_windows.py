"""Script para registrar a Gideon na inicialização do Windows de forma 100% silenciosa.
Usa pythonw.exe para rodar sem janela preta de terminal.
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
VENV_PYTHONW = ROOT_DIR / ".venv" / "Scripts" / "pythonw.exe"
PASTA_STARTUP = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
BAT_STARTUP = PASTA_STARTUP / "gideon_iniciar.vbs"


def instalar_inicializacao() -> bool:
    """Cria um script VBScript na pasta Startup do Windows para inicialização invisível."""
    if not VENV_PYTHONW.exists():
        print(f"Erro: pythonw.exe não encontrado em {VENV_PYTHONW}")
        return False

    # VBScript executa o comando com janela oculta (parâmetro 0)
    conteudo_vbs = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{ROOT_DIR}"
WshShell.Run """{VENV_PYTHONW}""" & " -m gideon.supervisor", 0, False
'''

    try:
        BAT_STARTUP.write_text(conteudo_vbs, encoding="utf-8")
        print(f"✅ Gideon integrada à inicialização do Windows com sucesso!")
        print(f"   Arquivo criado: {BAT_STARTUP}")
        print("   Ao ligar o PC, ela acordará automaticamente sem nenhuma janela aberta.")
        return True
    except Exception as e:
        print(f"Erro ao registrar inicialização: {e}")
        return False


def desinstalar_inicializacao() -> bool:
    """Remove a Gideon da inicialização do Windows."""
    if BAT_STARTUP.exists():
        BAT_STARTUP.unlink()
        print("✅ Gideon removida da inicialização do Windows.")
        return True
    print("Gideon não estava registrada na inicialização.")
    return True


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "remover":
        desinstalar_inicializacao()
    else:
        instalar_inicializacao()
