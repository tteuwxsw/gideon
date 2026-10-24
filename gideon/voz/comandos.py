"""Interpretação de linguagem natural, intenções locais e comandos sensíveis da Gideon."""

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


def detectar_comando_sistema(texto: str) -> str | None:
    """Detecta comandos críticos (Portão Vermelho) que exigem confirmação."""
    texto_norm = normalizar(texto)
    if re.search(r"\b(atualize|atualiza|atualizar|verifique)\b", texto_norm) and re.search(
        r"\b(sistema|sistemas|atualizacao|atualizacoes|novidades|versao)\b", texto_norm
    ):
        return "atualizar_sistemas"
    if any(
        frase in texto_norm
        for frase in (
            "pode fechar",
            "pode encerrar",
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
        "confirmo",
        "pode",
        "pode fazer",
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
    }
    negativas = {
        "nao",
        "cancelar",
        "cancela",
        "deixa",
        "deixa pra la",
        "agora nao",
        "nao quero",
        "esquece",
        "para",
    }
    if texto_norm in afirmativas or texto_norm.startswith(("sim ", "confirmo ", "pode fazer")):
        return True
    if texto_norm in negativas or texto_norm.startswith(("nao ", "cancela")):
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
        "opa",
        "aguarda",
        "pausa",
        "chega",
    )
    return any(g in t.split() or t.startswith(g) for g in gatilhos)


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
    """Detecta pedidos por voz para alterar o modo de escuta (ativacao_por_nome, conversa_continua, conversa_livre)."""
    t = normalizar(texto)
    if re.search(r"\b(conversa livre|modo livre|escuta livre|sem chamar|sem dizer seu nome)\b", t):
        return "conversa_livre"
    if re.search(r"\b(conversa continua|modo continuo|continuar conversando)\b", t):
        return "conversa_continua"
    if re.search(r"\b(ativacao por nome|modo por nome|so quando eu chamar|apenas pelo nome)\b", t):
        return "ativacao_por_nome"
    return None


