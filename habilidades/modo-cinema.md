---
nome: modo-cinema
descricao: Ajuste conservador de áudio para assistir a filmes, com aviso explícito sobre controles indisponíveis
quando_usar: Henry disser "ativar modo cinema", "hora do filme", "preparar para assistir" ou "sair do modo cinema"
ferramentas: controlar_som_sistema
risco_maximo: A
criada_em: 2026-10-29 00:37
---

# Habilidade: Modo Cinema

## Gatilhos de voz
- Ativar: "ativar modo cinema", "hora do filme" ou "preparar para assistir".
- Desfazer: "sair do modo cinema", "desativar modo cinema" ou "restaurar modo cinema".

## Limitação obrigatória
O catálogo atual não possui ferramentas para ajustar brilho, ler o brilho atual, pausar notificações ou ativar o modo Não Perturbe. Não executar comandos de sistema por conta própria, não usar atalhos como substituto e não afirmar que esses ajustes foram feitos. Informar a limitação e listar as ferramentas ausentes.

## Ativação disponível
1. Explicar que apenas o volume pode ser ajustado com segurança neste momento.
2. Perguntar quantos níveis o Henry quer diminuir; se ele não escolher, oferecer 3 níveis como padrão, sem executar antes da autorização.
3. Após a autorização, chamar `controlar_som_sistema(acao='diminuir', toques=<níveis>)` e guardar na conversa a quantidade aplicada.
4. Relatar o resultado real. Não afirmar um percentual final, pois a ferramenta só faz ajuste relativo e não lê o volume atual.

## Como desfazer
1. Se a quantidade aplicada ainda estiver no contexto, chamar `controlar_som_sistema(acao='aumentar', toques=<mesmos níveis>)`.
2. Se o estado tiver sido perdido, não adivinhar o volume anterior; perguntar ao Henry qual ajuste deseja.
3. Explicar que brilho e notificações não foram alterados, portanto não há o que restaurar nesses itens.

Todas as ações no computador devem ocorrer pela ferramenta catalogada, respeitando o portão de risco e as permissões.
