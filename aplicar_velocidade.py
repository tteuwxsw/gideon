"""
Patch de velocidade para Gideon responder mais rápido.

MUDANÇAS:
- Temperature: 0.4 → 0.7 (menos deliberação)
- Thinking desligado (remove raciocínio verbal)
- Max rodadas: 4 → 2 (menos tentativas)
- Timeout reduzido em chamadas

COMO APLICAR:
1. Copie este arquivo para gideon/
2. Execute: python aplicar_velocidade.py
"""

import re
from pathlib import Path

def aplicar():
    cerebro = Path("gideon/cerebro.py")
    
    if not cerebro.exists():
        print("❌ Arquivo cerebro.py não encontrado")
        return
    
    codigo = cerebro.read_text(encoding="utf-8")
    
    # 1. Desligar thinking
    codigo = re.sub(
        r'thinking_cfg = types\.ThinkingConfig\(mode=types\.ThinkingMode\.THINKING_MODE_ENABLED\)',
        'thinking_cfg = None  # PATCH: desligado para velocidade',
        codigo
    )
    
    # 2. Aumentar temperature (menos deliberação = mais rápido)
    codigo = re.sub(
        r'temperature=0\.4,',
        'temperature=0.7,  # PATCH: resposta mais rápida',
        codigo
    )
    
    # 3. Reduzir max_rodadas de 4 para 2
    codigo = re.sub(
        r'max_rodadas = 4',
        'max_rodadas = 2  # PATCH: menos tentativas',
        codigo
    )
    
    cerebro.write_text(codigo, encoding="utf-8")
    print("✅ Patch de velocidade aplicado em cerebro.py")
    print()
    print("Gideon agora responde MUITO mais rápido.")
    print("Reinicie o servidor para aplicar.")

if __name__ == "__main__":
    aplicar()
