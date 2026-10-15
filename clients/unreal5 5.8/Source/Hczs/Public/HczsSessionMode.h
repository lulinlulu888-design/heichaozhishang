#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "HczsSessionMode.generated.h"

class UHczsGameInstance;
class UHczsSessionWidget;
class AHczsBattlePresentation;

/** Keeps the explicit local session across real hall/battle world travel. */
UCLASS()
class HCZS_API AHczsSessionMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    AHczsSessionMode();
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
protected:
    UPROPERTY() TObjectPtr<UHczsGameInstance> Session;
    UPROPERTY() TObjectPtr<UHczsSessionWidget> SessionWidget;
    bool bBattleScene = false;
    virtual FName SceneCameraTag() const;
    void SessionChanged();
    void SyncPresentation();
private:
    void ApplySceneCamera();
    void TravelWhenReady();
    void PresentationChanged();
    FDelegateHandle SessionChangedHandle;
    FDelegateHandle PresentationChangedHandle;
    UPROPERTY() TObjectPtr<AHczsBattlePresentation> Presentation;
    bool bTravelScheduled = false;
};

/** Gameplay mode for original-resource first-battle staging. */
UCLASS()
class HCZS_API AHczsBattleMode : public AHczsSessionMode
{
    GENERATED_BODY()
public:
    AHczsBattleMode();
protected:
    virtual FName SceneCameraTag() const override;
};
