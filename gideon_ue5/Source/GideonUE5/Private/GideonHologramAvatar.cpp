#include "GideonHologramAvatar.h"
#include "GideonDesktopWindow.h"
#include "GideonUE5.h"
#include "Components/SkeletalMeshComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Dom/JsonObject.h"

static const FName CURVAS_EXPRESSAO_ARKIT[] = {
	TEXT("mouthSmileLeft"), TEXT("mouthSmileRight"),
	TEXT("mouthDimpleLeft"), TEXT("mouthDimpleRight"),
	TEXT("cheekSquintLeft"), TEXT("cheekSquintRight"),
	TEXT("browInnerUp"), TEXT("browOuterUpLeft"), TEXT("browOuterUpRight"),
	TEXT("browDownLeft"), TEXT("browDownRight"),
	TEXT("eyeWideLeft"), TEXT("eyeWideRight"),
	TEXT("eyeSquintLeft"), TEXT("eyeSquintRight"),
	TEXT("mouthFrownLeft"), TEXT("mouthFrownRight"),
	TEXT("mouthPressLeft"), TEXT("mouthPressRight")
};

static const TCHAR* LISTA_VISEMAS_OCULUS[] = {
	TEXT("viseme_sil"), TEXT("viseme_PP"), TEXT("viseme_FF"), TEXT("viseme_TH"), TEXT("viseme_DD"),
	TEXT("viseme_kk"), TEXT("viseme_CH"), TEXT("viseme_SS"), TEXT("viseme_nn"), TEXT("viseme_RR"),
	TEXT("viseme_aa"), TEXT("viseme_E"), TEXT("viseme_I"), TEXT("viseme_O"), TEXT("viseme_U")
};

AGideonHologramAvatar::AGideonHologramAvatar()
{
	PrimaryActorTick.bCanEverTick = true;

	PivoRaiz = CreateDefaultSubobject<USceneComponent>(TEXT("PivoRaiz"));
	RootComponent = PivoRaiz;

	MalhaTorso = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("MalhaTorso"));
	MalhaTorso->SetupAttachment(PivoRaiz);
	MalhaTorso->ForcedLodModel = 2; // Forca LOD 2 na RX 580 para preservar VRAM sem perda perceptivel

	MalhaRosto = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("MalhaRosto"));
	MalhaRosto->SetupAttachment(MalhaTorso);
	MalhaRosto->ForcedLodModel = 1; // Rosto em alta definicao (LOD 1) com Hair Cards

	MalhaCabeloCards = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("MalhaCabeloCards"));
	MalhaCabeloCards->SetupAttachment(MalhaRosto);
	MalhaCabeloCards->ForcedLodModel = 2;
}

void AGideonHologramAvatar::BeginPlay()
{
	Super::BeginPlay();

	InicializarTabelasCurvas();
	CriarMateriaisDinamicosHolograma();
	FGideonDesktopWindow::ConfigurarJanelaTransparenteDesktop(true, true);
	DefinirAlvosExpressao(TEXT("neutra"), 1.0f);
	AtualizarGovernadorFPS();

	if (UGameInstance* GI = GetGameInstance())
	{
		if (UGideonWSSubsystem* WS = GI->GetSubsystem<UGideonWSSubsystem>())
		{
			WS->OnEmocaoAlterada.AddDynamic(this, &AGideonHologramAvatar::AoMudarEmocao);
			WS->OnFalaIniciada.AddDynamic(this, &AGideonHologramAvatar::AoIniciarFala);
			WS->OnLipSyncChunk.AddDynamic(this, &AGideonHologramAvatar::AoReceberLipSyncChunk);
			WS->OnFalaFinalizada.AddDynamic(this, &AGideonHologramAvatar::AoFinalizarFala);
			WS->OnEstadoIAAlterado.AddDynamic(this, &AGideonHologramAvatar::AoMudarEstadoIA);
			WS->OnModoAlterado.AddDynamic(this, &AGideonHologramAvatar::AoMudarModoJanela);
			WS->OnOlharAlterado.AddDynamic(this, &AGideonHologramAvatar::AoMudarOlhar);
			WS->OnConfigHologramaRecebida = [this](const TSharedPtr<FJsonObject>& Config)
			{
				ProcessarConfigHolograma(Config);
			};
		}
	}
}

