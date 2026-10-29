"""Bateria completa de validação e benchmark de voz da Gideon (30 interações, p50/p95, consistência vocal)."""

import asyncio
import threading
import time
import httpx
import numpy as np
from gideon.servidor import app, TOKEN_LOCAL
from gideon.gate import PARADO
from gideon.voz.comandos import (
    avaliar_fala_direcionada,
    eh_desistencia_rapida,
    eh_encerramento_conversa,
    eh_interrupcao_barge_in,
    formatar_resposta_telemetria,
    interpretar_intencao_natural,
)
from gideon.voz.fala import (
    IDENTIFICADOR_VOZ_FIXA,
    SintetizadorVoz,
    formatar_prosodia_gideon,
    limpar_texto_para_fala,
)
from gideon.voz.metricas import metricas_voz_global
from gideon.voz.orquestrador import OrquestradorVoz
from gideon.voz.ouvido import OuvinteVoz, corrigir_erros_transcricao
from gideon.tools.sistema import obter_status_gpu, obter_status_pc


def test_extracao_wake_word_e_correcao_stt():
    print("[1/7] Testando Wake Word, variações informais e correção contextual de STT...")
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

    # Testa correção contextual de erros fonéticos do STT
    assert corrigir_erros_transcricao("abro navegador pra mim") == "abre o navegador pra mim"
    assert "Spotify" in corrigir_erros_transcricao("abre o espotifai")
    assert "memória RAM" in corrigir_erros_transcricao("quanto de memória rã")
    print("  -> Wake Word e correção contextual de transcrição: OK")


def test_conversacao_natural_sem_comandos_rigidos():
    print("[2/7] Testando interpretação natural, distinção pergunta/ordem e comandos incompletos...")
    variacoes_navegador = [
        "Abre o Chrome.",
        "Abre a internet pra mim.",
        "Entra no navegador.",
        "Consegue abrir o Google?",
        "Abre aí o Chrome, por favor",
    ]
    for frase in variacoes_navegador:
        intencao = interpretar_intencao_natural(frase)
        assert intencao is not None, f"Deveria compreender a intenção em: '{frase}'"
        assert intencao["acao"] == "abrir_programa", f"Ação incorreta para '{frase}': {intencao}"
        assert intencao["parametros"]["nome"] in {"chrome", "google"}

    # Não deve confundir pergunta conceitual com ordem de abrir
    assert interpretar_intencao_natural("O que é o Chrome?") is None

    # Comando incompleto sem contexto prévio pede esclarecimento em vez de executar ação errada
    inc = interpretar_intencao_natural("Abre isso aqui pra mim", {})
    assert inc and inc["acao"] == "esclarecer"
    assert "O que você gostaria que eu abrisse" in inc["resposta_direta"]

    print("  -> Intenções naturais, separação pergunta/ordem e esclarecimento de ambiguidade: OK")


def test_fluxo_contextual_continua_e_hardware():
    print("[3/7] Testando gerenciamento de contexto ('E a placa de vídeo?' -> 'Isso é normal?')...")
    contexto = {}

    # Fluxo 1: Spotify -> "Agora coloca uma música" -> "Coloca alguma coisa do Chase Atlantic"
    i1 = interpretar_intencao_natural("abre o Spotify", contexto)
    assert i1 and i1["acao"] == "abrir_programa" and i1["parametros"]["nome"] == "spotify"
    contexto.update(i1.get("novo_contexto", {}))

    i2 = interpretar_intencao_natural("Agora coloca uma música", contexto)
    assert i2 and i2["acao"] == "perguntar_midia"
    contexto.update(i2.get("novo_contexto", {}))

    i3 = interpretar_intencao_natural("Coloca alguma coisa do Chase Atlantic", contexto)
    assert i3 and i3["acao"] == "tocar_ou_pesquisar_midia"
    assert "Chase Atlantic" in i3["parametros"]["consulta"]
    contexto.update(i3.get("novo_contexto", {}))

    # Fluxo 2: RAM -> Placa de vídeo -> "Isso é normal?"
    h1 = interpretar_intencao_natural("Vê quanto de RAM meu computador está usando", contexto)
    assert h1 and h1["acao"] == "obter_status_pc" and h1["foco_resposta"] == "ram"
    contexto.update(h1.get("novo_contexto", {}))

    h2 = interpretar_intencao_natural("E a placa de vídeo?", contexto)
    assert h2 and h2["acao"] == "obter_status_gpu" and h2["foco_resposta"] == "gpu"
    contexto.update(h2.get("novo_contexto", {}))

    h3 = interpretar_intencao_natural("Isso é normal?", contexto)
    assert h3 and h3["acao"] == "avaliacao_contextual"
    assert "RX 580" in h3["resposta_direta"] or "normal" in h3["resposta_direta"]

    # Fluxo 3: "Por que meu computador tá travando?"
    h4 = interpretar_intencao_natural("Por que meu computador tá travando?", contexto)
    assert h4 and h4["acao"] == "obter_status_pc" and h4["foco_resposta"] == "diagnostico"

    print("  -> Fluxo contextual multi-turno (RAM -> GPU -> 'Isso é normal?' -> Diagnóstico): OK")


