"""Coletor de métricas de latência e desempenho de voz da Gideon (p50, p95 e TTFA)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, asdict
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
import psutil

from gideon.caminhos import DADOS_DIR

ARQUIVO_METRICAS = DADOS_DIR / "metricas_voz.jsonl"


@dataclass
class RegistroLatenciaTurno:
    """Medições reais (em milissegundos) de cada etapa do pipeline de voz."""

    timestamp: str
    modo_escuta: str
    origem_resposta: str  # "comando_local", "memoria_local", "llm_stream", "cache_instantaneo"
    voz_id: str
    vad_endpoint_ms: float
    stt_ms: float
    nlu_ms: float
    llm_ttft_ms: float
    tts_ttfa_ms: float
    ttfa_total_ms: float  # Tempo total entre o fim da fala do usuário e o primeiro áudio da resposta
    cpu_percent: float
    ram_usada_gb: float


class ColetorMetricasVoz:
    """Calcula estatísticas p50 e p95 em tempo real do pipeline de voz."""

    def __init__(self, max_historico: int = 200):
        self._historico: deque[RegistroLatenciaTurno] = deque(maxlen=max_historico)
        self._interacoes_totais = 0
        self._vozes_utilizadas: set[str] = set()

    def registrar(
        self,
        *,
        modo_escuta: str,
        origem_resposta: str,
        voz_id: str,
        vad_endpoint_ms: float = 0.0,
        stt_ms: float = 0.0,
        nlu_ms: float = 0.0,
        llm_ttft_ms: float = 0.0,
        tts_ttfa_ms: float = 0.0,
        ttfa_total_ms: float | None = None,
    ) -> RegistroLatenciaTurno:
        if ttfa_total_ms is None:
            ttfa_total_ms = vad_endpoint_ms + stt_ms + nlu_ms + llm_ttft_ms + tts_ttfa_ms

        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=None)

        reg = RegistroLatenciaTurno(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            modo_escuta=modo_escuta,
            origem_resposta=origem_resposta,
            voz_id=voz_id,
            vad_endpoint_ms=round(vad_endpoint_ms, 1),
            stt_ms=round(stt_ms, 1),
            nlu_ms=round(nlu_ms, 1),
            llm_ttft_ms=round(llm_ttft_ms, 1),
            tts_ttfa_ms=round(tts_ttfa_ms, 1),
            ttfa_total_ms=round(ttfa_total_ms, 1),
            cpu_percent=round(cpu, 1),
            ram_usada_gb=round(mem.used / (1024 ** 3), 2),
        )

        self._historico.append(reg)
        self._interacoes_totais += 1
        self._vozes_utilizadas.add(voz_id)

        try:
            ARQUIVO_METRICAS.parent.mkdir(parents=True, exist_ok=True)
            with ARQUIVO_METRICAS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(reg), ensure_ascii=False) + "\n")
        except Exception:
            pass

        return reg

    def resumo_estatistico(self) -> dict[str, Any]:
        """Retorna p50, p95 e consistência vocal das interações registradas."""
        if not self._historico:
            return {
                "interacoes": 0,
                "consistencia_voz_100_porcento": True,
                "vozes_vistas": [],
                "p50_ms": {},
                "p95_ms": {},
            }

        campos = ("vad_endpoint_ms", "stt_ms", "nlu_ms", "llm_ttft_ms", "tts_ttfa_ms", "ttfa_total_ms")
        p50 = {}
        p95 = {}

        for campo in campos:
            valores = [getattr(r, campo) for r in self._historico]
            p50[campo] = round(float(np.percentile(valores, 50)), 1)
            p95[campo] = round(float(np.percentile(valores, 95)), 1)

        ultimo = self._historico[-1]
        return {
            "interacoes": self._interacoes_totais,
            "amostras_janela": len(self._historico),
            "voz_fixa_unica": len(self._vozes_utilizadas) == 1,
            "vozes_vistas": sorted(list(self._vozes_utilizadas)),
            "p50_ms": p50,
            "p95_ms": p95,
            "ultimo_turno": asdict(ultimo),
        }


metricas_voz_global = ColetorMetricasVoz()
