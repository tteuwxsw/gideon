"""Conector do cérebro da Gideon com suporte a streaming, Function Calling e custos."""

from typing import Generator, Any
import re
import keyring
from google import genai
from google.genai import types
from gideon.gate import LIMITE_DIARIO_USD, gasto_diario_atual, somar_gasto
from gideon.persona import obter_prompt_sistema

# Preços de referência por 1 milhão de tokens (USD)
# Na cota do plano o custo real é $0, mas calculamos para telemetria
PRECO_PROMPT_1M = 0.10        # $0.10 por 1M tokens de entrada
PRECO_RESPOSTA_1M = 0.40      # $0.40 por 1M tokens de saída

# Cascata do modelo mais rápido e estável para fallbacks automáticos
MODELO_PRINCIPAL = "gemini-flash-lite-latest"
MODELOS_CASCATA = (
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
    "gemini-3-flash-preview",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
)

_PADRAO_RACIOCINIO_PROFUNDO = re.compile(
    r"\b(analis[ea]|passo a passo|detalhadamente|arquitetura|algoritmo|codigo|código|"
    r"debug|refator[ea]|compar[ea]|estrategia|estratégia|planej[ea]|calcul[ea]|demonstre)\b",
    re.IGNORECASE,
)

# Nome do serviço no cofre do sistema (Windows Credential Manager)
_SERVICO_COFRE = "gideon"
_SERVICO_LEGADO = "alfred"  # fallback para chaves guardadas antes da renomeação
_CONTA_COFRE = "gemini_api_key"


def _obter_chave_cofre() -> str:
    """Busca a chave da API no cofre, com fallback para o nome antigo."""
    chave = keyring.get_password(_SERVICO_COFRE, _CONTA_COFRE)
    if chave:
        return chave

    # Tenta o nome antigo (migração automática)
    chave = keyring.get_password(_SERVICO_LEGADO, _CONTA_COFRE)
    if chave:
        # Migra para o novo nome automaticamente
        keyring.set_password(_SERVICO_COFRE, _CONTA_COFRE, chave)
        return chave

    return ""


def _obter_ferramentas_gemini() -> list[types.Tool]:
    """Prepara o registro de ferramentas da Gideon para declaração no Gemini."""
    try:
        from gideon.tools import obter_catalogo_ferramentas
        catalogo = obter_catalogo_ferramentas()
        decls: list[types.FunctionDeclaration] = []
        for f in catalogo.listar_todas():
            if not f.expor_ao_modelo:
                continue
            schema = f.parametros if f.parametros else {"type": "object", "properties": {}}
            decls.append(
                types.FunctionDeclaration(
                    name=f.nome,
                    description=f.descricao,
                    parameters_json_schema=schema,
                )
            )
        if decls:
            return [types.Tool(function_declarations=decls)]
    except Exception:
        pass
    return []


