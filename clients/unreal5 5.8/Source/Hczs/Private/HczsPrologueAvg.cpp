#include "HczsPrologueAvg.h"
#include "Misc/AutomationTest.h"

namespace
{
const FHczsPrologueAvgLine Lines[] = {
    { TEXT("ailisha_voice"), TEXT("艾尔莎"), TEXT("就是“这里”了吗？") },
    { TEXT("mxt_vo"), TEXT("终焉使者"), TEXT("哦？来人了？没想到，在这最后的时刻，还能拥有演出的机会。") },
    { TEXT("mxt_vo"), TEXT("终焉使者"), TEXT("你们是特意来到这特等席，观赏第三次黑潮的壮丽景象的吗？还是，来阻止的呢？") },
    { TEXT("ailisha_voice"), TEXT("艾尔莎"), TEXT("第三次黑潮，并不是什么壮丽景象，它就是一场灾难。") },
    { TEXT("ailisha_voice"), TEXT("艾尔莎"), TEXT("这场灾难已经吞噬了琳、诺、瓦列莉亚和佐伊……我不会再让它吞噬更多的人……") },
    { TEXT("mxt_vo"), TEXT("终焉使者"), TEXT("哦，看来是后者了。就凭你们两个人，也想阻止黑潮吗？") },
    { TEXT("future_voice"), TEXT("未来"), TEXT("我们没有选择。") },
    { TEXT("ailisha_voice"), TEXT("艾尔莎"), TEXT("是的，我们没有选择，无论如何，我们都必须打败你！") },
    { TEXT("mxt_vo"), TEXT("终焉使者"), TEXT("打败我？那就试试看吧！") },
};
const TCHAR* const Narration134[] = {
    TEXT("进入那条世界线的时候，我见到了未来。#r——那个选择自己留在无望的终局，并将同伴传送回过去的未来。#r她似乎能看到我，她疑惑地问我，你是去帮助她的吗？帮助艾尔莎。"),
    TEXT("我无法回答她。#r她等待了一会，随后露出了一个释怀的微笑，她说，请你代替我，好好地陪伴她。#r之后，我彻底坠入了黑暗。"),
    TEXT("当我再一次睁开眼睛时，我已经出现在了这间屋子里。#r一间温馨而又充满少女气息的屋子，我知道这里是什么地方。#r这是她们的家——艾尔莎所带领的异能者小队：代号U1的根据地。"),
    TEXT("很奇妙，我还记得我是谁，同时，我也知道，我的身份不是真的。#r不过，这个世界线的人并不会知晓真相。#r在她们眼中，我现在的“身份”是“异能者小队：代号U1”的「副队长」。"),
    TEXT("我的名字是——"),
    TEXT("我叫%s，我当前的任务是帮助她们走到最后，阻止“第三次黑潮”。#r我的异能是……#r不知为何，我怎么也想不起来了……#r仿佛，那是不能碰触的禁忌。"),
};
}

const TArrayView<const TCHAR* const> HczsPrologueAvg134()
{
    return Narration134;
}

FString HczsPrologueAvg134Line(int32 Index, const FString& PlayerName)
{
    if (Index < 0 || Index >= UE_ARRAY_COUNT(Narration134)) return FString();
    return FString(Narration134[Index]).Replace(TEXT("%s"), *PlayerName).Replace(TEXT("#r"), TEXT("\n"));
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

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsPrologueAvg134Test, "Hczs.Dungeon.PrologueAvg134",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FHczsPrologueAvg134Test::RunTest(const FString& Parameters)
{
    TestEqual(TEXT("Six narration rows"), HczsPrologueAvg134().Num(), 6);
    TestEqual(TEXT("Line breaks"), HczsPrologueAvg134Line(1, TEXT("")),
        FString(TEXT("我无法回答她。\n她等待了一会，随后露出了一个释怀的微笑，她说，请你代替我，好好地陪伴她。\n之后，我彻底坠入了黑暗。")));
    TestTrue(TEXT("Name filled"), HczsPrologueAvg134Line(5, TEXT("测试")).StartsWith(TEXT("我叫测试，")));
    TestTrue(TEXT("Out of range is empty"), HczsPrologueAvg134Line(6, TEXT("x")).IsEmpty());
    return true;
}
