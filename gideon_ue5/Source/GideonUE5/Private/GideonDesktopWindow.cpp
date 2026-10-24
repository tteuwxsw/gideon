#include "GideonDesktopWindow.h"
#include "GideonUE5.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Widgets/SWindow.h"
#include "GenericPlatform/GenericWindow.h"

#if PLATFORM_WINDOWS
#include "Windows/AllowWindowsPlatformTypes.h"
#include <windows.h>
#include <dwmapi.h>
#include "Windows/HideWindowsPlatformTypes.h"
#endif

void* FGideonDesktopWindow::ObterHandleJanelaNativa()
{
	if (!GEngine || !GEngine->GameViewport)
	{
		return nullptr;
	}
	TSharedPtr<SWindow> JanelaSlate = GEngine->GameViewport->GetWindow();
	if (!JanelaSlate.IsValid() || !JanelaSlate->GetNativeWindow().IsValid())
	{
		return nullptr;
	}
	return JanelaSlate->GetNativeWindow()->GetOSWindowHandle();
}

bool FGideonDesktopWindow::ConfigurarJanelaTransparenteDesktop(bool bClickThrough, bool bSempreVisivel)
{
#if PLATFORM_WINDOWS
	HWND Hwnd = static_cast<HWND>(ObterHandleJanelaNativa());
	if (!Hwnd)
	{
		return false;
	}

	// 1. Remove bordas e barra de titulo convencionais (WS_POPUP)
	LONG_PTR EstiloJanela = GetWindowLongPtrW(Hwnd, GWL_STYLE);
	EstiloJanela &= ~(WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU);
	EstiloJanela |= WS_POPUP;
	SetWindowLongPtrW(Hwnd, GWL_STYLE, EstiloJanela);

	// 2. Configura ToolWindow (sem barra de tarefas e sem Alt+Tab), NoActivate e Click-Through
	LONG_PTR EstiloEx = GetWindowLongPtrW(Hwnd, GWL_EXSTYLE);
	EstiloEx &= ~WS_EX_APPWINDOW;
	EstiloEx |= (WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE);
	if (bClickThrough)
	{
		EstiloEx |= WS_EX_TRANSPARENT;
	}
	else
	{
		EstiloEx &= ~WS_EX_TRANSPARENT;
	}
	SetWindowLongPtrW(Hwnd, GWL_EXSTYLE, EstiloEx);

	// 3. Estende a folha de vidro do Desktop Window Manager (DWM) para toda a area cliente
	// Combinado com r.PostProcessing.PropagateAlpha=1 no DX11, compoe o canal Alpha por pixel sem caixa preta
	MARGINS Margens = { -1, -1, -1, -1 };
	DwmExtendFrameIntoClientArea(Hwnd, &Margens);
	SetLayeredWindowAttributes(Hwnd, 0, 255, LWA_ALPHA);

	HWND OrdemZ = bSempreVisivel ? HWND_TOPMOST : HWND_NOTOPMOST;
	SetWindowPos(
		Hwnd,
		OrdemZ,
		0, 0, 0, 0,
		SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED
	);

	UE_LOG(LogGideonUE5, Log, TEXT("[Gideon Desktop] Janela Win32/DWM transparente e click-through configurada."));
	return true;
#else
	return false;
#endif
}

void FGideonDesktopWindow::DefinirClickThrough(bool bClickThrough)
{
#if PLATFORM_WINDOWS
	HWND Hwnd = static_cast<HWND>(ObterHandleJanelaNativa());
	if (!Hwnd) return;
	LONG_PTR EstiloEx = GetWindowLongPtrW(Hwnd, GWL_EXSTYLE);
	if (bClickThrough)
	{
		EstiloEx |= (WS_EX_LAYERED | WS_EX_TRANSPARENT);
	}
	else
	{
		EstiloEx &= ~WS_EX_TRANSPARENT;
	}
	SetWindowLongPtrW(Hwnd, GWL_EXSTYLE, EstiloEx);
#endif
}

void FGideonDesktopWindow::DefinirSempreVisivel(bool bSempreVisivel)
{
#if PLATFORM_WINDOWS
	HWND Hwnd = static_cast<HWND>(ObterHandleJanelaNativa());
	if (!Hwnd) return;
	SetWindowPos(
		Hwnd,
		bSempreVisivel ? HWND_TOPMOST : HWND_NOTOPMOST,
		0, 0, 0, 0,
		SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
	);
#endif
}

void FGideonDesktopWindow::ObterResolucaoMonitorPrincipal(int32& OutLargura, int32& OutAltura)
{
#if PLATFORM_WINDOWS
	OutLargura = GetSystemMetrics(SM_CXSCREEN);
	OutAltura = GetSystemMetrics(SM_CYSCREEN);
	if (OutLargura <= 0) OutLargura = 1920;
	if (OutAltura <= 0) OutAltura = 1080;
#else
	OutLargura = 1920;
	OutAltura = 1080;
#endif
}

void FGideonDesktopWindow::MoverERedimensionarJanela(int32 PosX, int32 PosY, int32 Largura, int32 Altura)
{
#if PLATFORM_WINDOWS
	HWND Hwnd = static_cast<HWND>(ObterHandleJanelaNativa());
	if (!Hwnd) return;
	SetWindowPos(
		Hwnd,
		nullptr,
		PosX, PosY, Largura, Altura,
		SWP_NOZORDER | SWP_NOACTIVATE
	);
#endif
}

void FGideonDesktopWindow::ObterRetanguloJanela(int32& OutX, int32& OutY, int32& OutLargura, int32& OutAltura)
{
#if PLATFORM_WINDOWS
	HWND Hwnd = static_cast<HWND>(ObterHandleJanelaNativa());
	RECT Rect;
	if (Hwnd && GetWindowRect(Hwnd, &Rect))
	{
		OutX = Rect.left;
		OutY = Rect.top;
		OutLargura = Rect.right - Rect.left;
		OutAltura = Rect.bottom - Rect.top;
		return;
	}
#endif
	OutX = 1440;
	OutY = 360;
	OutLargura = 450;
	OutAltura = 650;
}
