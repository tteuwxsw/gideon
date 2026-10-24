"""Orquestrador inteligente de voz da Gideon: Wake Word, 3 Modos de Escuta, Barge-In e Contexto."""

from __future__ import annotations

from enum import Enum
import threading
import time
from typing import Callable, Any

import numpy as np

from gideon.cerebro import Cerebro
from gideon.memoria import Memoria
from gideon.protocolo import limpar_emocoes_texto, extrair_emocoes_texto
from gideon.tools import obter_catalogo_ferramentas
from gideon.voz.comandos import (
    detectar_comando_sistema,
    detectar_mudanca_modo_escuta,
    eh_encerramento_conversa,
    eh_interrupcao_barge_in,
    formatar_resposta_telemetria,
    interpretar_intencao_natural,
    normalizar,
    resposta_confirmacao,
)
from gideon.voz.ouvido import OuvinteVoz
from gideon.voz.fala import SintetizadorVoz


class ModoEscuta(str, Enum):
    """Três modos configuráveis de escuta inteligente da Gideon."""

    ATIVACAO_POR_NOME = "ativacao_por_nome"   # Modo 1: Aguarda "Gideon" e abre sessão
    CONVERSA_CONTINUA = "conversa_continua"   # Modo 2: Mantém sessão ativa sem repetir o nome
    CONVERSA_LIVRE = "conversa_livre"         # Modo 3: Escuta livre sem exigir palavra de ativação


