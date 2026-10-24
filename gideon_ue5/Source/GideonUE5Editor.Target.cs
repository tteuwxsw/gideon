using UnrealBuildTool;
using System.Collections.Generic;

public class GideonUE5EditorTarget : TargetRules
{
	public GideonUE5EditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.V5;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_4;
		ExtraModuleNames.Add("GideonUE5");
	}
}
