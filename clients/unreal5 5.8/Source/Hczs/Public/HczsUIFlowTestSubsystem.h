#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Containers/Ticker.h"
#include "HczsUIFlowTestSubsystem.generated.h"

class UHczsGameInstance;
class UHczsSessionWidget;
class UHczsHallWidget;
class UHczsWorldlineWidget;
class FJsonObject;
class FJsonValue;
enum class EHczsUITestSurface : uint8 { Session, Hall, Worldline };

/** Explicit nonshipping, isolated acceptance driver; uses real Slate pointer paths. */
UCLASS()
class HCZS_API UHczsUIFlowTestSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()
public:
    virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;
private:
    bool TickFlow(float DeltaTime);
    UHczsSessionWidget* FindSessionWidget() const;
    UHczsHallWidget* FindHallWidget() const;
    UHczsWorldlineWidget* FindWorldlineWidget() const;
    TSharedPtr<FJsonObject> ReadPaint(EHczsUITestSurface Surface = EHczsUITestSurface::Session) const;
    bool Click(const FString& Action, const FString& Value, bool bTouch, EHczsUITestSurface Surface = EHczsUITestSurface::Session);
    bool BeginDrag(const FString& Action, const FString& InstanceId, const FString& Target, bool bTouch, const FString& PreviewStage = FString());
    bool AdvanceDrag();
    bool RunCancellationProbes();
    TSharedPtr<FJsonObject> BattleProjection() const;
    TSharedPtr<FJsonObject> SceneProjection() const;
    bool StableBattle() const;
    bool StableHall() const;
    bool StableWorldline() const;
    bool QueueScreenshot(const FString& Stage, EHczsUITestSurface Surface = EHczsUITestSurface::Session);
    void ScreenshotCaptured(int32 Width, int32 Height, const TArray<FColor>& Pixels);
    bool SaveReport(bool bPassed, const FString& Failure = FString());
    bool SaveCheckpoint();
    bool CheckResumeBattle() const;
    bool Fail(const FString& Reason);
    void RequestQuit();
    UPROPERTY() TObjectPtr<UHczsGameInstance> Session;
    FTSTicker::FDelegateHandle TickHandle;
    TSharedPtr<FJsonObject> Checkpoint;
    TSharedPtr<FJsonObject> SavedBattle;
    TSharedPtr<FJsonObject> ResumeObserved;
    TSharedPtr<FJsonObject> PendingScreenshot;
    TSharedPtr<FJsonObject> PendingDrag, ProbeBefore, ProbeAction;
    TArray<TSharedPtr<FJsonValue>> Actions;
    TArray<TSharedPtr<FJsonValue>> Screenshots;
    FString ReportPath, CheckpointPath, ResumePath, ProfileId, BattleId;
    FString RunId, StartedAtUtc;
    FString DragTarget, DragPreviewStage;
    int32 DragStage = 0, ProbeIndex = 0, ProbeStage = 0;
    int64 ProbeStartedAtUnixMs = 0;
    int64 StartedAtUnixMs = 0;
    EHczsUITestSurface PendingSurface = EHczsUITestSurface::Session;
    int32 Port = 0, Step = 0, ResumeTurnProbes = 0, GameplayCommands = 0;
    int64 BeforeRevision = 0;
    double Deadline = 0, ScreenshotDeadline = 0;
    bool bResume = false, bFinished = false, bAwaitingAction = false, bCapturedResumePlay = false;
};
