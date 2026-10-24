"""Gideon — Assistente Pessoal com Interface Holográfica."""

__version__ = "0.2.0"


def main():
    """Ponto de entrada do comando `gideon`."""
    from gideon.servidor import main as servidor_main
    servidor_main()
