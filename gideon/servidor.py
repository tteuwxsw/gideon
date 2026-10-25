"""Servidor local da Gideon (FastAPI + SSE streaming + WebSocket para avatar)."""

import queue
import os
import secrets
import threading
from pathlib import Path
from typing import AsyncGenerator
from fastapi import (
    FastAPI, Depends, HTTPException, Header, Request, WebSocket,
    WebSocketDisconnect, status,
)
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import json
import asyncio

from gideon.cerebro import Cerebro
from gideon.auth import obter_ou_criar_token, token_valido
from gideon.memoria import Memoria

# Diretórios base
ROOT_DIR = Path(__file__).resolve().parent.parent
DADOS_DIR = Path(os.environ.get("GIDEON_DATA_DIR", ROOT_DIR / "dados"))
WEB_DIR = ROOT_DIR / "gideon" / "web"
TOKEN_FILE = DADOS_DIR / "auth_token.txt"
ORIGENS_LOCAIS = {"http://127.0.0.1:8000", "http://localhost:8000", "http://127.0.0.1", "http://localhost"}

DADOS_DIR.mkdir(parents=True, exist_ok=True)
WEB_DIR.mkdir(parents=True, exist_ok=True)


TOKEN_LOCAL = obter_ou_criar_token(TOKEN_FILE)

app = FastAPI(title="Gideon — Assistente Pessoal", version="0.3.0")

# Restringe CORS estritamente à máquina local
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ORIGENS_LOCAIS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def proteger_requisicoes_web(request: Request, call_next):
    """Impede que outras paginas locais usem o cookie da Gideon por CSRF."""
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origem = request.headers.get("origin")
        if origem and origem not in ORIGENS_LOCAIS:
            return JSONResponse({"detail": "Origem nao autorizada."}, status_code=403)
        if request.cookies.get("gideon_token") and request.url.path != "/api/auth/login":
            if request.headers.get("x-gideon-csrf") != "1":
                return JSONResponse({"detail": "Protecao CSRF ausente."}, status_code=403)
    return await call_next(request)

# Estado em memória
cerebro = Cerebro()
memoria = Memoria(DADOS_DIR / "memoria.db")
historico_conversa: list[dict[str, str]] = []
orquestrador_voz = None
_loop_servidor = None
_uvicorn_server = None

# Conexões WebSocket ativas (avatar Godot e outros clientes)
_clientes_ws: set[WebSocket] = set()
_lock_ws = asyncio.Lock()


# ─── Autenticação ──────────────────────────────────────────────

def autenticar(
    request: Request,
    x_gideon_token: str | None = Header(None, alias="x-gideon-token"),
) -> bool:
    """Verifica se o token fornecido confere com o token local."""
    token_fornecido = x_gideon_token or request.cookies.get("gideon_token")

    if not token_valido(token_fornecido, TOKEN_LOCAL):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token local inválido ou ausente.",
        )
    return True


# ─── Broadcast para WebSocket (envia eventos para o avatar) ───

async def broadcast_ws(evento: dict) -> None:
    """Envia um evento JSON para todos os clientes WebSocket conectados."""
    global _clientes_ws
    if not _clientes_ws:
        return
    mensagem = json.dumps(evento, ensure_ascii=False)
    async with _lock_ws:
        desconectados = set()
        for ws in list(_clientes_ws):
            try:
                await ws.send_text(mensagem)
            except Exception:
                desconectados.add(ws)
        _clientes_ws -= desconectados


# ─── Modelos de Requisição ────────────────────────────────────

class MensagemRequisicao(BaseModel):
    mensagem: str


class EmocaoRequisicao(BaseModel):
    nome: str
    intensidade: float = 1.0


class ModoRequisicao(BaseModel):
    modo: str


class ConfigHologramaRequisicao(BaseModel):
    estado_ia: str | None = None
    opacidade: float | None = None
    escala: float | None = None
    click_through: bool | None = None
    sempre_visivel: bool | None = None
    qualidade: str | None = None
    fps_ativo: int | None = None
    fps_ocioso: int | None = None
    posicao_x: int | None = None
    posicao_y: int | None = None


