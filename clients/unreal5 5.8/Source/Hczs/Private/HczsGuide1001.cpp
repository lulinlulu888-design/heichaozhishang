#include "HczsGuide1001.h"
#include "Misc/AutomationTest.h"

namespace
{
using A = EHczsGuideAnchor;
using V = EHczsGuideAdvance;
// Box X/Y are guide_show_table offsets (Cocos y-up) from the anchor centre; 0 size keeps the anchor size.
const FHczsGuideStep Steps[] = {
    { 1850, 1851, 4.0f, TEXT("未来"), TEXT("每个人携带的卡牌各不相同，长按卡牌可以查看详细描述"), 0, A::Hand, -1, 0, 0, 915, 210, nullptr, V::Tap },
    { 1851, 1852, 0.0f, nullptr, TEXT("攻击类型的卡牌，在卡面上有“攻”的标识"), 0, A::Card, 2, 0, 0, 0, 0, TEXT("click"), V::Tap },
    { 1852, 1853, 0.0f, nullptr, TEXT("对敌人拖动卡牌即可释放"), 300, A::Card, 2, 0, 0, 0, 0, TEXT("swipe"), V::PlayCard },
    { 1853, 1854, 0.8f, nullptr, TEXT("使用卡牌会消耗能量"), 0, A::Energy, -1, 70, 0, 160, 120, nullptr, V::Tap },
    { 1854, 1855, 0.2f, nullptr, TEXT("卡牌顶部显示打出所要消耗的能量"), 0, A::Card, 4, -5, 70, 190, 100, nullptr, V::Tap },
    { 1855, -1, 0.2f, nullptr, TEXT("尽全力去攻击吧！"), 0, A::Hand, -1, 0, 0, 915, 210, nullptr, V::Tap },
    { 1856, 1857, 1.0f, nullptr, TEXT("能量耗尽，等待下回合能量恢复"), 50, A::Energy, -1, 60, 0, 205, 120, nullptr, V::Tap },
    { 1857, -1, 0.5f, nullptr, TEXT("没有能量，或者没有想要使用的卡牌时，本回合的攻击就结束了"), 50, A::EndTurn, -1, 0, 0, 0, 0, TEXT("click"), V::EndTurn },
    { 1858, 1859, 2.2f, nullptr, TEXT("新的回合，能量将重新恢复"), 50, A::Energy, -1, 80, 0, 180, 120, nullptr, V::Tap },
    { 1859, 1860, 0.4f, nullptr, TEXT("并会重新抽取六张卡牌"), 50, A::None, -1, 0, 0, 0, 0, nullptr, V::Tap },
    { 1860, -1, 0.4f, nullptr, TEXT("到你的回合了，战胜它吧，接触者"), 50, A::None, -1, 0, 0, 0, 0, nullptr, V::Tap },
};
int32 IndexOf(int32 Id)
{
    for (int32 Index = 0; Index < UE_ARRAY_COUNT(Steps); ++Index)
        if (Steps[Index].Id == Id) return Index;
    return INDEX_NONE;
}
}

TArrayView<const FHczsGuideStep> HczsGuide1001Steps() { return Steps; }

const FHczsGuideStep* FHczsGuide1001::Current() const
{
    return StepIndex >= 0 && StepIndex < UE_ARRAY_COUNT(Steps) ? &Steps[StepIndex] : nullptr;
}

void FHczsGuide1001::Start(int32 Id, double Now)
{
    StepIndex = IndexOf(Id);
    ShowAt = Now + (StepIndex >= 0 ? Steps[StepIndex].Delay : 0);
    StepActionIndex = LastActionIndex;
    StepRound = LastRound;
}

void FHczsGuide1001::Next(double Now)
{
    const FHczsGuideStep* Step = Current();
    if (Step && Step->Id == 1860) bComplete = true;
    if (Step && Step->NextId > 0) Start(Step->NextId, Now);
    else StepIndex = INDEX_NONE;
}

