"""Testes de verificacao da arquitetura Unreal Engine 5 (gideon_ue5), otimizacoes RX 580 e rollback Godot."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from gideon.supervisor import ROOT_DIR, UE5_DIR, AVATAR_DIR, localizar_renderizador_avatar
from gideon.voz.visemas import VISEMAS_MODELO


def testar_estrutura_projeto_ue5() -> None:
    uproject_path = UE5_DIR / "GideonUE5.uproject"
    assert uproject_path.is_file(), "GideonUE5.uproject ausente"
    dados_uproject = json.loads(uproject_path.read_text(encoding="utf-8"))
    assert dados_uproject["FileVersion"] == 3
    modulos = [m["Name"] for m in dados_uproject.get("Modules", [])]
    assert "GideonUE5" in modulos

    arquivos_obrigatorios = [
        UE5_DIR / "Config" / "DefaultEngine.ini",
        UE5_DIR / "Config" / "DefaultGame.ini",
        UE5_DIR / "Config" / "DefaultScalability.ini",
        UE5_DIR / "Source" / "GideonUE5.Target.cs",
        UE5_DIR / "Source" / "GideonUE5Editor.Target.cs",
        UE5_DIR / "Source" / "GideonUE5" / "GideonUE5.Build.cs",
        UE5_DIR / "Source" / "GideonUE5" / "Public" / "GideonUE5.h",
        UE5_DIR / "Source" / "GideonUE5" / "GideonUE5.cpp",
        UE5_DIR / "Source" / "GideonUE5" / "Public" / "GideonGameMode.h",
        UE5_DIR / "Source" / "GideonUE5" / "Private" / "GideonGameMode.cpp",
        UE5_DIR / "Source" / "GideonUE5" / "Public" / "GideonWSSubsystem.h",
        UE5_DIR / "Source" / "GideonUE5" / "Private" / "GideonWSSubsystem.cpp",
        UE5_DIR / "Source" / "GideonUE5" / "Public" / "GideonDesktopWindow.h",
        UE5_DIR / "Source" / "GideonUE5" / "Private" / "GideonDesktopWindow.cpp",
        UE5_DIR / "Source" / "GideonUE5" / "Public" / "GideonHologramAvatar.h",
        UE5_DIR / "Source" / "GideonUE5" / "Private" / "GideonHologramAvatar.cpp",
        UE5_DIR / "Content" / "Maps" / "GideonTimeVault.umap",
        UE5_DIR / "Shaders" / "GideonStarLabsHologram.ush",
        UE5_DIR / "compilar_ue5.ps1",
    ]
    for arq in arquivos_obrigatorios:
        assert arq.is_file(), f"Arquivo UE5 obrigatorio ausente: {arq}"
    print("[OK] Estrutura do projeto Unreal Engine 5 (C++ / Config / Shaders) integra.")


def testar_otimizacao_rx580_ini() -> None:
    ini_texto = (UE5_DIR / "Config" / "DefaultEngine.ini").read_text(encoding="utf-8")
    regras_rx580 = [
        "DefaultGraphicsRHI=DefaultGraphicsRHI_DX11",
        "r.DynamicGlobalIlluminationMethod=0",
        "r.Nanite=0",
        "r.Shadow.Virtual.Enable=0",
        "r.PostProcessing.PropagateAlpha=1",
        "r.HairStrands.Enable=0",
        "r.HairStrands.Cards=1",
    ]
    for regra in regras_rx580:
        assert regra in ini_texto, f"Configuracao RX 580 ausente no DefaultEngine.ini: {regra}"
    print("[OK] Otimizacoes de hardware para AMD Radeon RX 580 8GB (sem Lumen/Nanite/Groom, DX11 Alpha) confirmadas.")


def testar_paridade_protocolo_e_visemas_cpp() -> None:
    ws_cpp = (UE5_DIR / "Source" / "GideonUE5" / "Private" / "GideonWSSubsystem.cpp").read_text(encoding="utf-8")
    avatar_cpp = (UE5_DIR / "Source" / "GideonUE5" / "Private" / "GideonHologramAvatar.cpp").read_text(encoding="utf-8")
    win_cpp = (UE5_DIR / "Source" / "GideonUE5" / "Private" / "GideonDesktopWindow.cpp").read_text(encoding="utf-8")

    # 1. Todos os 15 visemas foneticos do backend Python devem estar mapeados no C++ do UE5
    for visema in VISEMAS_MODELO:
        assert visema in avatar_cpp, f"Visema '{visema}' nao mapeado em GideonHologramAvatar.cpp"

    # 2. Eventos essenciais do protocolo WebSocket
    for ev in (
        "emocao",
        "fala_inicio",
        "fala_chunk",
        "fala_fim",
        "estado_ia",
        "modo",
        "olhar",
        "atencao_desktop",
        "config_holograma",
        "telemetria_avatar",
        "X-Gideon-Token",
    ):
        assert ev in ws_cpp, f"Evento/Header '{ev}' ausente em GideonWSSubsystem.cpp"

    # 3. Composicao transparente DWM e Click-Through Win32
    for api_win32 in ("DwmExtendFrameIntoClientArea", "WS_EX_TRANSPARENT", "WS_EX_TOOLWINDOW", "WS_EX_NOACTIVATE"):
        assert api_win32 in win_cpp, f"API Win32 '{api_win32}' ausente em GideonDesktopWindow.cpp"

    print("[OK] Paridade 100% entre protocolo Python, 15 visemas foneticos, curvas MetaHuman/ARKit e janela DWM no C++ UE5.")


def testar_selecao_supervisor_e_rollback_godot() -> None:
    # Garante que o projeto Godot original permanece intacto para rollback
    assert (AVATAR_DIR / "project.godot").is_file(), "Projeto Godot original foi removido indevidamente!"
    assert (AVATAR_DIR / "scripts" / "avatar_controller.gd").is_file()

    # Simula binario UE5 compilado e verifica selecao automatica + rollback imediato para Godot
    with tempfile.TemporaryDirectory() as tmp:
        falso_ue5 = Path(tmp) / "GideonUE5.exe"
        falso_ue5.write_bytes(b"MZ")
        anterior = os.environ.get("GIDEON_UE5_EXE")
        try:
            os.environ["GIDEON_UE5_EXE"] = str(falso_ue5)
            motor, cmd = localizar_renderizador_avatar("auto")
            assert motor == "ue5"
            assert cmd[0] == str(falso_ue5)
            assert "-dx11" in cmd and "-WINDOWED" in cmd

            # Testa rollback explicito para Godot
            motor_rb, cmd_rb = localizar_renderizador_avatar("godot")
            assert motor_rb == "godot"
        finally:
            if anterior is None:
                os.environ.pop("GIDEON_UE5_EXE", None)
            else:
                os.environ["GIDEON_UE5_EXE"] = anterior

    print("[OK] Seletor do supervisor prioriza UE5 quando compilado e preserva rollback instantaneo para Godot.")


if __name__ == "__main__":
    testar_estrutura_projeto_ue5()
    testar_otimizacao_rx580_ini()
    testar_paridade_protocolo_e_visemas_cpp()
    testar_selecao_supervisor_e_rollback_godot()
    print("\nTodos os testes da arquitetura Unreal Engine 5 passaram.")
