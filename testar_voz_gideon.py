"""
Teste do efeito de voz da Gideon (The Flash).

Gera dois áudios:
1. Voz original (sem efeitos)
2. Voz com efeitos da Gideon

Execute e ouça a diferença!
"""

import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from gideon.voz.fala import SintetizadorVoz

def testar_voz_gideon():
    """Gera áudios de teste com e sem efeitos."""
    
    print("🎙️ TESTE DE VOZ DA GIDEON")
    print()
    print("Gerando áudios de teste...")
    print()
    
    # Texto de teste (igual da série)
    texto_teste = "Olá, Senhor Henry. Todos os sistemas estão operacionais. Como posso ajudá-lo hoje?"
    
    try:
        # Cria sintetizador
        sintetizador = SintetizadorVoz(pre_aquecer=False)
        
        print("1. Gerando voz ORIGINAL (sem efeitos)...")
        
        # Desativa efeitos temporariamente
        import gideon.voz.fala as fala_module
        original_sintetizar = fala_module.SintetizadorVoz.sintetizar_para_memoria
        
        def sintetizar_sem_efeito(self, texto):
            """Versão sem efeitos."""
            from gideon.voz.fala import formatar_prosodia_gideon
            texto_prosodia = formatar_prosodia_gideon(texto)
            if not texto_prosodia:
                return np.zeros(0, dtype=np.float32), 24000, True
            
            chave = self._chave_cache(texto_prosodia)
            em_cache = self._obter_do_cache(chave)
            if em_cache is not None:
                return em_cache[0], em_cache[1], True
            
            amostras, taxa = self._gerar_audio_voz_fixa(texto_prosodia)
            return amostras, taxa, False
        
        # Gera sem efeitos
        fala_module.SintetizadorVoz.sintetizar_para_memoria = sintetizar_sem_efeito
        sintetizador.falar(texto_teste)
        
        print("   ✅ Áudio original reproduzido")
        print()
        
        import time
        time.sleep(2)
        
        # Restaura função original (com efeitos)
        fala_module.SintetizadorVoz.sintetizar_para_memoria = original_sintetizar
        
        print("2. Gerando voz com EFEITOS DA GIDEON (The Flash)...")
        
        # Gera com efeitos
        sintetizador.falar(texto_teste)
        
        print("   ✅ Áudio com efeitos reproduzido")
        print()
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print()
        print("DIFERENÇAS aplicadas:")
        print("  • Pitch +6% (voz mais aguda)")
        print("  • Reverb espacial leve")
        print("  • Equalização (médios reforçados)")
        print("  • Filtro passa-alta (graves suaves)")
        print()
        print("Resultado: VOZ MUITO PARECIDA COM A GIDEON!")
        
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    testar_voz_gideon()
