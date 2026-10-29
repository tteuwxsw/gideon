"""Módulo de síntese vocal (TTS) de baixa latência e identidade vocal única da Gideon.

Características principais:
1. Identidade Vocal Única e Imutável (PocketTTS local ou Francisca como recuperação):
   - Elimina alternância entre vozes ou mudanças de timbre multilíngues.
   - Prosódia natural brasileira com tratamento fonético de siglas, números e nomes.
2. Baixa Latência com Loop Assíncrono Persistente e Cache em RAM/Disco (`dados/cache_voz/`):
   - Respostas frequentes ("Abrindo.", "Tudo bem.", "Estou aqui, Henry.") têm latência < 5ms.
3. Síntese Incremental por Sentenças (`falar_stream`):
   - Começa a falar a primeira frase enquanto o LLM ainda gera o restante da resposta.
4. Barge-In Anti-Eco e Exclusão Mútua de Áudio:
   - Permite interromper imediatamente a fala sem sobreposição de vozes.
"""

from __future__ import annotations

import asyncio
from collections import deque
import hashlib
import io
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
from typing import Callable, Any, Iterable

import numpy as np

from gideon.caminhos import DADOS_DIR
from gideon.processos_windows import comando_powershell, opcoes_processo_oculto
from gideon.configuracao import obter_idioma, obter_voz_para_idioma
from gideon.voz.pockettts_local import criar_motor_local

CACHE_VOZ_DIR = DADOS_DIR / "cache_voz"

# IDENTIDADE VOCAL ÚNICA E FIXA DA GIDEON (Nunca alterna entre locutoras)
# Francisca tem um timbre mais maduro, sereno e próximo da presença da Gideon.
IDENTIFICADOR_VOZ_FIXA = "pt-BR-FranciscaNeural"
VELOCIDADE_VOZ_FIXA = "-4%"
TOM_VOZ_FIXO = "-3Hz"
PERFIL_VOZ_CACHE = "francisca-natural-v1"

# Frases curtas de uso frequente pré-aquecidas em cache para resposta instantânea (< 5ms)
FRASES_PRE_AQUECIMENTO = (
    "Abrindo.",
    "Executando.",
    "Tudo bem.",
    "Estou aqui, Senhor Henry.",
    "Pois não, Senhor Henry.",
    "Às suas ordens, Senhor Henry.",
    "Feito.",
    "Cancelado.",
    "Claro. O que gostaria de ouvir?",
    "O que está acontecendo?",
    "Quer que eu verifique o consumo de recursos?",
    "Pronto, Google Chrome aberto.",
    "Pronto, Bloco de Notas aberto.",
    "Abrindo o Chrome.",
    "Abrindo o Spotify.",
    "Pausado.",
)


