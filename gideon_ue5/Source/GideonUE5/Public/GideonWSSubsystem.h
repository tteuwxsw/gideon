#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Tickable.h"
#include "IWebSocket.h"
#include "GideonWSSubsystem.generated.h"

USTRUCT(BlueprintType)
struct FGideonLipSyncFrame
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Gideon|LipSync")
	float Intensidade = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "Gideon|LipSync")
	FString VisemaPrincipal = TEXT("viseme_sil");

	UPROPERTY(BlueprintReadOnly, Category = "Gideon|LipSync")
	FString VisemaSecundario = TEXT("viseme_sil");

	UPROPERTY(BlueprintReadOnly, Category = "Gideon|LipSync")
	float PesoPrincipal = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "Gideon|LipSync")
	float PesoSecundario = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "Gideon|LipSync")
	float AberturaMandibula = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "Gideon|LipSync")
	float Arredondamento = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "Gideon|LipSync")
	float EnfaseSobrancelha = 0.0f;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnGideonEmocao, const FString&, Nome, float, Intensidade);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnGideonFalaInicio, const FString&, Texto);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnGideonLipSyncChunk, const FGideonLipSyncFrame&, Quadro);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnGideonFalaFim);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnGideonEstadoIA, const FString&, Estado);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnGideonModoJanela, const FString&, Modo);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnGideonOlhar, const FString&, Alvo, float, OlharX, float, OlharY);

/**
 * Subsistema assincrono de comunicacao WebSocket com o backend Python da Gideon (ws://127.0.0.1:8000/ws).
 * Autentica via header X-Gideon-Token lido de dados/auth_token.txt sem nunca expor o token na URL.
 */
UCLASS()
class GIDEONUE5_API UGideonWSSubsystem : public UGameInstanceSubsystem, public FTickableGameObject
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;
	virtual bool IsTickable() const override { return !IsTemplate(); }

	UFUNCTION(BlueprintCallable, Category = "Gideon|WebSocket")
	void ConectarAoBackend();

	UFUNCTION(BlueprintCallable, Category = "Gideon|WebSocket")
	void EnviarTelemetriaAvatar(
		int32 FPS,
		const FString& EstadoIA,
		const FString& Emocao,
		const FString& VisemaAtivo,
		float OlharX,
		float OlharY,
		const FString& Modo
	);

	UPROPERTY(BlueprintAssignable, Category = "Gideon|Eventos")
	FOnGideonEmocao OnEmocaoAlterada;

	UPROPERTY(BlueprintAssignable, Category = "Gideon|Eventos")
	FOnGideonFalaInicio OnFalaIniciada;

	UPROPERTY(BlueprintAssignable, Category = "Gideon|Eventos")
	FOnGideonLipSyncChunk OnLipSyncChunk;

	UPROPERTY(BlueprintAssignable, Category = "Gideon|Eventos")
	FOnGideonFalaFim OnFalaFinalizada;

	UPROPERTY(BlueprintAssignable, Category = "Gideon|Eventos")
	FOnGideonEstadoIA OnEstadoIAAlterado;

	UPROPERTY(BlueprintAssignable, Category = "Gideon|Eventos")
	FOnGideonModoJanela OnModoAlterado;

	UPROPERTY(BlueprintAssignable, Category = "Gideon|Eventos")
	FOnGideonOlhar OnOlharAlterado;

	TFunction<void(const TSharedPtr<FJsonObject>&)> OnConfigHologramaRecebida;

private:
	FString CarregarTokenLocal() const;
	void ProcessarMensagemJson(const FString& MensagemTexto);
	void EnviarEventoPronto();

	TSharedPtr<IWebSocket> Socket;
	FString UrlServidor = TEXT("ws://127.0.0.1:8000/ws");
	bool bConectado = false;
	float TempoDesdeUltimaTentativa = 0.0f;
	float IntervaloReconexao = 3.0f;
};
