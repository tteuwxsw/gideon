"""Portão de Risco e Auditoria da Gideon (Apêndice B da especificação).

Classificação de ferramentas:
- VERDE (V): Apenas leitura do sistema (ver CPU, ler arquivos, listar apps). Executa e registra.
- AMARELO (A): Modificação reversível (abrir app, ajustar volume, mover para lixeira).
- VERMELHO (R): Ação destrutiva ou externa (apagar permanentemente, deploy, enviar mensagens). Exige confirmação expressa do Henry.
"""

import json
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

ROOT_DIR = Path(__file__).resolve().parent.parent
DADOS_DIR = ROOT_DIR / "dados"
LOG_AUDITORIA = DADOS_DIR / "auditoria.jsonl"
LIMITE_DIARIO_USD = 2.00

# Evento global de parada de emergência
PARADO = threading.Event()

# Controle de gasto diário
_gasto_hoje = {"dia": "", "usd": 0.0}
_lock_gasto = threading.Lock()


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


def registrar_auditoria(evento: dict[str, Any]) -> None:
    """Registra uma ação executada no arquivo de auditoria (apenas append)."""
    LOG_AUDITORIA.parent.mkdir(parents=True, exist_ok=True)
    evento["quando"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_AUDITORIA.open("a", encoding="utf-8") as f:
        f.write(json.dumps(evento, ensure_ascii=False) + "\n")


def somar_gasto(usd: float) -> None:
    """Acumula o gasto diário de API para controle do teto."""
    hoje = time.strftime("%Y-%m-%d")
    with _lock_gasto:
        if _gasto_hoje["dia"] != hoje:
            _gasto_hoje.update(dia=hoje, usd=0.0)
        _gasto_hoje["usd"] += usd


def gasto_diario_atual() -> float:
    hoje = time.strftime("%Y-%m-%d")
    with _lock_gasto:
        if _gasto_hoje["dia"] == hoje:
            return _gasto_hoje["usd"]
        return 0.0


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
        auto_amarelo: bool = True,
    ) -> dict[str, Any]:
        """Executa uma ferramenta passando pelo portão de risco e auditoria."""
        if PARADO.is_set():
            return {"ok": False, "motivo": "Sistema parado pelo comando de emergência."}

        if gasto_diario_atual() >= LIMITE_DIARIO_USD:
            return {"ok": False, "motivo": f"Teto diário de gasto atingido (${LIMITE_DIARIO_USD:.2f} USD)."}

        f = self.obter(nome)
        if not f:
            return {"ok": False, "motivo": f"Ferramenta '{nome}' não encontrada no catálogo."}

        try:
            texto_acao = f.frase(**args)
        except Exception as e:
            texto_acao = f"{f.nome} com argumentos {args}"

        # Avaliação de risco
        precisa_confirmar = f.risco is Risco.VERMELHO or (f.risco is Risco.AMARELO and not auto_amarelo)

        if precisa_confirmar:
            if not confirmar_fn or not confirmar_fn(texto_acao):
                registrar_auditoria({
                    "ferramenta": f.nome,
                    "risco": f.risco.value,
                    "acao": texto_acao,
                    "resultado": "recusado_pelo_usuario",
                })
                return {"ok": False, "motivo": f"Ação requer confirmação do Henry: '{texto_acao}'."}

        # Execução real
        try:
            saida = f.executar(**args)
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
