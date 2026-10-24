"""Bateria de testes de validação da Gideon (Fase 1 + WebSocket + Protocolo)."""

import asyncio
import json
import httpx
from gideon.servidor import app, TOKEN_LOCAL
from gideon.persona import obter_prompt_sistema, EMOCOES_DISPONIVEIS
from gideon.protocolo import (
    TipoMensagem,
    ModoAvatar,
    Emocao,
    criar_evento,
    analisar_evento,
    extrair_emocoes_texto,
    limpar_emocoes_texto,
)


def test_persona():
    print("[1/5] Testando Persona da Gideon...")
    prompt = obter_prompt_sistema()
    assert "Gideon" in prompt, "Nome Gideon deve estar presente no prompt"
    assert "Henry" in prompt, "Nome Henry deve estar presente no prompt"
    assert "[EMOCAO:" in prompt, "Instruções de emoção devem estar presentes"
    assert len(EMOCOES_DISPONIVEIS) == 9, "Devem existir 9 emoções catalogadas"
    print("  -> Persona: OK")


def test_protocolo():
    print("[2/5] Testando Protocolo WebSocket...")
    # Testa criação de evento
    evento_json = criar_evento("emocao", nome="curiosidade", intensidade=0.8)
    dados = analisar_evento(evento_json)
    assert dados["tipo"] == "emocao"
    assert dados["dados"]["nome"] == "curiosidade"
    assert dados["dados"]["intensidade"] == 0.8

    # Testa extração de emoções de texto
    texto = "[EMOCAO:amigavel] Olá Henry! [EMOCAO:humor] Que bom te ver."
    emocoes = extrair_emocoes_texto(texto)
    assert len(emocoes) == 2
    assert emocoes[0][1] == "amigavel"
    assert emocoes[1][1] == "humor"

    # Testa limpeza de emoções
    texto_limpo = limpar_emocoes_texto(texto)
    assert "[EMOCAO:" not in texto_limpo
    assert "Olá Henry! Que bom te ver." in texto_limpo
    print("  -> Protocolo: OK")


async def test_servidor_status():
    print("[3/5] Testando Endpoints HTTP do Servidor...")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Sem token -> deve falhar com 401
        res = await client.get("/api/status")
        assert res.status_code == 401, f"Deveria ser 401, foi {res.status_code}"

        # 2. Com token correto -> deve retornar 200 e dados da Gideon
        res = await client.get("/api/status", headers={"x-gideon-token": TOKEN_LOCAL})
        assert res.status_code == 200
        dados = res.json()
        assert dados["nome"] == "Gideon"
        assert dados["status"] == "online"
        print(f"  -> Status: OK ({dados})")


async def test_chat_streaming():
    print("[4/5] Testando Fluxo de Chat com Streaming e Custo...")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST",
            "/api/chat/stream",
            json={"mensagem": "Olá Gideon, apenas confirme que me ouve em uma frase curta."},
            headers={"x-gideon-token": TOKEN_LOCAL},
        ) as response:
            assert response.status_code == 200
            chunks = []
            fim_evento = None

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    ev = json.loads(line[6:])
                    if ev["tipo"] == "chunk":
                        chunks.append(ev["texto"])
                    elif ev["tipo"] == "fim":
                        fim_evento = ev

            resposta_completa = "".join(chunks)
            print(f"  -> Resposta recebida: {resposta_completa.strip()}")
            assert len(resposta_completa) > 0, "Resposta não pode ser vazia"
            assert fim_evento is not None, "Evento final com métricas deve existir"
            assert fim_evento["total_tokens"] > 0, "Total de tokens deve ser maior que 0"
            assert fim_evento["custo_estimado"] >= 0, "Custo estimado deve existir"
            print(f"  -> Métricas: {fim_evento['total_tokens']} tokens, Custo: ${fim_evento['custo_estimado']:.6f} USD")
            print("  -> Chat streaming: OK")


async def test_portao_fase1():
    print("[5/5] Testando Portão da Fase 1 (10 trocas de mensagens consecutivas)...")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Limpa histórico inicial
        await client.post("/api/chat/limpar", headers={"x-gideon-token": TOKEN_LOCAL})

        perguntas = [
            "1. Diga a palavra 'Alfa'",
            "2. Qual o número depois de 1?",
            "3. O que é mais rápido: som ou luz?",
            "4. Qual a capital da França?",
            "5. Qual a cor do céu?",
            "6. Quanto é 2 + 2?",
            "7. Diga a letra 'B'",
            "8. Qual o planeta mais próximo do Sol?",
            "9. Qual o dia depois de segunda?",
            "10. Diga 'Concluído com sucesso'",
        ]

        for i, pergunta in enumerate(perguntas, 1):
            async with client.stream(
                "POST",
                "/api/chat/stream",
                json={"mensagem": pergunta},
                headers={"x-gideon-token": TOKEN_LOCAL},
            ) as response:
                assert response.status_code == 200
                chunks = []
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        ev = json.loads(line[6:])
                        if ev["tipo"] == "chunk":
                            chunks.append(ev["texto"])
                resp = "".join(chunks).strip()
                print(f"    Troca {i:02d}/10: '{pergunta}' -> '{resp[:40]}...'")

        # Verifica histórico
        res = await client.get("/api/status", headers={"x-gideon-token": TOKEN_LOCAL})
        dados = res.json()
        assert dados["mensagens_no_historico"] == 20, f"Deveriam ter 20 mensagens (10 user + 10 assistant), tem {dados['mensagens_no_historico']}"
        print("  -> Portão da Fase 1: 10 trocas concluídas com sucesso e histórico verificado!")


async def principal():
    test_persona()
    test_protocolo()
    await test_servidor_status()
    await test_chat_streaming()
    await test_portao_fase1()
    print("\n=======================================================")
    print("  TODOS OS TESTES PASSARAM! GIDEON FASE 1 APROVADA!")
    print("=======================================================\n")


if __name__ == "__main__":
    asyncio.run(principal())
