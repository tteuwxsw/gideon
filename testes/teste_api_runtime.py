"""Portao HTTP isolado: autenticacao, cookie e protecao CSRF."""

import asyncio
import os
import tempfile
from pathlib import Path

import httpx


async def testar() -> None:
    with tempfile.TemporaryDirectory() as temporario:
        os.environ["GIDEON_DATA_DIR"] = str(Path(temporario) / "dados")

        from gideon.servidor import TOKEN_LOCAL, app

        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transporte,
            base_url="http://127.0.0.1:8000",
        ) as cliente:
            login = await cliente.post(
                "/api/auth/login",
                json={"token": TOKEN_LOCAL},
                headers={"Origin": "http://127.0.0.1:8000"},
            )
            assert login.status_code == 200
            assert "httponly" in login.headers["set-cookie"].lower()

            status = await cliente.get("/api/status")
            assert status.status_code == 200
            assert status.json()["versao"] == "0.3.0"

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
                "/api/avatar/modo",
                json={"modo": "compacto"},
                headers={
                    "Origin": "http://127.0.0.1:8000",
                    "X-Gideon-CSRF": "1",
                },
            )
            assert valido.status_code == 200

    print("[OK] API local autenticada e protegida contra CSRF/origens diferentes.")


if __name__ == "__main__":
    asyncio.run(testar())
