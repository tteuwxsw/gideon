#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GideonGameMode.generated.h"

class AGideonHologramAvatar;
class ACameraActor;
class APointLight;
class ASpotLight;

/**
 * GameMode principal da Gideon em Unreal Engine 5.
 * Configura automaticamente:
 * 1. Enquadramento de camera cinematografica estilo STAR Labs Time Vault (The Flash)
 * 2. Rig de iluminacao holografica em 4 pontos (Key Cyan, Fill Deep Blue, Rim Electric Cyan, Upward Projector)
 * 3. Spawn e gerenciamento do ator holografico AGideonHologramAvatar
 */
UCLASS()
class GIDEONUE5_API AGideonGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AGideonGameMode();

protected:
	virtual void StartPlay() override;

private:
	void ConfigurarCameraTimeVault();
	void ConfigurarIluminacaoHolografica();
	void GarantirAvatarPresente();

	UPROPERTY()
	AGideonHologramAvatar* AvatarInstancia = nullptr;

	UPROPERTY()
	ACameraActor* CameraRetrato = nullptr;

	UPROPERTY()
	APointLight* LuzKeyCyan = nullptr;

	UPROPERTY()
	APointLight* LuzFillAzul = nullptr;

	UPROPERTY()
	APointLight* LuzRimContorno = nullptr;

	UPROPERTY()
	ASpotLight* LuzProjetorBase = nullptr;
};