_telemetria_avatar_atual: dict = {
    "fps": 60,
    "estado_ia": "idle",
    "emocao": "neutra",
    "visema_ativo": "viseme_sil",
    "olhar_x": 0.0,
    "olhar_y": 0.0,
    "modo": "conversa",
}


# ─── Rotas HTTP ───────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve a interface web do chat local."""
    html_path = WEB_DIR / "index.html"
    if not html_path.exists():
        return HTMLResponse(
            "<h1>Interface não encontrada. Verifique gideon/web/index.html</h1>",
            status_code=404,
        )

    conteudo = html_path.read_text(encoding="utf-8")
    return HTMLResponse(conteudo)


class LoginRequisicao(BaseModel):
    token: str


@app.post("/api/auth/login")
async def login_local(req: LoginRequisicao):
    """Troca o token inicial por um cookie local que JavaScript nao consegue ler."""
    if not token_valido(req.token, TOKEN_LOCAL):
        raise HTTPException(status_code=401, detail="Token local invalido.")

    response = JSONResponse({"status": "ok"})
    response.set_cookie(
        key="gideon_token",
        value=TOKEN_LOCAL,
        httponly=True,
        samesite="strict",
        secure=False,
        max_age=86400,
    )
    return response


@app.get("/health")
async def health():
    """Health check local sem dados privados, usado pelo supervisor."""
    return {"status": "ok"}


@app.post("/api/runtime/shutdown")
async def encerrar_runtime(x_gideon_runtime: str | None = Header(None)):
    """Permite somente ao supervisor encerrar o backend cooperativamente."""
    token_runtime = os.environ.get("GIDEON_RUNTIME_TOKEN")
    if not token_runtime or not x_gideon_runtime or not secrets.compare_digest(
        x_gideon_runtime, token_runtime
    ):
        raise HTTPException(status_code=403, detail="Supervisor invalido.")
    if _uvicorn_server is not None:
        _uvicorn_server.should_exit = True
    return {"status": "encerrando"}


@app.get("/api/status")
async def obter_status(_: bool = Depends(autenticar)):
    """Retorna o status atual do serviço."""
    return {
        "status": "online",
        "nome": "Gideon",
        "versao": "0.3.0",
        "modelo": cerebro.modelo,
        "mensagens_no_historico": len(historico_conversa),
        "clientes_ws": len(_clientes_ws),
    }


@app.post("/api/chat/limpar")
async def limpar_chat(_: bool = Depends(autenticar)):
    """Limpa o histórico da sessão atual."""
    global historico_conversa
    historico_conversa = []
    return {"status": "ok", "mensagem": "Histórico limpo com sucesso."}


@app.get("/api/memoria/fatos")
async def listar_fatos(_: bool = Depends(autenticar)):
    """Lista todos os fatos gravados na memória permanente."""
    return {"fatos": memoria.listar_fatos()}


class FatoRequisicao(BaseModel):
    chave: str
    valor: str


@app.post("/api/memoria/fatos")
async def salvar_fato_api(req: FatoRequisicao, _: bool = Depends(autenticar)):
    """Grava ou atualiza um fato permanente."""
    memoria.salvar_fato(req.chave, req.valor, origem="api")
    return {"status": "ok", "mensagem": f"Fato '{req.chave}' salvo com sucesso."}


@app.delete("/api/memoria/fatos/{chave}")
async def esquecer_fato_api(chave: str, _: bool = Depends(autenticar)):
    """Exclui um fato da memória permanente."""
    removido = memoria.esquecer_fato(chave)
    if not removido:
        raise HTTPException(status_code=404, detail="Fato não encontrado.")
    return {"status": "ok", "mensagem": f"Fato '{chave}' excluído."}