void AGideonHologramAvatar::InicializarTabelasCurvas()
{
	for (const FName& Nome : CURVAS_EXPRESSAO_ARKIT)
	{
		PesosExpressaoAlvo.Add(Nome, 0.0f);
		PesosExpressaoAtual.Add(Nome, 0.0f);
	}
	for (const TCHAR* Vis : LISTA_VISEMAS_OCULUS)
	{
		PesosVisemasAtuais.Add(FString(Vis), 0.0f);
	}
}

void AGideonHologramAvatar::CriarMateriaisDinamicosHolograma()
{
	MateriaisHolograma.Empty();
	USkeletalMeshComponent* Componentes[] = { MalhaTorso, MalhaRosto, MalhaCabeloCards };
	for (USkeletalMeshComponent* Comp : Componentes)
	{
		if (!Comp) continue;
		const int32 NumMats = Comp->GetNumMaterials();
		for (int32 i = 0; i < NumMats; ++i)
		{
			if (UMaterialInstanceDynamic* MID = Comp->CreateAndSetMaterialInstanceDynamic(i))
			{
				MID->SetScalarParameterValue(TEXT("OpacidadeGeral"), OpacidadeGeral);
				MID->SetScalarParameterValue(TEXT("ProgressoMaterializacao"), ProgressoMaterializacao);
				MID->SetVectorParameterValue(TEXT("CorHolograma"), FLinearColor(0.08f, 0.68f, 0.98f, 0.94f));
				MID->SetVectorParameterValue(TEXT("CorFresnel"), FLinearColor(0.52f, 0.95f, 1.0f, 1.0f));
				MID->SetScalarParameterValue(TEXT("IntensidadeScanlines"), 0.032f);
				MID->SetScalarParameterValue(TEXT("PreservarDefinicaoFacial"), 0.88f);
				MateriaisHolograma.Add(MID);
			}
		}
	}
}

void AGideonHologramAvatar::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);

	TempoAcumulado += DeltaTime;
	AtualizarMaterializacao(DeltaTime);
	AtualizarPosturaCabecaEOmbros(DeltaTime);
	AtualizarOlharESacadas(DeltaTime);
	AtualizarExpressoesSuaves(DeltaTime);
	AtualizarPiscadasNaturais(DeltaTime);
	AtualizarLipSyncMultiVisema(DeltaTime);
	AtualizarTransicaoJanelaDesktop(DeltaTime);
	EnviarTelemetriaPeriodica(DeltaTime);
}

void AGideonHologramAvatar::AtualizarMaterializacao(float DeltaTime)
{
	if (!FMath::IsNearlyEqual(ProgressoMaterializacao, AlvoMaterializacao, 0.002f))
	{
		ProgressoMaterializacao = FMath::FInterpConstantTo(ProgressoMaterializacao, AlvoMaterializacao, DeltaTime, 1.8f);
		for (UMaterialInstanceDynamic* MID : MateriaisHolograma)
		{
			if (MID)
			{
				MID->SetScalarParameterValue(TEXT("ProgressoMaterializacao"), ProgressoMaterializacao);
			}
		}
		SetActorHiddenInGame(ProgressoMaterializacao <= 0.01f && AlvoMaterializacao == 0.0f);
	}
}

void AGideonHologramAvatar::AtualizarPosturaCabecaEOmbros(float DeltaTime)
{
	// Respiracao sutil nos ombros/busto
	const float FaseResp = TempoAcumulado * 1.45f;
	FVector Loc = PivoRaiz->GetRelativeLocation();
	Loc.Z = FMath::Sin(FaseResp) * 0.42f;
	PivoRaiz->SetRelativeLocation(Loc);

	TimerPosturaIdle -= DeltaTime;
	if (TimerPosturaIdle <= 0.0f)
	{
		TimerPosturaIdle = FMath::FRandRange(3.2f, 6.2f);
		switch (EstadoIAAtual)
		{
		case EGideonEstadoComportamental::Listening:
			RotacaoCabecaAlvo = FRotator(1.8f, FMath::FRandRange(-1.5f, 1.5f), 2.3f);
			break;
		case EGideonEstadoComportamental::Thinking:
			RotacaoCabecaAlvo = FRotator(-2.6f, 4.0f, -1.4f);
			break;
		default:
			RotacaoCabecaAlvo = FRotator(
				FMath::FRandRange(-1.8f, 2.0f),
				FMath::FRandRange(-4.2f, 4.2f),
				FMath::FRandRange(-1.6f, 1.6f)
			);
			break;
		}
	}

	float AcenoPitch = 0.0f;
	float AcenoRoll = 0.0f;
	if (bFalando && EnergiaVoz > 0.05f)
	{
		AcenoPitch = FMath::Sin(TempoAcumulado * 6.5f) * 1.8f * EnergiaVoz;
		AcenoRoll = FMath::Cos(TempoAcumulado * 4.2f) * 1.1f * EnergiaVoz;
	}

	const FRotator AlvoCombinado(
		RotacaoCabecaAlvo.Pitch + AcenoPitch + (OlharAtual.Y * 9.0f),
		RotacaoCabecaAlvo.Yaw - (OlharAtual.X * 13.0f),
		RotacaoCabecaAlvo.Roll + AcenoRoll
	);

	RotacaoCabecaAtual = FMath::RInterpTo(RotacaoCabecaAtual, AlvoCombinado, DeltaTime, 2.6f);
	RotacaoPescocoAtual = RotacaoCabecaAtual * 0.42f;
}

