"""Orquestrador de baixa latência e execução real verificada da Gideon."""

from __future__ import annotations

from enum import Enum
import re
import threading
import time
from typing import Callable, Any, Generator

import numpy as np

from gideon.cerebro import Cerebro
from gideon.configuracao import definir_interrupcao_voz_ativa, obter_interrupcao_voz_ativa
from gideon.executor import EstadoExecucao, ExecutorConfiavel, ResultadoExecucao
from gideon.gate import ativar_parada_emergencia, retomar_execucao
from gideon.memoria import Memoria
from gideon.tools import obter_catalogo_ferramentas
from gideon.voz.comandos import (
    avaliar_fala_direcionada,
    detectar_comando_sistema,
    detectar_mudanca_modo_escuta,
    eh_encerramento_conversa,
    eh_pedido_abrir_interface,
    eh_interrupcao_barge_in,
    formatar_resposta_telemetria,
    interpretar_intencao_natural,
    normalizar,
    resposta_confirmacao,
)
from gideon.voz.fala import SintetizadorVoz
from gideon.voz.metricas import metricas_voz_global
from gideon.voz.ouvido import OuvinteVoz
from gideon.voz.despertador import identificar_saudacao
from gideon.voz.sons import tocar_som_ativacao, tocar_som_conclusao, tocar_som_erro


_PADRAO_TAG_LEGADA = re.compile(r"\[EMOCAO:[^\]]+\]", re.IGNORECASE)


def _limpar_tags_legadas(texto: str) -> str:
    """Remove marcações antigas que ainda possam existir no histórico."""
    return re.sub(r"[ \t]+", " ", _PADRAO_TAG_LEGADA.sub("", texto)).strip()


class ModoEscuta(str, Enum):
    """Três modos configuráveis de escuta inteligente da Gideon."""

    ATIVACAO_POR_NOME = "ativacao_por_nome"   # Modo 1: Aguarda "Gideon" e abre sessão
    CONVERSA_CONTINUA = "conversa_continua"   # Modo 2: Mantém sessão ativa sem repetir o nome
    CONVERSA_LIVRE = "conversa_livre"         # Modo 3: Escuta livre direcionada sem exigir wake word


