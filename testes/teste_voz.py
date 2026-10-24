"""Bateria completa de testes do Subsistema Inteligente de Voz da Gideon."""

import asyncio
import threading
import time
import httpx
from gideon.servidor import app, TOKEN_LOCAL
from gideon.voz.comandos import (
    eh_encerramento_conversa,
    eh_interrupcao_barge_in,
    formatar_resposta_telemetria,
    interpretar_intencao_natural,
)
from gideon.voz.ouvido import OuvinteVoz
from gideon.voz.fala import SintetizadorVoz
from gideon.tools.sistema import obter_status_gpu


def test_extracao_wake_word():
    print("[1/6] Testando detecção de Wake Word e variações informais/fonéticas...")
    ouvinte = object.__new__(OuvinteVoz)
    ouvinte._palavras_ativacao_extras = []

    frases_teste = [
        ("Gideon, que horas são?", True, "que horas são?"),
        ("Olá, Gideon, como está meu computador?", True, "como está meu computador?"),
        ("Ei, Gideon, abre o Chrome", True, "abre o Chrome"),
        ("Oi, Gideon! Tudo bem?", True, "Tudo bem?"),
        ("Gideon, você está aí?", True, "__PRESENCA__"),
        ("gideon", True, ""),
        ("Oi Gidean, abre o navegador pra mim", True, "abre o navegador pra mim"),
        ("Guideon me mostre as notícias", True, "me mostre as notícias"),
        ("Olá computador, como vai?", False, "Olá computador, como vai?"),
    ]

    for frase, esperado_tem, esperado_cmd in frases_teste:
        tem, cmd = ouvinte.extrair_wake_word(frase)
        assert tem == esperado_tem, f"Falha na detecção para: '{frase}' (obteve {tem})"
        assert cmd == esperado_cmd, f"Comando incorreto em '{frase}': '{cmd}' (esperava '{esperado_cmd}')"

    print("  -> Wake Word e variações ('Gideon', 'Olá Gideon', 'Ei Gideon', 'Você está aí?'): OK")


def test_conversacao_natural_sem_comandos_rigidos():
    print("[2/6] Testando interpretação de linguagem natural sem comandos rígidos...")
    variacoes_navegador = [
        "abre o Chrome",
        "Abre o navegador pra mim",
        "Consegue abrir a internet?",
        "Quero entrar no Google",
        "Abre aí o Chrome, por favor",
    ]
    for frase in variacoes_navegador:
        intencao = interpretar_intencao_natural(frase)
        assert intencao is not None, f"Deveria compreender a intenção em: '{frase}'"
        assert intencao["acao"] == "abrir_programa", f"Ação incorreta para '{frase}': {intencao}"
        assert intencao["parametros"]["nome"] in {"chrome", "google"}

    print("  -> Todas as 5 variações naturais de abertura de navegador compreendidas: OK")


def test_fluxo_contextual_continua_e_hardware():
    print("[3/6] Testando conversação contínua contextual (Spotify -> Chase Atlantic e RAM -> GPU)...")
    contexto = {}

    # Fluxo 1: Spotify -> "Agora coloca uma música" -> "Coloca alguma coisa do Chase Atlantic"
    i1 = interpretar_intencao_natural("abre o Spotify", contexto)
    assert i1 and i1["acao"] == "abrir_programa" and i1["parametros"]["nome"] == "spotify"
    contexto.update(i1.get("novo_contexto", {}))

    i2 = interpretar_intencao_natural("Agora coloca uma música", contexto)
    assert i2 and i2["acao"] == "perguntar_midia"
    assert "O que você gostaria de ouvir" in i2["resposta_direta"]
    contexto.update(i2.get("novo_contexto", {}))

    i3 = interpretar_intencao_natural("Coloca alguma coisa do Chase Atlantic", contexto)
    assert i3 and i3["acao"] == "tocar_ou_pesquisar_midia"
    assert "Chase Atlantic" in i3["parametros"]["consulta"]
    contexto.update(i3.get("novo_contexto", {}))

    # Fluxo 2: "Quanto de memória RAM estou usando?" -> "E a placa de vídeo?"
    h1 = interpretar_intencao_natural("Quanto de memória RAM estou usando?", contexto)
    assert h1 and h1["acao"] == "obter_status_pc" and h1["foco_resposta"] == "ram"
    contexto.update(h1.get("novo_contexto", {}))

    h2 = interpretar_intencao_natural("E a placa de vídeo?", contexto)
    assert h2 and h2["acao"] == "obter_status_gpu" and h2["foco_resposta"] == "gpu"

    gpu_dados = obter_status_gpu()
    resposta_gpu = formatar_resposta_telemetria(gpu_dados, foco="gpu")
    assert "modelo" in gpu_dados and len(gpu_dados["modelo"]) > 0
    assert gpu_dados["modelo"] in resposta_gpu
    print(f"  -> Telemetria GPU detectada: {gpu_dados['modelo']} ({gpu_dados['vram']}): OK")


