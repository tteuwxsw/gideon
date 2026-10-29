# 🤖 GIDEON - Instalação no Windows e Linux

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

### Zorin OS / Ubuntu

Na pasta do projeto:

```bash
chmod +x instalar_linux.sh
./instalar_linux.sh
~/.local/bin/gideon open
```

Comandos úteis:

```bash
gideon start                 # núcleo em segundo plano
gideon open                  # abre a interface
gideon status                # mostra o estado
gideon stop                  # encerra
gideon autostart enable      # inicia no login
gideon autostart disable     # remove do login
```

O Linux usa Chrome/Chromium para a janela, `wmctrl` para janelas, `pactl`
para volume, `gio` para a Lixeira e o padrão XDG para autostart.

O instalador também cria `~/.config/systemd/user/gideon.service`. Assim, o
núcleo permanece ativo com a janela fechada e reinicia automaticamente se
falhar. Ele roda com seu usuário, nunca como `root`.

```bash
systemctl --user status gideon.service
journalctl --user -u gideon.service -f
systemctl --user restart gideon.service
```

## Interface holográfica 3D

A interface principal renderiza `gideon-head.glb` com Three.js/WebGL. O avatar
pisca, acompanha o cursor, muda sua iluminação e movimenta a boca conforme o
nível de áudio. Estados de escuta, pensamento e fala possuem cores e animações
próprias. Em máquinas sem WebGL, um avatar leve é exibido automaticamente.

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

- Windows 10/11 ou Zorin OS/Ubuntu
- Python 3.12+ (só para modo híbrido)
- Chave API Gemini (em `.env`)

---

**Escolha uma forma e use. Simples assim.**
