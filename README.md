# Gideon

Assistente pessoal local para Windows com cérebro Gemini, memória SQLite,
entrada e saída por voz e presença holográfica em Godot.

## Estado Atual

Este repositório ainda é um protótipo em desenvolvimento. O runtime supervisionado
já inicia backend e avatar como um conjunto, remove o overlay da barra de tarefas e
do Alt+Tab e permite encerramento/reinício direcionado. O rosto atual é provisório.

## Executar Pelo Projeto

```powershell
.\iniciar_gideon.bat
```

Para encerrar somente os processos pertencentes à Gideon:

```powershell
.\parar_gideon.bat
```

## Instalação no Windows

O instalador clona o repositório privado em
`%LOCALAPPDATA%\Programs\Gideon`, executa `uv sync --frozen` e registra uma tarefa
de inicialização no login do usuário. Ele não foi executado automaticamente.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\instalar_gideon.ps1
```

Depois da instalação, o código deixa de ocupar a pasta Documentos, mas continua
existindo na pasta de programas, como qualquer software instalado.

## Atualização

A atualização aceita somente avanço direto de `origin/master`, recusa alterações
locais, sincroniza o lockfile e executa o portão isolado do runtime.

```powershell
.\atualizar_gideon.bat
```

O fluxo de voz reconhece "Gideon, atualize seus sistemas", pede uma confirmação
separada e reinicia os componentes quando a atualização é validada.

## Painel Técnico

O painel é opcional. O comando abaixo abre uma sessão autenticada sem registrar o
token na URL HTTP ou no armazenamento JavaScript:

```powershell
uv run python -m gideon.painel
```

## Remoção

Por padrão, a desinstalação remove apenas a inicialização automática e preserva a
memória:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\desinstalar_gideon.ps1
```

`-ApagarMemoria` remove também a pasta instalada e deve ser usado somente depois
de exportar os dados importantes. A chave do Gemini no Credential Manager e o
acesso no provedor precisam ser removidos separadamente.

## Limite Técnico

O overlay pode ficar ausente da barra de tarefas e do Alt+Tab, mas os processos
continuam visíveis no Gerenciador de Tarefas. O projeto não usa técnicas de
ocultação de processo.
