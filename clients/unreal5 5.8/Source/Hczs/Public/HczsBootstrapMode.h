#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/HUD.h"
#include "GameFramework/PlayerController.h"
#include "TimerManager.h"
#include "HczsSessionMode.h"
#include "HczsBootstrapMode.generated.h"

class UHczsHallWidget;

UCLASS()
class HCZS_API AHczsBootstrapMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    AHczsBootstrapMode();
    virtual void BeginPlay() override;
};

UCLASS()
class HCZS_API AHczsBootstrapController : public APlayerController
{
    GENERATED_BODY()
protected:
    virtual void SetupInputComponent() override;
    void RefreshStatus();
};

UCLASS()
class HCZS_API AHczsBootstrapHUD : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
};

/** Inspection of recovered APK assets without the bootstrap debugging HUD. */
UCLASS()
class HCZS_API AHczsRecoveredHallMode : public AHczsSessionMode
{
    GENERATED_BODY()
public:
    AHczsRecoveredHallMode();
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
private:
    FTimerHandle InspectionCaptureTimer;
    UPROPERTY() TObjectPtr<UHczsHallWidget> HallWidget;
};
