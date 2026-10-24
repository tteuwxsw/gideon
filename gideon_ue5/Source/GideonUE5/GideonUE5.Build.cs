using UnrealBuildTool;

public class GideonUE5 : ModuleRules
{
	public GideonUE5(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"WebSockets",
			"Json",
			"JsonUtilities",
			"Slate",
			"SlateCore",
			"ApplicationCore",
			"RHI",
			"RenderCore"
		});

		if (Target.Platform == UnrealTargetPlatform.Win64)
		{
			PublicSystemLibraries.AddRange(new string[]
			{
				"dwmapi.lib",
				"user32.lib",
				"gdi32.lib"
			});
		}
	}
}