class OrquestradorVoz:
    """Controla o ciclo completo: Microfone -> VAD -> Wake Word -> IA/Contexto -> Ação -> TTS com Barge-In."""

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

        self.ativo = False
        self.modo_escuta: ModoEscuta = ModoEscuta.ATIVACAO_POR_NOME
        self.duracao_sessao: float = 25.0  # Segundos de janela de conversação contínua

        self._thread_loop: threading.Thread | None = None
        self._parar_evento = threading.Event()
        self._em_conversa_ativa = False
        self._ultimo_contato = 0.0

        self._catalogo = obter_catalogo_ferramentas()
        self._confirmacao_pendente: str | None = None
        self._parametros_pendentes: dict[str, Any] = {}
        self._confirmacao_expira_em = 0.0

        # Histórico contextual da sessão de voz (mantém as últimas trocas para referências como "E a placa de vídeo?")
        self.historico_sessao: list[dict[str, str]] = []
        self.contexto_conversa: dict[str, Any] = {}

    def obter_configuracao(self) -> dict[str, Any]:
        """Retorna o estado e as configurações atuais do subsistema de voz."""
        agora = time.time()
        sessao_ativa = self._em_conversa_ativa and (agora - self._ultimo_contato) < self.duracao_sessao
        return {
            "ativa": self.ativo,
            "modo_escuta": self.modo_escuta.value,
            "sessao_conversa_ativa": sessao_ativa or self.modo_escuta == ModoEscuta.CONVERSA_LIVRE,
            "duracao_sessao_segundos": self.duracao_sessao,
            "sensibilidade_microfone": self.ouvinte.sensibilidade,
            "barge_in_ativo": self.sintetizador.barge_in_ativo,
            "falando": self.sintetizador.falando,
            "contexto_atual": self.contexto_conversa.get("ultimo_topico", "geral"),
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
        """Repassa eventos do ouvido/fala para o avatar WebSocket."""
        if self.callback_ws:
            try:
                self.callback_ws(evento)
            except Exception:
                pass

    def iniciar(self) -> None:
        """Inicia a escuta em segundo plano."""
        if self.ativo:
            return
        self.ativo = True
        self._parar_evento.clear()
        self._thread_loop = threading.Thread(target=self._loop_principal, daemon=True)
        self._thread_loop.start()
        print("  [Gideon Voz] Orquestrador de voz mãos-livres ATIVADO.")

    def parar(self) -> None:
        """Encerra a escuta em segundo plano e interrompe qualquer fala ativa."""
        self.ativo = False
        self._parar_evento.set()
        self.sintetizador.interromper()
        if self._thread_loop:
            self._thread_loop.join(timeout=1.0)
        print("  [Gideon Voz] Orquestrador de voz DESATIVADO.")

    def _registrar_turno_sessao(self, pergunta: str, resposta_limpa: str) -> None:
        """Mantém histórico recente para referências contextuais ('E a placa de vídeo?', 'Me explica melhor')."""
        self.historico_sessao.append({"role": "user", "content": pergunta})
        self.historico_sessao.append({"role": "assistant", "content": resposta_limpa})
        if len(self.historico_sessao) > 16:
            self.historico_sessao = self.historico_sessao[-16:]

    def _emitir_emocoes_e_limpar(self, texto: str) -> str:
        emocoes = extrair_emocoes_texto(texto)
        for _, emo in emocoes:
            self._evento_interno({"tipo": "emocao", "nome": emo, "intensidade": 0.8})
        return limpar_emocoes_texto(texto)

    def processar_fala_usuario(self, comando: str) -> str:
        """Processa uma frase já ativada do usuário e retorna a resposta (com tags de emoção)."""
        comando_limpo = comando.strip()

        # 0. Chamado de presença ("Gideon" ou "Gideon, você está aí?")
        if not comando_limpo or comando_limpo == "__PRESENCA__":
            return "[EMOCAO:amigavel] Estou aqui, Henry. Como posso ajudar você?"

        # 1. Interrupção explícita ("Gideon, espera", "Para", "Silêncio")
        cmd_norm = normalizar(comando_limpo)
        if cmd_norm in {"espera", "espere", "para", "pare", "silencio", "calma", "aguarda", "pausa"}:
            return "[EMOCAO:neutra] Pois não, Henry. Estou ouvindo."

        # 2. Mudança de modo de escuta por voz
        novo_modo = detectar_mudanca_modo_escuta(comando_limpo)
        if novo_modo:
            self.configurar(modo_escuta=novo_modo)
            nomes_amigaveis = {
                "ativacao_por_nome": "ativação por nome",
                "conversa_continua": "conversação contínua",
                "conversa_livre": "conversação livre sem palavra de ativação",
            }
            return f"[EMOCAO:amigavel] Modo de {nomes_amigaveis.get(novo_modo, novo_modo)} ativado, Henry."

        # 3. Encerramento educado da sessão de conversa ("Obrigado, só isso", "Pode descansar")
        if eh_encerramento_conversa(comando_limpo):
            self._em_conversa_ativa = False
            if self.modo_escuta == ModoEscuta.CONVERSA_LIVRE:
                self.modo_escuta = ModoEscuta.ATIVACAO_POR_NOME
            self._evento_interno({"tipo": "modo", "nome": "compacto"})
            return "[EMOCAO:amigavel] Sempre às ordens, Henry. Estarei aqui se precisar."

        # 4. Confirmações pendentes ou comandos críticos de sistema (Portão Vermelho)
        resposta_sistema = self._processar_comando_sistema(comando_limpo)
        if resposta_sistema:
            self._registrar_turno_sessao(comando_limpo, limpar_emocoes_texto(resposta_sistema))
            return resposta_sistema

        # 5. Comandos diretos de memória permanente ("lembra que...", "o que você sabe sobre mim?")
        resp_memoria = self.memoria.processar_comando_explicito(comando_limpo)
        if resp_memoria:
            self.memoria.gravar_mensagem("voce", comando_limpo)
            self.memoria.gravar_mensagem("assistente", resp_memoria)
            self._registrar_turno_sessao(comando_limpo, limpar_emocoes_texto(resp_memoria))
            return resp_memoria

        # 6. Interpretador de Intenções Naturais (abrir apps/sites, colocar músicas, consultar RAM/GPU/CPU)
        intencao = interpretar_intencao_natural(comando_limpo, self.contexto_conversa)
        if intencao is not None:
            if "novo_contexto" in intencao:
                self.contexto_conversa.update(intencao["novo_contexto"])

            if intencao.get("resposta_direta"):
                resp_dir = intencao["resposta_direta"]
                self._registrar_turno_sessao(comando_limpo, limpar_emocoes_texto(resp_dir))
                return resp_dir

            acao = intencao.get("acao", "")
            params = intencao.get("parametros", {})

            if acao == "modo_avatar":
                modo_av = params.get("modo", "conversa")
                self._evento_interno({"tipo": "modo", "nome": modo_av})
                resp_modo = f"[EMOCAO:amigavel] Ajustando minha projeção para o modo {modo_av}, Henry."
                self._registrar_turno_sessao(comando_limpo, limpar_emocoes_texto(resp_modo))
                return resp_modo

            if acao in self._catalogo._ferramentas:
                resultado = self._catalogo.executar(acao, params, auto_amarelo=True)
                if resultado.get("ok"):
                    saida = resultado.get("saida")
                    if acao in ("obter_status_pc", "obter_status_gpu") and isinstance(saida, dict):
                        foco = intencao.get("foco_resposta", "geral")
                        resp_tool = formatar_resposta_telemetria(saida, foco=foco)
                    elif acao == "listar_programas_usuario" and isinstance(saida, list):
                        principais = ", ".join(saida[:10]) if saida else "nenhum aplicativo principal"
                        resp_tool = f"[EMOCAO:concentracao] No momento, os principais programas abertos são: {principais}."
                    elif acao == "abrir_programa":
                        nome_app = params.get("nome", "solicitado")
                        resp_tool = f"[EMOCAO:amigavel] Abrindo {nome_app}, Henry."
                    elif acao == "tocar_ou_pesquisar_midia":
                        consulta = params.get("consulta", "")
                        plat = params.get("plataforma", "Spotify").capitalize()
                        resp_tool = f"[EMOCAO:amigavel] Colocando {consulta} no {plat} para você, Henry."
                    else:
                        resp_tool = f"[EMOCAO:amigavel] {saida}"

                    self.memoria.gravar_mensagem("voce", comando_limpo)
                    self.memoria.gravar_mensagem("assistente", resp_tool)
                    self._registrar_turno_sessao(comando_limpo, limpar_emocoes_texto(resp_tool))
                    return resp_tool

        # 7. Consulta contextual ao Cérebro (Gemini) com histórico completo da sessão
        lembrancas = self.memoria.recuperar_lembrancas_para_prompt(comando_limpo)
        if self.contexto_conversa:
            resumo_ctx = f"\n[Contexto recente da sessão: {self.contexto_conversa}]"
            lembrancas = f"{lembrancas}{resumo_ctx}".strip()

        mensagens_ia = list(self.historico_sessao[-10:]) + [{"role": "user", "content": comando_limpo}]
        eventos_pensar = list(self.cerebro.pensar_stream(mensagens_ia, lembrancas=lembrancas))

        texto_resposta = "".join([e["texto"] for e in eventos_pensar if e["tipo"] == "chunk"]).strip()
        if not texto_resposta:
            erros = [e.get("mensagem", "") for e in eventos_pensar if e.get("tipo") == "erro"]
            if erros:
                return f"[EMOCAO:preocupacao] {erros[0]}"
            return "[EMOCAO:preocupacao] Perdão, Henry. Não consegui formular uma resposta agora."

        self.memoria.gravar_mensagem("voce", comando_limpo)
        self.memoria.gravar_mensagem("assistente", texto_resposta)
        self._registrar_turno_sessao(comando_limpo, limpar_emocoes_texto(texto_resposta))
        return texto_resposta

    def _loop_principal(self) -> None:
        """Loop contínuo de captura, detecção de modo, barge-in e resposta falada."""
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
                    self._evento_interno({"tipo": "modo", "nome": "compacto"})

                # Se houve barge-in no ciclo anterior, aproveita o áudio já capturado e complementa se necessário
                if self.sintetizador.audio_barge_in is not None:
                    audio_inicial = self.sintetizador.audio_barge_in
                    self.sintetizador.audio_barge_in = None
                    audio_extra = self.ouvinte.gravar_fala(limite_silencio=0.9, timeout=1.5, parar_evento=self._parar_evento)
                    if audio_extra is not None:
                        audio = np.concatenate([audio_inicial, audio_extra], axis=0)
                    else:
                        audio = audio_inicial
                    em_janela_continua = True
                else:
                    audio = self.ouvinte.gravar_fala(timeout=4.5, parar_evento=self._parar_evento)

                if self._parar_evento.is_set():
                    break
                if audio is None:
                    continue

                texto = self.ouvinte.transcrever_audio(audio)
                if not texto or len(texto.strip()) < 2:
                    continue

                # Verifica se o usuário chamou "Gideon" ou se já está em Conversação Contínua / Livre
                tem_wake, comando_extraido = self.ouvinte.extrair_wake_word(texto)

                if tem_wake:
                    comando = comando_extraido
                elif em_janela_continua:
                    # No modo livre, filtra ruídos soltos de 1 palavra que não sejam confirmações ou comandos conhecidos
                    if self.modo_escuta == ModoEscuta.CONVERSA_LIVRE and not self._em_conversa_ativa:
                        palavras = normalizar(texto).split()
                        if len(palavras) < 2 and resposta_confirmacao(texto) is None and not eh_interrupcao_barge_in(texto):
                            continue
                    comando = texto.strip()
                else:
                    continue  # Não era com a Gideon

                print(f"\n  [Voz] Henry disse: '{comando if comando else texto}'")
                self._em_conversa_ativa = True
                self._ultimo_contato = time.time()

                # Materializa a Gideon em modo conversa
                self._evento_interno({"tipo": "modo", "nome": "conversa"})
                self._evento_interno({"tipo": "pensando", "ativo": True})

                resposta_completa = self.processar_fala_usuario(comando)
                self._evento_interno({"tipo": "pensando", "ativo": False})

                texto_fala = self._emitir_emocoes_e_limpar(resposta_completa)
                print(f"  [Voz] Gideon responde: '{texto_fala}'")

                self.sintetizador.falar(texto_fala)
                self._ultimo_contato = time.time()

            except Exception as e:
                print(f"  [Voz] Erro no laço de voz: {e}")
                time.sleep(0.4)

    def _processar_comando_sistema(self, comando: str) -> str | None:
        """Confirma e executa comandos sensíveis protegidos pelo Portão Vermelho."""
        agora = time.time()
        if self._confirmacao_pendente and agora > self._confirmacao_expira_em:
            self._confirmacao_pendente = None
            self._parametros_pendentes = {}

        if self._confirmacao_pendente:
            confirmacao = resposta_confirmacao(comando)
            if confirmacao is None:
                return "[EMOCAO:duvida] Preciso que você diga sim para confirmar ou não para cancelar, Henry."

            ferramenta = self._confirmacao_pendente
            params = self._parametros_pendentes
            self._confirmacao_pendente = None
            self._parametros_pendentes = {}

            if not confirmacao:
                return "[EMOCAO:neutra] Ação cancelada, Henry."

            resultado = self._catalogo.executar(
                ferramenta,
                params,
                confirmar_fn=lambda _acao: True,
                auto_amarelo=False,
            )
            if not resultado.get("ok"):
                return str(resultado.get("motivo", "Não foi possível executar a ação."))
            saida = resultado.get("saida")
            if isinstance(saida, dict):
                return str(saida.get("mensagem") or saida.get("erro") or "Ação concluída.")
            return str(saida)

        ferramenta = detectar_comando_sistema(comando)
        if not ferramenta:
            return None

        self._confirmacao_pendente = ferramenta
        self._parametros_pendentes = {}
        self._confirmacao_expira_em = agora + 30.0
        if ferramenta == "atualizar_sistemas":
            return "[EMOCAO:concentracao] Vou buscar e instalar código do seu repositório privado. Confirma a atualização?"
        return "[EMOCAO:preocupacao] Vou encerrar o cérebro, a voz e o holograma da Gideon. Confirma?"
