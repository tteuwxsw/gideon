"""Sistema de memória permanente da Gideon (Fatos, Conversas com FTS5 e Resumos).

Segue estritamente a especificação da Seção 7:
- Fatos: chave -> valor curtos e editáveis com data de atualização.
- Conversa: histórico pesquisável por FTS5 (sem acentos).
- Lembranças: recuperação dos top 5 trechos relevantes citando a data de origem.
- Comandos explícitos: 'lembra que...', 'o que você sabe sobre mim?', 'esquece...'.
"""

import sqlite3
import re
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
DADOS_DIR = ROOT_DIR / "dados"
DB_PATH = DADOS_DIR / "memoria.db"


class Memoria:
    """Gerenciador do banco de dados local SQLite da Gideon."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._inicializar_banco()

    def _conectar(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        return con

    def _inicializar_banco(self) -> None:
        """Cria as tabelas e triggers conforme especificação da Seção 7."""
        with self._conectar() as con:
            cur = con.cursor()

            # Tabela de fatos permanentes
            cur.execute("""
            CREATE TABLE IF NOT EXISTS fatos (
                id INTEGER PRIMARY KEY,
                chave TEXT NOT NULL UNIQUE,
                valor TEXT NOT NULL,
                origem TEXT,
                criado_em TEXT DEFAULT (datetime('now', 'localtime')),
                atualizado_em TEXT DEFAULT (datetime('now', 'localtime'))
            );
            """)

            # Tabela de histórico de conversas
            cur.execute("""
            CREATE TABLE IF NOT EXISTS conversa (
                id INTEGER PRIMARY KEY,
                quando TEXT DEFAULT (datetime('now', 'localtime')),
                quem TEXT CHECK (quem IN ('voce', 'assistente')),
                texto TEXT NOT NULL
            );
            """)

            # Tabela virtual FTS5 para busca textual sem acentos
            cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS conversa_fts USING fts5(
                texto, content='conversa', content_rowid='id',
                tokenize='unicode61 remove_diacritics 2'
            );
            """)

            # Triggers para sincronizar conversa_fts
            cur.execute("""
            CREATE TRIGGER IF NOT EXISTS conversa_ai AFTER INSERT ON conversa BEGIN
                INSERT INTO conversa_fts(rowid, texto) VALUES (new.id, new.texto);
            END;
            """)

            cur.execute("""
            CREATE TRIGGER IF NOT EXISTS conversa_ad AFTER DELETE ON conversa BEGIN
                INSERT INTO conversa_fts(conversa_fts, rowid, texto) VALUES ('delete', old.id, old.texto);
            END;
            """)

            # Tabela de resumos periódicos
            cur.execute("""
            CREATE TABLE IF NOT EXISTS resumos (
                id INTEGER PRIMARY KEY,
                periodo TEXT NOT NULL,
                conteudo TEXT NOT NULL,
                criado_em TEXT DEFAULT (datetime('now', 'localtime'))
            );
            """)
            con.commit()

    # ─── Fatos ──────────────────────────────────────────────────

    def salvar_fato(self, chave: str, valor: str, origem: str = "conversa") -> None:
        """Adiciona ou atualiza um fato permanente."""
        chave_norm = chave.strip().lower()
        valor_norm = valor.strip()
        with self._conectar() as con:
            con.execute("""
                INSERT INTO fatos (chave, valor, origem, atualizado_em)
                VALUES (?, ?, ?, datetime('now', 'localtime'))
                ON CONFLICT(chave) DO UPDATE SET
                    valor = excluded.valor,
                    origem = excluded.origem,
                    atualizado_em = datetime('now', 'localtime');
            """, (chave_norm, valor_norm, origem))
            con.commit()

    def obter_fato(self, chave: str) -> str | None:
        """Busca o valor de um fato pela chave."""
        chave_norm = chave.strip().lower()
        with self._conectar() as con:
            row = con.execute("SELECT valor FROM fatos WHERE chave = ?", (chave_norm,)).fetchone()
            return row["valor"] if row else None

    def listar_fatos(self) -> list[dict[str, Any]]:
        """Retorna todos os fatos gravados."""
        with self._conectar() as con:
            rows = con.execute("SELECT chave, valor, atualizado_em FROM fatos ORDER BY atualizado_em DESC").fetchall()
            return [{"chave": r["chave"], "valor": r["valor"], "atualizado_em": r["atualizado_em"]} for r in rows]

    def esquecer_fato(self, chave: str) -> bool:
        """Remove um fato permanente."""
        chave_norm = chave.strip().lower()
        with self._conectar() as con:
            cur = con.execute("DELETE FROM fatos WHERE chave = ?", (chave_norm,))
            con.commit()
            return cur.rowcount > 0

    # ─── Conversa e Busca FTS5 ──────────────────────────────────

    def gravar_mensagem(self, quem: str, texto: str) -> None:
        """Registra uma fala no histórico permanente da memória."""
        quem_norm = "voce" if quem in ("voce", "user", "usuario") else "assistente"
        with self._conectar() as con:
            con.execute("INSERT INTO conversa (quem, texto) VALUES (?, ?)", (quem_norm, texto))
            con.commit()

    def buscar_historico(self, termo: str, limite: int = 5) -> list[dict[str, Any]]:
        """Busca mensagens no histórico usando FTS5 (insensível a acentos)."""
        termo_limpo = re.sub(r"[^\w\s]", " ", termo).strip()
        if not termo_limpo:
            return []

        # Constrói query de prefixo FTS5 para matching de palavras
        tokens = [f'"{token}"' for token in termo_limpo.split() if len(token) > 2]
        if not tokens:
            tokens = [f'"{t}"' for t in termo_limpo.split()]

        query_fts = " OR ".join(tokens)

        with self._conectar() as con:
            try:
                rows = con.execute("""
                    SELECT c.id, c.quando, c.quem, snippet(conversa_fts, 0, '[', ']', '…', 8) AS trecho, c.texto
                    FROM conversa_fts
                    JOIN conversa c ON c.id = conversa_fts.rowid
                    WHERE conversa_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?;
                """, (query_fts, limite)).fetchall()
                return [
                    {
                        "id": r["id"],
                        "quando": r["quando"],
                        "quem": r["quem"],
                        "trecho": r["trecho"],
                        "texto_original": r["texto"],
                    }
                    for r in rows
                ]
            except sqlite3.OperationalError:
                return []

    # ─── Comandos Rápidos e Recuperação de Lembranças ───────────

    def processar_comando_explicito(self, texto: str) -> str | None:
        """Detecta se a mensagem é um comando direto de memória e responde imediatamente."""
        texto_limpo = texto.strip()

        # "lembra que X é/gosta de/favorito Y"
        match_lembra = re.search(
            r"^(?:gideon[, ]+)?(?:lembre|lembra)(?:-se)?(?:\s+de)?(?:\s+que)?\s+(.+)$",
            texto_limpo,
            re.IGNORECASE,
        )
        if match_lembra:
            conteudo = match_lembra.group(1).strip()
            # Tenta dividir em chave e valor preservando maiúsculas
            partes = re.split(r"\s+(?:é|=|sao|são|gosta de|prefere)\s+", conteudo, maxsplit=1, flags=re.IGNORECASE)
            if len(partes) == 2:
                chave = partes[0].strip()
                valor = partes[1].strip()
                self.salvar_fato(chave, valor)
                return f"[EMOCAO:satisfacao] Anotado, Henry. Guardei em minha memória permanente que {chave} é {valor}."

            self.salvar_fato(conteudo, "verdadeiro")
            return f"[EMOCAO:satisfacao] Entendido, Henry. Registrei essa informação em minha memória permanente: '{conteudo}'."

        texto_lower = texto_limpo.lower()

        # "o que você sabe sobre mim?"
        if any(p in texto_lower for p in ["o que você sabe sobre mim", "o que voce sabe sobre mim", "quais fatos você sabe", "minhas lembranças"]):
            fatos = self.listar_fatos()
            if not fatos:
                return "[EMOCAO:neutra] No momento não possuo nenhuma informação permanente registrada sobre você em meu banco de dados."
            linhas = [f"• **{f['chave']}**: {f['valor']} (registrado em {f['atualizado_em'][:10]})" for f in fatos]
            return "[EMOCAO:amigavel] Aqui está o que tenho registrado em minha memória permanente sobre você, Henry:\n" + "\n".join(linhas)

        # "esquece / esquecer fato X"
        match_esquece = re.search(r"^(?:gideon[, ]+)?esquec(?:a|e)\s+(?:o fato |a informacao |sobre )?(.+)$", texto_lower)
        if match_esquece:
            alvo = match_esquece.group(1).strip()
            removido = self.esquecer_fato(alvo)
            if removido:
                return f"[EMOCAO:satisfacao] A informação '{alvo}' foi excluída de minha memória permanente com sucesso."
            else:
                return f"[EMOCAO:neutra] Não encontrei nenhum fato registrado sob a chave '{alvo}'."

        return None

    def recuperar_lembrancas_para_prompt(self, texto_usuario: str) -> str:
        """Gera o bloco 'LEMBRANÇAS' com fatos e histórico para ser injetado no prompt de sistema."""
        linhas = []

        # 1. Recupera fatos existentes
        fatos = self.listar_fatos()
        if fatos:
            linhas.append("FATOS PERMANENTES:")
            for f in fatos[:10]:
                linhas.append(f"- {f['chave']}: {f['valor']} (atualizado em {f['atualizado_em'][:10]})")

        # 2. Busca trechos relevantes do histórico por similaridade textual FTS5
        historico_relevante = self.buscar_historico(texto_usuario, limite=3)
        if historico_relevante:
            linhas.append("\nHISTÓRICO RELEVANTE PESQUISADO:")
            for h in historico_relevante:
                quem_str = "Henry" if h["quem"] == "voce" else "Gideon"
                linhas.append(f"- [{h['quando'][:10]}] {quem_str} disse: \"{h['texto_original'][:120]}\"")

        return "\n".join(linhas).strip()
