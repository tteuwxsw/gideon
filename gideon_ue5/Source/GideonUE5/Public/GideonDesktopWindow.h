#pragma once

#include "CoreMinimal.h"

/**
 * Camada nativa Win32 / DWM para transformar a janela do Unreal Engine 5 em um
 * overlay holografico sem bordas, com transparencia por pixel real (DwmExtendFrameIntoClientArea),
 * intangivel ao mouse (click-through) e oculto da barra de tarefas e do Alt+Tab.
 */
class GIDEONUE5_API FGideonDesktopWindow
{
public:
	static bool ConfigurarJanelaTransparenteDesktop(bool bClickThrough = true, bool bSempreVisivel = true);
	static void DefinirClickThrough(bool bClickThrough);
	static void DefinirSempreVisivel(bool bSempreVisivel);
	static void ObterResolucaoMonitorPrincipal(int32& OutLargura, int32& OutAltura);
	static void MoverERedimensionarJanela(int32 PosX, int32 PosY, int32 Largura, int32 Altura);
	static void ObterRetanguloJanela(int32& OutX, int32& OutY, int32& OutLargura, int32& OutAltura);

private:
	static void* ObterHandleJanelaNativa();
};