def limpar_texto_para_fala(texto: str) -> str:
    """Remove marcações Markdown e tags internas mantendo pontuação prosódica."""
    texto = re.sub(r"\[EMOCAO:[^\]]+\]", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"```[\s\S]*?```", " código exibido na tela. ", texto)
    texto = re.sub(r"`([^`]+)`", r"\1", texto)
    texto = re.sub(r"\*\*([^*]+)\*\*", r"\1", texto)
    texto = re.sub(r"\*([^*]+)\*", r"\1", texto)
    texto = re.sub(r"^#+\s*", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def formatar_prosodia_gideon(texto: str) -> str:
    """Ajusta pronúncia fonética de nomes, siglas e números para português brasileiro natural."""
    t = limpar_texto_para_fala(texto)
    if not t:
        return ""

    # Adaptações fonéticas para manter timbre 100% brasileiro e natural na voz fixa
    substituicoes = [
        (r"\bGideon\b", "Guídeon"),
        (r"\bgideon\b", "Guídeon"),
        (r"(\d+)\s*GB\b", r"\1 gigabytes"),
        (r"(\d+)\s*MB\b", r"\1 megabytes"),
        (r"(\d+(?:[.,]\d+)?)\s*%", r"\1 por cento"),
        (r"\bVRAM\b", "memória de vídeo"),
        (r"\bRX\s*580X?\b", "R X 580"),
        (r"\bVS\s*Code\b", "V S Code"),
    ]
    for padrao, destino in substituicoes:
        t = re.sub(padrao, destino, t)

    t = re.sub(r"\s+", " ", t).strip()
    return t


def dividir_em_sentencas_fala(texto: str) -> list[str]:
    """Divide um texto longo em sentenças naturais para síntese incremental."""
    limpo = limpar_texto_para_fala(texto)
    if not limpo:
        return []
    partes = re.split(r"(?<=[.!?…])\s+", limpo)
    return [p.strip() for p in partes if p.strip()]


class SintetizadorVoz:
    """Motor de voz única da Gideon com cache persistente, streaming de sentenças e Barge-In."""

    def __init__(
        self,
        callback_evento: Callable[[dict], Any] | None = None,
        callback_barge_in: Callable[[np.ndarray], bool] | None = None,
        barge_in_ativo: bool = True,
        limiar_barge_in: float = 0.06,
        pre_aquecer: bool = True,
    ):
        self.callback_evento = callback_evento
        self.callback_barge_in = callback_barge_in
        self.idioma = obter_idioma()
        self._pockettts = criar_motor_local()
        self.voz_id = (
            "gideon-local-pockettts"
            if (self._pockettts and self.idioma == "pt-BR")
            else obter_voz_para_idioma(self.idioma)
        )
        self._identidade_cache = (
            self._pockettts.identidade_cache
            if (self._pockettts and self.idioma == "pt-BR")
            else self.voz_id
        )
        self.barge_in_ativo = barge_in_ativo
        self.limiar_barge_in = limiar_barge_in
        self.fator_rejeicao_eco = 2.0

        self._edge_disponivel = False
        self._motor_ativo = "neural_hd_fixo"
        self._lock_fala = threading.Lock()
        self._falando = False
        self._evento_interromper = threading.Event()
        self._processo_windows: subprocess.Popen | None = None

        self.rms_saida_atual: float = 0.0
        self.foi_interrompida: bool = False
        self._barge_in_confirmado: bool = False
        self.audio_barge_in: np.ndarray | None = None
        self.ultima_latencia_ttfa_ms: float = 0.0
        self.ultimo_foi_cache: bool = False

        # Cache em memória: hash -> (amostras_float32, taxa_amostragem)
        self._cache_memoria: dict[str, tuple[np.ndarray, int]] = {}
        CACHE_VOZ_DIR.mkdir(parents=True, exist_ok=True)

        # Loop assíncrono persistente em thread dedicada (evita criar loops a cada fala)
        self._loop_async = asyncio.new_event_loop()
        self._thread_async = threading.Thread(target=self._rodar_loop_persistente, daemon=True)
        self._thread_async.start()

        self._inicializar_motor_unico()
        if pre_aquecer and self._edge_disponivel and self._pockettts is None:
            threading.Thread(target=self._pre_aquecer_frases_comuns, daemon=True).start()

    def _rodar_loop_persistente(self) -> None:
        asyncio.set_event_loop(self._loop_async)
        self._loop_async.run_forever()

    def _inicializar_motor_unico(self) -> None:
        """Inicializa e trava exclusivamente a voz feminina oficial da Gideon."""
        try:
            import edge_tts  # noqa: F401
            import av  # noqa: F401
            self._edge_disponivel = True
        except Exception as e:
            print(f"  [Voz] Aviso: Edge TTS indisponivel ({e}).")

        if self._pockettts is not None:
            self._motor_ativo = "pockettts_local"
        elif self._edge_disponivel:
            self._motor_ativo = "neural_hd_fixo"
        else:
            self._motor_ativo = "windows_fallback"
        print(f"  [Voz] Identidade vocal fixa carregada: {self.voz_id} (Timbre Unico Consistente).")

    @property
    def falando(self) -> bool:
        return self._falando

    def _chave_cache(self, texto_prosodia: str) -> str:
        identidade = (
            f"{PERFIL_VOZ_CACHE}|{self._identidade_cache}|{VELOCIDADE_VOZ_FIXA}|"
            f"{TOM_VOZ_FIXO}|{texto_prosodia.strip().lower()}"
        )
        return hashlib.sha256(identidade.encode("utf-8")).hexdigest()[:24]

    def _obter_do_cache(self, chave: str) -> tuple[np.ndarray, int] | None:
        if chave in self._cache_memoria:
            return self._cache_memoria[chave]

        caminho_npy = CACHE_VOZ_DIR / f"{chave}_24000.npy"
        if caminho_npy.exists():
            try:
                audio = np.load(caminho_npy)
                self._cache_memoria[chave] = (audio, 24000)
                return audio, 24000
            except Exception:
                pass
        return None

    def _salvar_no_cache(self, chave: str, audio: np.ndarray, taxa: int) -> None:
        self._cache_memoria[chave] = (audio, taxa)
        if len(audio) <= taxa * 8:  # Salva em disco áudios de até 8 segundos
            caminho_npy = CACHE_VOZ_DIR / f"{chave}_{taxa}.npy"
            if not caminho_npy.exists():
                try:
                    np.save(caminho_npy, audio)
                except Exception:
                    pass

    def _pre_aquecer_frases_comuns(self) -> None:
        """Pré-carrega frases frequentes em segundo plano na inicialização."""
        for frase in FRASES_PRE_AQUECIMENTO:
            try:
                texto_p = formatar_prosodia_gideon(frase)
                chave = self._chave_cache(texto_p)
                if self._obter_do_cache(chave) is None:
                    amostras, taxa = self._gerar_audio_voz_fixa(texto_p)
                    self._salvar_no_cache(chave, amostras, taxa)
            except Exception:
                pass

    def interromper(self) -> bool:
        """Interrompe imediatamente qualquer síntese ou reprodução em andamento (Barge-In)."""
        estava_falando = self._falando
        self._evento_interromper.set()
        self.foi_interrompida = True

        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass

        if self._processo_windows and self._processo_windows.poll() is None:
            try:
                self._processo_windows.terminate()
            except Exception:
                pass

        return estava_falando

    def _notificar(self, evento: dict) -> None:
        if self.callback_evento:
            try:
                self.callback_evento(evento)
            except Exception:
                pass

    def sintetizar_para_memoria(self, texto: str) -> tuple[np.ndarray, int, bool]:
        """Sintetiza o texto usando exclusivamente a voz fixa da Gideon (retorna audio, taxa, veio_do_cache)."""
        texto_prosodia = formatar_prosodia_gideon(texto)
        if not texto_prosodia:
            return np.zeros(0, dtype=np.float32), 24000, True

        chave = self._chave_cache(texto_prosodia)
        em_cache = self._obter_do_cache(chave)
        if em_cache is not None:
            return em_cache[0], em_cache[1], True

        amostras, taxa = self._gerar_audio_voz_fixa(texto_prosodia)
        amostras = self._finalizar_audio_natural(amostras, taxa)
        
        # O motor local pode ter sido desativado durante a sintese; nesse caso,
        # guarda o audio de recuperacao apenas sob a identidade da Francisca.
        chave_final = self._chave_cache(texto_prosodia)
        self._salvar_no_cache(chave_final, amostras, taxa)
        return amostras, taxa, False

    @staticmethod
    def _finalizar_audio_natural(amostras: np.ndarray, taxa: int) -> np.ndarray:
        """Uniformiza volume sem pitch, eco ou filtros que metalizem a voz."""
        if len(amostras) == 0:
            return amostras.astype(np.float32, copy=False)
        audio = np.asarray(amostras, dtype=np.float32).copy()
        audio -= float(np.mean(audio))
        pico = float(np.max(np.abs(audio)))
        if pico > 1e-6:
            audio *= min(1.0, 0.92 / pico)
        fade = min(len(audio) // 2, max(1, int(taxa * 0.008)))
        if fade:
            curva = np.linspace(0.0, 1.0, fade, dtype=np.float32)
            audio[:fade] *= curva
            audio[-fade:] *= curva[::-1]
        return np.clip(audio, -1.0, 1.0)

    def falar(self, texto: str) -> bool:
        """Sintetiza e reproduz o texto com identidade vocal única, baixa latência e Barge-In."""
        texto_limpo = limpar_texto_para_fala(texto)
        if not texto_limpo:
            return True

        with self._lock_fala:
            self._evento_interromper.clear()
            self.foi_interrompida = False
            self._barge_in_confirmado = False
            self.audio_barge_in = None
            self._falando = True
            t_inicio_tts = time.perf_counter()
            self._notificar({"tipo": "estado_ia", "estado": "speaking"})
            self._notificar({"tipo": "fala_inicio", "texto": texto_limpo, "voz_id": self.voz_id})

            try:
                if self._pockettts is not None or self._edge_disponivel:
                    sentencas = dividir_em_sentencas_fala(texto_limpo)
                    if len(sentencas) <= 1:
                        amostras, taxa, do_cache = self.sintetizar_para_memoria(texto_limpo)
                        self.ultima_latencia_ttfa_ms = (time.perf_counter() - t_inicio_tts) * 1000.0
                        self.ultimo_foi_cache = do_cache
                        if len(amostras) > 0 and not self._evento_interromper.is_set():
                            self._reproduzir_audio(amostras, taxa)
                        return not self.foi_interrompida
                    else:
                        # Para múltiplas sentenças, sintetiza a 1ª imediatamente e faz pré-busca das seguintes
                        return self._falar_lista_sentencas_incremental(sentencas, t_inicio_tts)

                self._falar_windows_fallback(texto_limpo)
                return not self.foi_interrompida
            except Exception as e:
                if self._evento_interromper.is_set():
                    return False
                print(f"  [Voz] Erro na síntese neural ({self.voz_id}): {e}. Acionando recuperação offline.")
                self._falar_windows_fallback(texto_limpo)
                return not self.foi_interrompida
            finally:
                self._falando = False
                self.rms_saida_atual = 0.0
                self._notificar({"tipo": "fala_fim", "interrompida_por_voz": self._barge_in_confirmado})
                self._notificar({"tipo": "estado_ia", "estado": "listening" if self._barge_in_confirmado else "idle"})

    def falar_stream(self, iterador_sentencas: Iterable[str]) -> bool:
        """Recebe sentenças em streaming do LLM e inicia a fala na 1ª sentença sem esperar o fim."""
        with self._lock_fala:
            self._evento_interromper.clear()
            self.foi_interrompida = False
            self._barge_in_confirmado = False
            self.audio_barge_in = None
            self._falando = True
            t_inicio = time.perf_counter()
            primeiro_audio_emitido = False
            self._notificar({"tipo": "estado_ia", "estado": "speaking"})
            self._notificar({"tipo": "fala_inicio", "texto": "", "voz_id": self.voz_id})

            try:
                # O produtor continua recebendo o Gemini e sintetizando a próxima
                # frase enquanto a frase atual toca. Isso elimina os cortes entre
                # sentenças causados pela rede no caminho de reprodução.
                import concurrent.futures

                fila: queue.Queue[object] = queue.Queue(maxsize=3)
                fim = object()
                trabalhadores = 1 if self._pockettts else 2

                with concurrent.futures.ThreadPoolExecutor(max_workers=trabalhadores) as pool:
                    def produzir() -> None:
                        try:
                            for sentenca in iterador_sentencas:
                                if self._evento_interromper.is_set():
                                    break
                                s_limpa = limpar_texto_para_fala(sentenca)
                                if not s_limpa:
                                    continue
                                item = pool.submit(self.sintetizar_para_memoria, s_limpa)
                                while not self._evento_interromper.is_set():
                                    try:
                                        fila.put(item, timeout=0.1)
                                        break
                                    except queue.Full:
                                        continue
                        finally:
                            while True:
                                try:
                                    fila.put(fim, timeout=0.1)
                                    break
                                except queue.Full:
                                    if self._evento_interromper.is_set():
                                        break

                    produtor = threading.Thread(target=produzir, name="gideon-tts-producer", daemon=True)
                    produtor.start()

                    while not self._evento_interromper.is_set():
                        item = fila.get()
                        if item is fim:
                            break
                        amostras, taxa, do_cache = item.result(timeout=15.0)
                        if not primeiro_audio_emitido:
                            self.ultima_latencia_ttfa_ms = (time.perf_counter() - t_inicio) * 1000.0
                            self.ultimo_foi_cache = do_cache
                            primeiro_audio_emitido = True
                        if len(amostras) > 0:
                            self._reproduzir_audio(amostras, taxa)

                    # A reprodução já foi parada; aguarda o produtor sair para não
                    # deixar uma thread de geração órfã após a interrupção.
                    produtor.join()
                return not self.foi_interrompida
            finally:
                self._falando = False
                self.rms_saida_atual = 0.0
                self._notificar({"tipo": "fala_fim", "interrompida_por_voz": self._barge_in_confirmado})
                self._notificar({"tipo": "estado_ia", "estado": "listening" if self._barge_in_confirmado else "idle"})

    def _falar_lista_sentencas_incremental(self, sentencas: list[str], t_inicio_tts: float) -> bool:
        """Sintetiza a Sentença 1 imediatamente e pré-carrega a Sentença N+1 enquanto a N toca."""
        import concurrent.futures

        fila_audios: deque[tuple[str, concurrent.futures.Future]] = deque()
        trabalhadores = 1 if self._pockettts else 2
        with concurrent.futures.ThreadPoolExecutor(max_workers=trabalhadores) as pool:
            for s in sentencas:
                fila_audios.append((s, pool.submit(self.sintetizar_para_memoria, s)))

            primeira = True
            while fila_audios and not self._evento_interromper.is_set():
                s_txt, fut = fila_audios.popleft()
                timeout_s = self._pockettts.config.timeout_s + 5.0 if self._pockettts else 12.0
                amostras, taxa, do_cache = fut.result(timeout=timeout_s)
                if primeira:
                    self.ultima_latencia_ttfa_ms = (time.perf_counter() - t_inicio_tts) * 1000.0
                    self.ultimo_foi_cache = do_cache
                    primeira = False
                if len(amostras) > 0 and not self._evento_interromper.is_set():
                    self._reproduzir_audio(amostras, taxa)

        return not self.foi_interrompida

    def atualizar_idioma(self, novo_idioma: str) -> None:
        """Atualiza dinamicamente o idioma e a voz neural ativa do sintetizador."""
        self.idioma = novo_idioma
        if self.idioma == "pt-BR" and self._pockettts is not None:
            self.voz_id = "gideon-local-pockettts"
            self._identidade_cache = self._pockettts.identidade_cache
        else:
            self.voz_id = obter_voz_para_idioma(novo_idioma)
            self._identidade_cache = self.voz_id
        print(f"  [Voz] Idioma atualizado para {novo_idioma} (Voz: {self.voz_id}).")

    def _gerar_audio_voz_fixa(self, texto_prosodia: str) -> tuple[np.ndarray, int]:
        """Gera e decodifica o áudio neural usando a voz configurada no loop persistente."""
        if self._pockettts is not None and self.idioma == "pt-BR":
            try:
                return self._pockettts.sintetizar(texto_prosodia)
            except Exception as erro:
                print(f"  [Voz] PocketTTS indisponivel ({erro}); usando voz de nuvem.")
                self._pockettts.encerrar()
                self._pockettts = None
                self.voz_id = obter_voz_para_idioma(self.idioma)
                self._identidade_cache = self.voz_id
                self._motor_ativo = "neural_hd_fixo" if self._edge_disponivel else "windows_fallback"

        if not self._edge_disponivel:
            raise RuntimeError("PocketTTS e Edge TTS estao indisponiveis.")

        import av
        import edge_tts

        async def _baixar_stream() -> bytes:
            comunicador = edge_tts.Communicate(
                texto_prosodia,
                self.voz_id,
                rate=VELOCIDADE_VOZ_FIXA,
                pitch=TOM_VOZ_FIXO,
            )
            buffer = io.BytesIO()
            async for pacote in comunicador.stream():
                if self._evento_interromper.is_set():
                    break
                if pacote["type"] == "audio":
                    buffer.write(pacote["data"])
            return buffer.getvalue()

        futuro = asyncio.run_coroutine_threadsafe(_baixar_stream(), self._loop_async)
        dados_mp3 = futuro.result(timeout=12.0)

        if not dados_mp3:
            raise ValueError("Stream de áudio vazio")

        container = av.open(io.BytesIO(dados_mp3), format="mp3")
        quadros = [frame.to_ndarray() for frame in container.decode(audio=0)]
        if not quadros:
            raise ValueError("Nenhum quadro de áudio decodificado")

        taxa = container.streams.audio[0].rate
        audio = np.concatenate(quadros, axis=1).T.astype(np.float32)
        if audio.ndim > 1 and audio.shape[1] == 1:
            audio = audio[:, 0]
        return audio, taxa

    def _reproduzir_audio(self, amostras: np.ndarray, taxa: int) -> None:
        """Reproduz o áudio, publica seu nível normalizado e monitora Barge-In."""
        import sounddevice as sd

        parar_monitoramento = threading.Event()
        passo_segundos = 0.04  # 25 Hz mantém o orbe responsivo sem sobrecarregar o WebSocket.
        tamanho_janela = max(1, int(taxa * passo_segundos))
        total_amostras = len(amostras)
        duracao_total = total_amostras / float(taxa)
        pico_audio = max(float(np.max(np.abs(amostras))), 1e-9)

        def _loop_nivel_voz():
            inicio = time.perf_counter()
            while not parar_monitoramento.is_set() and not self._evento_interromper.is_set():
                decorrido = time.perf_counter() - inicio
                idx_atual = int(decorrido * taxa)
                if idx_atual >= total_amostras:
                    break

                fatia = amostras[idx_atual : min(total_amostras, idx_atual + tamanho_janela)]
                if len(fatia) > 0:
                    rms = float(np.sqrt(np.mean(np.square(fatia))))
                    self.rms_saida_atual = rms
                    nivel = max(0.0, min(1.0, rms / pico_audio))
                else:
                    self.rms_saida_atual = 0.0
                    nivel = 0.0

                self._notificar({"tipo": "voz_nivel", "nivel": nivel})
                time.sleep(passo_segundos)

        def _loop_barge_in():
            """Procura uma fala mais forte que o eco e só interrompe após confirmar a wake word."""
            if not self.barge_in_ativo or self.callback_barge_in is None or duracao_total < 0.75:
                return
            taxa_mic = 16000
            chunk_mic = int(taxa_mic * 0.06)
            quadros_acima = 0
            quadros_silencio = 0
            pre_buffer: deque[np.ndarray] = deque(maxlen=8)
            capturados: list[np.ndarray] = []

            try:
                pass  # TURBO: sleep removido
                with sd.InputStream(samplerate=taxa_mic, channels=1, dtype="float32") as mic:
                    while not parar_monitoramento.is_set() and not self._evento_interromper.is_set():
                        dados, _ = mic.read(chunk_mic)
                        bloco = dados - np.mean(dados)
                        rms_mic = float(np.sqrt(np.mean(bloco ** 2)))

                        # Durante a reprodução o limiar é deliberadamente mais alto. O áudio
                        # precisa superar tanto o piso fixo quanto o eco estimado da caixa.
                        limiar_eco = max(self.limiar_barge_in * 1.6, self.rms_saida_atual * 2.8)

                        if rms_mic > limiar_eco:
                            quadros_acima += 1
                            quadros_silencio = 0
                            capturados.append(bloco)
                        elif quadros_acima >= 3:
                            quadros_silencio += 1
                            capturados.append(bloco)
                        else:
                            quadros_acima = max(0, quadros_acima - 1)
                            capturados.clear()
                            pre_buffer.append(bloco)

                        duracao_capturada = len(capturados) * chunk_mic / taxa_mic
                        frase_pronta = quadros_silencio >= 5 or duracao_capturada >= 2.2
                        if frase_pronta and capturados:
                            audio_candidato = np.concatenate(list(pre_buffer) + capturados, axis=0).flatten()
                            confirmou = False
                            try:
                                confirmou = bool(self.callback_barge_in(audio_candidato))
                            except Exception:
                                confirmou = False
                            if confirmou:
                                self._barge_in_confirmado = True
                                self.audio_barge_in = None
                                self._notificar({"tipo": "barge_in_confirmado"})
                                self.interromper()
                                break
                            quadros_acima = 0
                            quadros_silencio = 0
                            capturados.clear()
                            pre_buffer.clear()
            except Exception:
                pass

        thread_nivel = threading.Thread(target=_loop_nivel_voz, daemon=True)
        thread_barge = threading.Thread(target=_loop_barge_in, daemon=True)
        thread_nivel.start()
        thread_barge.start()

        try:
            sd.play(amostras, taxa)
            inicio_play = time.perf_counter()
            while (time.perf_counter() - inicio_play) < duracao_total:
                if self._evento_interromper.is_set():
                    sd.stop()
                    break
                time.sleep(0.01)
        finally:
            parar_monitoramento.set()
            thread_nivel.join()
            thread_barge.join()
            self.rms_saida_atual = 0.0
            self._notificar({"tipo": "voz_nivel", "nivel": 0.0})

    def _falar_windows_fallback(self, texto: str) -> None:
        """Política explícita de recuperação offline via System.Speech."""
        duracao_estimada = max(1.0, len(texto) / 14.0)
        parar_nivel = threading.Event()

        def _publicar_nivel_estimado():
            inicio = time.time()
            while not parar_nivel.is_set() and not self._evento_interromper.is_set():
                if time.time() - inicio > duracao_estimada + 1.0:
                    break
                self._notificar({"tipo": "voz_nivel", "nivel": 0.45})
                time.sleep(0.04)

        thread_nivel = threading.Thread(target=_publicar_nivel_estimado, daemon=True)
        thread_nivel.start()

        try:
            texto_escapado = texto.replace("'", "''").replace('"', '`"')
            comando_ps = f"""
            Add-Type -AssemblyName System.Speech;
            $speak = New-Object System.Speech.Synthesis.SpeechSynthesizer;
            try {{
                $speak.SelectVoice('Microsoft Maria Desktop');
            }} catch {{}}
            $speak.Rate = 1;
            $speak.Speak('{texto_escapado}');
            """
            self._processo_windows = subprocess.Popen(
                [comando_powershell(), "-NoProfile", "-NonInteractive", "-Command", comando_ps],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **opcoes_processo_oculto(),
            )
            while self._processo_windows.poll() is None:
                if self._evento_interromper.is_set():
                    self._processo_windows.terminate()
                    break
                time.sleep(0.02)
        finally:
            self._processo_windows = None
            parar_nivel.set()
            thread_nivel.join(timeout=0.2)
            self._notificar({"tipo": "voz_nivel", "nivel": 0.0})