void AGideonHologramAvatar::AtualizarOlharESacadas(float DeltaTime)
{
	TimerSacadaOlhos -= DeltaTime;
	if (TimerSacadaOlhos <= 0.0f)
	{
		TimerSacadaOlhos = FMath::FRandRange(1.5f, 3.6f);
		const float Amp = (EstadoIAAtual == EGideonEstadoComportamental::Listening || EstadoIAAtual == EGideonEstadoComportamental::Speaking)
			? 0.022f
			: 0.042f;
		OlharSacada = FVector2D(FMath::FRandRange(-Amp, Amp), FMath::FRandRange(-Amp * 0.7f, Amp * 0.7f));
	}

	FVector2D BaseOlhar = FVector2D::ZeroVector;
	if (EstadoIAAtual == EGideonEstadoComportamental::Thinking)
	{
		BaseOlhar = FVector2D(0.08f, 0.05f);
	}
	else if (EstadoIAAtual != EGideonEstadoComportamental::Listening && EstadoIAAtual != EGideonEstadoComportamental::Speaking)
	{
		BaseOlhar = OlharExternoAlvo;
	}

	const FVector2D AlvoFinal(
		FMath::Clamp(BaseOlhar.X + OlharSacada.X, -0.16f, 0.16f),
		FMath::Clamp(BaseOlhar.Y + OlharSacada.Y, -0.11f, 0.11f)
	);
	OlharAtual = FMath::Vector2DInterpTo(OlharAtual, AlvoFinal, DeltaTime, 6.0f);

	const float Dir = FMath::Max(0.0f, OlharAtual.X);
	const float Esq = FMath::Max(0.0f, -OlharAtual.X);
	const float Cima = FMath::Max(0.0f, OlharAtual.Y);
	const float Baixo = FMath::Max(0.0f, -OlharAtual.Y);

	AplicarCurvaFacial(TEXT("eyeLookOutRight"), Dir);
	AplicarCurvaFacial(TEXT("eyeLookInLeft"), Dir);
	AplicarCurvaFacial(TEXT("eyeLookOutLeft"), Esq);
	AplicarCurvaFacial(TEXT("eyeLookInRight"), Esq);
	AplicarCurvaFacial(TEXT("eyeLookUpLeft"), Cima);
	AplicarCurvaFacial(TEXT("eyeLookUpRight"), Cima);
	AplicarCurvaFacial(TEXT("eyeLookDownLeft"), Baixo);
	AplicarCurvaFacial(TEXT("eyeLookDownRight"), Baixo);
}

void AGideonHologramAvatar::AtualizarExpressoesSuaves(float DeltaTime)
{
	for (const FName& Nome : CURVAS_EXPRESSAO_ARKIT)
	{
		float Alvo = PesosExpressaoAlvo.FindRef(Nome);
		if (Nome == TEXT("browInnerUp") && bFalando)
		{
			Alvo = FMath::Clamp(Alvo + EnfaseSobrancelhaFala, 0.0f, 0.45f);
		}
		float Atual = PesosExpressaoAtual.FindRef(Nome);
		if (!FMath::IsNearlyEqual(Atual, Alvo, 0.001f))
		{
			Atual = FMath::FInterpTo(Atual, Alvo, DeltaTime, 7.0f);
			PesosExpressaoAtual.Add(Nome, Atual);
			AplicarCurvaFacial(Nome, Atual);
		}
	}
}

