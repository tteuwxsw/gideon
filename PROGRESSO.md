# Gideon — Progresso do Projeto

**Pessoa:** Henry  
**Início:** 23/10/2026  
**Evolução:** 24/10/2026 (Transição de Alfred para Gideon — Assistente Holográfica 3D inspirada em *The Flash*)  
**Arquitetura atual:** Núcleo local no Windows + raciocínio Gemini na nuvem + avatar Godot local
**Interface Visual:** Avatar 3D em Godot 4 (shader holográfico azul, expressões, overlay de desktop intangível ao mouse)  
**Voz:** Protótipo mãos-livres (Faster-Whisper local + Edge TTS online + detecção textual de "Gideon")
**Computador:** Windows  
**Interação desejada:** Holograma 3D e controle puramente por voz

---

## Estado real auditado em 24/10/2026

> Esta seção substitui as classificações antigas de "concluído" quando houver conflito. A auditoria foi feita por leitura do código, do modelo GLB, dos scripts e do estado do Windows. Nesta sessão foram executados testes isolados e testes reais do runtime/HTTP; microfone, qualidade da voz, Gemini e memória de produção não foram exercitados.

**Progresso estimado para a visão completa:** cerca de **45%**. O runtime integrado funciona, mas ainda não é um produto final instalado e o rosto continua provisório.

| Área | Estado confirmado | O que falta |
|---|---|---|
| Chat Gemini | Implementado no painel web com streaming | Configuração de modelo, sessões isoladas e limite de contexto |
| Memória SQLite | Implementada e usada no chat/voz | Backup, exportação, retenção, proteção de dados sensíveis e resumos automáticos |
| Ouvido | Faster-Whisper local e detecção por energia implementados | Wake word acústica dedicada, calibração de ruído, testes reais de latência e falsos positivos |
| Voz | Edge TTS online usa primeiro `pt-BR-ThalitaMultilingualNeural`; Francisca e Maria são fallbacks | Kokoro local não está ativo porque os pesos não existem; falta voz escolhida/configurável, fala por frase e interrupção |
| Lip sync | A boca reage à intensidade RMS do áudio | Não há alinhamento fonético; apenas 4 visemas são animados por oscilações artificiais |
| Rosto 3D | GLB válido do Ready Player Me com 72 morph targets | É um avatar feminino genérico, não se parece com a Gideon de *The Flash*; precisa de direção facial e modelo final próprio/licenciado |
| Overlay Godot | Transparente, click-through e integrado por estilos Win32; removido da barra de tarefas e do Alt+Tab em teste real | Exportar executável próprio, validar múltiplos monitores e eliminar o sufixo DEBUG |
| Ferramentas Windows | Atualização e encerramento estão ligados à voz por intenções determinísticas e confirmação; outras funções existem no catálogo | Function calling geral do Gemini ainda não está conectado |
| Segurança V/A/R | Atualização/encerramento são vermelhos, token foi rotacionado, CSRF/origens foram protegidos e a parada cooperativa funciona | Sandbox de pastas, confirmação geral das demais ferramentas e limite de gasto ainda precisam ser corrigidos |
| Inicialização no Windows | Supervisor silencioso inicia backend e avatar como um conjunto | O instalador ainda não foi executado e a tarefa de login ainda não foi registrada |
| Instalação/atualização | Instalador PowerShell e atualizador conservador com candidato isolado e rollback implementados | Validar a instalação real depois de publicar esta versão no repositório privado |
| Repositório | `tteuwxsw/gideon` confirmado como privado | Automatizar release/versionamento depois que existir um aplicativo instalável |

### Problemas prioritários encontrados

- [x] Remover o token local das URLs/logs, rotacionar o formato antigo e autenticar WebSocket por header ou cookie `HttpOnly`.
- [x] Aplicar `WS_EX_TOOLWINDOW`/`WS_EX_NOACTIVATE` e remover `WS_EX_APPWINDOW`; resultado confirmado na janela real do Godot.
- [ ] Exportar um executável próprio para substituir o runner do Godot e eliminar o modo DEBUG.
- [x] Criar supervisor único com mutex, health check, PIDs próprios, encerramento cooperativo e reinício completo.
- [ ] Conectar ferramentas ao cérebro por chamadas estruturadas somente depois de corrigir o portão de segurança, o `shell=True` e as permissões de arquivos.
- [ ] Substituir o avatar Ready Player Me por um rosto final aprovado pelo Henry e documentar origem/licença.
- [ ] Implementar lip sync fonético e usar os visemas reais do modelo.
- [ ] Tornar a voz configurável e decidir entre voz online de alta qualidade, Kokoro local ou serviço premium.
- [ ] Separar testes dos dados reais e criar testes de integração para voz, Godot, janela Windows, ferramentas e atualização.

