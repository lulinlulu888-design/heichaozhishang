#include "HczsUIFlowTestSubsystem.h"
#include "HczsGameInstance.h"
#include "HczsSessionWidget.h"
#include "HczsHallWidget.h"
#include "HczsWorldlineWidget.h"
#include "HczsBattlePresentation.h"
#include "HczsSessionContract.h"
#include "Containers/Ticker.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "HAL/PlatformFileManager.h"
#include "HAL/PlatformTime.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformProcess.h"
#include "UObject/UObjectIterator.h"
#include "Engine/World.h"
#include "Engine/GameViewportClient.h"
#include "Engine/SkeletalMesh.h"
#include "EngineUtils.h"
#include "Components/SkeletalMeshComponent.h"
#include "Animation/AnimSingleNodeInstance.h"
#include "Animation/AnimSequence.h"
#include "GameFramework/PlayerController.h"
#include "Camera/CameraActor.h"
#include "Widgets/SWindow.h"
#include "UnrealClient.h"
#include "RHIResources.h"
#include "ImageUtils.h"

namespace
{
FString Serialize(const TSharedPtr<FJsonObject>& Object)
{
    FString Result;
    if (Object) FJsonSerializer::Serialize(Object.ToSharedRef(), TJsonWriterFactory<>::Create(&Result));
    return Result;
}

TSharedPtr<FJsonObject> Parse(const FString& Text)
{
    TSharedPtr<FJsonObject> Object;
    FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Object);
    return Object;
}

bool SaveJson(const FString& Filename, const TSharedPtr<FJsonObject>& Object)
{
    FPlatformFileManager::Get().GetPlatformFile().CreateDirectoryTree(*FPaths::GetPath(Filename));
    return FFileHelper::SaveStringToFile(Serialize(Object), *Filename, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
}

bool AllowedFile(FString& Path)
{
    Path = Path.TrimQuotes();
    FPaths::NormalizeFilename(Path);
    Path = FPaths::ConvertRelativePathToFull(Path);
    FString Workspace = FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::ProjectDir(), TEXT("../..")));
    FPaths::CollapseRelativeDirectories(Workspace);
    FString Allowed = FPaths::Combine(Workspace, TEXT("analysis/unreal/session-test"));
    FPaths::NormalizeFilename(Allowed);
    return FPaths::IsUnderDirectory(Path, Allowed) && FPaths::GetExtension(Path) == TEXT("json");
}

bool TrueField(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key)
{
    bool Value = false;
    return Object && Object->TryGetBoolField(Key, Value) && Value;
}

bool NumberIs(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key, double Expected)
{
    double Value = 0;
    return Object && Object->TryGetNumberField(Key, Value) && Value == Expected;
}

bool StringIs(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key, const FString& Expected)
{
    FString Value;
    return Object && Object->TryGetStringField(Key, Value) && Value == Expected;
}

bool JsonEqual(const TSharedPtr<FJsonValue>& Left, const TSharedPtr<FJsonValue>& Right)
{
    if (!Left || !Right || Left->Type != Right->Type) return false;
    switch (Left->Type)
    {
    case EJson::Null: return true;
    case EJson::Boolean: return Left->AsBool() == Right->AsBool();
    case EJson::String: return Left->AsString() == Right->AsString();
    case EJson::Number: return Left->AsNumber() == Right->AsNumber();
    case EJson::Array:
    {
        const auto& A = Left->AsArray(); const auto& B = Right->AsArray();
        if (A.Num() != B.Num()) return false;
        for (int32 Index = 0; Index < A.Num(); ++Index) if (!JsonEqual(A[Index], B[Index])) return false;
        return true;
    }
    case EJson::Object:
    {
        const auto A = Left->AsObject(); const auto B = Right->AsObject();
        if (!A || !B || A->Values.Num() != B->Values.Num()) return false;
        for (const auto& Pair : A->Values)
        {
            const TSharedPtr<FJsonValue>* Other = B->Values.Find(Pair.Key);
            if (!Other || !JsonEqual(Pair.Value, *Other)) return false;
        }
        return true;
    }
    default: return false;
    }
}
}

bool UHczsUIFlowTestSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
#if UE_BUILD_SHIPPING
    return false;
#else
    int32 TestPort = 0; FString TestReport;
    return Cast<UHczsGameInstance>(Outer) && !IsRunningCommandlet()
        && FParse::Param(FCommandLine::Get(), TEXT("HczsUITest"))
        && FParse::Value(FCommandLine::Get(), TEXT("HczsServerPort="), TestPort)
        && TestPort > 0 && TestPort <= 65535 && TestPort != 7460
        && FParse::Value(FCommandLine::Get(), TEXT("HczsUITestReport="), TestReport) && AllowedFile(TestReport);
#endif
}

void UHczsUIFlowTestSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
#if !UE_BUILD_SHIPPING
    Session = Cast<UHczsGameInstance>(GetGameInstance());
    RunId = FGuid::NewGuid().ToString(EGuidFormats::DigitsWithHyphensLower);
    const FDateTime Started = FDateTime::UtcNow();
    StartedAtUtc = Started.ToIso8601();
    StartedAtUnixMs = Started.ToUnixTimestamp() * 1000 + Started.GetMillisecond();
    FParse::Value(FCommandLine::Get(), TEXT("HczsServerPort="), Port);
    FParse::Value(FCommandLine::Get(), TEXT("HczsUITestReport="), ReportPath);
    AllowedFile(ReportPath);
    FPlatformFileManager::Get().GetPlatformFile().CreateDirectoryTree(*FPaths::GetPath(ReportPath));
    bResume = FParse::Value(FCommandLine::Get(), TEXT("HczsUITestResume="), ResumePath);
    if (!FParse::Value(FCommandLine::Get(), TEXT("HczsUITestCheckpoint="), CheckpointPath))
        CheckpointPath = FPaths::Combine(FPaths::GetPath(ReportPath), TEXT("ui-checkpoint.json"));
    if (!AllowedFile(CheckpointPath)) { Fail(TEXT("Checkpoint path is outside the isolated report directory")); return; }
    if (bResume)
    {
        FString Text;
        if (!AllowedFile(ResumePath) || !FFileHelper::LoadFileToString(Text, *ResumePath) || Text.Len() > 1024 * 1024)
        { Fail(TEXT("Cannot load a contained UI checkpoint")); return; }
        Checkpoint = Parse(Text);
        if (!Checkpoint || !StringIs(Checkpoint, TEXT("mode"), TEXT("ue-slate-ui-checkpoint"))
            || !NumberIs(Checkpoint, TEXT("port"), Port)
            || !Checkpoint->TryGetStringField(TEXT("profileId"), ProfileId)
            || !Checkpoint->TryGetStringField(TEXT("battleId"), BattleId)
            || !HczsSessionContract::IsUuid(ProfileId) || !HczsSessionContract::IsUuid(BattleId))
        { Fail(TEXT("Checkpoint identity does not match the explicit isolated run")); return; }
        const TSharedPtr<FJsonObject>* Battle = nullptr;
        if (!Checkpoint->TryGetObjectField(TEXT("battle"), Battle))
        { Fail(TEXT("Checkpoint has no authoritative battle projection")); return; }
        SavedBattle = *Battle;
    }
    Deadline = FPlatformTime::Seconds() + (bResume ? 300.0 : 150.0);
    TickHandle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateUObject(this, &UHczsUIFlowTestSubsystem::TickFlow), 0.25f);
    UE_LOG(LogTemp, Display, TEXT("HCZS UI acceptance started: run=%s port=%d report=%s"),
        bResume ? TEXT("resume") : TEXT("initial"), Port, *ReportPath);
#endif
}

void UHczsUIFlowTestSubsystem::Deinitialize()
{
    UGameViewportClient::OnScreenshotCaptured().RemoveAll(this);
    if (TickHandle.IsValid()) FTSTicker::RemoveTicker(TickHandle);
    if (!bFinished && Session) SaveReport(false, TEXT("Game instance ended before UI acceptance completed"));
    Session = nullptr;
    Super::Deinitialize();
}

UHczsSessionWidget* UHczsUIFlowTestSubsystem::FindSessionWidget() const
{
    UWorld* World = GetGameInstance() ? GetGameInstance()->GetWorld() : nullptr;
    for (TObjectIterator<UHczsSessionWidget> It; It; ++It)
        if (!It->IsTemplate() && It->GetWorld() == World && It->IsInViewport()) return *It;
    return nullptr;
}

UHczsHallWidget* UHczsUIFlowTestSubsystem::FindHallWidget() const
{
    UWorld* World = GetGameInstance() ? GetGameInstance()->GetWorld() : nullptr;
    for (TObjectIterator<UHczsHallWidget> It; It; ++It)
        if (!It->IsTemplate() && It->GetWorld() == World && It->IsInViewport()) return *It;
    return nullptr;
}

UHczsWorldlineWidget* UHczsUIFlowTestSubsystem::FindWorldlineWidget() const
{
    UWorld* World = GetGameInstance() ? GetGameInstance()->GetWorld() : nullptr;
    for (TObjectIterator<UHczsWorldlineWidget> It; It; ++It)
        if (!It->IsTemplate() && It->GetWorld() == World && It->IsInViewport()) return *It;
    return nullptr;
}

TSharedPtr<FJsonObject> UHczsUIFlowTestSubsystem::ReadPaint(EHczsUITestSurface Surface) const
{
    if (Surface == EHczsUITestSurface::Worldline)
    {
        if (const auto* Widget = FindWorldlineWidget()) return Parse(Widget->DevelopmentDescribeUI());
    }
    else if (Surface == EHczsUITestSurface::Hall)
    {
        if (const auto* Widget = FindHallWidget()) return Parse(Widget->DevelopmentDescribeUI());
    }
    else if (const auto* Widget = FindSessionWidget()) return Parse(Widget->DevelopmentDescribeUI());
    return nullptr;
}

bool UHczsUIFlowTestSubsystem::Click(const FString& Action, const FString& Value, bool bTouch, EHczsUITestSurface Surface)
{
    if (!Session || Session->bRequestInFlight || Session->bHasPendingIntent) return false;
    TSharedPtr<FJsonObject> Before = ReadPaint(Surface);
    double PaintSerial = 0;
    if (!Before || !Before->TryGetNumberField(TEXT("paintSerial"), PaintSerial) || PaintSerial < 1
        || TrueField(Before, TEXT("presentationBusy"))) return false;
    const FString Map = GetGameInstance()->GetWorld()->GetMapName();
    const int32 Phase = static_cast<int32>(Session->Phase);
    const int64 Revision = Session->CurrentBattle.Revision;
    bool Hit = false;
    // The worldline delegate closes its widget on a successful click. Hold that
    // exact UObject for after-pointer observation rather than reading the new
    // adapter widget and pretending its pointer serial belongs to the source page.
    UHczsWorldlineWidget* Worldline = Surface == EHczsUITestSurface::Worldline ? FindWorldlineWidget() : nullptr;
    if (Worldline)
    {
        if (!Value.IsEmpty()) return false;
        Hit = Worldline->DevelopmentClickControl(Action, bTouch);
    }
    else if (Surface == EHczsUITestSurface::Hall)
    {
        if (auto* Widget = FindHallWidget()) Hit = Widget->DevelopmentClickControl(Action, bTouch);
    }
    else if (Surface == EHczsUITestSurface::Session)
        if (auto* Widget = FindSessionWidget()) Hit = Widget->DevelopmentClickControl(Action, Value, bTouch);
    if (!Hit) return false;
    auto Row = MakeShared<FJsonObject>();
    Row->SetStringField(TEXT("action"), Action); Row->SetStringField(TEXT("value"), Value);
    Row->SetStringField(TEXT("inputSource"), TEXT("slate-pointer"));
    Row->SetStringField(TEXT("input"), bTouch ? TEXT("touch") : TEXT("mouse"));
    Row->SetBoolField(TEXT("controlHit"), Hit); Row->SetStringField(TEXT("map"), Map);
    Row->SetNumberField(TEXT("phase"), Phase); Row->SetNumberField(TEXT("revision"), static_cast<double>(Revision));
    Row->SetBoolField(TEXT("requestInFlight"), false); Row->SetBoolField(TEXT("pendingIntent"), false);
    Row->SetObjectField(TEXT("paint"), Before);
    Row->SetStringField(TEXT("surface"), Surface == EHczsUITestSurface::Worldline ? TEXT("worldline") : Surface == EHczsUITestSurface::Hall ? TEXT("hall") : TEXT("session"));
    const auto After = Worldline ? Parse(Worldline->DevelopmentDescribeUI()) : ReadPaint(Surface);
    if (After) Row->SetObjectField(TEXT("pointerObservation"), After);
    Actions.Add(MakeShared<FJsonValueObject>(Row));
    BeforeRevision = Revision;
    UE_LOG(LogTemp, Display, TEXT("HCZS UI acceptance action: step=%d input=%s action=%s beforeRevision=%lld"),
        Step, bTouch ? TEXT("touch") : TEXT("mouse"), *Action, Revision);
    return true;
}

