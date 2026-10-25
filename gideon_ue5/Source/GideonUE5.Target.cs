using UnrealBuildTool;
using System.Collections.Generic;

public class GideonUE5Target : TargetRules
{
	public GideonUE5Target(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("GideonUE5");
	}
}
