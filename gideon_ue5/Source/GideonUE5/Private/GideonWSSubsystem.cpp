#include "GideonWSSubsystem.h"
#include "GideonUE5.h"
#include "WebSocketsModule.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Dom/JsonObject.h"

void UGideonWSSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	ConectarAoBackend();
}

void UGideonWSSubsystem::Deinitialize()
{
	if (Socket.IsValid() && Socket->IsConnected())
	{
		Socket->Close();
	}
	Socket.Reset();
	Super::Deinitialize();
}

TStatId UGideonWSSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UGideonWSSubsystem, STATGROUP_Tickables);
}

FString UGideonWSSubsystem::CarregarTokenLocal() const
{
	TArray<FString> Candidatos = {
		FPaths::Combine(FPaths::ProjectDir(), TEXT("../dados/auth_token.txt")),
		FPaths::Combine(FPaths::LaunchDir(), TEXT("../dados/auth_token.txt")),
		FPaths::Combine(FPaths::LaunchDir(), TEXT("dados/auth_token.txt"))
	};

	for (const FString& Caminho : Candidatos)
	{
		FString Conteudo;
		if (FPaths::FileExists(Caminho) && FFileHelper::LoadFileToString(Conteudo, *Caminho))
		{
			Conteudo.TrimStartAndEndInline();
			if (!Conteudo.IsEmpty())
			{
				return Conteudo;
			}
		}
	}
	return FString();
}

void UGideonWSSubsystem::ConectarAoBackend()
{
	if (Socket.IsValid() && Socket->IsConnected())
	{
		return;
	}

	TMap<FString, FString> Headers;
	const FString Token = CarregarTokenLocal();
	if (!Token.IsEmpty())
	{
		Headers.Add(TEXT("X-Gideon-Token"), Token);
	}

	Socket = FWebSocketsModule::Get().CreateWebSocket(UrlServidor, TEXT(""), Headers);

	Socket->OnConnected().AddLambda([this]()
	{
		bConectado = true;
		UE_LOG(LogGideonUE5, Log, TEXT("[Gideon WS] Conectado ao backend Python com sucesso."));
		EnviarEventoPronto();
	});

	Socket->OnConnectionError().AddLambda([this](const FString& Erro)
	{
		bConectado = false;
		UE_LOG(LogGideonUE5, Warning, TEXT("[Gideon WS] Erro de conexao: %s"), *Erro);
	});

	Socket->OnClosed().AddLambda([this](int32 StatusCode, const FString& Reason, bool bWasClean)
	{
		bConectado = false;
		UE_LOG(LogGideonUE5, Log, TEXT("[Gideon WS] Conexao encerrada (%d): %s"), StatusCode, *Reason);
	});

	Socket->OnMessage().AddLambda([this](const FString& MessageString)
	{
		ProcessarMensagemJson(MessageString);
	});

	Socket->Connect();
}

void UGideonWSSubsystem::Tick(float DeltaTime)
{
	if (!bConectado)
	{
		TempoDesdeUltimaTentativa += DeltaTime;
		if (TempoDesdeUltimaTentativa >= IntervaloReconexao)
		{
			TempoDesdeUltimaTentativa = 0.0f;
			ConectarAoBackend();
		}
	}
}

void UGideonWSSubsystem::EnviarEventoPronto()
{
	if (!Socket.IsValid() || !Socket->IsConnected())
	{
		return;
	}

	TSharedPtr<FJsonObject> Msg = MakeShared<FJsonObject>();
	Msg->SetStringField(TEXT("tipo"), TEXT("pronto"));
	Msg->SetStringField(TEXT("cliente"), TEXT("ue5_avatar"));
	Msg->SetStringField(TEXT("versao"), TEXT("0.5.0"));

	FString Saida;
	TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Saida);
	FJsonSerializer::Serialize(Msg.ToSharedRef(), Writer);
	Socket->Send(Saida);
}

void UGideonWSSubsystem::EnviarTelemetriaAvatar(
	int32 FPS,
	const FString& EstadoIA,
	const FString& Emocao,
	const FString& VisemaAtivo,
	float OlharX,
	float OlharY,
	const FString& Modo
)
{
	if (!Socket.IsValid() || !Socket->IsConnected())
	{
		return;
	}

	TSharedPtr<FJsonObject> Msg = MakeShared<FJsonObject>();
	Msg->SetStringField(TEXT("tipo"), TEXT("telemetria_avatar"));
	Msg->SetStringField(TEXT("motor"), TEXT("unreal_engine_5"));
	Msg->SetNumberField(TEXT("fps"), FPS);
	Msg->SetStringField(TEXT("estado_ia"), EstadoIA);
	Msg->SetStringField(TEXT("emocao"), Emocao);
	Msg->SetStringField(TEXT("visema_ativo"), VisemaAtivo);
	Msg->SetNumberField(TEXT("olhar_x"), OlharX);
	Msg->SetNumberField(TEXT("olhar_y"), OlharY);
	Msg->SetStringField(TEXT("modo"), Modo);

	FString Saida;
	TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Saida);
	FJsonSerializer::Serialize(Msg.ToSharedRef(), Writer);
	Socket->Send(Saida);
}

