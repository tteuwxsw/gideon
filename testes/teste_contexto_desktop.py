"""Testes não visuais de contexto do desktop e proteção de privacidade."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import gideon.presenca as presenca
from gideon.tools import sistema


class _User32Falso:
    def __init__(self, titulo: str) -> None:
        self.titulo = titulo

    def GetSystemMetrics(self, indice: int) -> int:
        return 1920 if indice == 0 else 1080

    def GetForegroundWindow(self) -> int:
        return 321

    def GetWindowTextLengthW(self, _hwnd: int) -> int:
        return len(self.titulo)

    def GetWindowTextW(self, _hwnd: int, buffer, _tamanho: int) -> None:
        buffer.value = self.titulo

    def GetWindowThreadProcessId(self, _hwnd: int, pid) -> None:
        pid._obj.value = 654

    def GetWindowRect(self, _hwnd: int, rect) -> bool:
        rect._obj.left = 100
        rect._obj.top = 80
        rect._obj.right = 1500
        rect._obj.bottom = 900
        return True


@contextmanager
def _janela_falsa(titulo: str, processo: str):
    with (
        patch.object(presenca, "os", SimpleNamespace(name="nt")),
        patch.object(
            presenca.ctypes,
            "windll",
            SimpleNamespace(user32=_User32Falso(titulo)),
            create=True,
        ),
        patch.object(
            presenca.psutil,
            "Process",
            lambda _pid: SimpleNamespace(name=lambda: processo),
        ),
    ):
        yield


class TesteContextoDesktopPrivacidade(unittest.TestCase):
    def test_inspecao_da_janela_ativa_nao_rastreia_ponteiro(self):
        with _janela_falsa("Documento de trabalho", "editor.exe"):
            contexto = presenca.inspecionar_janela_ativa_segura()

        self.assertEqual(contexto["hwnd"], 321)
        self.assertEqual(contexto["pid"], 654)
        self.assertEqual(contexto["titulo"], "Documento de trabalho")
        self.assertEqual(contexto["processo"], "editor.exe")
        self.assertEqual(
            contexto["dimensoes"],
            {
                "esquerda": 100,
                "topo": 80,
                "largura": 1400,
                "altura": 820,
            },
        )
        self.assertFalse(hasattr(presenca, "obter_posicao_cursor_normalizada"))
        self.assertFalse(hasattr(presenca, "MonitorPresencaDesktop"))
        self.assertFalse(any("olhar" in chave or "cursor" in chave for chave in contexto))

    def test_inspecao_mascara_titulo_e_processo_sensiveis(self):
        with _janela_falsa("Cofre pessoal", "segredos.exe"):
            contexto = presenca.inspecionar_janela_ativa_segura(
                apps_excluidos=["cofre", "segredos.exe"]
            )

        self.assertTrue(contexto["protegida_privacidade"])
        self.assertEqual(contexto["titulo"], "[Janela Protegida por Privacidade]")
        self.assertEqual(contexto["processo"], "[Processo Protegido]")

    def test_ferramenta_de_contexto_e_explicita_e_nao_visual(self):
        janela = {
            "hwnd": 321,
            "pid": 654,
            "titulo": "Documento de trabalho",
            "processo": "editor.exe",
            "protegida_privacidade": False,
        }
        with patch.object(presenca, "inspecionar_janela_ativa_segura", lambda: janela):
            resultado = sistema.inspecionar_contexto_tela()

        self.assertTrue(resultado["sucesso"])
        self.assertTrue(resultado["verificado"])
        self.assertEqual(resultado["janela_ativa"], janela)
        self.assertEqual(resultado["evidencias"]["hwnd_ativo"], 321)
        self.assertNotIn("cursor", resultado)
        self.assertNotIn("janelas_visiveis", resultado)

    def test_telemetria_gpu_preserva_adaptador_generico(self):
        adaptador = {
            "modelo": "Adaptador de teste",
            "vram_total": "4 GB",
            "status": "OK",
        }
        cache = {
            "modelo": adaptador["modelo"],
            "vram": adaptador["vram_total"],
            "uso_3d": "Não disponível",
            "status": adaptador["status"],
            "adaptadores": [adaptador],
        }
        with (
            patch.object(sistema, "_CACHE_GPU", cache),
            patch.object(sistema, "_CACHE_GPU_TS", sistema.time.time()),
        ):
            resultado = sistema.obter_status_gpu()

        self.assertTrue(resultado["sucesso"])
        self.assertTrue(resultado["verificado"])
        self.assertEqual(resultado["modelo"], "Adaptador de teste")
        self.assertEqual(resultado["adaptadores"], [adaptador])


if __name__ == "__main__":
    unittest.main()
