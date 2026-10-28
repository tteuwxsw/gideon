---
nome: faxina-pastas
descricao: Faxina segura da pasta Downloads e Desktop sem jamais excluir arquivos em definitivo
quando_usar: Henry pede para organizar ou limpar a pasta Downloads ou Área de Trabalho
ferramentas: listar_arquivos, pesquisar_arquivos, mover_para_lixeira, abrir_pasta
risco_maximo: A
criada_em: 2026-10-25 11:45
---

# Habilidade: Faxina Segura de Pastas

Regra da especificação (seção 6): Apagar = Mover para a Lixeira do Windows.
Nunca realizar exclusão definitiva no computador do Henry.

## Procedimento Seguro
1. Chamar `listar_arquivos(pasta='downloads', limite=30)` para inspecionar os arquivos existentes.
2. Agrupar os arquivos por tipo (instaladores .exe/.msi, documentos .pdf/.docx, compactados .zip/.rar, imagens).
3. Apresentar ao Henry o plano claro do que foi encontrado antes de agir.
4. Para itens que ele pedir para limpar, usar `mover_para_lixeira(caminho)` (ação amarela reversível).
5. Relatar quantos arquivos foram movidos para a Lixeira e confirmar que todos permanecem restauráveis caso precise.
