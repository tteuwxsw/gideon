"""Portão de Risco e Auditoria da Gideon (Apêndice B da especificação).

Classificação de ferramentas:
- VERDE (V): Apenas leitura do sistema (ver CPU, ler arquivos, listar apps). Executa e registra.
- AMARELO (A): Modificação reversível (abrir app, ajustar volume, mover para lixeira).
- VERMELHO (R): Ação destrutiva ou externa (apagar permanentemente, deploy, enviar mensagens). Exige confirmação expressa do Henry.
"""

import json
import math
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from gideon.caminhos import DADOS_DIR

LOG_AUDITORIA = DADOS_DIR / "auditoria.jsonl"
ARQUIVO_GASTO = DADOS_DIR / "gasto_diario.json"
LIMITE_DIARIO_USD = 2.00

# Evento global de parada de emergência
PARADO = threading.Event()

# Controle de gasto diário
_gasto_hoje = {"dia": "", "usd": 0.0}
_lock_gasto = threading.Lock()


def _carregar_gasto_locked() -> None:
    hoje = time.strftime("%Y-%m-%d")
    if _gasto_hoje["dia"] == hoje:
        return

    gasto = 0.0
    try:
        dados = json.loads(ARQUIVO_GASTO.read_text(encoding="utf-8"))
        valor = float(dados.get("usd", 0.0))
        if dados.get("dia") == hoje and math.isfinite(valor) and valor >= 0:
            gasto = valor
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    _gasto_hoje.update(dia=hoje, usd=gasto)


def _persistir_gasto_locked() -> None:
    ARQUIVO_GASTO.parent.mkdir(parents=True, exist_ok=True)
    temporario = ARQUIVO_GASTO.with_suffix(".tmp")
    temporario.write_text(json.dumps(_gasto_hoje), encoding="utf-8")
    temporario.replace(ARQUIVO_GASTO)


class Risco(str, Enum):
    VERDE = "V"      # Só lê, não altera nada fora
    AMARELO = "A"    # Altera algo de forma reversível
    VERMELHO = "R"   # Destrutivo, envia dados para fora ou gasta recursos


@dataclass
class Ferramenta:
    nome: str
    descricao: str
    risco: Risco
    executar: Callable[..., Any]
    frase: Callable[..., str]
    parametros: dict[str, Any] = field(default_factory=dict)
    # Risco calculado pelos parametros reais (ex.: ligar automacao com acoes vermelhas).
    # Nunca pode rebaixar o risco declarado em `risco`.
    risco_dinamico: Callable[..., Risco] | None = None
    # Ferramentas que so podem ser acionadas por comando explicito (regex/voz), nunca pelo modelo.
    expor_ao_modelo: bool = True

    def risco_para(self, params: dict[str, Any] | None = None) -> Risco:
        """Retorna o risco efetivo para estes parametros (o maior entre o fixo e o dinamico)."""
        if self.risco_dinamico is None:
            return self.risco
        try:
            dinamico = self.risco_dinamico(**dict(params or {}))
        except Exception:
            return Risco.VERMELHO
        ordem = {Risco.VERDE: 0, Risco.AMARELO: 1, Risco.VERMELHO: 2}
        return dinamico if ordem.get(dinamico, 2) > ordem[self.risco] else self.risco