def test_barge_in_e_interrupcoes():
    print("[4/6] Testando sistema de Barge-In e interrupção durante a fala...")
    assert eh_interrupcao_barge_in("Gideon, espera") is True
    assert eh_interrupcao_barge_in("para") is True
    assert eh_interrupcao_barge_in("Obrigado, só isso") is False
    assert eh_encerramento_conversa("Obrigado, só isso") is True

    eventos = []
    sintetizador = SintetizadorVoz(callback_evento=lambda e: eventos.append(e))

    # Dispara interrupção após 250ms de uma fala longa
    def interromper_logo():
        time.sleep(0.25)
        sintetizador.interromper()

    threading.Thread(target=interromper_logo, daemon=True).start()
    concluiu = sintetizador.falar(
        "Esta é uma frase longa para testar se o sistema de barge in interrompe imediatamente a síntese vocal."
    )
    assert concluiu is False or sintetizador.foi_interrompida is True
    tipos = [e["tipo"] for e in eventos]
    assert "fala_inicio" in tipos and "fala_fim" in tipos
    print("  -> Interrupção de fala (Barge-In) e emissão de eventos: OK")


async def test_api_modos_e_configuracao():
    print("[5/6] Testando os 3 modos de escuta e configuração via API...")
    transport = httpx.ASGITransport(app=app)
    headers = {
        "x-gideon-token": TOKEN_LOCAL,
        "x-gideon-csrf": "1",
        "origin": "http://127.0.0.1:8000",
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # 1. Status inicial
        res = await client.get("/api/voz/status", headers=headers)
        assert res.status_code == 200
        dados = res.json()
        assert dados["modo_escuta"] == "ativacao_por_nome"

        # 2. Alterna para Modo 2 (conversa_continua) e Modo 3 (conversa_livre)
        for modo in ("conversa_continua", "conversa_livre", "ativacao_por_nome"):
            res_cfg = await client.post(
                "/api/voz/configurar",
                headers=headers,
                json={"modo_escuta": modo, "duracao_sessao": 30.0, "sensibilidade": 0.018},
            )
            assert res_cfg.status_code == 200
            assert res_cfg.json()["modo_escuta"] == modo

        # 3. Inicia e pausa escuta
        res = await client.post("/api/voz/iniciar", headers=headers)
        assert res.status_code == 200
        res = await client.get("/api/voz/status", headers=headers)
        assert res.json()["ativa"] is True

        res = await client.post("/api/voz/parar", headers=headers)
        assert res.status_code == 200
        res = await client.get("/api/voz/status", headers=headers)
        assert res.json()["ativa"] is False

    print("  -> Modos (ativacao_por_nome, conversa_continua, conversa_livre) e API: OK")


async def principal():
    test_extracao_wake_word()
    test_conversacao_natural_sem_comandos_rigidos()
    test_fluxo_contextual_continua_e_hardware()
    test_barge_in_e_interrupcoes()
    await test_api_modos_e_configuracao()
    print("\n=======================================================")
    print("  SISTEMA AVANCADO DE VOZ DA GIDEON VALIDADO (100%)!")
    print("=======================================================\n")


if __name__ == "__main__":
    asyncio.run(principal())