void AGideonHologramAvatar::AtualizarPiscadasNaturais(float DeltaTime)
{
	if (!bPiscando)
	{
		TimerProximoPiscar -= DeltaTime;
		if (TimerProximoPiscar <= 0.0f)
		{
			bPiscando = true;
			TempoPiscarAtual = 0.0f;
			if (bPiscadaDuplaPendente)
			{
				bPiscadaDuplaPendente = false;
				TimerProximoPiscar = FMath::FRandRange(3.0f, 5.8f);
			}
			else
			{
				bPiscadaDuplaPendente = FMath::FRand() < 0.18f;
				TimerProximoPiscar = bPiscadaDuplaPendente ? 0.18f : FMath::FRandRange(2.4f, 5.4f);
			}
		}
	}
	else
	{
		TempoPiscarAtual += DeltaTime;
		const float Progresso = TempoPiscarAtual / DuracaoPiscar;
		if (Progresso >= 1.0f)
		{
			bPiscando = false;
			AplicarCurvaFacial(TEXT("eyeBlinkLeft"), 0.0f);
			AplicarCurvaFacial(TEXT("eyeBlinkRight"), 0.0f);
		}
		else
		{
			const float PesoPiscar = FMath::Sin(Progresso * PI);
			AplicarCurvaFacial(TEXT("eyeBlinkLeft"), PesoPiscar);
			AplicarCurvaFacial(TEXT("eyeBlinkRight"), PesoPiscar);
		}
	}
}

void AGideonHologramAvatar::AtualizarLipSyncMultiVisema(float DeltaTime)
{
	const float VelLabios = 22.0f;
	if (bFalando && EnergiaVozAlvo > 0.01f)
	{
		EnergiaVoz = FMath::FInterpTo(EnergiaVoz, EnergiaVozAlvo, DeltaTime, VelLabios);
		AberturaBocaAtual = FMath::FInterpTo(AberturaBocaAtual, AberturaBocaAlvo, DeltaTime, VelLabios);
		ArredondamentoAtual = FMath::FInterpTo(ArredondamentoAtual, ArredondamentoAlvo, DeltaTime, VelLabios);
	}
	else
	{
		EnergiaVoz = FMath::FInterpTo(EnergiaVoz, 0.0f, DeltaTime, 15.0f);
		AberturaBocaAtual = FMath::FInterpTo(AberturaBocaAtual, 0.0f, DeltaTime, 15.0f);
		ArredondamentoAtual = FMath::FInterpTo(ArredondamentoAtual, 0.0f, DeltaTime, 15.0f);
		VisemaPrincipalAlvo = TEXT("viseme_sil");
		VisemaSecundarioAlvo = TEXT("viseme_sil");
		PesoVisemaPrincipal = 0.0f;
		PesoVisemaSecundario = 0.0f;
		EnfaseSobrancelhaFala = FMath::FInterpTo(EnfaseSobrancelhaFala, 0.0f, DeltaTime, 10.0f);
	}

	AplicarCurvaFacial(TEXT("jawOpen"), AberturaBocaAtual);
	AplicarCurvaFacial(TEXT("mouthFunnel"), ArredondamentoAtual);

	for (const TCHAR* VisPtr : LISTA_VISEMAS_OCULUS)
	{
		const FString Vis(VisPtr);
		float AlvoV = 0.0f;
		if (Vis == VisemaPrincipalAlvo) AlvoV = PesoVisemaPrincipal;
		else if (Vis == VisemaSecundarioAlvo) AlvoV = PesoVisemaSecundario;

		float AtualV = PesosVisemasAtuais.FindRef(Vis);
		if (!FMath::IsNearlyEqual(AtualV, AlvoV, 0.002f))
		{
			AtualV = FMath::FInterpTo(AtualV, AlvoV, DeltaTime, VelLabios);
			PesosVisemasAtuais.Add(Vis, AtualV);
			AplicarVisemaNoRigFacial(Vis, AtualV);
		}
	}
}

