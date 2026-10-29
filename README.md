# 🤖 Gideon

Assistente pessoal com IA inspirada na Gideon do The Flash.

## 🚀 Instalação Rápida

**Duas formas:**

### 1. Linha de comando (Windows e Linux)
```bash
gideon open
```

### 2. Executável (.exe)
```
dist\GideonWake.exe
```

📖 [Guia completo de instalação](INSTALAR.md)

### Zorin OS / Ubuntu

```bash
chmod +x instalar_linux.sh
./instalar_linux.sh
~/.local/bin/gideon open
```

O instalador registra a Gideon automaticamente como um serviço pessoal do `systemd`,
sempre ativo após o login e reiniciado automaticamente em caso de falha:

```bash
systemctl --user status gideon.service
journalctl --user -u gideon.service -f
systemctl --user restart gideon.service
```

A interface usa Three.js e o modelo 3D holográfico em
`gideon/web/avatar/gideon-head.glb`. O rosto reage aos estados de escuta,
processamento e fala; se WebGL não estiver disponível, a interface usa um
fallback leve automaticamente.

A chave do Gemini não fica no código-fonte. Abra **Configurações → Google
Gemini**, cole a chave e use **Salvar**. A Gideon valida a conexão e guarda o
segredo no cofre do sistema (`keyring`), sem devolvê-lo ao navegador ou aos
logs.

---

## ✨ Recursos

- 🎙️ Controle por voz
- 🧠 IA Gemini integrada
- 🖥️ Automação desktop
- 📱 Interface web local
- 🔒 Dados locais protegidos; respostas usam Gemini e podem recorrer ao Ollama local quando configurado e sem conexão

---

## 📦 Estrutura

```
gideon/
├── cerebro.py       # Motor de IA
├── voz/            # Síntese e reconhecimento
├── servidor.py     # API local
└── wake.py         # Ponto de entrada
```

---

## ⚙️ Configuração

1. Copie `.env.example` para `.env`
2. Adicione sua chave Gemini:
   ```
   GEMINI_API_KEY=sua_chave_aqui
   ```
3. Execute

---

## 🎯 Comandos

```bash
# Iniciar e abrir a interface
gideon open

# Manter somente o núcleo em segundo plano
gideon start

# Ou com comando instalado
gideon

# Autostart no Windows
.\registrar_autostart.ps1

# Autostart no Linux
gideon autostart enable

# Voz Gideon
.\instalar_ffmpeg.bat
```

---

## 📄 Licença

Uso pessoal.

---

**Gideon está online. Como posso ajudar?**