class OrquestradorVoz:
    """Controla o pipeline: Microfone -> VAD -> STT -> NLU/Executor Verificado/LLM Stream -> TTS -> Áudio."""

    def __init__(
        self,
        cerebro: Cerebro | None = None,
        memoria: Memoria | None = None,
        callback_ws: Callable[[dict], Any] | None = None,
    ):
        self.cerebro = cerebro or Cerebro()
        self.memoria = memoria or Memoria()
        self.callback_ws = callback_ws
        self.ouvinte = OuvinteVoz(callback_evento=self._evento_interno)
        self.sintetizador = SintetizadorVoz(
            callback_evento=self._evento_interno,
            callback_barge_in=self._detectar_interrupcao_por_voz,
            barge_in_ativo=obter_interrupcao_voz_ativa(),
        )
        self.estado_comportamental_atual: str = "idle"

        self.ativo = False
        self.modo_escuta: ModoEscuta = ModoEscuta.ATIVACAO_POR_NOME
        self.duracao_sessao: float = 30.0  # Janela de conversação contínua

        self._thread_loop: threading.Thread | None = None
        self._parar_evento = threading.Event()
        self._cancelar_geracao = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._em_conversa_ativa = False
        self._ultimo_contato = 0.0

        self._catalogo = obter_catalogo_ferramentas()
        self._executor = ExecutorConfiavel(self._catalogo)
        self.ultima_execucao: ResultadoExecucao | None = None

        self._confirmacao_pendente: str | None = None
        self._parametros_pendentes: dict[str, Any] = {}
        self._confirmacao_expira_em = 0.0
        self._confirmacao_lock = threading.Lock()

        # Memória de curta duração enxuta (últimos 6 turnos = 12 mensagens)
        self.historico_sessao: list[dict[str, str]] = []
        self.contexto_conversa: dict[str, Any] = {}

        # Métricas do último turno
        self.ultima_origem_resposta: str = "comando_local"
        self.ultimo_nlu_ms: float = 0.0
        self.ultimo_llm_ttft_ms: float = 0.0

    def _obter_executor(self) -> ExecutorConfiavel:
        exec_inst = getattr(self, "_executor", None)
        if exec_inst is None:
            exec_inst = ExecutorConfiavel(self._catalogo)
            self._executor = exec_inst
        return exec_inst

    def _cancelar_confirmacao_pendente(self) -> bool:
        with self._confirmacao_lock:
            existia = self._confirmacao_pendente is not None
            self._confirmacao_pendente = None
            self._parametros_pendentes = {}
            self._confirmacao_expira_em = 0.0
            return existia

    def _definir_confirmacao_pendente(
        self,
        ferramenta: str | None,
        parametros: dict[str, Any] | None = None,
        *,
        validade_s: float = 30.0,
    ) -> None:
        with self._confirmacao_lock:
            self._confirmacao_pendente = ferramenta
            self._parametros_pendentes = dict(parametros or {})
            self._confirmacao_expira_em = time.time() + validade_s

    def obter_configuracao(self) -> dict[str, Any]:
        """Retorna estado, configurações e resumo de métricas p50/p95."""
        agora = time.time()
        sessao_ativa = self._em_conversa_ativa and (agora - self._ultimo_contato) < self.duracao_sessao
        ultima_exec = getattr(self, "ultima_execucao", None)
        return {
            "ativa": self.ativo,
            "voz_fixa_id": self.sintetizador.voz_id,
            "modo_escuta": self.modo_escuta.value,
            "sessao_conversa_ativa": sessao_ativa or self.modo_escuta == ModoEscuta.CONVERSA_LIVRE,
            "duracao_sessao_segundos": self.duracao_sessao,
            "sensibilidade_microfone": self.ouvinte.sensibilidade,
            "barge_in_ativo": self.sintetizador.barge_in_ativo,
            "falando": self.sintetizador.falando,
            "contexto_atual": self.contexto_conversa.get("ultimo_topico", "geral"),
            "ultima_execucao": ultima_exec.para_dict() if ultima_exec else None,
            "metricas_latencia": metricas_voz_global.resumo_estatistico(),
        }

    def configurar(
        self,
        modo_escuta: str | None = None,
        duracao_sessao: float | None = None,
        sensibilidade: float | None = None,
        barge_in_ativo: bool | None = None,
        palavras_ativacao: list[str] | None = None,
    ) -> dict[str, Any]:
        """Atualiza modo de escuta, sensibilidade do microfone e tempo de sessão."""
        if modo_escuta is not None:
            modo_norm = modo_escuta.strip().lower()
            for m in ModoEscuta:
                if m.value == modo_norm:
                    self.modo_escuta = m
                    if m == ModoEscuta.CONVERSA_LIVRE:
                        self._em_conversa_ativa = True
                        self._ultimo_contato = time.time()
                    break

        if duracao_sessao is not None:
            self.duracao_sessao = max(5.0, min(300.0, float(duracao_sessao)))

        if sensibilidade is not None or palavras_ativacao is not None:
            self.ouvinte.configurar(limiar_energia=sensibilidade, palavras_ativacao=palavras_ativacao)

        if barge_in_ativo is not None:
            ativo = definir_interrupcao_voz_ativa(bool(barge_in_ativo))
            self.sintetizador.barge_in_ativo = ativo

        return self.obter_configuracao()

    def interromper_fala(self) -> bool:
        """Interrompe imediatamente a fala atual da Gideon."""
        self._cancelar_geracao.set()
        return self.sintetizador.interromper()

    def _detectar_interrupcao_por_voz(self, audio: np.ndarray) -> bool:
        """Confirma exclusivamente a palavra de ativação antes de parar a fala."""
        if not self.sintetizador.barge_in_ativo or not self.sintetizador.falando:
            return False
        texto = self.ouvinte.transcrever_audio(audio)
        tem_wake, _ = self.ouvinte.extrair_wake_word(texto)
        if not tem_wake:
            return False
        self._cancelar_geracao.set()
        self._em_conversa_ativa = True
        self._ultimo_contato = time.time()
        self._evento_interno({"tipo": "interrupcao_voz", "texto": texto})
        return True

    def atualizar_idioma(self, novo_idioma: str) -> None:
        """Atualiza o idioma na síntese vocal e componentes dependentes."""
        self.sintetizador.atualizar_idioma(novo_idioma)

    def _evento_interno(self, evento: dict) -> None:
        if evento.get("tipo") == "estado_ia":
            self.estado_comportamental_atual = evento.get("estado", self.estado_comportamental_atual)
        if getattr(self, "callback_ws", None):
            try:
                self.callback_ws(evento)
            except Exception:
                pass

    def _definir_estado_ia(self, estado: str) -> None:
        self.estado_comportamental_atual = estado
        self._evento_interno({"tipo": "estado_ia", "estado": estado})

    def iniciar(self) -> None:
        """Inicia a escuta de voz em segundo plano."""
        with self._lifecycle_lock:
            if self.ativo:
                return
            if self._thread_loop and self._thread_loop.is_alive():
                self._thread_loop.join(timeout=1.0)
                if self._thread_loop.is_alive():
                    return
            self.ativo = True
            self._parar_evento.clear()
            self._thread_loop = threading.Thread(target=self._loop_principal, daemon=True)
            self._thread_loop.start()
            self._definir_estado_ia("idle")
            print("  [Gideon Voz] Orquestrador de voz mãos-livres ATIVADO.")

    def parar(self) -> None:
        """Encerra a escuta em segundo plano e interrompe qualquer fala ativa."""
        with self._lifecycle_lock:
            self.ativo = False
            self._parar_evento.set()
            self._cancelar_geracao.set()
            self.sintetizador.interromper()
            if self._thread_loop:
                self._thread_loop.join(timeout=1.0)
                if not self._thread_loop.is_alive():
                    self._thread_loop = None
            self._definir_estado_ia("idle")
            print("  [Gideon Voz] Orquestrador de voz DESATIVADO.")

    def _registrar_turno_sessao(self, pergunta: str, resposta_limpa: str) -> None:
        """Mantém histórico curto enxuto (últimas 12 mensagens) para não inflar o prompt."""
        self.historico_sessao.append({"role": "user", "content": pergunta})
        self.historico_sessao.append({"role": "assistant", "content": resposta_limpa})
        if len(self.historico_sessao) > 12:
            self.historico_sessao = self.historico_sessao[-12:]

    def _executar_intencao_verificada(
        self,
        intencao: dict[str, Any],
        *,
        falar_feedback_imediato: bool = False,
    ) -> str:
        """Executa uma única intenção pelo ExecutorConfiavel e retorna resposta humana baseada no resultado real."""
        acao = intencao.get("acao", "")
        params = intencao.get("parametros", {})

        # Define estado comportamental antes de executar a ferramenta
        if acao == "inspecionar_contexto_tela":
            self._definir_estado_ia("observing")
        else:
            self._definir_estado_ia("executing")

        # Se for uma ação que abre janela/processo e estivermos no loop de voz real, dá feedback curto antes de verificar
        if falar_feedback_imediato and acao in {"abrir_programa", "pesquisar_navegador", "abrir_pasta"}:
            self.sintetizador.falar("Abrindo.")
            self._definir_estado_ia("executing")

        executor = self._obter_executor()
        res = executor.executar(acao, params, auto_amarelo=True)
        self.ultima_execucao = res

        # Se a execução falhou ou não foi verificada, NUNCA confirma sucesso!
        if res.estado != EstadoExecucao.SUCCESS or not res.verificado:
            self._definir_estado_ia("error")
            if res.sugestao_recuperacao and res.alternativa_recuperacao:
                self._definir_confirmacao_pendente(
                    res.alternativa_recuperacao.get("acao"),
                    res.alternativa_recuperacao.get("parametros"),
                    validade_s=45.0,
                )
                return res.mensagem_humana
            return res.mensagem_humana

        # Execução verificada com sucesso! Formata a resposta de acordo com a ferramenta
        saida = res.resultado
        if acao in ("obter_status_pc", "obter_status_gpu") and isinstance(saida, dict):
            foco = intencao.get("foco_resposta", "geral")
            return formatar_resposta_telemetria(saida, foco=foco)

        if acao == "listar_programas_usuario" and isinstance(saida, list):
            principais = ", ".join(saida[:8]) if saida else "nenhum aplicativo principal"
            return f"Estão abertos: {principais}."

        return res.mensagem_humana

    def processar_fala_local_rapida(
        self,
        comando: str,
        *,
        falar_feedback_imediato: bool = False,
    ) -> str | None:
        """Resolve solicitações localmente e executa ferramentas com verificação real no Windows."""
        t0 = time.perf_counter()
        comando_limpo = comando.strip()

        # 0. Chamado de presença ("Gideon" ou "Gideon, você está aí?")
        if not comando_limpo or comando_limpo == "__PRESENCA__":
            self.ultima_origem_resposta = "cache_instantaneo"
            self.ultimo_nlu_ms = (time.perf_counter() - t0) * 1000.0
            self.ultimo_llm_ttft_ms = 0.0
            return "Estou aqui, Senhor Henry."

        saudacao_interface = identificar_saudacao(comando_limpo)
        if saudacao_interface:
            self._evento_interno({"tipo": "abrir_interface", "saudacao": saudacao_interface})
            self.ultima_origem_resposta = "comando_local"
            respostas = {
                "bom dia": "Bom dia, Senhor Henry. Estou aqui.",
                "boa tarde": "Boa tarde, Senhor Henry. Estou aqui.",
                "boa noite": "Boa noite, Senhor Henry. Estou aqui.",
            }
            return respostas[saudacao_interface]
        if eh_pedido_abrir_interface(comando_limpo):
            self._evento_interno({"tipo": "abrir_interface", "comando": comando_limpo})
            self.ultima_origem_resposta = "comando_local"
            self.ultimo_nlu_ms = (time.perf_counter() - t0) * 1000.0
            self.ultimo_llm_ttft_ms = 0.0
            return "Abrindo o aplicativo, Senhor Henry."



        # 1. Interrupção explícita ("Gideon, espera", "Para", "Silêncio")
        cmd_norm = normalizar(comando_limpo)
        if cmd_norm in {"parada de emergencia", "pare todas as acoes", "bloqueie as ferramentas"}:
            ativar_parada_emergencia()
            self._cancelar_confirmacao_pendente()
            self.sintetizador.interromper()
            self.ultima_origem_resposta = "comando_local"
            return "Parada de emergência ativada. Nenhuma nova ferramenta será executada."

        if cmd_norm in {"retomar execucao", "liberar as ferramentas", "desativar parada de emergencia"}:
            retomar_execucao()
            self.ultima_origem_resposta = "comando_local"
            return "Execução de ferramentas liberada novamente."

        if cmd_norm in {"espera", "espere", "para", "pare", "silencio", "calma", "aguarda", "pausa"} or (
            len(cmd_norm.split()) <= 2 and eh_interrupcao_barge_in(comando_limpo)
        ):
            cancelou_acao = self._cancelar_confirmacao_pendente()
            self.ultima_origem_resposta = "cache_instantaneo"
            self.ultimo_nlu_ms = (time.perf_counter() - t0) * 1000.0
            self.ultimo_llm_ttft_ms = 0.0
            return "Tudo bem, ação cancelada." if cancelou_acao else "Tudo bem."

        # 2. Mudança de modo de escuta por voz
        novo_modo = detectar_mudanca_modo_escuta(comando_limpo)
        if novo_modo:
            self.configurar(modo_escuta=novo_modo)
            nomes_amigaveis = {
                "ativacao_por_nome": "ativação por nome",
                "conversa_continua": "conversação contínua",
                "conversa_livre": "conversação livre",
            }
            self.ultima_origem_resposta = "comando_local"
            self.ultimo_nlu_ms = (time.perf_counter() - t0) * 1000.0
            self.ultimo_llm_ttft_ms = 0.0
            return f"Modo de {nomes_amigaveis.get(novo_modo, novo_modo)} ativado."

        # 3. Encerramento educado da sessão de conversa
        if eh_encerramento_conversa(comando_limpo):
            self._em_conversa_ativa = False
            if self.modo_escuta == ModoEscuta.CONVERSA_LIVRE:
                self.modo_escuta = ModoEscuta.ATIVACAO_POR_NOME
            self.ultima_origem_resposta = "cache_instantaneo"
            self.ultimo_nlu_ms = (time.perf_counter() - t0) * 1000.0
            self.ultimo_llm_ttft_ms = 0.0
            return "Tudo bem."

        # 4. Confirmações pendentes (Portão Vermelho ou Recuperação Automática de Falha)
        resposta_sistema = self._processar_comando_sistema(comando_limpo)
        if resposta_sistema:
            self._registrar_turno_sessao(comando_limpo, _limpar_tags_legadas(resposta_sistema))
            self.ultima_origem_resposta = "comando_local"
            self.ultimo_nlu_ms = (time.perf_counter() - t0) * 1000.0
            self.ultimo_llm_ttft_ms = 0.0
            return resposta_sistema

        # 5. Comandos diretos de memória permanente ("lembra que...", "o que você sabe sobre mim?")
        resp_memoria = self.memoria.processar_comando_explicito(comando_limpo)
        if resp_memoria:
            self.memoria.gravar_mensagem("voce", comando_limpo)
            self.memoria.gravar_mensagem("assistente", resp_memoria)
            self._registrar_turno_sessao(comando_limpo, _limpar_tags_legadas(resp_memoria))
            self.ultima_origem_resposta = "memoria_local"
            self.ultimo_nlu_ms = (time.perf_counter() - t0) * 1000.0
            self.ultimo_llm_ttft_ms = 0.0
            return resp_memoria

        # 6. Interpretador de Intenções Naturais e Planejador Multietapas
        intencao = interpretar_intencao_natural(comando_limpo, self.contexto_conversa)
        if intencao is not None:
            self.ultimo_nlu_ms = (time.perf_counter() - t0) * 1000.0
            if "novo_contexto" in intencao:
                self.contexto_conversa.update(intencao["novo_contexto"])

            if intencao.get("resposta_direta"):
                resp_dir = intencao["resposta_direta"]
                self._registrar_turno_sessao(comando_limpo, _limpar_tags_legadas(resp_dir))
                self.ultima_origem_resposta = "cache_instantaneo"
                self.ultimo_llm_ttft_ms = 0.0
                return resp_dir

            acao = intencao.get("acao", "")

            # Execução sequencial de plano com múltiplas etapas verificadas
            if acao == "plano_multietapas":
                etapas = intencao.get("etapas", [])
                if falar_feedback_imediato:
                    self.sintetizador.falar("Executando.")
                mensagens_etapas: list[str] = []
                for etapa in etapas:
                    msg_etapa = self._executar_intencao_verificada(etapa, falar_feedback_imediato=False)
                    mensagens_etapas.append(_limpar_tags_legadas(msg_etapa))
                    if self.ultima_execucao and (
                        self.ultima_execucao.estado != EstadoExecucao.SUCCESS
                        or not self.ultima_execucao.verificado
                    ):
                        break

                resp_plano = " ".join(mensagens_etapas)
                self.memoria.gravar_mensagem("voce", comando_limpo)
                self.memoria.gravar_mensagem("assistente", resp_plano)
                self._registrar_turno_sessao(comando_limpo, _limpar_tags_legadas(resp_plano))
                self.ultima_origem_resposta = "plano_multietapas"
                self.ultimo_llm_ttft_ms = 0.0
                return resp_plano

            if acao in self._catalogo._ferramentas:
                resp_tool = self._executar_intencao_verificada(
                    intencao,
                    falar_feedback_imediato=falar_feedback_imediato,
                )
                self.memoria.gravar_mensagem("voce", comando_limpo)
                self.memoria.gravar_mensagem("assistente", resp_tool)
                self._registrar_turno_sessao(comando_limpo, _limpar_tags_legadas(resp_tool))
                self.ultima_origem_resposta = "comando_local"
                self.ultimo_llm_ttft_ms = 0.0
                return resp_tool

        self.ultimo_nlu_ms = (time.perf_counter() - t0) * 1000.0
        return None

    def processar_fala_usuario(self, comando: str) -> str:
        """Processa a fala do usuário (local verificada ou via LLM) e retorna o texto completo."""
        local = self.processar_fala_local_rapida(comando, falar_feedback_imediato=False)
        if local is not None:
            return local

        comando_limpo = comando.strip()
        t_llm = time.perf_counter()
        lembrancas = self.memoria.recuperar_lembrancas_para_prompt(comando_limpo)
        if self.contexto_conversa:
            resumo_ctx = f"\n[Contexto ativo: {self.contexto_conversa}]"
            lembrancas = f"{lembrancas}{resumo_ctx}".strip()

        mensagens_ia = list(self.historico_sessao[-8:]) + [{"role": "user", "content": comando_limpo}]
        partes = []
        primeiro_token = True
        for ev in self.cerebro.pensar_stream(mensagens_ia, lembrancas=lembrancas):
            if ev["tipo"] == "chunk":
                if primeiro_token:
                    self.ultimo_llm_ttft_ms = (time.perf_counter() - t_llm) * 1000.0
                    primeiro_token = False
                partes.append(ev["texto"])
            elif ev["tipo"] == "erro":
                self._definir_estado_ia("error")
                return ev.get("mensagem", "Erro ao consultar o cérebro.")

        texto_resposta = _limpar_tags_legadas("".join(partes))
        if not texto_resposta:
            self._definir_estado_ia("error")
            return "Perdão, Senhor Henry. Não consegui responder agora."

        self.ultima_origem_resposta = "llm_stream"
        self.memoria.gravar_mensagem("voce", comando_limpo)
        self.memoria.gravar_mensagem("assistente", texto_resposta)
        self._registrar_turno_sessao(comando_limpo, texto_resposta)
        return texto_resposta

    def _responder_com_llm_streaming(self, comando_limpo: str) -> None:
        """Gera a resposta no LLM em streaming e envia sentença por sentença direto para o TTS."""
        t_llm = time.perf_counter()
        lembrancas = self.memoria.recuperar_lembrancas_para_prompt(comando_limpo)
        if self.contexto_conversa:
            resumo_ctx = f"\n[Contexto ativo: {self.contexto_conversa}]"
            lembrancas = f"{lembrancas}{resumo_ctx}".strip()

        mensagens_ia = list(self.historico_sessao[-8:]) + [{"role": "user", "content": comando_limpo}]
        texto_completo_acumulado: list[str] = []
        primeiro_chunk = True

        def _gerador_sentencas() -> Generator[str, None, None]:
            nonlocal primeiro_chunk
            buffer_atual = ""
            stream = self.cerebro.pensar_stream(mensagens_ia, lembrancas=lembrancas)
            try:
                for ev in stream:
                    if self._cancelar_geracao.is_set() or self.sintetizador.foi_interrompida:
                        break
                    if ev["tipo"] == "chunk":
                        pedaco = ev["texto"]
                        if primeiro_chunk:
                            self.ultimo_llm_ttft_ms = (time.perf_counter() - t_llm) * 1000.0
                            primeiro_chunk = False

                        texto_completo_acumulado.append(pedaco)
                        buffer_atual += pedaco
                        buffer_atual = _limpar_tags_legadas(buffer_atual)

                        while True:
                            if self._cancelar_geracao.is_set() or self.sintetizador.foi_interrompida:
                                break
                            m = re.search(r"^(.+?[.!?…])\s+(.*)$", buffer_atual, re.DOTALL)
                            if m:
                                sentenca_pronta = m.group(1).strip()
                                buffer_atual = m.group(2)
                            else:
                                break
                            if sentenca_pronta:
                                yield sentenca_pronta

                    elif ev["tipo"] == "erro":
                        self._definir_estado_ia("error")
                        yield ev.get("mensagem", "Ocorreu um problema na consulta.")
                        return
            finally:
                fechar = getattr(stream, "close", None)
                if callable(fechar):
                    fechar()

            restante = _limpar_tags_legadas(buffer_atual)
            if restante and not self._cancelar_geracao.is_set() and not self.sintetizador.foi_interrompida:
                if primeiro_chunk:
                    self.ultimo_llm_ttft_ms = (time.perf_counter() - t_llm) * 1000.0
                    primeiro_chunk = False
                yield restante

        self.ultima_origem_resposta = "llm_stream"
        self.sintetizador.falar_stream(_gerador_sentencas())

        resposta_final = _limpar_tags_legadas("".join(texto_completo_acumulado))
        if resposta_final and not self._cancelar_geracao.is_set():
            self.memoria.gravar_mensagem("voce", comando_limpo)
            self.memoria.gravar_mensagem("assistente", resposta_final)
            self._registrar_turno_sessao(comando_limpo, resposta_final)
            self._evento_interno({"tipo": "resposta_voz", "texto": resposta_final})

    def _loop_principal(self) -> None:
        """Loop contínuo de captura, detecção direcionada, execução verificada e streaming LLM->TTS."""
        while not self._parar_evento.is_set():
            try:
                agora = time.time()
                em_janela_continua = (
                    self.modo_escuta == ModoEscuta.CONVERSA_LIVRE
                    or (self._em_conversa_ativa and (agora - self._ultimo_contato) < self.duracao_sessao)
                )

                if not em_janela_continua and self._em_conversa_ativa:
                    self._em_conversa_ativa = False
                    self.contexto_conversa["aguardando_escolha_midia"] = False
                    self.contexto_conversa["aguardando_pesquisa_web"] = False

                if self.sintetizador.audio_barge_in is not None:
                    audio_inicial = self.sintetizador.audio_barge_in
                    self.sintetizador.audio_barge_in = None
                    audio_extra = self.ouvinte.gravar_fala(limite_silencio=0.55, timeout=1.0, parar_evento=self._parar_evento)
                    if audio_extra is not None:
                        audio = np.concatenate([audio_inicial, audio_extra], axis=0)
                    else:
                        audio = audio_inicial
                    em_janela_continua = True
                else:
                    audio = self.ouvinte.gravar_fala(timeout=4.0, parar_evento=self._parar_evento)

                if self._parar_evento.is_set():
                    break
                if audio is None:
                    continue

                texto = self.ouvinte.transcrever_audio(audio)
                if not texto or len(texto.strip()) < 2:
                    continue

                saudacao_interface = identificar_saudacao(texto)
                tem_wake, comando_extraido = self.ouvinte.extrair_wake_word(texto)

                if saudacao_interface:
                    comando = texto.strip()
                elif tem_wake:
                    self._evento_interno({"tipo": "som", "som": "ativacao"})
                    try:
                        tocar_som_ativacao()
                    except Exception:
                        pass
                    comando = comando_extraido
                elif em_janela_continua:
                    prob = avaliar_fala_direcionada(
                        texto,
                        self.contexto_conversa,
                        sessao_ativa=self._em_conversa_ativa,
                    )
                    if prob < 0.65:
                        continue
                    comando = texto.strip()
                else:
                    if (time.time() - self._ultimo_contato) < 45.0 and avaliar_fala_direcionada(texto, self.contexto_conversa, False) >= 0.88:
                        comando = texto.strip()
                    else:
                        continue

                print(f"\n  [Voz] Henry disse: '{comando if comando else texto}'")
                self._em_conversa_ativa = True
                self._ultimo_contato = time.time()
                self._evento_interno({"tipo": "transcricao_voz", "texto": comando or texto})

                self._definir_estado_ia("thinking")
                self._cancelar_geracao.clear()

                # 1. Tenta resolução rápida local e execução verificada no Windows
                resposta_local = self.processar_fala_local_rapida(
                    comando,
                    falar_feedback_imediato=True,
                )
                if resposta_local is not None:
                    texto_fala = _limpar_tags_legadas(resposta_local)
                    print(f"  [Voz] Gideon responde ({self.ultima_origem_resposta}): '{texto_fala}'")
                    self._evento_interno({"tipo": "resposta_voz", "texto": texto_fala})
                    self.sintetizador.falar(texto_fala)
                else:
                    # 2. Resolução via LLM com Streaming Sentença-por-Sentença para o TTS
                    self._responder_com_llm_streaming(comando)

                metricas_voz_global.registrar(
                    modo_escuta=self.modo_escuta.value,
                    origem_resposta=self.ultima_origem_resposta,
                    voz_id=self.sintetizador.voz_id,
                    vad_endpoint_ms=self.ouvinte.ultima_latencia_vad_ms,
                    stt_ms=self.ouvinte.ultima_latencia_stt_ms,
                    nlu_ms=self.ultimo_nlu_ms,
                    llm_ttft_ms=self.ultimo_llm_ttft_ms,
                    tts_ttfa_ms=self.sintetizador.ultima_latencia_ttfa_ms,
                )
                self._ultimo_contato = time.time()

            except Exception as e:
                print(f"  [Voz] Erro no laço de voz: {e}")
                self._definir_estado_ia("error")
                # Evita um loop de erro consumir um núcleo inteiro e disputar
                # tempo de CPU com captura e reprodução de áudio.
                self._parar_evento.wait(0.2)

    def _processar_comando_sistema(self, comando: str) -> str | None:
        """Confirma e executa comandos sensíveis ou alternativas de recuperação de falha."""
        with self._confirmacao_lock:
            return self._processar_comando_sistema_sem_lock(comando)

    def _processar_comando_sistema_sem_lock(self, comando: str) -> str | None:
        agora = time.time()
        if self._confirmacao_pendente and agora > self._confirmacao_expira_em:
            self._confirmacao_pendente = None
            self._parametros_pendentes = {}

        if self._confirmacao_pendente:
            confirmacao = resposta_confirmacao(comando)
            if confirmacao is None:
                # Se não for sim/não claro, expira a confirmação pendente e deixa o fluxo avaliar o novo comando
                self._confirmacao_pendente = None
                self._parametros_pendentes = {}
            else:
                ferramenta = self._confirmacao_pendente
                params = self._parametros_pendentes
                self._confirmacao_pendente = None
                self._parametros_pendentes = {}

                if not confirmacao:
                    return "Tudo bem, cancelado."

                executor = self._obter_executor()
                res = executor.executar(
                    ferramenta,
                    params,
                    confirmado_pelo_usuario=True,
                    auto_amarelo=True,
                )
                self.ultima_execucao = res
                if res.estado != EstadoExecucao.SUCCESS or not res.verificado:
                    return res.mensagem_humana
                return res.mensagem_humana

        ferramenta = detectar_comando_sistema(comando)
        if not ferramenta:
            return None

        self._confirmacao_pendente = ferramenta
        self._parametros_pendentes = {}
        self._confirmacao_expira_em = agora + 30.0
        if ferramenta == "atualizar_sistemas":
            return "Confirma a atualização dos meus sistemas pelo repositório privado?"
        if ferramenta == "reiniciar_gideon":
            return "Confirma o reinício da Gideon?"
        return "Confirma o encerramento completo da Gideon?"
