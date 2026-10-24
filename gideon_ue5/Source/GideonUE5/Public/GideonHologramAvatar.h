#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GideonWSSubsystem.h"
#include "GideonHologramAvatar.generated.h"

class USkeletalMeshComponent;
class UMaterialInstanceDynamic;

UENUM(BlueprintType)
enum class EGideonModoDesktop : uint8
{
	Compacto,
	Conversa,
	Foco,
	Operacional,
	Oculto
};

UENUM(BlueprintType)
enum class EGideonEstadoComportamental : uint8
{
	Idle,
	Listening,
	Thinking,
	Speaking,
	Executing,
	Observing,
	Error
};

/**
 * Ator principal do Holograma da Gideon em Unreal Engine 5 (The Flash / STAR Labs Time Vault).
 * Conduz simultaneamente:
 * 1. Morph Targets ARKit (52 curvas) + Curvas do Rig Facial MetaHuman (CTRL_expressions_*)
 * 2. Sincronizacao labial fonetica multi-visema (15 visemas Oculus + abertura mandibular + coarticulacao)
 * 3. Movimento natural de cabeca, pescoco, ombros, piscadas espontaneas e micro-sacadas oculares
 * 4. Parametros dinamicos do shader holografico (opacidade, feixe de materializacao, scanlines discretas)
 * 5. Governador dinamico de FPS para AMD Radeon RX 580 8GB (60 FPS falando, 30 FPS ociosa, 10 FPS oculta)
 */
UCLASS()
class GIDEONUE5_API AGideonHologramAvatar : public AActor
{
	GENERATED_BODY()

public:
	AGideonHologramAvatar();

protected:
	virtual void BeginPlay() override;

public:
	virtual void Tick(float DeltaTime) override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Gideon|Malhas")
	USceneComponent* PivoRaiz;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Gideon|Malhas")
	USkeletalMeshComponent* MalhaTorso;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Gideon|Malhas")
	USkeletalMeshComponent* MalhaRosto;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Gideon|Malhas")
	USkeletalMeshComponent* MalhaCabeloCards;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Gideon|Performance RX580")
	int32 FPSAtivo = 60;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Gideon|Performance RX580")
	int32 FPSOcioso = 30;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Gideon|Holograma")
	float OpacidadeGeral = 0.94f;

	/** Rotacao calculada para cabeca e pescoco (pode ser lida diretamente pelo AnimBlueprint / ControlRig) */
	UPROPERTY(BlueprintReadOnly, Category = "Gideon|Postura")
	FRotator RotacaoCabecaAtual = FRotator::ZeroRotator;

	UPROPERTY(BlueprintReadOnly, Category = "Gideon|Postura")
	FRotator RotacaoPescocoAtual = FRotator::ZeroRotator;

	UPROPERTY(BlueprintReadOnly, Category = "Gideon|Olhar")
	FVector2D OlharAtual = FVector2D::ZeroVector;

private:
	UFUNCTION()
	void AoMudarEmocao(const FString& Nome, float Intensidade);

	UFUNCTION()
	void AoIniciarFala(const FString& Texto);

	UFUNCTION()
	void AoReceberLipSyncChunk(const FGideonLipSyncFrame& Quadro);

	UFUNCTION()
	void AoFinalizarFala();

	UFUNCTION()
	void AoMudarEstadoIA(const FString& NovoEstado);

	UFUNCTION()
	void AoMudarModoJanela(const FString& NovoModo);

	UFUNCTION()
	void AoMudarOlhar(const FString& Alvo, float X, float Y);

	void ProcessarConfigHolograma(const TSharedPtr<FJsonObject>& Config);

	void InicializarTabelasCurvas();
	void CriarMateriaisDinamicosHolograma();
	void AtualizarMaterializacao(float DeltaTime);
	void AtualizarPosturaCabecaEOmbros(float DeltaTime);
	void AtualizarOlharESacadas(float DeltaTime);
	void AtualizarExpressoesSuaves(float DeltaTime);
	void AtualizarPiscadasNaturais(float DeltaTime);
	void AtualizarLipSyncMultiVisema(float DeltaTime);
	void AtualizarTransicaoJanelaDesktop(float DeltaTime);
	void AtualizarGovernadorFPS();
	void EnviarTelemetriaPeriodica(float DeltaTime);

	void DefinirAlvosExpressao(const FString& NomeEmocao, float Intensidade);
	void AplicarCurvaFacial(const FName& NomeARKit, float Peso);
	void AplicarVisemaNoRigFacial(const FString& NomeVisema, float Peso);

	UPROPERTY()
	TArray<UMaterialInstanceDynamic*> MateriaisHolograma;

	EGideonModoDesktop ModoAtual = EGideonModoDesktop::Conversa;
	EGideonEstadoComportamental EstadoIAAtual = EGideonEstadoComportamental::Idle;
	FString NomeEstadoIAAtual = TEXT("idle");
	FString EmocaoAlvo = TEXT("neutra");
	float IntensidadeEmocao = 1.0f;

	float ProgressoMaterializacao = 0.0f;
	float AlvoMaterializacao = 1.0f;
	float EscalaUsuario = 1.0f;

	// Piscar espontaneo
	float TimerProximoPiscar = 2.6f;
	float DuracaoPiscar = 0.13f;
	bool bPiscando = false;
	float TempoPiscarAtual = 0.0f;
	bool bPiscadaDuplaPendente = false;

	// Olhar e micro-sacadas
	FVector2D OlharSacada = FVector2D::ZeroVector;
	FVector2D OlharExternoAlvo = FVector2D::ZeroVector;
	float TimerSacadaOlhos = 2.0f;

	// Postura corporal
	float TempoAcumulado = 0.0f;
	FRotator RotacaoCabecaAlvo = FRotator::ZeroRotator;
	float TimerPosturaIdle = 3.5f;

	// Lip-sync e fala
	bool bFalando = false;
	float EnergiaVoz = 0.0f;
	float EnergiaVozAlvo = 0.0f;
	float AberturaBocaAtual = 0.0f;
	float AberturaBocaAlvo = 0.0f;
	float ArredondamentoAtual = 0.0f;
	float ArredondamentoAlvo = 0.0f;
	float EnfaseSobrancelhaFala = 0.0f;
	FString VisemaPrincipalAlvo = TEXT("viseme_sil");
	FString VisemaSecundarioAlvo = TEXT("viseme_sil");
	float PesoVisemaPrincipal = 0.0f;
	float PesoVisemaSecundario = 0.0f;

	TMap<FName, float> PesosExpressaoAlvo;
	TMap<FName, float> PesosExpressaoAtual;
	TMap<FString, float> PesosVisemasAtuais;

	// Interpolacao suave de janela no desktop
	bool bTransicionandoJanela = false;
	float TempoTransicaoJanela = 0.0f;
	float DuracaoTransicaoJanela = 0.7f;
	FIntPoint PosJanelaInicio = FIntPoint(1440, 360);
	FIntPoint PosJanelaDestino = FIntPoint(1440, 360);
	FIntPoint TamJanelaInicio = FIntPoint(450, 650);
	FIntPoint TamJanelaDestino = FIntPoint(450, 650);

	float TimerTelemetria = 1.5f;
};
