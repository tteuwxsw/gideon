#include "GideonUE5.h"
#include "Modules/ModuleManager.h"
#include "WebSocketsModule.h"

DEFINE_LOG_CATEGORY(LogGideonUE5);

void FGideonUE5Module::StartupModule()
{
	FModuleManager::LoadModuleChecked<FWebSocketsModule>("WebSockets");
	UE_LOG(LogGideonUE5, Log, TEXT("[Gideon UE5] Modulo grafico e subsistema WebSocket inicializados."));
}

void FGideonUE5Module::ShutdownModule()
{
}

IMPLEMENT_PRIMARY_GAME_MODULE(FGideonUE5Module, GideonUE5, "GideonUE5");
