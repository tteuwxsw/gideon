---
nome: dev
descricao: Diagnóstico cuidadoso de erros de terminal colados, ditados ou visíveis na tela
quando_usar: Henry disser "modo dev", "explique este erro", "analise este erro do terminal", "por que isso falhou" ou "sair do modo dev"
ferramentas: analisar_tela
risco_maximo: V
criada_em: 2026-10-29 00:37
---

# Habilidade: Dev

## Gatilhos de voz
- Ativar: "modo dev", "explique este erro", "analise este erro do terminal" ou "por que isso falhou".
- Desfazer: "sair do modo dev", "parar análise" ou "cancelar diagnóstico".

## Procedimento
1. Priorizar o texto que o Henry colar ou ditar. Preservar a mensagem de erro, nomes de exceções, arquivo, linha, comando e primeiras causas da pilha.
2. Se não houver texto e o Henry pedir explicitamente para ler o terminal visível, chamar `analisar_tela(pergunta='Leia somente a mensagem de erro e o traceback visíveis no terminal, sem expor outros dados da tela.')`.
3. Antes de analisar, alertar e pedir uma versão saneada se o conteúdo aparentar conter senha, token, chave, cookie ou outra credencial. Nunca repetir segredos na resposta ou em logs.
4. Responder em quatro partes curtas:
   - erro principal observado;
   - causa provável, distinguindo fato de hipótese;
   - uma correção mínima sugerida;
   - como verificar se a correção funcionou.
5. Se faltarem contexto, versões ou linhas anteriores, pedir exatamente o dado necessário. Não inventar arquivo, dependência, comando ou saída.
6. Não executar comandos, editar arquivos nem controlar o terminal. Esta habilidade apenas explica. Se uma correção sugerida for destrutiva, deixar isso explícito e não orientar sua execução sem confirmação e ferramenta apropriada.

## Como desfazer
Ao ouvir um gatilho de saída, encerrar o diagnóstico e descartar apenas o contexto temporário da análise na conversa. Nenhuma ação de sistema precisa ser revertida.
