#include "HczsGameInstance.h"
#include "HczsSessionContract.h"
#include "HttpModule.h"
#include "Interfaces/IHttpResponse.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Guid.h"

using namespace HczsSessionContract;
namespace
{
    FString RequestId() { return FString::Printf(TEXT("ue-%s"), *FGuid::NewGuid().ToString(EGuidFormats::DigitsWithHyphensLower)); }
    FString Json(const TSharedRef<FJsonObject>& O) { return Serialize(O); }
    constexpr int32 MaxResponseBytes = 8 * 1024 * 1024;
}

void UHczsGameInstance::Init()
{
    Super::Init();
    // An explicit runtime port override allows isolated HTTP/Mongo acceptance runs.
    int32 Override = 0;
    if (FParse::Value(FCommandLine::Get(), TEXT("HczsServerPort="), Override)) LocalServerPort = Override;
    RefreshBootstrap();
}
void UHczsGameInstance::Shutdown()
{
    bShuttingDown = true; ++SessionEpoch;
    ClearPendingIntent();
    if (PendingRequest.IsValid())
    {
        PendingRequest->OnProcessRequestComplete().Unbind(); PendingRequest->CancelRequest(); PendingRequest.Reset();
    }
    bRequestInFlight = false;
    OnStateChanged.Clear(); OnStateChangedNative.Clear();
    OnCardIntentDispatchedNative.Clear(); OnCardIntentSettledNative.Clear();
    if (!bIsIsolatedAutomationSession) Super::Shutdown();
}
#if WITH_DEV_AUTOMATION_TESTS
bool UHczsGameInstance::StartIsolatedTestSession(int32 Port)
{
    if (!FParse::Param(FCommandLine::Get(), TEXT("HczsSessionIntegration")) || Port < 1 || Port > 65535 || Port == 7460 ||
        bRequestInFlight || bLocalServiceAvailable || bShuttingDown) return false;
    bIsIsolatedAutomationSession = true; LocalServerPort = Port; RefreshBootstrap(); return true;
}
#endif
void UHczsGameInstance::Notify()
{
    if (bShuttingDown) return;
    LocalStatus = UserMessage;
    OnStateChanged.Broadcast(); OnStateChangedNative.Broadcast();
}
void UHczsGameInstance::Fail(const FString& Code, const FString& Message)
{
    ErrorCode = Code; UserMessage = Message;
    UE_LOG(LogTemp, Warning, TEXT("HCZS session: phase=%d code=%s revision=%lld"), static_cast<int32>(Phase), *Code, CurrentBattle.Revision);
    Notify();
}
FString UHczsGameInstance::FriendlyError(int32 HttpCode, const FString& Code) const
{
    if (Code == TEXT("TRANSPORT_FAILURE") || HttpCode == 0) return TEXT("无法连接本地服务。请检查服务，然后重试。");
    if (Code == TEXT("REVISION_CONFLICT") || Code == TEXT("COMMAND_CONFLICT") || Code == TEXT("REQUEST_ID_CONFLICT")) return TEXT("存档版本已变化，正在读取最新状态；请根据新状态重新操作。");
    if (Code == TEXT("BATTLE_CREATION_DISABLED")) return TEXT("后台已暂停新战斗，已有战斗仍可继续。");
    if (Code == TEXT("PROFILE_CREATION_DISABLED")) return TEXT("后台已暂停创建本地档案。");
    if (Code == TEXT("PROFILE_NOT_FOUND")) return TEXT("该本地档案已不存在，请刷新后重新选择。");
    if (Code == TEXT("BATTLE_NOT_FOUND")) return TEXT("此档案中找不到这场战斗，请刷新战斗列表。");
    if (Code == TEXT("ENCOUNTER_UNAVAILABLE")) return TEXT("此关卡当前未开放，请刷新关卡目录。");
    if (Code == TEXT("INVALID_BATTLE_ACTION")) return TEXT("服务端拒绝本次行动，请刷新战斗状态后再操作。");
    if (Code == TEXT("CHALLENGE_ALREADY_COMPLETED")) return TEXT("序章首战已经记录通关，正在读取最新进度。");
    if (Code == TEXT("BATTLE_NOT_MAINLINE")) return TEXT("这场战斗不属于已接入的主线挑战。");
    if (Code == TEXT("BATTLE_NOT_WON")) return TEXT("这场战斗尚未取得服务端确认的胜利。");
    if (Code == TEXT("CHALLENGE_LOCKED")) return TEXT("前置挑战尚未通关，请读取最新进度。");
    if (Code == TEXT("CONTENT_CHANGED")) return TEXT("主线目录已经更新，请刷新连接后重新读取进度。");
    if (Code == TEXT("MAINLINE_CONTENT_CHANGED")) return TEXT("主线存档与当前内容版本不兼容，原进度已保留。请检查服务端内容版本。");
    if (Code == TEXT("UNEXPECTED_RESPONSE") || Code == TEXT("INVALID_JSON") || Code == TEXT("RESPONSE_TOO_LARGE")) return TEXT("本地服务响应不符合游戏契约，未采用这份数据。");
    if (HttpCode >= 500) return TEXT("本地服务暂时出错，操作结果尚未确认；请使用重试读取或重试原操作。");
    return TEXT("本次操作未完成，请刷新数据后再试。");
}
void UHczsGameInstance::Fetch(const FString& RequestPhase, const FString& Verb, const FString& Route, const FString& Body, FReply Completion)
{
    if (bShuttingDown || PendingRequest.IsValid()) return;
    if (LocalServerPort < 1 || LocalServerPort > 65535)
    {
        Completion(nullptr, 0, TEXT("INVALID_PORT")); return;
    }
    const uint64 Epoch = SessionEpoch;
    auto Request = FHttpModule::Get().CreateRequest();
    Request->SetURL(FString::Printf(TEXT("http://127.0.0.1:%d/api/rebuild/v1%s"), LocalServerPort, *Route));
    Request->SetVerb(Verb); Request->SetDelegateThreadPolicy(EHttpRequestDelegateThreadPolicy::CompleteOnGameThread);
    Request->SetHeader(TEXT("Accept"), TEXT("application/json")); Request->SetTimeout(8.0f);
    if (!Body.IsEmpty()) { Request->SetHeader(TEXT("Content-Type"), TEXT("application/json; charset=utf-8")); Request->SetContentAsString(Body); }
    PendingRequest = Request; bRequestInFlight = true;
    const TWeakObjectPtr<UHczsGameInstance> WeakThis(this);
    // Shared callback permits synchronous ProcessRequest failure without invoking a moved-from closure.
    const auto Reply = MakeShared<FReply>(MoveTemp(Completion));
    Request->OnProcessRequestComplete().BindLambda([WeakThis, Epoch, RequestPhase, Reply](FHttpRequestPtr Completed, FHttpResponsePtr Response, bool bSucceeded)
    {
        auto* Self = WeakThis.Get();
        if (!Self || !CanAcceptReply(Self->SessionEpoch, Epoch, Self->bShuttingDown, Completed == Self->PendingRequest)) return;
        Self->PendingRequest.Reset(); Self->bRequestInFlight = false;
        TSharedPtr<FJsonObject> Parsed; int32 Code = 0; FString Failure;
        if (!bSucceeded || !Response.IsValid()) Failure = TEXT("TRANSPORT_FAILURE");
        else
        {
            Code = Response->GetResponseCode();
            if (Response->GetContent().Num() > MaxResponseBytes) Failure = TEXT("RESPONSE_TOO_LARGE");
            else
            {
                const auto Reader = TJsonReaderFactory<>::Create(Response->GetContentAsString());
                if (!FJsonSerializer::Deserialize(Reader, Parsed) || !Parsed.IsValid()) Failure = TEXT("INVALID_JSON");
                else if (Code < 200 || Code >= 300) Failure = ServerErrorCode(Parsed);
            }
        }
        UE_LOG(LogTemp, Display, TEXT("HCZS HTTP: phase=%s http=%d revision=%lld"), *RequestPhase, Code, Self->CurrentBattle.Revision);
        (*Reply)(Parsed, Code, Failure);
    });
    Notify();
    if (!Request->ProcessRequest())
    {
        Request->OnProcessRequestComplete().Unbind(); PendingRequest.Reset(); bRequestInFlight = false;
        (*Reply)(nullptr, 0, TEXT("TRANSPORT_FAILURE"));
    }
    else if (RequestPhase == TEXT("action") && Verb == TEXT("POST") && bHasPendingIntent &&
        !PendingCardVisual.RequestId.IsEmpty() && !PendingCardVisual.bDispatched)
    {
        // ProcessRequest accepted this intent. Retries preserve the same cue/id.
        PendingCardVisual.bDispatched = true;
        const FDateTime Now = FDateTime::UtcNow();
        UE_LOG(LogTemp, Display, TEXT("HCZS card intent dispatched: request=%s revision=%lld atUnixMs=%lld"),
            *PendingCardVisual.RequestId, PendingCardVisual.ExpectedRevision, Now.ToUnixTimestamp() * 1000 + Now.GetMillisecond());
        OnCardIntentDispatchedNative.Broadcast(PendingCardVisual);
    }
}
bool UHczsGameInstance::CanStartRead()
{
    if (bShuttingDown || bRequestInFlight) return false;
    if (bHasPendingIntent) { Fail(TEXT("INTENT_PENDING"), TEXT("上一操作结果尚未确认，请先重试原操作。")); return false; }
    return true;
}
void UHczsGameInstance::RefreshLocalStatus() { RefreshBootstrap(); }
void UHczsGameInstance::RefreshProfilesAfterUncertainCreation() { RefreshBootstrap(); }
void UHczsGameInstance::RefreshBootstrap()
{
    if (!CanStartRead()) return;
    UserMessage = TEXT("正在连接本地重建服务…"); ErrorCode.Reset();
    if (SelectedProfileId.IsEmpty()) Phase = EHczsSessionPhase::Connecting;
    Fetch(TEXT("bootstrap"), TEXT("GET"), TEXT("/bootstrap"), TEXT(""), [this](TSharedPtr<FJsonObject> O, int32 Code, const FString& Error)
    {
        TArray<FHczsLocalProfile> Next; bool AllowProfiles = false, AllowBattles = false, HasMainline = false; FString ContentId;
        if (!Error.IsEmpty() || Code != 200 || !ParseBootstrap(O, Next, AllowProfiles, AllowBattles) || !ParseMainlineCapability(O, HasMainline, ContentId))
        {
            bLocalServiceAvailable = false; bAllowNewProfiles = false; bAllowNewBattles = false; bMainlineStateCurrent = false;
            if (SelectedProfileId.IsEmpty()) Phase = EHczsSessionPhase::Unavailable;
            const FString Reason = Error.IsEmpty() ? TEXT("UNEXPECTED_RESPONSE") : Error;
            Fail(Reason, FriendlyError(Code, Reason)); return;
        }
        bLocalServiceAvailable = true; bOriginalGameplayReady = false;
        if (HasMainline != bHasMainlineProgression || ContentId != MainlineContentId) bMainlineStateCurrent = false;
        bHasMainlineProgression = HasMainline; MainlineContentId = ContentId;
        bAllowNewProfiles = AllowProfiles; bAllowNewBattles = AllowBattles; Profiles = MoveTemp(Next); ErrorCode.Reset();
        UE_LOG(LogTemp, Display, TEXT("HCZS bootstrap verified; profiles=%d; selected=%s; no original login"), Profiles.Num(), SelectedProfileId.IsEmpty() ? TEXT("none") : TEXT("explicit"));
        if (!SelectedProfileId.IsEmpty())
        {
            if (!Profiles.ContainsByPredicate([this](const FHczsLocalProfile& P) { return P.Id == SelectedProfileId; }))
            {
                ++SessionEpoch; SelectedProfileId.Reset(); SelectedEncounterId.Reset(); CurrentBattle = FHczsBattleView();
                HallPreference = FHczsHallPreference(); bBattleStateCurrent = false; bEncounterScenarioReady = false;
                bProfileStateCurrent = false; LastVisualReceipt = FHczsBattleVisualReceipt(); LastEvents.Reset(); Battles.Reset();
                ResetMainlineProgress();
            }
        }
        if (SelectedProfileId.IsEmpty())
        {
            Phase = EHczsSessionPhase::ProfileSelection; UserMessage = TEXT("请选择本地档案，或创建一份新档案。"); Notify(); ReadEncounters();
        }
        else { UserMessage = TEXT("本地服务已连接。"); Notify(); ReadEncounters(); }
    });
}
FString UHczsGameInstance::ProfilesRoute() const { return FString::Printf(TEXT("/profiles/%s"), *SelectedProfileId); }
FString UHczsGameInstance::BattlesRoute() const { return ProfilesRoute() + TEXT("/battles"); }
void UHczsGameInstance::SelectProfile(const FString& ProfileId)
{
    if (!CanStartRead() || !bLocalServiceAvailable) return;
    if (!IsUuid(ProfileId) || !Profiles.ContainsByPredicate([&ProfileId](const FHczsLocalProfile& P) { return P.Id == ProfileId; }))
    { Fail(TEXT("INVALID_PROFILE"), TEXT("请选择列表中存在的本地档案。")); return; }
    ++SessionEpoch; SelectedProfileId = ProfileId; SelectedEncounterId.Reset(); SelectedDefinitionId.Reset();
    CurrentBattle = FHczsBattleView(); HallPreference = FHczsHallPreference(); LastEvents.Reset(); Battles.Reset();
    ResetMainlineProgress();
    LastVisualReceipt = FHczsBattleVisualReceipt(); bProfileStateCurrent = false;
    bBattleStateCurrent = false; bEncounterScenarioReady = false; MinimumBattleRevision = 0;
    Phase = EHczsSessionPhase::ProfileSelection;
    ReadSelectedProfile();
}
void UHczsGameInstance::ReadSelectedProfile()
{
    UserMessage = TEXT("正在读取所选档案…"); ErrorCode.Reset();
    const FString Expected = SelectedProfileId;
    Fetch(TEXT("profile"), TEXT("GET"), ProfilesRoute(), TEXT(""), [this, Expected](TSharedPtr<FJsonObject> O, int32 Code, const FString& Error)
    {
        FHczsLocalProfile Profile;
        if (!Error.IsEmpty() || Code != 200 || !ParseProfile(Child(O, TEXT("profile")), Profile) || Profile.Id != Expected)
        { const FString Reason = Error.IsEmpty() ? TEXT("UNEXPECTED_RESPONSE") : Error; Fail(Reason, FriendlyError(Code, Reason)); return; }
        const int32 Index = Profiles.IndexOfByPredicate([&Expected](const FHczsLocalProfile& P) { return P.Id == Expected; });
        if (Index != INDEX_NONE) Profiles[Index] = Profile;
        bProfileStateCurrent = true;
        UserMessage = FString::Printf(TEXT("已选择本地档案 · %s"), *Profile.DisplayName);
        ReadHall(true);
    });
}
void UHczsGameInstance::CreateLocalProfile(const FString& DisplayName)
{
    if (!CanStartRead() || !bLocalServiceAvailable || !bAllowNewProfiles) return;
    const FString Name = DisplayName.TrimStartAndEnd();
    bool bVisible = true; for (TCHAR Character : Name) if (Character < 32 || Character == 127) bVisible = false;
    if (Name.IsEmpty() || Name.Len() > 32 || !bVisible)
    { Fail(TEXT("INVALID_NAME"), TEXT("请输入 1 至 32 字的档案名称。")); return; }
    auto Input = MakeShared<FJsonObject>(); Input->SetStringField(TEXT("displayName"), Name);
    Phase = EHczsSessionPhase::ProfileSelection;
    UserMessage = TEXT("正在创建本地档案…"); ErrorCode.Reset();
    Fetch(TEXT("create-profile"), TEXT("POST"), TEXT("/profiles"), Json(Input), [this, Name](TSharedPtr<FJsonObject> O, int32 Code, const FString& Error)
    {
        FHczsLocalProfile Profile;
        if (!Error.IsEmpty() || Code != 201 || !ParseProfile(Child(O, TEXT("profile")), Profile) || Profile.DisplayName != Name || Profile.Revision != 1 ||
            Profiles.ContainsByPredicate([&Profile](const FHczsLocalProfile& P) { return P.Id == Profile.Id; }))
        {
            const FString Reason = Error.IsEmpty() ? TEXT("UNEXPECTED_RESPONSE") : Error;
            if (Code == 0 || Code >= 500 || (Code >= 200 && Code < 300))
            {
                // This endpoint is deliberately not retried: it has no server idempotency key.
                bAllowNewProfiles = false;
                Fail(Reason, TEXT("档案创建结果尚未确认。请刷新档案列表后选择，避免重复创建。"));
            }
            else Fail(Reason, FriendlyError(Code, Reason));
            return;
        }
        Profiles.Add(Profile); ++SessionEpoch; SelectedProfileId = Profile.Id;
        SelectedEncounterId.Reset(); CurrentBattle = FHczsBattleView(); HallPreference = FHczsHallPreference();
        ResetMainlineProgress();
        LastEvents.Reset(); Battles.Reset(); bBattleStateCurrent = false; bEncounterScenarioReady = false; MinimumBattleRevision = 0;
        LastVisualReceipt = FHczsBattleVisualReceipt(); bProfileStateCurrent = true;
        UserMessage = TEXT("本地档案已创建并保存。"); ErrorCode.Reset(); ReadHall(true);
    });
}
void UHczsGameInstance::ReadHall(bool bThenLoadBattles)
{
    if (SelectedProfileId.IsEmpty()) return;
    const FString Expected = SelectedProfileId;
    Fetch(TEXT("hall"), TEXT("GET"), ProfilesRoute() + TEXT("/hall"), TEXT(""), [this, Expected, bThenLoadBattles](TSharedPtr<FJsonObject> O, int32 Code, const FString& Error)
    {
        FHczsHallPreference Next;
        if (!Error.IsEmpty() || Code != 200 || !ParseHall(Child(O, TEXT("hall")), Expected, Next) ||
            (HallPreference.bIsValid && Next.Revision < HallPreference.Revision))
        {
            if (bPendingReceiptConfirmed && PendingIntentKind == TEXT("hall")) bPendingIntentRetryable = true;
            const FString Reason = Error.IsEmpty() ? TEXT("UNEXPECTED_RESPONSE") : Error; Fail(Reason, FriendlyError(Code, Reason)); return;
        }
        HallPreference = Next;
        if (bThenLoadBattles) Phase = EHczsSessionPhase::Hall;
        if (bPendingReceiptConfirmed && PendingIntentKind == TEXT("hall")) ClearPendingIntent();
        UserMessage = TEXT("本地档案已读取，可以选择关卡或继续已保存战斗。"); ErrorCode.Reset(); Notify();
        if (bThenLoadBattles) RefreshBattles();
    });
}
void UHczsGameInstance::ReadEncounters()
{
    Fetch(TEXT("encounters"), TEXT("GET"), TEXT("/encounters"), TEXT(""), [this](TSharedPtr<FJsonObject> O, int32 Code, const FString& Error)
    {
        TArray<FHczsEncounterSummary> Next;
        if (!Error.IsEmpty() || Code != 200 || !ParseEncounters(O, Next))
        { const FString Reason = Error.IsEmpty() ? TEXT("UNEXPECTED_RESPONSE") : Error; Fail(Reason, FriendlyError(Code, Reason)); return; }
        Encounters = MoveTemp(Next);
        if (!SelectedEncounterId.IsEmpty())
        {
            const auto* Selected = Encounters.FindByPredicate([this](const FHczsEncounterSummary& E) { return E.Id == SelectedEncounterId; });
            if (!Selected || Selected->DefinitionId != SelectedDefinitionId) bEncounterScenarioReady = false;
        }
        ErrorCode.Reset();
        if (!SelectedProfileId.IsEmpty() && Phase == EHczsSessionPhase::Hall) RefreshBattles();
        else if (bHasMainlineProgression && bProfileStateCurrent && !SelectedProfileId.IsEmpty()) ReadMainline();
        else Notify();
    });
}
void UHczsGameInstance::SelectEncounter(const FString& EncounterId)
{
    if (!CanStartRead() || SelectedProfileId.IsEmpty() || !bProfileStateCurrent || !bLocalServiceAvailable) return;
    const auto* Entry = Encounters.FindByPredicate([&EncounterId](const FHczsEncounterSummary& E) { return E.Id == EncounterId; });
    if (!Entry || !IsId(EncounterId, 80)) { Fail(TEXT("INVALID_ENCOUNTER"), TEXT("请选择当前目录中的关卡。")); return; }
    SelectedEncounterId = EncounterId; SelectedDefinitionId = Entry->DefinitionId; bEncounterScenarioReady = false;
    UserMessage = TEXT("正在读取关卡规则…"); ErrorCode.Reset();
    const FString Definition = SelectedDefinitionId;
    Fetch(TEXT("scenario"), TEXT("GET"), TEXT("/encounters/") + EncounterId, TEXT(""), [this, EncounterId, Definition](TSharedPtr<FJsonObject> O, int32 Code, const FString& Error)
    {
        FScenario Scenario;
        if (!Error.IsEmpty() || Code != 200 || !ParseScenario(Child(O, TEXT("scenario")), Scenario) ||
            Scenario.EncounterId != EncounterId || Scenario.DefinitionId != Definition)
        { const FString Reason = Error.IsEmpty() ? TEXT("UNEXPECTED_RESPONSE") : Error; Fail(Reason, FriendlyError(Code, Reason)); return; }
        SelectedPlayerId = Scenario.PlayerId; SelectedEnemyId = Scenario.EnemyId; bEncounterScenarioReady = true;
        UserMessage = FString::Printf(TEXT("已选择 · %s"), *Scenario.Title); ErrorCode.Reset(); Notify();
    });
}
void UHczsGameInstance::RefreshBattles()
{
    if (!CanStartRead() || SelectedProfileId.IsEmpty() || !bProfileStateCurrent || !bLocalServiceAvailable) return;
    Fetch(TEXT("battle-list"), TEXT("GET"), BattlesRoute(), TEXT(""), [this](TSharedPtr<FJsonObject> O, int32 Code, const FString& Error)
    {
        TArray<FHczsBattleSummary> Next;
        if (!Error.IsEmpty() || Code != 200 || !ParseBattleList(O, Next))
        { const FString Reason = Error.IsEmpty() ? TEXT("UNEXPECTED_RESPONSE") : Error; Fail(Reason, FriendlyError(Code, Reason)); return; }
        Battles = MoveTemp(Next); ErrorCode.Reset();
        if (bHasMainlineProgression) ReadMainline(); else Notify();
    });
}
void UHczsGameInstance::ContinueBattle(const FString& BattleId)
{
    if (!CanStartRead() || SelectedProfileId.IsEmpty() || !bProfileStateCurrent || !bLocalServiceAvailable) return;
    if (!IsUuid(BattleId) || !Battles.ContainsByPredicate([&BattleId](const FHczsBattleSummary& B) { return B.Id == BattleId; }))
    { Fail(TEXT("INVALID_BATTLE"), TEXT("请选择此档案中已保存的战斗。")); return; }
    MinimumBattleRevision = CurrentBattle.Id == BattleId ? CurrentBattle.Revision : 0;
    const auto* Summary = Battles.FindByPredicate([&BattleId](const FHczsBattleSummary& B) { return B.Id == BattleId; });
    MinimumBattleRevision = FMath::Max(MinimumBattleRevision, Summary->Revision);
    ReadBattle(BattleId);
}
void UHczsGameInstance::ReadBattle(const FString& BattleId, bool bAfterReceipt, bool bPrepareSettlement)
{
    if (SelectedProfileId.IsEmpty()) return;
    const FString ProfileId = SelectedProfileId; bBattleStateCurrent = false;
    if (!bAfterReceipt) LastVisualReceipt = FHczsBattleVisualReceipt();
    UserMessage = bAfterReceipt ? TEXT("操作已保存，正在同步最新战斗…") : TEXT("正在读取已保存战斗…");
    Fetch(TEXT("battle-state"), TEXT("GET"), BattlesRoute() + TEXT("/") + BattleId, TEXT(""), [this, ProfileId, BattleId, bAfterReceipt, bPrepareSettlement](TSharedPtr<FJsonObject> O, int32 Code, const FString& Error)
    {
        FHczsBattleView Next;
        if (!Error.IsEmpty() || Code != 200 || !ParseBattle(Child(O, TEXT("battle")), ProfileId, BattleId, Next) || !CanApplyBattleRevision(CurrentBattle, Next, MinimumBattleRevision))
        {
            const FString Reason = Error.IsEmpty() ? TEXT("UNEXPECTED_RESPONSE") : Error;
            if (bAfterReceipt) bPendingIntentRetryable = true;
            Fail(Reason, bAfterReceipt ? TEXT("操作已保存，但最新状态读取失败。请重试同步，暂时不能继续出牌。") : FriendlyError(Code, Reason)); return;
        }
        CurrentBattle = MoveTemp(Next); MinimumBattleRevision = CurrentBattle.Revision; bBattleStateCurrent = true;
        LastVisualReceipt = bAfterReceipt && CanPublishVisualReceipt(CurrentBattle, PendingVisualReceipt)
            ? PendingVisualReceipt : FHczsBattleVisualReceipt();
        Phase = EHczsSessionPhase::Battle; ErrorCode.Reset();
        if (bAfterReceipt) ClearPendingIntent(LastVisualReceipt.bValid);
        UserMessage = CurrentBattle.Status == TEXT("player-turn") ? TEXT("轮到本方行动，操作会自动保存。") : CurrentBattle.Status == TEXT("won") ? TEXT("战斗胜利，结果已保存。") : TEXT("战斗结束，结果已保存。");
        UE_LOG(LogTemp, Display, TEXT("HCZS battle synchronized: revision=%lld round=%d status=%s hand=%d"), CurrentBattle.Revision, CurrentBattle.Round, *CurrentBattle.Status, CurrentBattle.Hand.Num());
        if (bHasMainlineProgression && CurrentBattle.Status == TEXT("won") && CurrentBattle.EncounterId == TEXT("tutorial-5000"))
        {
            // Deliver the final hit to the existing presentation before starting
            // an unrelated progress GET (scene readiness requires an idle request).
            if (bAfterReceipt && LastVisualReceipt.bValid) Notify();
            if (!bHasPendingIntent && !bRequestInFlight) ReadMainline(bPrepareSettlement);
        }
        else Notify();
    });
}
void UHczsGameInstance::RefreshCurrentBattle()
{
    if (!CanStartRead() || SelectedProfileId.IsEmpty() || !bProfileStateCurrent || !CurrentBattle.bIsValid) return;
    MinimumBattleRevision = FMath::Max(MinimumBattleRevision, CurrentBattle.Revision);
    ReadBattle(CurrentBattle.Id);
}
void UHczsGameInstance::ResetMainlineProgress()
{
    MainlineProgress = FHczsMainlineProgress(); bMainlineStateCurrent = false;
}
void UHczsGameInstance::RefreshMainline()
{
    if (!CanStartRead() || !bLocalServiceAvailable || !bHasMainlineProgression || !bProfileStateCurrent || SelectedProfileId.IsEmpty()) return;
    ReadMainline();
}
bool UHczsGameInstance::CanConfirmMainlineVictory() const
{
    return !bShuttingDown && bLocalServiceAvailable && bHasMainlineProgression && bProfileStateCurrent &&
        Phase == EHczsSessionPhase::Battle && bBattleStateCurrent && bMainlineStateCurrent &&
        !bRequestInFlight && !bHasPendingIntent && MainlineProgress.ProfileId == SelectedProfileId &&
        MainlineProgress.ContentId == MainlineContentId && CanSettleMainlineBattle(MainlineProgress, CurrentBattle);
}
void UHczsGameInstance::ConfirmMainlineVictory()
{
    if (!CanConfirmMainlineVictory()) return;
    // Explicit result-panel confirmation, after presentation has finished. Re-read
    // both authorities before constructing the command; a victory alone never advances progress.
    MinimumBattleRevision = FMath::Max(MinimumBattleRevision, CurrentBattle.Revision);
    ReadBattle(CurrentBattle.Id, false, true);
}
void UHczsGameInstance::RefreshMainlineIdentity(bool bPrepareSettlement)
{
    // Internal identity refresh is allowed only after a confirmed settlement or
    // a plain GET. It never replaces an unresolved command's original payload.
    if (bRequestInFlight || (bHasPendingIntent && (!bPendingReceiptConfirmed || PendingIntentKind != TEXT("settlement")))) return;
    Fetch(TEXT("mainline-content"), TEXT("GET"), TEXT("/bootstrap"), TEXT(""),
        [this, bPrepareSettlement](TSharedPtr<FJsonObject> O, int32 Code, const FString& Error)
    {
        TArray<FHczsLocalProfile> Next; bool ProfilesAllowed = false, BattlesAllowed = false, Enabled = false; FString Content;
        if (!Error.IsEmpty() || Code != 200 || !ParseBootstrap(O, Next, ProfilesAllowed, BattlesAllowed) ||
            !ParseMainlineCapability(O, Enabled, Content) || !Enabled ||
            !Next.ContainsByPredicate([this](const FHczsLocalProfile& P) { return P.Id == SelectedProfileId; }))
        {
            if (bPendingReceiptConfirmed) bPendingIntentRetryable = true;
            const FString Reason = Error.IsEmpty() ? TEXT("UNEXPECTED_RESPONSE") : Error;
            Fail(Reason, TEXT("主线内容身份读取失败，原进度和已确认操作均已保留。请重试同步。")); return;
        }
        MainlineContentId = Content; bMainlineStateCurrent = false;
        ReadMainline(bPrepareSettlement, false);
    });
}
void UHczsGameInstance::ReadMainline(bool bPrepareSettlement, bool bCanRefreshContent)
{
    if (!bHasMainlineProgression || SelectedProfileId.IsEmpty() || !bProfileStateCurrent || bRequestInFlight) return;
    if (bHasPendingIntent && (PendingIntentKind != TEXT("settlement") || !bPendingReceiptConfirmed)) return;
    const FString Profile = SelectedProfileId, Content = MainlineContentId, Battle = CurrentBattle.Id;
    bMainlineStateCurrent = false;
    const bool bAfterSettlement = bHasPendingIntent && PendingIntentKind == TEXT("settlement") && bPendingReceiptConfirmed;
    UserMessage = bAfterSettlement ? TEXT("通关已保存，正在读取最新主线进度…") : TEXT("正在读取本地主线进度…");
    Fetch(TEXT("mainline"), TEXT("GET"), ProfilesRoute() + TEXT("/mainline"), TEXT(""),
        [this, Profile, Content, Battle, bPrepareSettlement, bAfterSettlement, bCanRefreshContent](TSharedPtr<FJsonObject> O, int32 Code, const FString& Error)
    {
        FHczsMainlineProgress Next;
        const int64 MinimumRevision = bAfterSettlement ? PendingIntentRevision + 1 : 0;
        FString ResponseContent; const auto Campaign = Child(O, TEXT("campaign"));
        if (bCanRefreshContent && Error.IsEmpty() && Code == 200 && Campaign.IsValid() &&
            Campaign->TryGetStringField(TEXT("contentId"), ResponseContent) && ResponseContent != Content)
        { RefreshMainlineIdentity(bPrepareSettlement); return; }
        FHczsMainlineProgress Prior = MainlineProgress;
        // Bootstrap has supplied the new content identity. ParseMainline still
        // requires the same supported source nodes/policy; completion may not regress.
        if (Prior.bIsValid && Prior.ContentId != Content) Prior.ContentId = Content;
        if (!Error.IsEmpty() || Code != 200 || !O.IsValid() || O->Values.Num() != 1 ||
            Profile != SelectedProfileId || Content != MainlineContentId ||
            !ParseMainline(Campaign, Profile, Content, Next) ||
            !CanApplyMainlineProgress(Prior, Next, MinimumRevision) ||
            (bAfterSettlement && (Next.CompletedBattleId != PendingIntentBattle ||
                Next.CompletedBattleRevision != PendingSettlementBattleRevision)))
        {
            if (bAfterSettlement) bPendingIntentRetryable = true;
            const FString Reason = Error.IsEmpty() ? TEXT("UNEXPECTED_RESPONSE") : Error;
            Fail(Reason, bAfterSettlement ? TEXT("通关已保存，但最新进度读取失败。请重试同步，原通关操作不会再次提交。") : FriendlyError(Code, Reason));
            return;
        }
        MainlineProgress = MoveTemp(Next); bMainlineStateCurrent = true; ErrorCode.Reset();
        UE_LOG(LogTemp, Display, TEXT("HCZS mainline synchronized: revision=%lld passed=%d confirmed=%d"),
            MainlineProgress.Revision, MainlineProgress.bFirstChallengePassed, bAfterSettlement);
        if (bAfterSettlement) ClearPendingIntent();
        if (bPrepareSettlement && Battle == CurrentBattle.Id && CanConfirmMainlineVictory())
        {
            auto Input = MakeShared<FJsonObject>();
            // Reopening the same won battle reuses the same identity. The server's
            // one-time challenge + immutable receipt also cover process interruption.
            Input->SetStringField(TEXT("requestId"), TEXT("ue-mainline-") + CurrentBattle.Id);
            Input->SetNumberField(TEXT("expectedRevision"), static_cast<double>(MainlineProgress.Revision));
            Input->SetStringField(TEXT("contentId"), MainlineContentId); Input->SetStringField(TEXT("battleId"), CurrentBattle.Id);
            UserMessage = TEXT("正在确认序章首战通关…");
            BeginIntent(TEXT("settlement"), TEXT("POST"), ProfilesRoute() + TEXT("/mainline/settlements"), Json(Input), MainlineProgress.Revision);
            return;
        }
        UserMessage = MainlineProgress.bFirstChallengePassed
            ? TEXT("序章首战已通关；下一挑战的战斗仍待恢复。本次不发放奖励。")
            : TEXT("序章首战尚未确认通关。胜利后可在结果面板确认。");
        Notify();
    });
}
void UHczsGameInstance::BeginIntent(const FString& Kind, const FString& Verb, const FString& Route, const FString& Body, int64 ExpectedRevision)
{
    PendingIntentKind = Kind; PendingIntentVerb = Verb; PendingIntentRoute = Route; PendingIntentBody = Body;
    PendingIntentProfile = SelectedProfileId; PendingIntentBattle = (Kind == TEXT("action") || Kind == TEXT("settlement")) ? CurrentBattle.Id : FString();
    PendingSettlementContentId = Kind == TEXT("settlement") ? MainlineContentId : FString();
    PendingSettlementBattleRevision = Kind == TEXT("settlement") ? CurrentBattle.Revision : 0;
    PendingIntentEncounter = Kind == TEXT("create-battle") ? SelectedEncounterId : FString(); PendingIntentRevision = ExpectedRevision;
    bHasPendingIntent = true; bPendingIntentRetryable = false; bPendingReceiptConfirmed = false; ConfirmedBattleId.Reset(); ConfirmedBattleRevision = 0;
    LastVisualReceipt = FHczsBattleVisualReceipt(); PendingVisualReceipt = FHczsBattleVisualReceipt();
    PendingCardVisual = FHczsCardIntentVisual();
    if (Kind == TEXT("action"))
    {
        TSharedPtr<FJsonObject> Intent; FString Type, Instance;
        if (FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Body), Intent) && Intent.IsValid() &&
            Intent->TryGetStringField(TEXT("type"), Type) && Type == TEXT("play-card") &&
            Intent->TryGetStringField(TEXT("instanceId"), Instance))
        {
            const auto* Card = CurrentBattle.Hand.FindByPredicate([&Instance](const FHczsHandCard& C) { return C.InstanceId == Instance; });
            if (Card && Intent->TryGetStringField(TEXT("requestId"), PendingCardVisual.RequestId))
            { PendingCardVisual.BattleId = CurrentBattle.Id; PendingCardVisual.CardId = Card->CardId; PendingCardVisual.ExpectedRevision = ExpectedRevision; }
        }
    }
    SendPendingIntent();
}
void UHczsGameInstance::ClearPendingIntent(bool bConfirmedCard)
{
    const FString VisualRequest = PendingCardVisual.RequestId;
    const bool bWasDispatched = PendingCardVisual.bDispatched;
    PendingCardVisual = FHczsCardIntentVisual();
    bHasPendingIntent = false; bPendingIntentRetryable = false; bPendingReceiptConfirmed = false;
    PendingIntentKind.Reset(); PendingIntentVerb.Reset(); PendingIntentRoute.Reset(); PendingIntentBody.Reset();
    PendingIntentProfile.Reset(); PendingIntentBattle.Reset(); PendingIntentEncounter.Reset(); PendingIntentRevision = 0;
    PendingSettlementContentId.Reset(); PendingSettlementBattleRevision = 0;
    ConfirmedBattleId.Reset(); ConfirmedBattleRevision = 0;
    PendingVisualReceipt = FHczsBattleVisualReceipt();
    if (bWasDispatched) OnCardIntentSettledNative.Broadcast(VisualRequest, bConfirmedCard);
}
void UHczsGameInstance::CreateSelectedBattle()
{
    if (!CanStartRead() || !bLocalServiceAvailable || SelectedProfileId.IsEmpty() || !bProfileStateCurrent || !bEncounterScenarioReady || !bAllowNewBattles) return;
    auto Input = MakeShared<FJsonObject>(); Input->SetStringField(TEXT("requestId"), RequestId());
    Input->SetStringField(TEXT("encounterId"), SelectedEncounterId);
#if !UE_BUILD_SHIPPING
    int64 DebugSeed = 0;
    if (FParse::Value(FCommandLine::Get(), TEXT("HczsDebugBattleSeed="), DebugSeed) && DebugSeed >= 0 && DebugSeed <= 4294967295LL)
        Input->SetNumberField(TEXT("seed"), static_cast<double>(DebugSeed));
#endif
    UserMessage = TEXT("正在创建并保存战斗…"); ErrorCode.Reset();
    BeginIntent(TEXT("create-battle"), TEXT("POST"), BattlesRoute(), Json(Input), 0);
}
bool UHczsGameInstance::CanSubmitBattleIntent() const
{
    return !bShuttingDown && bLocalServiceAvailable && Phase == EHczsSessionPhase::Battle && CurrentBattle.bIsValid &&
        bProfileStateCurrent && CurrentBattle.ProfileId == SelectedProfileId && bBattleStateCurrent && !bRequestInFlight && !bHasPendingIntent && CurrentBattle.Status == TEXT("player-turn");
}
bool UHczsGameInstance::IsPendingReceiptConfirmed() const { return bHasPendingIntent && bPendingReceiptConfirmed; }
bool UHczsGameInstance::IsHallSceneReady() const
{
    return !bShuttingDown && IsSessionSceneReady(EHczsSessionPhase::Hall, Phase, SelectedProfileId, bProfileStateCurrent, HallPreference,
        CurrentBattle, bBattleStateCurrent, bRequestInFlight, bHasPendingIntent);
}
bool UHczsGameInstance::IsBattleSceneReady() const
{
    return !bShuttingDown && IsSessionSceneReady(EHczsSessionPhase::Battle, Phase, SelectedProfileId, bProfileStateCurrent, HallPreference,
        CurrentBattle, bBattleStateCurrent, bRequestInFlight, bHasPendingIntent);
}
void UHczsGameInstance::PlayCard(const FString& InstanceId) { StartBattleAction(TEXT("play-card"), InstanceId); }
void UHczsGameInstance::EndTurn() { StartBattleAction(TEXT("end-turn"), FString()); }
void UHczsGameInstance::StartBattleAction(const FString& Type, const FString& InstanceId)
{
    if (!CanSubmitBattleIntent()) return;
    if (Type == TEXT("play-card"))
    {
        const auto* Card = CurrentBattle.Hand.FindByPredicate([&InstanceId](const FHczsHandCard& C) { return C.InstanceId == InstanceId; });
        if (!Card || Card->Cost > CurrentBattle.Energy) { Fail(TEXT("INVALID_ACTION"), TEXT("这张牌不在手牌中，或当前能量不足。")); return; }
    }
    auto Input = MakeShared<FJsonObject>(); Input->SetStringField(TEXT("requestId"), RequestId());
    Input->SetNumberField(TEXT("expectedRevision"), static_cast<double>(CurrentBattle.Revision)); Input->SetStringField(TEXT("type"), Type);
    if (Type == TEXT("play-card")) Input->SetStringField(TEXT("instanceId"), InstanceId);
    UserMessage = TEXT("正在执行并保存行动…"); ErrorCode.Reset();
    BeginIntent(TEXT("action"), TEXT("POST"), BattlesRoute() + TEXT("/") + CurrentBattle.Id + TEXT("/actions"), Json(Input), CurrentBattle.Revision);
}
void UHczsGameInstance::SaveHallHero(int32 HeroId)
{
    if (!CanStartRead() || !bLocalServiceAvailable || SelectedProfileId.IsEmpty() || !bProfileStateCurrent || !HallPreference.bIsValid || HeroId < 0) return;
    auto Input = MakeShared<FJsonObject>(); Input->SetStringField(TEXT("requestId"), RequestId());
    Input->SetNumberField(TEXT("expectedRevision"), static_cast<double>(HallPreference.Revision));
    if (HeroId == 0) Input->SetField(TEXT("selectedHeroId"), MakeShared<FJsonValueNull>()); else Input->SetNumberField(TEXT("selectedHeroId"), HeroId);
    UserMessage = TEXT("正在保存大厅角色偏好…"); ErrorCode.Reset();
    BeginIntent(TEXT("hall"), TEXT("PATCH"), ProfilesRoute() + TEXT("/hall"), Json(Input), HallPreference.Revision);
}
void UHczsGameInstance::SendPendingIntent()
{
    if (!bHasPendingIntent || bRequestInFlight || bShuttingDown || PendingIntentProfile != SelectedProfileId) return;
    bPendingIntentRetryable = false;
    Fetch(PendingIntentKind, PendingIntentVerb, PendingIntentRoute, PendingIntentBody, [this](TSharedPtr<FJsonObject> O, int32 Code, const FString& Error)
    {
        if (!Error.IsEmpty())
        {
            if (PendingIntentKind == TEXT("settlement"))
            {
                bMainlineStateCurrent = false;
                if (Code == 0 || Code >= 500 || Error == TEXT("INVALID_JSON") || Error == TEXT("RESPONSE_TOO_LARGE"))
                {
                    bPendingIntentRetryable = true;
                    Fail(Error, TEXT("通关确认结果未知。请重试原操作，同一通关只会保存一次。"));
                }
                else
                {
                    // A definite rejection is reconciled by GET, never by changing
                    // the request id or silently resubmitting a new command.
                    ClearPendingIntent(); Fail(Error, FriendlyError(Code, Error));
                    if (Error == TEXT("CONTENT_CHANGED") || Code == 404) RefreshBootstrap();
                    else ReadMainline();
                }
                return;
            }
            if (Code == 409)
            {
                const FString Kind = PendingIntentKind, Battle = PendingIntentBattle; ClearPendingIntent(); bBattleStateCurrent = false;
                Fail(Error, FriendlyError(Code, Error));
                if (Kind == TEXT("hall")) ReadHall(); else if (!Battle.IsEmpty()) ReadBattle(Battle); else RefreshBattles();
            }
            else if (Code == 0 || Code >= 500 || Error == TEXT("INVALID_JSON") || Error == TEXT("RESPONSE_TOO_LARGE"))
            { bPendingIntentRetryable = true; bBattleStateCurrent = false; Fail(Error, TEXT("操作结果尚未确认。请重试原操作，确认同一次操作的保存结果。")); }
            else
            {
                const FString Kind = PendingIntentKind, Battle = PendingIntentBattle; ClearPendingIntent(); Fail(Error, FriendlyError(Code, Error));
                if (Kind == TEXT("action") && !Battle.IsEmpty()) ReadBattle(Battle);
            }
            return;
        }
        if (PendingIntentKind == TEXT("settlement"))
        {
            FHczsMainlineProgress Receipt;
            if (Code != 200 || !ParseMainlineReceipt(O, PendingIntentProfile, PendingSettlementContentId,
                PendingIntentBattle, PendingSettlementBattleRevision, PendingIntentRevision, Receipt))
            {
                bPendingIntentRetryable = true; bMainlineStateCurrent = false;
                Fail(TEXT("UNEXPECTED_RESPONSE"), TEXT("通关回执不符合契约，请重试原操作确认。未更新主线进度。")); return;
            }
            // Historical idempotent receipts are confirmations, not current state.
            bPendingReceiptConfirmed = true; ReadMainline(); return;
        }
        if (PendingIntentKind == TEXT("hall"))
        {
            FHczsHallPreference Receipt; bool Replayed = false;
            TSharedPtr<FJsonObject> Intent;
            const auto Reader = TJsonReaderFactory<>::Create(PendingIntentBody);
            double ExpectedHero = 0;
            if (!FJsonSerializer::Deserialize(Reader, Intent) || !Intent.IsValid() || !Intent->HasField(TEXT("selectedHeroId")))
            { bPendingIntentRetryable = true; Fail(TEXT("INVALID_LOCAL_INTENT"), TEXT("大厅偏好载荷无效，尚未确认保存。")); return; }
            if (!Intent->TryGetField(TEXT("selectedHeroId"))->IsNull()) Intent->TryGetNumberField(TEXT("selectedHeroId"), ExpectedHero);
            if (Code != 200 || !ParseHall(Child(O, TEXT("hall")), PendingIntentProfile, Receipt) ||
                Receipt.Revision != PendingIntentRevision + 1 || Receipt.SelectedHeroId != ExpectedHero || !O->TryGetBoolField(TEXT("replayed"), Replayed))
            { bPendingIntentRetryable = true; Fail(TEXT("UNEXPECTED_RESPONSE"), TEXT("保存结果响应异常，请重试原操作确认。")); return; }
            // Do not paint historical receipts. GET will load the current preference.
            bPendingReceiptConfirmed = true; HallPreference.Revision = FMath::Max(HallPreference.Revision, Receipt.Revision);
            ReadHall(); return;
        }
        FHczsBattleView Receipt; TArray<FString> Events; FHczsBattleVisualReceipt Visual;
        const bool bCreate = PendingIntentKind == TEXT("create-battle");
        TSharedPtr<FJsonObject> Intent; FString ActionType, Instance;
        const auto Reader = TJsonReaderFactory<>::Create(PendingIntentBody);
        if (!FJsonSerializer::Deserialize(Reader, Intent) || !Intent.IsValid())
        { bPendingIntentRetryable = true; Fail(TEXT("INVALID_LOCAL_INTENT"), TEXT("操作载荷无效，尚未确认保存。")); return; }
        if (!bCreate) { Intent->TryGetStringField(TEXT("type"), ActionType); Intent->TryGetStringField(TEXT("instanceId"), Instance); }
        if (Code != (bCreate ? 201 : 200) || !ParseReceipt(O, PendingIntentProfile, PendingIntentBattle, PendingIntentEncounter, PendingIntentRevision, Receipt, Events, ActionType, Instance, &Visual) ||
            (bCreate && (Receipt.PlayerId != SelectedPlayerId || Receipt.EnemyId != SelectedEnemyId)))
        { bPendingIntentRetryable = true; bBattleStateCurrent = false; Fail(TEXT("UNEXPECTED_RESPONSE"), TEXT("操作回执不符合战斗契约。请重试原操作确认，未替换当前画面。")); return; }
        if (bCreate)
        {
            FString Template;
            const auto Selection = Child(Child(Child(Child(O, TEXT("battle")), TEXT("scenario")), TEXT("provenance")), TEXT("enemySelection"));
            if (Selection.IsValid()) Selection->TryGetStringField(TEXT("templateDefinitionId"), Template);
            double ExpectedSeed = 0;
            if ((Receipt.DefinitionId != SelectedDefinitionId && Template != SelectedDefinitionId) ||
                (Intent->TryGetNumberField(TEXT("seed"), ExpectedSeed) && O->GetArrayField(TEXT("events"))[0]->AsObject()->GetNumberField(TEXT("seed")) != ExpectedSeed))
            { bPendingIntentRetryable = true; bBattleStateCurrent = false; Fail(TEXT("UNEXPECTED_RESPONSE"), TEXT("创建回执与已选择的关卡规则不一致，请重试确认。")); return; }
        }
        bPendingReceiptConfirmed = true; ConfirmedBattleId = Receipt.Id; ConfirmedBattleRevision = Receipt.Revision;
        PendingVisualReceipt = MoveTemp(Visual);
        MinimumBattleRevision = FMath::Max(CurrentBattle.Id == Receipt.Id ? CurrentBattle.Revision : int64(0), Receipt.Revision);
        LastEvents = MoveTemp(Events); ReadBattle(Receipt.Id, true);
    });
}
void UHczsGameInstance::RetryPendingIntent()
{
    if (!bHasPendingIntent || !bPendingIntentRetryable || bRequestInFlight) return;
    ErrorCode.Reset(); UserMessage = TEXT("正在确认上一操作…");
    if (bPendingReceiptConfirmed)
    {
        bPendingIntentRetryable = false;
        if (PendingIntentKind == TEXT("hall")) ReadHall();
        else if (PendingIntentKind == TEXT("settlement")) ReadMainline();
        else ReadBattle(ConfirmedBattleId, true);
    }
    else SendPendingIntent();
}
void UHczsGameInstance::ReturnToHall()
{
    if (!CanStartRead() || SelectedProfileId.IsEmpty() || !bProfileStateCurrent) return;
    LastVisualReceipt = FHczsBattleVisualReceipt();
    Phase = EHczsSessionPhase::Hall; UserMessage = TEXT("已返回大厅，战斗保留在此档案中。"); ErrorCode.Reset(); Notify(); RefreshBattles();
}