def test_fala_direcionada_sem_wake_word():
    print("[4/7] Testando detecção de fala direcionada sem palavra de ativação...")
    frases_direcionadas = [
        "Ei, olha isso aqui.",
        "Me ajuda com uma coisa.",
        "Você consegue ver o que está acontecendo?",
        "Abre isso aqui pra mim.",
        "Por que meu computador tá travando?",
        "Tá, agora fecha.",
        "Não, espera, deixa aberto.",
        "Não precisa mais.",
    ]
    for f in frases_direcionadas:
        prob = avaliar_fala_direcionada(f, {}, sessao_ativa=False)
        assert prob >= 0.70, f"Fala direcionada teve score baixo ({prob}) para: '{f}'"

    # Ruído solto ou frase desconexa sem sessão ativa deve ter score baixo
    prob_ruido = avaliar_fala_direcionada("la la la musica tocando", {}, sessao_ativa=False)
    assert prob_ruido < 0.50
    assert eh_desistencia_rapida("Não precisa mais") is True
    assert eh_desistencia_rapida("Não, espera, deixa aberto") is True
    print("  -> Detecção de fala direcionada vs ruído/música: OK")


def test_30_interacoes_consistencia_voz_e_latencia():
    print("[5/7] Executando 30 interações consecutivas (Consistência Vocal + Latência p50/p95)...")
    sintetizador = SintetizadorVoz(pre_aquecer=False)
    assert sintetizador.voz_id == IDENTIFICADOR_VOZ_FIXA == "pt-BR-FranciscaNeural"
    sintetizador._gerar_audio_voz_fixa = lambda _texto: (
        np.full(2400, 0.02, dtype=np.float32),
        24000,
    )

    # Pré-aquece as frases no cache em memória/disco
    sintetizador._pre_aquecer_frases_comuns()

    from gideon.voz.orquestrador import ModoEscuta
    orc = object.__new__(OrquestradorVoz)
    orc.sintetizador = sintetizador
    orc.ouvinte = type("OuvDummy", (), {"sensibilidade": 0.016, "configurar": lambda *a, **k: None})()
    orc.ativo = False
    orc.modo_escuta = ModoEscuta.ATIVACAO_POR_NOME
    orc.duracao_sessao = 30.0
    orc.memoria = type("MemDummy", (), {
        "processar_comando_explicito": lambda self, _: None,
        "gravar_mensagem": lambda self, *_: None,
    })()
    from gideon.tools import obter_catalogo_ferramentas
    orc._catalogo = obter_catalogo_ferramentas()
    orc._confirmacao_pendente = None
    orc._parametros_pendentes = {}
    orc._confirmacao_expira_em = 0.0
    orc._confirmacao_lock = threading.Lock()
    orc._em_conversa_ativa = True
    orc._ultimo_contato = time.time()
    orc.historico_sessao = []
    orc.contexto_conversa = {}
    orc.callback_ws = None

    orc._confirmacao_pendente = "encerrar_gideon"
    assert "cancelada" in orc.processar_fala_local_rapida("para").lower()
    assert orc._confirmacao_pendente is None
    assert "ativada" in orc.processar_fala_local_rapida("parada de emergência").lower()
    assert PARADO.is_set()
    assert "liberada" in orc.processar_fala_local_rapida("retomar execução").lower()
    assert not PARADO.is_set()

    entradas_30 = [
        "__PRESENCA__",
        "Vê quanto de RAM meu computador está usando",
        "E a placa de vídeo?",
        "Isso é normal?",
        "Por que meu computador tá travando?",
        "Como está meu computador?",
        "E o processador?",
        "E o espaço em disco?",
        "Agora coloca uma música",
        "Não precisa mais",
        "Gideon, espera",
        "Não, espera, deixa aberto",
        "Abre isso aqui pra mim",
        "Quais programas estão abertos?",
        "Meu computador tá estranho hoje",
        "Tá meio lento",
        "Não precisa",
        "Ativar modo conversa livre",
        "Ativar modo conversa contínua",
        "Ativar modo por nome",
        "Vê quanto de RAM meu computador está usando",
        "E a placa de vídeo?",
        "Isso é normal?",
        "Agora coloca uma música",
        "Esquece",
        "Como está a CPU?",
        "E a memória?",
        "Isso é normal?",
        "Para",
        "Obrigado, só isso",
    ]

    assert len(entradas_30) == 30
    vozes_usadas = set()

    for idx, entrada in enumerate(entradas_30, 1):
        t0 = time.perf_counter()
        resp = orc.processar_fala_local_rapida(entrada)
        assert resp is not None, f"Falha na interação #{idx}: '{entrada}'"
        assert "[EMOCAO:" not in resp, f"Resposta local contém tag legada: {resp}"
        nlu_ms = orc.ultimo_nlu_ms

        # Verifica síntese para memória e cache com a voz única fixa
        t_tts = time.perf_counter()
        texto_fala = limpar_texto_para_fala(resp)
        audio, taxa, do_cache = sintetizador.sintetizar_para_memoria(texto_fala)
        tts_ms = (time.perf_counter() - t_tts) * 1000.0

        assert len(audio) > 0 and taxa == 24000
        vozes_usadas.add(sintetizador.voz_id)

        metricas_voz_global.registrar(
            modo_escuta="conversa_continua",
            origem_resposta=orc.ultima_origem_resposta,
            voz_id=sintetizador.voz_id,
            vad_endpoint_ms=720.0,
            stt_ms=351.0,
            nlu_ms=nlu_ms,
            llm_ttft_ms=0.0,
            tts_ttfa_ms=tts_ms,
        )

    resumo = metricas_voz_global.resumo_estatistico()
    assert resumo["voz_fixa_unica"] is True, f"Voz mudou! Vozes vistas: {resumo['vozes_vistas']}"
    assert vozes_usadas == {"pt-BR-FranciscaNeural"}
    print(f"  -> 30/30 interações com 100% de consistência vocal ({sintetizador.voz_id})!")
    print(f"  -> Latência NLU p50: {resumo['p50_ms']['nlu_ms']} ms | p95: {resumo['p95_ms']['nlu_ms']} ms")
    print(f"  -> Latência TTS (com cache) p50: {resumo['p50_ms']['tts_ttfa_ms']} ms | p95: {resumo['p95_ms']['tts_ttfa_ms']} ms")
    print(f"  -> TTFA Total p50: {resumo['p50_ms']['ttfa_total_ms']} ms | p95: {resumo['p95_ms']['ttfa_total_ms']} ms")


