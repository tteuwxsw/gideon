"""Testes isolados do acionamento por saudacao da Gideon."""

import json

from gideon.voz.comandos import eh_pedido_abrir_interface
from gideon.voz.despertador import (
    identificar_saudacao,
    interpretar_resultado_vosk,
)


def testar_matcher_estrito() -> None:
    aceitas = {
        "Bom dia, Gideon!": "bom dia",
        "boa tarde gideon": "boa tarde",
        "BOA NOITE GIDEON": "boa noite",
    }
    for frase, esperado in aceitas.items():
        assert identificar_saudacao(frase) == esperado

    rejeitadas = (
        "Gideon",
        "oi Gideon",
        "bom dia",
        "bom dia Gideon abra o navegador",
        "boa noite minha Gideon",
        "a televisao disse bom dia Gideon agora",
    )
    for frase in rejeitadas:
        assert identificar_saudacao(frase) is None
    print("[OK] Somente as tres saudacoes exatas acionam a interface.")


def testar_alias_fonetico_vosk() -> None:
    payload = json.dumps({
        "text": "boa tarde gente viu",
        "result": [
            {"word": "boa", "conf": 0.98},
            {"word": "tarde", "conf": 0.97},
            {"word": "gente", "conf": 0.82},
            {"word": "viu", "conf": 0.78},
        ],
    })
    assert interpretar_resultado_vosk(payload) == "boa tarde"

    baixa_confianca = json.dumps({
        "text": "boa tarde gente viu",
        "result": [{"word": "boa", "conf": 0.30}],
    })
    assert interpretar_resultado_vosk(baixa_confianca) is None
    assert identificar_saudacao("boa tarde gente viu") is None
    print("[OK] Alias fonetico vale apenas para o Vosk e exige confianca minima.")

def testar_abertura_explicita_da_interface() -> None:
    aceitas = (
        "abre o app",
        "Abra o aplicativo pra mim",
        "mostre sua interface",
        "apareca na tela",
        "quero ver a Gideon",
    )
    for frase in aceitas:
        assert eh_pedido_abrir_interface(frase)
    assert not eh_pedido_abrir_interface("abre o Chrome")
    assert not eh_pedido_abrir_interface("abre um aplicativo")
    print("[OK] Pedido de voz abre somente a interface da propria Gideon.")



if __name__ == "__main__":
    testar_matcher_estrito()
    testar_abertura_explicita_da_interface()
    testar_alias_fonetico_vosk()
    print("\nPortao do Gideon Wake aprovado.")
