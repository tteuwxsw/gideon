"""Bateria de testes do Subsistema de Voz da Gideon (Fase 5)."""

import asyncio
import httpx
from gideon.servidor import app, TOKEN_LOCAL
from gideon.voz.ouvido import OuvinteVoz
from gideon.voz.fala import SintetizadorVoz


def test_extracao_wake_word():
    print("[1/3] Testando detecção e extração de Wake Word 'Gideon'...")
    # Cria instância sem carregar modelo pesado para teste rápido de regex
    ouvinte = object.__new__(OuvinteVoz)

    frases_teste = [
        ("Gideon, que horas são?", True, "que horas são?"),
        ("Gideon preciso de ajuda", True, "preciso de ajuda"),
        ("Por favor gideon, qual o clima hoje?", True, "qual o clima hoje?"),
        ("gideon", True, ""),
        ("Olá computador, como vai?", False, "Olá computador, como vai?"),
        ("Guideon me mostre as notícias", True, "me mostre as notícias"),
    ]

    for frase, esperado_tem, esperado_cmd in frases_teste:
        tem, cmd = ouvinte.extrair_wake_word(frase)
        assert tem == esperado_tem, f"Falha na detecção para: '{frase}'"
        assert cmd == esperado_cmd, f"Comando incorreto: '{cmd}' (esperava '{esperado_cmd}')"

    print("  -> Extração de Wake Word: OK (100% de precisão nos padrões)")


def test_sintetizador_eventos():
    print("[2/3] Testando emissão de eventos do Sintetizador...")
    eventos_capturados = []

    def callback(ev):
        eventos_capturados.append(ev)

    sintetizador = SintetizadorVoz(callback_evento=callback)
    # Testa fala rápida
    sintetizador.falar("Teste.")

    tipos = [e["tipo"] for e in eventos_capturados]
    assert "fala_inicio" in tipos, "Deveria emitir fala_inicio"
    assert "fala_fim" in tipos, "Deveria emitir fala_fim"
    print(f"  -> Eventos emitidos para o avatar: {tipos}")


async def test_api_voz_endpoints():
    print("[3/3] Testando controle da escuta de voz via API...")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Verifica status inicial
        res = await client.get("/api/voz/status", headers={"x-gideon-token": TOKEN_LOCAL})
        assert res.status_code == 200
        assert res.json()["ativa"] is False

        # 2. Inicia voz
        res = await client.post("/api/voz/iniciar", headers={"x-gideon-token": TOKEN_LOCAL})
        assert res.status_code == 200

        # 3. Verifica status ativa
        res = await client.get("/api/voz/status", headers={"x-gideon-token": TOKEN_LOCAL})
        assert res.json()["ativa"] is True

        # 4. Pausa voz
        res = await client.post("/api/voz/parar", headers={"x-gideon-token": TOKEN_LOCAL})
        assert res.status_code == 200

        # 5. Verifica status inativa
        res = await client.get("/api/voz/status", headers={"x-gideon-token": TOKEN_LOCAL})
        assert res.json()["ativa"] is False

    print("  -> Endpoints de controle da voz: OK")


async def principal():
    test_extracao_wake_word()
    test_sintetizador_eventos()
    await test_api_voz_endpoints()
    print("\n=======================================================")
    print("  SUBSISTEMA DE VOZ DA GIDEON VALIDADO COM SUCESSO!")
    print("=======================================================\n")


if __name__ == "__main__":
    asyncio.run(principal())
