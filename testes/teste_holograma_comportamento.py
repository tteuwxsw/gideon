"""Bateria de testes da Reconstrução Visual, Comportamental, Lip-Sync Fonético e Consciência de Desktop da Gideon."""

from __future__ import annotations

import asyncio
import subprocess
import time
import httpx
import numpy as np

from gideon.executor import EstadoExecucao, ExecutorConfiavel
from gideon.presenca import (
    MonitorPresencaDesktop,
    inspecionar_janela_ativa_segura,
    obter_posicao_cursor_normalizada,
)
from gideon.protocolo import EstadoComportamental, TipoMensagem, criar_evento
from gideon.servidor import app, TOKEN_LOCAL
from gideon.supervisor import _localizar_godot
from gideon.tools import obter_catalogo_ferramentas
from gideon.tools.sistema import obter_status_pc
from gideon.voz.fala import IDENTIFICADOR_VOZ_FIXA, SintetizadorVoz
from gideon.voz.orquestrador import ModoEscuta, OrquestradorVoz
from gideon.voz.visemas import (
    VISEMAS_MODELO,
    calcular_frame_lipsync_audio,
    converter_texto_em_sequencia_visemas,
)


def test_visemas_foneticos_e_coarticulacao_audio():
    print("[1/5] Testando motor de visemas fonéticos (15 visemas Oculus) e sincronização com áudio real...")
    frase = "Olá Henry, estou verificando o consumo de memória do seu computador."
    quadros = converter_texto_em_sequencia_visemas(frase, duracao_audio_s=3.2)
    assert len(quadros) > 15
    visemas_gerados = {q.visema_principal for q in quadros}
    # Deve conter vogais e consoantes variadas da língua portuguesa
    assert "viseme_O" in visemas_gerados
    assert "viseme_aa" in visemas_gerados
    assert "viseme_E" in visemas_gerados
    assert "viseme_FF" in visemas_gerados or "viseme_SS" in visemas_gerados
    assert visemas_gerados.issubset(set(VISEMAS_MODELO))

    # 1. Silêncio absoluto no áudio DEVE manter a boca fechada (viseme_sil e abertura 0.0)
    fatia_silencio = np.zeros(800, dtype=np.float32)
    frame_sil = calcular_frame_lipsync_audio(fatia_silencio, 24000, 0.5, quadros)
    assert frame_sil["visema"] == "viseme_sil"
    assert frame_sil["abertura_mandibula"] == 0.0
    assert frame_sil["intensidade"] == 0.0

    # 2. Áudio real sintetizado com a voz fixa da Gideon deve acionar visemas e mandíbula sincronizados
    sintetizador = SintetizadorVoz(pre_aquecer=False)
    assert sintetizador.voz_id == IDENTIFICADOR_VOZ_FIXA == "pt-BR-FranciscaNeural"
    audio, taxa, _ = sintetizador.sintetizar_para_memoria("Estou aqui, Henry.")
    duracao = len(audio) / float(taxa)
    seq = converter_texto_em_sequencia_visemas("Estou aqui, Henry.", duracao)

    frames_ativos = []
    passo = int(taxa * 0.033)
    for idx in range(0, len(audio), passo):
        fatia = audio[idx : idx + passo]
        t_atual = idx / float(taxa)
        f = calcular_frame_lipsync_audio(fatia, taxa, t_atual, seq)
        if f["intensidade"] > 0.05:
            frames_ativos.append(f)

    assert len(frames_ativos) >= 5, "Deveria gerar múltiplos quadros ativos de lip-sync durante a fala!"
    visemas_fala = {f["visema"] for f in frames_ativos}
    assert len(visemas_fala) >= 2, f"Boca não deve repetir um único visema estático: {visemas_fala}"
    print(f"  -> Lip-sync fonético validado ({len(frames_ativos)} quadros ativos, visemas: {sorted(visemas_fala)})")


def test_consciencia_desktop_cursor_e_janela():
    print("[2/5] Testando sensor de consciência de desktop (cursor, janela ativa e proteção de privacidade)...")
    cur = obter_posicao_cursor_normalizada()
    assert "x_px" in cur and "y_px" in cur
    assert -0.15 <= cur["x_olhar"] <= 0.15
    assert -0.11 <= cur["y_olhar"] <= 0.11

    jan = inspecionar_janela_ativa_segura()
    assert "hwnd" in jan and "titulo" in jan and "processo" in jan
    assert -0.15 <= jan["x_olhar"] <= 0.15

    # Testa filtro de privacidade simulando que a janela/processo atual está na lista excluída
    chave_priv = jan.get("processo") or jan.get("titulo") or "explorer.exe"
    jan_privada = inspecionar_janela_ativa_segura(apps_excluidos=[chave_priv, "área de trabalho", "explorer.exe"])
    assert jan_privada["protegida_privacidade"] is True
    assert jan_privada["titulo"] == "[Janela Protegida por Privacidade]"

    eventos_presenca = []
    monitor = MonitorPresencaDesktop(callback_evento=lambda e: eventos_presenca.append(e))
    monitor.definir_foco_conversa(True)
    assert any(e.get("tipo") == "olhar" and e.get("alvo") == "usuario" for e in eventos_presenca)
    print(f"  -> Cursor ({cur['x_px']}, {cur['y_px']}) -> Olhar ({cur['x_olhar']}, {cur['y_olhar']}) | Janela: '{jan['titulo'][:35]}'")


