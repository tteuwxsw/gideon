"""Servidor local da Gideon (FastAPI, streaming e eventos do aplicativo)."""

import queue
import os
import secrets
import threading
from typing import AsyncGenerator
from fastapi import (
    FastAPI, Depends, HTTPException, Header, Request, WebSocket,
    WebSocketDisconnect, status,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import json
import asyncio
import keyring
from google import genai

from gideon.cerebro import Cerebro
from gideon.auth import obter_ou_criar_token, token_valido
from gideon.caminhos import DADOS_DIR, ROOT_DIR, WEB_DIR
from gideon.gate import PARADO, ativar_parada_emergencia, retomar_execucao
from gideon.memoria import Memoria
from gideon.versao import VERSAO

# Diretórios base
TOKEN_FILE = DADOS_DIR / "auth_token.txt"
ORIGENS_LOCAIS = {"http://127.0.0.1:8000", "http://localhost:8000", "http://127.0.0.1", "http://localhost"}
_bootstrap_token = os.environ.pop("GIDEON_BOOTSTRAP_TOKEN", None)
_runtime_token = os.environ.pop("GIDEON_RUNTIME_TOKEN", None)
_bootstrap_lock = threading.Lock()

DADOS_DIR.mkdir(parents=True, exist_ok=True)
WEB_DIR.mkdir(parents=True, exist_ok=True)


TOKEN_LOCAL = obter_ou_criar_token(TOKEN_FILE)

app = FastAPI(title="Gideon — Assistente Pessoal", version=VERSAO)

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
_estado_inicializacao_voz = "nao_iniciada"
_erro_inicializacao_voz: str | None = None
_loop_servidor = None
_uvicorn_server = None

# Conexoes WebSocket ativas no aplicativo
_clientes_ws: set[WebSocket] = set()
_lock_ws = asyncio.Lock()
_estado_interface = {"estado": "idle", "nivel_voz": 0.0, "sequencia": 0}


# ─── Autenticação ──────────────────────────────────────────────

def autenticar(
    request: Request,
    x_gideon_token: str | None = Header(None, alias="x-gideon-token"),
) -> bool:
    """Verifica se o token fornecido confere com o token local."""
    token_fornecido = x_gideon_token or request.cookies.get("gideon_token") or request.query_params.get("token")

    if not token_valido(token_fornecido, TOKEN_LOCAL):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token local inválido ou ausente.",
        )
    return True


# ─── Eventos em tempo real do aplicativo ─────────────────────

async def broadcast_ws(evento: dict) -> None:
    """Envia um evento JSON para todos os clientes WebSocket conectados."""
    global _clientes_ws
    tipo = evento.get("tipo")
    if tipo == "som":
        from gideon.configuracao import obter_configuracao_sons

        config_sons = obter_configuracao_sons()
        microfone_gravando = bool(
            orquestrador_voz
            and getattr(getattr(orquestrador_voz, "ouvinte", None), "gravando", False)
        )
        if not config_sons["ativo"] or microfone_gravando:
            return
    estado = None
    if tipo == "estado_ia":
        estado = evento.get("estado")
    elif tipo == "ouvindo":
        estado = "listening" if evento.get("ativo") else "idle"
    elif tipo == "pensando":
        estado = "thinking" if evento.get("ativo") else "idle"
    elif tipo == "fala_inicio":
        estado = "speaking"
    elif tipo == "fala_fim":
        estado = "listening" if evento.get("interrompida_por_voz") else "idle"
    if estado and evento.get("origem") != "voz" and _estado_interface["estado"] in {"listening", "speaking"}:
        estado = None
    if estado:
        _estado_interface["estado"] = estado
    if tipo == "voz_nivel":
        _estado_interface["nivel_voz"] = float(evento.get("nivel", 0.0))
    if estado or tipo == "voz_nivel":
        _estado_interface["sequencia"] += 1
        evento = {**evento, "sequencia": _estado_interface["sequencia"]}
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


