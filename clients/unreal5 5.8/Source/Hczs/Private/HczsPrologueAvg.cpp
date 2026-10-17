#include "HczsPrologueAvg.h"
#include "Misc/AutomationTest.h"

namespace
{
const FHczsPrologueAvgLine Lines[] = {
    { TEXT("ailisha_voice"), TEXT("就是“这里”了吗？") },
    { TEXT("mxt_vo"), TEXT("哦？来人了？没想到，在这最后的时刻，还能拥有演出的机会。") },
    { TEXT("mxt_vo"), TEXT("你们是特意来到这特等席，观赏第三次黑潮的壮丽景象的吗？还是，来阻止的呢？") },
    { TEXT("ailisha_voice"), TEXT("第三次黑潮，并不是什么壮丽景象，它就是一场灾难。") },
    { TEXT("ailisha_voice"), TEXT("这场灾难已经吞噬了琳、诺、瓦列莉亚和佐伊……我不会再让它吞噬更多的人……") },
    { TEXT("mxt_vo"), TEXT("哦，看来是后者了。就凭你们两个人，也想阻止黑潮吗？") },
    { TEXT("future_voice"), TEXT("我们没有选择。") },
    { TEXT("ailisha_voice"), TEXT("是的，我们没有选择，无论如何，我们都必须打败你！") },
    { TEXT("mxt_vo"), TEXT("打败我？那就试试看吧！") },
};
}

const TArrayView<const FHczsPrologueAvgLine> HczsPrologueAvg138()
{
    return Lines;
}

int32 HczsAdvancePrologueAvg138(int32 Index)
{
    const int32 Count = UE_ARRAY_COUNT(Lines);
    if (Index < -1) return -1;
    if (Index + 1 < Count) return Index + 1;
    return Count;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsPrologueAvg138Test, "Hczs.Dungeon.PrologueAvg138",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FHczsPrologueAvg138Test::RunTest(const FString& Parameters)
{
    const auto LinesView = HczsPrologueAvg138();
    TestEqual(TEXT("Nine spoken lines"), LinesView.Num(), 9);
    TestEqual(TEXT("Elsa opens"), FString(LinesView[0].Text), TEXT("就是“这里”了吗？"));
    TestEqual(TEXT("Future answers"), FString(LinesView[6].Voice), TEXT("future_voice"));
    TestEqual(TEXT("Boss closes"), FString(LinesView[8].Text), TEXT("打败我？那就试试看吧！"));
    int32 Index = -1;
    for (int32 Step = 0; Step < LinesView.Num(); ++Step) Index = HczsAdvancePrologueAvg138(Index);
    TestEqual(TEXT("Last line stays addressable"), Index, LinesView.Num() - 1);
    TestEqual(TEXT("Finished sentinel does not wrap"), HczsAdvancePrologueAvg138(Index), LinesView.Num());
    TestEqual(TEXT("Finished sentinel stays finished"), HczsAdvancePrologueAvg138(LinesView.Num()), LinesView.Num());
    return true;
}
