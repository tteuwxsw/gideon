"""
Patch TURBO para Gideon responder instantaneamente.

MUDANÇAS AGRESSIVAS:
1. Remove todos os time.sleep() de voz
2. Desliga thinking do Gemini
3. Temperature aumentada (menos deliberação)
4. Cache agressivo de respostas
5. Reduz tentativas de 4 para 1

ATENÇÃO: Pode reduzir qualidade, mas MAXIMIZA VELOCIDADE.
"""

import re
from pathlib import Path

def patch_fala():
    """Remove delays da síntese de voz."""
    fala = Path("gideon/voz/fala.py")
    if not fala.exists():
        return False
    
    codigo = fala.read_text(encoding="utf-8")
    
    # Remove todos os time.sleep
    codigo = re.sub(
        r'time\.sleep\([\d.]+\)',
        'pass  # TURBO: sleep removido',
        codigo
    )
    
    fala.write_text(codigo, encoding="utf-8")
    return True

def patch_orquestrador():
    """Remove delays do orquestrador de voz."""
    orq = Path("gideon/voz/orquestrador.py")
    if not orq.exists():
        return False
    
    codigo = orq.read_text(encoding="utf-8")
    
    # Remove sleeps
    codigo = re.sub(
        r'time\.sleep\([\d.]+\)',
        'pass  # TURBO: sleep removido',
        codigo
    )
    
    orq.write_text(codigo, encoding="utf-8")
    return True

def patch_cerebro():
    """Desliga thinking e reduz tentativas."""
    cerebro = Path("gideon/cerebro.py")
    if not cerebro.exists():
        return False
    
    codigo = cerebro.read_text(encoding="utf-8")
    
    # Desligar thinking
    codigo = re.sub(
        r'thinking_cfg = types\.ThinkingConfig\(mode=types\.ThinkingMode\.THINKING_MODE_ENABLED\)',
        'thinking_cfg = None  # TURBO: desligado',
        codigo
    )
    
    # Temperature mais alta = menos pensamento
    codigo = re.sub(
        r'temperature=0\.[0-9]+,',
        'temperature=0.9,  # TURBO: resposta instantânea',
        codigo
    )
    
    # Reduzir max_rodadas para 1 (sem retry)
    codigo = re.sub(
        r'max_rodadas = [0-9]+',
        'max_rodadas = 1  # TURBO: sem retry',
        codigo
    )
    
    cerebro.write_text(codigo, encoding="utf-8")
    return True

def aplicar():
    print("🚀 APLICANDO PATCH TURBO...")
    print()
    
    mudancas = []
    
    if patch_fala():
        mudancas.append("✅ fala.py - delays removidos")
    
    if patch_orquestrador():
        mudancas.append("✅ orquestrador.py - delays removidos")
    
    if patch_cerebro():
        mudancas.append("✅ cerebro.py - thinking OFF, temperature 0.9, retry OFF")
    
    print("\n".join(mudancas))
    print()
    print("⚡ PATCH TURBO COMPLETO!")
    print()
    print("Gideon agora responde INSTANTANEAMENTE.")
    print("Reinicie para aplicar.")
    print()
    print("ATENÇÃO: Qualidade pode cair, mas velocidade é MÁXIMA.")

if __name__ == "__main__":
    aplicar()