void AGideonHologramAvatar::AplicarCurvaFacial(const FName& NomeARKit, float Peso)
{
	const float Valor = FMath::Clamp(Peso, 0.0f, 1.0f);
	if (MalhaRosto)
	{
		MalhaRosto->SetMorphTarget(NomeARKit, Valor);

		// Compatibilidade direta com curvas do MetaHuman Facial Rig (CTRL_expressions_*)
		if (NomeARKit == TEXT("jawOpen"))
		{
			MalhaRosto->SetMorphTarget(TEXT("CTRL_expressions_jawOpen"), Valor);
		}
		else if (NomeARKit == TEXT("eyeBlinkLeft"))
		{
			MalhaRosto->SetMorphTarget(TEXT("CTRL_expressions_eyeBlinkL"), Valor);
		}
		else if (NomeARKit == TEXT("eyeBlinkRight"))
		{
			MalhaRosto->SetMorphTarget(TEXT("CTRL_expressions_eyeBlinkR"), Valor);
		}
		else if (NomeARKit == TEXT("mouthFunnel"))
		{
			MalhaRosto->SetMorphTarget(TEXT("CTRL_expressions_mouthFunnelDL"), Valor);
			MalhaRosto->SetMorphTarget(TEXT("CTRL_expressions_mouthFunnelDR"), Valor);
			MalhaRosto->SetMorphTarget(TEXT("CTRL_expressions_mouthFunnelUL"), Valor);
			MalhaRosto->SetMorphTarget(TEXT("CTRL_expressions_mouthFunnelUR"), Valor);
		}
	}
}

void AGideonHologramAvatar::AplicarVisemaNoRigFacial(const FString& NomeVisema, float Peso)
{
	const float V = FMath::Clamp(Peso, 0.0f, 1.0f);
	if (!MalhaRosto) return;

	// 1. Aplica diretamente no morph target Oculus caso exista na malha
	MalhaRosto->SetMorphTarget(FName(*NomeVisema), V);

	// 2. Traduz o visema Oculus para combinacoes anatomicas ARKit / MetaHuman (para malhas MetaHuman puras)
	if (NomeVisema == TEXT("viseme_PP"))
	{
		MalhaRosto->SetMorphTarget(TEXT("mouthClose"), V * 0.75f);
		MalhaRosto->SetMorphTarget(TEXT("mouthPressLeft"), V * 0.55f);
		MalhaRosto->SetMorphTarget(TEXT("mouthPressRight"), V * 0.55f);
	}
	else if (NomeVisema == TEXT("viseme_FF"))
	{
		MalhaRosto->SetMorphTarget(TEXT("mouthRollLower"), V * 0.65f);
		MalhaRosto->SetMorphTarget(TEXT("mouthUpperUpLeft"), V * 0.25f);
		MalhaRosto->SetMorphTarget(TEXT("mouthUpperUpRight"), V * 0.25f);
	}
	else if (NomeVisema == TEXT("viseme_SS") || NomeVisema == TEXT("viseme_I"))
	{
		MalhaRosto->SetMorphTarget(TEXT("mouthStretchLeft"), V * 0.42f);
		MalhaRosto->SetMorphTarget(TEXT("mouthStretchRight"), V * 0.42f);
	}
	else if (NomeVisema == TEXT("viseme_O") || NomeVisema == TEXT("viseme_U") || NomeVisema == TEXT("viseme_CH"))
	{
		MalhaRosto->SetMorphTarget(TEXT("mouthPucker"), V * 0.52f);
	}
}

