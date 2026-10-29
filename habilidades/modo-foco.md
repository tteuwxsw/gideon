---
nome: modo-foco
descricao: Sessão de foco com fechamento seguro de distrações, um ciclo Pomodoro 25/5 e música de concentração
quando_usar: Henry disser "ativar modo foco", "iniciar foco", "começar Pomodoro" ou "sair do modo foco"
ferramentas: perfil_ler, perfil_adicionar_regra, listar_programas_usuario, fechar_programa, criar_lembrete, tocar_ou_pesquisar_midia, controlar_midia, automacao_listar, automacao_desligar
risco_maximo: A
criada_em: 2026-10-29 00:37
---

# Habilidade: Modo Foco

## Gatilhos de voz
- Ativar: "ativar modo foco", "iniciar foco", "quero me concentrar" ou "começar Pomodoro".
- Desfazer: "sair do modo foco", "encerrar foco", "cancelar Pomodoro" ou "parar modo foco".

## Ativação segura
1. Consultar `perfil_ler()` para procurar uma lista aprovada de aplicativos de distração. Se não houver lista configurada, perguntar quais aplicativos devem compor a lista nesta sessão; nunca adivinhar nem alterar o perfil automaticamente. Se o Henry pedir explicitamente para tornar a lista permanente, usar `perfil_adicionar_regra(secao='Preferências', regra='Aplicativos de distração do modo foco: <lista aprovada>')`.
2. Chamar `listar_programas_usuario()` e cruzar o resultado somente com a lista configurada.
3. Mostrar os aplicativos encontrados e pedir confirmação antes de fechá-los, pois pode haver trabalho não salvo. Nunca fechar a Gideon, terminal, editor ou outro aplicativo fora da lista.
4. Após a confirmação, chamar `fechar_programa(nome)` separadamente para cada aplicativo aprovado e relatar qualquer falha.
5. Criar um único ciclo Pomodoro persistente com `criar_lembrete`:
   - lembrete falado em "daqui a 25 minutos": "Fim do foco. Faça uma pausa de 5 minutos.";
   - lembrete falado em "daqui a 30 minutos": "Pausa encerrada. O ciclo Pomodoro terminou.".
6. Guardar na conversa os IDs retornados pelos dois lembretes para permitir o cancelamento.
7. Perguntar qual música, artista ou playlist de concentração o Henry prefere. Usar `tocar_ou_pesquisar_midia(consulta, plataforma='spotify')`; não escolher conteúdo sem uma preferência ou autorização.
8. Confirmar de forma curta que este é um ciclo de 25 minutos de foco e 5 minutos de pausa. Não prometer repetição automática.

## Como desfazer
1. Pausar a música com `controlar_midia(acao='pausar')`.
2. Desligar os dois lembretes pelos IDs guardados usando `automacao_desligar(id)`. Se os IDs não estiverem mais no contexto, chamar `automacao_listar()`, identificar apenas os dois lembretes desta sessão pelo nome/descrição e pedir confirmação antes de desligá-los.
3. Não tentar reabrir os aplicativos fechados: não existe estado confiável dos aplicativos anteriores nem garantia de restauração da sessão. Informar essa limitação.

Todas as ações no computador devem ocorrer pelas ferramentas catalogadas, respeitando o portão de risco e as permissões.
