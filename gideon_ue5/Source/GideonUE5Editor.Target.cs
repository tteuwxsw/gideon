using UnrealBuildTool;
using System.Collections.Generic;

public class GideonUE5EditorTarget : TargetRules
{
	public GideonUE5EditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("GideonUE5");
	}
}
