---
nome: lembretes
descricao: Lembretes confiáveis baseados em relógio de parede que sobrevivem à suspensão do computador
quando_usar: Henry pede para lembrá-lo de algo em um horário ou daqui a alguns minutos/horas
ferramentas: criar_lembrete, automacao_listar, automacao_desligar
risco_maximo: A
criada_em: 2026-10-25 11:45
---

# Habilidade: Lembretes por Relógio de Parede

Regra da especificação (seção 5, Fase 7):
Lembretes usam relógio de parede (comparação contínua da hora real do sistema), NUNCA timers `sleep`, porque o computador dorme e suspende.

## Procedimento
1. Usar a ferramenta direta `criar_lembrete(mensagem, quando, falar=True)`.
2. O parâmetro `quando` aceita:
   - Tempo relativo: "daqui a 15 minutos", "em 2 horas".
   - Horário no mesmo dia ou próximo: "às 16:30", "às 09:00".
   - Data ISO: "2026-10-25T17:00:00".
3. Ao disparar, o motor de automações avisa na tela e reproduz a fala em voz alta via sintetizador.
4. Para consultar lembretes pendentes, chamar `automacao_listar()`.
