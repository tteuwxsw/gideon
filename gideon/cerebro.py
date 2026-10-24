"""Conector do cérebro da Gideon com suporte a streaming, custos e emoções."""

from typing import Generator, Any
import keyring
from google import genai
from google.genai import types
from gideon.persona import obter_prompt_sistema

# Preços padrão por 1 milhão de tokens (USD) — Gemini Flash Lite
# Na camada gratuita o custo real é $0, mas calculamos para referência
PRECO_PROMPT_1M = 0.075       # $0.075 por 1M tokens de entrada
PRECO_RESPOSTA_1M = 0.30      # $0.30 por 1M tokens de saída

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


class Cerebro:
    """Interface unificada de comunicação com o cérebro de IA."""

    def __init__(self, modelo: str = "gemini-3.1-flash-lite"):
        self.modelo = modelo
        self._cliente: genai.Client | None = None

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
    ) -> Generator[dict[str, Any], None, None]:
        """Gera respostas em fluxo (streaming), emitindo pedaços de texto e métricas finais.

        Formato das mensagens: [{'role': 'user'|'assistant', 'content': '...'}]

        Os chunks podem conter tags [EMOCAO:nome] que serão extraídas pelo
        módulo protocolo para controlar o avatar.
        """
        try:
            cliente = self._obter_cliente()
        except Exception as e:
            yield {
                "tipo": "erro",
                "mensagem": f"Erro de autenticação: {str(e)}",
            }
            return

        # Monta prompt de sistema
        prompt_sistema = obter_prompt_sistema(lembrancas=lembrancas)
        config = types.GenerateContentConfig(
            system_instruction=prompt_sistema,
            temperature=0.7,
        )

        # Converte histórico para o formato do Google GenAI
        contents: list[types.Content] = []
        for msg in mensagens:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=msg["content"])],
                )
            )

        prompt_tokens = 0
        resposta_tokens = 0
        total_tokens = 0
        texto_acumulado = []

        try:
            stream = cliente.models.generate_content_stream(
                model=self.modelo,
                contents=contents,
                config=config,
            )

            for chunk in stream:
                if chunk.text:
                    texto_acumulado.append(chunk.text)
                    yield {
                        "tipo": "chunk",
                        "texto": chunk.text,
                    }

                # Coleta metadados de uso se disponíveis
                if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                    meta = chunk.usage_metadata
                    if getattr(meta, "prompt_token_count", None) is not None:
                        prompt_tokens = meta.prompt_token_count
                    if getattr(meta, "candidates_token_count", None) is not None:
                        resposta_tokens = meta.candidates_token_count
                    if getattr(meta, "total_token_count", None) is not None:
                        total_tokens = meta.total_token_count

            # Estimativa de tokens caso a API não tenha retornado contagem
            if total_tokens == 0:
                caracteres_prompt = sum(len(m["content"]) for m in mensagens) + len(prompt_sistema)
                caracteres_resposta = len("".join(texto_acumulado))
                prompt_tokens = max(1, caracteres_prompt // 4)
                resposta_tokens = max(1, caracteres_resposta // 4)
                total_tokens = prompt_tokens + resposta_tokens

            custo = self.calcular_custo(prompt_tokens, resposta_tokens)

            yield {
                "tipo": "fim",
                "prompt_tokens": prompt_tokens,
                "resposta_tokens": resposta_tokens,
                "total_tokens": total_tokens,
                "custo_estimado": custo,
                "modelo": self.modelo,
            }

        except Exception as e:
            erro_str = str(e)
            if "429" in erro_str:
                mensagem_amigavel = (
                    "O limite temporário de requisições do Gemini foi atingido. "
                    "Aguarde alguns segundos e tente novamente."
                )
            elif "503" in erro_str:
                mensagem_amigavel = (
                    "Os servidores do Gemini estão temporariamente sobrecarregados. "
                    "Tente novamente em instantes."
                )
            elif "404" in erro_str:
                mensagem_amigavel = (
                    f"O modelo '{self.modelo}' não foi encontrado. Verifique as configurações."
                )
            elif "Failed to connect" in erro_str or "connection" in erro_str.lower():
                mensagem_amigavel = (
                    "Falha ao conectar com o servidor do Gemini. "
                    "Verifique sua conexão com a internet."
                )
            else:
                mensagem_amigavel = f"Problema ao consultar o Gemini: {erro_str[:160]}"

            yield {
                "tipo": "erro",
                "mensagem": mensagem_amigavel,
            }
