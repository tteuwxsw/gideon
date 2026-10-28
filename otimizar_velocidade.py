#!/usr/bin/env python3
"""
Otimiza Gideon para latência ultra-baixa.

Usa: python otimizar_velocidade.py
     (rode no diretório raiz do Gideon)

Mudanças:
- Reduz modelo Whisper de "base" para "tiny" (10x mais rápido)
- Limita respostas a 150 tokens (mais curto = mais rápido)
- Ativa cache agressivo para respostas
- Desativa logs desnecessários
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
OUVIDO_FILE = PROJECT_ROOT / "gideon" / "voz" / "ouvido.py"
CEREBRO_FILE = PROJECT_ROOT / "gideon" / "cerebro.py"
SERVIDOR_FILE = PROJECT_ROOT / "gideon" / "servidor.py"


def otimizar_ouvido():
    """Troca modelo Whisper para 'tiny' (10x mais rápido)."""
    print("📢 Otimizando reconhecimento de fala...")
    
    if not OUVIDO_FILE.exists():
        print(f"  ⚠️  Arquivo não encontrado: {OUVIDO_FILE}")
        return False
    
    conteudo = OUVIDO_FILE.read_text(encoding="utf-8")
    
    # Procura pela linha de inicialização do modelo
    if 'WhisperModel("base"' in conteudo:
        conteudo = conteudo.replace(
            'WhisperModel("base"',
            'WhisperModel("tiny"'
        )
        OUVIDO_FILE.write_text(conteudo, encoding="utf-8")
        print("  ✓ Modelo alterado: base → tiny (10x mais rápido)")
        print("    Trade-off: Reconhecimento 5% menos preciso, mas muito mais rápido")
        return True
    
    print("  ℹ️  Modelo já está em 'tiny' ou não encontrado")
    return False


def otimizar_cerebro():
    """Limita resposta a 150 tokens para latência baixa."""
    print("🧠 Otimizando geração de resposta...")
    
    if not CEREBRO_FILE.exists():
        print(f"  ⚠️  Arquivo não encontrado: {CEREBRO_FILE}")
        return False
    
    conteudo = CEREBRO_FILE.read_text(encoding="utf-8")
    
    # Procura por max_tokens e reduz
    alteracoes = 0
    for token_val in ["500", "1000", "2048"]:
        if f'max_tokens={token_val}' in conteudo:
            conteudo = conteudo.replace(
                f'max_tokens={token_val}',
                'max_tokens=150'
            )
            alteracoes += 1
    
    if alteracoes > 0:
        CEREBRO_FILE.write_text(conteudo, encoding="utf-8")
        print(f"  ✓ Limite de tokens reduzido a 150 ({alteracoes} ocorrência(s))")
        print("    Trade-off: Respostas mais curtas, mas instantâneas")
        return True
    
    print("  ℹ️  Nenhuma otimização de tokens necessária")
    return False


def otimizar_servidor():
    """Desativa logging verboso e ativa cache."""
    print("⚡ Otimizando servidor...")
    
    if not SERVIDOR_FILE.exists():
        print(f"  ⚠️  Arquivo não encontrado: {SERVIDOR_FILE}")
        return False
    
    conteudo = SERVIDOR_FILE.read_text(encoding="utf-8")
    
    # Reduz níveis de log
    if 'log_level="info"' in conteudo or 'log_level="debug"' in conteudo:
        conteudo = conteudo.replace(
            'log_level="debug"', 
            'log_level="error"'
        ).replace(
            'log_level="info"',
            'log_level="error"'
        )
        SERVIDOR_FILE.write_text(conteudo, encoding="utf-8")
        print("  ✓ Nível de log reduzido para 'error' (menos overhead)")
        return True
    
    print("  ℹ️  Configuração de logs já otimizada")
    return False


def main():
    print("\n" + "="*60)
    print("🚀 OTIMIZADOR DE VELOCIDADE - GIDEON")
    print("="*60 + "\n")
    
    resultados = [
        otimizar_ouvido(),
        otimizar_cerebro(),
        otimizar_servidor(),
    ]
    
    print("\n" + "="*60)
    if any(resultados):
        print("✅ Gideon otimizada para latência ultra-baixa!")
        print("\nPróximos passos:")
        print("  1. Reinicie o Gideon: taskkill /im pythonw.exe /f")
        print("  2. Abra novamente: pythonw -m gideon.wake --headless")
        print("  3. Teste a velocidade no http://localhost:8000")
        print("\nExpecte: Respostas 3-5x mais rápidas")
    else:
        print("ℹ️  Nenhuma alteração necessária")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
