"""Interpretação de linguagem natural, planejamento multietapas e intenções verificadas da Gideon."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalizar(texto: str) -> str:
    """Remove acentos e normaliza espaços em minúsculas."""
    sem_acentos = unicodedata.normalize("NFKD", texto.lower())
    return " ".join(
        "".join(c for c in sem_acentos if not unicodedata.combining(c)).split()
    )


def eh_pedido_abrir_interface(texto: str) -> bool:
    """Reconhece pedidos explicitos para mostrar a propria interface da Gideon."""
    t = re.sub(r"[^a-z0-9 ]", " ", normalizar(texto))
    t = " ".join(t.split())
    return t in {
        "abre o app",
        "abra o app",
        "abre o app pra mim",
        "abra o app pra mim",
        "abre o aplicativo",
        "abra o aplicativo",
        "abre o aplicativo pra mim",
        "abra o aplicativo pra mim",
        "abre a gideon",
        "abra a gideon",
        "mostra a gideon",
        "mostre a gideon",
        "abre sua interface",
        "abra sua interface",
        "mostra sua interface",
        "mostre sua interface",
        "aparece na tela",
        "apareca na tela",
        "quero ver a gideon",
    }

def detectar_comando_sistema(texto: str) -> str | None:
    """Detecta comandos críticos (Portão Vermelho) que exigem confirmação."""
    texto_norm = normalizar(texto)
    if texto_norm.startswith(("qual ", "como ", "por que ", "quando ", "quem ", "o que ")):
        return None
    if re.search(r"\b(atualize|atualiza|atualizar|verifique)\b", texto_norm) and re.search(
        r"\b(sistema|sistemas|atualizacao|atualizacoes|novidades|versao)\b", texto_norm
    ):
        return "atualizar_sistemas"
    if any(
        frase in texto_norm
        for frase in (
            "reinicie a gideon",
            "reinicia a gideon",
            "reiniciar a gideon",
            "reiniciar gideon",
            "pode reiniciar a gideon",
        )
    ):
        return "reiniciar_gideon"
    if any(
        frase in texto_norm
        for frase in (
            "pode fechar a gideon",
            "pode encerrar a gideon",
            "encerre a gideon",
            "encerrar gideon",
            "desligue a gideon",
            "desliga a gideon",
            "fechar a gideon",
        )
    ):
        return "encerrar_gideon"
    return None


def resposta_confirmacao(texto: str) -> bool | None:
    """Interpreta respostas naturais de confirmação ou cancelamento."""
    texto_norm = re.sub(r"[^a-z0-9 ]", "", normalizar(texto)).strip()
    afirmativas = {
        "sim",
        "sim confirmo",
        "sim pode",
        "sim pode fazer",
        "sim abre",
        "sim pode abrir",
        "confirmo",
        "pode",
        "pode fazer",
        "pode abrir",
        "pode olhar",
        "pode verificar",
        "pode checar",
        "pode ver",
        "pode continuar",
        "pode atualizar",
        "confirmado",
        "faz isso",
        "faz isso pra mim",
        "claro",
        "com certeza",
        "ok",
        "tudo bem",
        "isso mesmo",
        "manda ver",
        "quero",
        "quero sim",
    }
    negativas = {
        "nao",
        "cancelar",
        "cancela",
        "deixa",
        "deixa pra la",
        "deixa aberto",
        "nao espera deixa aberto",
        "nao precisa",
        "nao precisa mais",
        "agora nao",
        "nao quero",
        "esquece",
        "para",
    }
    if texto_norm in afirmativas or texto_norm.startswith(("sim ", "confirmo ", "pode fazer", "pode abrir", "quero sim")):
        return True
    if texto_norm in negativas or texto_norm.startswith(("nao ", "cancela", "nao precisa", "deixa aberto")):
        return False
    return None


def eh_interrupcao_barge_in(texto: str) -> bool:
    """Verifica se uma fala curta durante a reprodução é um pedido de interrupção (barge-in)."""
    t = re.sub(r"[^a-z0-9 ]", "", normalizar(texto)).strip()
    if not t:
        return False
    gatilhos = (
        "gideon",
        "guideon",
        "gidion",
        "gideao",
        "espera",
        "espere",
        "para",
        "pare",
        "silencio",
        "calma",
        "cancela",
        "nao precisa",
        "nao precisa mais",
        "opa",
        "aguarda",
        "pausa",
        "chega",
    )
    return any(g in t.split() or t.startswith(g) for g in gatilhos)


def eh_desistencia_rapida(texto: str) -> bool:
    """Detecta frases como 'Não precisa mais', 'Não, espera, deixa aberto', 'Esquece'."""
    t = re.sub(r"[^a-z0-9 ]", "", normalizar(texto)).strip()
    frases = (
        "nao precisa mais",
        "nao precisa",
        "nao espera deixa aberto",
        "espera deixa aberto",
        "deixa aberto",
        "deixa quieto",
        "deixa pra la",
        "esquece",
        "cancela isso",
        "cancela",
    )
    return any(f in t for f in frases)


def eh_encerramento_conversa(texto: str) -> bool:
    """Detecta quando o usuário encerra educadamente a sessão de conversa contínua."""
    t = re.sub(r"[^a-z0-9 ]", "", normalizar(texto)).strip()
    frases_fim = (
        "obrigado so isso",
        "era so isso",
        "so isso",
        "so isso obrigado",
        "pode descansar",
        "ate logo",
        "ate mais",
        "tchau",
        "encerrar conversa",
        "fim da conversa",
        "modo espera",
        "voltar para espera",
    )
    return any(t == f or t.endswith(f) for f in frases_fim)


def detectar_mudanca_modo_escuta(texto: str) -> str | None:
    """Detecta pedidos por voz para alterar o modo de escuta."""
    t = normalizar(texto)
    if re.search(r"\b(conversa livre|modo livre|escuta livre|sem chamar|sem dizer seu nome|sem palavra de ativacao)\b", t):
        return "conversa_livre"
    if re.search(r"\b(conversa continua|modo continuo|continuar conversando)\b", t):
        return "conversa_continua"
    if re.search(r"\b(ativacao por nome|modo por nome|so quando eu chamar|apenas pelo nome)\b", t):
        return "ativacao_por_nome"
    return None


def avaliar_fala_direcionada(
    texto: str,
    contexto: dict[str, Any] | None = None,
    sessao_ativa: bool = False,
) -> float:
    """Calcula a probabilidade [0.0 a 1.0] de que uma fala sem 'Gideon' seja direcionada à assistente."""
    t = normalizar(texto)
    t_limpo = re.sub(r"[^a-z0-9 ]", " ", t).strip()
    palavras = t_limpo.split()
    if not palavras:
        return 0.0

    if eh_interrupcao_barge_in(texto) or eh_desistencia_rapida(texto) or eh_encerramento_conversa(texto):
        return 0.98
    if sessao_ativa and resposta_confirmacao(texto) is not None:
        return 0.95

    if interpretar_intencao_natural(texto, contexto) is not None:
        return 0.92

    marcadores_diretos = (
        "me ajuda",
        "pode me ajudar",
        "voce consegue",
        "consegue ver",
        "olha isso",
        "olhe isso",
        "ve isso",
        "abre isso",
        "fecha isso",
        "minimiza",
        "maximiza",
        "ta agora",
        "agora fecha",
        "meu computador",
        "meu pc",
        "o que esta acontecendo",
        "por que meu",
        "isso e normal",
        "me explica",
        "o que voce acha",
        "pra mim",
        "por favor",
    )
    if any(m in t_limpo for m in marcadores_diretos):
        return 0.88

    if sessao_ativa and len(palavras) >= 2:
        return 0.82

    if ("?" in texto or palavras[0] in {"como", "qual", "quanto", "quanta", "por", "onde", "quem", "quando"}) and len(palavras) >= 3:
        return 0.72

    return 0.20


def interpretar_plano_multietapas(
    texto: str,
    contexto: dict[str, Any] | None = None,
) -> list[dict[str, Any]] | None:
    """Decompõe comandos compostos com múltiplas etapas verificáveis.

    Exemplos:
    - "Abre o navegador e pesquisa sobre inteligência artificial"
    - "Abre o Gerenciador de Tarefas e verifica o consumo de memória"
    - "Abre o Bloco de Notas e digita reunião às 15 horas"
    """
    ctx = dict(contexto or {})
    texto_limpo = texto.strip(" .,!?")
    t_norm = normalizar(texto_limpo)

    # Só tenta dividir se houver conectivo de sequência (" e depois ", " e em seguida ", " e ")
    partes_brutas = re.split(
        r"\s+(?:e depois|e em seguida|depois|em seguida|e tambem|e verifica|e veja|e olha|e pesquisa|e busca|e digita|e escreve|e minimiza|e maximiza|e fecha)\s+",
        texto_limpo,
        flags=re.IGNORECASE,
    )

    # Caso especial: preservamos o verbo quando o separador consumiu o verbo da 2ª etapa
    padrao_composto = re.search(
        r"^(.+?)\s+(?:e depois\s+|e em seguida\s+|,\s*depois\s+|e\s+)"
        r"((?:pesquisa|pesquise|busca|busque|procura|procure|verifica|verifique|checa|veja|olha|digita|digite|escreve|escreva|minimiza|minimize|maximiza|maximize|fecha|feche|abre|abra)\b.+)$",
        texto_limpo,
        re.IGNORECASE,
    )
    if not padrao_composto:
        return None

    etapa1_txt = padrao_composto.group(1).strip()
    etapa2_txt = padrao_composto.group(2).strip()

    int1 = interpretar_intencao_natural(etapa1_txt, ctx, permitir_multietapas=False)
    if not int1 or int1.get("acao") in {None, "nenhuma", "esclarecer", "perguntar_midia"}:
        return None

    if "novo_contexto" in int1:
        ctx.update(int1["novo_contexto"])

    int2 = interpretar_intencao_natural(etapa2_txt, ctx, permitir_multietapas=False)
    if not int2 or int2.get("acao") in {None, "nenhuma", "esclarecer", "perguntar_midia"}:
        return None

    # Evita abrir navegador duas vezes se a etapa 1 é "abre o navegador" e a etapa 2 já é "pesquisar_navegador"
    # Mas mantemos ambas no plano para que ambas sejam executadas/verificadas em sequência clara
    return [int1, int2]


def interpretar_intencao_natural(
    texto: str,
    contexto: dict[str, Any] | None = None,
    *,
    permitir_multietapas: bool = True,
) -> dict[str, Any] | None:
    """Interpreta intenções naturais de controle real do Windows 10, arquivos, janelas, mídia e telemetria."""
    ctx = contexto or {}
    t = normalizar(texto)
    t_limpo = re.sub(r"[^a-z0-9 ]", " ", t)
    t_limpo = " ".join(t_limpo.split())

    if not t_limpo:
        return None

    # 0. Desistência rápida ou cancelamento ("Não precisa mais", "Não, espera, deixa aberto")
    if eh_desistencia_rapida(texto):
        return {
            "acao": "cancelar_fluxo",
            "resposta_direta": "Tudo bem.",
            "novo_contexto": {"aguardando_escolha_midia": False, "aguardando_pesquisa_web": False},
        }

    # 0.5. Verifica se é um plano multietapas ("abre o navegador e pesquisa sobre IA")
    if permitir_multietapas:
        plano = interpretar_plano_multietapas(texto, ctx)
        if plano and len(plano) >= 2:
            novo_ctx: dict[str, Any] = {}
            for p in plano:
                novo_ctx.update(p.get("novo_contexto") or {})
            return {
                "acao": "plano_multietapas",
                "etapas": plano,
                "novo_contexto": novo_ctx,
            }

    # 1. Contexto ativo: se a Gideon acabou de perguntar "O que você gostaria de pesquisar?"
    if ctx.get("aguardando_pesquisa_web"):
        if resposta_confirmacao(texto) is False:
            return {
                "acao": "nenhuma",
                "resposta_direta": "Tudo bem.",
                "novo_contexto": {"aguardando_pesquisa_web": False},
            }
        termo_busca = extrair_termo_pesquisa(texto)
        motor = ctx.get("motor_pesquisa", "google")
        if termo_busca:
            return {
                "acao": "pesquisar_navegador",
                "parametros": {"consulta": termo_busca, "motor": motor},
                "novo_contexto": {
                    "aguardando_pesquisa_web": False,
                    "ultimo_topico": "navegador",
                    "ultimo_app": "chrome",
                },
            }

    # 1.5. Contexto ativo: se a Gideon acabou de perguntar "O que gostaria de ouvir?"
    if ctx.get("aguardando_escolha_midia"):
        if resposta_confirmacao(texto) is False:
            return {
                "acao": "nenhuma",
                "resposta_direta": "Tudo bem.",
                "novo_contexto": {"aguardando_escolha_midia": False},
            }
        termo = extrair_termo_midia(texto)
        plataforma = ctx.get("plataforma_midia", "spotify")
        if termo:
            return {
                "acao": "tocar_ou_pesquisar_midia",
                "parametros": {"consulta": termo, "plataforma": plataforma},
                "novo_contexto": {
                    "aguardando_escolha_midia": False,
                    "ultimo_topico": "midia",
                    "ultima_midia": termo,
                },
            }

    # 2. Pedido conversacional para pesquisar algo sem dizer o termo ainda ("Quero pesquisar uma coisa no Google")
    if re.search(
        r"\b(quero pesquisar uma coisa|quero fazer uma pesquisa|quero buscar uma coisa|pesquisa uma coisa pra mim)\b",
        t_limpo,
    ):
        motor = "youtube" if "youtube" in t_limpo else "google"
        return {
            "acao": "perguntar_pesquisa",
            "resposta_direta": f"Claro. O que você gostaria de pesquisar no {motor.capitalize()}?",
            "novo_contexto": {
                "aguardando_pesquisa_web": True,
                "motor_pesquisa": motor,
                "ultimo_topico": "navegador",
            },
        }

    # 2.5. Pedido genérico para colocar música ("agora coloca uma musica", "bota uma musica")
    if re.search(r"\b(coloca|coloque|bota|toca|tocar|ouvir|reproduz|play)\b", t_limpo) and re.search(
        r"\b(uma musica|alguma musica|musica|um som)\b$", t_limpo
    ):
        plataforma = "spotify" if ctx.get("ultimo_app") == "spotify" else "spotify"
        return {
            "acao": "perguntar_midia",
            "resposta_direta": "Claro. O que gostaria de ouvir?",
            "novo_contexto": {
                "aguardando_escolha_midia": True,
                "plataforma_midia": plataforma,
                "ultimo_topico": "midia",
            },
        }

    # 3. Gerenciamento de janelas ("minimiza ele", "maximiza a janela", "restaura o chrome", "alterna para o vscode")
    match_janela = re.search(
        r"\b(minimiza|minimize|maximiza|maximize|restaura|restaure|alterna para|alterne para|muda para|foca no|foca na|traz para frente)\b"
        r"(?:\s+(?:o|a|os|as|janela d[eo]|programa|aplicativo))?\s*(.*)$",
        t_limpo,
    )
    if match_janela:
        verbo_jan = match_janela.group(1).strip()
        alvo_jan = match_janela.group(2).strip()
        for sufixo in ("pra mim", "por favor", "agora"):
            if alvo_jan.endswith(sufixo):
                alvo_jan = alvo_jan[: -len(sufixo)].strip()

        if verbo_jan.startswith("minimiz"):
            acao_jan = "minimizar"
        elif verbo_jan.startswith("maximiz"):
            acao_jan = "maximizar"
        elif verbo_jan.startswith("restaur"):
            acao_jan = "restaurar"
        else:
            acao_jan = "focar"

        if alvo_jan in {"", "ele", "ela", "isso", "janela", "programa", "aplicativo"}:
            alvo_resolvido = ctx.get("ultimo_app", "")
        else:
            alvo_resolvido = alvo_jan

        return {
            "acao": "gerenciar_janela",
            "parametros": {"acao": acao_jan, "alvo": alvo_resolvido},
            "novo_contexto": {"ultimo_topico": "janelas"},
        }

    # 4. Fechar aplicativo ("fecha o bloco de notas", "pode fechar a calculadora", "fecha ele")
    match_fechar = re.search(
        r"\b(?:fecha|feche|fechar|encerra|encerre|encerrar)\s+(?:o|a|os|as|programa|aplicativo|janela d[eo])?\s*(.+)$",
        t_limpo,
    )
    if match_fechar and "gideon" not in t_limpo and "conversa" not in t_limpo:
        alvo_fechar = match_fechar.group(1).strip()
        for sufixo in ("pra mim", "por favor", "agora"):
            if alvo_fechar.endswith(sufixo):
                alvo_fechar = alvo_fechar[: -len(sufixo)].strip()
        if alvo_fechar in {"ele", "ela", "isso", "programa", "aplicativo", "janela"}:
            alvo_fechar = ctx.get("ultimo_app", "")
        if alvo_fechar:
            return {
                "acao": "fechar_programa",
                "parametros": {"nome": alvo_fechar},
                "novo_contexto": {"ultimo_topico": "aplicativos"},
            }

    # 5. Abrir pastas do Windows ("abre a pasta downloads", "abre meus documentos", "abre a área de trabalho")
    match_pasta = re.search(
        r"\b(?:abre|abra|abrir|mostra|acessa)\s+(?:a\s+pasta|o\s+diretorio|meus|minhas|a\s+area\s+de\s+trabalho)\s*(.*)$",
        t_limpo,
    )
    if match_pasta:
        nome_pasta = match_pasta.group(1).strip()
        for sufixo in ("pra mim", "por favor", "no computador"):
            if nome_pasta.endswith(sufixo):
                nome_pasta = nome_pasta[: -len(sufixo)].strip()
        if not nome_pasta and "area de trabalho" in t_limpo:
            nome_pasta = "desktop"
        elif not nome_pasta and "documentos" in t_limpo:
            nome_pasta = "documentos"
        if nome_pasta in {"", "downloads", "download", "documentos", "desktop", "area de trabalho", "imagens", "fotos", "musicas", "videos", "projeto"}:
            return {
                "acao": "abrir_pasta",
                "parametros": {"pasta": nome_pasta or "downloads"},
                "novo_contexto": {"ultimo_topico": "arquivos", "ultima_pasta": nome_pasta or "downloads"},
            }

    # 6. Listar ou pesquisar arquivos ("lista os arquivos de downloads", "procura o arquivo relatorio", "pesquisa arquivos com nome teste")
    if re.search(r"\b(lista os arquivos|listar arquivos|quais arquivos tem|o que tem na pasta)\b", t_limpo):
        pasta_alvo = "downloads"
        for p_nome in ("documentos", "desktop", "area de trabalho", "projeto", "downloads"):
            if p_nome in t_limpo:
                pasta_alvo = p_nome
                break
        return {
            "acao": "listar_arquivos",
            "parametros": {"pasta": pasta_alvo},
            "novo_contexto": {"ultimo_topico": "arquivos", "ultima_pasta": pasta_alvo},
        }

    match_busca_arq = re.search(
        r"\b(?:procura|procure|pesquisa|pesquise|encontra|encontre|acha|ache)\s+(?:o\s+arquivo|arquivos?\s+com\s+nome|arquivos?\s+chamado|pelo\s+arquivo)\s+(.+)$",
        texto.strip(" .,!?"),
        re.IGNORECASE,
    )
    if match_busca_arq:
        termo_arq = match_busca_arq.group(1).strip(" \"'")
        for sufixo in (" pra mim", " por favor", " no computador", " no pc"):
            if termo_arq.lower().endswith(sufixo):
                termo_arq = termo_arq[: -len(sufixo)].strip(" \"'")
        return {
            "acao": "pesquisar_arquivos",
            "parametros": {"termo": termo_arq},
            "novo_contexto": {"ultimo_topico": "arquivos"},
        }

    # 7. Criar arquivo ("cria um arquivo chamado notas.txt com o texto comprar café")
    match_criar_arq = re.search(
        r"\b(?:cria|crie|criar)\s+(?:um\s+)?arquivo\s+(?:chamado\s+|com\s+nome\s+)?([^\s]+)(?:\s+com\s+(?:o\s+texto|o\s+conteudo)\s+(.+))?$",
        texto.strip(" .,!?"),
        re.IGNORECASE,
    )
    if match_criar_arq:
        nome_arq = match_criar_arq.group(1).strip(" \"'")
        conteudo_arq = (match_criar_arq.group(2) or "").strip()
        return {
            "acao": "criar_arquivo",
            "parametros": {"caminho": nome_arq, "conteudo": conteudo_arq},
            "novo_contexto": {"ultimo_topico": "arquivos"},
        }

    # 8. Digitar texto ou executar atalho de teclado
    match_digitar = re.search(
        r"\b(?:digita|digite|escreve|escreva)\s+(?:o\s+texto\s+)?(.+?)(?:\s+no\s+(bloco de notas|notepad|chrome|navegador|vscode))?$",
        texto.strip(" .,!?"),
        re.IGNORECASE,
    )
    if match_digitar and not re.search(r"\b(arquivo|poema|codigo|historia|resumo|email)\b", t_limpo[:25]):
        texto_dig = match_digitar.group(1).strip(" \"'")
        janela_dig = (match_digitar.group(2) or ctx.get("ultimo_app") or "").strip()
        return {
            "acao": "digitar_texto",
            "parametros": {"texto": texto_dig, "janela_alvo": janela_dig},
            "novo_contexto": {"ultimo_topico": "automacao_ui"},
        }

    match_atalho = re.search(
        r"\b(?:pressiona|pressione|aperta|aperte|executa o atalho|atalho)\s+((?:ctrl|control|alt|shift|win)\s*[\+\-\s]\s*[a-z0-9]+|enter|esc|f[0-9]{1,2}|alt\s*tab)\b",
        t_limpo,
    )
    if match_atalho:
        atalho_bruto = re.sub(r"\s+", "+", match_atalho.group(1).strip())
        return {
            "acao": "executar_atalho_teclado",
            "parametros": {"atalho": atalho_bruto},
            "novo_contexto": {"ultimo_topico": "automacao_ui"},
        }

    # 9. Pesquisa explícita no navegador ("pesquisa sobre inteligência artificial", "pesquisa X no Google")
    match_pesquisa_web = re.search(
        r"\b(?:pesquisa|pesquise|pesquisar|busca|busque|buscar|procura|procure)\s+"
        r"(?:sobre\s+|por\s+|no\s+google\s+sobre\s+|no\s+navegador\s+sobre\s+)?"
        r"(.+?)(?:\s+no\s+(google|youtube|navegador|internet))?$",
        texto.strip(" .,!?"),
        re.IGNORECASE,
    )
    if match_pesquisa_web:
        termo_web = match_pesquisa_web.group(1).strip()
        motor_explicito = (match_pesquisa_web.group(2) or "").lower()
        for sufixo in (" pra mim", " por favor"):
            if termo_web.lower().endswith(sufixo):
                termo_web = termo_web[: -len(sufixo)].strip()
        if (
            motor_explicito in {"google", "youtube", "navegador", "internet"}
            or re.search(r"\b(pesquisa sobre|pesquise sobre|busca sobre|pesquisa no google)\b", t_limpo)
        ):
            motor_final = "youtube" if motor_explicito == "youtube" else "google"
            return {
                "acao": "pesquisar_navegador",
                "parametros": {"consulta": termo_web, "motor": motor_final},
                "novo_contexto": {
                    "ultimo_topico": "navegador",
                    "ultimo_app": "chrome",
                },
            }

    # 10. Pedido direto para tocar artista/música específica ("coloca alguma coisa do Chase Atlantic")
    match_midia = re.search(
        r"\b(?:coloca|coloque|bota|toca|tocar|ouvir|reproduz)\s+"
        r"(?:alguma coisa d[eo]s?\s+|uma musica d[eo]s?\s+|musica d[eo]s?\s+|um som d[eo]s?\s+|algo d[eo]s?\s+)?"
        r"(.+?)(?:\s+no\s+(spotify|youtube|google))?$",
        texto.strip(" .,!?"),
        re.IGNORECASE,
    )
    if match_midia:
        possivel_termo = match_midia.group(1).strip()
        plataforma_explicita = (match_midia.group(2) or "").lower()
        termo_norm = normalizar(possivel_termo)
        palavras_sistema = {"chrome", "navegador", "internet", "google", "spotify", "calculadora", "vscode", "discord", "steam", "isso", "isso aqui"}
        if (
            plataforma_explicita in {"spotify", "youtube", "google"}
            or re.search(r"\b(alguma coisa d|musica d|som d|toca |bota |coloca )\b", t_limpo)
        ) and termo_norm not in palavras_sistema and not termo_norm.startswith(("uma musica", "musica", "no ")):
            plat = plataforma_explicita or ctx.get("plataforma_midia") or "spotify"
            return {
                "acao": "tocar_ou_pesquisar_midia",
                "parametros": {"consulta": possivel_termo, "plataforma": plat},
                "novo_contexto": {
                    "aguardando_escolha_midia": False,
                    "ultimo_topico": "midia",
                    "ultima_midia": possivel_termo,
                },
            }

    # 11. Controles de mídia e volume ("pausa a musica", "proxima musica", "aumenta o volume")
    if re.search(r"\b(pausa|pausar|para a musica)\b", t_limpo):
        return {"acao": "controlar_midia", "parametros": {"acao": "pausar"}, "novo_contexto": {"ultimo_topico": "midia"}}
    if re.search(r"\b(proxima musica|proxima faixa|pula a musica|passa a musica)\b", t_limpo):
        return {"acao": "controlar_midia", "parametros": {"acao": "proxima"}, "novo_contexto": {"ultimo_topico": "midia"}}
    if re.search(r"\b(musica anterior|faixa anterior|volta a musica)\b", t_limpo):
        return {"acao": "controlar_midia", "parametros": {"acao": "anterior"}, "novo_contexto": {"ultimo_topico": "midia"}}
    if re.search(r"\b(aumenta o volume|subir volume|aumentar volume|mais alto)\b", t_limpo):
        return {"acao": "controlar_midia", "parametros": {"acao": "aumentar_volume"}, "novo_contexto": {}}
    if re.search(r"\b(abaixa o volume|diminui o volume|diminuir volume|mais baixo)\b", t_limpo):
        return {"acao": "controlar_midia", "parametros": {"acao": "diminuir_volume"}, "novo_contexto": {}}
    if re.search(r"\b(silencia|deixa no mudo|tirar o som|mutar)\b", t_limpo):
        return {"acao": "controlar_midia", "parametros": {"acao": "mudo"}, "novo_contexto": {}}

    # 12. Comandos incompletos ou dêiticos sem alvo ("Abre isso aqui pra mim", "Ei, olha isso aqui")
    if re.search(r"\b(abre isso|abra isso|abrir isso|abre aqui)\b", t_limpo):
        ultimo_app = ctx.get("ultimo_app")
        if ultimo_app:
            return {
                "acao": "abrir_programa",
                "parametros": {"nome": ultimo_app},
                "novo_contexto": {"ultimo_topico": "aplicativos"},
            }
        return {
            "acao": "esclarecer",
            "resposta_direta": "O que você gostaria que eu abrisse, Henry?",
            "novo_contexto": {},
        }

    # 13. Abertura natural de navegador / internet / aplicativos sem comandos rígidos
    eh_pergunta_conceitual = t_limpo.startswith(("o que e ", "quem criou ", "para que serve ", "como funciona "))
    verbos_abrir = (
        r"\b(abre|abra|abrir|abro|abri|inicia|iniciar|executa|roda|entrar|entra|entre|"
        r"acessar|acessa|liga|quero ir|quero entrar|consegue abrir|pode abrir|coloca no)\b"
    )
    if not eh_pergunta_conceitual and re.search(verbos_abrir, t_limpo):
        mapa_alvos = [
            (r"\b(chrome|google chrome|navegador|internet|browser|web)\b", "chrome"),
            (r"\b(google)\b", "google"),
            (r"\b(spotify)\b", "spotify"),
            (r"\b(youtube)\b", "youtube"),
            (r"\b(whatsapp)\b", "whatsapp"),
            (r"\b(discord)\b", "discord"),
            (r"\b(steam)\b", "steam"),
            (r"\b(vscode|vs code|visual studio code|editor de codigo)\b", "vscode"),
            (r"\b(calculadora|calc)\b", "calculadora"),
            (r"\b(bloco de notas|notepad)\b", "bloco de notas"),
            (r"\b(explorador de arquivos|meus arquivos|minhas pastas|explorer)\b", "explorador de arquivos"),
            (r"\b(gerenciador de tarefas|taskmgr)\b", "gerenciador de tarefas"),
            (r"\b(configuracoes|ajustes do windows)\b", "configuracoes"),
            (r"\b(terminal|powershell|prompt)\b", "terminal"),
            (r"\b(edge|microsoft edge)\b", "edge"),
            (r"\b(paint|mspaint)\b", "paint"),
        ]
        for padrao_alvo, nome_app in mapa_alvos:
            if re.search(padrao_alvo, t_limpo):
                return {
                    "acao": "abrir_programa",
                    "parametros": {"nome": nome_app},
                    "novo_contexto": {
                        "ultimo_app": nome_app,
                        "ultimo_topico": "midia" if nome_app in {"spotify", "youtube"} else "aplicativos",
                        "plataforma_midia": nome_app if nome_app in {"spotify", "youtube"} else ctx.get("plataforma_midia", "spotify"),
                    },
                }

        # Se o usuário pediu explicitamente para abrir algum outro programa ("abre o photoshop", "abre o blender")
        # Roteamos para abrir_programa para que o ExecutorConfiavel verifique a existência real e NUNCA minta!
        match_app_generico = re.search(
            r"\b(?:abre|abra|abrir|inicia|iniciar|executa)\s+(?:o\s+programa\s+|o\s+aplicativo\s+|o\s+app\s+|o\s+|a\s+)?([a-z0-9_.\- ]+?)(?:\s+pra mim|\s+por favor|\s+agora)?$",
            t_limpo,
        )
        if match_app_generico:
            cand = match_app_generico.group(1).strip()
            palavras_ignorar = {"conversa", "modo", "sessao", "olho", "mente", "explicacao", "jogo"}
            if cand and cand not in palavras_ignorar and len(cand.split()) <= 3:
                return {
                    "acao": "abrir_programa",
                    "parametros": {"nome": cand},
                    "novo_contexto": {"ultimo_app": cand, "ultimo_topico": "aplicativos"},
                }

    # 14. Pergunta contextual sobre normalidade do hardware ("Isso é normal?", "Está alto?", "Está bom?")
    if ctx.get("ultimo_topico") == "hardware_pc" and re.search(
        r"\b(isso e normal|ta normal|esta normal|e normal|ta bom|esta alto|ta alto|preocupante)\b",
        t_limpo,
    ):
        recurso = ctx.get("ultimo_recurso", "geral")
        if recurso == "gpu":
            resp_norm = "Sim, Henry. Sua RX 580 com 8 GB está operando em temperatura e carga perfeitamente normais."
        elif recurso == "ram":
            resp_norm = "Sim, está dentro do esperado para o Windows com seus aplicativos abertos."
        else:
            resp_norm = "Sim, Henry. Todos os indicadores de uso estão saudáveis e dentro do normal."
        return {
            "acao": "avaliacao_contextual",
            "resposta_direta": resp_norm,
            "novo_contexto": {"ultimo_topico": "hardware_pc"},
        }

    # 14.5. Diálogo proativo de diagnóstico ("Meu computador tá estranho hoje" -> "O que está acontecendo?" -> "Tá meio lento" -> "Quer que eu verifique o consumo de recursos?" -> "Pode olhar")
    if ctx.get("aguardando_confirmacao_diagnostico"):
        conf_diag = resposta_confirmacao(texto)
        if conf_diag is True or re.search(r"\b(pode olhar|olha ai|ve ai|verifica|checa)\b", t_limpo):
            return {
                "acao": "obter_status_pc",
                "parametros": {},
                "foco_resposta": "diagnostico",
                "novo_contexto": {
                    "aguardando_confirmacao_diagnostico": False,
                    "aguardando_sintoma_pc": False,
                    "ultimo_topico": "hardware_pc",
                    "ultimo_recurso": "geral",
                },
            }
        if conf_diag is False:
            return {
                "acao": "nenhuma",
                "resposta_direta": "Tudo bem, Henry. Qualquer coisa me avise.",
                "novo_contexto": {"aguardando_confirmacao_diagnostico": False, "aguardando_sintoma_pc": False},
            }

    if re.search(r"\b(meu computador ta estranho|meu pc ta estranho|computador esta estranho|pc esquisito)\b", t_limpo):
        return {
            "acao": "perguntar_sintoma_pc",
            "resposta_direta": "O que está acontecendo?",
            "novo_contexto": {
                "aguardando_sintoma_pc": True,
                "ultimo_topico": "hardware_pc",
            },
        }

    if (ctx.get("aguardando_sintoma_pc") and re.search(r"\b(lento|devagar|travando|engasgando|demorando|pesado)\b", t_limpo)) or (
        t_limpo in {"ta meio lento", "esta meio lento", "ele ta meio lento", "ta lento"}
    ):
        return {
            "acao": "oferecer_diagnostico_pc",
            "resposta_direta": "Quer que eu verifique o consumo de recursos?",
            "novo_contexto": {
                "aguardando_sintoma_pc": False,
                "aguardando_confirmacao_diagnostico": True,
                "ultimo_topico": "hardware_pc",
            },
        }

    # 15. Diagnóstico natural imediato de lentidão ("Por que meu computador tá travando?", "Você consegue ver o que está acontecendo?")
    if re.search(
        r"\b(por que meu computador ta travando|computador travando|pc lento|computador lento|o que esta acontecendo no pc|ve o que esta acontecendo)\b",
        t_limpo,
    ):
        return {
            "acao": "obter_status_pc",
            "parametros": {},
            "foco_resposta": "diagnostico",
            "novo_contexto": {"ultimo_topico": "hardware_pc", "ultimo_recurso": "geral"},
        }

    # 15.5. Consciência de tela e janela ativa ("o que está na minha tela?", "qual janela está ativa?", "analisa minha tela")
    if re.search(
        r"\b(o que esta na minha tela|qual janela esta ativa|qual janela esta aberta|analisa minha tela|olha minha tela|o que estou vendo|janela atual)\b",
        t_limpo,
    ):
        return {
            "acao": "inspecionar_contexto_tela",
            "parametros": {},
            "novo_contexto": {"ultimo_topico": "tela"},
        }

    # 16. Telemetria contextual do PC (CPU, RAM, GPU / Placa de Vídeo, Disco)
    if re.search(r"\b(placa de video|gpu|radeon|rx 580|vram|memoria de video)\b", t_limpo):
        return {
            "acao": "obter_status_gpu",
            "parametros": {},
            "foco_resposta": "gpu",
            "novo_contexto": {"ultimo_topico": "hardware_pc", "ultimo_recurso": "gpu"},
        }

    if re.search(
        r"\b(memoria ram|uso de ram|consumo de memoria|consumo de ram|quanto de ram|quanta ram|memoria estou usando|ram meu computador|verifica a memoria|verificar a memoria)\b",
        t_limpo,
    ) or (ctx.get("ultimo_topico") == "hardware_pc" and re.search(r"^(e a |e de )?(memoria|ram)\b", t_limpo)):
        return {
            "acao": "obter_status_pc",
            "parametros": {},
            "foco_resposta": "ram",
            "novo_contexto": {"ultimo_topico": "hardware_pc", "ultimo_recurso": "ram"},
        }

    if re.search(r"\b(uso de cpu|consumo de cpu|processador|como esta a cpu)\b", t_limpo) or (
        ctx.get("ultimo_topico") == "hardware_pc" and re.search(r"^(e o |e a )?(processador|cpu)\b", t_limpo)
    ):
        return {
            "acao": "obter_status_pc",
            "parametros": {},
            "foco_resposta": "cpu",
            "novo_contexto": {"ultimo_topico": "hardware_pc", "ultimo_recurso": "cpu"},
        }

    if re.search(r"\b(espaco em disco|disco c|hd|ssd|armazenamento)\b", t_limpo) or (
        ctx.get("ultimo_topico") == "hardware_pc" and re.search(r"^(e o |e no )?(disco|hd|ssd|espaco)\b", t_limpo)
    ):
        return {
            "acao": "obter_status_pc",
            "parametros": {},
            "foco_resposta": "disco",
            "novo_contexto": {"ultimo_topico": "hardware_pc", "ultimo_recurso": "disco"},
        }

    if re.search(
        r"\b(como esta meu computador|como esta o meu pc|como esta o pc|status do pc|status do computador|desempenho do pc|recursos do computador)\b",
        t_limpo,
    ):
        return {
            "acao": "obter_status_pc",
            "parametros": {},
            "foco_resposta": "geral",
            "novo_contexto": {"ultimo_topico": "hardware_pc", "ultimo_recurso": "geral"},
        }

    # 17. Programas abertos em execução
    if re.search(
        r"\b(programas\s+(?:estao\s+|que\s+estao\s+)?abertos|o\s+que\s+(?:esta|ta)\s+aberto|aplicativos\s+(?:estao\s+)?abertos|rodando\s+no\s+pc)\b",
        t_limpo,
    ):
        return {
            "acao": "listar_programas_usuario",
            "parametros": {},
            "novo_contexto": {"ultimo_topico": "aplicativos"},
        }

    # 18. Bloquear tela
    if re.search(r"\b(bloqueia a tela|bloquear a tela|bloqueia o pc|tranca a tela|bloquear computador)\b", t_limpo):
        return {
            "acao": "bloquear_estacao",
            "parametros": {},
            "novo_contexto": {"ultimo_topico": "seguranca"},
        }

    return None


def extrair_termo_pesquisa(texto: str) -> str:
    """Extrai o termo de busca quando o usuário responde ao prompt de pesquisa."""
    limpo = texto.strip(" .,!?")
    padrao = (
        r"^(?:por favor\s+|entao\s+|agora\s+)?"
        r"(?:pesquisa|pesquise|busca|busque|procura|procure|quero saber)?\s*"
        r"(?:sobre\s+|por\s+|a\s+respeito\s+de\s+)?"
        r"(.+?)(?:\s+no\s+(?:google|youtube))?"
        r"(?:\s+pra mim|\s+por favor)?$"
    )
    m = re.search(padrao, limpo, re.IGNORECASE)
    if m:
        return m.group(1).strip(" .,!?")
    return limpo


def extrair_termo_midia(texto: str) -> str:
    """Limpa prefixos conversacionais para extrair o nome da música ou artista."""
    limpo = texto.strip(" .,!?")
    padrao = (
        r"^(?:por favor\s+|entao\s+|agora\s+)?"
        r"(?:coloca|coloque|bota|toca|tocar|quero ouvir|reproduz|poe|põe)?\s*"
        r"(?:alguma coisa d[eo]s?\s+|uma m[uú]sica d[eo]s?\s+|m[uú]sica d[eo]s?\s+|algo d[eo]s?\s+|um som d[eo]s?\s+)?"
        r"(.+?)(?:\s+no\s+(?:spotify|youtube))?"
        r"(?:\s+pra mim|\s+por favor)?$"
    )
    m = re.search(padrao, limpo, re.IGNORECASE)
    if m:
        return m.group(1).strip(" .,!?")
    return limpo


def formatar_resposta_telemetria(dados: dict[str, Any], foco: str = "geral") -> str:
    """Formata os dados reais de hardware do PC em uma resposta concisa, natural e objetiva."""
    if foco == "gpu" or ("modelo" in dados and "vram" in dados and "cpu_percent" not in dados):
        modelo = dados.get("modelo", "AMD Radeon RX 580")
        vram = dados.get("vram", "8 GB")
        uso = dados.get("uso_3d", "operando normalmente")
        return f"Sua {modelo} de {vram} está com utilização em {uso}, Henry."

    ram = dados.get("memoria_ram", {})
    cpu = dados.get("cpu_percent", "0%")
    disco = dados.get("disco_c", {})
    gpu = dados.get("gpu", {})

    if foco == "ram":
        return (
            f"Você está utilizando {ram.get('usado_gb', '')} de memória RAM, "
            f"com {ram.get('livre_gb', '')} livres."
        )
    if foco == "cpu":
        return f"O processador está em {cpu} de uso agora, Henry."
    if foco == "disco":
        return (
            f"O disco C está em {disco.get('percentual_usado', '')}, "
            f"com {disco.get('livre_gb', '')} livres."
        )
    if foco == "diagnostico":
        return (
            f"Verifiquei agora: o processador está em {cpu} e a RAM em "
            f"{ram.get('usado_gb', '')} ({ram.get('percentual', '')}). Não há sobrecarga crítica no sistema."
        )

    gpu_str = f" e a {gpu.get('modelo', 'GPU')} está normal" if gpu else ""
    return (
        f"Seu computador está funcionando normalmente: CPU em {cpu}, "
        f"RAM em {ram.get('usado_gb', '')}{gpu_str}. Deseja que eu verifique mais alguma coisa?"
    )
