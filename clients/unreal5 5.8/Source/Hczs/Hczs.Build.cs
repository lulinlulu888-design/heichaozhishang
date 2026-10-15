using UnrealBuildTool;

public class Hczs : ModuleRules
{
    public Hczs(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "InputCore", "HTTP", "UMG", "SlateCore", "MediaAssets" });
        PrivateDependencyModuleNames.AddRange(new[] { "Json", "Slate", "RHI", "MediaUtils", "AudioMixer" });
    }
}
