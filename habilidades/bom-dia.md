---
nome: bom-dia
descricao: Rotina matinal inteligente com telemetria do computador, pendências e resumo falado
quando_usar: Henry pede para configurar a rotina da manhã ou quer um resumo matinal
ferramentas: obter_status_pc, obter_status_gpu, perfil_ler, criar_lembrete
risco_maximo: V
criada_em: 2026-10-25 11:45
---

# Habilidade: Bom dia da Gideon (Rotina Matinal)

Esta habilidade ensina a Gideon a executar ou estruturar a automação matinal perfeita para o Henry.

## O que fazer
1. Consultar a telemetria do computador através de `obter_status_pc()` e `obter_status_gpu()`.
2. Verificar se o Henry possui regras ou preferências ativas no `perfil_ler()`.
3. Montar uma saudação elegante, concisa e calorosa em português do Brasil:
   - Dizer o horário atual e desejar um bom dia.
   - Resumir em 1 frase como o PC acordou (uso de memória, CPU e espaço livre no disco C).
   - Se houver lembretes ou tarefas marcadas para hoje, mencionar brevemente.
4. Resposta falada deve ser curta (máximo 2 a 3 sentenças) para manter fluidez auditiva.

## Para transformar em Automação Permanente
Se o Henry pedir para rodar todo dia:
1. Criar automação com gatilho `horario`: `{"tipo": "horario", "hora": "08:00", "dias": ["seg","ter","qua","qui","sex"]}`.
2. Passo 1: ferramenta `obter_status_pc`, salvar como `pc`.
3. Passo 2: pensar `Faça um bom-dia caloroso e curto para o Henry usando as informações de {{pc}}. Máximo 2 frases.`, salvar como `fala`.
4. Passo 3: avisar `mensagem: {{fala}}, falar: true`.
5. Apresentar desligada e testar em simulação antes de pedir para ligar.