class GeminiChaveRequisicao(BaseModel):
    chave: str


# ─── Rotas HTTP ───────────────────────────────────────────────

# Monta os assets estáticos compilados do React se existirem
dist_assets = WEB_DIR / "dist" / "assets"
if dist_assets.is_dir():
    app.mount("/assets", StaticFiles(directory=str(dist_assets)), name="assets")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve a interface web moderna em React com fallback para legada."""
    dist_html = WEB_DIR / "dist" / "index.html"
    if dist_html.is_file():
        return HTMLResponse(dist_html.read_text(encoding="utf-8"))

    html_path = WEB_DIR / "index.html"
    if not html_path.exists():
        return HTMLResponse(
            "<h1>Interface não encontrada. Verifique gideon/web/index.html</h1>",
            status_code=404,
        )

    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/avatar/{nome}")
async def avatar_asset(nome: str):
    """Serve somente os assets conhecidos do retrato holografico."""
    permitidos = {
        "gideon-idle.webp": "image/webp",
        "gideon-speaking.webp": "image/webp",
        "gideon-thinking.webp": "image/webp",
        "gideon-welcome.webp": "image/webp",
        "gideon-head.glb": "model/gltf-binary",
    }
    if nome not in permitidos:
        raise HTTPException(status_code=404, detail="Asset de avatar nao encontrado.")
    return FileResponse(
        WEB_DIR / "avatar" / nome,
        media_type=permitidos[nome],
        headers={"Cache-Control": "public, max-age=86400"},
    )


class LoginRequisicao(BaseModel):
    token: str


@app.post("/api/auth/login")
async def login_local(req: LoginRequisicao):
    """Troca o token inicial por um cookie local que JavaScript nao consegue ler."""
    global _bootstrap_token
    autorizado = token_valido(req.token, TOKEN_LOCAL)
    if not autorizado:
        with _bootstrap_lock:
            if _bootstrap_token and secrets.compare_digest(req.token, _bootstrap_token):
                autorizado = True
                _bootstrap_token = None
    if not autorizado:
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


@app.get("/api/gemini/status")
async def status_gemini(_: bool = Depends(autenticar)):
    """Informa apenas se há uma chave; nunca devolve o segredo ao navegador."""
    configurada = bool(
        os.environ.get("GEMINI_API_KEY", "").strip()
        or keyring.get_password("gideon", "gemini_api_key")
        or keyring.get_password("alfred", "gemini_api_key")
    )
    return {"configurada": configurada, "modelo": cerebro.modelo}


@app.post("/api/gemini/chave")
async def configurar_chave_gemini(req: GeminiChaveRequisicao, _: bool = Depends(autenticar)):
    """Valida e guarda a chave no cofre do sistema, fora do código e dos logs."""
    chave = req.chave.strip()
    if len(chave) < 20:
        raise HTTPException(status_code=400, detail="A chave informada parece incompleta.")

    def validar() -> None:
        cliente = genai.Client(api_key=chave)
        cliente.models.generate_content(
            model="gemini-flash-lite-latest",
            contents="Responda somente OK.",
        )

    try:
        await asyncio.to_thread(validar)
        keyring.set_password("gideon", "gemini_api_key", chave)
        cerebro._cliente = None
        if orquestrador_voz is not None:
            orquestrador_voz.cerebro._cliente = None
    except Exception as erro:
        raise HTTPException(status_code=400, detail=f"O Gemini recusou a chave: {erro}") from erro
    return {"status": "ok", "configurada": True, "modelo": cerebro.modelo}


@app.post("/api/runtime/shutdown")
async def encerrar_runtime(x_gideon_runtime: str | None = Header(None)):
    """Permite somente ao supervisor encerrar o backend cooperativamente."""
    if not _runtime_token or not x_gideon_runtime or not secrets.compare_digest(
        x_gideon_runtime, _runtime_token
    ):
        raise HTTPException(status_code=403, detail="Supervisor invalido.")
    if _uvicorn_server is not None:
        _uvicorn_server.should_exit = True
    return {"status": "encerrando"}


@app.post("/api/runtime/bootstrap")
async def renovar_bootstrap(x_gideon_runtime: str | None = Header(None)):
    """Entrega ao supervisor um token descartavel para reabrir a interface."""
    global _bootstrap_token
    if not _runtime_token or not x_gideon_runtime or not secrets.compare_digest(
        x_gideon_runtime, _runtime_token
    ):
        raise HTTPException(status_code=403, detail="Supervisor invalido.")
    with _bootstrap_lock:
        _bootstrap_token = secrets.token_urlsafe(24)
        return {"token": _bootstrap_token}


@app.get("/api/status")
async def obter_status(_: bool = Depends(autenticar)):
    """Retorna o status atual do serviço."""
    return {
        "status": "online",
        "nome": "Gideon",
        "versao": VERSAO,
        "modelo": cerebro.modelo,
        "mensagens_no_historico": len(historico_conversa),
        "clientes_ws": len(_clientes_ws),
        "parada_emergencia": PARADO.is_set(),
    }


@app.post("/api/emergencia/parar")
async def parar_emergencia(_: bool = Depends(autenticar)):
    """Bloqueia ferramentas e cancela fala ou confirmacao pendente."""
    ativar_parada_emergencia()
    if orquestrador_voz is not None:
        orquestrador_voz._cancelar_confirmacao_pendente()
        orquestrador_voz.interromper_fala()
    await broadcast_ws({"tipo": "parada_emergencia", "ativa": True})
    return {"status": "parado", "parada_emergencia": True}


@app.post("/api/emergencia/retomar")
async def retomar_emergencia(_: bool = Depends(autenticar)):
    """Libera ferramentas depois de uma decisao explicita do usuario."""
    retomar_execucao()
    await broadcast_ws({"tipo": "parada_emergencia", "ativa": False})
    return {"status": "ativo", "parada_emergencia": False}


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


@app.get("/api/automacoes")
async def listar_automacoes_api(_: bool = Depends(autenticar)):
    """Lista as automações registradas na Gideon."""
    from gideon.tools.automacoes_tools import automacao_listar
    return automacao_listar()


@app.get("/api/habilidades")
async def listar_habilidades_api(_: bool = Depends(autenticar)):
    """Lista as habilidades registradas da Gideon."""
    from gideon.tools.automacoes_tools import habilidade_listar
    return habilidade_listar()


@app.get("/api/perfil")
async def obter_perfil_api(_: bool = Depends(autenticar)):
    """Retorna o perfil vivo do Henry."""
    from gideon import perfil
    return {"perfil": perfil.ler()}


class IdiomaRequisicao(BaseModel):
    idioma: str


@app.get("/api/idioma")
async def obter_idioma_api(_: bool = Depends(autenticar)):
    """Retorna o idioma ativo e os idiomas suportados."""
    from gideon.configuracao import obter_idioma, IDIOMAS_SUPORTADOS
    idioma_atual = obter_idioma()
    return {
        "status": "ok",
        "idioma": idioma_atual,
        "idiomas": [
            {"codigo": cod, "nome": dados["nome"], "descricao": dados["descricao"]}
            for cod, dados in IDIOMAS_SUPORTADOS.items()
        ],
    }


@app.get("/api/sons/{tipo}")
async def obter_som_api(tipo: str):
    """Retorna o áudio WAV de um earcon procedural da Gideon."""
    from fastapi.responses import Response
    from gideon.voz.sons import obter_wav_bytes
    try:
        dados_wav = obter_wav_bytes(tipo)
        return Response(content=dados_wav, media_type="audio/wav")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


class ConfiguracaoSonsRequisicao(BaseModel):
    ativo: bool
    volume: float


@app.get("/api/configuracao/sons")
async def obter_configuracao_sons_api(_: bool = Depends(autenticar)):
    """Retorna a preferência persistente dos earcons da interface."""
    from gideon.configuracao import obter_configuracao_sons

    return {"status": "ok", **obter_configuracao_sons()}


@app.post("/api/configuracao/sons")
async def definir_configuracao_sons_api(req: ConfiguracaoSonsRequisicao, _: bool = Depends(autenticar)):
    """Liga/desliga earcons e limita o volume máximo a 50%."""
    from gideon.configuracao import definir_configuracao_sons

    return {"status": "ok", **definir_configuracao_sons(req.ativo, req.volume)}


@app.post("/api/idioma")
async def definir_idioma_api(req: IdiomaRequisicao, _: bool = Depends(autenticar)):
    """Atualiza o idioma da Gideon (salva em config e sincroniza a voz)."""
    from gideon.configuracao import definir_idioma, IDIOMAS_SUPORTADOS
    if req.idioma not in IDIOMAS_SUPORTADOS:
        raise HTTPException(
            status_code=400,
            detail=f"Idioma '{req.idioma}' inválido. Suportados: {list(IDIOMAS_SUPORTADOS.keys())}",
        )
    idioma_salvo = definir_idioma(req.idioma)
    if orquestrador_voz is not None:
        orquestrador_voz.atualizar_idioma(idioma_salvo)
    await broadcast_ws({"tipo": "idioma_alterado", "idioma": idioma_salvo})
    return {"status": "ok", "idioma": idioma_salvo}


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

    # 1. Verifica se é um comando explícito de memória ou uma intenção de execução real no Windows
    resposta_comando_local = memoria.processar_comando_explicito(texto_usuario)
    if not resposta_comando_local:
        from gideon.voz.comandos import interpretar_intencao_natural, detectar_comando_sistema
        contexto = orquestrador_voz.contexto_conversa if orquestrador_voz else {}
        intencao = interpretar_intencao_natural(texto_usuario, contexto)
        if (
            (orquestrador_voz and orquestrador_voz._confirmacao_pendente)
            or detectar_comando_sistema(texto_usuario) is not None
            or intencao is not None
        ):
            resposta_comando_local = await asyncio.to_thread(
                obter_orquestrador().processar_fala_local_rapida,
                texto_usuario,
                falar_feedback_imediato=False,
            )

    if resposta_comando_local:
        # Grava no histórico permanente
        memoria.gravar_mensagem("voce", texto_usuario)
        memoria.gravar_mensagem("assistente", resposta_comando_local)
        historico_conversa.append({"role": "assistant", "content": resposta_comando_local})

        async def gerador_comando() -> AsyncGenerator[str, None]:
            # Transmite o texto do comando
            yield f"data: {json.dumps({'tipo': 'chunk', 'texto': resposta_comando_local}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.05)

            # Transmite evento fim com 0 custo de API (executado localmente)
            yield f"data: {json.dumps({'tipo': 'fim', 'total_tokens': 0, 'custo_estimado': 0.0, 'modelo': 'executor_verificado'}, ensure_ascii=False)}\n\n"
            await broadcast_ws({"tipo": "pensando", "ativo": False})

        return StreamingResponse(
            gerador_comando(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    # 2. Se for pergunta comum, busca lembranças relevantes para injetar no cérebro
    lembrancas = memoria.recuperar_lembrancas_para_prompt(texto_usuario)

    # Atualiza o avatar enquanto a resposta e gerada.
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

                    # Na primeira palavra, a resposta deixa o estado de raciocinio.
                    if primeira_palavra:
                        await broadcast_ws({"tipo": "pensando", "ativo": False})
                        primeira_palavra = False

                elif evento["tipo"] == "fim":
                    resposta_completa = "".join(texto_resposta)
                    historico_conversa.append({
                        "role": "assistant",
                        "content": resposta_completa,
                    })

                    # Persiste a conversa na memória permanente SQLite
                    memoria.gravar_mensagem("voce", texto_usuario)
                    memoria.gravar_mensagem("assistente", resposta_completa)

                    await broadcast_ws({"tipo": "pensando", "ativo": False})
                    await broadcast_ws({"tipo": "som", "som": "conclusao"})

                elif evento["tipo"] == "erro":
                    await broadcast_ws({"tipo": "pensando", "ativo": False})
                    await broadcast_ws({"tipo": "som", "som": "erro"})

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


# ─── WebSocket do aplicativo ──────────────────────────────────

@app.websocket("/ws")
async def websocket_app(websocket: WebSocket):
    """Mantem o avatar do aplicativo sincronizado com voz e processamento."""
    origem = websocket.headers.get("origin")
    if origem and origem.rstrip("/") not in ORIGENS_LOCAIS:
        await websocket.close(code=4003, reason="Origem nao autorizada")
        return

    token_header = websocket.headers.get("x-gideon-token")
    token_cookie = websocket.cookies.get("gideon_token")
    token_param = websocket.query_params.get("token")
    token = token_header or token_cookie or token_param
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
        "estado_interface": dict(_estado_interface),
    }, ensure_ascii=False))

    try:
        while True:
            data = await websocket.receive_text()
            try:
                mensagem = json.loads(data)
                tipo = mensagem.get("tipo", "")

                if tipo != "pronto":
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
    global orquestrador_voz, _estado_inicializacao_voz, _erro_inicializacao_voz
    if orquestrador_voz is None:
        with _lock_orquestrador:
            if orquestrador_voz is None:
                _estado_inicializacao_voz = "inicializando"
                try:
                    from gideon.voz.orquestrador import OrquestradorVoz

                    def repassar(ev):
                        if ev.get("tipo") == "abrir_interface":
                            from gideon.supervisor import sinalizar_abertura

                            sinalizar_abertura()
                        if _loop_servidor and _loop_servidor.is_running():
                            asyncio.run_coroutine_threadsafe(
                                broadcast_ws({**ev, "origem": "voz"}),
                                _loop_servidor,
                            )

                    orquestrador_voz = OrquestradorVoz(cerebro, memoria, repassar)
                    _estado_inicializacao_voz = "pronta"
                    _erro_inicializacao_voz = None
                except Exception as erro:
                    _estado_inicializacao_voz = "falhou"
                    _erro_inicializacao_voz = str(erro)[:160]
                    raise
    return orquestrador_voz


def _inicializar_voz_em_background(ativar: bool = True) -> None:
    """Prepara os modelos de voz sem bloquear o servidor HTTP."""
    global _estado_inicializacao_voz
    with _lock_orquestrador:
        if orquestrador_voz is not None:
            if ativar:
                threading.Thread(target=orquestrador_voz.iniciar, daemon=True).start()
            return
        if _estado_inicializacao_voz == "inicializando":
            return
        _estado_inicializacao_voz = "inicializando"

    def preparar() -> None:
        try:
            orc = obter_orquestrador()
            if ativar:
                orc.iniciar()
        except Exception as erro:
            print(f"  [Gideon Voz] Falha ao inicializar: {erro}")

    threading.Thread(target=preparar, daemon=True, name="gideon-init-voz").start()


@app.post("/api/voz/iniciar")
async def iniciar_voz(_: bool = Depends(autenticar)):
    """Inicia o ouvinte contínuo de voz (Wake Word 'Gideon')."""
    if orquestrador_voz is None:
        _inicializar_voz_em_background(ativar=True)
        return {"status": "inicializando", "mensagem": "A voz esta sendo preparada."}
    await asyncio.to_thread(orquestrador_voz.iniciar)
    return {"status": "ok", "mensagem": "Escuta por voz ativada."}


@app.post("/api/voz/parar")
async def parar_voz(_: bool = Depends(autenticar)):
    """Pausa a escuta contínua de voz."""
    if orquestrador_voz is not None:
        await asyncio.to_thread(orquestrador_voz.parar)
    return {"status": "ok", "mensagem": "Escuta por voz pausada."}


@app.get("/api/voz/status")
async def status_voz(_: bool = Depends(autenticar)):
    """Retorna o estado detalhado da escuta de voz, modo atual e sensibilidade."""
    if orquestrador_voz is None:
        return {
            "status": "ok",
            "inicializacao": _estado_inicializacao_voz,
            "ativa": False,
            "erro": _erro_inicializacao_voz,
        }
    return {"status": "ok", "inicializacao": "pronta", **orquestrador_voz.obter_configuracao()}


class ConfiguracaoVozRequisicao(BaseModel):
    modo_escuta: str | None = None
    duracao_sessao: float | None = None
    sensibilidade: float | None = None
    barge_in_ativo: bool | None = None
    palavras_ativacao: list[str] | None = None


@app.post("/api/voz/configurar")
async def configurar_voz(req: ConfiguracaoVozRequisicao, _: bool = Depends(autenticar)):
    """Configura modo de escuta (ativacao_por_nome, conversa_continua, conversa_livre), sensibilidade e sessão."""
    orc = await asyncio.to_thread(obter_orquestrador)
    cfg = await asyncio.to_thread(
        orc.configurar,
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
    interrompeu = orquestrador_voz.interromper_fala() if orquestrador_voz else False
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
        caminho_log = DADOS_DIR / "gideon_background.log"
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

        # Conecta e inicializa o motor de automações por relógio de parede
        from gideon.automacoes import obter_motor
        motor = obter_motor()

        def _callback_notificar(texto: str, falar: bool, meta: dict):
            memoria.gravar_mensagem("assistente", texto)
            historico_conversa.append({"role": "assistant", "content": texto})
            if _loop_servidor and _loop_servidor.is_running():
                asyncio.run_coroutine_threadsafe(
                    broadcast_ws({"tipo": "resposta_voz", "texto": texto, "automacao": True}),
                    _loop_servidor,
                )
            if falar:
                try:
                    orc = obter_orquestrador()
                    if orc and orc.sintetizador:
                        orc.sintetizador.falar(texto)
                except Exception:
                    pass

        def _callback_pensar(prompt_instrucao: str, usar_tools: bool) -> str:
            partes = []
            for ev in cerebro.pensar_stream([{"role": "user", "content": prompt_instrucao}], usar_ferramentas=usar_tools):
                if ev.get("tipo") == "chunk":
                    partes.append(ev.get("texto", ""))
            return "".join(partes).strip()

        motor.notificar = _callback_notificar
        motor._pensar = _callback_pensar
        motor.iniciar()

        # Inicializa o vigilante proativo de sistema
        from gideon.vigilante import obter_vigilante

        def _notificar_vigilante(ev: dict):
            if _loop_servidor and _loop_servidor.is_running():
                asyncio.run_coroutine_threadsafe(broadcast_ws(ev), _loop_servidor)

        vigilante = obter_vigilante(
            notificador=_notificar_vigilante,
            fala_callback=lambda txt: _callback_notificar(txt, falar=True, meta={"origem": "vigilante"}),
        )
        vigilante.iniciar()

        if ativar_voz_ao_iniciar:
            _inicializar_voz_em_background(ativar=True)

    @app.on_event("shutdown")
    async def ao_encerrar():
        from gideon.automacoes import obter_motor
        obter_motor().parar()
        from gideon.vigilante import obter_vigilante
        obter_vigilante().parar()
        if orquestrador_voz is not None and orquestrador_voz.ativo:
            orquestrador_voz.parar()
        try:
            from gideon.mcp import obter_gerenciador_mcp

            obter_gerenciador_mcp().encerrar_todos()
        except Exception:
            pass

    config = uvicorn.Config(app, host="127.0.0.1", port=8000, reload=False, log_level="info")
    _uvicorn_server = uvicorn.Server(config)
    _uvicorn_server.run()


if __name__ == "__main__":
    main()
