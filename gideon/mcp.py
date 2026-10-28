"""Cliente Nativo do Protocolo MCP (Model Context Protocol) para a Gideon.

Permite conectar a qualquer servidor MCP compatível (arquivos, banco de dados, GitHub,
APIs externas) via stdio JSON-RPC 2.0 e expor suas ferramentas nativamente ao Gemini.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any, Callable

from gideon.caminhos import DADOS_DIR
from gideon.gate import Ferramenta, Risco

ARQUIVO_MCP = DADOS_DIR / "mcp_servers.json"

CONFIG_PADRAO = {
    "mcpServers": {
        "sistema_arquivos": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", str(Path.home() / "Documents")],
            "ativo": False,
            "descricao": "Servidor MCP oficial para navegação profunda no sistema de arquivos.",
        }
    }
}


def _garantir_config_mcp() -> dict[str, Any]:
    ARQUIVO_MCP.parent.mkdir(parents=True, exist_ok=True)
    if not ARQUIVO_MCP.exists():
        ARQUIVO_MCP.write_text(json.dumps(CONFIG_PADRAO, indent=2, ensure_ascii=False), encoding="utf-8")
        return CONFIG_PADRAO
    try:
        return json.loads(ARQUIVO_MCP.read_text(encoding="utf-8"))
    except Exception:
        return CONFIG_PADRAO


class SessaoServidorMCP:
    """Gerencia o ciclo de vida e comunicação JSON-RPC com um processo de servidor MCP."""

    def __init__(self, nome: str, comando: str, args: list[str], env: dict[str, str] | None = None):
        self.nome = nome
        self.comando = comando
        self.args = args
        self.env = env or {}
        self.processo: subprocess.Popen | None = None
        self._req_id = 0
        self._lock = threading.Lock()
        self.ferramentas_descobertas: list[dict[str, Any]] = []

    def iniciar(self, timeout_s: float = 6.0) -> bool:
        """Inicializa o subprocesso MCP e realiza o handshake de protocolo."""
        with self._lock:
            try:
                cmd_completo = [self.comando, *self.args]
                ambiente = os.environ.copy()
                ambiente.update(self.env)

                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                self.processo = subprocess.Popen(
                    cmd_completo,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    env=ambiente,
                    creationflags=flags,
                )

                # 1. Envia requisição 'initialize'
                req_init = {
                    "jsonrpc": "2.0",
                    "id": self._proximo_id(),
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "Gideon", "version": "1.0"},
                    },
                }
                res_init = self._enviar_e_aguardar(req_init, timeout_s=timeout_s)
                if not res_init or "result" not in res_init:
                    self.encerrar()
                    return False

                # 2. Envia notificação 'notifications/initialized'
                notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
                self._escrever_linha(notif)

                # 3. Lista as ferramentas disponibilizadas pelo servidor
                req_tools = {
                    "jsonrpc": "2.0",
                    "id": self._proximo_id(),
                    "method": "tools/list",
                    "params": {},
                }
                res_tools = self._enviar_e_aguardar(req_tools, timeout_s=timeout_s)
                if res_tools and "result" in res_tools:
                    self.ferramentas_descobertas = res_tools["result"].get("tools", [])

                return True
            except Exception as e:
                print(f"  [MCP] Falha ao iniciar servidor '{self.nome}': {e}")
                self.encerrar()
                return False

    def executar_ferramenta(self, nome_ferramenta: str, argumentos: dict[str, Any], timeout_s: float = 12.0) -> dict[str, Any]:
        """Invoca uma ferramenta via JSON-RPC 'tools/call'."""
        with self._lock:
            if not self.processo or self.processo.poll() is not None:
                if not self.iniciar():
                    return {"sucesso": False, "erro": f"Servidor MCP '{self.nome}' indisponível."}

            req = {
                "jsonrpc": "2.0",
                "id": self._proximo_id(),
                "method": "tools/call",
                "params": {"name": nome_ferramenta, "arguments": argumentos},
            }

            res = self._enviar_e_aguardar(req, timeout_s=timeout_s)
            if not res:
                return {"sucesso": False, "erro": f"Tempo esgotado aguardando MCP '{self.nome}'."}

            if "error" in res:
                return {"sucesso": False, "erro": res["error"].get("message", "Erro interno MCP")}

            resultado = res.get("result", {})
            conteudos = resultado.get("content", [])
            textos = [c.get("text", "") for c in conteudos if c.get("type") == "text"]
            resposta_texto = "\n".join(textos) if textos else json.dumps(resultado, ensure_ascii=False)

            return {
                "sucesso": not resultado.get("isError", False),
                "conteudo": resposta_texto,
                "mensagem_humana": resposta_texto,
            }

    def _proximo_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _escrever_linha(self, objeto: dict[str, Any]) -> None:
        if self.processo and self.processo.stdin:
            linha = json.dumps(objeto, ensure_ascii=False) + "\n"
            self.processo.stdin.write(linha)
            self.processo.stdin.flush()

    def _enviar_e_aguardar(self, requisicao: dict[str, Any], timeout_s: float = 5.0) -> dict[str, Any] | None:
        if not self.processo or not self.processo.stdin or not self.processo.stdout:
            return None

        self._escrever_linha(requisicao)
        id_esperado = requisicao.get("id")

        inicio = time.time()
        while time.time() - inicio < timeout_s:
            if self.processo.poll() is not None:
                return None
            linha = self.processo.stdout.readline()
            if not linha:
                time.sleep(0.05)
                continue
            try:
                d = json.loads(linha.strip())
                if d.get("id") == id_esperado:
                    return d
            except json.JSONDecodeError:
                continue

        return None

    def encerrar(self) -> None:
        """Finaliza o subprocesso com segurança."""
        if self.processo:
            try:
                self.processo.terminate()
                self.processo.wait(timeout=2)
            except Exception:
                try:
                    self.processo.kill()
                except Exception:
                    pass
            self.processo = None


class GerenciadorMCP:
    """Gerencia todas as conexões MCP e converte suas ferramentas para o catálogo da Gideon."""

    def __init__(self):
        self.sessoes: dict[str, SessaoServidorMCP] = {}
        self._lock = threading.Lock()

    def carregar_e_registrar(self) -> list[Ferramenta]:
        """Lê `mcp_servers.json`, inicializa os servidores ativos e retorna a lista de ferramentas."""
        with self._lock:
            config = _garantir_config_mcp()
            servers = config.get("mcpServers", {})
            novas_ferramentas: list[Ferramenta] = []

            for nome, cfg in servers.items():
                if not cfg.get("ativo", False):
                    continue

                cmd = cfg.get("command", "")
                args = cfg.get("args", [])
                env = cfg.get("env", {})

                sessao = SessaoServidorMCP(nome, cmd, args, env)
                if sessao.iniciar():
                    self.sessoes[nome] = sessao
                    print(f"  [MCP] Servidor '{nome}' conectado! ({len(sessao.ferramentas_descobertas)} ferramentas)")

                    for t_info in sessao.ferramentas_descobertas:
                        t_nome = t_info.get("name", "sem_nome")
                        t_desc = t_info.get("description", f"Ferramenta fornecida pelo servidor MCP '{nome}'.")
                        t_schema = t_info.get("inputSchema", {"type": "object", "properties": {}})

                        nome_registrado = f"mcp_{nome}_{t_nome}"

                        def criar_handler(s: SessaoServidorMCP, nome_original: str):
                            return lambda **kwargs: s.executar_ferramenta(nome_original, kwargs)

                        ferr = Ferramenta(
                            nome=nome_registrado,
                            descricao=f"[MCP {nome}] {t_desc}",
                            risco=Risco.AMARELO,
                            executar=criar_handler(sessao, t_nome),
                            frase=lambda nome_orig=t_nome, s_nome=nome, **kw: f"executar ação MCP '{nome_orig}' no servidor '{s_nome}'",
                            parametros=t_schema,
                        )
                        novas_ferramentas.append(ferr)

            return novas_ferramentas

    def encerrar_todos(self) -> None:
        """Encerra todas as sessões de servidores MCP ativos."""
        with self._lock:
            for s in self.sessoes.values():
                s.encerrar()
            self.sessoes.clear()


_gerenciador_global_mcp: GerenciadorMCP | None = None


def obter_gerenciador_mcp() -> GerenciadorMCP:
    global _gerenciador_global_mcp
    if _gerenciador_global_mcp is None:
        _gerenciador_global_mcp = GerenciadorMCP()
    return _gerenciador_global_mcp


def listar_servidores_mcp() -> dict[str, Any]:
    """Lista a configuração atual dos servidores MCP e seus status de conexão."""
    config = _garantir_config_mcp()
    mgr = obter_gerenciador_mcp()
    servidores = config.get("mcpServers", {})

    status_lista = []
    for nome, cfg in servidores.items():
        ativo = cfg.get("ativo", False)
        conectado = nome in mgr.sessoes and mgr.sessoes[nome].processo is not None
        ferramentas = [t.get("name") for t in mgr.sessoes[nome].ferramentas_descobertas] if conectado else []
        status_lista.append({
            "nome": nome,
            "ativo": ativo,
            "conectado": conectado,
            "descricao": cfg.get("descricao", ""),
            "ferramentas": ferramentas,
        })

    return {
        "sucesso": True,
        "arquivo_config": str(ARQUIVO_MCP),
        "servidores": status_lista,
        "mensagem_humana": f"Há {len(status_lista)} servidores MCP configurados em '{ARQUIVO_MCP.name}'.",
    }


FERRAMENTAS_MCP: list[Ferramenta] = [
    Ferramenta(
        nome="listar_servidores_mcp",
        descricao="Lista os servidores MCP (Model Context Protocol) cadastrados e suas ferramentas disponíveis.",
        risco=Risco.VERDE,
        executar=listar_servidores_mcp,
        frase=lambda **kwargs: "listar os servidores e ferramentas MCP configurados",
        parametros={"type": "object", "properties": {}},
    ),
]
