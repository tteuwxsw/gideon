#include "GideonGameMode.h"
#include "GideonHologramAvatar.h"
#include "GideonUE5.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Engine/PointLight.h"
#include "Engine/SpotLight.h"
#include "Components/PointLightComponent.h"
#include "Components/SpotLightComponent.h"
#include "Kismet/GameplayStatics.h"
#include "GameFramework/PlayerController.h"

AGideonGameMode::AGideonGameMode()
{
	DefaultPawnClass = nullptr;
}

void AGideonGameMode::StartPlay()
{
	Super::StartPlay();

	GarantirAvatarPresente();
	ConfigurarCameraTimeVault();
	ConfigurarIluminacaoHolografica();

	UE_LOG(LogGideonUE5, Log, TEXT("[Gideon GameMode] Cena Time Vault inicializada com enquadramento de camera e iluminacao holografica 4-point."));
}

void AGideonGameMode::GarantirAvatarPresente()
{
	TArray<AActor*> AtoresEncontrados;
	UGameplayStatics::GetAllActorsOfClass(GetWorld(), AGideonHologramAvatar::StaticClass(), AtoresEncontrados);

	if (AtoresEncontrados.Num() > 0)
	{
		AvatarInstancia = Cast<AGideonHologramAvatar>(AtoresEncontrados[0]);
	}
	else if (GetWorld())
	{
		FActorSpawnParameters SpawnParams;
		SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		AvatarInstancia = GetWorld()->SpawnActor<AGideonHologramAvatar>(
			AGideonHologramAvatar::StaticClass(),
			FVector(0.0f, 0.0f, 0.0f),
			FRotator(0.0f, 0.0f, 0.0f),
			SpawnParams
		);
	}
}

void AGideonGameMode::ConfigurarCameraTimeVault()
{
	UWorld* World = GetWorld();
	if (!World) return;

	// Enquadramento de retrato focal fechado (85mm focal equiv, FOV 26.0f)
	// Posicionada em frente a face da Gideon (altura ~146cm)
	const FVector PosCamera(145.0f, 0.0f, 146.0f);
	const FRotator RotCamera(0.0f, 180.0f, 0.0f);

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	CameraRetrato = World->SpawnActor<ACameraActor>(ACameraActor::StaticClass(), PosCamera, RotCamera, Params);

	if (CameraRetrato)
	{
		UCameraComponent* CamComp = CameraRetrato->GetCameraComponent();
		if (CamComp)
		{
			CamComp->SetFieldOfView(26.0f);
			CamComp->PostProcessSettings.bOverride_MotionBlurAmount = true;
			CamComp->PostProcessSettings.MotionBlurAmount = 0.0f;
			CamComp->PostProcessSettings.bOverride_VignetteIntensity = true;
			CamComp->PostProcessSettings.VignetteIntensity = 0.0f;
			CamComp->PostProcessSettings.bOverride_BloomIntensity = true;
			CamComp->PostProcessSettings.BloomIntensity = 0.22f; // Leve brilho etereo holografico
		}

		APlayerController* PC = UGameplayStatics::GetPlayerController(World, 0);
		if (PC)
		{
			PC->SetViewTarget(CameraRetrato);
			PC->bShowMouseCursor = false;
			PC->SetInputMode(FInputModeGameAndUI());
		}
	}
}

void AGideonGameMode::ConfigurarIluminacaoHolografica()
{
	UWorld* World = GetWorld();
	if (!World) return;

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	// 1. Key Light (Ciano gelo suave) - Ilumina a testa, macas do rosto, ponte nasal e olhos
	LuzKeyCyan = World->SpawnActor<APointLight>(APointLight::StaticClass(), FVector(85.0f, -42.0f, 162.0f), FRotator::ZeroRotator, Params);
	if (LuzKeyCyan)
	{
		if (UPointLightComponent* PLC = Cast<UPointLightComponent>(LuzKeyCyan->GetLightComponent()))
		{
			PLC->SetLightColor(FLinearColor(0.28f, 0.85f, 1.0f));
			PLC->SetIntensity(1750.0f);
			PLC->SetAttenuationRadius(380.0f);
			PLC->SetCastShadows(false); // Otimizacao RX 580: holograma autoemissivo dispensa mapas de sombra pesados
		}
	}

	// 2. Fill Light (Azul profundo STAR Labs) - Preserva sombras suaves e volume tridimensional do rosto
	LuzFillAzul = World->SpawnActor<APointLight>(APointLight::StaticClass(), FVector(75.0f, 48.0f, 138.0f), FRotator::ZeroRotator, Params);
	if (LuzFillAzul)
	{
		if (UPointLightComponent* PLC = Cast<UPointLightComponent>(LuzFillAzul->GetLightComponent()))
		{
			PLC->SetLightColor(FLinearColor(0.06f, 0.42f, 0.95f));
			PLC->SetIntensity(780.0f);
			PLC->SetAttenuationRadius(350.0f);
			PLC->SetCastShadows(false);
		}
	}

	// 3. Rim / Backlight (Ciano eletrico) - Silhueta luminosa no cabelo, orelhas, pescoco e queixo
	LuzRimContorno = World->SpawnActor<APointLight>(APointLight::StaticClass(), FVector(-60.0f, 8.0f, 172.0f), FRotator::ZeroRotator, Params);
	if (LuzRimContorno)
	{
		if (UPointLightComponent* PLC = Cast<UPointLightComponent>(LuzRimContorno->GetLightComponent()))
		{
			PLC->SetLightColor(FLinearColor(0.45f, 0.96f, 1.0f));
			PLC->SetIntensity(2800.0f);
			PLC->SetAttenuationRadius(420.0f);
			PLC->SetCastShadows(false);
		}
	}

	// 4. Feixe Projetor Inferior (STAR Labs Time Vault Pedestal) - Feixe ascendente da base para o queixo
	const FVector PosProjetor(0.0f, 0.0f, 112.0f);
	const FRotator RotProjetor(68.0f, 0.0f, 0.0f); // Apontado para cima em direcao ao pescoco e rosto
	LuzProjetorBase = World->SpawnActor<ASpotLight>(ASpotLight::StaticClass(), PosProjetor, RotProjetor, Params);
	if (LuzProjetorBase)
	{
		if (USpotLightComponent* SLC = Cast<USpotLightComponent>(LuzProjetorBase->GetLightComponent()))
		{
			SLC->SetLightColor(FLinearColor(0.05f, 0.72f, 1.0f));
			SLC->SetIntensity(2200.0f);
			SLC->SetInnerConeAngle(16.0f);
			SLC->SetOuterConeAngle(34.0f);
			SLC->SetAttenuationRadius(260.0f);
			SLC->SetCastShadows(false);
		}
	}
}
