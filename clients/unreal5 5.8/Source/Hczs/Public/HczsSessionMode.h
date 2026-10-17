#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "HczsSessionMode.generated.h"

class UHczsGameInstance;
class UHczsSessionWidget;
class UHczsDungeonWidget;
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
    bool bDungeonScene = false;
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
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
protected:
    virtual FName SceneCameraTag() const override;
private:
    void ApplySourceProjection();
    void ViewportResized(FViewport* Viewport, uint32 Unused);
    FDelegateHandle ViewportResizedHandle;
};

/** Recovered chess map 239. Vertical FOV stays at the source dungeon camera's 30 degrees. */
UCLASS()
class HCZS_API AHczsDungeonMode : public AHczsSessionMode
{
    GENERATED_BODY()
public:
    AHczsDungeonMode();
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
protected:
    virtual FName SceneCameraTag() const override;
private:
    void ApplySourceProjection();
    void ViewportResized(FViewport* Viewport, uint32 Unused);
    void Leave();
    void Explore();
    void ExploreState();
    UPROPERTY() TObjectPtr<UHczsDungeonWidget> DungeonWidget;
    FDelegateHandle ViewportResizedHandle;
    FDelegateHandle ExploreHandle;
    bool bWaitingExplore = false;
    FString ExploreEncounter;
};
