"""Orquestrador do ciclo completo de voz 100% mãos-livres da Gideon."""

import asyncio
import threading
import time
from typing import Callable, Any

from gideon.cerebro import Cerebro
from gideon.memoria import Memoria
from gideon.protocolo import limpar_emocoes_texto, extrair_emocoes_texto
from gideon.tools import obter_catalogo_ferramentas
from gideon.voz.comandos import detectar_comando_sistema, resposta_confirmacao
from gideon.voz.ouvido import OuvinteVoz
from gideon.voz.fala import SintetizadorVoz


class OrquestradorVoz:
    """Controla o laço de escuta contínua, ativação por wake word e resposta falada."""

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
        self._thread_loop: threading.Thread | None = None
        self._parar_evento = threading.Event()
        self._em_conversa_ativa = False
        self._ultimo_contato = 0.0
        self._catalogo = obter_catalogo_ferramentas()
        self._confirmacao_pendente: str | None = None
        self._confirmacao_expira_em = 0.0

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
        """Encerra a escuta em segundo plano."""
        self.ativo = False
        self._parar_evento.set()
        if self._thread_loop:
            self._thread_loop.join(timeout=1.0)
        print("  [Gideon Voz] Orquestrador de voz DESATIVADO.")

    def _loop_principal(self) -> None:
        """Loop contínuo de captura e resposta de voz."""
        while not self._parar_evento.is_set():
            try:
                # 1. Se estiver em conversa ativa recente (< 12 segundos), ouve direto
                agora = time.time()
                janela_followup = (agora - self._ultimo_contato) < 12.0 and self._em_conversa_ativa

                if not janela_followup and self._em_conversa_ativa:
                    # Timeout da conversa: recolhe a Gideon
                    self._em_conversa_ativa = False
                    self._evento_interno({"tipo": "modo", "nome": "compacto"})

                # 2. Ouve o microfone
                audio = self.ouvinte.gravar_fala(timeout=5.0, parar_evento=self._parar_evento)
                if self._parar_evento.is_set():
                    break
                if audio is None:
                    continue

                texto = self.ouvinte.transcrever_audio(audio)
                if not texto or len(texto.strip()) < 2:
                    continue

                # 3. Verifica Wake Word se não estiver em follow-up
                if not janela_followup:
                    tem_wake, comando = self.ouvinte.extrair_wake_word(texto)
                    if not tem_wake:
                        continue  # Não era com ela
                else:
                    comando = texto

                print(f"\n  [Voz] Henry disse: '{comando if comando else texto}'")
                self._em_conversa_ativa = True
                self._ultimo_contato = time.time()

                # 4. Materializa a Gideon na tela (se estiver oculta ou compacta)
                self._evento_interno({"tipo": "modo", "nome": "conversa"})

                if not comando:
                    # Henry apenas disse "Gideon"
                    self.sintetizador.falar("Sim, Henry?")
                    continue

                resposta_sistema = self._processar_comando_sistema(comando)
                if resposta_sistema:
                    self.sintetizador.falar(resposta_sistema)
                    self._ultimo_contato = time.time()
                    continue

                # 5. Processa o comando (Cérebro + Memória)
                self._evento_interno({"tipo": "pensando", "ativo": True})

                # Verifica comandos diretos de memória ("lembra que...", etc.)
                resp_memoria = self.memoria.processar_comando_explicito(comando)
                if resp_memoria:
                    self._evento_interno({"tipo": "pensando", "ativo": False})
                    # Extrai emoção e limpa texto
                    emocoes = extrair_emocoes_texto(resp_memoria)
                    for _, emo in emocoes:
                        self._evento_interno({"tipo": "emocao", "nome": emo, "intensidade": 0.8})

                    texto_limpo = limpar_emocoes_texto(resp_memoria)
                    self.sintetizador.falar(texto_limpo)
                    self._ultimo_contato = time.time()
                    continue

                # Pergunta ao Cérebro
                lembrancas = self.memoria.recuperar_lembrancas_para_prompt(comando)
                historico = [{"role": "user", "content": comando}]
                eventos_pensar = list(self.cerebro.pensar_stream(historico, lembrancas=lembrancas))

                self._evento_interno({"tipo": "pensando", "ativo": False})

                # Coleta resposta textual
                texto_resposta = "".join([e["texto"] for e in eventos_pensar if e["tipo"] == "chunk"])
                if not texto_resposta:
                    self.sintetizador.falar("Perdão, Henry. Não consegui formular uma resposta.")
                    continue

                # Registra na memória permanente
                self.memoria.gravar_mensagem("voce", comando)
                self.memoria.gravar_mensagem("assistente", texto_resposta)

                # Extrai emoções
                emocoes = extrair_emocoes_texto(texto_resposta)
                for _, emo in emocoes:
                    self._evento_interno({"tipo": "emocao", "nome": emo, "intensidade": 0.8})

                texto_fala = limpar_emocoes_texto(texto_resposta)
                print(f"  [Voz] Gideon responde: '{texto_fala}'")

                # 6. Fala a resposta com sincronia labial no avatar
                self.sintetizador.falar(texto_fala)
                self._ultimo_contato = time.time()

            except Exception as e:
                print(f"  [Voz] Erro no laço de voz: {e}")
                time.sleep(0.5)

    def _processar_comando_sistema(self, comando: str) -> str | None:
        """Confirma e executa somente comandos locais reconhecidos de forma exata."""
        agora = time.time()
        if self._confirmacao_pendente and agora > self._confirmacao_expira_em:
            self._confirmacao_pendente = None

        if self._confirmacao_pendente:
            confirmacao = resposta_confirmacao(comando)
            if confirmacao is None:
                return "Preciso que você diga sim para confirmar ou não para cancelar."

            ferramenta = self._confirmacao_pendente
            self._confirmacao_pendente = None
            if not confirmacao:
                return "Ação cancelada, Henry."

            resultado = self._catalogo.executar(
                ferramenta,
                {},
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
        self._confirmacao_expira_em = agora + 30.0
        if ferramenta == "atualizar_sistemas":
            return "Vou buscar e instalar código do seu repositório privado. Confirma a atualização?"
        return "Vou encerrar o cérebro, a voz e o holograma da Gideon. Confirma?"
