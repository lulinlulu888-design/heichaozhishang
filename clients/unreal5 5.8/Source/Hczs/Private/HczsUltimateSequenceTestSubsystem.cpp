#include "HczsUltimateSequenceTestSubsystem.h"
#include "HczsUltimateSequence.h"
#include "HczsBattlePresentation.h"
#include "HczsGameInstance.h"
#include "HczsSessionContract.h"
#include "Animation/AnimSingleNodeInstance.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/GameInstance.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "MediaPlayer.h"
#include "ImageUtils.h"
#include "UnrealClient.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "HAL/PlatformFileManager.h"
#include "HAL/PlatformTime.h"
#include "HAL/PlatformMisc.h"

bool UHczsUltimateSequenceTestSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
#if UE_BUILD_SHIPPING
    return false;
#else
    return !IsRunningCommandlet() && Cast<UGameInstance>(Outer) && FParse::Param(FCommandLine::Get(), TEXT("HczsUltimateSequenceTest"));
#endif
}
void UHczsUltimateSequenceTestSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    FString Requested;
    FParse::Value(FCommandLine::Get(), TEXT("HczsUltimateSequenceInterrupt="), InterruptMode);
    if (!InterruptMode.IsEmpty() && InterruptMode != TEXT("cancel") && InterruptMode != TEXT("destroy") && InterruptMode != TEXT("endplay"))
    { bDone = true; FPlatformMisc::RequestExitWithStatus(false, 1); return; }
    int32 Port = -1;
    bHttpTest = FParse::Param(FCommandLine::Get(), TEXT("HczsUltimateHttpTest"));
    FParse::Value(FCommandLine::Get(), TEXT("HczsUltimateSequenceReport="), Requested);
    Requested = FPaths::ConvertRelativePathToFull(Requested.TrimQuotes()); FPaths::NormalizeFilename(Requested);
    FPaths::CollapseRelativeDirectories(Requested);
    FString Root = FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::ProjectDir(), TEXT("../../analysis/unreal/ultimate-video-test")));
    FPaths::CollapseRelativeDirectories(Root);
    if (!FPaths::IsUnderDirectory(FPaths::GetPath(Requested), Root) || FPaths::IsSamePath(FPaths::GetPath(Requested), Root) ||
        FPaths::GetExtension(Requested) != TEXT("json") || FPaths::FileExists(Requested) ||
        !FParse::Value(FCommandLine::Get(), TEXT("HczsServerPort="), Port) ||
        (bHttpTest ? (Port < 1 || Port > 65535 || Port == 7460 || !FParse::Param(FCommandLine::Get(), TEXT("HczsUltimateControllerTest"))) : Port != 0))
    { bDone = true; FPlatformMisc::RequestExitWithStatus(false, 1); return; }
    Report = Requested;
    FPlatformFileManager::Get().GetPlatformFile().CreateDirectoryTree(*FPaths::GetPath(Report));
    Deadline = FPlatformTime::Seconds() + (bHttpTest ? 150 : 60);
    Ticker = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateUObject(this, &UHczsUltimateSequenceTestSubsystem::TickTest), .01f);
}
bool UHczsUltimateSequenceTestSubsystem::PrepareHttpBattle()
{
    auto* Game = Cast<UHczsGameInstance>(GetGameInstance());
    if (!Game) { Failure = TEXT("Missing HTTP session"); return false; }
    if (Game->bRequestInFlight) return false;
    if (Game->bHasPendingIntent || !Game->ErrorCode.IsEmpty()) { Failure = TEXT("HTTP setup failed: ") + Game->ErrorCode; return false; }
    switch (HttpStep)
    {
    case 0:
        if (!Game->bLocalServiceAvailable || Game->Phase != EHczsSessionPhase::ProfileSelection || !Game->Profiles.IsEmpty())
        { Failure = TEXT("HTTP render test requires a fresh empty isolated service"); return false; }
        ++HttpStep; Game->CreateLocalProfile(TEXT("UE大招画面通信验收")); return false;
    case 1:
        if (Game->Phase != EHczsSessionPhase::Hall) { Failure = TEXT("Profile creation failed"); return false; }
        ++HttpStep; Game->SelectEncounter(TEXT("city-preview-10405")); return false;
    case 2:
        if (!Game->bEncounterScenarioReady) { Failure = TEXT("City scenario unavailable"); return false; }
        ++HttpStep; Game->CreateSelectedBattle(); return false;
    default:
        if (!Game->bBattleStateCurrent || Game->CurrentBattle.Status != TEXT("player-turn"))
        { Failure = TEXT("No active authoritative city battle"); return false; }
        for (const auto& Card : Game->CurrentBattle.Hand)
            if (Card.CardId == TEXT("410104")) { UltimateInstance = Card.InstanceId; return true; }
        if (++HttpActions > 40) { Failure = TEXT("Ultimate was not generated"); return false; }
        const FHczsHandCard* Best = nullptr;
        for (const auto& Card : Game->CurrentBattle.Hand)
            if (Card.Cost <= Game->CurrentBattle.Energy && (!Best || Card.Cost < Best->Cost)) Best = &Card;
        if (Best) Game->PlayCard(Best->InstanceId); else Game->EndTurn();
        return false;
    }
}
void UHczsUltimateSequenceTestSubsystem::Cue(const FString& Id, const FString& Name, float Position)
{
    auto Event = MakeShared<FJsonObject>();
    Event->SetStringField(TEXT("name"), Name); Event->SetStringField(TEXT("sequenceId"), Id);
    Event->SetNumberField(TEXT("sourcePosition"), Position);
    Event->SetNumberField(TEXT("actualPosition"), Sequence->GetAnimationPosition());
    Event->SetNumberField(TEXT("realSeconds"), FPlatformTime::Seconds());
    Events.Add(MakeShared<FJsonValueObject>(Event));
    if (Name.StartsWith(TEXT("attack"))) ++AttackCount;
    if (Name == TEXT("video")) VideoPosition = Sequence->GetAnimationPosition();
    if (Name == TEXT("video-complete")) ResumePosition = Sequence->GetAnimationPosition();
}
void UHczsUltimateSequenceTestSubsystem::Ended(const FString& Id, bool Success, const FString& Error)
{
    ++FinishCount;
    if (bInterrupting)
    {
        if (Success) Failure = TEXT("Interrupted sequence reported success");
        return;
    }
    bSequenceDone = Success;
    if (!Success) Failure = Error.IsEmpty() ? TEXT("Sequence failed") : Error;
}
void UHczsUltimateSequenceTestSubsystem::Capture(const FString& Name)
{
    ScreenshotPath = FPaths::Combine(FPaths::GetPath(Report), Name + TEXT(".png"));
    if (FPaths::FileExists(ScreenshotPath)) { Failure = TEXT("Refusing to overwrite screenshot"); return; }
    bAwaitingScreenshot = true;
    ScreenshotHandle = UGameViewportClient::OnScreenshotCaptured().AddUObject(this, &UHczsUltimateSequenceTestSubsystem::Captured);
    FScreenshotRequest::RequestScreenshot(ScreenshotPath, true, false);
}
void UHczsUltimateSequenceTestSubsystem::Captured(int32 Width, int32 Height, const TArray<FColor>& Pixels)
{
    UGameViewportClient::OnScreenshotCaptured().Remove(ScreenshotHandle); ScreenshotHandle.Reset(); bAwaitingScreenshot = false;
    if (Width < 64 || Height < 64 || static_cast<int64>(Width) * Height != Pixels.Num()) { Failure = TEXT("Invalid viewport pixels"); return; }
    TArray64<uint8> Png;
    FImageUtils::PNGCompressImageArray(Width, Height, TArrayView64<const FColor>(Pixels.GetData(), Pixels.Num()), Png);
    if (!FFileHelper::SaveArrayToFile(Png, *ScreenshotPath)) { Failure = TEXT("Screenshot save failed"); return; }
    auto Shot = MakeShared<FJsonObject>(); Shot->SetStringField(TEXT("path"), ScreenshotPath);
    Shot->SetNumberField(TEXT("animationPosition"), Sequence->GetAnimationPosition());
    Shot->SetBoolField(TEXT("worldPaused"), UGameplayStatics::IsGamePaused(GetGameInstance()->GetWorld()));
    Screenshots.Add(MakeShared<FJsonValueObject>(Shot));
}
bool UHczsUltimateSequenceTestSubsystem::TickTest(float Delta)
{
    if (bDone) return false;
    if (!Failure.IsEmpty()) { Finish(false, Failure); return false; }
    if (FPlatformTime::Seconds() > Deadline) { Finish(false, TEXT("Sequence real-time deadline exceeded")); return false; }
    UWorld* World = GetGameInstance()->GetWorld();
    if (!World || !World->HasBegunPlay() || !GetGameInstance()->GetGameViewportClient()) return true;
    if (bHttpTest && Stage == 0 && !PrepareHttpBattle()) return true;
    if (Stage == 0)
    {
        const bool bControllerTest = FParse::Param(FCommandLine::Get(), TEXT("HczsUltimateControllerTest"));
        if (World->WorldType != EWorldType::Game || !World->GetMapName().EndsWith(bControllerTest ? TEXT("L_City2077Preview") : TEXT("L_TutorialBattle")))
        { Finish(false, TEXT("Use explicit battle-map presentation test with no business server")); return false; }
        TArray<AActor*> Players; UGameplayStatics::GetAllActorsWithTag(World, TEXT("HCZSBattlePlayer"), Players);
        if (Players.Num() != 1) { Finish(false, TEXT("Missing original battle actor")); return false; }
        Mesh = Players[0]->FindComponentByClass<USkeletalMeshComponent>();
        if (!Mesh || !Mesh->GetSingleNodeInstance()) { Finish(false, TEXT("Missing single-node animation")); return false; }
        PriorAnimation = Mesh->GetSingleNodeInstance()->GetCurrentAsset();
        GetGameInstance()->GetGameViewportClient()->RemoveAllViewportWidgets();
        if (bControllerTest)
        {
            TArray<AActor*> Found; UGameplayStatics::GetAllActorsWithTag(World, TEXT("HCZSBattlePresentation"), Found);
            Presentation = Found.Num() == 1 ? Cast<AHczsBattlePresentation>(Found[0]) : nullptr;
            if (!Presentation || !Presentation->IsSceneReady()) { Finish(false, TEXT("City controller unavailable")); return false; }
            Sequence = Presentation->GetUltimateSequence();
        }
        else
        {
            Sequence = NewObject<UHczsUltimateSequence>(Players[0]); Players[0]->AddInstanceComponent(Sequence); Sequence->RegisterComponent();
        }
        Sequence->OnCueNative.AddUObject(this, &UHczsUltimateSequenceTestSubsystem::Cue);
        Sequence->OnFinishedNative.AddUObject(this, &UHczsUltimateSequenceTestSubsystem::Ended);
        Stage = 1;
        if (bHttpTest)
        {
            auto* Game = Cast<UHczsGameInstance>(GetGameInstance());
            Presentation->ApplySnapshot(Game->CurrentBattle, FHczsBattleVisualReceipt());
            Game->PlayCard(UltimateInstance);
            bImmediateHttpStart = Game->bRequestInFlight && Presentation->IsPresentationBusy() &&
                Sequence->GetState() != EHczsUltimateSequenceState::Idle;
            if (!bImmediateHttpStart) Failure = TEXT("Real HTTP intent failed to start before response");
        }
        else if (bControllerTest)
        {
            TestView.bIsValid = true; TestView.Id = TEXT("native-controller-fixture");
            TestView.EncounterId = TEXT("city-preview-10405"); TestView.DefinitionId = TEXT("city-preview-10405-fixture");
            TestView.PlayerId = TEXT("1"); TestView.EnemyId = TEXT("6605");
            TestView.PlayerHp.Approximate = TestView.EnemyHp.Approximate = 100;
            TestView.PlayerHp.Decimal = TestView.EnemyHp.Decimal = TEXT("100");
            TestView.Revision = 1;
            TestView.Status = TEXT("player-turn");
            Presentation->ApplySnapshot(TestView, TestReceipt);
            TestView.ActionIndex = 1; TestView.Revision = 2;
            TestReceipt.bValid = true; TestReceipt.BattleId = TestView.Id; TestReceipt.ActionIndex = 1;
            FHczsBattleVisualEvent Card; Card.Type = TEXT("CardPlayed"); Card.CardId = TEXT("410104");
            TestReceipt.Events.Add(Card);
            bLocalIntentFixture = FParse::Param(FCommandLine::Get(), TEXT("HczsUltimateLocalIntentTest"));
            if (bLocalIntentFixture)
            {
                auto* Session = Cast<UHczsGameInstance>(GetGameInstance());
                if (!Session) { Finish(false, TEXT("Missing session")); return false; }
                Session->CurrentBattle = TestView; Session->CurrentBattle.ActionIndex = 0; Session->CurrentBattle.Revision = 1;
                Session->Phase = EHczsSessionPhase::Battle;
                FHczsCardIntentVisual Intent; Intent.bDispatched = true; Intent.RequestId = TEXT("local-ultimate-fixture");
                Intent.BattleId = TestView.Id; Intent.CardId = TEXT("410104"); Intent.ExpectedRevision = 1;
                Session->OnCardIntentDispatchedNative.Broadcast(Intent);
                Session->OnCardIntentDispatchedNative.Broadcast(Intent); // Retry must not restart local playback.
                float Delay = 1;
                FParse::Value(FCommandLine::Get(), TEXT("HczsUltimateReceiptDelay="), Delay);
                ReceiptDue = FPlatformTime::Seconds() + Delay; bPendingReceipt = true;
            }
            else
            {
                Presentation->ApplySnapshot(TestView, TestReceipt);
                Presentation->ApplySnapshot(TestView, TestReceipt);
            }
            if (!Presentation->IsPresentationBusy()) Failure = TEXT("Controller failed to acquire presentation input lock");
        }
        else if (!Sequence->PlayElsa(Mesh, TEXT("native-elsa-sequence"), true)) Failure = TEXT("Original source sequence could not start");
    }
    if (!Sequence || bAwaitingScreenshot) return true;
    if (bHttpTest)
    {
        auto* Game = Cast<UHczsGameInstance>(GetGameInstance());
        if (!Game->bRequestInFlight && Game->bBattleStateCurrent && HczsSessionContract::CanPublishVisualReceipt(Game->CurrentBattle, Game->LastVisualReceipt) &&
            Game->LastVisualReceipt.Events.ContainsByPredicate([](const FHczsBattleVisualEvent& E) { return E.Type == TEXT("CardPlayed") && E.CardId == TEXT("410104"); }))
        {
            bHttpConfirmed = true;
            Presentation->ApplySnapshot(Game->CurrentBattle, Game->LastVisualReceipt);
        }
    }
    if (bPendingReceipt && !Presentation->IsPresentationBusy())
    { Finish(false, TEXT("Ultimate released request lock before authority")); return false; }
    if (bPendingReceipt && FPlatformTime::Seconds() >= ReceiptDue)
    {
        bPendingReceipt = false;
        if (FParse::Param(FCommandLine::Get(), TEXT("HczsUltimateRejectTest")))
        {
            if (Sequence->GetState() != EHczsUltimateSequenceState::Video || !UGameplayStatics::IsGamePaused(World))
            { Finish(false, TEXT("Rejection fixture missed the paused video interval")); return false; }
            bInterrupting = true;
            Cast<UHczsGameInstance>(GetGameInstance())->OnCardIntentSettledNative.Broadcast(TEXT("local-ultimate-fixture"), false);
            const bool Clean = !Presentation->IsPresentationBusy() && !UGameplayStatics::IsGamePaused(World) &&
                !Mesh->bPauseAnims && FinishCount == 1 && Sequence->GetState() == EHczsUltimateSequenceState::Cancelled;
            Finish(Clean, Clean ? FString() : TEXT("Rejected ultimate retained playback/input/pause")); return false;
        }
        Presentation->ApplySnapshot(TestView, TestReceipt);
        Presentation->ApplySnapshot(TestView, TestReceipt);
    }
    const float Position = Sequence->GetAnimationPosition();
    if (Sequence->GetState() == EHczsUltimateSequenceState::Video)
        bPauseVerified &= UGameplayStatics::IsGamePaused(World) && FMath::Abs(Position - VideoPosition) < .001f;
    if (Stage == 1 && Position >= .3f) { Stage = 2; Capture(TEXT("before-video")); }
    else if (Stage == 2 && Sequence->GetState() == EHczsUltimateSequenceState::Video)
    {
        auto* Video = Sequence->GetVideo();
        if (Video && Video->HasDecodedVideoSurface() && Video->GetMediaPlayer()->GetTime().GetTotalSeconds() >= .8)
        {
            if (!InterruptMode.IsEmpty())
            {
                bInterrupting = true;
                const bool WasPaused = UGameplayStatics::IsGamePaused(World) && Mesh->bPauseAnims;
                if (InterruptMode == TEXT("destroy")) Sequence->DestroyComponent();
                else if (InterruptMode == TEXT("endplay")) Sequence->GetOwner()->RouteEndPlay(EEndPlayReason::LevelTransition);
                else Sequence->Cancel();
                Sequence->Cancel(); // Duplicate cleanup must not notify or resume again.
                bCleanupVerified = WasPaused && !UGameplayStatics::IsGamePaused(World) && !Mesh->bPauseAnims &&
                    Mesh->GetSingleNodeInstance()->GetCurrentAsset() == PriorAnimation && !Sequence->GetVideo() &&
                    FinishCount == 1 && Sequence->GetState() == EHczsUltimateSequenceState::Cancelled;
                Finish(bCleanupVerified && Failure.IsEmpty(), bCleanupVerified ? Failure : TEXT("Interrupted sequence leaked pause, pose or media"));
                return false;
            }
            Stage = 3; Capture(TEXT("during-video"));
        }
    }
    else if (Stage == 3 && ResumePosition >= 0 && Position >= 5.8f) { Stage = 4; Capture(TEXT("after-video")); }
    if (bSequenceDone && !bAwaitingScreenshot && !bPendingReceipt && (!bHttpTest || (bHttpConfirmed && !Presentation->IsPresentationBusy())))
    {
        if (Presentation && !bHttpTest) Presentation->ApplySnapshot(TestView, TestReceipt);
        const bool Passed = Stage == 4 && Screenshots.Num() == 3 && AttackCount == 9 && FinishCount == 1 &&
            (!Presentation || !Presentation->IsPresentationBusy()) && bPauseVerified &&
            FMath::Abs(VideoPosition - 3.8399976f) < .001f && FMath::Abs(VideoPosition - ResumePosition) < .001f &&
            Sequence->GetFinalPosition() >= 7.199f && !UGameplayStatics::IsGamePaused(World);
        Finish(Passed, Passed ? FString() : TEXT("Source sequence/cue/return validation failed")); return false;
    }
    return true;
}
void UHczsUltimateSequenceTestSubsystem::Finish(bool Success, const FString& Error)
{
    if (bDone) return;
    bDone = true;
    auto Result = MakeShared<FJsonObject>(); Result->SetBoolField(TEXT("passed"), Success); Result->SetStringField(TEXT("error"), Error);
    Result->SetNumberField(TEXT("videoPosition"), VideoPosition); Result->SetNumberField(TEXT("resumePosition"), ResumePosition);
    Result->SetNumberField(TEXT("finalPosition"), Sequence ? Sequence->GetFinalPosition() : -1); Result->SetNumberField(TEXT("attackCues"), AttackCount);
    Result->SetBoolField(TEXT("worldAndPoseHeldDuringVideo"), bPauseVerified);
    Result->SetStringField(TEXT("interruptMode"), InterruptMode);
    Result->SetBoolField(TEXT("interruptionCleanupVerified"), bCleanupVerified);
    Result->SetNumberField(TEXT("finishNotifications"), FinishCount);
    Result->SetBoolField(TEXT("controllerFixture"), Presentation != nullptr);
    Result->SetBoolField(TEXT("localIntentFixture"), bLocalIntentFixture);
    Result->SetBoolField(TEXT("damageMappingVerified"), false); Result->SetBoolField(TEXT("businessCommandsIssued"), bHttpTest);
    Result->SetBoolField(TEXT("realHttpConfirmed"), bHttpConfirmed);
    Result->SetBoolField(TEXT("startedBeforeHttpResponse"), bImmediateHttpStart);
    Result->SetArrayField(TEXT("events"), Events); Result->SetArrayField(TEXT("screenshots"), Screenshots);
    FString Json; FJsonSerializer::Serialize(Result, TJsonWriterFactory<>::Create(&Json));
    const bool Saved = FFileHelper::SaveStringToFile(Json, *Report, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
    if (Sequence) { Sequence->OnFinishedNative.RemoveAll(this); Sequence->OnCueNative.RemoveAll(this); Sequence->Cancel(); }
    FPlatformMisc::RequestExitWithStatus(false, Success && Saved ? 0 : 1);
}
void UHczsUltimateSequenceTestSubsystem::Deinitialize()
{
    if (Ticker.IsValid()) FTSTicker::RemoveTicker(Ticker);
    if (ScreenshotHandle.IsValid()) UGameViewportClient::OnScreenshotCaptured().Remove(ScreenshotHandle);
    if (!bDone && !Report.IsEmpty()) Finish(false, TEXT("World ended before source sequence completed"));
    Super::Deinitialize();
}