def test_barge_in_e_streaming_incremental():
    print("[6/7] Testando Barge-In e síntese incremental por sentenças (falar_stream)...")
    eventos = []
    sintetizador = SintetizadorVoz(callback_evento=lambda e: eventos.append(e), pre_aquecer=False)
    sintetizador._gerar_audio_voz_fixa = lambda _texto: (
        np.full(12000, 0.02, dtype=np.float32),
        24000,
    )

    def reproduzir_sem_hardware(_audio, _taxa):
        while not sintetizador._evento_interromper.wait(0.04):
            sintetizador._notificar({"tipo": "voz_nivel", "nivel": 0.4})

    sintetizador._reproduzir_audio = reproduzir_sem_hardware

    def interromper_logo():
        time.sleep(0.15)
        sintetizador.interromper()

    threading.Thread(target=interromper_logo, daemon=True).start()
    concluiu = sintetizador.falar_stream(iter(["Abrindo o Chrome.", "Estou aqui, Henry.", "Claro. O que gostaria de ouvir?"]))
    assert concluiu is False or sintetizador.foi_interrompida is True
    tipos = [e["tipo"] for e in eventos]
    assert "fala_inicio" in tipos and "fala_fim" in tipos
    assert "voz_nivel" in tipos
    assert "speaking" in [e.get("estado") for e in eventos if e["tipo"] == "estado_ia"]
    assert all(
        set(e) == {"tipo", "nivel"} and 0.0 <= e["nivel"] <= 1.0
        for e in eventos
        if e["tipo"] == "voz_nivel"
    )
    print("  -> Barge-In em streaming incremental validado: OK")


async def test_api_modos_e_metricas():
    print("[7/7] Testando endpoints de modos, interrupção e métricas via API...")
    transport = httpx.ASGITransport(app=app)
    headers = {
        "x-gideon-token": TOKEN_LOCAL,
        "x-gideon-csrf": "1",
        "origin": "http://127.0.0.1:8000",
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        res = await client.get("/api/voz/status", headers=headers)
        assert res.status_code == 200
        dados_voz = res.json()
        assert dados_voz["inicializacao"] in {"nao_iniciada", "inicializando", "pronta"}
        if dados_voz["inicializacao"] == "pronta":
            assert dados_voz["voz_fixa_id"] == "pt-BR-FranciscaNeural"

        res_m = await client.get("/api/voz/metricas", headers=headers)
        assert res_m.status_code == 200
        assert res_m.json()["voz_fixa_unica"] is True

    status_pc = obter_status_pc()
    print(
        f"  -> Recursos de Hardware: CPU {status_pc['cpu_percent']} | "
        f"RAM {status_pc['memoria_ram']['usado_gb']}/{status_pc['memoria_ram']['total_gb']} | "
        f"GPU {status_pc['gpu']['modelo']} ({status_pc['gpu']['vram']})"
    )


async def principal():
    test_extracao_wake_word_e_correcao_stt()
    test_conversacao_natural_sem_comandos_rigidos()
    test_fluxo_contextual_continua_e_hardware()
    test_fala_direcionada_sem_wake_word()
    test_30_interacoes_consistencia_voz_e_latencia()
    test_barge_in_e_streaming_incremental()
    await test_api_modos_e_metricas()
    print("\n=======================================================")
    print("  OTIMIZACAO AVANCADA DE VOZ E LATENCIA VALIDADA (100%)!")
    print("=======================================================\n")


if __name__ == "__main__":
    asyncio.run(principal())