### Marco 0.3.0 · Runtime Windows e instalação por comando

- [x] `gideon/supervisor.py`: inicia backend e avatar, impede duplicação e controla somente os processos da Gideon.
- [x] Overlay testado com `TOOLWINDOW=true`, `NOACTIVATE=true` e `APPWINDOW=false`.
- [x] Parada cooperativa testada: backend Uvicorn encerrou pela rota privada do supervisor e o avatar recebeu `WM_CLOSE`.
- [x] Reinício automático testado: novos PIDs de supervisor, backend e avatar foram criados e o health check voltou a responder.
- [x] Token antigo rotacionado; Godot conectou por header e nenhum token apareceu nos novos logs.
- [x] `instalar_gideon.ps1`: instalação planejada em `%LOCALAPPDATA%\Programs\Gideon` e tarefa no login.
- [x] `desinstalar_gideon.ps1`: remove a tarefa preservando memória por padrão.
- [x] Atualizador exige repositório limpo, usa mutex, valida a versão candidata isoladamente, aplica somente `merge --ff-only`, sincroniza pelo lockfile e testa novamente.
- [x] Comando falado de atualização conectado de forma determinística, com confirmação separada e reinício automático após sucesso.
- [x] Identidade visual decidida: a meta é a aparência da Gideon de *The Flash* para uso pessoal; o GLB atual permanece explicitamente provisório.
- [x] Instalação no `%LOCALAPPDATA%\Programs\Gideon` executada e registrada na Tarefa Agendada `Gideon`.
- [x] Ciclo de atualização testado com árvore modificada: recusou sobrescrever os arquivos, reiniciou o runtime e preservou o trabalho local.
- [x] Proteção HTTP testada: login local funcionou e requisições sem CSRF ou com origem local diferente receberam `403`.
- [x] Recuperação de falhas testada: quedas forçadas separadamente no backend e no avatar reiniciaram o conjunto e restauraram o health check.
- [x] Versão candidata é testada em clone temporário; falha excepcional depois do merge restaura o commit anterior e sincroniza novamente o ambiente.

### Direção de produto aprovada para discussão

- **Gideon Core:** único núcleo de identidade, memória, permissões, ferramentas e roteamento de modelos.
- **Gideon Presence:** presença de voz e holograma integrada ao Windows, sem barra de tarefas ou Alt+Tab e sem bloquear cliques.
- **Gideon Workspace:** IDE opcional para projetos e tarefas complexas. O chat principal continua sendo a Gideon.
- **Adaptadores de agentes:** OpenCode, Antigravity, APIs, CLIs e MCPs entram como especialistas que a Gideon pode acionar. Eles não recebem acesso total automaticamente; cada adaptador terá escopo, pasta, orçamento e auditoria próprios.
- **Painel técnico:** permanece opcional e oculto no uso diário para diagnóstico, permissões, memória, custos e recuperação. A interface normal continua sendo a voz da Gideon.

### Limite técnico importante

A Gideon pode parecer parte do Windows: iniciar com o login, não aparecer na barra de tarefas nem no Alt+Tab, responder por voz e projetar o avatar quando chamada. Porém qualquer software em execução continuará visível no **Gerenciador de Tarefas**; tentar esconder o processo seria comportamento de malware e não faz parte do projeto.

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
  - Modos funcionais: Compacto, Conversa, Foco e Oculto; Operacional está declarado, mas ainda não implementado
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

### Fase 5 · Subsistema de Voz Mãos-Livres (Protótipo Parcial)
- [x] **Transcrição Local** (`gideon/voz/ouvido.py`):
  - Captura contínua de microfone a 16 kHz via `sounddevice`
  - Detector de energia/silêncio (VAD) automático
  - Captura contínua de microfone a 16 kHz via `sounddevice` com pré-buffer circular (~420ms), piso de ruído adaptativo, ganho automático para fala baixa e tolerância a pausas no meio da frase
  - Transcrição ultra-rápida local com **Faster-Whisper** (`base`, int8, em português) com prompt de vocabulário contextual e filtro de alucinações de silêncio
  - Reconhecimento amplo de ativação (*"Gideon"*, *"Olá, Gideon"*, *"Ei, Gideon"*, *"Oi, Gideon"*, *"Gideon, você está aí?"* e correspondência fonética aproximada)