bool UHczsUIFlowTestSubsystem::BeginDrag(const FString& Action, const FString& InstanceId,
    const FString& Target, bool bTouch, const FString& PreviewStage)
{
    if (PendingDrag || !StableBattle()) return false;
    auto* Widget = FindSessionWidget();
    const auto Before = ReadPaint();
    if (!Widget || !Before || TrueField(Before, TEXT("pending"))) return false;
    const FDateTime Now = FDateTime::UtcNow();
    const int64 Revision = Session->CurrentBattle.Revision;
    auto Row = MakeShared<FJsonObject>();
    Row->SetStringField(TEXT("action"), Action); Row->SetStringField(TEXT("value"), InstanceId);
    Row->SetStringField(TEXT("inputSource"), TEXT("slate-drag"));
    Row->SetStringField(TEXT("input"), bTouch ? TEXT("touch") : TEXT("mouse"));
    Row->SetStringField(TEXT("surface"), TEXT("session"));
    Row->SetStringField(TEXT("map"), GetGameInstance()->GetWorld()->GetMapName());
    Row->SetNumberField(TEXT("phase"), static_cast<int32>(Session->Phase));
    Row->SetNumberField(TEXT("revision"), static_cast<double>(Revision));
    Row->SetNumberField(TEXT("startedAtUnixMs"), static_cast<double>(Now.ToUnixTimestamp() * 1000 + Now.GetMillisecond()));
    Row->SetBoolField(TEXT("requestInFlight"), false); Row->SetBoolField(TEXT("pendingIntent"), false);
    Row->SetObjectField(TEXT("paint"), Before);
    if (!Widget->DevelopmentDragCard(InstanceId, Target, bTouch, TEXT("begin"))) return false;
    Row->SetBoolField(TEXT("controlHit"), true);
    PendingDrag = Row; DragTarget = Target; DragPreviewStage = PreviewStage; DragStage = 0;
    BeforeRevision = Revision;
    return true;
}

bool UHczsUIFlowTestSubsystem::AdvanceDrag()
{
    if (!PendingDrag) return true;
    auto* Widget = FindSessionWidget();
    if (!Widget || !Session || Session->bRequestInFlight || Session->bHasPendingIntent)
        return Fail(TEXT("Drag lost its native UI or authoritative state before physical release"));
    const FString Instance = PendingDrag->GetStringField(TEXT("value"));
    const bool bTouch = StringIs(PendingDrag, TEXT("input"), TEXT("touch"));
    if (DragStage == 0)
    {
        if (!Widget->DevelopmentDragCard(Instance, DragTarget, bTouch, TEXT("move")))
            return Fail(TEXT("Native captured pointer move did not reach the selected card"));
        DragStage = 1;
        return true; // hold down across frames so the selection/target cue actually paints
    }
    if (DragStage == 1 && !DragPreviewStage.IsEmpty())
    {
        const auto Paint = ReadPaint();
        const TSharedPtr<FJsonObject>* Gesture = nullptr;
        if (!Paint || !Paint->TryGetObjectField(TEXT("lastGesture"), Gesture)
            || !TrueField(*Gesture, TEXT("active")))
            return Fail(TEXT("Drag preview disappeared before its native frame"));
        if (!QueueScreenshot(DragPreviewStage)) return true;
        DragStage = 2;
        return true; // screenshot callback must finish while pointer is still captured
    }
    if (!Widget->DevelopmentDragCard(Instance, DragTarget, bTouch, TEXT("release")))
        return Fail(TEXT("Physical release/capture cancellation did not end the native gesture"));
    const auto After = ReadPaint();
    const TSharedPtr<FJsonObject>* Gesture = nullptr;
    if (!After || !After->TryGetObjectField(TEXT("lastGesture"), Gesture))
        return Fail(TEXT("Native gesture has no pointer observation"));
    const FString Action = PendingDrag->GetStringField(TEXT("action"));
    const FString Expected = Action == TEXT("play-card") ? TEXT("submitted")
        : Action == TEXT("tap-card") ? TEXT("tap")
        : Action == TEXT("cancel-card-drag") ? TEXT("cancelled") : TEXT("rejected");
    if (!StringIs(*Gesture, TEXT("outcome"), Expected))
        return Fail(TEXT("Native card gesture produced the wrong submit/cancel outcome"));
    const FDateTime Now = FDateTime::UtcNow();
    PendingDrag->SetNumberField(TEXT("finishedAtUnixMs"), static_cast<double>(Now.ToUnixTimestamp() * 1000 + Now.GetMillisecond()));
    PendingDrag->SetObjectField(TEXT("pointerObservation"), After);
    Actions.Add(MakeShared<FJsonValueObject>(PendingDrag));
    UE_LOG(LogTemp, Display, TEXT("HCZS UI drag: action=%s input=%s outcome=%s revision=%lld"),
        *Action, bTouch ? TEXT("touch") : TEXT("mouse"), *Expected, BeforeRevision);
    PendingDrag.Reset(); DragPreviewStage.Reset(); DragStage = 0;
    return true;
}