def interpretar_intencao_natural(
    texto: str,
    contexto: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Interpreta intenções naturais de controle do PC, mídia e telemetria sem exigir frases rígidas.

    Retorna um dicionário com:
      - `acao`: nome da ferramenta ou ação contextual
      - `parametros`: argumentos para a ferramenta
      - `resposta_direta`: opcional (quando a própria intenção é uma etapa conversacional)
      - `novo_contexto`: atualizações para o estado da sessão
    """
    ctx = contexto or {}
    t = normalizar(texto)
    t_limpo = re.sub(r"[^a-z0-9 ]", " ", t)
    t_limpo = " ".join(t_limpo.split())

    if not t_limpo:
        return None

    # 1. Contexto ativo: se a Gideon acabou de perguntar "O que gostaria de ouvir?"
    if ctx.get("aguardando_escolha_midia"):
        # Se não for um cancelamento nem outra pergunta de sistema
        if resposta_confirmacao(texto) is False:
            return {
                "acao": "nenhuma",
                "resposta_direta": "[EMOCAO:neutra] Tudo bem, Henry. Cancelei a reprodução.",
                "novo_contexto": {"aguardando_escolha_midia": False},
            }
        # Extrai o nome do artista/música de frases como "coloca alguma coisa do Chase Atlantic"
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

    # 2. Pedido genérico para colocar música ("agora coloca uma musica", "bota uma musica", "toca alguma musica")
    if re.search(r"\b(coloca|coloque|bota|toca|tocar|ouvir|reproduz|play)\b", t_limpo) and re.search(
        r"\b(uma musica|alguma musica|musica|um som)\b$", t_limpo
    ):
        plataforma = "spotify" if ctx.get("ultimo_app") == "spotify" else "spotify"
        return {
            "acao": "perguntar_midia",
            "resposta_direta": "[EMOCAO:amigavel] Claro, Henry. O que você gostaria de ouvir?",
            "novo_contexto": {
                "aguardando_escolha_midia": True,
                "plataforma_midia": plataforma,
                "ultimo_topico": "midia",
            },
        }

    # 3. Pedido direto para tocar artista/música específica ("coloca alguma coisa do Chase Atlantic", "toca X no Spotify")
    match_midia = re.search(
        r"\b(?:coloca|coloque|bota|toca|tocar|ouvir|reproduz|pesquisa|busca)\s+"
        r"(?:alguma coisa d[eo]s?\s+|uma musica d[eo]s?\s+|musica d[eo]s?\s+|um som d[eo]s?\s+|algo d[eo]s?\s+)?"
        r"(.+?)(?:\s+no\s+(spotify|youtube|google))?$",
        texto.strip(" .,!?"),
        re.IGNORECASE,
    )
    if match_midia:
        possivel_termo = match_midia.group(1).strip()
        plataforma_explicita = (match_midia.group(2) or "").lower()
        termo_norm = normalizar(possivel_termo)
        # Garante que não é um pedido de abrir programa comum (ex: "abre o chrome")
        palavras_sistema = {"chrome", "navegador", "internet", "google", "spotify", "calculadora", "vscode", "discord", "steam"}
        if (
            plataforma_explicita in {"spotify", "youtube", "google"}
            or re.search(r"\b(alguma coisa d|musica d|som d|toca |bota |coloca )\b", t_limpo)
        ) and termo_norm not in palavras_sistema and not termo_norm.startswith(("uma musica", "musica")):
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

    # 4. Controles de mídia e volume ("pausa a musica", "proxima musica", "aumenta o volume")
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

    # 5. Abertura natural de navegador / internet / aplicativos sem comandos rígidos
    # Ex: "abre o chrome", "abre o navegador pra mim", "consegue abrir a internet?", "quero entrar no google"
    verbos_abrir = r"\b(abre|abra|abrir|inicia|iniciar|executa|roda|entrar|entra|acessar|acessa|liga|quero ir|quero entrar|consegue abrir|pode abrir)\b"
    if re.search(verbos_abrir, t_limpo):
        mapa_alvos = [
            (r"\b(chrome|google chrome|navegador|internet|browser)\b", "chrome"),
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

    # 6. Telemetria contextual do PC (CPU, RAM, GPU / Placa de Vídeo, Disco)
    # Perguntas diretas ou de continuação ("E a placa de vídeo?", "E a GPU?", "E o processador?", "E o espaço em disco?")
    if re.search(r"\b(placa de video|gpu|radeon|rx 580|vram|memoria de video)\b", t_limpo):
        return {
            "acao": "obter_status_gpu",
            "parametros": {},
            "foco_resposta": "gpu",
            "novo_contexto": {"ultimo_topico": "hardware_pc", "ultimo_recurso": "gpu"},
        }

    if re.search(r"\b(memoria ram|uso de ram|quanto de ram|quanta ram|memoria estou usando)\b", t_limpo) or (
        ctx.get("ultimo_topico") == "hardware_pc" and re.search(r"^(e a |e de )?(memoria|ram)\b", t_limpo)
    ):
        return {
            "acao": "obter_status_pc",
            "parametros": {},
            "foco_resposta": "ram",
            "novo_contexto": {"ultimo_topico": "hardware_pc", "ultimo_recurso": "ram"},
        }

    if re.search(r"\b(uso de cpu|processador|como esta a cpu)\b", t_limpo) or (
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

    # 7. Programas abertos em execução
    if re.search(r"\b(programas abertos|o que esta aberto|aplicativos abertos|rodando no pc)\b", t_limpo):
        return {
            "acao": "listar_programas_usuario",
            "parametros": {},
            "novo_contexto": {"ultimo_topico": "aplicativos"},
        }

    # 8. Bloquear tela
    if re.search(r"\b(bloqueia a tela|bloquear a tela|bloqueia o pc|tranca a tela|bloquear computador)\b", t_limpo):
        return {
            "acao": "bloquear_estacao",
            "parametros": {},
            "novo_contexto": {"ultimo_topico": "seguranca"},
        }

    # 9. Modos visuais do holograma
    if re.search(r"\b(modo foco|focar|centro da tela)\b", t_limpo):
        return {"acao": "modo_avatar", "parametros": {"modo": "foco"}, "novo_contexto": {}}
    if re.search(r"\b(modo compacto|ir para o canto|ficar pequena)\b", t_limpo):
        return {"acao": "modo_avatar", "parametros": {"modo": "compacto"}, "novo_contexto": {}}
    if re.search(r"\b(modo conversa|aparecer|mostrar holograma)\b", t_limpo):
        return {"acao": "modo_avatar", "parametros": {"modo": "conversa"}, "novo_contexto": {}}
    if re.search(r"\b(ocultar holograma|esconder holograma|ficar invisivel)\b", t_limpo):
        return {"acao": "modo_avatar", "parametros": {"modo": "oculto"}, "novo_contexto": {}}

    return None


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
    """Formata os dados reais de hardware do PC em uma resposta natural e fluida digna da Gideon."""
    if foco == "gpu" or ("modelo" in dados and "vram" in dados and "cpu_percent" not in dados):
        modelo = dados.get("modelo", "AMD Radeon RX 580")
        vram = dados.get("vram", "8 GB")
        uso = dados.get("uso_3d", "operando normalmente")
        return (
            f"[EMOCAO:concentracao] Sua placa de vídeo {modelo} com {vram} de memória dedicada "
            f"está ativa e com utilização 3D em {uso}, Henry."
        )

    ram = dados.get("memoria_ram", {})
    cpu = dados.get("cpu_percent", "0%")
    disco = dados.get("disco_c", {})
    gpu = dados.get("gpu", {})

    if foco == "ram":
        return (
            f"[EMOCAO:concentracao] Você está utilizando {ram.get('usado_gb', '')} de memória RAM "
            f"({ram.get('percentual', '')} do total de {ram.get('total_gb', '')}), "
            f"restando {ram.get('livre_gb', '')} disponíveis."
        )
    if foco == "cpu":
        return (
            f"[EMOCAO:concentracao] O processador está operando em {cpu} de utilização neste momento, Henry."
        )
    if foco == "disco":
        return (
            f"[EMOCAO:concentracao] O disco principal está com {disco.get('percentual_usado', '')} ocupado, "
            f"tendo {disco.get('livre_gb', '')} livres de um total de {disco.get('total_gb', '')}."
        )

    gpu_str = f", e sua {gpu.get('modelo', 'GPU')} está operando normalmente" if gpu else ""
    return (
        f"[EMOCAO:amigavel] Seu computador está funcionando perfeitamente, Henry. "
        f"O processador está em {cpu}, a memória RAM em {ram.get('usado_gb', '')} ({ram.get('percentual', '')})"
        f"{gpu_str}. Deseja que eu verifique mais alguma coisa?"
    )
