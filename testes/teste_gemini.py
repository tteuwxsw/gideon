import sys
import keyring
from google import genai

print("Obtendo chave do cofre...", flush=True)
chave = keyring.get_password("alfred", "gemini_api_key")
if not chave:
    print("ERRO: Nenhuma chave encontrada no cofre do sistema!", flush=True)
    sys.exit(1)

print(f"Chave encontrada ({len(chave)} caracteres). Conectando ao Gemini...", flush=True)
client = genai.Client(api_key=chave)

modelos_para_testar = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-flash-latest",
]

sucesso = False
for modelo in modelos_para_testar:
    print(f"\nTestando modelo '{modelo}'...", flush=True)
    try:
        resp = client.models.generate_content(
            model=modelo,
            contents="Diga em uma frase curta: 'Ola Henry, sou o Alfred e estou pronto!'",
        )
        print(f"--> SUCESSO com {modelo}!")
        print(f"Resposta: {resp.text.strip()}")
        sucesso = True
        break
    except Exception as e:
        msg = str(e)
        if "404" in msg:
            print("--> Indisponivel (404)")
        elif "503" in msg:
            print("--> Sobrecarga temporaria (503)")
        elif "429" in msg:
            print("--> Limite de cota (429)")
        else:
            print(f"--> Erro: {msg[:120]}")

if not sucesso:
    print("\nNenhum modelo respondeu no momento. Vamos tentar novamente em instantes.", flush=True)