bool UHczsUIFlowTestSubsystem::RunCancellationProbes()
{
    if (ProbeIndex >= 4) return true;
    if (!StableBattle()) return false;
    static const TCHAR* const Kinds[] = {TEXT("tap"), TEXT("invalid-target"), TEXT("outside"), TEXT("cancel")};
    static const TCHAR* const ActionsForProbe[] = {TEXT("tap-card"), TEXT("invalid-target-card-drag"), TEXT("outside-card-drag"), TEXT("cancel-card-drag")};
    static const TCHAR* const Targets[] = {TEXT("tap"), TEXT("player"), TEXT("outside"), TEXT("cancel")};
    if (ProbeStage == 0)
    {
        const FDateTime Now = FDateTime::UtcNow();
        ProbeStartedAtUnixMs = Now.ToUnixTimestamp() * 1000 + Now.GetMillisecond();
        // Both readbacks go through the real refresh button; no GI API stands in for input.
        if (Click(TEXT("refresh-battle"), TEXT(""), false)) ProbeStage = 1;
        return false;
    }
    if (ProbeStage == 1)
    {
        ProbeBefore = BattleProjection();
        for (const auto& Card : Session->CurrentBattle.Hand)
        {
            if (Card.Cost > Session->CurrentBattle.Energy) continue;
            if (BeginDrag(ActionsForProbe[ProbeIndex], Card.InstanceId, Targets[ProbeIndex], (ProbeIndex & 1) != 0))
            {
                ProbeAction = PendingDrag;
                ProbeStage = 2;
                return false;
            }
        }
        return false;
    }
    if (ProbeStage == 2)
    {
        if (PendingDrag) return false;
        if (Click(TEXT("refresh-battle"), TEXT(""), false)) ProbeStage = 3;
        return false;
    }
    if (!JsonEqual(MakeShared<FJsonValueObject>(ProbeBefore), MakeShared<FJsonValueObject>(BattleProjection())))
    { Fail(TEXT("Cancelled/tapped card gesture changed persisted battle state")); return false; }
    const FDateTime Now = FDateTime::UtcNow();
    auto Probe = MakeShared<FJsonObject>();
    Probe->SetStringField(TEXT("kind"), Kinds[ProbeIndex]);
    Probe->SetNumberField(TEXT("beforeServerRevision"), ProbeBefore->GetNumberField(TEXT("revision")));
    Probe->SetNumberField(TEXT("afterServerRevision"), static_cast<double>(Session->CurrentBattle.Revision));
    Probe->SetNumberField(TEXT("startedAtUnixMs"), static_cast<double>(ProbeStartedAtUnixMs));
    Probe->SetNumberField(TEXT("finishedAtUnixMs"), static_cast<double>(Now.ToUnixTimestamp() * 1000 + Now.GetMillisecond()));
    Probe->SetObjectField(TEXT("beforeBattle"), ProbeBefore);
    Probe->SetObjectField(TEXT("afterBattle"), BattleProjection());
    ProbeAction->SetObjectField(TEXT("probe"), Probe);
    ProbeBefore.Reset(); ProbeAction.Reset(); ProbeStage = 0; ++ProbeIndex;
    return ProbeIndex >= 4;
}

TSharedPtr<FJsonObject> UHczsUIFlowTestSubsystem::BattleProjection() const
{
    auto Object = MakeShared<FJsonObject>();
    if (!Session) return Object;
    const auto& B = Session->CurrentBattle;
    Object->SetStringField(TEXT("id"), B.Id); Object->SetStringField(TEXT("profileId"), B.ProfileId);
    Object->SetNumberField(TEXT("revision"), static_cast<double>(B.Revision));
    Object->SetStringField(TEXT("definitionId"), B.DefinitionId); Object->SetStringField(TEXT("encounterId"), B.EncounterId);
    Object->SetStringField(TEXT("status"), B.Status); Object->SetNumberField(TEXT("round"), B.Round);
    Object->SetNumberField(TEXT("energy"), B.Energy);
    Object->SetStringField(TEXT("playerHp"), B.PlayerHp.Decimal); Object->SetStringField(TEXT("enemyHp"), B.EnemyHp.Decimal);
    Object->SetStringField(TEXT("playerShield"), B.PlayerShield.Decimal); Object->SetStringField(TEXT("enemyShield"), B.EnemyShield.Decimal);
    Object->SetNumberField(TEXT("drawCount"), B.DrawCount); Object->SetNumberField(TEXT("discardCount"), B.DiscardCount);
    TArray<TSharedPtr<FJsonValue>> Hand;
    for (const auto& Card : B.Hand)
    {
        auto Row = MakeShared<FJsonObject>(); Row->SetStringField(TEXT("instanceId"), Card.InstanceId);
        Row->SetStringField(TEXT("cardId"), Card.CardId); Row->SetNumberField(TEXT("cost"), Card.Cost);
        Row->SetStringField(TEXT("name"), Card.Name); Hand.Add(MakeShared<FJsonValueObject>(Row));
    }
    Object->SetArrayField(TEXT("hand"), Hand);
    return Object;
}

