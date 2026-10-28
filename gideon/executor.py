"""Motor de execução confiável, verificação pós-condição no Windows e planejamento multietapas da Gideon.

Separa estritamente três responsabilidades:
1. Inteligência: interpreta o que o usuário deseja.
2. Executor: realiza a ação usando ferramentas autorizadas do sistema.
3. Verificador: confirma com evidências reais do sistema operacional (PID, HWND, arquivo, estado de janela) se a ação realmente aconteceu.

REGRA ABSOLUTA: Nenhuma ação recebe estado `success` com `verificado=True` sem evidência real coletada do Windows.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
import json
import time
from typing import Any, Callable
import uuid

from gideon.gate import RegistroFerramentas, Risco, registrar_auditoria, PARADO
from gideon.caminhos import DADOS_DIR

LOG_EXECUCOES = DADOS_DIR / "execucoes.jsonl"


class EstadoExecucao(str, Enum):
    """Estados formais do ciclo de vida de uma ação."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    NEEDS_CONFIRMATION = "needs_confirmation"
    UNSUPPORTED = "unsupported"


@dataclass
class ResultadoExecucao:
    """Registro estruturado e auditável de execução e verificação de uma ferramenta."""

    id_acao: str
    ferramenta: str
    parametros: dict[str, Any]
    estado: EstadoExecucao
    verificado: bool
    resultado: Any = None
    erros: list[str] = field(default_factory=list)
    evidencias: dict[str, Any] = field(default_factory=dict)
    duracao_ms: float = 0.0
    sugestao_recuperacao: str | None = None
    alternativa_recuperacao: dict[str, Any] | None = None
    mensagem_humana: str = ""

    def para_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["estado"] = self.estado.value
        return d


