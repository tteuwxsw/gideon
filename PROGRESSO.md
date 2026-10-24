# Gideon — Progresso do Projeto

**Pessoa:** Henry  
**Início:** 23/10/2026  
**Evolução:** 24/10/2026 (Transição de Alfred para Gideon — Assistente Holográfica 3D inspirada em *The Flash*)  
**Caminho:** B — Cérebro na nuvem (Gemini gratuito), mãos no computador, presença holográfica na tela  
**Interface Visual:** Avatar 3D em Godot 4 (shader holográfico azul, expressões, overlay de desktop intangível ao mouse)  
**Voz:** 100% Mãos-Livres (Faster-Whisper local + Síntese vocal + Wake Word "Gideon")  
**Computador:** Windows  
**Interação:** Holograma 3D e controle puramente por voz  

---

## ✅ O que já foi feito

### Fase 0 · Preparação e Cofre (Concluída)
- [x] **Entrevista inicial** — Computador Windows, prioridades definidas
- [x] **Git** — Repositório inicializado e limpo
- [x] **Python 3.12 + uv** — Ambiente virtual isolado
- [x] **.gitignore** — Proteção de segredos e dados locais
- [x] **Chave da API do Gemini** — Salva com segurança no Windows Credential Manager (`gideon` / `alfred`)
- [x] **Portão da Fase 0** — Chave no cofre, teste de conexão aprovado

### Fase 1 · Cérebro por Texto e Telemetria (Concluída)
- [x] **Renomeação do projeto para Gideon** em todo o código e dependências
- [x] **Persona da Gideon** (`gideon/persona.py`) — Elegante, serena, cordial, inspirada em The Flash, com tags emocionais `[EMOCAO:nome]`
- [x] **Conector do cérebro** (`gideon/cerebro.py`) — Streaming em tempo real via Gemini (`gemini-3.1-flash-lite`) com cálculo de tokens e custo em USD
- [x] **Servidor local seguro** (`gideon/servidor.py`) — FastAPI restrito a `127.0.0.1:8000`, autenticado via token em `dados/auth_token.txt`
- [x] **Hub WebSocket bidirecional** (`/ws`) — Broadcast em tempo real de fala, emoções e estados para o avatar 3D
- [x] **Protocolo de comunicação** (`gideon/protocolo.py`) — Tipos de mensagem, 9 emoções, 5 modos de exibição e extração de tags
- [x] **Interface Web HUD Holográfica** (`gideon/web/index.html`) — Design Time Vault / STAR Labs, streaming SSE, status do WebSocket, badges de emoção e custos
- [x] **Portão da Fase 1 Aprovado** (`testes/teste_gideon.py`):
  - 10 trocas de mensagens consecutivas sem falhas
  - Custo em dólares calculado e exibido em cada resposta
  - Tratamento resiliente de erros de rede sem travamentos

### Fase 1.5 · Base do Avatar Holográfico 3D (Criada)
- [x] **Estrutura do projeto Godot 4** (`gideon_avatar/`)
- [x] **Configuração de janela transparente, sem bordas e INTANGÍVEL ao mouse** (`MOUSE_PASSTHROUGH = true`)
- [x] **Shader holográfico cinematográfico** (`gideon_avatar/shaders/holograma.gdshader`) — Fresnel, scanlines móveis, pulso digital, transparência
- [x] **Cliente WebSocket nativo** (`gideon_avatar/scripts/ws_client.gd`) — Conexão com token local e reconexão automática
- [x] **Controlador de animações humanas** (`gideon_avatar/scripts/avatar_controller.gd`):
  - Micro-idle: piscar natural (3-6s), respiração sutil, micro-movimentos de olhar
  - Deslizamento suave com Tween cúbico ao trocar de posição na tela
  - 5 modos de presença: Compacto, Conversa, Foco, Operacional, Oculto
