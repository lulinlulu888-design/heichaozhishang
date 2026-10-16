#include "HczsSessionMode.h"
#include "HczsGameInstance.h"
#include "HczsSessionWidget.h"
#include "HczsBattlePresentation.h"
#include "HczsBattleCamera.h"
#include "Camera/CameraActor.h"
#include "Engine/GameViewportClient.h"
#include "UnrealClient.h"
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
const TCHAR* TutorialMap = TEXT("/Game/Recovered/Battle/Maps/L_TutorialSource2133");
const TCHAR* CityMap = TEXT("/Game/Recovered/City/Maps/L_City2077Preview");
const TCHAR* HallMap = TEXT("/Game/Recovered/Hall/Maps/L_ElsaHallFxPreview");

bool Identity(const UHczsGameInstance* Session, const TCHAR* Encounter, const TCHAR* Enemy, const TCHAR* DefinitionPrefix)
{
    return Session && Session->CurrentBattle.PlayerId == TEXT("1") && Session->CurrentBattle.EnemyId == Enemy &&
        (Session->CurrentBattle.EncounterId == Encounter ||
         (Session->CurrentBattle.EncounterId.IsEmpty() && Session->CurrentBattle.DefinitionId.StartsWith(DefinitionPrefix)));
}

const TCHAR* RecoveredBattleMap(const UHczsGameInstance* Session)
{
    // 3997/5000 stays on the prologue scene and keeps ultimates disabled.
    // 10405 is the recovered local preview whose source gate allows Elsa's ultimate.
    if (Identity(Session, TEXT("city-preview-10405"), TEXT("6605"), TEXT("city-preview-10405-"))) return CityMap;
    if (Identity(Session, TEXT("tutorial-5000"), TEXT("991"), TEXT("tutorial-5000-"))) return TutorialMap;
    return nullptr;
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
    if (bBattleScene && Presentation && Session->IsBattleSceneReady() && RecoveredBattleMap(Session))
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
        const TCHAR* Map = RecoveredBattleMap(Session);
        if (!Map) Problem = TEXT("这场战斗的角色场景尚未恢复，可以返回大厅继续其他关卡。");
        else if (!FPackageName::DoesPackageExist(Map)) Problem = TEXT("这场战斗的原场景尚未载入，请返回大厅。");
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
    if (!bBattleScene && Session->IsBattleSceneReady())
        if (const TCHAR* Map = RecoveredBattleMap(Session)) Desired = Map;
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

void AHczsBattleMode::BeginPlay()
{
    Super::BeginPlay();
    ViewportResizedHandle = FViewport::ViewportResizedEvent.AddUObject(this, &AHczsBattleMode::ViewportResized);
    ApplySourceProjection();
    GetWorldTimerManager().SetTimerForNextTick(this, &AHczsBattleMode::ApplySourceProjection);
}

void AHczsBattleMode::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    FViewport::ViewportResizedEvent.Remove(ViewportResizedHandle);
    Super::EndPlay(EndPlayReason);
}

void AHczsBattleMode::ViewportResized(FViewport* Viewport, uint32)
{
    const UGameViewportClient* Client = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
    if (Client && Viewport == Client->Viewport) ApplySourceProjection();
}

void AHczsBattleMode::ApplySourceProjection()
{
    const UGameViewportClient* Client = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
    if (!Client || !Client->Viewport) return;
    for (TActorIterator<ACameraActor> It(GetWorld()); It; ++It)
        if (It->ActorHasTag(SceneCameraTag()))
        {
            HczsBattleCamera::Apply(*It, Client->Viewport->GetSizeXY());
            break;
        }
}
