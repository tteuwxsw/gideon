"""Servidor local da Gideon (FastAPI + SSE streaming + WebSocket para avatar)."""

import secrets
import queue
import threading
import time
from pathlib import Path
from typing import AsyncGenerator
from fastapi import (
    FastAPI, Depends, HTTPException, Query, Header, Request, WebSocket,
    WebSocketDisconnect, status,
)
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import json
import asyncio

from gideon.cerebro import Cerebro
from gideon.memoria import Memoria

# Diretórios base
ROOT_DIR = Path(__file__).resolve().parent.parent
DADOS_DIR = ROOT_DIR / "dados"
WEB_DIR = ROOT_DIR / "gideon" / "web"
TOKEN_FILE = DADOS_DIR / "auth_token.txt"

DADOS_DIR.mkdir(parents=True, exist_ok=True)
WEB_DIR.mkdir(parents=True, exist_ok=True)


def obter_ou_criar_token() -> str:
    """Garante a existência de um token de autenticação local no diretório dados/."""
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token

    novo_token = secrets.token_hex(16)
    TOKEN_FILE.write_text(novo_token, encoding="utf-8")
    return novo_token


TOKEN_LOCAL = obter_ou_criar_token()

app = FastAPI(title="Gideon — Assistente Pessoal", version="0.2.0")

# Restringe CORS estritamente à máquina local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Estado em memória
cerebro = Cerebro()
memoria = Memoria()
historico_conversa: list[dict[str, str]] = []

# Conexões WebSocket ativas (avatar Godot e outros clientes)
_clientes_ws: set[WebSocket] = set()
_lock_ws = asyncio.Lock()


# ─── Autenticação ──────────────────────────────────────────────

def autenticar(
    request: Request,
    token_query: str | None = Query(None, alias="token"),
    x_gideon_token: str | None = Header(None, alias="x-gideon-token"),
) -> bool:
    """Verifica se o token fornecido confere com o token local."""
    token_fornecido = x_gideon_token or token_query
    if not token_fornecido:
        token_fornecido = request.cookies.get("gideon_token")

    if not token_fornecido or not secrets.compare_digest(token_fornecido, TOKEN_LOCAL):
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


# ─── Rotas HTTP ───────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(token: str | None = None):
    """Serve a interface web do chat local."""
    html_path = WEB_DIR / "index.html"
    if not html_path.exists():
        return HTMLResponse(
            "<h1>Interface não encontrada. Verifique gideon/web/index.html</h1>",
            status_code=404,
        )

    conteudo = html_path.read_text(encoding="utf-8")
    response = HTMLResponse(conteudo)
    if token and secrets.compare_digest(token, TOKEN_LOCAL):
        response.set_cookie(key="gideon_token", value=token, httponly=False, samesite="lax")
    return response


@app.get("/api/status")
async def obter_status(_: bool = Depends(autenticar)):
    """Retorna o status atual do serviço."""
    return {
        "status": "online",
        "nome": "Gideon",
        "versao": "0.2.0",
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

    # 1. Verifica se é um comando explícito de memória ("lembra que...", "o que você sabe sobre mim?", etc.)
    resposta_comando_memoria = memoria.processar_comando_explicito(texto_usuario)
    if resposta_comando_memoria:
        # Grava no histórico permanente
        memoria.gravar_mensagem("voce", texto_usuario)
        memoria.gravar_mensagem("assistente", resposta_comando_memoria)
        historico_conversa.append({"role": "assistant", "content": resposta_comando_memoria})

        async def gerador_comando() -> AsyncGenerator[str, None]:
            # Emite evento de início de fala para o avatar
            await broadcast_ws({"tipo": "fala_inicio", "texto": resposta_comando_memoria})

            # Extrai emoções do comando
            try:
                from gideon.protocolo import extrair_emocoes_texto
                for _, emo in extrair_emocoes_texto(resposta_comando_memoria):
                    await broadcast_ws({"tipo": "emocao", "nome": emo, "intensidade": 0.8})
            except Exception:
                pass

            # Transmite o texto do comando
            yield f"data: {json.dumps({'tipo': 'chunk', 'texto': resposta_comando_memoria}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.05)

            # Transmite evento fim com 0 custo de API (executado localmente no banco)
            yield f"data: {json.dumps({'tipo': 'fim', 'total_tokens': 0, 'custo_estimado': 0.0, 'modelo': 'memoria_local'}, ensure_ascii=False)}\n\n"
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


# ─── WebSocket para o Avatar ──────────────────────────────────

@app.websocket("/ws")
async def websocket_avatar(websocket: WebSocket, token: str | None = Query(None)):
    """Conexão WebSocket bidirecional para o avatar (Godot) ou outros clientes."""
    # Autentica
    if not token or not secrets.compare_digest(token, TOKEN_LOCAL):
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
                    print(f"  [WebSocket] Modo do avatar: {modo}")

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


# ─── Ponto de Entrada ─────────────────────────────────────────

def main():
    """Inicia o servidor web local na porta 8000, restrito ao localhost."""
    url = f"http://127.0.0.1:8000/?token={TOKEN_LOCAL}"
    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║           GIDEON — Assistente Pessoal                ║")
    print("  ╠══════════════════════════════════════════════════════╣")
    print(f"  ║  Servidor: 127.0.0.1:8000                           ║")
    print(f"  ║  WebSocket: ws://127.0.0.1:8000/ws                  ║")
    print(f"  ║  Modelo: {cerebro.modelo:<43}  ║")
    print("  ╠══════════════════════════════════════════════════════╣")
    print(f"  ║  Acesse no navegador:                               ║")
    print(f"  ║  {url}")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()

    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False, log_level="info")


if __name__ == "__main__":
    main()