void AGideonHologramAvatar::DefinirAlvosExpressao(const FString& NomeEmocao, float Intensidade)
{
	for (const FName& Nome : CURVAS_EXPRESSAO_ARKIT)
	{
		PesosExpressaoAlvo.Add(Nome, 0.0f);
	}

	const float K = FMath::Clamp(Intensidade, 0.2f, 1.0f);
	if (NomeEmocao == TEXT("amigavel") || NomeEmocao == TEXT("satisfacao") || NomeEmocao == TEXT("humor"))
	{
		PesosExpressaoAlvo.Add(TEXT("mouthSmileLeft"), 0.22f * K);
		PesosExpressaoAlvo.Add(TEXT("mouthSmileRight"), 0.22f * K);
		PesosExpressaoAlvo.Add(TEXT("cheekSquintLeft"), 0.11f * K);
		PesosExpressaoAlvo.Add(TEXT("cheekSquintRight"), 0.11f * K);
		PesosExpressaoAlvo.Add(TEXT("browInnerUp"), 0.06f * K);
	}
	else if (NomeEmocao == TEXT("curiosidade") || NomeEmocao == TEXT("duvida"))
	{
		PesosExpressaoAlvo.Add(TEXT("browInnerUp"), 0.24f * K);
		PesosExpressaoAlvo.Add(TEXT("browOuterUpRight"), 0.18f * K);
		PesosExpressaoAlvo.Add(TEXT("eyeSquintLeft"), 0.08f * K);
	}
	else if (NomeEmocao == TEXT("surpresa"))
	{
		PesosExpressaoAlvo.Add(TEXT("eyeWideLeft"), 0.16f * K);
		PesosExpressaoAlvo.Add(TEXT("eyeWideRight"), 0.16f * K);
		PesosExpressaoAlvo.Add(TEXT("browInnerUp"), 0.28f * K);
	}
	else if (NomeEmocao == TEXT("concentracao"))
	{
		PesosExpressaoAlvo.Add(TEXT("browDownLeft"), 0.20f * K);
		PesosExpressaoAlvo.Add(TEXT("browDownRight"), 0.20f * K);
		PesosExpressaoAlvo.Add(TEXT("eyeSquintLeft"), 0.10f * K);
		PesosExpressaoAlvo.Add(TEXT("eyeSquintRight"), 0.10f * K);
	}
	else if (NomeEmocao == TEXT("preocupacao"))
	{
		PesosExpressaoAlvo.Add(TEXT("browInnerUp"), 0.26f * K);
		PesosExpressaoAlvo.Add(TEXT("mouthFrownLeft"), 0.08f * K);
		PesosExpressaoAlvo.Add(TEXT("mouthFrownRight"), 0.08f * K);
	}
	else
	{
		PesosExpressaoAlvo.Add(TEXT("mouthSmileLeft"), 0.06f);
		PesosExpressaoAlvo.Add(TEXT("mouthSmileRight"), 0.06f);
		PesosExpressaoAlvo.Add(TEXT("browInnerUp"), 0.04f);
	}
}

void AGideonHologramAvatar::AtualizarGovernadorFPS()
{
	if (!GEngine) return;
	if (ModoAtual == EGideonModoDesktop::Oculto)
	{
		GEngine->SetMaxFPS(10.0f);
	}
	else if (
		EstadoIAAtual == EGideonEstadoComportamental::Speaking ||
		EstadoIAAtual == EGideonEstadoComportamental::Listening ||
		EstadoIAAtual == EGideonEstadoComportamental::Thinking ||
		EstadoIAAtual == EGideonEstadoComportamental::Executing
	)
	{
		GEngine->SetMaxFPS(static_cast<float>(FPSAtivo));
	}
	else
	{
		GEngine->SetMaxFPS(static_cast<float>(FPSOcioso));
	}
}

void AGideonHologramAvatar::AtualizarTransicaoJanelaDesktop(float DeltaTime)
{
	if (!bTransicionandoJanela) return;

	TempoTransicaoJanela += DeltaTime;
	const float T = FMath::Clamp(TempoTransicaoJanela / FMath::Max(0.05f, DuracaoTransicaoJanela), 0.0f, 1.0f);
	const float Suave = 1.0f - FMath::Pow(1.0f - T, 3.0f);

	const int32 X = FMath::RoundToInt(FMath::Lerp(static_cast<float>(PosJanelaInicio.X), static_cast<float>(PosJanelaDestino.X), Suave));
	const int32 Y = FMath::RoundToInt(FMath::Lerp(static_cast<float>(PosJanelaInicio.Y), static_cast<float>(PosJanelaDestino.Y), Suave));
	const int32 W = FMath::RoundToInt(FMath::Lerp(static_cast<float>(TamJanelaInicio.X), static_cast<float>(TamJanelaDestino.X), Suave));
	const int32 H = FMath::RoundToInt(FMath::Lerp(static_cast<float>(TamJanelaInicio.Y), static_cast<float>(TamJanelaDestino.Y), Suave));

	FGideonDesktopWindow::MoverERedimensionarJanela(X, Y, W, H);
	if (T >= 1.0f)
	{
		bTransicionandoJanela = false;
	}
}