TSharedPtr<FJsonObject> UHczsUIFlowTestSubsystem::SceneProjection() const
{
    auto Scene = MakeShared<FJsonObject>();
    UWorld* World = GetGameInstance() ? GetGameInstance()->GetWorld() : nullptr;
    if (!World || !Session) return Scene;
    TActorIterator<AHczsBattlePresentation> PresentationIt(World);
    if (PresentationIt)
    {
        const auto* P = *PresentationIt;
        Scene->SetBoolField(TEXT("ready"), P->IsSceneReady());
        Scene->SetBoolField(TEXT("canPresentBattle"), P->CanPresentBattle(Session->CurrentBattle));
        if (P->SceneAssets)
        {
            Scene->SetStringField(TEXT("playerId"), P->SceneAssets->PlayerId);
            Scene->SetStringField(TEXT("enemyId"), P->SceneAssets->EnemyId);
            Scene->SetStringField(TEXT("expectedPlayerMesh"), P->SceneAssets->PlayerMesh ? P->SceneAssets->PlayerMesh->GetPathName() : FString());
            Scene->SetStringField(TEXT("expectedEnemyMesh"), P->SceneAssets->EnemyMesh ? P->SceneAssets->EnemyMesh->GetPathName() : FString());
            Scene->SetBoolField(TEXT("originalTutorialStageRecovered"), P->SceneAssets->bOriginalTutorialStageRecovered);
            auto Animations = MakeShared<FJsonObject>();
            for (const auto& Pair : P->SceneAssets->PlayerAnimations)
                if (Pair.Value) Animations->SetStringField(TEXT("player/") + Pair.Key, Pair.Value->GetPathName());
            for (const auto& Pair : P->SceneAssets->EnemyAnimations)
                if (Pair.Value) Animations->SetStringField(TEXT("enemy/") + Pair.Key, Pair.Value->GetPathName());
            Scene->SetObjectField(TEXT("sourceAnimations"), Animations);
        }
    }
    APlayerController* Controller = World->GetFirstPlayerController();
    AActor* Target = Controller ? Controller->GetViewTarget() : nullptr;
    Scene->SetStringField(TEXT("cameraTag"), TEXT("HCZSBattleCamera"));
    Scene->SetBoolField(TEXT("cameraReady"), Target && Target->ActorHasTag(TEXT("HCZSBattleCamera")));
    FVector2D PlayerPoint = FVector2D::ZeroVector, EnemyPoint = FVector2D::ZeroVector;
    bool bPlayerProjected = false, bEnemyProjected = false;
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        const bool bPlayer = It->ActorHasTag(TEXT("HCZSBattlePlayer"));
        const bool bEnemy = It->ActorHasTag(TEXT("HCZSBattleEnemy"));
        if (!bPlayer && !bEnemy) continue;
        const auto* Component = It->FindComponentByClass<USkeletalMeshComponent>();
        const FString Prefix = bPlayer ? TEXT("player") : TEXT("enemy");
        Scene->SetStringField(Prefix + TEXT("Mesh"), Component && Component->GetSkeletalMeshAsset()
            ? Component->GetSkeletalMeshAsset()->GetPathName() : FString());
        Scene->SetBoolField(Prefix + TEXT("Visible"), !It->IsHidden() && Component && Component->IsVisible() && !Component->bHiddenInGame);
        if (Component && Controller)
        {
            FVector2D Point = FVector2D::ZeroVector;
            const bool Projected = Controller->ProjectWorldLocationToScreen(Component->Bounds.Origin, Point, true);
            Scene->SetNumberField(Prefix + TEXT("ScreenX"), Point.X);
            if (bPlayer) { PlayerPoint = Point; bPlayerProjected = Projected; }
            else { EnemyPoint = Point; bEnemyProjected = Projected; }
            if (auto* Anim = Component->GetSingleNodeInstance())
                if (const auto* Asset = Anim->GetCurrentAsset()) Scene->SetStringField(Prefix + TEXT("CurrentAnimation"), Asset->GetPathName());
        }
    }
    Scene->SetBoolField(TEXT("playerLeftEnemyRight"), bPlayerProjected && bEnemyProjected && PlayerPoint.X < EnemyPoint.X);
    Scene->SetBoolField(TEXT("playerProjected"), bPlayerProjected);
    Scene->SetBoolField(TEXT("enemyProjected"), bEnemyProjected);
    return Scene;
}

bool UHczsUIFlowTestSubsystem::StableBattle() const
{
    if (!Session || !Session->IsBattleSceneReady() || Session->CurrentBattle.PlayerId != TEXT("1")
        || Session->CurrentBattle.EnemyId != TEXT("991") || !GetGameInstance()->GetWorld()->GetMapName().EndsWith(TEXT("L_TutorialBattle"))) return false;
    const auto Paint = ReadPaint(), Scene = SceneProjection();
    return Paint && TrueField(Paint, TEXT("battleScene")) && TrueField(Paint, TEXT("visible"))
        && !TrueField(Paint, TEXT("presentationBusy")) && TrueField(Scene, TEXT("ready"))
        && TrueField(Scene, TEXT("canPresentBattle")) && TrueField(Scene, TEXT("cameraReady"))
        && TrueField(Scene, TEXT("playerLeftEnemyRight"));
}

bool UHczsUIFlowTestSubsystem::StableHall() const
{
    return Session && Session->IsHallSceneReady() && GetGameInstance()->GetWorld()
        && GetGameInstance()->GetWorld()->GetMapName().EndsWith(TEXT("L_ElsaHallFxPreview")) && FindHallWidget() && !FindWorldlineWidget();
}

bool UHczsUIFlowTestSubsystem::StableWorldline() const
{
    if (!Session || !Session->IsHallSceneReady() || Session->Phase != EHczsSessionPhase::Hall) return false;
    const auto Paint = ReadPaint(EHczsUITestSurface::Worldline);
    const TArray<TSharedPtr<FJsonValue>>* Sprites = nullptr;
    const TArray<TSharedPtr<FJsonValue>>* Texts = nullptr;
    if (!Paint || !TrueField(Paint, TEXT("visible")) || !TrueField(Paint, TEXT("sourceReady"))
        || !TrueField(Paint, TEXT("sourceChineseFont")) || !TrueField(Paint, TEXT("originalSourcePage"))
        || TrueField(Paint, TEXT("pending")) || TrueField(Paint, TEXT("readOnlySourceInspection"))
        || TrueField(Paint, TEXT("progressAvailable")) || !NumberIs(Paint, TEXT("chapterInstances"), 0)
        || !StringIs(Paint, TEXT("sourceLayoutSha256"), TEXT("8afc937db8a3cc13ddde0bc771995734895b590828b70454444d7b9e282007ef"))
        || !Paint->TryGetArrayField(TEXT("actualPaintedSprites"), Sprites) || Sprites->Num() != 12
        || !Paint->TryGetArrayField(TEXT("renderedTexts"), Texts)) return false;
    return Texts->ContainsByPredicate([](const TSharedPtr<FJsonValue>& Value) { return Value->AsString() == TEXT("世界线"); });
}