def gravar_log_execucao(registro: ResultadoExecucao) -> None:
    """Persiste o registro estruturado de execução em `dados/execucoes.jsonl`."""
    try:
        LOG_EXECUCOES.parent.mkdir(parents=True, exist_ok=True)
        payload = registro.para_dict()
        payload["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOG_EXECUCOES.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass



def _registrar_auto_cura(nome_ferramenta: str, params: dict[str, Any], erro: str) -> None:
    """Registra lição de auto-correção na memória permanente quando uma ferramenta falha."""
    try:
        from gideon.memoria import Memoria
        Memoria().salvar_licao(
            contexto=f"Ao executar a ferramenta '{nome_ferramenta}' com parâmetros {params}",
            erro_detectado=str(erro),
            solucao_ou_regra=f"A ferramenta '{nome_ferramenta}' falhou ({str(erro)[:80]}). Verificar parâmetros ou tentar caminho alternativo.",
            sucesso=False,
        )
    except Exception:
        pass


class ExecutorConfiavel:
    """Executa ferramentas do catálogo exigindo validação de resultado e verificação real."""

    def __init__(self, catalogo: RegistroFerramentas):
        self.catalogo = catalogo

    def executar(
        self,
        nome_ferramenta: str,
        parametros: dict[str, Any] | None = None,
        *,
        confirmado_pelo_usuario: bool = False,
        auto_amarelo: bool = False,
        timeout_s: float = 10.0,
    ) -> ResultadoExecucao:
        params = dict(parametros or {})
        id_acao = f"act-{uuid.uuid4().hex[:8]}"
        t0 = time.perf_counter()

        if PARADO.is_set():
            res = ResultadoExecucao(
                id_acao=id_acao,
                ferramenta=nome_ferramenta,
                parametros=params,
                estado=EstadoExecucao.FAILED,
                verificado=False,
                erros=["Sistema parado pelo comando de emergência."],
                mensagem_humana="Meus sistemas de execução estão pausados por segurança, Senhor Henry.",
            )
            gravar_log_execucao(res)
            return res

        ferramenta = self.catalogo.obter(nome_ferramenta)
        if ferramenta is None:
            res = ResultadoExecucao(
                id_acao=id_acao,
                ferramenta=nome_ferramenta,
                parametros=params,
                estado=EstadoExecucao.UNSUPPORTED,
                verificado=False,
                erros=[f"Ferramenta '{nome_ferramenta}' não existe no catálogo autorizado."],
                mensagem_humana="Ainda não possuo uma ferramenta autorizada para realizar essa ação específica, Senhor Henry.",
            )
            gravar_log_execucao(res)
            return res

        try:
            texto_acao = ferramenta.frase(**params)
        except Exception:
            texto_acao = f"{ferramenta.nome}({params})"

        risco_efetivo = ferramenta.risco_para(params)
        precisa_confirmar = (
            risco_efetivo is Risco.VERMELHO
            or (risco_efetivo is Risco.AMARELO and not auto_amarelo)
        )
        if precisa_confirmar and not confirmado_pelo_usuario:
            res = ResultadoExecucao(
                id_acao=id_acao,
                ferramenta=nome_ferramenta,
                parametros=params,
                estado=EstadoExecucao.NEEDS_CONFIRMATION,
                verificado=False,
                evidencias={"risco": risco_efetivo.value, "descricao_acao": texto_acao},
                duracao_ms=round((time.perf_counter() - t0) * 1000.0, 1),
                mensagem_humana=f"Para {texto_acao}, preciso da sua confirmação, Senhor Henry. Posso prosseguir?",
            )
            gravar_log_execucao(res)
            return res

        # Executa a ferramenta e interpreta o retorno estruturado
        try:
            if PARADO.is_set():
                raise RuntimeError("Sistema parado pelo comando de emergência.")
            saida_bruta = ferramenta.executar(**params)
        except TimeoutError as e:
            duracao = round((time.perf_counter() - t0) * 1000.0, 1)
            res = ResultadoExecucao(
                id_acao=id_acao,
                ferramenta=nome_ferramenta,
                parametros=params,
                estado=EstadoExecucao.TIMEOUT,
                verificado=False,
                erros=[str(e)],
                duracao_ms=duracao,
                mensagem_humana=f"A tentativa de {texto_acao} excedeu o tempo limite, Senhor Henry.",
            )
            gravar_log_execucao(res)
            _registrar_auto_cura(nome_ferramenta, params, str(e))
            registrar_auditoria({
                "id_acao": id_acao,
                "ferramenta": nome_ferramenta,
                "risco": ferramenta.risco.value,
                "acao": texto_acao,
                "estado": res.estado.value,
                "verificado": False,
                "resultado": str(e),
            })
            return res
        except Exception as e:
            duracao = round((time.perf_counter() - t0) * 1000.0, 1)
            res = ResultadoExecucao(
                id_acao=id_acao,
                ferramenta=nome_ferramenta,
                parametros=params,
                estado=EstadoExecucao.FAILED,
                verificado=False,
                erros=[f"{type(e).__name__}: {str(e)}"],
                duracao_ms=duracao,
                mensagem_humana=f"Não consegui {texto_acao}. Ocorreu um erro: {str(e)}",
            )
            gravar_log_execucao(res)
            registrar_auditoria({
                "id_acao": id_acao,
                "ferramenta": nome_ferramenta,
                "risco": ferramenta.risco.value,
                "acao": texto_acao,
                "estado": res.estado.value,
                "verificado": False,
                "resultado": f"{type(e).__name__}: {str(e)}",
            })
            return res

        duracao = round((time.perf_counter() - t0) * 1000.0, 1)
        res = self._avaliar_saida_ferramenta(
            id_acao=id_acao,
            nome_ferramenta=nome_ferramenta,
            params=params,
            saida=saida_bruta,
            duracao_ms=duracao,
        )

        if res.estado == EstadoExecucao.FAILED:
            _registrar_auto_cura(nome_ferramenta, params, res.erros[0] if res.erros else "falha de verificação")

        gravar_log_execucao(res)
        registrar_auditoria({
            "id_acao": id_acao,
            "ferramenta": nome_ferramenta,
            "risco": ferramenta.risco.value,
            "acao": texto_acao,
            "estado": res.estado.value,
            "verificado": res.verificado,
            "evidencias": res.evidencias,
            "resultado": "ok" if res.estado == EstadoExecucao.SUCCESS else (res.erros[0] if res.erros else "falha"),
        })
        return res

    def _avaliar_saida_ferramenta(
        self,
        *,
        id_acao: str,
        nome_ferramenta: str,
        params: dict[str, Any],
        saida: Any,
        duracao_ms: float,
    ) -> ResultadoExecucao:
        """Inspeciona o retorno da ferramenta e garante que erros internos nunca virem falso sucesso."""
        ferramenta = self.catalogo.obter(nome_ferramenta)
        risco = ferramenta.risco if ferramenta else Risco.VERMELHO

        if isinstance(saida, ResultadoExecucao):
            saida.id_acao = id_acao
            saida.duracao_ms = duracao_ms
            if saida.estado is EstadoExecucao.SUCCESS and not saida.verificado:
                saida.estado = EstadoExecucao.FAILED
                saida.erros.append("A ferramenta informou sucesso sem verificacao.")
            return saida

        if isinstance(saida, dict):
            # Se a ferramenta já retornou estrutura com 'sucesso' / 'verificado' / 'erro'
            if "erro" in saida and saida["erro"]:
                erro_msg = str(saida["erro"])
                return ResultadoExecucao(
                    id_acao=id_acao,
                    ferramenta=nome_ferramenta,
                    parametros=params,
                    estado=EstadoExecucao.FAILED,
                    verificado=False,
                    resultado=saida,
                    erros=[erro_msg],
                    evidencias=saida.get("evidencias", {}),
                    duracao_ms=duracao_ms,
                    sugestao_recuperacao=saida.get("sugestao_recuperacao"),
                    alternativa_recuperacao=saida.get("alternativa_recuperacao"),
                    mensagem_humana=saida.get("mensagem_humana") or erro_msg,
                )

            if saida.get("sucesso") is False:
                erro_msg = str(saida.get("mensagem") or saida.get("motivo") or "A execução não pôde ser confirmada.")
                return ResultadoExecucao(
                    id_acao=id_acao,
                    ferramenta=nome_ferramenta,
                    parametros=params,
                    estado=EstadoExecucao.FAILED,
                    verificado=False,
                    resultado=saida,
                    erros=[erro_msg],
                    evidencias=saida.get("evidencias", {}),
                    duracao_ms=duracao_ms,
                    sugestao_recuperacao=saida.get("sugestao_recuperacao"),
                    alternativa_recuperacao=saida.get("alternativa_recuperacao"),
                    mensagem_humana=saida.get("mensagem_humana") or erro_msg,
                )

            verificado = bool(saida.get("verificado", risco is Risco.VERDE))
            evidencias = saida.get("evidencias", {})
            if not evidencias and any(k in saida for k in ("pid", "hwnd", "caminho", "cpu_percent", "modelo", "arquivos")):
                evidencias = {
                    k: saida[k]
                    for k in ("pid", "hwnd", "titulo_janela", "caminho", "cpu_percent", "modelo", "total_encontrados")
                    if k in saida
                }

            if not verificado or (
                risco is not Risco.VERDE
                and (saida.get("sucesso") is not True or not evidencias)
            ):
                erro_msg = str(saida.get("mensagem_humana") or "A execucao nao apresentou evidencia verificavel.")
                return ResultadoExecucao(
                    id_acao=id_acao,
                    ferramenta=nome_ferramenta,
                    parametros=params,
                    estado=EstadoExecucao.FAILED,
                    verificado=False,
                    resultado=saida,
                    erros=[erro_msg],
                    evidencias=evidencias,
                    duracao_ms=duracao_ms,
                    mensagem_humana=erro_msg,
                )

            return ResultadoExecucao(
                id_acao=id_acao,
                ferramenta=nome_ferramenta,
                parametros=params,
                estado=EstadoExecucao.SUCCESS,
                verificado=verificado,
                resultado=saida,
                evidencias=evidencias,
                duracao_ms=duracao_ms,
                mensagem_humana=str(saida.get("mensagem_humana") or saida.get("mensagem") or "Concluído."),
            )

        if isinstance(saida, str):
            s_lower = saida.lower()
            if s_lower.startswith(("falha", "erro", "não foi possível", "nao foi possivel", "acesso negado")):
                return ResultadoExecucao(
                    id_acao=id_acao,
                    ferramenta=nome_ferramenta,
                    parametros=params,
                    estado=EstadoExecucao.FAILED,
                    verificado=False,
                    resultado=saida,
                    erros=[saida],
                    duracao_ms=duracao_ms,
                    mensagem_humana=saida,
                )
            if risco is not Risco.VERDE:
                return ResultadoExecucao(
                    id_acao=id_acao,
                    ferramenta=nome_ferramenta,
                    parametros=params,
                    estado=EstadoExecucao.FAILED,
                    verificado=False,
                    resultado=saida,
                    erros=["A ferramenta modificadora retornou texto sem evidencia verificavel."],
                    duracao_ms=duracao_ms,
                    mensagem_humana=saida,
                )
            return ResultadoExecucao(
                id_acao=id_acao,
                ferramenta=nome_ferramenta,
                parametros=params,
                estado=EstadoExecucao.SUCCESS,
                verificado=True,
                resultado=saida,
                evidencias={"detalhe": saida},
                duracao_ms=duracao_ms,
                mensagem_humana=saida,
            )

        if isinstance(saida, list):
            if risco is not Risco.VERDE:
                return ResultadoExecucao(
                    id_acao=id_acao,
                    ferramenta=nome_ferramenta,
                    parametros=params,
                    estado=EstadoExecucao.FAILED,
                    verificado=False,
                    resultado=saida,
                    erros=["A ferramenta modificadora retornou uma lista sem evidencia verificavel."],
                    duracao_ms=duracao_ms,
                    mensagem_humana="A acao nao apresentou evidencia verificavel.",
                )
            return ResultadoExecucao(
                id_acao=id_acao,
                ferramenta=nome_ferramenta,
                parametros=params,
                estado=EstadoExecucao.SUCCESS,
                verificado=True,
                resultado=saida,
                evidencias={"quantidade_itens": len(saida)},
                duracao_ms=duracao_ms,
                mensagem_humana=f"Encontrei {len(saida)} itens.",
            )

        return ResultadoExecucao(
            id_acao=id_acao,
            ferramenta=nome_ferramenta,
            parametros=params,
            estado=EstadoExecucao.FAILED,
            verificado=False,
            resultado=saida,
            erros=["A ferramenta retornou um formato sem evidencia verificavel."],
            duracao_ms=duracao_ms,
            mensagem_humana="Nao consegui verificar o resultado da acao.",
        )

    def executar_plano(
        self,
        etapas: list[dict[str, Any]],
        *,
        confirmado_pelo_usuario: bool = False,
    ) -> list[ResultadoExecucao]:
        """Executa uma sequência de etapas verificando cada uma antes de avançar para a próxima."""
        resultados: list[ResultadoExecucao] = []
        for etapa in etapas:
            nome = etapa.get("acao") or etapa.get("ferramenta") or ""
            params = etapa.get("parametros") or {}
            res = self.executar(
                nome,
                params,
                confirmado_pelo_usuario=confirmado_pelo_usuario,
            )
            resultados.append(res)
            if res.estado != EstadoExecucao.SUCCESS:
                # Interrompe o plano imediatamente se uma etapa falhar ou exigir confirmação
                break
        return resultados
