"""Testes isolados de autenticacao e integracao do runtime Windows."""

import http.cookiejar
import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import gideon.gate as gate
from gideon.auth import TOKEN_PREFIX, obter_ou_criar_token, token_valido
from gideon.executor import EstadoExecucao, ExecutorConfiavel
from gideon.supervisor import _montar_comando_app
from gideon.voz.comandos import detectar_comando_sistema, resposta_confirmacao
from gideon.gate import (
    Ferramenta,
    RegistroFerramentas,
    Risco,
    ativar_parada_emergencia,
    retomar_execucao,
)
from gideon.tools.sistema import FERRAMENTAS_SISTEMA
from gideon.versao import VERSAO


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


def testar_comando_app() -> None:
    comando = _montar_comando_app(
        Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
        Path("C:/Gideon/app-profile"),
        "token-descartavel",
    )
    assert comando[0].endswith("msedge.exe")
    assert "--app=http://127.0.0.1:8000/#token=token-descartavel" in comando
    assert "--disable-background-mode" in comando
    assert not any("auth_token.txt" in parte for parte in comando)
    print("[OK] Comando do aplicativo usa perfil dedicado e token descartavel.")


def testar_comandos_sensiveis() -> None:
    assert detectar_comando_sistema("atualize seus sistemas") == "atualizar_sistemas"
    assert detectar_comando_sistema("verifique se ha atualizacoes") == "atualizar_sistemas"
    assert detectar_comando_sistema("reinicie a Gideon") == "reiniciar_gideon"
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
    assert riscos["reiniciar_gideon"] is Risco.VERMELHO
    assert riscos["atualizar_sistemas"] is Risco.VERMELHO
    print("[OK] Atualizacao e encerramento permanecem protegidos pelo portao vermelho.")


def testar_portao_fail_closed() -> None:
    catalogo = RegistroFerramentas()
    chamadas: list[str] = []
    catalogo.registrar(Ferramenta(
        nome="acao_amarela",
        descricao="Acao de teste",
        risco=Risco.AMARELO,
        executar=lambda: chamadas.append("executada") or {
            "sucesso": True,
            "verificado": True,
            "evidencias": {"teste": True},
        },
        frase=lambda: "executar acao de teste",
    ))
    catalogo.registrar(Ferramenta(
        nome="retorno_invalido",
        descricao="Retorno sem prova",
        risco=Risco.AMARELO,
        executar=lambda: {},
        frase=lambda: "executar retorno invalido",
    ))

    executor = ExecutorConfiavel(catalogo)
    negado_catalogo = catalogo.executar("acao_amarela", {})
    assert negado_catalogo["ok"] is False
    assert chamadas == []

    autorizado_catalogo = catalogo.executar(
        "acao_amarela",
        {},
        confirmar_fn=lambda _acao: True,
    )
    assert autorizado_catalogo["ok"] is True

    chamadas.clear()
    pendente = executor.executar("acao_amarela")
    assert pendente.estado is EstadoExecucao.NEEDS_CONFIRMATION
    assert chamadas == []

    autorizado = executor.executar("acao_amarela", auto_amarelo=True)
    assert autorizado.estado is EstadoExecucao.SUCCESS
    assert autorizado.verificado is True

    invalido = executor.executar("retorno_invalido", auto_amarelo=True)
    assert invalido.estado is EstadoExecucao.FAILED
    assert invalido.verificado is False

    ativar_parada_emergencia()
    try:
        bloqueado = executor.executar("acao_amarela", auto_amarelo=True)
        assert bloqueado.estado is EstadoExecucao.FAILED
    finally:
        retomar_execucao()
    print("[OK] Executor exige autorizacao, evidencia e respeita a parada de emergencia.")


def testar_gasto_persistente() -> None:
    caminho_original = gate.ARQUIVO_GASTO
    estado_original = dict(gate._gasto_hoje)
    try:
        with tempfile.TemporaryDirectory() as temporario:
            gate.ARQUIVO_GASTO = Path(temporario) / "gasto.json"
            gate._gasto_hoje.update(dia="", usd=0.0)
            gate.somar_gasto(0.25)
            assert gate.gasto_diario_atual() == 0.25

            gate._gasto_hoje.update(dia="", usd=0.0)
            assert gate.gasto_diario_atual() == 0.25
            try:
                gate.somar_gasto(-1.0)
                raise AssertionError("Custo negativo deveria ser rejeitado.")
            except ValueError:
                pass
    finally:
        gate.ARQUIVO_GASTO = caminho_original
        gate._gasto_hoje.update(estado_original)
    print("[OK] Limite de gasto usa acumulador persistente e rejeita valores invalidos.")


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
    assert status["versao"] == VERSAO

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
    testar_comando_app()
    testar_comandos_sensiveis()
    testar_riscos_do_runtime()
    testar_portao_fail_closed()
    testar_gasto_persistente()
    testar_servidor_ativo()
    print("\nPortao do runtime da Gideon aprovado.")
