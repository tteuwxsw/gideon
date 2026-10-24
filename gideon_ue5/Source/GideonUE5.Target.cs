using UnrealBuildTool;
using System.Collections.Generic;

public class GideonUE5Target : TargetRules
{
	public GideonUE5Target(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.V5;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_4;
		ExtraModuleNames.Add("GideonUE5");
	}
}
