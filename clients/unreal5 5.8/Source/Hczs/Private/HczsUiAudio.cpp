#include "HczsUiAudio.h"

namespace HczsUiAudio
{
const FCue& Get(ECue Cue)
{
    static const FCue DrawCard{TEXT("UI_DRAWCARD"), TEXT("ui_battle_fapai_a"), {46920884u, 81447368u, 1061850655u}, -9.0f, 1};
    static const FCue FapaiB{TEXT("UI_FAPAI_B"), TEXT("ui_battle_fapai_b"), {1050791224u}, -4.5f, 0};
    return Cue == ECue::DrawCard ? DrawCard : FapaiB;
}

int32 PickVariant(ECue Cue, int32 Previous, FRandomStream& Random)
{
    const FCue& Def = Get(Cue);
    const int32 Count = Def.Sources.Num();
    if (Count <= 1) return 0;
    if (Def.AvoidRepeat <= 0 || !Def.Sources.IsValidIndex(Previous)) return Random.RandRange(0, Count - 1);
    const int32 Pick = Random.RandRange(0, Count - 2);
    return Pick >= Previous ? Pick + 1 : Pick;
}

FString SoundPath(uint32 SourceId)
{
    return FString::Printf(TEXT("/Game/Recovered/Audio/UI/UiBattle_%u.UiBattle_%u"), SourceId, SourceId);
}

float VolumeMultiplier(ECue Cue)
{
    return FMath::Pow(10.0f, Get(Cue).VolumeDb / 20.0f);
}
}

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsUiAudioCueTest, "Hczs.SourceUI.Audio.DealCues",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsUiAudioCueTest::RunTest(const FString& Parameters)
{
    using namespace HczsUiAudio;
    TestEqual(TEXT("Draw cue key"), FString(Get(ECue::DrawCard).Key), FString(TEXT("UI_DRAWCARD")));
    TestEqual(TEXT("Three random variants"), Get(ECue::DrawCard).Sources.Num(), 3);
    TestEqual(TEXT("Land cue single source"), Get(ECue::FapaiB).Sources.Num(), 1);
    TestTrue(TEXT("-9 dB multiplier"), FMath::IsNearlyEqual(VolumeMultiplier(ECue::DrawCard), 0.35481f, 1e-4f));
    TestTrue(TEXT("-4.5 dB multiplier"), FMath::IsNearlyEqual(VolumeMultiplier(ECue::FapaiB), 0.59566f, 1e-4f));
    FRandomStream Random(17);
    int32 Previous = -1;
    TSet<int32> Seen;
    for (int32 I = 0; I < 200; ++I)
    {
        const int32 Pick = PickVariant(ECue::DrawCard, Previous, Random);
        if (!TestTrue(TEXT("Variant in range"), Pick >= 0 && Pick < 3)) return false;
        if (!TestNotEqual(TEXT("Avoid repeat 1"), Pick, Previous)) return false;
        Seen.Add(Pick); Previous = Pick;
    }
    TestEqual(TEXT("All variants reachable"), Seen.Num(), 3);
    TestEqual(TEXT("Single-source cue"), PickVariant(ECue::FapaiB, 0, Random), 0);
    TestEqual(TEXT("Asset path"), SoundPath(1050791224u), FString(TEXT("/Game/Recovered/Audio/UI/UiBattle_1050791224.UiBattle_1050791224")));
    return true;
}
#endif
