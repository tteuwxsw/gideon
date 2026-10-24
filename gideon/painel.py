"""Abre o painel local sem colocar o token nos logs HTTP."""

import urllib.parse
import webbrowser
from pathlib import Path

from gideon.auth import obter_ou_criar_token


ROOT_DIR = Path(__file__).resolve().parent.parent


def main() -> None:
    token = obter_ou_criar_token(ROOT_DIR / "dados" / "auth_token.txt")
    fragmento = urllib.parse.quote(token, safe="")
    webbrowser.open(f"http://127.0.0.1:8000/#token={fragmento}")


if __name__ == "__main__":
    main()