@app.post("/api/chat/stream")
async def chat_stream(req: MensagemRequisicao, _: bool = Depends(autenticar)):
    """Processa a mensagem e transmite a resposta via SSE."""
    texto_usuario = req.mensagem.strip()
    if not texto_usuario:
        raise HTTPException(status_code=400, detail="A mensagem não pode ser vazia.")

    historico_conversa.append({"role": "user", "content": texto_usuario})

    # Detecta intenções de movimentação física da Gideon na tela
    texto_lower = texto_usuario.lower()
    if any(c in texto_lower for c in ["vai pro canto", "vai para o canto", "fica no canto", "modo compacto"]):
        await broadcast_ws({"tipo": "modo", "nome": "compacto"})
    elif any(c in texto_lower for c in ["vem pro centro", "vem para o centro", "modo conversa", "fica no meio"]):
        await broadcast_ws({"tipo": "modo", "nome": "conversa"})
    elif any(c in texto_lower for c in ["modo foco", "aumenta de tamanho", "fica maior"]):
        await broadcast_ws({"tipo": "modo", "nome": "foco"})
    elif any(c in texto_lower for c in ["canto esquerdo", "vai pra esquerda"]):
        await broadcast_ws({"tipo": "modo", "nome": "canto_esquerdo"})
    elif any(c in texto_lower for c in ["some da tela", "modo oculto", "oculta", "se esconde"]):
        await broadcast_ws({"tipo": "modo", "nome": "oculto"})

    # 1. Verifica se é um comando explícito de memória ou uma intenção de execução real no Windows
    resposta_comando_local = memoria.processar_comando_explicito(texto_usuario)
    if not resposta_comando_local:
        from gideon.voz.comandos import interpretar_intencao_natural, detectar_comando_sistema
        orc_local = obter_orquestrador()
        if (
            orc_local._confirmacao_pendente
            or detectar_comando_sistema(texto_usuario) is not None
            or interpretar_intencao_natural(texto_usuario, orc_local.contexto_conversa) is not None
        ):
            resposta_comando_local = orc_local.processar_fala_local_rapida(
                texto_usuario,
                falar_feedback_imediato=False,
            )

    if resposta_comando_local:
        # Grava no histórico permanente
        memoria.gravar_mensagem("voce", texto_usuario)
        memoria.gravar_mensagem("assistente", resposta_comando_local)
        historico_conversa.append({"role": "assistant", "content": resposta_comando_local})

        async def gerador_comando() -> AsyncGenerator[str, None]:
            # Emite evento de início de fala para o avatar
            await broadcast_ws({"tipo": "fala_inicio", "texto": resposta_comando_local})

            # Extrai emoções do comando
            try:
                from gideon.protocolo import extrair_emocoes_texto
                for _, emo in extrair_emocoes_texto(resposta_comando_local):
                    await broadcast_ws({"tipo": "emocao", "nome": emo, "intensidade": 0.8})
            except Exception:
                pass

            # Transmite o texto do comando
            yield f"data: {json.dumps({'tipo': 'chunk', 'texto': resposta_comando_local}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.05)

            # Transmite evento fim com 0 custo de API (executado localmente)
            yield f"data: {json.dumps({'tipo': 'fim', 'total_tokens': 0, 'custo_estimado': 0.0, 'modelo': 'executor_verificado'}, ensure_ascii=False)}\n\n"
            await broadcast_ws({"tipo": "fala_fim"})

        return StreamingResponse(
            gerador_comando(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    # 2. Se for pergunta comum, busca lembranças relevantes para injetar no cérebro
    lembrancas = memoria.recuperar_lembrancas_para_prompt(texto_usuario)

    # Notifica o avatar que a Gideon está pensando
    await broadcast_ws({"tipo": "pensando", "ativo": True})

    async def gerador_eventos() -> AsyncGenerator[str, None]:
        texto_resposta = []
        fila: queue.Queue = queue.Queue()
        loop = asyncio.get_running_loop()

        def produtor():
            try:
                for evento in cerebro.pensar_stream(historico_conversa, lembrancas=lembrancas):
                    fila.put(evento)
            except Exception as e:
                fila.put({
                    "tipo": "erro",
                    "mensagem": f"Erro no fluxo do cérebro: {str(e)[:150]}",
                })
            finally:
                fila.put(None)

        threading.Thread(target=produtor, daemon=True).start()

        primeira_palavra = True

        try:
            while True:
                evento = await loop.run_in_executor(None, fila.get)
                if evento is None:
                    break

                if evento["tipo"] == "chunk":
                    texto_resposta.append(evento["texto"])

                    # Na primeira palavra, notifica o avatar que a Gideon começou a falar
                    if primeira_palavra:
                        await broadcast_ws({"tipo": "pensando", "ativo": False})
                        await broadcast_ws({"tipo": "fala_inicio", "texto": ""})
                        primeira_palavra = False

                    # Envia o texto para o avatar (para lip sync futuro)
                    await broadcast_ws({
                        "tipo": "fala_chunk",
                        "texto": evento["texto"],
                    })

                    # Extrai emoções do texto, se houver
                    try:
                        from gideon.protocolo import extrair_emocoes_texto
                        emocoes = extrair_emocoes_texto(evento["texto"])
                        for _, emocao in emocoes:
                            await broadcast_ws({
                                "tipo": "emocao",
                                "nome": emocao,
                                "intensidade": 0.8,
                            })
                    except ImportError:
                        pass

                elif evento["tipo"] == "fim":
                    resposta_completa = "".join(texto_resposta)
                    historico_conversa.append({
                        "role": "assistant",
                        "content": resposta_completa,
                    })

                    # Persiste a conversa na memória permanente SQLite
                    memoria.gravar_mensagem("voce", texto_usuario)
                    memoria.gravar_mensagem("assistente", resposta_completa)

                    await broadcast_ws({"tipo": "fala_fim"})

                elif evento["tipo"] == "erro":
                    await broadcast_ws({"tipo": "pensando", "ativo": False})

                yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"

        except Exception as e:
            msg_erro = {
                "tipo": "erro",
                "mensagem": f"Erro inesperado no servidor: {str(e)[:150]}",
            }
            yield f"data: {json.dumps(msg_erro, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gerador_eventos(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Controle do Avatar via HTTP (para testes e automações) ──

@app.post("/api/avatar/emocao")
async def definir_emocao(req: EmocaoRequisicao, _: bool = Depends(autenticar)):
    """Envia uma emoção para o avatar."""
    await broadcast_ws({
        "tipo": "emocao",
        "nome": req.nome,
        "intensidade": req.intensidade,
    })
    return {"status": "ok"}


@app.post("/api/avatar/modo")
async def definir_modo(req: ModoRequisicao, _: bool = Depends(autenticar)):
    """Altera o modo de exibição do avatar."""
    await broadcast_ws({
        "tipo": "modo",
        "nome": req.modo,
    })
    return {"status": "ok"}


@app.post("/api/avatar/config")
async def configurar_holograma(req: ConfigHologramaRequisicao, _: bool = Depends(autenticar)):
    """Configura presença do holograma no desktop (opacidade, escala, posição, click-through, FPS e estado_ia)."""
    payload = {k: v for k, v in req.model_dump().items() if v is not None}
    if "estado_ia" in payload:
        await broadcast_ws({"tipo": "estado_ia", "estado": payload["estado_ia"]})
    await broadcast_ws({"tipo": "config_holograma", **payload})
    return {"status": "ok", "config_enviada": payload}


@app.get("/api/avatar/telemetria")
async def obter_telemetria_avatar(_: bool = Depends(autenticar)):
    """Retorna a telemetria visual em tempo real do avatar Godot (FPS, estado comportamental, olhar, visema)."""
    from gideon.presenca import inspecionar_janela_ativa_segura, obter_posicao_cursor_normalizada
    return {
        "status": "ok",
        "avatar": _telemetria_avatar_atual,
        "consciencia_desktop": {
            "cursor": obter_posicao_cursor_normalizada(),
            "janela_ativa": inspecionar_janela_ativa_segura(),
        },
    }


# ─── WebSocket para o Avatar ──────────────────────────────────

@app.websocket("/ws")
async def websocket_avatar(websocket: WebSocket):
    """Conexão WebSocket bidirecional para o avatar (Godot ou Unreal Engine 5)."""
    origem = websocket.headers.get("origin")
    token_header = websocket.headers.get("x-gideon-token")
    token_query = websocket.query_params.get("token")
    token_cookie = websocket.cookies.get("gideon_token")
    token = token_header or token_query or token_cookie

    if origem and origem not in ORIGENS_LOCAIS:
        await websocket.close(code=4003, reason="Origem nao autorizada")
        return
    if not token or not token_valido(token, TOKEN_LOCAL):
        await websocket.close(code=4001, reason="Token inválido")
        return

    await websocket.accept()

    async with _lock_ws:
        _clientes_ws.add(websocket)

    cliente_id = f"ws-{id(websocket)}"
    print(f"  [WebSocket] Cliente conectado: {cliente_id} (total: {len(_clientes_ws)})")

    # Envia status inicial
    await websocket.send_text(json.dumps({
        "tipo": "status",
        "nome": "Gideon",
        "modelo": cerebro.modelo,
        "mensagens": len(historico_conversa),
    }, ensure_ascii=False))

    try:
        while True:
            data = await websocket.receive_text()
            try:
                mensagem = json.loads(data)
                tipo = mensagem.get("tipo", "")

                if tipo == "pronto":
                    print(f"  [WebSocket] Avatar '{cliente_id}' reportou pronto")

                elif tipo == "clique_avatar":
                    # Futuro: pode disparar o modo de conversa
                    pass

                elif tipo == "modo_mudou":
                    modo = mensagem.get("modo", "")
                    _telemetria_avatar_atual["modo"] = modo
                    print(f"  [WebSocket] Modo do avatar: {modo}")

                elif tipo == "telemetria_avatar":
                    for k in ("fps", "estado_ia", "emocao", "visema_ativo", "olhar_x", "olhar_y", "modo"):
                        if k in mensagem:
                            _telemetria_avatar_atual[k] = mensagem[k]

                # Outros eventos do avatar são logados
                else:
                    print(f"  [WebSocket] Evento de '{cliente_id}': {tipo}")

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        async with _lock_ws:
            _clientes_ws.discard(websocket)
        print(f"  [WebSocket] Cliente desconectado: {cliente_id} (total: {len(_clientes_ws)})")


# ─── Controle de Voz ──────────────────────────────────────────

_lock_orquestrador = threading.Lock()


def obter_orquestrador():
    global orquestrador_voz
    if orquestrador_voz is None:
        with _lock_orquestrador:
            if orquestrador_voz is None:
                from gideon.voz.orquestrador import OrquestradorVoz
                def repassar(ev):
                    if _loop_servidor and _loop_servidor.is_running():
                        asyncio.run_coroutine_threadsafe(broadcast_ws(ev), _loop_servidor)
                orquestrador_voz = OrquestradorVoz(cerebro, memoria, repassar)
    return orquestrador_voz


@app.post("/api/voz/iniciar")
async def iniciar_voz(_: bool = Depends(autenticar)):
    """Inicia o ouvinte contínuo de voz (Wake Word 'Gideon')."""
    orc = obter_orquestrador()
    orc.iniciar()
    return {"status": "ok", "mensagem": "Escuta por voz ativada."}


@app.post("/api/voz/parar")
async def parar_voz(_: bool = Depends(autenticar)):
    """Pausa a escuta contínua de voz."""
    orc = obter_orquestrador()
    orc.parar()
    return {"status": "ok", "mensagem": "Escuta por voz pausada."}


@app.get("/api/voz/status")
async def status_voz(_: bool = Depends(autenticar)):
    """Retorna o estado detalhado da escuta de voz, modo atual e sensibilidade."""
    orc = obter_orquestrador()
    cfg = orc.obter_configuracao()
    return {"status": "ok", **cfg}


class ConfiguracaoVozRequisicao(BaseModel):
    modo_escuta: str | None = None
    duracao_sessao: float | None = None
    sensibilidade: float | None = None
    barge_in_ativo: bool | None = None
    palavras_ativacao: list[str] | None = None


@app.post("/api/voz/configurar")
async def configurar_voz(req: ConfiguracaoVozRequisicao, _: bool = Depends(autenticar)):
    """Configura modo de escuta (ativacao_por_nome, conversa_continua, conversa_livre), sensibilidade e sessão."""
    orc = obter_orquestrador()
    cfg = orc.configurar(
        modo_escuta=req.modo_escuta,
        duracao_sessao=req.duracao_sessao,
        sensibilidade=req.sensibilidade,
        barge_in_ativo=req.barge_in_ativo,
        palavras_ativacao=req.palavras_ativacao,
    )
    return {"status": "ok", **cfg}


@app.post("/api/voz/interromper")
async def interromper_voz(_: bool = Depends(autenticar)):
    """Interrompe imediatamente a fala atual da Gideon (Barge-In)."""
    orc = obter_orquestrador()
    interrompeu = orc.interromper_fala()
    return {"status": "ok", "interrompida": interrompeu}


@app.get("/api/voz/metricas")
async def metricas_voz(_: bool = Depends(autenticar)):
    """Retorna as métricas reais de latência (p50, p95, TTFA) e consistência vocal."""
    from gideon.voz.metricas import metricas_voz_global
    return {"status": "ok", **metricas_voz_global.resumo_estatistico()}


@app.get("/api/execucoes/historico")
async def historico_execucoes(limite: int = 20, _: bool = Depends(autenticar)):
    """Retorna os últimos registros estruturados de execução e verificação pós-condição."""
    from gideon.executor import LOG_EXECUCOES
    if not LOG_EXECUCOES.exists():
        return {"status": "ok", "execucoes": []}
    linhas = LOG_EXECUCOES.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    itens = []
    for ln in linhas[-limite:]:
        try:
            itens.append(json.loads(ln))
        except Exception:
            pass
    return {"status": "ok", "execucoes": itens}


# ─── Ponto de Entrada ─────────────────────────────────────────

def main():
    """Inicia o servidor web local na porta 8000, restrito ao localhost."""
    import sys
    global _loop_servidor, _uvicorn_server

    # Quando executado via pythonw.exe (sem janela preta), redireciona stdout/stderr para log
    if sys.stdout is None or sys.stderr is None:
        caminho_log = ROOT_DIR / "dados" / "gideon_background.log"
        caminho_log.parent.mkdir(parents=True, exist_ok=True)
        arquivo_log = open(caminho_log, "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = arquivo_log
        if sys.stderr is None:
            sys.stderr = arquivo_log

    # Garante saída compatível com qualquer terminal Windows (CP1252 / UTF-8)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ativar_voz_ao_iniciar = "--voz" in sys.argv

    print()
    print("  +------------------------------------------------------+")
    print("  |           GIDEON - Assistente Pessoal                |")
    print("  +------------------------------------------------------+")
    print(f"  |  Servidor: 127.0.0.1:8000                           |")
    print(f"  |  WebSocket: ws://127.0.0.1:8000/ws                  |")
    print(f"  |  Modelo: {cerebro.modelo:<43}  |")
    if ativar_voz_ao_iniciar:
        print("  |  Voz Maos-Livres: ATIVA ('Gideon')                   |")
    print("  +------------------------------------------------------+")
    print("  |  Painel local: http://127.0.0.1:8000/               |")
    print("  +------------------------------------------------------+")
    print()

    @app.on_event("startup")
    async def ao_iniciar():
        global _loop_servidor
        _loop_servidor = asyncio.get_running_loop()
        if ativar_voz_ao_iniciar:
            threading.Thread(
                target=lambda: obter_orquestrador().iniciar(),
                daemon=True,
                name="gideon-init-voz",
            ).start()

    @app.on_event("shutdown")
    async def ao_encerrar():
        if orquestrador_voz is not None and orquestrador_voz.ativo:
            orquestrador_voz.parar()

    config = uvicorn.Config(app, host="127.0.0.1", port=8000, reload=False, log_level="info")
    _uvicorn_server = uvicorn.Server(config)
    _uvicorn_server.run()


if __name__ == "__main__":
    main()