void AGideonHologramAvatar::EnviarTelemetriaPeriodica(float DeltaTime)
{
	TimerTelemetria -= DeltaTime;
	if (TimerTelemetria > 0.0f) return;
	TimerTelemetria = 2.0f;

	if (UGameInstance* GI = GetGameInstance())
	{
		if (UGideonWSSubsystem* WS = GI->GetSubsystem<UGideonWSSubsystem>())
		{
			const int32 FPSAtual = FMath::RoundToInt(1.0f / FMath::Max(0.001f, DeltaTime));
			FString ModoStr = TEXT("conversa");
			switch (ModoAtual)
			{
			case EGideonModoDesktop::Compacto: ModoStr = TEXT("compacto"); break;
			case EGideonModoDesktop::Foco: ModoStr = TEXT("foco"); break;
			case EGideonModoDesktop::Operacional: ModoStr = TEXT("operacional"); break;
			case EGideonModoDesktop::Oculto: ModoStr = TEXT("oculto"); break;
			default: ModoStr = TEXT("conversa"); break;
			}
			WS->EnviarTelemetriaAvatar(
				FPSAtual,
				NomeEstadoIAAtual,
				EmocaoAlvo,
				VisemaPrincipalAlvo,
				OlharAtual.X,
				OlharAtual.Y,
				ModoStr
			);
		}
	}
}

void AGideonHologramAvatar::AoMudarEmocao(const FString& Nome, float Intensidade)
{
	EmocaoAlvo = Nome;
	IntensidadeEmocao = Intensidade;
	DefinirAlvosExpressao(Nome, Intensidade);
}

void AGideonHologramAvatar::AoIniciarFala(const FString& Texto)
{
	bFalando = true;
	AoMudarEstadoIA(TEXT("speaking"));
}

void AGideonHologramAvatar::AoReceberLipSyncChunk(const FGideonLipSyncFrame& Quadro)
{
	bFalando = true;
	EnergiaVozAlvo = Quadro.Intensidade;
	VisemaPrincipalAlvo = Quadro.VisemaPrincipal;
	VisemaSecundarioAlvo = Quadro.VisemaSecundario;
	PesoVisemaPrincipal = Quadro.PesoPrincipal;
	PesoVisemaSecundario = Quadro.PesoSecundario;
	AberturaBocaAlvo = Quadro.AberturaMandibula;
	ArredondamentoAlvo = Quadro.Arredondamento;
	EnfaseSobrancelhaFala = Quadro.EnfaseSobrancelha;
}

void AGideonHologramAvatar::AoFinalizarFala()
{
	bFalando = false;
	EnergiaVozAlvo = 0.0f;
	AberturaBocaAlvo = 0.0f;
	ArredondamentoAlvo = 0.0f;
	AoMudarEstadoIA(TEXT("idle"));
}

void AGideonHologramAvatar::AoMudarEstadoIA(const FString& NovoEstado)
{
	NomeEstadoIAAtual = NovoEstado.ToLower().TrimStartAndEnd();
	if (NomeEstadoIAAtual == TEXT("listening"))
	{
		EstadoIAAtual = EGideonEstadoComportamental::Listening;
		OlharExternoAlvo = FVector2D::ZeroVector;
		DefinirAlvosExpressao(TEXT("curiosidade"), 0.55f);
	}
	else if (NomeEstadoIAAtual == TEXT("thinking"))
	{
		EstadoIAAtual = EGideonEstadoComportamental::Thinking;
		DefinirAlvosExpressao(TEXT("concentracao"), 0.65f);
	}
	else if (NomeEstadoIAAtual == TEXT("speaking"))
	{
		EstadoIAAtual = EGideonEstadoComportamental::Speaking;
		OlharExternoAlvo = FVector2D::ZeroVector;
	}
	else if (NomeEstadoIAAtual == TEXT("executing"))
	{
		EstadoIAAtual = EGideonEstadoComportamental::Executing;
		DefinirAlvosExpressao(TEXT("concentracao"), 0.75f);
	}
	else if (NomeEstadoIAAtual == TEXT("observing"))
	{
		EstadoIAAtual = EGideonEstadoComportamental::Observing;
		DefinirAlvosExpressao(TEXT("curiosidade"), 0.50f);
	}
	else if (NomeEstadoIAAtual == TEXT("error"))
	{
		EstadoIAAtual = EGideonEstadoComportamental::Error;
		DefinirAlvosExpressao(TEXT("preocupacao"), 0.80f);
	}
	else
	{
		EstadoIAAtual = EGideonEstadoComportamental::Idle;
		DefinirAlvosExpressao(EmocaoAlvo, IntensidadeEmocao);
	}
	AtualizarGovernadorFPS();
}