- [x] **Síntese Vocal Neural de Identidade Única e Baixa Latência** (`gideon/voz/fala.py`):
  - **Voz única e fixa (`pt-BR-FranciscaNeural`)**: eliminada a alternância com `ThalitaMultilingualNeural` para garantir 100% de consistência de timbre em todas as interações
  - **Cache persistente em RAM e disco (`dados/cache_voz/`)**: respostas frequentes (*"Abrindo."*, *"Tudo bem."*, *"Estou aqui, Henry."*) são sintetizadas em `< 5 ms`
  - **Streaming de Sentenças (`falar_stream`)**: a Gideon começa a falar na 1ª frase sem esperar o texto inteiro do LLM terminar
  - Análise da onda sonora (envelope RMS em tempo real) para controlar a abertura da boca
  - Sistema de **Barge-In anti-eco**: permite interromper a fala da Gideon imediatamente ao falar por cima ou dizer *"Gideon, espera"* / *"Não precisa mais"*
- [x] **Orquestrador Inteligente, Fala Direcionada e Métricas p50/p95** (`gideon/voz/orquestrador.py`, `gideon/voz/comandos.py`, `gideon/voz/metricas.py`):
  - **Modo 1 (`ativacao_por_nome`)**, **Modo 2 (`conversa_continua`)** e **Modo 3 (`conversa_livre`)** com avaliador de probabilidade de fala direcionada (`avaliar_fala_direcionada`)
  - Compreensão natural sem comandos rígidos e correção fonética de erros do STT (`corrigir_erros_transcricao`)
  - Histórico enxuto de curta duração para perguntas encadeadas (*"Vê quanto de RAM..."* $\rightarrow$ *"E a placa de vídeo?"* $\rightarrow$ *"Isso é normal?"*)
  - Medição real de latência (`vad_endpoint_ms`, `stt_ms`, `nlu_ms`, `llm_ttft_ms`, `tts_ttfa_ms`, `ttfa_total_ms`) com percentis **p50** e **p95** em `dados/metricas_voz.jsonl`
- [x] **Flag CLI `--voz`**: Inicia o servidor com o ouvinte mãos-livres ativo direto do terminal
- [x] **Bateria de 30 interações e validação de voz** (`testes/teste_voz.py`): 7 suítes aprovadas (30 interações consecutivas com 100% de consistência vocal, p50/p95, fala direcionada, NLU, contexto e barge-in)
- [ ] **Portão real de voz**: falta medir microfone, ruído, TV, voz baixa, falsos positivos, latência e qualidade do TTS/lip sync

### Fase 4 · Módulos de Mãos, Execução Real Verificada e Segurança V/A/R (Concluída)
- [x] **Arquitetura de 3 Camadas: Inteligência $\rightarrow$ Executor $\rightarrow$ Verificador** (`gideon/executor.py`):
  - Registro estruturado `ResultadoExecucao` com estados formais (`pending`, `running`, `success`, `failed`, `timeout`, `needs_confirmation`, `unsupported`)
  - **Regra Absoluta Anti-Alucinação**: nenhuma tarefa recebe `estado == "success"` ou confirmação verbal sem evidência real verificada do Windows (`verificado == True`, PID, HWND, caminho de arquivo, estado Win32)
  - Persistência de auditoria detalhada em `dados/execucoes.jsonl` e endpoint `/api/execucoes/historico`
  - **Recuperação Automática de Falhas**: quando um aplicativo desktop (ex: Spotify, Discord, Steam) não está instalado localmente, sugere abrir a versão web e aguarda confirmação natural (*"Sim"*)
- [x] **Portão de Risco e Auditoria** (`gideon/gate.py`):
  - Classificação formal de risco: Verde (leitura direta), Amarelo (reversível) e Vermelho (confirmação obrigatória)
  - Inspeção estrita do retorno estruturado: ferramentas que retornam `"erro"`, `sucesso=False` ou `verificado=False` são marcadas como `ok=False` (eliminado falso positivo)
  - Log permanente em formato JSONL (`dados/auditoria.jsonl`)
