#include "HczsSessionMode.h"
#include "HczsGameInstance.h"
#include "HczsSessionWidget.h"
#include "HczsBattlePresentation.h"
#include "Camera/CameraActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/PackageName.h"
#include "TimerManager.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

namespace
{
const TCHAR* BattleMap = TEXT("/Game/Recovered/Battle/Maps/L_TutorialSource2133");
const TCHAR* HallMap = TEXT("/Game/Recovered/Hall/Maps/L_ElsaHallFxPreview");

bool SupportedBattle(const UHczsGameInstance* Session)
{
    return Session && Session->CurrentBattle.PlayerId == TEXT("1") && Session->CurrentBattle.EnemyId == TEXT("991") &&
        (Session->CurrentBattle.EncounterId == TEXT("tutorial-5000") ||
         (Session->CurrentBattle.EncounterId.IsEmpty() && Session->CurrentBattle.DefinitionId.StartsWith(TEXT("tutorial-5000-"))));
}
}

AHczsSessionMode::AHczsSessionMode()
{
    DefaultPawnClass = nullptr;
    HUDClass = nullptr;
}

void AHczsSessionMode::BeginPlay()
{
    Super::BeginPlay();
    Session = Cast<UHczsGameInstance>(GetGameInstance());
    if (APlayerController* Controller = GetWorld()->GetFirstPlayerController())
    {
        SessionWidget = CreateWidget<UHczsSessionWidget>(Controller);
        if (SessionWidget)
        {
            SessionWidget->SetBattleScene(bBattleScene);
            SessionWidget->AddToViewport(50);
            FInputModeGameAndUI Input;
            Input.SetWidgetToFocus(SessionWidget->TakeWidget());
            Input.SetHideCursorDuringCapture(false);
            Input.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
            Controller->SetInputMode(Input);
        }
        Controller->bShowMouseCursor = true;
    }
    ApplySceneCamera();
    if (bBattleScene)
    {
        for (TActorIterator<AHczsBattlePresentation> It(GetWorld()); It; ++It)
        {
            if (!It->ActorHasTag(TEXT("HCZSBattlePresentation"))) continue;
            Presentation = *It;
            PresentationChangedHandle = Presentation->OnPresentationChangedNative.AddUObject(this, &AHczsSessionMode::PresentationChanged);
            break;
        }
    }
    if (Session)
        SessionChangedHandle = Session->OnStateChangedNative.AddUObject(this, &AHczsSessionMode::SessionChanged);
    // Init/bootstrap belong to the GameInstance. Map loads must not choose a
    // profile, create a battle, or race its chained single-flight requests.
    SessionChanged();
    GetWorld()->GetTimerManager().SetTimerForNextTick(this, &AHczsSessionMode::SessionChanged);
}

FName AHczsSessionMode::SceneCameraTag() const { return TEXT("HCZSInspectionCamera"); }

void AHczsSessionMode::ApplySceneCamera()
{
    for (TActorIterator<ACameraActor> It(GetWorld()); It; ++It)
    {
        if (!It->ActorHasTag(SceneCameraTag())) continue;
        if (APlayerController* Controller = GetWorld()->GetFirstPlayerController()) Controller->SetViewTarget(*It);
        break;
    }
}

void AHczsSessionMode::SyncPresentation()
{
    if (!SessionWidget || !Session) return;
    if (bBattleScene && Presentation && Session->IsBattleSceneReady() && SupportedBattle(Session))
    {
        Presentation->ApplySnapshot(Session->CurrentBattle, Session->LastVisualReceipt);
    }
    PresentationChanged();
}

void AHczsSessionMode::PresentationChanged()
{
    if (!SessionWidget || !bBattleScene || !Presentation) return;
    SessionWidget->SetPresentationBusy(Presentation->IsPresentationBusy());
    if (!Presentation->IsSceneReady()) SessionWidget->SetSceneProblem(TEXT("原战斗模型或动作尚未载入，请返回大厅。"));
}

void AHczsSessionMode::SessionChanged()
{
    if (!Session || !SessionWidget) return;
    FString Problem;
    if (Session->Phase == EHczsSessionPhase::Battle && Session->CurrentBattle.bIsValid)
    {
        if (!SupportedBattle(Session)) Problem = TEXT("这场战斗的角色场景尚未恢复，可以返回大厅继续其他关卡。");
        else if (!FPackageName::DoesPackageExist(BattleMap)) Problem = TEXT("序章战斗资源尚未载入，请返回大厅。");
        else if (bBattleScene && !Presentation) Problem = TEXT("战斗演出资源尚未载入，请返回大厅。");
    }
    SessionWidget->SetSceneProblem(Problem);
    SyncPresentation();
    if (bTravelScheduled || !Problem.IsEmpty()) return;
    const bool bToBattle = !bBattleScene && Session->Phase == EHczsSessionPhase::Battle;
    const bool bToHall = bBattleScene && Session->Phase == EHczsSessionPhase::Hall;
    if (!bToBattle && !bToHall) return;
    bTravelScheduled = true;
    GetWorld()->GetTimerManager().SetTimerForNextTick(this, &AHczsSessionMode::TravelWhenReady);
}

void AHczsSessionMode::TravelWhenReady()
{
    bTravelScheduled = false;
#if !UE_BUILD_SHIPPING
    // The isolated render/HTTP harness prepares its profile in the fixed city map.
    if (FParse::Param(FCommandLine::Get(), TEXT("HczsUltimateHttpTest")) &&
        FParse::Param(FCommandLine::Get(), TEXT("HczsUltimateSequenceTest"))) return;
#endif
    if (!Session) return;
    FString Desired;
    if (!bBattleScene && Session->IsBattleSceneReady() && SupportedBattle(Session))
        Desired = BattleMap;
    else if (bBattleScene && Session->IsHallSceneReady())
        Desired = HallMap;
    if (Desired.IsEmpty() || !FPackageName::DoesPackageExist(Desired)) return;
    const FString Current = UGameplayStatics::GetCurrentLevelName(this, true);
    const FString Target = FPackageName::GetShortName(Desired);
    if (Current == Target) return;
    UE_LOG(LogTemp, Display, TEXT("HCZS: session map travel %s -> %s"), *Current, *Target);
    UGameplayStatics::OpenLevel(this, FName(*Desired));
}

void AHczsSessionMode::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    if (Session && SessionChangedHandle.IsValid()) Session->OnStateChangedNative.Remove(SessionChangedHandle);
    if (Presentation && PresentationChangedHandle.IsValid()) Presentation->OnPresentationChangedNative.Remove(PresentationChangedHandle);
    if (SessionWidget) SessionWidget->RemoveFromParent();
    GetWorld()->GetTimerManager().ClearAllTimersForObject(this);
    Super::EndPlay(EndPlayReason);
}

AHczsBattleMode::AHczsBattleMode() { bBattleScene = true; }
FName AHczsBattleMode::SceneCameraTag() const { return TEXT("HCZSBattleCamera"); }
