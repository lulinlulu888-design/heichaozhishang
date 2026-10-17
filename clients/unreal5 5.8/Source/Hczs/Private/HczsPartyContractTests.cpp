#include "HczsSessionContract.h"
#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

#if WITH_DEV_AUTOMATION_TESTS
using namespace HczsSessionContract;
namespace
{
    const FString PartyProfileId = TEXT("11111111-1111-1111-1111-111111111111");
    const FString PartyBattleId = TEXT("22222222-2222-2222-2222-222222222222");
    const FString PartyMainlineId = TEXT("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef");
    TSharedPtr<FJsonObject> ReadJson(const FString& Text)
    {
        TSharedPtr<FJsonObject> Object; FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Object); return Object;
    }
    TSharedPtr<FJsonObject> Copy(const TSharedPtr<FJsonObject>& Object) { return ReadJson(Serialize(Object)); }
    TSharedPtr<FJsonObject> PartyFixture()
    {
        FString Json;
        if (!FFileHelper::LoadFileToString(Json, *FPaths::Combine(FPaths::ProjectDir(),
            TEXT("Source/Hczs/Private/Tests/Fixtures/prologue-boss-party-v1.json")))) return nullptr;
        return ReadJson(Json);
    }
    TArray<TSharedPtr<FJsonObject>> Steps(const TSharedPtr<FJsonObject>& Fixture, const TCHAR* Field)
    {
        TArray<TSharedPtr<FJsonObject>> Result;
        const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
        if (Fixture.IsValid() && Fixture->TryGetArrayField(Field, Values) && Values)
            for (const auto& Value : *Values) Result.Add(Value->AsObject());
        return Result;
    }
    bool ParseStep(const TSharedPtr<FJsonObject>& Step, FHczsBattleView& View, FHczsBattleVisualReceipt& Visual, TArray<FString>& Events)
    {
        const auto Command = Child(Step, TEXT("command")); const auto Receipt = Child(Step, TEXT("receipt"));
        FString Type, Instance; double Expected = 0;
        if (!Command.IsValid() || !Command->TryGetStringField(TEXT("type"), Type) || !Command->TryGetNumberField(TEXT("expectedRevision"), Expected)) return false;
        Command->TryGetStringField(TEXT("instanceId"), Instance);
        return ParseReceipt(Receipt, PartyProfileId, PartyBattleId, TEXT("prologue-boss-1703"), static_cast<int64>(Expected),
            View, Events, Type, Instance, &Visual);
    }
    TSharedPtr<FJsonObject> BossMainline(int32 Revision)
    {
        auto C = ReadJson(TEXT(R"JSON({
          "profileId":"11111111-1111-1111-1111-111111111111","activityId":2,
          "contentId":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
          "policy":"local-prologue-progress-v1","revision":0,"updatedAt":null,
          "initialStateAuthority":"local-fresh-profile-policy; not recovered original account state",
          "activityDatas":null,
          "challenges":[
            {"id":3997,"name":"终局","subtitle":"序章","battleId":5000,"predecessors":[],"hasLoot":false,
             "status":"available","recordPresent":false,"successTime":null,"encounterId":"tutorial-5000","executable":true},
            {"id":3998,"name":"终局","subtitle":"序章","battleId":1703,"predecessors":[3997],"hasLoot":false,
             "status":"locked","recordPresent":false,"successTime":null,"encounterId":"prologue-boss-1703","executable":true}],"completed":[]
        })JSON"));
        if (Revision == 0) return C;
        C->SetNumberField(TEXT("revision"), Revision); C->SetNumberField(TEXT("updatedAt"), 300);
        const auto Challenges = C->GetArrayField(TEXT("challenges"));
        auto Records = MakeShared<FJsonObject>(); auto Activity = MakeShared<FJsonObject>();
        TArray<TSharedPtr<FJsonValue>> Completed;
        for (int32 Index = 0; Index < Revision; ++Index)
        {
            auto Node = Challenges[Index]->AsObject();
            Node->SetStringField(TEXT("status"), TEXT("passed")); Node->SetBoolField(TEXT("recordPresent"), true); Node->SetNumberField(TEXT("successTime"), 1);
            auto Row = MakeShared<FJsonObject>(); Row->SetNumberField(TEXT("successTime"), 1);
            Activity->SetObjectField(FString::FromInt(3997 + Index), Row);
            auto Done = MakeShared<FJsonObject>(); Done->SetNumberField(TEXT("challengeId"), 3997 + Index);
            Done->SetStringField(TEXT("battleId"), Index == 0 ? TEXT("33333333-3333-3333-3333-333333333333") : PartyBattleId);
            Done->SetNumberField(TEXT("battleRevision"), Index == 0 ? 9 : 27); Done->SetNumberField(TEXT("completedAt"), Index == 0 ? 200 : 300);
            Completed.Add(MakeShared<FJsonValueObject>(Done));
        }
        if (Revision == 1) Challenges[1]->AsObject()->SetStringField(TEXT("status"), TEXT("available"));
        Records->SetObjectField(TEXT("2"), Activity); C->SetObjectField(TEXT("activityDatas"), Records);
        C->SetArrayField(TEXT("completed"), Completed);
        return C;
    }
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsPartyBattleContractTest, "Hczs.LocalSession.Contract.PartyBattle", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsPartyBattleContractTest::RunTest(const FString& Parameters)
{
    const auto Fixture = PartyFixture();
    if (!TestTrue(TEXT("Party fixture loads"), Fixture.IsValid())) return false;
    FHczsBattleView View;
    const auto Initial = Child(Child(Fixture, TEXT("initial")), TEXT("battle"));
    TestTrue(TEXT("Fresh boss battle parses"), ParseBattle(Initial, PartyProfileId, PartyBattleId, View));
    TestTrue(TEXT("Party view keeps both source members"), View.bIsParty && View.Party.Num() == 2 &&
        View.Party[0].Id == TEXT("1") && View.Party[1].Id == TEXT("3") && View.Party[1].Name == TEXT("未来"));
    TestEqual(TEXT("Player fields mirror the animated member"), View.PlayerHp.Decimal, View.Party[0].Hp.Decimal);
    TestEqual(TEXT("Boss identity"), View.EnemyId, FString(TEXT("2013")));
    TestEqual(TEXT("Boss intent previews calcDamage per hit"), View.EnemyIntentText, FString(TEXT("首位伤害 144 ×3")));
    const FHczsHandCard* Shield = View.Hand.FindByPredicate([](const FHczsHandCard& C) { return C.CardId == TEXT("140004"); });
    const FHczsHandCard* Double = View.Hand.FindByPredicate([](const FHczsHandCard& C) { return C.CardId == TEXT("410101"); });
    TestTrue(TEXT("Future owns the party shield with a calcBlock preview"), Shield && Shield->OwnerId == TEXT("3") && Shield->OwnerIndex == 1 &&
        Shield->EffectsText == TEXT("全队护盾 1206"));
    TestTrue(TEXT("Elsa's double slash previews trunc(482.4 * 75 / 100)"), Double && Double->OwnerName == TEXT("艾尔莎") && Double->FirstDamage == TEXT("361"));
    TestEqual(TEXT("Neutral calcDamage with five stacks"), PartyDamagePreview(180.0, 160, 5, 6), static_cast<int64>(374));

    int32 PartyHits = 0, EnemyHits = 0, OwnedPlays = 0;
    FHczsBattleView Last;
    for (const auto& Step : Steps(Fixture, TEXT("steps")))
    {
        FHczsBattleVisualReceipt Visual; TArray<FString> Events;
        if (!TestTrue(TEXT("Every scripted win receipt parses"), ParseStep(Step, Last, Visual, Events))) return false;
        for (const auto& Event : Visual.Events)
        {
            if (Event.Type == TEXT("DamageApplied") && Event.Target == TEXT("enemy")) ++EnemyHits;
            if (Event.Type == TEXT("DamageApplied") && Event.Target == TEXT("player") && Event.MemberIndex == 0) ++PartyHits;
            if (Event.Type == TEXT("CardPlayed") && Event.MemberIndex >= 0) ++OwnedPlays;
        }
    }
    TestTrue(TEXT("Scripted run ends in a won party state"), Last.Status == TEXT("won") && Last.OutcomeReason == TEXT("enemy-defeated") && Last.EnemyHp.Approximate == 0);
    TestEqual(TEXT("Seven boss hits all land on Elsa first"), PartyHits, 7);
    TestTrue(TEXT("Card plays carry owners and enemy damage"), OwnedPlays > 0 && EnemyHits > 0);

    int32 Defeats = 0;
    for (const auto& Step : Steps(Fixture, TEXT("lossSteps")))
    {
        FHczsBattleVisualReceipt Visual; TArray<FString> Events;
        if (!TestTrue(TEXT("Every end-turn loss receipt parses"), ParseStep(Step, Last, Visual, Events))) return false;
        for (const auto& Event : Visual.Events) if (Event.Type == TEXT("MemberDefeated")) ++Defeats;
    }
    TestTrue(TEXT("Loss removes both members' cards"), Last.Status == TEXT("lost") && Last.OutcomeReason == TEXT("party-defeated") &&
        Defeats == 2 && Last.RemovedCount == 14 && Last.Hand.IsEmpty());

    FHczsBattleView Rejected;
    auto Bad = Copy(Initial);
    Child(Child(Bad, TEXT("scenario")), TEXT("definition"))->GetObjectField(TEXT("partyRules"))->SetStringField(TEXT("policy"), TEXT("original-party-rules"));
    TestFalse(TEXT("Party rules cannot claim recovered policy"), ParseBattle(Bad, PartyProfileId, PartyBattleId, Rejected));
    Bad = Copy(Initial);
    Child(Child(Bad, TEXT("scenario")), TEXT("definition"))->GetArrayField(TEXT("deck"))[0]->AsObject()->SetStringField(TEXT("ownerId"), TEXT("2013"));
    TestFalse(TEXT("Deck owner must be a party member"), ParseBattle(Bad, PartyProfileId, PartyBattleId, Rejected));
    Bad = Copy(Initial);
    Child(Bad, TEXT("state"))->GetArrayField(TEXT("cards"))[0]->AsObject()->SetStringField(TEXT("ownerId"), TEXT("1"));
    TestFalse(TEXT("State registry cannot reassign an owner"), ParseBattle(Bad, PartyProfileId, PartyBattleId, Rejected));
    Bad = Copy(Initial);
    auto Piles = Child(Child(Bad, TEXT("state")), TEXT("piles"));
    auto Hand = Piles->GetArrayField(TEXT("hand")); const auto Moved = Hand.Pop();
    Piles->SetArrayField(TEXT("hand"), Hand); Piles->SetArrayField(TEXT("removed"), {Moved});
    TestFalse(TEXT("A living member's card cannot be removed"), ParseBattle(Bad, PartyProfileId, PartyBattleId, Rejected));
    Bad = Copy(Initial);
    Child(Bad, TEXT("state"))->GetArrayField(TEXT("party"))[1]->AsObject()->SetObjectField(TEXT("hp"),
        ReadJson(TEXT(R"JSON({"numeric_type":"integer","decimal":"2011"})JSON")));
    TestFalse(TEXT("Member HP cannot exceed its maximum"), ParseBattle(Bad, PartyProfileId, PartyBattleId, Rejected));

    const auto FirstEnd = Steps(Fixture, TEXT("lossSteps"))[0];
    auto Tampered = Copy(FirstEnd);
    for (const auto& Value : Child(Tampered, TEXT("receipt"))->GetArrayField(TEXT("events")))
        if (Value->AsObject()->GetStringField(TEXT("type")) == TEXT("DamageApplied")) { Value->AsObject()->SetStringField(TEXT("target"), TEXT("enemy")); break; }
    FHczsBattleVisualReceipt Visual; TArray<FString> Events;
    TestFalse(TEXT("Boss damage must target a party member"), ParseStep(Tampered, Rejected, Visual, Events));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsBossMainlineContractTest, "Hczs.LocalSession.Contract.BossMainline", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsBossMainlineContractTest::RunTest(const FString& Parameters)
{
    FHczsMainlineProgress Fresh, First, Both, Rejected;
    TestTrue(TEXT("Bound 3998 is locked before 3997"), ParseMainline(BossMainline(0), PartyProfileId, PartyMainlineId, Fresh) &&
        Fresh.Challenges[1].bExecutable && Fresh.Challenges[1].Status == TEXT("locked"));
    TestTrue(TEXT("After 3997 the bound boss is available"), ParseMainline(BossMainline(1), PartyProfileId, PartyMainlineId, First) &&
        First.Challenges[1].Status == TEXT("available") && !First.bBossChallengePassed);
    TestTrue(TEXT("Both completions project two successTime records"), ParseMainline(BossMainline(2), PartyProfileId, PartyMainlineId, Both) &&
        Both.bBossChallengePassed && Both.CompletedBattleId == PartyBattleId && Both.CompletedBattleIds.Num() == 2);
    auto Bad = BossMainline(2);
    Bad->GetArrayField(TEXT("completed"))[0]->AsObject()->SetNumberField(TEXT("challengeId"), 3998);
    TestFalse(TEXT("Completions must follow the predecessor chain"), ParseMainline(Bad, PartyProfileId, PartyMainlineId, Rejected));
    Bad = BossMainline(2);
    Bad->GetArrayField(TEXT("completed"))[1]->AsObject()->SetNumberField(TEXT("completedAt"), 150);
    TestFalse(TEXT("A later completion cannot predate the earlier one"), ParseMainline(Bad, PartyProfileId, PartyMainlineId, Rejected));
    Bad = BossMainline(1);
    Bad->GetArrayField(TEXT("challenges"))[1]->AsObject()->SetStringField(TEXT("encounterId"), TEXT("city-preview-10405"));
    TestFalse(TEXT("Only the boss encounter may bind 3998"), ParseMainline(Bad, PartyProfileId, PartyMainlineId, Rejected));

    FHczsBattleView Won; Won.bIsValid = true; Won.bIsParty = true; Won.Id = PartyBattleId; Won.ProfileId = PartyProfileId; Won.Revision = 27;
    Won.EncounterId = TEXT("prologue-boss-1703"); Won.PlayerId = TEXT("party-1-3"); Won.EnemyId = TEXT("2013");
    Won.Status = TEXT("won"); Won.OutcomeReason = TEXT("enemy-defeated");
    TestTrue(TEXT("Boss victory settles after 3997"), CanSettleMainlineBattle(First, Won));
    TestFalse(TEXT("Boss victory cannot skip 3997"), CanSettleMainlineBattle(Fresh, Won));
    TestFalse(TEXT("Boss victory cannot settle twice"), CanSettleMainlineBattle(Both, Won));
    Won.bIsParty = false;
    TestFalse(TEXT("A non-party battle cannot impersonate the boss"), CanSettleMainlineBattle(First, Won));

    auto Receipt = MakeShared<FJsonObject>(); auto Campaign = BossMainline(2);
    Receipt->SetObjectField(TEXT("campaign"), Campaign);
    Receipt->SetObjectField(TEXT("settlement"), Copy(Campaign->GetArrayField(TEXT("completed"))[1]->AsObject()));
    Receipt->SetArrayField(TEXT("rewards"), {}); Receipt->SetBoolField(TEXT("replayed"), false);
    FHczsMainlineProgress Settled;
    TestTrue(TEXT("Boss settlement receipt confirms the second completion"),
        ParseMainlineReceipt(Receipt, PartyProfileId, PartyMainlineId, PartyBattleId, 27, 1, Settled) && Settled.bBossChallengePassed);
    Receipt->SetObjectField(TEXT("settlement"), Copy(Campaign->GetArrayField(TEXT("completed"))[0]->AsObject()));
    TestFalse(TEXT("Receipt must echo the newest completion"), ParseMainlineReceipt(Receipt, PartyProfileId, PartyMainlineId, PartyBattleId, 27, 1, Rejected));

    TestTrue(TEXT("Progress appends the boss completion"), CanApplyMainlineProgress(First, Both, 2));
    TestFalse(TEXT("Stale GET cannot drop the boss completion"), CanApplyMainlineProgress(Both, First));
    auto Rewritten = Both; Rewritten.CompletedBattleIds[0] = PartyProfileId;
    TestFalse(TEXT("Earlier completions stay immutable"), CanApplyMainlineProgress(First, Rewritten));
    return true;
}
#endif
