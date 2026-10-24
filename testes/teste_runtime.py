"""Testes isolados de autenticacao e integracao do runtime Windows."""

import http.cookiejar
import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from gideon.auth import TOKEN_PREFIX, obter_ou_criar_token, token_valido
from gideon.supervisor import (
    WS_EX_APPWINDOW,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    calcular_estilo_overlay,
)
from gideon.voz.comandos import detectar_comando_sistema, resposta_confirmacao
from gideon.gate import Risco
from gideon.tools.sistema import FERRAMENTAS_SISTEMA


def testar_token() -> None:
    with tempfile.TemporaryDirectory() as temporario:
        caminho = Path(temporario) / "auth_token.txt"
        caminho.write_text("token-antigo", encoding="utf-8")
        token = obter_ou_criar_token(caminho)
        assert token.startswith(TOKEN_PREFIX)
        assert token != "token-antigo"
        assert obter_ou_criar_token(caminho) == token
        assert token_valido(token, token)
        assert not token_valido("incorreto", token)
    print("[OK] Token local rotacionado e comparado com seguranca.")


def testar_estilo_overlay() -> None:
    novo = calcular_estilo_overlay(WS_EX_APPWINDOW)
    assert novo & WS_EX_TOOLWINDOW
    assert novo & WS_EX_NOACTIVATE
    assert not novo & WS_EX_APPWINDOW
    print("[OK] Estilo Win32 remove APPWINDOW e adiciona TOOLWINDOW/NOACTIVATE.")


def testar_comandos_sensiveis() -> None:
    assert detectar_comando_sistema("atualize seus sistemas") == "atualizar_sistemas"
    assert detectar_comando_sistema("verifique se ha atualizacoes") == "atualizar_sistemas"
    assert detectar_comando_sistema("pode encerrar a Gideon") == "encerrar_gideon"
    assert detectar_comando_sistema("qual e a versao?") is None
    assert resposta_confirmacao("Sim, confirmo") is True
    assert resposta_confirmacao("sim") is True
    assert resposta_confirmacao("agora nao") is False
    print("[OK] Comandos sensiveis exigem intencao explicita e confirmacao separada.")


def testar_riscos_do_runtime() -> None:
    riscos = {ferramenta.nome: ferramenta.risco for ferramenta in FERRAMENTAS_SISTEMA}
    assert riscos["obter_status_pc"] is Risco.VERDE
    assert riscos["encerrar_gideon"] is Risco.VERMELHO
    assert riscos["atualizar_sistemas"] is Risco.VERMELHO
    print("[OK] Atualizacao e encerramento permanecem protegidos pelo portao vermelho.")


def testar_servidor_ativo() -> None:
    if os.environ.get("GIDEON_TEST_SERVER") != "1":
        return

    token = (Path(__file__).resolve().parent.parent / "dados" / "auth_token.txt").read_text(
        encoding="utf-8"
    ).strip()
    cookies = http.cookiejar.CookieJar()
    cliente = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    login = urllib.request.Request(
        "http://127.0.0.1:8000/api/auth/login",
        data=json.dumps({"token": token}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Origin": "http://127.0.0.1:8000",
        },
        method="POST",
    )
    assert cliente.open(login, timeout=3).status == 200
    status = json.loads(cliente.open("http://127.0.0.1:8000/api/status", timeout=3).read())
    assert status["versao"] == "0.3.0"

    bloqueios = []
    for headers in ({}, {"Origin": "http://127.0.0.1:9999", "X-Gideon-CSRF": "1"}):
        requisicao = urllib.request.Request(
            "http://127.0.0.1:8000/api/chat/limpar",
            data=b"",
            headers=headers,
            method="POST",
        )
        try:
            cliente.open(requisicao, timeout=3)
        except urllib.error.HTTPError as erro:
            bloqueios.append(erro.code)
    assert bloqueios == [403, 403]
    print("[OK] Login local ativo e mutacoes sem origem/CSRF confiaveis foram bloqueadas.")


if __name__ == "__main__":
    testar_token()
    testar_estilo_overlay()
    testar_comandos_sensiveis()
    testar_riscos_do_runtime()
    testar_servidor_ativo()
    print("\nPortao do runtime da Gideon aprovado.")