def test_dialogo_proativo_e_maquina_7_estados():
    print("[3/5] Testando iniciativa conversacional e máquina de 7 estados comportamentais...")
    eventos_ws = []
    orc = object.__new__(OrquestradorVoz)
    orc._catalogo = obter_catalogo_ferramentas()
    orc._executor = ExecutorConfiavel(orc._catalogo)
    orc.ultima_execucao = None
    orc._confirmacao_pendente = None
    orc._parametros_pendentes = {}
    orc._confirmacao_expira_em = 0.0
    orc._em_conversa_ativa = True
    orc._ultimo_contato = time.time()
    orc.modo_escuta = ModoEscuta.CONVERSA_CONTINUA
    orc.duracao_sessao = 30.0
    orc.historico_sessao = []
    orc.contexto_conversa = {}
    orc.estado_comportamental_atual = "idle"
    orc.monitor_presenca = MonitorPresencaDesktop(callback_evento=lambda e: eventos_ws.append(e))
    orc.callback_ws = lambda e: eventos_ws.append(e)
    orc.memoria = type("MemDummy", (), {
        "processar_comando_explicito": lambda self, _: None,
        "gravar_mensagem": lambda self, *_: None,
    })()

    # Diálogo proativo de diagnóstico:
    # 1. "Gideon, meu computador tá estranho hoje." -> "O que está acontecendo?"
    r1 = orc.processar_fala_local_rapida("Meu computador tá estranho hoje")
    assert r1 is not None and "O que está acontecendo?" in r1

    # 2. "Tá meio lento." -> "Quer que eu verifique o consumo de recursos?"
    r2 = orc.processar_fala_local_rapida("Tá meio lento")
    assert r2 is not None and "Quer que eu verifique o consumo de recursos?" in r2

    # 3. "Pode olhar." -> Executa verificação real de CPU/RAM e relata os dados obtidos
    r3 = orc.processar_fala_local_rapida("Pode olhar")
    assert r3 is not None and "Verifiquei agora" in r3
    assert orc.ultima_execucao is not None and orc.ultima_execucao.estado == EstadoExecucao.SUCCESS
    assert orc.ultima_execucao.verificado is True
    print(f"  -> Fluxo proativo validado: '{r1}' -> '{r2}' -> '{r3}'")

    # 4. Inspecionar contexto real da tela (transição para 'observing')
    r4 = orc.processar_fala_local_rapida("O que está na minha tela?")
    assert r4 is not None and "janela em foco" in r4.lower()
    estados_emitidos = [e.get("estado") for e in eventos_ws if e.get("tipo") == "estado_ia"]
    assert "executing" in estados_emitidos and "observing" in estados_emitidos

    # 5. Controle de presença do holograma ("Deixa o holograma mais transparente")
    r5 = orc.processar_fala_local_rapida("Deixa o holograma mais transparente")
    assert r5 is not None and "projeção holográfica" in r5
    assert any(e.get("tipo") == "config_holograma" for e in eventos_ws)
    print(f"  -> Estados comportamentais emitidos e validados: {estados_emitidos}")


def test_godot_4_carregamento_esqueleto_e_shader():
    print("[4/5] Validando carregamento real do busto 3D, esqueleto (8 ossos) e shader no Godot 4...")
    exe_godot, _ = _localizar_godot()
    assert exe_godot is not None and exe_godot.is_file(), "Executável do Godot 4 não encontrado!"

    res = subprocess.run(
        [str(exe_godot), "--path", "gideon_avatar", "--headless", "--quit-after", "3"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10.0,
    )
    assert res.returncode == 0, f"Godot retornou erro: {res.stderr}"
    assert "4 malhas faciais e 8 ossos articulados" in res.stdout
    assert "SCRIPT ERROR" not in res.stderr and "Shader compilation failed" not in res.stderr
    print(f"  -> Godot 4 validado sem erros: {[ln.strip() for ln in res.stdout.splitlines() if '[Gideon' in ln]}")


async def test_api_telemetria_e_config_holograma():
    print("[5/5] Testando endpoints de configuração e telemetria do holograma e desempenho RX 580...")
    transport = httpx.ASGITransport(app=app)
    headers = {
        "x-gideon-token": TOKEN_LOCAL,
        "x-gideon-csrf": "1",
        "origin": "http://127.0.0.1:8000",
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        res_cfg = await client.post(
            "/api/avatar/config",
            headers=headers,
            json={
                "estado_ia": "speaking",
                "opacidade": 0.85,
                "escala": 1.05,
                "fps_ativo": 60,
                "fps_ocioso": 30,
            },
        )
        assert res_cfg.status_code == 200
        assert res_cfg.json()["status"] == "ok"

        res_tel = await client.get("/api/avatar/telemetria", headers=headers)
        assert res_tel.status_code == 200
        dados_tel = res_tel.json()
        assert "avatar" in dados_tel and "consciencia_desktop" in dados_tel

    status_pc = obter_status_pc()
    print(
        f"  -> Telemetria de Hardware e Presença: CPU {status_pc['cpu_percent']} | "
        f"RAM {status_pc['memoria_ram']['usado_gb']} | GPU {status_pc['gpu']['modelo']} ({status_pc['gpu']['vram']})"
    )


async def principal():
    test_visemas_foneticos_e_coarticulacao_audio()
    test_consciencia_desktop_cursor_e_janela()
    test_dialogo_proativo_e_maquina_7_estados()
    test_godot_4_carregamento_esqueleto_e_shader()
    await test_api_telemetria_e_config_holograma()
    print("\n=======================================================")
    print("  RECONSTRUCAO VISUAL, COMPORTAMENTAL E VOCAL APROVADA!")
    print("=======================================================\n")


if __name__ == "__main__":
    asyncio.run(principal())
