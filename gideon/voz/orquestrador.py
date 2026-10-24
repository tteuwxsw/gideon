"""Orquestrador de baixa latência e execução real verificada da Gideon."""

from __future__ import annotations

from enum import Enum
import re
import threading
import time
from typing import Callable, Any, Generator

import numpy as np

from gideon.cerebro import Cerebro
from gideon.executor import EstadoExecucao, ExecutorConfiavel, ResultadoExecucao
from gideon.memoria import Memoria
from gideon.presenca import MonitorPresencaDesktop
from gideon.protocolo import limpar_emocoes_texto, extrair_emocoes_texto
from gideon.tools import obter_catalogo_ferramentas
from gideon.voz.comandos import (
    avaliar_fala_direcionada,
    detectar_comando_sistema,
    detectar_mudanca_modo_escuta,
    eh_encerramento_conversa,
    eh_interrupcao_barge_in,
    formatar_resposta_telemetria,
    interpretar_intencao_natural,
    normalizar,
    resposta_confirmacao,
)
from gideon.voz.fala import SintetizadorVoz
from gideon.voz.metricas import metricas_voz_global
from gideon.voz.ouvido import OuvinteVoz


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
        self.sintetizador = SintetizadorVoz(callback_evento=self._evento_interno)
        self.monitor_presenca = MonitorPresencaDesktop(callback_evento=self._evento_interno)
        self.estado_comportamental_atual: str = "idle"

        self.ativo = False
        self.modo_escuta: ModoEscuta = ModoEscuta.ATIVACAO_POR_NOME
        self.duracao_sessao: float = 30.0  # Janela de conversação contínua

        self._thread_loop: threading.Thread | None = None
        self._parar_evento = threading.Event()
        self._em_conversa_ativa = False
        self._ultimo_contato = 0.0

        self._catalogo = obter_catalogo_ferramentas()
        self._executor = ExecutorConfiavel(self._catalogo)
        self.ultima_execucao: ResultadoExecucao | None = None

        self._confirmacao_pendente: str | None = None
        self._parametros_pendentes: dict[str, Any] = {}
        self._confirmacao_expira_em = 0.0

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
            self.sintetizador.barge_in_ativo = bool(barge_in_ativo)

        return self.obter_configuracao()

    def interromper_fala(self) -> bool:
        """Interrompe imediatamente a fala atual da Gideon."""
        return self.sintetizador.interromper()

    def _evento_interno(self, evento: dict) -> None:
        if getattr(self, "callback_ws", None):
            try:
                self.callback_ws(evento)
            except Exception:
                pass

    def _definir_estado_ia(self, estado: str) -> None:
        self.estado_comportamental_atual = estado
        self._evento_interno({"tipo": "estado_ia", "estado": estado})
        monitor = getattr(self, "monitor_presenca", None)
        if monitor is not None:
            monitor.definir_foco_conversa(estado in {"listening", "thinking", "speaking"})

    def iniciar(self) -> None:
        """Inicia a escuta e o sensor de presença de desktop em segundo plano."""
        if self.ativo:
            return
        self.ativo = True
        self._parar_evento.clear()
        if hasattr(self, "monitor_presenca") and self.monitor_presenca:
            self.monitor_presenca.iniciar()
        self._thread_loop = threading.Thread(target=self._loop_principal, daemon=True)
        self._thread_loop.start()
        print("  [Gideon Voz] Orquestrador de voz mãos-livres e consciência de desktop ATIVADOS.")

    def parar(self) -> None:
        """Encerra a escuta em segundo plano e interrompe qualquer fala ativa."""
        self.ativo = False
        self._parar_evento.set()
        self.sintetizador.interromper()
        if hasattr(self, "monitor_presenca") and self.monitor_presenca:
            self.monitor_presenca.parar()
        if self._thread_loop:
            self._thread_loop.join(timeout=1.0)
        print("  [Gideon Voz] Orquestrador de voz DESATIVADO.")

    def _registrar_turno_sessao(self, pergunta: str, resposta_limpa: str) -> None:
        """Mantém histórico curto enxuto (últimas 12 mensagens) para não inflar o prompt."""
        self.historico_sessao.append({"role": "user", "content": pergunta})
        self.historico_sessao.append({"role": "assistant", "content": resposta_limpa})
        if len(self.historico_sessao) > 12:
            self.historico_sessao = self.historico_sessao[-12:]

    def _emitir_emocoes_e_limpar(self, texto: str) -> str:
        emocoes = extrair_emocoes_texto(texto)
        for _, emo in emocoes:
            self._evento_interno({"tipo": "emocao", "nome": emo, "intensidade": 0.8})
        return limpar_emocoes_texto(texto)

    def _executar_intencao_verificada(
        self,
        intencao: dict[str, Any],
        *,
        falar_feedback_imediato: bool = False,
    ) -> str:
        """Executa uma única intenção pelo ExecutorConfiavel e retorna resposta humana baseada no resultado real."""
        acao = intencao.get("acao", "")
        params = intencao.get("parametros", {})

        if acao == "modo_avatar":
            modo_av = params.get("modo", "conversa")
            self._evento_interno({"tipo": "modo", "nome": modo_av})
            return "[EMOCAO:amigavel] Feito."

        if acao == "config_holograma":
            self._evento_interno({"tipo": "config_holograma", **params})
            return "[EMOCAO:amigavel] Ajustei a projeção holográfica."

        # Define estado comportamental antes de executar a ferramenta
        if acao == "inspecionar_contexto_tela":
            self._definir_estado_ia("observing")
        else:
            self._definir_estado_ia("executing")

        # Se for uma ação que abre janela/processo e estivermos no loop de voz real, dá feedback curto antes de verificar
        if falar_feedback_imediato and acao in {"abrir_programa", "pesquisar_navegador", "abrir_pasta"}:
            self._evento_interno({"tipo": "pensando", "ativo": False})
            self.sintetizador.falar("Abrindo.")
            self._definir_estado_ia("executing")

        executor = self._obter_executor()
        res = executor.executar(acao, params, auto_amarelo=True)
        self.ultima_execucao = res

        # Se a execução falhou ou não foi verificada, NUNCA confirma sucesso!
        if res.estado != EstadoExecucao.SUCCESS or not res.verificado:
            self._definir_estado_ia("error")
            if res.sugestao_recuperacao and res.alternativa_recuperacao:
                self._confirmacao_pendente = res.alternativa_recuperacao.get("acao")
                self._parametros_pendentes = dict(res.alternativa_recuperacao.get("parametros") or {})
                self._confirmacao_expira_em = time.time() + 45.0
                return f"[EMOCAO:curiosidade] {res.mensagem_humana}"
            return f"[EMOCAO:preocupacao] {res.mensagem_humana}"

        # Execução verificada com sucesso! Formata a resposta de acordo com a ferramenta
        saida = res.resultado
        if acao in ("obter_status_pc", "obter_status_gpu") and isinstance(saida, dict):
            foco = intencao.get("foco_resposta", "geral")
            return formatar_resposta_telemetria(saida, foco=foco)

        if acao == "listar_programas_usuario" and isinstance(saida, list):
            principais = ", ".join(saida[:8]) if saida else "nenhum aplicativo principal"
            return f"[EMOCAO:concentracao] Estão abertos: {principais}."

        return f"[EMOCAO:satisfacao] {res.mensagem_humana}"

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
            return "[EMOCAO:amigavel] Estou aqui, Henry."

        # 1. Interrupção explícita ("Gideon, espera", "Para", "Silêncio")
        cmd_norm = normalizar(comando_limpo)
        if cmd_norm in {"espera", "espere", "para", "pare", "silencio", "calma", "aguarda", "pausa"} or (
            len(cmd_norm.split()) <= 2 and eh_interrupcao_barge_in(comando_limpo)
        ):
            self.ultima_origem_resposta = "cache_instantaneo"
            self.ultimo_nlu_ms = (time.perf_counter() - t0) * 1000.0
            self.ultimo_llm_ttft_ms = 0.0
            return "[EMOCAO:neutra] Tudo bem."

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
            return f"[EMOCAO:amigavel] Modo de {nomes_amigaveis.get(novo_modo, novo_modo)} ativado."

        # 3. Encerramento educado da sessão de conversa
        if eh_encerramento_conversa(comando_limpo):
            self._em_conversa_ativa = False
            if self.modo_escuta == ModoEscuta.CONVERSA_LIVRE:
                self.modo_escuta = ModoEscuta.ATIVACAO_POR_NOME
            self._evento_interno({"tipo": "modo", "nome": "compacto"})
            self.ultima_origem_resposta = "cache_instantaneo"
            self.ultimo_nlu_ms = (time.perf_counter() - t0) * 1000.0
            self.ultimo_llm_ttft_ms = 0.0
            return "[EMOCAO:amigavel] Tudo bem."

        # 4. Confirmações pendentes (Portão Vermelho ou Recuperação Automática de Falha)
        resposta_sistema = self._processar_comando_sistema(comando_limpo)
        if resposta_sistema:
            self._registrar_turno_sessao(comando_limpo, limpar_emocoes_texto(resposta_sistema))
            self.ultima_origem_resposta = "comando_local"
            self.ultimo_nlu_ms = (time.perf_counter() - t0) * 1000.0
            self.ultimo_llm_ttft_ms = 0.0
            return resposta_sistema

        # 5. Comandos diretos de memória permanente ("lembra que...", "o que você sabe sobre mim?")
        resp_memoria = self.memoria.processar_comando_explicito(comando_limpo)
        if resp_memoria:
            self.memoria.gravar_mensagem("voce", comando_limpo)
            self.memoria.gravar_mensagem("assistente", resp_memoria)
            self._registrar_turno_sessao(comando_limpo, limpar_emocoes_texto(resp_memoria))
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
                self._registrar_turno_sessao(comando_limpo, limpar_emocoes_texto(resp_dir))
                self.ultima_origem_resposta = "cache_instantaneo"
                self.ultimo_llm_ttft_ms = 0.0
                return resp_dir

            acao = intencao.get("acao", "")

            # Execução sequencial de plano com múltiplas etapas verificadas
            if acao == "plano_multietapas":
                etapas = intencao.get("etapas", [])
                if falar_feedback_imediato:
                    self._evento_interno({"tipo": "pensando", "ativo": False})
                    self.sintetizador.falar("Executando.")
                mensagens_etapas: list[str] = []
                for etapa in etapas:
                    msg_etapa = self._executar_intencao_verificada(etapa, falar_feedback_imediato=False)
                    mensagens_etapas.append(limpar_emocoes_texto(msg_etapa))
                    if self.ultima_execucao and (
                        self.ultima_execucao.estado != EstadoExecucao.SUCCESS
                        or not self.ultima_execucao.verificado
                    ):
                        break

                resp_plano = "[EMOCAO:satisfacao] " + " ".join(mensagens_etapas)
                self.memoria.gravar_mensagem("voce", comando_limpo)
                self.memoria.gravar_mensagem("assistente", resp_plano)
                self._registrar_turno_sessao(comando_limpo, limpar_emocoes_texto(resp_plano))
                self.ultima_origem_resposta = "plano_multietapas"
                self.ultimo_llm_ttft_ms = 0.0
                return resp_plano

            if acao in {"modo_avatar", "config_holograma"} or acao in self._catalogo._ferramentas:
                resp_tool = self._executar_intencao_verificada(
                    intencao,
                    falar_feedback_imediato=falar_feedback_imediato,
                )
                self.memoria.gravar_mensagem("voce", comando_limpo)
                self.memoria.gravar_mensagem("assistente", resp_tool)
                self._registrar_turno_sessao(comando_limpo, limpar_emocoes_texto(resp_tool))
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
                return f"[EMOCAO:preocupacao] {ev.get('mensagem', 'Erro ao consultar o cérebro.')}"

        texto_resposta = "".join(partes).strip()
        if not texto_resposta:
            return "[EMOCAO:preocupacao] Perdão, Henry. Não consegui responder agora."

        self.ultima_origem_resposta = "llm_stream"
        self.memoria.gravar_mensagem("voce", comando_limpo)
        self.memoria.gravar_mensagem("assistente", texto_resposta)
        self._registrar_turno_sessao(comando_limpo, limpar_emocoes_texto(texto_resposta))
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
            for ev in self.cerebro.pensar_stream(mensagens_ia, lembrancas=lembrancas):
                if self.sintetizador.foi_interrompida:
                    break
                if ev["tipo"] == "chunk":
                    pedaco = ev["texto"]
                    if primeiro_chunk:
                        self.ultimo_llm_ttft_ms = (time.perf_counter() - t_llm) * 1000.0
                        self._evento_interno({"tipo": "pensando", "ativo": False})
                        primeiro_chunk = False

                    texto_completo_acumulado.append(pedaco)
                    buffer_atual += pedaco

                    for _, emo in extrair_emocoes_texto(buffer_atual):
                        self._evento_interno({"tipo": "emocao", "nome": emo, "intensidade": 0.8})
                    buffer_atual = limpar_emocoes_texto(buffer_atual)

                    while True:
                        m = re.search(r"^(.+?[.!?…])\s+(.*)$", buffer_atual, re.DOTALL)
                        if not m:
                            break
                        sentenca_pronta = m.group(1).strip()
                        buffer_atual = m.group(2)
                        if sentenca_pronta:
                            yield sentenca_pronta

                elif ev["tipo"] == "erro":
                    self._evento_interno({"tipo": "pensando", "ativo": False})
                    yield ev.get("mensagem", "Ocorreu um problema na consulta.")
                    return

            restante = limpar_emocoes_texto(buffer_atual).strip()
            if restante and not self.sintetizador.foi_interrompida:
                if primeiro_chunk:
                    self.ultimo_llm_ttft_ms = (time.perf_counter() - t_llm) * 1000.0
                    self._evento_interno({"tipo": "pensando", "ativo": False})
                    primeiro_chunk = False
                yield restante

        self.ultima_origem_resposta = "llm_stream"
        self.sintetizador.falar_stream(_gerador_sentencas())
        self._evento_interno({"tipo": "pensando", "ativo": False})

        resposta_final = "".join(texto_completo_acumulado).strip()
        if resposta_final:
            self.memoria.gravar_mensagem("voce", comando_limpo)
            self.memoria.gravar_mensagem("assistente", resposta_final)
            self._registrar_turno_sessao(comando_limpo, limpar_emocoes_texto(resposta_final))

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
                    self._evento_interno({"tipo": "modo", "nome": "compacto"})

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

                tem_wake, comando_extraido = self.ouvinte.extrair_wake_word(texto)

                if tem_wake:
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

                self._evento_interno({"tipo": "modo", "nome": "conversa"})
                self._evento_interno({"tipo": "pensando", "ativo": True})

                # 1. Tenta resolução rápida local e execução verificada no Windows
                resposta_local = self.processar_fala_local_rapida(
                    comando,
                    falar_feedback_imediato=True,
                )
                if resposta_local is not None:
                    self._evento_interno({"tipo": "pensando", "ativo": False})
                    texto_fala = self._emitir_emocoes_e_limpar(resposta_local)
                    print(f"  [Voz] Gideon responde ({self.ultima_origem_resposta}): '{texto_fala}'")
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
                time.sleep(0.3)

    def _processar_comando_sistema(self, comando: str) -> str | None:
        """Confirma e executa comandos sensíveis ou alternativas de recuperação de falha."""
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
                    return "[EMOCAO:neutra] Tudo bem, cancelado."

                executor = self._obter_executor()
                res = executor.executar(
                    ferramenta,
                    params,
                    confirmado_pelo_usuario=True,
                    auto_amarelo=True,
                )
                self.ultima_execucao = res
                if res.estado != EstadoExecucao.SUCCESS or not res.verificado:
                    return f"[EMOCAO:preocupacao] {res.mensagem_humana}"
                return f"[EMOCAO:satisfacao] {res.mensagem_humana}"

        ferramenta = detectar_comando_sistema(comando)
        if not ferramenta:
            return None

        self._confirmacao_pendente = ferramenta
        self._parametros_pendentes = {}
        self._confirmacao_expira_em = agora + 30.0
        if ferramenta == "atualizar_sistemas":
            return "[EMOCAO:concentracao] Confirma a atualização dos meus sistemas pelo repositório privado?"
        return "[EMOCAO:preocupacao] Confirma o encerramento completo da Gideon?"
