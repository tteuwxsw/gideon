# 🤖 GIDEON - Instalação

Duas formas de usar Gideon:

---

## 1️⃣ LINHA DE COMANDO (Híbrido)

Usa Python direto no terminal.

### Executar uma vez:
```bash
python -m gideon.wake
```

### Ou instalar comando global:
```bash
pip install -e .
gideon
```

**Vantagens:**
- Mais leve (~50 MB)
- Fácil de atualizar (git pull)
- Acesso a todos os recursos

---

## 2️⃣ EXECUTÁVEL (.EXE)

Um arquivo standalone que roda sozinho.

### Localização:
```
C:\Users\henry\Documents\Gideon\dist\GideonWake.exe
```

**Como usar:**
1. Clique duplo no arquivo
2. Pronto! Gideon inicia invisível

**Vantagens:**
- Não precisa de Python
- Roda em qualquer PC Windows
- Portátil (copie para USB)

---

## ⚙️ Configurações Extras

### Autostart (Iniciar com Windows):
```powershell
.\registrar_autostart.ps1
```

### Voz da Gideon (The Flash):
```bash
.\instalar_ffmpeg.bat
python testar_voz_gideon.py
```

### Otimizar Velocidade:
```bash
python patch_turbo.py
```

---

## 📝 Requisitos

- Windows 10/11
- Python 3.12+ (só para modo híbrido)
- Chave API Gemini (em `.env`)

---

**Escolha uma forma e use. Simples assim.**