bool UHczsUIFlowTestSubsystem::QueueScreenshot(const FString& Stage, EHczsUITestSurface Surface)
{
    if (PendingScreenshot || !GetGameInstance()->GetWorld()) return false;
    auto* Client = GetGameInstance()->GetWorld()->GetGameViewport();
    if (!Client || !Client->Viewport) return false;
    const auto Window = Client->GetWindow();
    const FIntPoint Size = Client->Viewport->GetSizeXY();
    const FTextureRHIRef Texture = Client->Viewport->GetRenderTargetTexture();
    if (!Window || Window->IsWindowMinimized() || Size.X < 1280 || Size.Y < 720
        || Client->Viewport->GetRenderTargetTextureSizeXY() != Size
        || (Texture.IsValid() && Texture->GetDesc().Extent != Size)) return false;
    const auto Paint = ReadPaint(Surface);
    if (!Paint) return false;
    auto Shot = MakeShared<FJsonObject>();
    Shot->SetStringField(TEXT("stage"), Stage);
    Shot->SetStringField(TEXT("path"), FPaths::Combine(FPaths::GetPath(ReportPath),
        (bResume ? TEXT("resume-") : TEXT("initial-")) + Stage + TEXT(".png")));
    Shot->SetStringField(TEXT("worldMap"), GetGameInstance()->GetWorld()->GetMapName());
    Shot->SetStringField(TEXT("surface"), Surface == EHczsUITestSurface::Worldline ? TEXT("worldline") : Surface == EHczsUITestSurface::Hall ? TEXT("hall") : TEXT("session"));
    Shot->SetNumberField(TEXT("actionCount"), Actions.Num());
    Shot->SetStringField(TEXT("playerId"), Session->CurrentBattle.PlayerId);
    Shot->SetStringField(TEXT("enemyId"), Session->CurrentBattle.EnemyId);
    Shot->SetObjectField(TEXT("paint"), Paint);
    Shot->SetObjectField(TEXT("scene"), SceneProjection());
    PendingScreenshot = Shot;
    PendingSurface = Surface;
    ScreenshotDeadline = FPlatformTime::Seconds() + 15.0;
    UGameViewportClient::OnScreenshotCaptured().AddUObject(this, &UHczsUIFlowTestSubsystem::ScreenshotCaptured);
    FScreenshotRequest::RequestScreenshot(Shot->GetStringField(TEXT("path")), true, false);
    return true;
}

void UHczsUIFlowTestSubsystem::ScreenshotCaptured(int32 Width, int32 Height, const TArray<FColor>& Pixels)
{
    UGameViewportClient::OnScreenshotCaptured().RemoveAll(this);
    if (!PendingScreenshot || bFinished) return;
    TArray64<uint8> Png;
    FImageUtils::PNGCompressImageArray(Width, Height, TArrayView64<const FColor>(Pixels.GetData(), Pixels.Num()), Png);
    const FString Path = PendingScreenshot->GetStringField(TEXT("path"));
    if (!FFileHelper::SaveArrayToFile(Png, *Path)) { PendingScreenshot.Reset(); Fail(TEXT("Cannot save native UI screenshot")); return; }
    PendingScreenshot->SetNumberField(TEXT("width"), Width); PendingScreenshot->SetNumberField(TEXT("height"), Height);
    PendingScreenshot->SetBoolField(TEXT("nativeSlateViewportPixels"), true);
    // Use the actual paint observed in the capture's frame, not a pre-request
    // loaded-assets list. In particular disabled/active icon states can change.
    if (!GetGameInstance()->GetWorld() || !StringIs(PendingScreenshot, TEXT("worldMap"), GetGameInstance()->GetWorld()->GetMapName()))
    { PendingScreenshot.Reset(); Fail(TEXT("Map changed before the native screenshot frame")); return; }
    const auto Paint = ReadPaint(PendingSurface);
    if (!Paint) { PendingScreenshot.Reset(); Fail(TEXT("The intended UI surface was absent in the native screenshot frame")); return; }
    PendingScreenshot->SetObjectField(TEXT("paint"), Paint);
    PendingScreenshot->SetNumberField(TEXT("actionCount"), Actions.Num());
    PendingScreenshot->SetObjectField(TEXT("scene"), SceneProjection());
    Screenshots.Add(MakeShared<FJsonValueObject>(PendingScreenshot));
    UE_LOG(LogTemp, Display, TEXT("HCZS UI screenshot saved: stage=%s size=%dx%d map=%s"),
        *PendingScreenshot->GetStringField(TEXT("stage")), Width, Height,
        *GetGameInstance()->GetWorld()->GetMapName());
    PendingScreenshot.Reset();
}

bool UHczsUIFlowTestSubsystem::SaveCheckpoint()
{
    auto Object = MakeShared<FJsonObject>();
    Object->SetNumberField(TEXT("schemaVersion"), 1); Object->SetStringField(TEXT("mode"), TEXT("ue-slate-ui-checkpoint"));
    Object->SetNumberField(TEXT("port"), Port); Object->SetStringField(TEXT("profileId"), ProfileId);
    Object->SetStringField(TEXT("battleId"), BattleId); Object->SetObjectField(TEXT("battle"), SavedBattle);
    Object->SetStringField(TEXT("initialRunId"), RunId);
    Object->SetNumberField(TEXT("initialUEProcessId"), FPlatformProcess::GetCurrentProcessId());
    return SaveJson(CheckpointPath, Object);
}

bool UHczsUIFlowTestSubsystem::CheckResumeBattle() const
{
    return SavedBattle && JsonEqual(MakeShared<FJsonValueObject>(SavedBattle), MakeShared<FJsonValueObject>(BattleProjection()));
}