- [x] **Cena base 3D** (`gideon_avatar/scenes/avatar.tscn`) com Bloom/Glow

### Fase 2 · Memória Permanente (Concluída)
- [x] **Banco de dados local SQLite** (`dados/memoria.db`) com tabelas `fatos`, `conversa`, `resumos`
- [x] **Busca textual sem acento** (`conversa_fts`) usando FTS5 com tokenizer `unicode61 remove_diacritics 2` e triggers automáticos
- [x] **Comandos diretos de memória**:
  - *"lembra que [chave] é [valor]"* -> grava fato permanente imediatamente sem gastar tokens de API
  - *"o que você sabe sobre mim?"* -> lista os fatos conhecidos
  - *"esquece [fato]"* -> remove o fato do banco
- [x] **Injeção contextual no Cérebro**: lembranças relevantes e fatos são injetados automaticamente no prompt do sistema
- [x] **Portão da Fase 2 Aprovado** (`testes/teste_memoria.py`):
  - Dados sobrevivem ao reinício completo da aplicação
  - Busca FTS5 por "reuniao" localiza "reunião"
  - Gideon cita a data em que a informação foi registrada (*"Conforme registrei em nossa conversa de hoje, 24/10/2026..."*)

### Fase 5 · Subsistema de Voz Mãos-Livres (Concluída)
- [x] **Ouvido Neural** (`gideon/voz/ouvido.py`):
  - Captura contínua de microfone a 16 kHz via `sounddevice`
  - Detector de energia/silêncio (VAD) automático
  - Transcrição ultra-rápida local com **Faster-Whisper** (`base`, int8, em português)
  - Reconhecimento da palavra de chamada (*"Gideon"* e variações fonéticas)
- [x] **Síntese Vocal Local** (`gideon/voz/fala.py`):
  - Motor de fala nativo do Windows (Microsoft Maria Desktop) com zero latência e 100% offline
  - Suporte a Kokoro ONNX neural de alta fidelidade
  - Transmissão de eventos de sincronia labial (lip sync) para o avatar durante a fala
- [x] **Orquestrador Mãos-Livres** (`gideon/voz/orquestrador.py`):
  - Ciclo completo: Ouve "Gideon" -> Materializa avatar -> Processa resposta -> Fala com boca mexendo -> Aguarda follow-up por 12s
- [x] **Flag CLI `--voz`**: Inicia o servidor com o ouvinte mãos-livres ativo direto do terminal
- [x] **Testes de Voz Aprovados** (`testes/teste_voz.py`):
  - Extração de Wake Word: 100%
  - Emissão de eventos para o avatar: 100%
  - Controle de início/pausa via API: 100%

### Fase 4 · Mãos que Leem e Agem — Segurança V/A/R (Concluída)
- [x] **Portão de Risco e Auditoria** (`gideon/gate.py`):
  - Classificação formal de risco: Verde (leitura direta), Amarelo (reversível) e Vermelho (confirmação obrigatória)
  - Log permanente em formato JSONL (`dados/auditoria.jsonl`) registrando ferramenta, parâmetros, risco e resultado
  - Botão de parada e controle de limite diário de gastos em USD
- [x] **Ferramentas de Sistema** (`gideon/tools/sistema.py`):
  - Telemetria de hardware em tempo real: CPU, memória RAM usada/livre, espaço no disco C, bateria e uptime
  - Listagem dos aplicativos reais em execução no Windows (Discord, Spotify, Chrome, Steam, etc.)
  - Abertura de programas do Windows via PowerShell/processos (`abrir_programa`)
  - Bloqueio instantâneo da tela do computador (`bloquear_estacao`)
- [x] **Ferramentas de Arquivos** (`gideon/tools/arquivos.py`):
  - Listagem de diretórios do usuário (Downloads, Documentos, Desktop)
  - Leitura segura de arquivos de texto e código com proteção rigorosa a segredos (`.env`, chaves e senhas)
  - Envio de arquivos para a Lixeira do Windows (`mover_para_lixeira`, sem exclusão destrutiva)