void AGideonHologramAvatar::AoMudarModoJanela(const FString& NovoModo)
{
	int32 TelaW = 1920, TelaH = 1080;
	FGideonDesktopWindow::ObterResolucaoMonitorPrincipal(TelaW, TelaH);

	int32 AtualX, AtualY, AtualW, AtualH;
	FGideonDesktopWindow::ObterRetanguloJanela(AtualX, AtualY, AtualW, AtualH);
	PosJanelaInicio = FIntPoint(AtualX, AtualY);
	TamJanelaInicio = FIntPoint(AtualW, AtualH);

	const FString M = NovoModo.ToLower().TrimStartAndEnd();
	if (M == TEXT("oculto"))
	{
		ModoAtual = EGideonModoDesktop::Oculto;
		AlvoMaterializacao = 0.0f;
		AtualizarGovernadorFPS();
		return;
	}

	if (M == TEXT("compacto") || M == TEXT("canto"))
	{
		ModoAtual = EGideonModoDesktop::Compacto;
		PosJanelaDestino = FIntPoint(TelaW - 320, TelaH - 440);
		TamJanelaDestino = FIntPoint(300, 380);
	}
	else if (M == TEXT("foco") || M == TEXT("centro"))
	{
		ModoAtual = EGideonModoDesktop::Foco;
		PosJanelaDestino = FIntPoint((TelaW - 600) / 2, (TelaH - 850) / 2);
		TamJanelaDestino = FIntPoint(600, 850);
	}
	else if (M == TEXT("operacional"))
	{
		ModoAtual = EGideonModoDesktop::Operacional;
		PosJanelaDestino = FIntPoint(TelaW - 380, 60);
		TamJanelaDestino = FIntPoint(340, 460);
	}
	else
	{
		ModoAtual = EGideonModoDesktop::Conversa;
		PosJanelaDestino = FIntPoint(TelaW - 480, TelaH - 720);
		TamJanelaDestino = FIntPoint(450, 650);
	}

	SetActorHiddenInGame(false);
	AlvoMaterializacao = 1.0f;
	TempoTransicaoJanela = 0.0f;
	DuracaoTransicaoJanela = 0.7f;
	bTransicionandoJanela = true;
	AtualizarGovernadorFPS();
}

void AGideonHologramAvatar::AoMudarOlhar(const FString& Alvo, float X, float Y)
{
	if (Alvo == TEXT("usuario"))
	{
		OlharExternoAlvo = FVector2D::ZeroVector;
		return;
	}
	OlharExternoAlvo = FVector2D(X, Y);
}

void AGideonHologramAvatar::ProcessarConfigHolograma(const TSharedPtr<FJsonObject>& Config)
{
	if (!Config.IsValid()) return;

	double Val = 0.0;
	if (Config->TryGetNumberField(TEXT("opacidade"), Val))
	{
		OpacidadeGeral = FMath::Clamp(static_cast<float>(Val), 0.25f, 1.0f);
	}
	if (Config->TryGetNumberField(TEXT("opacidade_delta"), Val))
	{
		OpacidadeGeral = FMath::Clamp(OpacidadeGeral + static_cast<float>(Val), 0.25f, 1.0f);
	}
	for (UMaterialInstanceDynamic* MID : MateriaisHolograma)
	{
		if (MID) MID->SetScalarParameterValue(TEXT("OpacidadeGeral"), OpacidadeGeral);
	}

	if (Config->TryGetNumberField(TEXT("escala"), Val))
	{
		EscalaUsuario = FMath::Clamp(static_cast<float>(Val), 0.6f, 1.6f);
		PivoRaiz->SetRelativeScale3D(FVector(EscalaUsuario));
	}
	if (Config->TryGetNumberField(TEXT("escala_delta"), Val))
	{
		EscalaUsuario = FMath::Clamp(EscalaUsuario + static_cast<float>(Val), 0.6f, 1.6f);
		PivoRaiz->SetRelativeScale3D(FVector(EscalaUsuario));
	}

	bool bFlag = true;
	if (Config->TryGetBoolField(TEXT("click_through"), bFlag))
	{
		FGideonDesktopWindow::DefinirClickThrough(bFlag);
	}
	if (Config->TryGetBoolField(TEXT("sempre_visivel"), bFlag))
	{
		FGideonDesktopWindow::DefinirSempreVisivel(bFlag);
	}
	if (Config->TryGetNumberField(TEXT("fps_ativo"), Val))
	{
		FPSAtivo = FMath::Clamp(static_cast<int32>(Val), 24, 120);
	}
	if (Config->TryGetNumberField(TEXT("fps_ocioso"), Val))
	{
		FPSOcioso = FMath::Clamp(static_cast<int32>(Val), 10, 60);
	}
	AtualizarGovernadorFPS();
}