def registrar_auditoria(evento: dict[str, Any]) -> None:
    """Registra uma ação executada no arquivo de auditoria (apenas append)."""
    LOG_AUDITORIA.parent.mkdir(parents=True, exist_ok=True)
    evento["quando"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_AUDITORIA.open("a", encoding="utf-8") as f:
        f.write(json.dumps(evento, ensure_ascii=False) + "\n")


def somar_gasto(usd: float) -> None:
    """Acumula o gasto diário de API para controle do teto."""
    if not math.isfinite(usd) or usd < 0:
        raise ValueError("O custo deve ser um numero finito e nao negativo.")
    with _lock_gasto:
        _carregar_gasto_locked()
        _gasto_hoje["usd"] += usd
        _persistir_gasto_locked()


def gasto_diario_atual() -> float:
    with _lock_gasto:
        _carregar_gasto_locked()
        return _gasto_hoje["usd"]


def ativar_parada_emergencia() -> None:
    """Bloqueia novas execucoes de ferramentas imediatamente."""
    PARADO.set()


def retomar_execucao() -> None:
    """Libera novamente o executor apos uma parada explicita."""
    PARADO.clear()


def obter_historico_auditoria(limite: int = 10) -> list[dict[str, Any]]:
    """Lê os últimos registros de auditoria."""
    if not LOG_AUDITORIA.exists():
        return []
    linhas = LOG_AUDITORIA.read_text(encoding="utf-8").strip().splitlines()
    registros = []
    for l in linhas[-limite:]:
        try:
            registros.append(json.loads(l))
        except Exception:
            pass
    return registros


class RegistroFerramentas:
    """Catálogo central de ferramentas da Gideon com validação de segurança."""

    def __init__(self):
        self._ferramentas: dict[str, Ferramenta] = {}

    def registrar(self, f: Ferramenta) -> None:
        self._ferramentas[f.nome] = f

    def obter(self, nome: str) -> Ferramenta | None:
        return self._ferramentas.get(nome)

    def listar_todas(self) -> list[Ferramenta]:
        return list(self._ferramentas.values())

    def executar(
        self,
        nome: str,
        args: dict[str, Any],
        confirmar_fn: Callable[[str], bool] | None = None,
        auto_amarelo: bool = False,
    ) -> dict[str, Any]:
        """Executa uma ferramenta passando pelo portão de risco e auditoria."""
        if PARADO.is_set():
            return {"ok": False, "motivo": "Sistema parado pelo comando de emergência."}

        f = self.obter(nome)
        if not f:
            return {"ok": False, "motivo": f"Ferramenta '{nome}' não encontrada no catálogo."}

        try:
            texto_acao = f.frase(**args)
        except Exception as e:
            texto_acao = f"{f.nome} com argumentos {args}"

        # Avaliação de risco (considera o risco calculado pelos parâmetros reais)
        risco_efetivo = f.risco_para(args)
        precisa_confirmar = risco_efetivo is Risco.VERMELHO or (risco_efetivo is Risco.AMARELO and not auto_amarelo)

        if precisa_confirmar:
            if not confirmar_fn or not confirmar_fn(texto_acao):
                registrar_auditoria({
                    "ferramenta": f.nome,
                    "risco": f.risco.value,
                    "acao": texto_acao,
                    "resultado": "recusado_pelo_usuario",
                })
                return {"ok": False, "motivo": f"Ação requer confirmação do Henry: '{texto_acao}'."}

        # Execução real com verificação obrigatória do retorno estruturado
        try:
            if PARADO.is_set():
                raise RuntimeError("Sistema parado pelo comando de emergência.")
            saida = f.executar(**args)
            if isinstance(saida, dict) and (
                ("erro" in saida and saida["erro"])
                or saida.get("sucesso") is False
                or saida.get("verificado") is False
            ):
                motivo_erro = str(
                    saida.get("erro")
                    or saida.get("mensagem_humana")
                    or saida.get("mensagem")
                    or "Execução não verificada."
                )
                resultado = {"ok": False, "motivo": motivo_erro, "saida": saida}
            elif f.risco is not Risco.VERDE and (
                not isinstance(saida, dict)
                or saida.get("sucesso") is not True
                or saida.get("verificado") is not True
                or not saida.get("evidencias")
            ):
                resultado = {
                    "ok": False,
                    "motivo": "A ferramenta modificadora nao apresentou evidencia verificavel.",
                    "saida": saida,
                }
            elif isinstance(saida, str) and saida.lower().startswith(
                ("falha", "erro", "não foi possível", "nao foi possivel", "acesso negado")
            ):
                resultado = {"ok": False, "motivo": saida, "saida": saida}
            else:
                resultado = {"ok": True, "saida": saida}
        except Exception as e:
            resultado = {"ok": False, "motivo": f"{type(e).__name__}: {str(e)}"}

        registrar_auditoria({
            "ferramenta": f.nome,
            "risco": f.risco.value,
            "acao": texto_acao,
            "resultado": "ok" if resultado["ok"] else resultado["motivo"],
        })

        return resultado