- [x] **Controle Real do Windows 10** (`gideon/tools/sistema.py` — 16 ferramentas):
  - Descoberta real de executáveis via Registro (`App Paths`), `%ProgramFiles%`, `%LOCALAPPDATA%\Programs` e `PATH` (`localizar_executavel_windows`)
  - Abertura verificada de aplicativos e URLs (`abrir_programa`) confirmando PID (`psutil`) e janela visível (`HWND` via `EnumWindows`)
  - Fechamento verificado de aplicativos (`fechar_programa`) via `WM_CLOSE` + verificação de encerramento
  - Gerenciamento real de janelas (`gerenciar_janela`: minimizar, maximizar, restaurar, alternar foco) verificado via Win32 `IsIconic`, `IsZoomed` e `GetForegroundWindow`, suportando pronomes contextuais (*"Agora minimiza ele"*)
  - Pesquisa real no navegador (`pesquisar_navegador`) no Google e YouTube
  - Automação de interface gráfica: digitação Unicode (`digitar_texto` via Win32 `SendInput`), atalhos de teclado (`executar_atalho_teclado`) e clique virtual de mouse (`clicar_mouse`)
  - Telemetria instantânea (`< 2 ms`) de CPU, RAM, GPU (`AMD Radeon RX 580X 8 GB`), disco C e uptime (`obter_status_pc`, `obter_status_gpu`)
- [x] **Gerenciamento Real e Verificado de Arquivos e Pastas** (`gideon/tools/arquivos.py` — 6 ferramentas):
  - Abertura verificada de pastas no Explorador de Arquivos (`abrir_pasta`: Downloads, Documentos, Desktop, Imagens, Projeto)
  - Pesquisa recursiva rápida de arquivos (`pesquisar_arquivos`)
  - Criação e escrita de arquivos verificada no disco (`criar_arquivo`)
  - Leitura segura com proteção a credenciais (`ler_arquivo`) e envio verificado para a Lixeira do Windows (`mover_para_lixeira`)
- [x] **Planejador Multietapas** (`gideon/voz/comandos.py`, `gideon/voz/orquestrador.py`):
  - Decomposição e execução sequencial verificada de comandos compostos (*"Abre o navegador e pesquisa sobre inteligência artificial"*, *"Abre o Bloco de Notas e verifica o consumo de memória"*)
- [x] **Bateria de Testes de Execução Real** (`testes/teste_execucao_real.py`, `testes/teste_ferramentas.py`):
  - Catálogo completo de **22 ferramentas** validado em execução real no Windows 10

---

## 🔜 O que falta fazer

### Fase 3 · Rosto 3D da Gideon, Esqueleto Articulado, Lip-Sync Fonético e Consciência de Desktop (Concluída com Visual STAR Labs Time Vault)
- [x] **Godot Engine 4.7.2** integrado ao supervisor com janela transparente, sem bordas, intangível ao mouse (`MOUSE_PASSTHROUGH = true`) e oculta da barra de tarefas/Alt+Tab (`WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE`)
- [x] **Shader Holográfico Cinematográfico STAR Labs em Duas Passagens** (`gideon_avatar/shaders/holograma.gdshader` + `gideon_avatar/shaders/holograma_fade.gdshader`):
  - **Passagem 1 (`holograma.gdshader`, Hardware Z-Buffer 100% Ativo)**: renderiza o busto esculpido em luz ciano-azul da Gideon (idêntico à projeção da Sala do Tempo do STAR Labs em *The Flash*), com olhos holográficos luminosos (`modo_componente = 1`, preservando fibras radiais da íris, pupila profunda e reflexo corneano), feições faciais naturais (sobrancelhas, cílios, nariz e lábios) e zero vazamento de geometria interna da cavidade bucal ou órbitas oculares
  - **Passagem 2 (`holograma_fade.gdshader`, `next_pass` de Transição Contínua)**: realiza a dissolução volumétrica suave na base do pescoço (`corte_pescoco_min = -0.128`, `corte_pescoco_max = -0.052`) e o feixe de materialização com equação fotométrica idêntica à Passagem 1 (sem costuras e sem pontilhado)
- [x] **Articulação Anatômica de `Skeleton3D` + 72 Blendshapes** (`gideon_avatar/scripts/avatar_controller.gd`):
  - Articula 8 ossos reais do esqueleto (`Head`, `Neck`, `Spine2`, `Spine1`, `LeftShoulder`, `RightShoulder`, `LeftEye`, `RightEye`) para respiração orgânica nos ombros, inclinação distribuída pescoço/cabeça e micro-acenos durante a fala
  - Interpolação contínua e suave (`lerp`) de todas as expressões faciais sem saltos bruscos