- [x] **Integração Silenciosa com o Windows** (`gideon/integracao_windows.py`):
  - Inicialização 100% oculta via `pythonw.exe` e VBScript no `shell:startup`
  - Sem janela preta de terminal, sem ícone na barra de tarefas, pronta na inicialização do sistema
- [x] **Portão da Fase 4 Aprovado** (`testes/teste_ferramentas.py`):
  - Catálogo de 7 ferramentas validado
  - Leitura real de telemetria do PC
  - Bloqueio de arquivos protegidos
  - Registro de auditoria no log permanente verificado

---

## 🔜 O que falta fazer

### Fase 3 · Rosto 3D da Gideon + Integração Godot 4 (Concluída)
- [x] **Godot Engine 4.7.2** instalado no Windows via WinGet oficial
- [x] **Projeto `gideon_avatar/` validado**:
  - Shader holográfico GLSL com Fresnel e scanlines compilado sem erros
  - Cliente WebSocket conectando e autenticando via token local
  - Janela transparente sem bordas e intangível (`MOUSE_PASSTHROUGH = true`)
  - Sistema de tween cúbico para movimentação suave na tela
- [x] **Launchers de um clique**:
  - `iniciar_gideon.bat`: Acorda o cérebro em segundo plano e projeta o holograma 3D
  - `parar_gideon.bat`: Encerra todos os processos de forma limpa
  - `atualizar_gideon.bat`: Sincroniza o repositório e valida testes com um duplo clique
- [x] **Repositório Privado no GitHub**:
  - Código sincronizado em `https://github.com/tteuwxsw/gideon` (privado e seguro)
  - `origin/master` configurado para atualizações contínuas
- [x] **Auto-Atualização por Voz**:
  - Comando *"Gideon, atualize seus sistemas"* puxa melhorias do GitHub e sincroniza dependências sem intervenção manual

---

## 🔜 O que falta fazer

### Fases 6–9 · Automações, Proatividade e Integrações
- [x] Inicialização 100% oculta junto com o Windows (`gideon/integracao_windows.py` via `pythonw.exe`)
- [ ] Importação de malha de rosto feminino com 52 blendshapes faciais (pasta `gideon_avatar/modelos/` criada e scripts preparados)
- [ ] Rotina matinal falada por horário com relógio de parede
- [ ] Integração com WhatsApp / Telegram (áudio no bolso)
- [ ] Encadeamento de automações (gatilhos e tarefas autônomas)

---

## 📋 Decisões de Arquitetura

| Decisão | Escolha | Motivo |
|---|---|---|
| Nome | **Gideon** | Escolha do Henry (inspirado em *The Flash*) |
| Interação | **100% Voz Mãos-Livres** | Sem necessidade de teclado ou mouse no dia a dia |
| Transparência da Janela | `MOUSE_PASSTHROUGH = true` | Cliques do mouse atravessam o holograma; não atrapalha o uso do PC |
| Cérebro | Google Gemini (`gemini-3.1-flash-lite`) | Raciocínio de ponta, custo gratuito e respostas rápidas |
| Ouvido | Faster-Whisper (`base`, int8) | Transcrição local em português sem latência de rede |
| Voz | Microsoft Maria Desktop + Kokoro ONNX | Voz feminina natural rodando 100% no computador |
| Avatar 3D | Godot 4 | Janela transparente nativa no Windows, shaders cinematográficos, leve |
| Formato do Rosto | `.glb` (ARKit Blendshapes) | Padrão da indústria com sincronia labial e piscar natural |
| Memória | SQLite FTS5 Local | Fatos permanentes com busca insensível a acentos |
| Segurança | Cofre do Windows (`keyring`) + Token Local | Chaves e comandos protegidos localmente |

---

*Atualizado em: 24/10/2026 01:45*
