#include "HczsSessionContract.h"
#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include <limits>

#if WITH_DEV_AUTOMATION_TESTS
using namespace HczsSessionContract;
namespace
{
    const FString ProfileId = TEXT("11111111-1111-1111-1111-111111111111");
    const FString BattleId = TEXT("22222222-2222-2222-2222-222222222222");
    const FString MainlineId = TEXT("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef");
    TSharedPtr<FJsonObject> Read(const FString& Text)
    {
        TSharedPtr<FJsonObject> Object; FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Object); return Object;
    }
    TSharedPtr<FJsonObject> Fixture()
    {
        return Read(TEXT(R"JSON({
          "id":"22222222-2222-2222-2222-222222222222", "profileId":"11111111-1111-1111-1111-111111111111", "revision":1,
          "scenario":{"title":"契约样本", "notice":"独立测试", "encounterId":"test-encounter",
            "definition":{"id":"test-definition", "player":{"id":"1","name":"艾尔莎","maxHp":{"numeric_type":"integer","decimal":"100"}},
              "enemy":{"id":"991","name":"幻眼魔方","maxHp":{"numeric_type":"integer","decimal":"100"}},
              "deck":[{"instanceId":"card-1","cardId":"110001"}], "cards":{"110001":{"name":"斩击","cost":1,"effects":[{"type":"damage","target":"opponent","amount":"5"}]}},
              "enemySkills":{"9911":{"effects":[{"type":"damage","target":"opponent","amount":"2"}]}},
              "enemyIntents":[["9911"]], "enemyFallback":["9911"], "initialDraw":1,"roundDraw":1,"energyPerRound":1,"handLimit":10,"maxRounds":10,
              "statusRules":{"policy":"breakdown-reconstruction-v1","attack":{"player":{"numeric_type":"integer","decimal":"10"},"enemy":{"numeric_type":"integer","decimal":"10"}}}}},
          "state":{"format":"hczs-battle-session-v2","definitionId":"test-definition","round":1,"status":"player-turn","outcomeReason":null,"energy":1,"actionIndex":0,
            "breakdown":{"player":0,"enemy":0}, "player":{"hp":{"numeric_type":"integer","decimal":"100"},"shield":{"numeric_type":"integer","decimal":"0"}},
            "enemy":{"hp":{"numeric_type":"integer","decimal":"100"},"shield":{"numeric_type":"integer","decimal":"0"}},
            "cards":[{"instanceId":"card-1","cardId":"110001"}],"piles":{"hand":["card-1"],"draw":[],"discard":[],"exhausted":[],"powerUsed":[],"removed":[]},
            "rng":{"algorithm":"mulberry32-v1","state":7}}, "createdAt":100,"updatedAt":100
        })JSON"));
    }
    TSharedPtr<FJsonObject> Receipt(const TSharedPtr<FJsonObject>& Battle, bool bAction = false)
    {
        auto R = MakeShared<FJsonObject>(); R->SetObjectField(TEXT("battle"), Battle); R->SetBoolField(TEXT("replayed"), false);
        auto First = MakeShared<FJsonObject>();
        if (bAction)
        {
            First->SetStringField(TEXT("type"), TEXT("CardPlayed")); First->SetStringField(TEXT("instanceId"), TEXT("card-1"));
            First->SetStringField(TEXT("cardId"), TEXT("110001")); First->SetNumberField(TEXT("cost"), 1);
        }
        else
        {
            First->SetStringField(TEXT("type"), TEXT("BattleStarted")); First->SetStringField(TEXT("definitionId"), TEXT("test-definition")); First->SetNumberField(TEXT("seed"), 7);
        }
        auto Last = MakeShared<FJsonObject>(); Last->SetStringField(TEXT("type"), TEXT("StateUpdated"));
        Last->SetObjectField(TEXT("state"), Read(Serialize(Child(Battle, TEXT("state")))));
        R->SetArrayField(TEXT("events"), {MakeShared<FJsonValueObject>(First), MakeShared<FJsonValueObject>(Last)});
        return R;
    }
    TSharedPtr<FJsonObject> UltimateReceipt(const FString& Step = FString())
    {
        FString Json;
        if (!FFileHelper::LoadFileToString(Json, *FPaths::Combine(FPaths::ProjectDir(),
            TEXT("Source/Hczs/Private/Tests/Fixtures/city-ultimate-v3.json")))) return nullptr;
        const auto Root = Read(Json); if (!Root.IsValid()) return nullptr;
        if (Step.IsEmpty()) return Child(Root, TEXT("initial"));
        const TArray<TSharedPtr<FJsonValue>>* Steps = nullptr;
        if (!Root->TryGetArrayField(TEXT("steps"), Steps) || !Steps) return nullptr;
        for (const auto& Value : *Steps)
        {
            const auto Object = Value->AsObject(); FString Name;
            if (Object.IsValid() && Object->TryGetStringField(TEXT("name"), Name) && Name == Step) return Child(Object, TEXT("receipt"));
        }
        return nullptr;
    }
    TSharedPtr<FJsonObject> MainlineFixture(bool bPassed = false)
    {
        auto C = Read(TEXT(R"JSON({
          "profileId":"11111111-1111-1111-1111-111111111111","activityId":2,
          "contentId":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
          "policy":"local-prologue-progress-v1","revision":0,"updatedAt":null,
          "initialStateAuthority":"local-fresh-profile-policy; not recovered original account state",
          "activityDatas":null,
          "challenges":[
            {"id":3997,"name":"终局","subtitle":"序章","battleId":5000,"predecessors":[],"hasLoot":false,
             "status":"available","recordPresent":false,"successTime":null,"encounterId":"tutorial-5000","executable":true},
            {"id":3998,"name":"终局","subtitle":"序章","battleId":1703,"predecessors":[3997],"hasLoot":false,
             "status":"locked","recordPresent":false,"successTime":null,"encounterId":null,"executable":false,
             "unavailableReason":"original-boss-mechanics-and-client-not-restored"}],"completed":[]
        })JSON"));
        if (bPassed)
        {
            C->SetNumberField(TEXT("revision"), 1); C->SetNumberField(TEXT("updatedAt"), 200);
            auto First = C->GetArrayField(TEXT("challenges"))[0]->AsObject();
            First->SetStringField(TEXT("status"), TEXT("passed")); First->SetBoolField(TEXT("recordPresent"), true); First->SetNumberField(TEXT("successTime"), 1);
            auto Records = MakeShared<FJsonObject>(); auto Activity = MakeShared<FJsonObject>(); auto Row = MakeShared<FJsonObject>();
            Row->SetNumberField(TEXT("successTime"), 1); Activity->SetObjectField(TEXT("3997"), Row); Records->SetObjectField(TEXT("2"), Activity);
            C->SetObjectField(TEXT("activityDatas"), Records);
            C->GetArrayField(TEXT("challenges"))[1]->AsObject()->SetStringField(TEXT("status"), TEXT("available"));
            auto Done = Read(TEXT(R"JSON({"challengeId":3997,"battleId":"22222222-2222-2222-2222-222222222222","battleRevision":9,"completedAt":200})JSON"));
            C->SetArrayField(TEXT("completed"), {MakeShared<FJsonValueObject>(Done)});
        }
        return C;
    }
    TSharedPtr<FJsonObject> MainlineReceiptFixture()
    {
        auto R = MakeShared<FJsonObject>(); auto C = MainlineFixture(true);
        R->SetObjectField(TEXT("campaign"), C);
        R->SetObjectField(TEXT("settlement"), Read(Serialize(C->GetArrayField(TEXT("completed"))[0]->AsObject())));
        R->SetArrayField(TEXT("rewards"), {}); R->SetBoolField(TEXT("replayed"), false); return R;
    }
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsSessionMainlineContractTest, "Hczs.LocalSession.Contract.MainlineProgress", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsSessionMainlineContractTest::RunTest(const FString& Parameters)
{
    FHczsMainlineProgress Fresh, Passed, Rejected;
    TestTrue(TEXT("Fresh progress has revision zero and null timestamp"), ParseMainline(MainlineFixture(), ProfileId, MainlineId, Fresh));
    TestTrue(TEXT("One confirmed tutorial win projects passed and next available"), ParseMainline(MainlineFixture(true), ProfileId, MainlineId, Passed));
    TestTrue(TEXT("First challenge is recorded"), Passed.bFirstChallengePassed);
    TestFalse(TEXT("Next challenge never gains an executable boss"), Passed.Challenges[1].bExecutable);
    TestEqual(TEXT("Next source challenge may be available without a restored battle"), Passed.Challenges[1].Status, FString(TEXT("available")));
    TestFalse(TEXT("Cross-profile campaign rejected"), ParseMainline(MainlineFixture(), BattleId, MainlineId, Rejected));
    TestFalse(TEXT("Unverified content identity rejected"), ParseMainline(MainlineFixture(), ProfileId, FString::ChrN(64, 'f'), Rejected));
    auto Bad = MainlineFixture(); Bad->SetNumberField(TEXT("revision"), 1);
    TestFalse(TEXT("Completion is required for revision one"), ParseMainline(Bad, ProfileId, MainlineId, Rejected));
    Bad = MainlineFixture(); Bad->SetNumberField(TEXT("updatedAt"), 0);
    TestFalse(TEXT("Fresh virtual state does not invent a save timestamp"), ParseMainline(Bad, ProfileId, MainlineId, Rejected));
    Bad = MainlineFixture(true); Bad->GetArrayField(TEXT("challenges"))[1]->AsObject()->SetBoolField(TEXT("executable"), true);
    TestFalse(TEXT("Unrestored boss cannot become executable"), ParseMainline(Bad, ProfileId, MainlineId, Rejected));
    Bad = MainlineFixture(); Bad->GetArrayField(TEXT("challenges"))[0]->AsObject()->SetStringField(TEXT("encounterId"), TEXT("city-preview-10405"));
    TestFalse(TEXT("City preview cannot replace the tutorial"), ParseMainline(Bad, ProfileId, MainlineId, Rejected));
    Bad = MainlineFixture(); Bad->GetArrayField(TEXT("challenges"))[0]->AsObject()->SetBoolField(TEXT("hasLoot"), true);
    TestFalse(TEXT("Unimplemented rewards rejected"), ParseMainline(Bad, ProfileId, MainlineId, Rejected));
    Bad = MainlineFixture(true); Bad->GetArrayField(TEXT("completed"))[0]->AsObject()->SetNumberField(TEXT("challengeId"), 3998);
    TestFalse(TEXT("Unrestored challenge completion rejected"), ParseMainline(Bad, ProfileId, MainlineId, Rejected));
    Bad = MainlineFixture(true); Bad->SetNumberField(TEXT("updatedAt"), 199);
    TestFalse(TEXT("Completion cannot postdate the authoritative state"), ParseMainline(Bad, ProfileId, MainlineId, Rejected));
    Bad = MainlineFixture(); Bad->SetStringField(TEXT("policy"), TEXT("original-account-restored"));
    TestFalse(TEXT("Local progress does not claim recovered original account state"), ParseMainline(Bad, ProfileId, MainlineId, Rejected));
    Bad = MainlineFixture(); Bad->GetArrayField(TEXT("challenges"))[0]->AsObject()->SetNumberField(TEXT("successTime"), 0);
    TestFalse(TEXT("A missing challenge is not stored as successTime zero"), ParseMainline(Bad, ProfileId, MainlineId, Rejected));
    TestTrue(TEXT("Latest progress advances monotonically"), CanApplyMainlineProgress(Fresh, Passed, 1));
    TestFalse(TEXT("Stale GET cannot undo confirmation"), CanApplyMainlineProgress(Passed, Fresh, 1));
    auto Changed = Passed; Changed.ContentId = FString::ChrN(64, 'f');
    TestFalse(TEXT("Unverified content switch rejected"), CanApplyMainlineProgress(Passed, Changed));
    Changed = Passed; Changed.ProfileId = BattleId;
    TestFalse(TEXT("Another profile cannot borrow a completed campaign"), CanApplyMainlineProgress(Passed, Changed));
    Changed = Passed; Changed.CompletedBattleId = ProfileId;
    TestFalse(TEXT("Same revision cannot replace the completed battle"), CanApplyMainlineProgress(Passed, Changed));
    Changed = Passed; Changed.CompletedAt = 199;
    TestFalse(TEXT("Completion timestamp is immutable"), CanApplyMainlineProgress(Passed, Changed));
    FHczsBattleView Won; Won.bIsValid = true; Won.Id = BattleId; Won.ProfileId = ProfileId; Won.Revision = 9;
    Won.EncounterId = TEXT("tutorial-5000"); Won.PlayerId = TEXT("1"); Won.EnemyId = TEXT("991");
    Won.Status = TEXT("won"); Won.OutcomeReason = TEXT("enemy-defeated");
    TestTrue(TEXT("Only verified tutorial victory enables confirmation"), CanSettleMainlineBattle(Fresh, Won));
    TestFalse(TEXT("Passed challenge cannot be settled twice"), CanSettleMainlineBattle(Passed, Won));
    Won.EncounterId = TEXT("city-preview-10405");
    TestFalse(TEXT("City victory is not mainline victory"), CanSettleMainlineBattle(Fresh, Won));
    Won.EncounterId = TEXT("tutorial-5000"); Won.EnemyId = TEXT("6605");
    TestFalse(TEXT("Wrong enemy cannot impersonate the restored scene"), CanSettleMainlineBattle(Fresh, Won));
    Won.EnemyId = TEXT("991"); Won.ProfileId = BattleId;
    TestFalse(TEXT("Cross-profile victory cannot advance progress"), CanSettleMainlineBattle(Fresh, Won));
    Won.ProfileId = ProfileId; Won.Status = TEXT("player-turn");
    TestFalse(TEXT("Unfinished battle has no confirmation"), CanSettleMainlineBattle(Fresh, Won));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsSessionMainlineReceiptTest, "Hczs.LocalSession.Contract.MainlineReceiptAndCapability", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsSessionMainlineReceiptTest::RunTest(const FString& Parameters)
{
    auto Bootstrap = Read(TEXT(R"JSON({"capabilities":["local-profiles","encounter-selection"]})JSON"));
    bool Enabled = true; FString Content;
    TestTrue(TEXT("Older service remains supported without mainline"), ParseMainlineCapability(Bootstrap, Enabled, Content));
    TestFalse(TEXT("Absent capability does not invent progress"), Enabled);
    Bootstrap = Read(TEXT(R"JSON({"capabilities":["mainline-progression"],
      "content":{"mainlineId":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"},
      "endpoints":{"mainline":"/api/rebuild/v1/profiles/{profileId}/mainline","settlements":"/api/rebuild/v1/profiles/{profileId}/mainline/settlements"}})JSON"));
    TestTrue(TEXT("Versioned capability requires reviewed local routes and content hash"), ParseMainlineCapability(Bootstrap, Enabled, Content));
    TestTrue(TEXT("Mainline is explicitly enabled"), Enabled);
    Child(Bootstrap, TEXT("endpoints"))->SetStringField(TEXT("settlements"), TEXT("https://elsewhere/settle"));
    TestFalse(TEXT("External settlement route rejected"), ParseMainlineCapability(Bootstrap, Enabled, Content));
    Child(Bootstrap, TEXT("content"))->SetStringField(TEXT("mainlineId"), TEXT("unknown"));
    TestFalse(TEXT("Malformed content identity rejected"), ParseMainlineCapability(Bootstrap, Enabled, Content));
    FHczsMainlineProgress Progress;
    auto R = MainlineReceiptFixture();
    TestTrue(TEXT("Actual one-time receipt accepted"), ParseMainlineReceipt(R, ProfileId, MainlineId, BattleId, 9, 0, Progress));
    R->SetBoolField(TEXT("replayed"), true);
    TestTrue(TEXT("Identical idempotent historical receipt accepted"), ParseMainlineReceipt(R, ProfileId, MainlineId, BattleId, 9, 0, Progress));
    TestFalse(TEXT("Expected revision comes from campaign, not battle"), ParseMainlineReceipt(R, ProfileId, MainlineId, BattleId, 9, 9, Progress));
    TestFalse(TEXT("Receipt must confirm the exact won battle revision"), ParseMainlineReceipt(R, ProfileId, MainlineId, BattleId, 8, 0, Progress));
    TestFalse(TEXT("Another battle cannot satisfy this command"), ParseMainlineReceipt(R, ProfileId, MainlineId, ProfileId, 9, 0, Progress));
    Child(R, TEXT("settlement"))->SetNumberField(TEXT("completedAt"), 199);
    TestFalse(TEXT("Settlement must equal the campaign completion row"), ParseMainlineReceipt(R, ProfileId, MainlineId, BattleId, 9, 0, Progress));
    R = MainlineReceiptFixture(); R->SetArrayField(TEXT("rewards"), {MakeShared<FJsonValueString>(TEXT("invented-reward"))});
    TestFalse(TEXT("Reward list must remain empty"), ParseMainlineReceipt(R, ProfileId, MainlineId, BattleId, 9, 0, Progress));
    R = MainlineReceiptFixture(); R->SetStringField(TEXT("replayed"), TEXT("true"));
    TestFalse(TEXT("Replay flag must be a boolean"), ParseMainlineReceipt(R, ProfileId, MainlineId, BattleId, 9, 0, Progress));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsSessionBattleContractTest, "Hczs.LocalSession.Contract.BattleProjection", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsSessionBattleContractTest::RunTest(const FString& Parameters)
{
    FHczsBattleView View;
    TestTrue(TEXT("Known reconstruction state is parsed"), ParseBattle(Fixture(), ProfileId, BattleId, View));
    TestEqual(TEXT("Only source hand becomes interactive cards"), View.Hand.Num(), 1);
    TestEqual(TEXT("Server decimal is retained"), View.PlayerHp.Decimal, FString(TEXT("100")));
    TestFalse(TEXT("Cross-profile response is rejected"), ParseBattle(Fixture(), TEXT("33333333-3333-3333-3333-333333333333"), BattleId, View));
    TestFalse(TEXT("Wrong battle response is rejected"), ParseBattle(Fixture(), ProfileId, TEXT("33333333-3333-3333-3333-333333333333"), View));
    auto Bad = Fixture(); Bad->SetNumberField(TEXT("revision"), 2);
    TestFalse(TEXT("Revision must match persisted actionIndex+1"), ParseBattle(Bad, ProfileId, BattleId, View));
    Bad = Fixture(); Child(Bad, TEXT("state"))->SetNumberField(TEXT("energy"), -1);
    TestFalse(TEXT("Negative counters rejected"), ParseBattle(Bad, ProfileId, BattleId, View));
    Bad = Fixture(); Child(Bad, TEXT("state"))->SetNumberField(TEXT("energy"), std::numeric_limits<double>::quiet_NaN());
    TestFalse(TEXT("Non-finite counters rejected"), ParseBattle(Bad, ProfileId, BattleId, View));
    Bad = Fixture(); Child(Bad, TEXT("state"))->SetStringField(TEXT("definitionId"), TEXT("different-definition"));
    TestFalse(TEXT("Scenario/state identity mismatch rejected"), ParseBattle(Bad, ProfileId, BattleId, View));
    Bad = Fixture(); Child(Child(Bad, TEXT("state")), TEXT("piles"))->SetArrayField(TEXT("draw"), {MakeShared<FJsonValueString>(TEXT("card-1"))});
    TestFalse(TEXT("Duplicated pile instance rejected"), ParseBattle(Bad, ProfileId, BattleId, View));
    Bad = Fixture(); Child(Child(Bad, TEXT("state")), TEXT("piles"))->SetArrayField(TEXT("hand"), {});
    TestFalse(TEXT("Missing instance rejected"), ParseBattle(Bad, ProfileId, BattleId, View));
    Bad = Fixture(); Child(Child(Bad, TEXT("scenario")), TEXT("definition"))->SetArrayField(TEXT("enemyFallback"), {MakeShared<FJsonValueString>(TEXT("unknown-skill"))});
    TestFalse(TEXT("Unknown enemy intent rejected"), ParseBattle(Bad, ProfileId, BattleId, View));
    Bad = Fixture(); auto Hp = Child(Child(Child(Bad, TEXT("state")), TEXT("player")), TEXT("hp"));
    Hp->SetStringField(TEXT("numeric_type"), TEXT("binary64")); Hp->SetStringField(TEXT("decimal"), TEXT("100.0")); Hp->SetStringField(TEXT("hex"), TEXT("0x1.0p+1"));
    TestFalse(TEXT("Binary64 decimal/hex disagreement rejected"), ParseBattle(Bad, ProfileId, BattleId, View));
    Hp->SetStringField(TEXT("decimal"), TEXT("0.1")); Hp->SetStringField(TEXT("hex"), TEXT("0x1.999999999999ap-4"));
    TestTrue(TEXT("Finite exact tagged binary64 preserved"), ParseBattle(Bad, ProfileId, BattleId, View));
    for (const TCHAR* InvalidDecimal : {TEXT(" 0.1"), TEXT("0.1 "), TEXT("+0.1"), TEXT("0,1"), TEXT("0.1junk"), TEXT("0.1e"), TEXT("nan"), TEXT("inf"), TEXT("1e9999"), TEXT("1e-9999")})
    {
        Hp->SetStringField(TEXT("decimal"), InvalidDecimal);
        Hp->SetStringField(TEXT("hex"), FString(InvalidDecimal) == TEXT("1e-9999") ? TEXT("0x0.0p+0") : TEXT("0x1.999999999999ap-4"));
        TestFalse(FString::Printf(TEXT("Malformed or out-of-range decimal rejected: %s"), InvalidDecimal), ParseBattle(Bad, ProfileId, BattleId, View));
    }
    Hp->SetStringField(TEXT("decimal"), TEXT("1e-1")); Hp->SetStringField(TEXT("hex"), TEXT("0x1.999999999999ap-4"));
    TestTrue(TEXT("Exponent decimal preserves exact binary64"), ParseBattle(Bad, ProfileId, BattleId, View));
    Bad = Fixture(); Child(Bad, TEXT("state"))->SetStringField(TEXT("status"), TEXT("won")); Child(Bad, TEXT("state"))->SetStringField(TEXT("outcomeReason"), TEXT("enemy-defeated"));
    TestFalse(TEXT("A victory cannot have a live enemy"), ParseBattle(Bad, ProfileId, BattleId, View));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsSessionUltimateContractTest, "Hczs.LocalSession.Contract.UltimateV3Projection", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsSessionUltimateContractTest::RunTest(const FString& Parameters)
{
    const auto Generated = UltimateReceipt(TEXT("generated"));
    if (!TestTrue(TEXT("Production reducer fixture is available"), Generated.IsValid())) return false;
    FHczsBattleView View;
    TestTrue(TEXT("V3 initial state parses without generated cards"), ParseBattle(Child(UltimateReceipt(), TEXT("battle")), ProfileId, BattleId, View));
    TestTrue(TEXT("Server-generated ultimate enters the interactive hand"), ParseBattle(Child(Generated, TEXT("battle")), ProfileId, BattleId, View));
    const auto* Ultimate = View.Hand.FindByPredicate([](const FHczsHandCard& Card) { return Card.CardId == TEXT("410104"); });
    if (TestNotNull(TEXT("Ultimate hand card was projected"), Ultimate))
    {
        TestEqual(TEXT("Generated instance identity retained"), Ultimate->InstanceId, FString(TEXT("ultimate:1")));
        TestEqual(TEXT("Ultimate remains zero-cost"), Ultimate->Cost, 0);
    }
    TestEqual(TEXT("City enemy remains its real identity, never tutorial cube 991"), View.EnemyId, FString(TEXT("6605")));
    TestEqual(TEXT("Explicit city encounter is retained"), View.EncounterId, FString(TEXT("city-preview-10405")));
    TestTrue(TEXT("Zero-energy use and removed zone parse"), ParseBattle(Child(UltimateReceipt(TEXT("used")), TEXT("battle")), ProfileId, BattleId, View));
    TestEqual(TEXT("No extra energy is invented"), View.Energy, 0);
    TestFalse(TEXT("Removed card is not interactive"), View.Hand.ContainsByPredicate([](const FHczsHandCard& Card) { return Card.InstanceId == TEXT("ultimate:1"); }));
    TestTrue(TEXT("Round reset with historical generated registry parses"), ParseBattle(Child(UltimateReceipt(TEXT("next-round")), TEXT("battle")), ProfileId, BattleId, View));

    // These are structural counter/registry bounds, not a claim to authenticate a play history.
    auto LongBattle = Child(UltimateReceipt(), TEXT("battle")); auto State = Child(LongBattle, TEXT("state"));
    State->SetNumberField(TEXT("round"), 24); State->SetNumberField(TEXT("actionIndex"), 230); LongBattle->SetNumberField(TEXT("revision"), 231);
    Child(State, TEXT("ultimate"))->SetNumberField(TEXT("generatedTotal"), 69);
    auto Cards = State->GetArrayField(TEXT("cards")); TArray<TSharedPtr<FJsonValue>> Removed;
    for (int32 I = 1; I <= 69; ++I)
    {
        const FString Id = FString::Printf(TEXT("ultimate:%d"), I); auto Card = MakeShared<FJsonObject>();
        Card->SetStringField(TEXT("instanceId"), Id); Card->SetStringField(TEXT("cardId"), TEXT("410104"));
        Cards.Add(MakeShared<FJsonValueObject>(Card)); Removed.Add(MakeShared<FJsonValueString>(Id));
    }
    State->SetArrayField(TEXT("cards"), Cards); Child(State, TEXT("piles"))->SetArrayField(TEXT("removed"), Removed);
    TestTrue(TEXT("Removed registry can exceed 64, still bounded by rounds times three"), ParseBattle(LongBattle, ProfileId, BattleId, View));

    const auto Reject = [this, &View](const TCHAR* Label, TFunctionRef<void(const TSharedPtr<FJsonObject>&)> Mutate)
    {
        const auto Bad = Child(UltimateReceipt(TEXT("generated")), TEXT("battle")); Mutate(Bad);
        TestFalse(Label, ParseBattle(Bad, ProfileId, BattleId, View));
    };
    Reject(TEXT("V3 cannot masquerade as v2"), [](const auto& B) { Child(B,TEXT("state"))->SetStringField(TEXT("format"),TEXT("hczs-battle-session-v2")); });
    Reject(TEXT("V3 requires its combo state"), [](const auto& B) { Child(B,TEXT("state"))->RemoveField(TEXT("ultimate")); });
    Reject(TEXT("Unsupported policy rejected"), [](const auto& B) { Child(Child(Child(B,TEXT("scenario")),TEXT("definition")),TEXT("ultimateRules"))->SetStringField(TEXT("policy"),TEXT("invented")); });
    Reject(TEXT("Wrong card owner rejected"), [](const auto& B) { Child(Child(Child(Child(B,TEXT("scenario")),TEXT("definition")),TEXT("cards")),TEXT("410104"))->SetStringField(TEXT("ownerId"),TEXT("2")); });
    Reject(TEXT("Nonzero ultimate cost rejected"), [](const auto& B) { Child(Child(Child(Child(B,TEXT("scenario")),TEXT("definition")),TEXT("cards")),TEXT("410104"))->SetNumberField(TEXT("cost"),1); });
    Reject(TEXT("Ultimate cannot contribute a point"), [](const auto& B) { Child(Child(Child(Child(B,TEXT("scenario")),TEXT("definition")),TEXT("cards")),TEXT("410104"))->SetNumberField(TEXT("specialPoints"),1); });
    Reject(TEXT("Ultimate removal metadata cannot be disabled"), [](const auto& B) { Child(Child(Child(Child(B,TEXT("scenario")),TEXT("definition")),TEXT("cards")),TEXT("410104"))->SetBoolField(TEXT("removeOnLeaveHand"),false); });
    Reject(TEXT("Generated card must match ultimate definition"), [](const auto& B) { Child(B,TEXT("state"))->GetArrayField(TEXT("cards")).Last()->AsObject()->SetStringField(TEXT("cardId"),TEXT("110001")); });
    Reject(TEXT("Generated sequence must be contiguous"), [](const auto& B) { Child(B,TEXT("state"))->GetArrayField(TEXT("cards")).Last()->AsObject()->SetStringField(TEXT("instanceId"),TEXT("ultimate:2")); });
    Reject(TEXT("Counters must match the registry"), [](const auto& B) { Child(Child(B,TEXT("state")),TEXT("ultimate"))->SetNumberField(TEXT("generatedTotal"),2); });
    Reject(TEXT("Round generation cap enforced"), [](const auto& B) { Child(Child(B,TEXT("state")),TEXT("ultimate"))->SetNumberField(TEXT("generatedThisRound"),4); });
    Reject(TEXT("Combo owner must match nonzero points"), [](const auto& B) { auto U=Child(Child(B,TEXT("state")),TEXT("ultimate")); U->SetNumberField(TEXT("points"),1); U->SetStringField(TEXT("chainOwnerId"),TEXT("2")); });
    Reject(TEXT("Dynamic card cannot be duplicated across piles"), [](const auto& B) { Child(Child(B,TEXT("state")),TEXT("piles"))->SetArrayField(TEXT("removed"),{MakeShared<FJsonValueString>(TEXT("ultimate:1"))}); });
    Reject(TEXT("Dynamic card cannot enter discard/recycle"), [](const auto& B) {
        auto P=Child(Child(B,TEXT("state")),TEXT("piles")); auto Hand=P->GetArrayField(TEXT("hand"));
        Hand.RemoveAll([](const auto& Value) { return Value->AsString()==TEXT("ultimate:1"); }); P->SetArrayField(TEXT("hand"),Hand);
        auto Discard=P->GetArrayField(TEXT("discard")); Discard.Add(MakeShared<FJsonValueString>(TEXT("ultimate:1"))); P->SetArrayField(TEXT("discard"),Discard);
    });
    auto Old = Fixture(); Child(Child(Old,TEXT("scenario")),TEXT("definition"))->RemoveField(TEXT("statusRules"));
    Child(Old,TEXT("state"))->RemoveField(TEXT("breakdown")); Child(Old,TEXT("state"))->SetStringField(TEXT("format"),TEXT("hczs-battle-session-v1"));
    TestTrue(TEXT("Legacy v1 still parses"),ParseBattle(Old,ProfileId,BattleId,View));
    Child(Old,TEXT("state"))->SetObjectField(TEXT("ultimate"),MakeShared<FJsonObject>());
    TestFalse(TEXT("Legacy v1 rejects injected ultimate state"),ParseBattle(Old,ProfileId,BattleId,View));
    Old=Fixture(); Child(Child(Old,TEXT("state")),TEXT("piles"))->SetArrayField(TEXT("removed"),{MakeShared<FJsonValueString>(TEXT("card-1"))});
    TestFalse(TEXT("Legacy v2 still rejects removed cards"),ParseBattle(Old,ProfileId,BattleId,View));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsSessionUltimateReceiptTest, "Hczs.LocalSession.Contract.UltimateV3Receipts", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsSessionUltimateReceiptTest::RunTest(const FString& Parameters)
{
    auto Result=UltimateReceipt(TEXT("used")); if(!TestTrue(TEXT("Ultimate receipt fixture available"),Result.IsValid())) return false;
    FHczsBattleView View; FHczsBattleVisualReceipt Visual; TArray<FString> Events;
    TestTrue(TEXT("Dynamic instance can confirm the exact pending play"),ParseReceipt(Result,ProfileId,BattleId,TEXT(""),5,View,Events,TEXT("play-card"),TEXT("ultimate:1"),&Visual));
    if(TestEqual(TEXT("CardPlayed plus eight real damage visual events"),Visual.Events.FilterByPredicate([](const FHczsBattleVisualEvent& E)
        { return E.Type==TEXT("CardPlayed")||E.Type==TEXT("DamageApplied"); }).Num(),9))
        TestEqual(TEXT("Original skill card identity reaches presentation"),Visual.Events[0].CardId,FString(TEXT("410104")));
    TestEqual(TEXT("Receipt never rewrites enemy identity"),View.EnemyId,FString(TEXT("6605")));
    Result->SetBoolField(TEXT("replayed"),true);
    TestTrue(TEXT("Valid persisted ultimate receipt can confirm a retry"),ParseReceipt(Result,ProfileId,BattleId,TEXT(""),5,View,Events,TEXT("play-card"),TEXT("ultimate:1"),&Visual));
    Result->GetArrayField(TEXT("events"))[0]->AsObject()->SetStringField(TEXT("instanceId"),TEXT("ultimate:2"));
    TestFalse(TEXT("Unknown generated instance cannot confirm or animate"),ParseReceipt(Result,ProfileId,BattleId,TEXT(""),5,View,Events,TEXT("play-card"),TEXT("ultimate:2"),&Visual));
    TestFalse(TEXT("Rejected dynamic receipt clears visual bundle"),Visual.bValid);
    Result=UltimateReceipt(TEXT("used"));
    Result->GetArrayField(TEXT("events"))[0]->AsObject()->SetStringField(TEXT("cardId"),TEXT("110001"));
    TestFalse(TEXT("Registered ultimate instance cannot impersonate normal card"),ParseReceipt(Result,ProfileId,BattleId,TEXT(""),5,View,Events,TEXT("play-card"),TEXT("ultimate:1")));
    Result=UltimateReceipt(TEXT("used"));
    for(const auto& E:Result->GetArrayField(TEXT("events"))) if(E->AsObject()->GetStringField(TEXT("type"))==TEXT("CardMoved")) E->AsObject()->SetStringField(TEXT("to"),TEXT("discard"));
    TestFalse(TEXT("Ultimate receipt cannot claim recycling into discard"),ParseReceipt(Result,ProfileId,BattleId,TEXT(""),5,View,Events,TEXT("play-card"),TEXT("ultimate:1")));
    Result=UltimateReceipt(TEXT("generated"));
    TestTrue(TEXT("Real generated CardDrawn event accepted"),ParseReceipt(Result,ProfileId,BattleId,TEXT(""),3,View,Events,TEXT("play-card"),TEXT("tutorial-card-3")));
    for(const auto& E:Result->GetArrayField(TEXT("events"))) if(E->AsObject()->GetStringField(TEXT("type"))==TEXT("CardDrawn")) E->AsObject()->SetBoolField(TEXT("generated"),false);
    TestFalse(TEXT("Malformed generated flag rejected"),ParseReceipt(Result,ProfileId,BattleId,TEXT(""),3,View,Events,TEXT("play-card"),TEXT("tutorial-card-3")));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsSessionReceiptContractTest, "Hczs.LocalSession.Contract.ReceiptsAndLateResponses", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsSessionReceiptContractTest::RunTest(const FString& Parameters)
{
    FHczsBattleView View; TArray<FString> Events; auto Result = Receipt(Fixture());
    TestTrue(TEXT("Creation receipt matches explicit encounter"), ParseReceipt(Result, ProfileId, TEXT(""), TEXT("test-encounter"), 0, View, Events));
    TestFalse(TEXT("Creation receipt for another encounter rejected"), ParseReceipt(Result, ProfileId, TEXT(""), TEXT("other-encounter"), 0, View, Events));
    TestFalse(TEXT("CAS receipt must equal expectedRevision+1"), ParseReceipt(Result, ProfileId, BattleId, TEXT(""), 5, View, Events));
    auto Battle = Fixture(); Battle->SetNumberField(TEXT("revision"), 2); Child(Battle, TEXT("state"))->SetNumberField(TEXT("actionIndex"), 1);
    Result = Receipt(Battle, true);
    TestTrue(TEXT("Action receipt binds the exact played instance"), ParseReceipt(Result, ProfileId, BattleId, TEXT(""), 1, View, Events, TEXT("play-card"), TEXT("card-1")));
    TestFalse(TEXT("Wrong played instance cannot confirm pending intent"), ParseReceipt(Result, ProfileId, BattleId, TEXT(""), 1, View, Events, TEXT("play-card"), TEXT("other-card")));
    TestFalse(TEXT("End-turn must not be reported as play-card"), ParseReceipt(Result, ProfileId, BattleId, TEXT(""), 1, View, Events, TEXT("end-turn")));
    Result->SetBoolField(TEXT("replayed"), true);
    TestTrue(TEXT("Valid historical receipt may confirm the original intent"), ParseReceipt(Result, ProfileId, BattleId, TEXT(""), 1, View, Events, TEXT("play-card"), TEXT("card-1")));
    FHczsBattleView Newer = View; Newer.Revision = 5;
    TestFalse(TEXT("Historical receipt/read never rolls a newer viewport back"), CanApplyBattleRevision(Newer, View, 2));
    TestFalse(TEXT("A read must reach the confirmed receipt revision"), CanApplyBattleRevision(FHczsBattleView(), View, 3));
    auto ChangedDefinition = Newer; ChangedDefinition.DefinitionId = TEXT("different-definition");
    TestFalse(TEXT("An existing battle cannot change its frozen definition"), CanApplyBattleRevision(Newer, ChangedDefinition, 5));
    TestTrue(TEXT("Same epoch and active request may complete"), CanAcceptReply(7, 7, false, true));
    TestFalse(TEXT("Late response after profile/session change ignored"), CanAcceptReply(8, 7, false, true));
    TestFalse(TEXT("Late response after shutdown ignored"), CanAcceptReply(7, 7, true, true));
    TestFalse(TEXT("Response from superseded request ignored"), CanAcceptReply(7, 7, false, false));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsSessionIdentityContractTest, "Hczs.LocalSession.Contract.ServiceIdentity", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsSessionIdentityContractTest::RunTest(const FString& Parameters)
{
    TestTrue(TEXT("Canonical lowercase UUID accepted"), IsUuid(ProfileId));
    TestFalse(TEXT("Arbitrary 36-character route IDs rejected"), IsUuid(TEXT("------------------unknown-----------")));
    TestFalse(TEXT("Path fragments rejected"), IsId(TEXT("../profiles")));
    const FString Json = TEXT(R"JSON({"service":"hczs-rebuild","apiVersion":1,"saveSchemaVersion":1,"storage":"mongodb","gameplayReady":false,
      "profiles":[],"capabilities":["local-profiles","encounter-selection"],"operational":{"settings":{"allowNewProfiles":true,"allowNewBattles":false}},
      "endpoints":{"profiles":"/api/rebuild/v1/profiles","encounters":"/api/rebuild/v1/encounters","battles":"/api/rebuild/v1/profiles/{profileId}/battles"}})JSON");
    auto Object = Read(Json); TArray<FHczsLocalProfile> Profiles; bool A = false, B = true;
    TestTrue(TEXT("Known versioned reconstruction service accepted"), ParseBootstrap(Object, Profiles, A, B));
    TestTrue(TEXT("Policy permits profile creation"), A); TestFalse(TEXT("Policy disables new battle creation"), B);
    Object->SetStringField(TEXT("service"), TEXT("another-service"));
    TestFalse(TEXT("Unknown service rejected"), ParseBootstrap(Object, Profiles, A, B));
    Object = Read(Json); Object->SetNumberField(TEXT("apiVersion"), 2);
    TestFalse(TEXT("Unsupported API version rejected"), ParseBootstrap(Object, Profiles, A, B));
    Object = Read(Json); Child(Object, TEXT("endpoints"))->SetStringField(TEXT("profiles"), TEXT("https://elsewhere/profiles"));
    TestFalse(TEXT("Unexpected externally redirected route rejected"), ParseBootstrap(Object, Profiles, A, B));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsSessionVisualContractTest, "Hczs.LocalSession.Contract.VisualReceiptAndSceneReadiness", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsSessionVisualContractTest::RunTest(const FString& Parameters)
{
    auto Battle = Fixture(); Battle->SetNumberField(TEXT("revision"), 2); Child(Battle, TEXT("state"))->SetNumberField(TEXT("actionIndex"), 1);
    auto Result = Receipt(Battle, true); FHczsBattleView View; FHczsBattleVisualReceipt Visual; TArray<FString> Lines;
    TestTrue(TEXT("Visual receipt comes from validated raw card event"), ParseReceipt(Result, ProfileId, BattleId, TEXT(""), 1, View, Lines, TEXT("play-card"), TEXT("card-1"), &Visual));
    TestEqual(TEXT("ActionIndex read from state.actionIndex"), View.ActionIndex, int64(1));
    TestEqual(TEXT("Card id is raw cardId, not translated UI text"), Visual.Events[0].CardId, FString(TEXT("110001")));
    TestEqual(TEXT("CardPlayed has no invented raw target"), Visual.Events[0].Target, FString());
    TestTrue(TEXT("Same latest state can publish this receipt"), CanPublishVisualReceipt(View, Visual));
    auto Latest = View; ++Latest.ActionIndex; ++Latest.Revision;
    TestFalse(TEXT("Historical receipt is not replayed over advanced GET state"), CanPublishVisualReceipt(Latest, Visual));
    auto DifferentBattle = View; DifferentBattle.Id = TEXT("33333333-3333-3333-3333-333333333333");
    TestFalse(TEXT("Another battle cannot borrow visual events"), CanPublishVisualReceipt(DifferentBattle, Visual));
    TestFalse(TEXT("Fresh continue only presents a baseline"), CanPublishVisualReceipt(View, FHczsBattleVisualReceipt()));
    TestFalse(TEXT("Invalid state never grants visual presentation"), CanPublishVisualReceipt(FHczsBattleView(), Visual));

    auto First = Result->GetArrayField(TEXT("events"))[0]->AsObject(); First->SetStringField(TEXT("cardId"), TEXT("unknown-card"));
    TestFalse(TEXT("Unregistered card visual is rejected"), ParseReceipt(Result, ProfileId, BattleId, TEXT(""), 1, View, Lines, TEXT("play-card"), TEXT("card-1"), &Visual));
    TestFalse(TEXT("Rejected receipt also clears the prior visual bundle"), Visual.bValid);
    Result = Receipt(Battle, true); Result->GetArrayField(TEXT("events"))[0]->AsObject()->SetNumberField(TEXT("cost"), 2);
    TestFalse(TEXT("Card event cost must match the frozen definition"), ParseReceipt(Result, ProfileId, BattleId, TEXT(""), 1, View, Lines, TEXT("play-card"), TEXT("card-1"), &Visual));
    Result = Receipt(Battle, true);
    auto Skill = Result->GetArrayField(TEXT("events"))[0]->AsObject();
    Skill->RemoveField(TEXT("instanceId")); Skill->RemoveField(TEXT("cardId")); Skill->RemoveField(TEXT("cost"));
    Skill->SetStringField(TEXT("type"), TEXT("EnemySkillUsed")); Skill->SetStringField(TEXT("skillId"), TEXT("9911")); Skill->SetNumberField(TEXT("round"), 1);
    TestTrue(TEXT("Frozen enemy skill id maps a real raw enemy event"), ParseReceipt(Result, ProfileId, BattleId, TEXT(""), 1, View, Lines, TEXT("end-turn"), TEXT(""), &Visual));
    TestEqual(TEXT("Enemy visual keeps skillId"), Visual.Events[0].SkillId, FString(TEXT("9911")));
    {
        auto TurnEvents = Result->GetArrayField(TEXT("events"));
        const int32 StateIndex = TurnEvents.Num() - 1;
        TurnEvents.Insert(MakeShared<FJsonValueObject>(Read(TEXT(R"JSON({"type":"TurnStarted","round":2})JSON"))), StateIndex);
        TurnEvents.Insert(MakeShared<FJsonValueObject>(Read(TEXT(R"JSON({"type":"CardDrawn","instanceId":"card-1"})JSON"))), StateIndex + 1);
        Result->SetArrayField(TEXT("events"), TurnEvents);
        TestTrue(TEXT("End-turn receipt with round-start draw accepted"), ParseReceipt(Result, ProfileId, BattleId, TEXT(""), 1, View, Lines, TEXT("end-turn"), TEXT(""), &Visual));
        if (TestEqual(TEXT("Enemy, turn and draw visuals kept in order"), Visual.Events.Num(), 3))
        {
            TestEqual(TEXT("Turn visual keeps round"), Visual.Events[1].Round, 2);
            TestEqual(TEXT("Draw visual keeps registered instance"), Visual.Events[2].InstanceId, FString(TEXT("card-1")));
        }
        TurnEvents.RemoveAt(StateIndex, 2); Result->SetArrayField(TEXT("events"), TurnEvents);
    }
    Skill->SetStringField(TEXT("skillId"), TEXT("unregistered-skill"));
    TestFalse(TEXT("Unregistered skill cannot trigger a visual"), ParseReceipt(Result, ProfileId, BattleId, TEXT(""), 1, View, Lines, TEXT("end-turn"), TEXT(""), &Visual));

    Result = Receipt(Battle, true);
    auto Events = Result->GetArrayField(TEXT("events"));
    auto Damage = Read(TEXT(R"JSON({"type":"DamageApplied","actor":"player","target":"enemy","effectIndex":0,"amount":"5",
      "absorbed":{"numeric_type":"integer","decimal":"0"},"hpLost":{"numeric_type":"integer","decimal":"5"},
      "previousHp":{"numeric_type":"integer","decimal":"100"},"finalHp":{"numeric_type":"integer","decimal":"95"},
      "previousShield":{"numeric_type":"integer","decimal":"0"},"finalShield":{"numeric_type":"integer","decimal":"0"}})JSON"));
    Events.Insert(MakeShared<FJsonValueObject>(Damage), 1); Result->SetArrayField(TEXT("events"), Events);
    TestTrue(TEXT("Actual damage event shape supplies target presentation"), ParseReceipt(Result, ProfileId, BattleId, TEXT(""), 1, View, Lines, TEXT("play-card"), TEXT("card-1"), &Visual));
    TestEqual(TEXT("Damage target is a raw side id"), Visual.Events[1].Target, FString(TEXT("enemy")));
    Damage->SetStringField(TEXT("target"), TEXT("ally"));
    TestFalse(TEXT("Unknown damage target is rejected"), ParseReceipt(Result, ProfileId, BattleId, TEXT(""), 1, View, Lines, TEXT("play-card"), TEXT("card-1"), &Visual));
    Damage->SetStringField(TEXT("target"), TEXT("enemy")); Damage->RemoveField(TEXT("hpLost"));
    TestFalse(TEXT("Incomplete damage event is rejected"), ParseReceipt(Result, ProfileId, BattleId, TEXT(""), 1, View, Lines, TEXT("play-card"), TEXT("card-1"), &Visual));

    FHczsHallPreference Hall; Hall.bIsValid = true;
    TestTrue(TEXT("Verified idle Hall can travel"), IsSessionSceneReady(EHczsSessionPhase::Hall, EHczsSessionPhase::Hall, ProfileId, true, Hall, View, true, false, false));
    TestTrue(TEXT("Verified current Battle can travel"), IsSessionSceneReady(EHczsSessionPhase::Battle, EHczsSessionPhase::Battle, ProfileId, true, Hall, View, true, false, false));
    TestFalse(TEXT("Cached battle does not send ReturnToHall back to Battle"), IsSessionSceneReady(EHczsSessionPhase::Battle, EHczsSessionPhase::Hall, ProfileId, true, Hall, View, true, false, false));
    TestFalse(TEXT("Pending confirmed or uncertain intent blocks travel"), IsSessionSceneReady(EHczsSessionPhase::Battle, EHczsSessionPhase::Battle, ProfileId, true, Hall, View, true, false, true));
    TestFalse(TEXT("Read/write flight blocks travel during callback chains"), IsSessionSceneReady(EHczsSessionPhase::Hall, EHczsSessionPhase::Hall, ProfileId, true, Hall, View, true, true, false));
    TestFalse(TEXT("Unverified selected UUID cannot enter a player scene"), IsSessionSceneReady(EHczsSessionPhase::Hall, EHczsSessionPhase::Hall, ProfileId, false, Hall, View, true, false, false));
    TestFalse(TEXT("Profile GET success is not yet Hall read success"), IsSessionSceneReady(EHczsSessionPhase::Hall, EHczsSessionPhase::Hall, ProfileId, true, FHczsHallPreference(), View, true, false, false));
    TestFalse(TEXT("Unsynchronized battle does not travel"), IsSessionSceneReady(EHczsSessionPhase::Battle, EHczsSessionPhase::Battle, ProfileId, true, Hall, View, false, false, false));
    TestFalse(TEXT("Other profile's battle cannot enter the scene"), IsSessionSceneReady(EHczsSessionPhase::Battle, EHczsSessionPhase::Battle,
        TEXT("33333333-3333-3333-3333-333333333333"), true, Hall, View, true, false, false));
    auto Directory = Read(TEXT(R"JSON({"schemaVersion":1,"defaultEncounterId":"test-encounter","selectionPolicy":"explicit-local-selection",
      "originalUnlockBehaviorVerified":false,"rewardsImplemented":false,"encounters":[{"id":"test-encounter","title":"样本关卡","notice":"",
      "definitionId":"test-definition","player":{"id":"1","name":"艾尔莎"},"enemy":{"id":"6605","name":"比克卢"}}]})JSON"));
    TArray<FHczsEncounterSummary> Encounters;
    TestTrue(TEXT("Encounter combatant IDs are retained from the server"), ParseEncounters(Directory, Encounters));
    TestEqual(TEXT("Player ID is raw directory id"), Encounters[0].PlayerId, FString(TEXT("1")));
    TestEqual(TEXT("City enemy does not become the restored tutorial enemy"), Encounters[0].EnemyId, FString(TEXT("6605")));
    return true;
}
#endif