void UGideonWSSubsystem::ProcessarMensagemJson(const FString& MensagemTexto)
{
	TSharedPtr<FJsonObject> Root;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(MensagemTexto);
	if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
	{
		return;
	}

	FString Tipo;
	if (!Root->TryGetStringField(TEXT("tipo"), Tipo))
	{
		return;
	}

	TSharedPtr<FJsonObject> Payload = Root;
	const TSharedPtr<FJsonObject>* DadosSubObj = nullptr;
	if (Root->TryGetObjectField(TEXT("dados"), DadosSubObj) && DadosSubObj && (*DadosSubObj).IsValid())
	{
		Payload = *DadosSubObj;
	}

	if (Tipo == TEXT("emocao"))
	{
		FString Nome = TEXT("neutra");
		double Intensidade = 1.0;
		Payload->TryGetStringField(TEXT("nome"), Nome);
		Payload->TryGetNumberField(TEXT("intensidade"), Intensidade);
		OnEmocaoAlterada.Broadcast(Nome, static_cast<float>(Intensidade));
	}
	else if (Tipo == TEXT("fala_inicio"))
	{
		FString Texto;
		Payload->TryGetStringField(TEXT("texto"), Texto);
		OnFalaIniciada.Broadcast(Texto);
	}
	else if (Tipo == TEXT("fala_chunk"))
	{
		FGideonLipSyncFrame Quadro;
		double Val = 0.0;
		if (Payload->TryGetNumberField(TEXT("intensidade"), Val)) Quadro.Intensidade = static_cast<float>(Val);
		Payload->TryGetStringField(TEXT("visema"), Quadro.VisemaPrincipal);
		Payload->TryGetStringField(TEXT("visema_secundario"), Quadro.VisemaSecundario);
		if (Payload->TryGetNumberField(TEXT("peso_visema"), Val)) Quadro.PesoPrincipal = static_cast<float>(Val);
		if (Payload->TryGetNumberField(TEXT("peso_secundario"), Val)) Quadro.PesoSecundario = static_cast<float>(Val);
		if (Payload->TryGetNumberField(TEXT("abertura_mandibula"), Val)) Quadro.AberturaMandibula = static_cast<float>(Val);
		if (Payload->TryGetNumberField(TEXT("arredondamento"), Val)) Quadro.Arredondamento = static_cast<float>(Val);
		if (Payload->TryGetNumberField(TEXT("enfase_sobrancelha"), Val)) Quadro.EnfaseSobrancelha = static_cast<float>(Val);

		OnLipSyncChunk.Broadcast(Quadro);
	}
	else if (Tipo == TEXT("fala_fim"))
	{
		OnFalaFinalizada.Broadcast();
	}
	else if (Tipo == TEXT("pensando"))
	{
		bool bAtivo = false;
		Payload->TryGetBoolField(TEXT("ativo"), bAtivo);
		OnEstadoIAAlterado.Broadcast(bAtivo ? TEXT("thinking") : TEXT("idle"));
	}
	else if (Tipo == TEXT("ouvindo"))
	{
		bool bAtivo = false;
		Payload->TryGetBoolField(TEXT("ativo"), bAtivo);
		if (bAtivo)
		{
			OnEstadoIAAlterado.Broadcast(TEXT("listening"));
		}
	}
	else if (Tipo == TEXT("estado_ia"))
	{
		FString Estado = TEXT("idle");
		Payload->TryGetStringField(TEXT("estado"), Estado);
		OnEstadoIAAlterado.Broadcast(Estado);
	}
	else if (Tipo == TEXT("modo"))
	{
		FString Modo = TEXT("conversa");
		if (!Payload->TryGetStringField(TEXT("nome"), Modo))
		{
			Payload->TryGetStringField(TEXT("modo"), Modo);
		}
		OnModoAlterado.Broadcast(Modo);
	}
	else if (Tipo == TEXT("olhar") || Tipo == TEXT("atencao_desktop"))
	{
		FString Alvo = Tipo == TEXT("atencao_desktop") ? TEXT("janela_ativa") : TEXT("cursor");
		Payload->TryGetStringField(TEXT("alvo"), Alvo);
		double X = 0.0, Y = 0.0;
		Payload->TryGetNumberField(TEXT("x"), X);
		Payload->TryGetNumberField(TEXT("y"), Y);
		OnOlharAlterado.Broadcast(Alvo, static_cast<float>(X), static_cast<float>(Y));
	}
	else if (Tipo == TEXT("config_holograma"))
	{
		if (OnConfigHologramaRecebida)
		{
			OnConfigHologramaRecebida(Payload);
		}
	}
}
