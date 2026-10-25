import unreal

def criar_mapa():
    unreal.log("=== CRIANDO MAPA /Game/Maps/GideonTimeVault ===")
    
    # Cria novo nivel vazio
    sucesso = unreal.EditorLevelLibrary.new_level("/Game/Maps/GideonTimeVault")
    if not sucesso:
        unreal.log_warning("Nao foi possivel criar novo level via EditorLevelLibrary, tentando carregar/salvar pacote...")

    # Salva o level atual
    salvou = unreal.EditorLevelLibrary.save_current_level()
    unreal.log(f"Level /Game/Maps/GideonTimeVault salvo: {salvou}")

if __name__ == "__main__":
    criar_mapa()