bool UHczsUIFlowTestSubsystem::SaveReport(bool bPassed, const FString& Failure)
{
    auto Object = MakeShared<FJsonObject>();
    Object->SetNumberField(TEXT("schemaVersion"), 1); Object->SetStringField(TEXT("mode"), TEXT("ue-slate-ui-flow"));
    Object->SetStringField(TEXT("runKind"), bResume ? TEXT("resume") : TEXT("initial"));
    Object->SetStringField(TEXT("runId"), RunId);
    Object->SetNumberField(TEXT("ueProcessId"), FPlatformProcess::GetCurrentProcessId());
    const FDateTime Finished = FDateTime::UtcNow();
    Object->SetStringField(TEXT("startedAtUtc"), StartedAtUtc);
    Object->SetStringField(TEXT("finishedAtUtc"), Finished.ToIso8601());
    Object->SetNumberField(TEXT("startedAtUnixMs"), static_cast<double>(StartedAtUnixMs));
    Object->SetNumberField(TEXT("finishedAtUnixMs"), static_cast<double>(Finished.ToUnixTimestamp() * 1000 + Finished.GetMillisecond()));
    Object->SetBoolField(TEXT("passed"), bPassed); Object->SetStringField(TEXT("failure"), Failure);
    Object->SetNumberField(TEXT("step"), Step); Object->SetNumberField(TEXT("port"), Port);
    Object->SetStringField(TEXT("profileId"), ProfileId); Object->SetStringField(TEXT("battleId"), BattleId);
    Object->SetArrayField(TEXT("actions"), Actions); Object->SetArrayField(TEXT("screenshots"), Screenshots);
    if (ResumeObserved) Object->SetObjectField(TEXT("checkpointObserved"), ResumeObserved);
    if (Session && Session->CurrentBattle.bIsValid) Object->SetObjectField(TEXT("finalBattle"), BattleProjection());
    if (!bPassed)
    {
        auto Diagnostic = MakeShared<FJsonObject>();
        if (Session)
        {
            Diagnostic->SetNumberField(TEXT("phase"), static_cast<int32>(Session->Phase));
            Diagnostic->SetBoolField(TEXT("requestInFlight"), Session->bRequestInFlight);
            Diagnostic->SetBoolField(TEXT("pendingIntent"), Session->bHasPendingIntent);
            Diagnostic->SetStringField(TEXT("errorCode"), Session->ErrorCode);
        }
        if (const auto Paint = ReadPaint()) Diagnostic->SetObjectField(TEXT("sessionPaint"), Paint);
        if (const auto Paint = ReadPaint(EHczsUITestSurface::Hall)) Diagnostic->SetObjectField(TEXT("hallPaint"), Paint);
        if (const auto Paint = ReadPaint(EHczsUITestSurface::Worldline)) Diagnostic->SetObjectField(TEXT("worldlinePaint"), Paint);
        Object->SetObjectField(TEXT("failureDiagnostic"), Diagnostic);
    }
    Object->SetStringField(TEXT("checkpointPath"), bResume ? ResumePath : CheckpointPath);
    Object->SetStringField(TEXT("verificationScope"), TEXT("Real Slate hit paths, original-resource UE scene, real HTTP state; independent wire/Mongo readback and human image inspection are separate gates."));
    return SaveJson(ReportPath, Object);
}

void UHczsUIFlowTestSubsystem::RequestQuit()
{
    bFinished = true;
    UGameViewportClient::OnScreenshotCaptured().RemoveAll(this);
    FPlatformMisc::RequestExit(false);
}

bool UHczsUIFlowTestSubsystem::Fail(const FString& Reason)
{
    UE_LOG(LogTemp, Error, TEXT("HCZS UI acceptance failed: step=%d reason=%s"), Step, *Reason);
    SaveReport(false, Reason); RequestQuit(); return false;
}