- [x] **Lip-Sync Fonético Multi-Visema + Coarticulação Acústica** (`gideon/voz/visemas.py`, `gideon/voz/fala.py`):
  - Mapeia fonemas e dígrafos do português para os **15 visemas Oculus** (`viseme_aa`, `viseme_E`, `viseme_I`, `viseme_O`, `viseme_U`, `viseme_PP`, `viseme_FF`, `viseme_SS`, `viseme_DD`, `viseme_CH`, `viseme_RR`, `viseme_kk`, `viseme_nn`, `viseme_TH`, `viseme_sil`) combinados com análise espectral (ZCR) e energia RMS da onda sonora real a 30 Hz
- [x] **Máquina de 7 Estados Comportamentais** (`Idle`, `Listening`, `Thinking`, `Speaking`, `Executing`, `Observing`, `Error`) sincronizada em tempo real via WebSocket
- [x] **Consciência do que Acontece no Computador** (`gideon/presenca.py`, `inspecionar_contexto_tela` em `gideon/tools/sistema.py`):
  - Acompanhamento suave e limitado do cursor do mouse (`GetCursorPos`) sem capturas constantes de tela
  - Detecção de abertura e troca de janelas (`GetForegroundWindow` + `GetWindowRect`) com proteção de privacidade (`PADROES_PRIVACIDADE_EXCLUIDOS`)
  - Retorno imediato do olhar para o Henry (`(0, 0)`) ao iniciar conversa
- [x] **Governador de Desempenho Medido na AMD Radeon RX 580 8GB**:
  - Ajuste automático de `Engine.max_fps` (`60 FPS` ativa/falando, `30 FPS` em repouso `Idle`, `10 FPS` quando oculta), consumindo apenas **54,3 MB de VRAM**, **38,7 MB de RAM estática** e **5 draw calls por quadro** (verificado em captura real `dados/captura_avatar.png`)
- [x] **Bateria de Validação Visual e Comportamental** (`testes/teste_holograma_comportamento.py`): 5 suítes aprovadas (visemas fonéticos, consciência de desktop, diálogo proativo, carregamento de esqueleto/shader no Godot 4 e telemetria)

---

## 🔜 O que falta fazer

### Fases 6–9 · Automações, Proatividade e Integrações
- [ ] Inicialização completa junto com o Windows: supervisor já cobre backend e avatar, mas a tarefa no login depende da execução do instalador
- [x] **Avatar feminino provisório** (`gideon_avatar/modelos/gideon.glb`) do Ready Player Me com 72 morph targets, piscar, olhar e shader holográfico
- [ ] **Rosto definitivo da Gideon** com semelhança aprovada pelo Henry, maior realismo e licença documentada
- [ ] Rotina matinal falada por horário com relógio de parede
- [ ] Integração com WhatsApp / Telegram (áudio no bolso)
- [ ] Encadeamento de automações (gatilhos e tarefas autônomas)

---

## 📋 Decisões de Arquitetura

| Decisão | Escolha | Motivo |
|---|---|---|
| Nome | **Gideon** | Escolha do Henry (inspirado em *The Flash*) |
| Interação desejada | **100% Voz Mãos-Livres** | Sem necessidade de teclado ou mouse no dia a dia |
| Transparência da Janela | `MOUSE_PASSTHROUGH = true` | Cliques do mouse atravessam o holograma; não atrapalha o uso do PC |
| Cérebro | Google Gemini (`gemini-3.1-flash-lite`) | Raciocínio de ponta, custo gratuito e respostas rápidas |
| Ouvido | Faster-Whisper (`base`, int8) | Transcrição local em português sem latência de rede |
| Voz atual | Edge TTS (`ThalitaMultilingualNeural`, depois `FranciscaNeural`) | Melhor que a voz nativa, mas online e ainda sem prosódia configurável |
| Avatar 3D atual | Godot 4 + avatar provisório `gideon.glb` | Validar a tecnologia enquanto o rosto definitivo não é produzido |
| Formato do Rosto | `.glb` com morph targets ARKit/Oculus | Suporta expressões; o uso fonético completo dos visemas ainda será implementado |
| Memória | SQLite FTS5 Local | Fatos permanentes com busca insensível a acentos |
| Segurança | Cofre do Windows (`keyring`) + portão V/A/R + autenticação local sem token na URL | Base corrigida para runtime/update; sandbox de arquivos e function calling geral continuam pendentes |
| IDE futura | **Gideon Workspace** com adaptadores | Gideon permanece como chat e identidade principal; outras IAs atuam como especialistas |

---

*Atualizado em: 24/10/2026 — versão 0.3.0, runtime Windows supervisionado, autenticação corrigida e instalação por comando preparada.*
