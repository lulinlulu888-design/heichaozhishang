#pragma once
#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Containers/Ticker.h"
#include "HczsSessionTypes.h"
#include "HczsUltimateSequenceTestSubsystem.generated.h"
class UHczsUltimateSequence;
class USkeletalMeshComponent;
class FJsonObject;
class UAnimationAsset;
class AHczsBattlePresentation;
UCLASS()
class HCZS_API UHczsUltimateSequenceTestSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()
public:
    virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;
private:
    bool TickTest(float Delta);
    bool PrepareHttpBattle();
    void Cue(const FString& Id, const FString& Name, float Position);
    void Ended(const FString& Id, bool Success, const FString& Error);
    void Capture(const FString& Name);
    void Captured(int32 Width, int32 Height, const TArray<FColor>& Pixels);
    void Finish(bool Success, const FString& Error);
    UPROPERTY() TObjectPtr<UHczsUltimateSequence> Sequence;
    UPROPERTY() TObjectPtr<USkeletalMeshComponent> Mesh;
    UPROPERTY() TObjectPtr<UAnimationAsset> PriorAnimation;
    UPROPERTY() TObjectPtr<AHczsBattlePresentation> Presentation;
    FHczsBattleView TestView;
    FHczsBattleVisualReceipt TestReceipt;
    double ReceiptDue = 0;
    bool bPendingReceipt = false, bLocalIntentFixture = false;
    bool bHttpTest = false, bHttpConfirmed = false, bImmediateHttpStart = false;
    int32 HttpStep = 0, HttpActions = 0;
    FString UltimateInstance;
    FTSTicker::FDelegateHandle Ticker;
    FDelegateHandle ScreenshotHandle;
    FString Report, ScreenshotPath, Failure;
    FString InterruptMode;
    TArray<TSharedPtr<FJsonValue>> Events, Screenshots;
    double Deadline = 0;
    float VideoPosition = -1, ResumePosition = -1;
    int32 Stage = 0, AttackCount = 0;
    int32 FinishCount = 0;
    bool bInterrupting = false, bCleanupVerified = false;
    bool bDone = false, bSequenceDone = false, bAwaitingScreenshot = false, bPauseVerified = true;
};
