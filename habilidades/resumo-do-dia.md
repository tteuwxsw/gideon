---
nome: resumo-do-dia
descricao: Resumo falado e honesto do que foi feito e das pendências encontradas em lembretes e memória
quando_usar: Henry disser "resumo do dia", "como foi meu dia", "o que fiz hoje", "o que falta hoje" ou "parar resumo"
ferramentas: automacao_listar, memoria_buscar
risco_maximo: V
criada_em: 2026-10-29 00:37
---

# Habilidade: Resumo do Dia

## Gatilhos de voz
- Ativar: "resumo do dia", "como foi meu dia", "o que fiz hoje" ou "o que falta hoje".
- Desfazer/interromper: "parar resumo", "cancelar resumo" ou "chega de resumo".

## Procedimento
1. Chamar `automacao_listar()` e considerar como pendências somente lembretes ou automações que os dados retornados identifiquem como ativos. Não tratar toda automação cadastrada como tarefa de hoje.
2. Chamar `memoria_buscar(termo='hoje', limite=10)`. Se a busca não trouxer contexto suficiente, fazer buscas curtas e separadas por "feito", "concluído" e "pendente", sem inventar acontecimentos.
3. Separar os achados em:
   - **Feito:** apenas fatos que a memória sustenta claramente;
   - **Falta:** lembretes ativos e pendências explícitas;
   - **Sem confirmação:** itens ambíguos, que devem ser apresentados como pergunta, não como fato.
4. Produzir resposta adequada à voz, com no máximo 5 frases: uma abertura, feitos principais, pendências e uma pergunta final opcional.
5. Se não houver dados, dizer claramente que não há registros suficientes para reconstruir o dia. Nunca preencher lacunas por suposição.

## Como desfazer
Esta habilidade não altera o computador nem mantém modo persistente. Ao ouvir um gatilho de interrupção, parar a recapitulação e apenas confirmar o cancelamento; não chamar ferramentas adicionais.