bool UHczsUIFlowTestSubsystem::TickFlow(float DeltaTime)
{
    if (bFinished) return false;
    if (!Session || FPlatformTime::Seconds() >= Deadline) return Fail(TEXT("UI flow timed out without claiming success"));
    if (PendingScreenshot)
    {
        if (FPlatformTime::Seconds() >= ScreenshotDeadline) return Fail(TEXT("Native screenshot request timed out"));
        return true;
    }
    // Every down/move/frame/up is driven on a separate ticker turn. Gameplay
    // steps cannot advance while the physical gesture or its screenshot is held.
    if (PendingDrag) return AdvanceDrag();
    if (!Session->ErrorCode.IsEmpty() && !Session->bRequestInFlight)
        return Fail(TEXT("Unexpected service error in isolated UI flow: ") + Session->ErrorCode);
    if (Session->bRequestInFlight || Session->bHasPendingIntent) return true;
    if (!bResume)
    {
        switch (Step)
        {
        case 0:
            if (!Session->bLocalServiceAvailable || Session->Phase != EHczsSessionPhase::ProfileSelection) return true;
            if (!Session->Profiles.IsEmpty() || !Session->SelectedProfileId.IsEmpty()) return Fail(TEXT("Refusing creation in a nonempty or preselected service"));
            if (Click(TEXT("confirm-new-profile"), TEXT(""), false)) Step = 1;
            return true;
        case 1:
            if (Click(TEXT("create-profile"), TEXT(""), false)) Step = 2;
            return true;
        case 2:
            if (!StableHall()) return true;
            ProfileId = Session->SelectedProfileId;
            if (!HczsSessionContract::IsUuid(ProfileId)) return Fail(TEXT("UI-created profile has no canonical identity"));
            if (QueueScreenshot(TEXT("hall-created"), EHczsUITestSurface::Hall)) Step = 3;
            return true;
        case 3:
            if (Click(TEXT("worldline"), TEXT(""), true, EHczsUITestSurface::Hall)) Step = 4;
            return true;
        case 4:
            if (!StableWorldline()) return true;
            if (QueueScreenshot(TEXT("worldline-first"), EHczsUITestSurface::Worldline)) Step = 5;
            return true;
        case 5:
            if (Click(TEXT("local-battle-preview"), TEXT(""), false, EHczsUITestSurface::Worldline)) Step = 6;
            return true;
        case 6:
            if (Click(TEXT("select-encounter"), TEXT("tutorial-5000"), false)) Step = 7;
            return true;
        case 7:
            if (!Session->bEncounterScenarioReady) return true;
            if (Click(TEXT("new-battle"), TEXT(""), false)) Step = 8;
            return true;
        case 8:
            if (!StableBattle()) return true;
            BattleId = Session->CurrentBattle.Id;
            if (!HczsSessionContract::IsUuid(BattleId)) return Fail(TEXT("UI-created battle identity invalid"));
            if (QueueScreenshot(TEXT("battle-created"))) Step = 9;
            return true;
        case 9:
            if (!StableBattle()) return true;
            if (!RunCancellationProbes()) return !bFinished;
            for (const auto& Card : Session->CurrentBattle.Hand)
                if (Card.Cost <= Session->CurrentBattle.Energy
                    && BeginDrag(TEXT("play-card"), Card.InstanceId, TEXT("enemy"), false, TEXT("card-drag-preview")))
                {
                    Step = 10; return true;
                }
            return true;
        case 10:
            if (!StableBattle()) return true;
            if (Session->CurrentBattle.Revision != BeforeRevision + 1) return Fail(TEXT("Mouse card drag was not persisted once"));
            if (Click(TEXT("end-turn"), TEXT(""), true)) { Step = 11; QueueScreenshot(TEXT("turn-submitted")); }
            return true;
        case 11:
            if (!StableBattle()) return true;
            if (Session->CurrentBattle.Revision != BeforeRevision + 1 || Session->CurrentBattle.Round != 2)
                return Fail(TEXT("Touch turn click was not persisted once into round two"));
            SavedBattle = BattleProjection();
            if (QueueScreenshot(TEXT("battle-checkpoint"))) Step = 12;
            return true;
        case 12:
            if (Click(TEXT("hall"), TEXT(""), false)) Step = 13;
            return true;
        case 13:
            if (!StableHall()) return true;
            if (QueueScreenshot(TEXT("hall-checkpoint"), EHczsUITestSurface::Hall)) Step = 14;
            return true;
        case 14:
            if (!SaveCheckpoint() || !SaveReport(true)) return Fail(TEXT("Cannot save initial UI checkpoint/report"));
            UE_LOG(LogTemp, Display, TEXT("HCZS UI initial acceptance passed; checkpoint saved"));
            RequestQuit(); return false;
        default: return Fail(TEXT("Unknown initial UI flow step"));
        }
    }
    switch (Step)
    {
    case 0:
        if (!Session->bLocalServiceAvailable || Session->Phase != EHczsSessionPhase::ProfileSelection) return true;
        if (!Session->SelectedProfileId.IsEmpty()) return Fail(TEXT("Resume started with an implicit selected profile"));
        if (!Session->Profiles.ContainsByPredicate([this](const FHczsLocalProfile& P) { return P.Id == ProfileId; }))
            return Fail(TEXT("Checkpoint profile is absent from the server"));
        if (Click(TEXT("select-profile"), ProfileId, false)) Step = 1;
        return true;
    case 1:
        if (!StableHall()) return true;
        if (Session->SelectedProfileId != ProfileId) return Fail(TEXT("Explicit profile click selected another profile"));
        if (QueueScreenshot(TEXT("hall-resume"), EHczsUITestSurface::Hall)) Step = 2;
        return true;
    case 2:
        if (Click(TEXT("worldline"), TEXT(""), true, EHczsUITestSurface::Hall)) Step = 3;
        return true;
    case 3:
        if (!StableWorldline()) return true;
        if (QueueScreenshot(TEXT("worldline-resume"), EHczsUITestSurface::Worldline)) Step = 4;
        return true;
    case 4:
        if (Click(TEXT("local-battle-preview"), TEXT(""), true, EHczsUITestSurface::Worldline)) Step = 5;
        return true;
    case 5:
        if (Click(TEXT("continue-battle"), BattleId, false)) Step = 6;
        return true;
    case 6:
        if (!StableBattle()) return true;
        if (!CheckResumeBattle()) return Fail(TEXT("Reopened game UI differs from exact persisted checkpoint"));
        ResumeObserved = BattleProjection();
        if (QueueScreenshot(TEXT("battle-restored"))) Step = 7;
        return true;
    case 7:
        if (!StableBattle()) return true;
        if (bAwaitingAction)
        {
            if (Session->CurrentBattle.Revision != BeforeRevision + 1) return Fail(TEXT("Shield-probe touch command did not persist exactly once"));
            bAwaitingAction = false;
        }
        if (Session->CurrentBattle.Round >= 4)
        {
            if (Session->CurrentBattle.EnemyShield.Approximate <= 0) return Fail(TEXT("The real source 992 turn did not yield a shield HUD state"));
            if (QueueScreenshot(TEXT("shield-confirmed"))) Step = 8;
            return true;
        }
        if (Session->CurrentBattle.Status != TEXT("player-turn") || ResumeTurnProbes >= 3)
            return Fail(TEXT("Cannot reach real shield icon state through source turns"));
        if (Click(TEXT("end-turn"), TEXT(""), true)) { ++ResumeTurnProbes; bAwaitingAction = true; }
        return true;
    case 8:
        if (!StableBattle()) return true;
        if (bAwaitingAction)
        {
            if (Session->CurrentBattle.Revision != BeforeRevision + 1) return Fail(TEXT("UI combat command did not persist exactly once"));
            bAwaitingAction = false;
        }
        if (Session->CurrentBattle.Status != TEXT("player-turn"))
        {
            if (Session->CurrentBattle.Status != TEXT("won") && Session->CurrentBattle.Status != TEXT("lost"))
                return Fail(TEXT("Unknown battle terminal state"));
            if (QueueScreenshot(TEXT("battle-terminal"))) Step = 9;
            return true;
        }
        if (++GameplayCommands > 100) return Fail(TEXT("UI battle command budget exhausted without terminal state"));
        for (const auto& Card : Session->CurrentBattle.Hand)
        {
            if (Card.Cost > Session->CurrentBattle.Energy) continue;
            if (BeginDrag(TEXT("play-card"), Card.InstanceId, TEXT("enemy"), !bCapturedResumePlay,
                !bCapturedResumePlay ? TEXT("resumed-card-drag-preview") : FString()))
            {
                bAwaitingAction = true;
                bCapturedResumePlay = true;
                return true;
            }
            --GameplayCommands; return true;
        }
        if (Click(TEXT("end-turn"), TEXT(""), true)) bAwaitingAction = true;
        else --GameplayCommands;
        return true;
    case 9:
        if (Click(TEXT("hall"), TEXT(""), false)) Step = 10;
        return true;
    case 10:
        if (!StableHall()) return true;
        if (QueueScreenshot(TEXT("hall-terminal"), EHczsUITestSurface::Hall)) Step = 11;
        return true;
    case 11:
        if (!SaveReport(true)) return Fail(TEXT("Cannot save final UI acceptance report"));
        UE_LOG(LogTemp, Display, TEXT("HCZS UI resume acceptance passed; terminal=%s"), *Session->CurrentBattle.Status);
        RequestQuit(); return false;
    default: return Fail(TEXT("Unknown resumed UI flow step"));
    }
}