class Cerebro:
    """Interface unificada de comunicação com o cérebro de IA."""

    def __init__(self, modelo: str = MODELO_PRINCIPAL):
        self.modelo = modelo
        self._cliente: genai.Client | None = None

    @staticmethod
    def _orcamento_raciocinio(mensagens: list[dict[str, str]]) -> int:
        """Usa resposta imediata (budget=0) na voz/conversa rápida e raciocínio profundo em pedidos complexos."""
        if not mensagens:
            return 0
        ultima = mensagens[-1].get("content", "")
        if len(ultima.split()) >= 14 or _PADRAO_RACIOCINIO_PROFUNDO.search(ultima):
            return 1024
        return 0

    def _obter_cliente(self) -> genai.Client:
        """Obtém ou inicializa o cliente com a chave guardada no cofre."""
        if self._cliente is not None:
            return self._cliente

        chave = _obter_chave_cofre()
        if not chave:
            raise RuntimeError(
                "Chave do Gemini não encontrada no cofre do sistema. "
                "Execute guardar_chave.py para configurá-la."
            )

        self._cliente = genai.Client(api_key=chave)
        return self._cliente

    def calcular_custo(self, prompt_tokens: int, resposta_tokens: int) -> float:
        """Calcula o custo estimado em dólares com base na contagem de tokens."""
        custo_prompt = (prompt_tokens / 1_000_000) * PRECO_PROMPT_1M
        custo_resposta = (resposta_tokens / 1_000_000) * PRECO_RESPOSTA_1M
        return custo_prompt + custo_resposta

    def pensar_stream(
        self,
        mensagens: list[dict[str, str]],
        lembrancas: str = "",
        licoes: str = "",
        usar_ferramentas: bool = True,
        executor: Any | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Gera respostas em fluxo (streaming), executando ferramentas via Function Calling quando necessário.

        Formato das mensagens: [{'role': 'user'|'assistant', 'content': '...'}]
        """
        if gasto_diario_atual() >= LIMITE_DIARIO_USD:
            yield {
                "tipo": "erro",
                "mensagem": f"O limite diário de uso do Gemini (${LIMITE_DIARIO_USD:.2f}) foi atingido.",
            }
            return

        try:
            cliente = self._obter_cliente()
        except Exception as e:
            yield {
                "tipo": "erro",
                "mensagem": f"Erro de autenticação: {str(e)}",
            }
            return

        # Monta prompt de sistema com raciocínio adaptativo
        if not licoes:
            try:
                from gideon.memoria import Memoria
                licoes = Memoria().formatar_licoes_para_prompt()
            except Exception:
                licoes = ""
        prompt_sistema = obter_prompt_sistema(lembrancas=lembrancas, licoes=licoes)
        budget_thinking = self._orcamento_raciocinio(mensagens)
        ferramentas_gemini = _obter_ferramentas_gemini() if usar_ferramentas else None

        thinking_cfg = (
            types.ThinkingConfig(thinking_budget=budget_thinking)
            if (budget_thinking > 0 and not usar_ferramentas)
            else types.ThinkingConfig(thinking_budget=0)
        )

        config = types.GenerateContentConfig(
            system_instruction=prompt_sistema,
            temperature=0.9,  # TURBO: resposta instantânea  # PATCH: resposta mais rápida
            thinking_config=thinking_cfg,
            tools=ferramentas_gemini if ferramentas_gemini else None,
        )

        # Converte histórico para o formato do Google GenAI
        contents_base: list[types.Content] = []
        for msg in mensagens:
            role = "user" if msg["role"] == "user" else "model"
            contents_base.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=msg["content"])],
                )
            )

        # Prepara o executor confiável caso seja necessário rodar ferramentas
        if executor is None and usar_ferramentas:
            try:
                from gideon.executor import ExecutorConfiavel
                from gideon.tools import obter_catalogo_ferramentas
                executor = ExecutorConfiavel(obter_catalogo_ferramentas())
            except Exception:
                executor = None

        candidatos = [self.modelo] + [m for m in MODELOS_CASCATA if m != self.modelo]
        ultimo_erro: Exception | None = None

        for idx, modelo_tentativa in enumerate(candidatos):
            prompt_tokens_acum = 0
            resposta_tokens_acum = 0
            total_tokens_acum = 0
            texto_acumulado_geral: list[str] = []
            rodada = 0
            max_rodadas = 1  # TURBO: sem retry  # PATCH: menos tentativas

            # Cópia isolada do histórico para cada tentativa de modelo
            contents: list[types.Content] = [
                types.Content(role=c.role, parts=list(c.parts)) for c in contents_base
            ]

            try:
                while rodada < max_rodadas:
                    rodada += 1
                    stream = cliente.models.generate_content_stream(
                        model=modelo_tentativa,
                        contents=contents,
                        config=config,
                    )

                    function_calls_rodada: list[Any] = []
                    model_parts_rodada: list[Any] = []
                    texto_rodada: list[str] = []

                    for chunk in stream:
                        if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts:
                            model_parts_rodada.extend(chunk.candidates[0].content.parts)

                        if chunk.text:
                            texto_rodada.append(chunk.text)
                            texto_acumulado_geral.append(chunk.text)
                            yield {
                                "tipo": "chunk",
                                "texto": chunk.text,
                            }

                        if chunk.function_calls:
                            for fc in chunk.function_calls:
                                function_calls_rodada.append(fc)

                        # Coleta metadados de uso se disponíveis
                        if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                            meta = chunk.usage_metadata
                            if getattr(meta, "prompt_token_count", None) is not None:
                                prompt_tokens_acum = max(prompt_tokens_acum, meta.prompt_token_count)
                            if getattr(meta, "candidates_token_count", None) is not None:
                                resposta_tokens_acum += meta.candidates_token_count
                            if getattr(meta, "total_token_count", None) is not None:
                                total_tokens_acum = max(total_tokens_acum, meta.total_token_count)

                    # Se o modelo não chamou ferramentas, o fluxo concluiu normalmente
                    if not function_calls_rodada:
                        break

                    # Registra no histórico os parts gerados pelo modelo preservando o thought_signature
                    if model_parts_rodada:
                        contents.append(
                            types.Content(
                                role="model",
                                parts=model_parts_rodada,
                            )
                        )
                    else:
                        contents.append(
                            types.Content(
                                role="model",
                                parts=[types.Part.from_function_call(name=fc.name, args=dict(fc.args or {})) for fc in function_calls_rodada],
                            )
                        )

                    # Processa as chamadas de função usando o ExecutorConfiavel
                    parar_por_confirmacao = False
                    respostas_parts: list[types.Part] = []

                    for fc in function_calls_rodada:
                        nome_fc = fc.name
                        args_fc = dict(fc.args or {})

                        yield {
                            "tipo": "ferramenta",
                            "ferramenta": nome_fc,
                            "parametros": args_fc,
                        }

                        if executor is not None:
                            from gideon.executor import EstadoExecucao
                            res_exec = executor.executar(nome_fc, args_fc, auto_amarelo=True)

                            # Se a ferramenta exigir confirmação expressa do Henry (risco R ou A não liberado)
                            if res_exec.estado == EstadoExecucao.NEEDS_CONFIRMATION:
                                yield {
                                    "tipo": "chunk",
                                    "texto": res_exec.mensagem_humana,
                                }
                                parar_por_confirmacao = True
                                break

                            payload_retorno = res_exec.para_dict()
                        else:
                            payload_retorno = {
                                "sucesso": False,
                                "erro": f"Executor indisponível para {nome_fc}.",
                                "mensagem_humana": f"Não consegui executar {nome_fc}.",
                            }

                        respostas_parts.append(
                            types.Part.from_function_response(name=nome_fc, response=payload_retorno)
                        )

                    if parar_por_confirmacao:
                        break

                    # Adiciona as respostas das ferramentas como turno do usuário
                    contents.append(
                        types.Content(
                            role="user",
                            parts=respostas_parts,
                        )
                    )

                # Estimativa de tokens caso a API não tenha retornado contagem
                if total_tokens_acum == 0:
                    caracteres_prompt = sum(len(m["content"]) for m in mensagens) + len(prompt_sistema)
                    caracteres_resposta = len("".join(texto_acumulado_geral))
                    prompt_tokens_acum = max(1, caracteres_prompt // 4)
                    resposta_tokens_acum = max(1, caracteres_resposta // 4)
                    total_tokens_acum = prompt_tokens_acum + resposta_tokens_acum

                custo = self.calcular_custo(prompt_tokens_acum, resposta_tokens_acum)
                somar_gasto(custo)

                yield {
                    "tipo": "fim",
                    "prompt_tokens": prompt_tokens_acum,
                    "resposta_tokens": resposta_tokens_acum,
                    "total_tokens": total_tokens_acum,
                    "custo_estimado": custo,
                    "modelo": modelo_tentativa,
                }
                return

            except Exception as e:
                ultimo_erro = e
                # Se ainda não emitiu texto e restam modelos candidatos, avança para o próximo
                if not texto_acumulado_geral and idx < len(candidatos) - 1:
                    continue
                break

        erro_str = str(ultimo_erro or "Erro desconhecido")
        if "429" in erro_str or "RESOURCE_EXHAUSTED" in erro_str:
            mensagem_amigavel = (
                "O limite temporário de requisições foi atingido. "
                "Por gentileza, aguarde alguns instantes."
            )
        elif "503" in erro_str or "UNAVAILABLE" in erro_str:
            mensagem_amigavel = (
                "Os servidores do modelo estão temporariamente com alta demanda. "
                "Tentarei novamente em instantes."
            )
        elif "404" in erro_str or "NOT_FOUND" in erro_str:
            mensagem_amigavel = (
                f"O modelo '{self.modelo}' está indisponível no momento."
            )
        elif "Failed to connect" in erro_str or "connection" in erro_str.lower():
            mensagem_amigavel = (
                "Falha ao conectar com o servidor. "
                "Verifique sua conexão com a internet."
            )
        else:
            mensagem_amigavel = (
                "Houve uma instabilidade temporária no processamento da solicitação. "
                "Por gentileza, repita o pedido."
            )

        yield {
            "tipo": "erro",
            "mensagem": mensagem_amigavel,
        }
