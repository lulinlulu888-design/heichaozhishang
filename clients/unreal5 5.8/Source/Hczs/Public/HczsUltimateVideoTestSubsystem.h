#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Containers/Ticker.h"
#include "Styling/SlateBrush.h"
#include "HczsUltimateVideoTestSubsystem.generated.h"

class AActor;
class UMediaTexture;
class UHczsUltimateVideoPlayer;
class SWidget;
class FJsonObject;
class FJsonValue;
struct FHczsUltimateVideoPaintObservation;
enum class EHczsUltimateVideoFinish : uint8;

/** Opt-in, nonshipping, real decoder/Slate viewport acceptance. No game commands. */
UCLASS()
class HCZS_API UHczsUltimateVideoTestSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()
public:
    virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;
private:
    bool TickTest(float DeltaSeconds);
    void VideoReady(const FString& Sequence, UMediaTexture* Texture);
    void VideoStarted(const FString& Sequence);
    void VideoFinished(const FString& Sequence, EHczsUltimateVideoFinish Result, const FString& Message);
    bool MountVideo();
    void CaptureFrame();
    void ScreenshotCaptured(int32 Width, int32 Height, const TArray<FColor>& Pixels);
    void FinishTest(bool bPassed, const FString& Reason = FString());
    void Cleanup();
    bool SaveReport(bool bPassed, const FString& Reason);
    void RecordEvent(const TCHAR* Kind, const FString& Sequence);

    UPROPERTY(Transient) TObjectPtr<AActor> TestActor;
    UPROPERTY(Transient) TObjectPtr<UHczsUltimateVideoPlayer> Video;
    UPROPERTY(Transient) TObjectPtr<UMediaTexture> DisplayTexture;
    FTSTicker::FDelegateHandle TickHandle;
    FDelegateHandle ScreenshotHandle;
    TSharedPtr<SWidget> Overlay;
    TSharedPtr<FHczsUltimateVideoPaintObservation> Paint;
    TSharedPtr<FJsonObject> Screenshot;
    TArray<TSharedPtr<FJsonValue>> Events;
    FSlateBrush VideoBrush, BlackBrush;
    FString ReportPath, ScreenshotPath, SequenceId, StartedAtUtc, Failure, MapName, Decoder;
    int64 StartedAtUnixMs = 0;
    int32 Step = 0, ReadyCount = 0, StartedCount = 0, FinishedCount = 0;
    double Deadline = 0.0, ScreenshotDeadline = 0.0, TerminalAt = 0.0, SettleUntil = 0.0;
    double DurationSeconds = 0.0, RequestedFrameSeconds = 0.0;
    double WorldTimeAtStart = 0.0, WorldTimeAtFinish = 0.0;
    bool bPausedDuringVideo = false, bResumedAfterVideo = false;
    bool bPrepausedCase = false, bCancelCase = false, bCancelIssued = false, bTerminalExpected = false;
    uint64 RequestedPaintSerial = 0;
    bool bInitialized = false, bFinished = false, bAwaitingScreenshot = false, bScreenshotValid = false;
    bool bTerminalCompleted = false, bDuplicatePrepareAccepted = false, bDuplicatePlayAccepted = false;
    bool bRetiredSequenceRejected = false, bRetiredPlayRejected = false, bNoBusinessServer = false;
};
