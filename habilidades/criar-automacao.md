---
nome: criar-automacao
descricao: Como arquitetar, estruturar, testar em simulação e ligar automações seguras para o Henry
quando_usar: Henry pede para automatizar tarefas repetitivas, rotinas ou ações disparadas por eventos
ferramentas: automacao_criar, automacao_testar, automacao_ligar, automacao_listar, ajuda_criar
risco_maximo: A
criada_em: 2026-10-25 11:45
---

# Habilidade: Construção Segura de Automações

Regra de ouro da especificação ALFRED-PARA-O-CLAUDE (seção 18):
A meta da Gideon é operar o computador pelo Henry. Ela não só responde, ela monta e encadeia o que falta.

## Passos para Criar uma Automação
1. **Entenda o objetivo e o gatilho**:
   - Qual a frequência?
     * `horario`: horário fixo (ex: 08:30) com dias da semana.
     * `intervalo`: a cada X minutos (mínimo 5 min).
     * `uma_vez`: momento específico futuro (AAAA-MM-DDTHH:MM).
     * `data`: evento anual (ex: aniversários em dia/mês).
     * `evento`: quando outra automação ou sistema emitir um evento nominal.
     * `manual`: disparada sob demanda.
2. **Defina os passos atômicos**:
   - Passo `ferramenta`: executa ferramenta do catálogo autorizado e pode salvar saída com `salvar_como`.
   - Passo `pensar`: usa o cérebro para analisar, resumir ou filtrar dados de terceiros.
   - Passo `avisar`: entrega notificação na tela e opcionalmente em voz (`falar: true`).
   - Passo `automacao`: chama outra automação existente.
   - Passo `emitir`: dispara eventos nominais.
3. **Segurança Obrigatória**:
   - Toda automação nasce DESLIGADA (`ativa: false`).
   - Sem ninguém olhando, ferramentas vermelhas só rodam se estiverem declaradas em `permite`.
   - Chamar `automacao_testar(id)` em modo simulação primeiro para mostrar o resultado ao Henry.
   - Só chamar `automacao_ligar(id)` após o Henry confirmar expressamente.
