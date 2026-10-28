"""Portao HTTP isolado: autenticacao, cookie e protecao CSRF."""

import asyncio
import os
import tempfile
from pathlib import Path

import httpx

from gideon.versao import VERSAO


async def testar() -> None:
    with tempfile.TemporaryDirectory() as temporario:
        os.environ["GIDEON_DATA_DIR"] = str(Path(temporario) / "dados")
        os.environ["GIDEON_BOOTSTRAP_TOKEN"] = "bootstrap-teste"
        os.environ["GIDEON_RUNTIME_TOKEN"] = "runtime-teste"

        from gideon.servidor import TOKEN_LOCAL, app

        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transporte,
            base_url="http://127.0.0.1:8000",
        ) as cliente:
            bootstrap = await cliente.post(
                "/api/auth/login",
                json={"token": "bootstrap-teste"},
                headers={"Origin": "http://127.0.0.1:8000"},
            )
            assert bootstrap.status_code == 200
            bootstrap_reutilizado = await cliente.post(
                "/api/auth/login",
                json={"token": "bootstrap-teste"},
                headers={"Origin": "http://127.0.0.1:8000"},
            )
            assert bootstrap_reutilizado.status_code == 401

            login = await cliente.post(
                "/api/auth/login",
                json={"token": TOKEN_LOCAL},
                headers={"Origin": "http://127.0.0.1:8000"},
            )
            assert login.status_code == 200
            assert "httponly" in login.headers["set-cookie"].lower()

            status = await cliente.get("/api/status")
            assert status.status_code == 200
            assert status.json()["versao"] == VERSAO
            assert status.json()["parada_emergencia"] is False

            interface = await cliente.get("/")
            assert interface.status_code == 200
            assert '<div id="root">' in interface.text or 'id="avatarImage"' in interface.text
            assert "gideon-3d.js" not in interface.text

            avatar = await cliente.get("/avatar/gideon-idle.webp")
            assert avatar.status_code == 200
            assert avatar.headers["content-type"] == "image/webp"
            assert len(avatar.content) > 10_000

            avatar_3d = await cliente.get("/avatar/gideon-head.glb")
            assert avatar_3d.status_code == 200
            assert avatar_3d.headers["content-type"] == "model/gltf-binary"
            assert avatar_3d.content[:4] == b"glTF"

            avatar_inexistente = await cliente.get("/avatar/desconhecido.webp")
            assert avatar_inexistente.status_code == 404

            sem_csrf = await cliente.post("/api/chat/limpar")
            assert sem_csrf.status_code == 403

            origem_invalida = await cliente.post(
                "/api/chat/limpar",
                headers={
                    "Origin": "http://127.0.0.1:9999",
                    "X-Gideon-CSRF": "1",
                },
            )
            assert origem_invalida.status_code == 403

            valido = await cliente.post(
                "/api/chat/limpar",
                headers={
                    "Origin": "http://127.0.0.1:8000",
                    "X-Gideon-CSRF": "1",
                },
            )
            assert valido.status_code == 200

            novo_bootstrap = await cliente.post(
                "/api/runtime/bootstrap",
                headers={
                    "Origin": "http://127.0.0.1:8000",
                    "X-Gideon-CSRF": "1",
                    "X-Gideon-Runtime": "runtime-teste",
                },
            )
            assert novo_bootstrap.status_code == 200
            token_reabertura = novo_bootstrap.json()["token"]
            assert token_reabertura and token_reabertura != "bootstrap-teste"

            login_reabertura = await cliente.post(
                "/api/auth/login",
                json={"token": token_reabertura},
                headers={"Origin": "http://127.0.0.1:8000"},
            )
            assert login_reabertura.status_code == 200

            parar = await cliente.post(
                "/api/emergencia/parar",
                headers={"Origin": "http://127.0.0.1:8000", "X-Gideon-CSRF": "1"},
            )
            assert parar.status_code == 200
            assert parar.json()["parada_emergencia"] is True

            retomar = await cliente.post(
                "/api/emergencia/retomar",
                headers={"Origin": "http://127.0.0.1:8000", "X-Gideon-CSRF": "1"},
            )
            assert retomar.status_code == 200
            assert retomar.json()["parada_emergencia"] is False

    print("[OK] API local autenticada e protegida contra CSRF/origens diferentes.")


if __name__ == "__main__":
    asyncio.run(testar())
