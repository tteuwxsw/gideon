"""Guarda a chave da API do Gemini no cofre do Windows.
Uso: copie a chave (Ctrl+C) e rode: .venv\\Scripts\\python.exe guardar_chave.py
A chave é lida da área de transferência e apagada dela logo depois."""

import keyring
import subprocess

SERVICO = "alfred"
CONTA = "gemini_api_key"

# Lê a chave da área de transferência do Windows
resultado = subprocess.run(
    ["powershell", "-command", "Get-Clipboard"],
    capture_output=True, text=True
)
chave = resultado.stdout.strip()

if not chave or len(chave) < 10:
    print("❌ Nenhuma chave encontrada na área de transferência.")
    print("   Copie a chave (Ctrl+C no site) e rode de novo.")
else:
    keyring.set_password(SERVICO, CONTA, chave)
    # Limpa a área de transferência
    subprocess.run(["powershell", "-command", "Set-Clipboard -Value ''"], capture_output=True)
    # Verifica
    salva = keyring.get_password(SERVICO, CONTA)
    if salva == chave:
        print(f"✅ Chave guardada no cofre do Windows! ({len(chave)} caracteres)")
        print("   A área de transferência foi limpa por segurança.")
    else:
        print("❌ Algo deu errado ao salvar. Tente novamente.")