void FHczsGuide1001::Observe(const FString& Battle, const FString& Status, int32 Round, int32 Energy, int64 ActionIndex, double Now)
{
    if (Battle != BattleId)
    {
        *this = FHczsGuide1001();
        BattleId = Battle;
    }
    LastActionIndex = ActionIndex; LastRound = Round;
    if (bComplete || Status != TEXT("player-turn")) { StepIndex = INDEX_NONE; return; }
    if (const FHczsGuideStep* Step = Current())
    {
        if ((Step->Advance == EHczsGuideAdvance::PlayCard && ActionIndex > StepActionIndex) ||
            (Step->Advance == EHczsGuideAdvance::EndTurn && Round > StepRound)) Next(Now);
        else return;
        if (Current()) return;
    }
    if (!bChainCard)
    {
        bChainCard = true;
        // Condition 8 {Count 1, BattleId 5000}: only a fresh first round opens the card lesson.
        if (Round == 1 && ActionIndex == 0) { Start(1850, Now); return; }
    }
    if (!bChainEnergy && Round == 1 && Energy == 0) { bChainEnergy = true; Start(1856, Now); return; }
    if (!bChainRound && Round >= 2) { bChainEnergy = bChainRound = true; Start(1858, Now); }
}

bool FHczsGuide1001::Tap(double Now)
{
    const FHczsGuideStep* Step = Current();
    if (!Step || Now < ShowAt || Step->Advance != EHczsGuideAdvance::Tap) return false;
    Next(Now);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsGuide1001Test, "Hczs.Session.Guide1001",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FHczsGuide1001Test::RunTest(const FString& Parameters)
{
    TestEqual(TEXT("Eleven source steps"), HczsGuide1001Steps().Num(), 11);
    FHczsGuide1001 Guide;
    Guide.Observe(TEXT("b"), TEXT("player-turn"), 1, 5, 0, 10);
    TestEqual(TEXT("Round one opens 1850"), Guide.Current()->Id, 1850);
    TestFalse(TEXT("Source delay 4.0 hides it first"), Guide.IsVisible(13.9));
    TestFalse(TEXT("Hidden step ignores taps"), Guide.Tap(13.9));
    TestTrue(TEXT("Tap 1850"), Guide.Tap(14));
    TestEqual(TEXT("1851 follows"), Guide.Current()->Id, 1851);
    TestTrue(TEXT("Tap 1851"), Guide.Tap(14));
    TestEqual(TEXT("Drag lesson"), Guide.Current()->Id, 1852);
    TestFalse(TEXT("D_OUT_CARD ignores taps"), Guide.Tap(15));
    Guide.Observe(TEXT("b"), TEXT("player-turn"), 1, 4, 1, 16);
    TestEqual(TEXT("Card play opens 1853"), Guide.Current()->Id, 1853);
    TestTrue(TEXT("1853"), Guide.Tap(17));
    TestFalse(TEXT("1854 waits its 0.2s delay"), Guide.Tap(17.1));
    TestTrue(TEXT("1854"), Guide.Tap(17.5)); TestTrue(TEXT("1855"), Guide.Tap(18));
    TestNull(TEXT("Shared 1855 ends the chain"), Guide.Current());
    Guide.Observe(TEXT("b"), TEXT("player-turn"), 1, 0, 3, 19);
    TestEqual(TEXT("Empty energy opens 1856"), Guide.Current()->Id, 1856);
    TestTrue(TEXT("1856"), Guide.Tap(20));
    TestEqual(TEXT("End-turn lesson"), Guide.Current()->Id, 1857);
    Guide.Observe(TEXT("b"), TEXT("enemy-turn"), 1, 0, 4, 21);
    TestNull(TEXT("Non-player phases hide the guide"), Guide.Current());
    Guide.Observe(TEXT("b"), TEXT("player-turn"), 2, 5, 5, 22);
    TestEqual(TEXT("Round two opens 1858"), Guide.Current()->Id, 1858);
    TestTrue(TEXT("1858"), Guide.Tap(25)); TestTrue(TEXT("1859"), Guide.Tap(26)); TestTrue(TEXT("1860"), Guide.Tap(27));
    TestTrue(TEXT("Group complete"), Guide.bComplete);
    Guide.Observe(TEXT("b"), TEXT("player-turn"), 3, 5, 9, 30);
    TestNull(TEXT("Completed group stays closed"), Guide.Current());
    FHczsGuide1001 Resumed;
    Resumed.Observe(TEXT("r"), TEXT("player-turn"), 1, 3, 2, 0);
    TestNull(TEXT("A resumed round-one battle skips the card lesson"), Resumed.Current());
    Resumed.Observe(TEXT("r"), TEXT("player-turn"), 1, 0, 3, 1);
    TestEqual(TEXT("but still gets the energy lesson"), Resumed.Current()->Id, 1856);
    return true;
}
