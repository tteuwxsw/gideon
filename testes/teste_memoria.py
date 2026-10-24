"""Bateria de testes de validação da Memória Permanente da Gideon (Fase 2)."""

import asyncio
import json
import httpx
from pathlib import Path
from gideon.memoria import Memoria, DB_PATH
from gideon.servidor import app, TOKEN_LOCAL


def test_persistencia_reiniciar():
    print("[1/4] Testando persistência da memória após reinício...")
    # 1. Instância 1: grava fato
    m1 = Memoria()
    m1.salvar_fato("traje", "Uniforme com emissor taquiônico")
    del m1

    # 2. Instância 2 (simulando fechar e reabrir o programa): lê fato
    m2 = Memoria()
    valor = m2.obter_fato("traje")
    assert valor == "Uniforme com emissor taquiônico", f"Valor incorreto: {valor}"
    print(f"  -> Persistência confirmada: traje = '{valor}'")


def test_busca_fts_sem_acento():
    print("[2/4] Testando busca FTS5 insensível a acentuação...")
    m = Memoria()
    m.gravar_mensagem("voce", "Precisamos discutir a reunião sobre o acelerador de partículas.")
    m.gravar_mensagem("assistente", "Entendido, agendando a reunião.")

    # Busca com a palavra SEM acento: "reuniao"
    resultados = m.buscar_historico("reuniao")
    assert len(resultados) > 0, "A busca sem acento 'reuniao' deveria ter encontrado 'reunião'!"
    print(f"  -> Busca FTS5 encontrou {len(resultados)} trechos para 'reuniao'")


async def test_fluxo_chat_com_memoria():
    print("[3/4] Testando fluxo completo de chat com comandos de memória...")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Comando explícito: "lembra que meu restaurante favorito é Ostradamus"
        async with client.stream(
            "POST",
            "/api/chat/stream",
            json={"mensagem": "lembra que meu restaurante favorito é Ostradamus"},
            headers={"x-gideon-token": TOKEN_LOCAL},
        ) as response:
            assert response.status_code == 200
            texto = ""
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    ev = json.loads(line[6:])
                    if ev["tipo"] == "chunk":
                        texto += ev["texto"]
            print(f"  -> Resposta ao 'lembra que': {texto.strip()}")
            assert "Ostradamus" in texto

        # 2. Verifica se o fato está na API de fatos
        res = await client.get("/api/memoria/fatos", headers={"x-gideon-token": TOKEN_LOCAL})
        assert res.status_code == 200
        fatos = res.json()["fatos"]
        chaves = [f["chave"] for f in fatos]
        assert any("restaurante" in c for c in chaves), f"Chave não encontrada em: {chaves}"
        print("  -> Fato confirmado na API de fatos!")

        # 3. Pergunta para a Gideon usando o Cérebro + Memória Injetada
        async with client.stream(
            "POST",
            "/api/chat/stream",
            json={"mensagem": "Qual é o meu restaurante favorito que te falei?"},
            headers={"x-gideon-token": TOKEN_LOCAL},
        ) as response:
            assert response.status_code == 200
            resposta_cerebro = ""
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    ev = json.loads(line[6:])
                    if ev["tipo"] == "chunk":
                        resposta_cerebro += ev["texto"]
            print(f"  -> Gideon lembrou via Cérebro: {resposta_cerebro.strip()}")
            assert "Ostradamus" in resposta_cerebro, "Gideon deve citar o restaurante lembrado!"


async def test_esquecer_fato():
    print("[4/4] Testando comando 'esquece'...")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Grava fato temporário
        m = Memoria()
        m.salvar_fato("senha secreta", "123456")

        # Pede para esquecer
        res = await client.delete("/api/memoria/fatos/senha secreta", headers={"x-gideon-token": TOKEN_LOCAL})
        assert res.status_code == 200
        assert m.obter_fato("senha secreta") is None
        print("  -> Fato esquecido e apagado com sucesso!")


async def principal():
    test_persistencia_reiniciar()
    test_busca_fts_sem_acento()
    await test_fluxo_chat_com_memoria()
    await test_esquecer_fato()
    print("\n=======================================================")
    print("  PORTÃO DA FASE 2 APROVADO! MEMÓRIA PERMANENTE ATIVA!")
    print("=======================================================\n")


if __name__ == "__main__":
    asyncio.run(principal())
