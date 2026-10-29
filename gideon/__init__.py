"""Gideon - assistente pessoal local para Windows e Linux."""

from gideon.versao import VERSAO

__version__ = VERSAO


def main():
    """Ponto de entrada do comando `gideon`."""
    from gideon.supervisor import main as supervisor_main
    return supervisor_main()
