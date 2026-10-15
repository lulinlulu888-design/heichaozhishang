#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Containers/Ticker.h"
#include "HczsUltimateVideoPlayer.generated.h"

class UFileMediaSource;
class UMediaPlayer;
class UMediaTexture;
class UMediaSoundComponent;
class UHczsUltimateVideoPlayer;

UENUM(BlueprintType)
enum class EHczsUltimateVideoState : uint8 { Idle, Preparing, Ready, Playing, Completed, Failed, Cancelled };

UENUM(BlueprintType)
enum class EHczsUltimateVideoFinish : uint8 { Completed, Failed, Cancelled };

enum class EHczsUltimateVideoBegin : uint8 { Fresh, Idempotent, Rejected };
enum class EHczsUltimateMediaCallback : uint8 { Opened, OpenFailed, EndReached, Closed, Resumed };

/** Pure request lifecycle: late callbacks and repeated sequence ids never replay. */
struct HCZS_API FHczsUltimateVideoLifecycle
{
    FString SequenceId;
    uint64 Generation = 0;
    EHczsUltimateVideoState State = EHczsUltimateVideoState::Idle;
    bool bStartedNotified = false;
    TSet<FString> RetiredSequences;

    EHczsUltimateVideoBegin Begin(const FString& NewSequenceId);
    bool IsActive() const;
    bool IsCurrent(uint64 CallbackGeneration) const;
    bool MarkReady(uint64 CallbackGeneration);
    bool RequestPlay(const FString& ExpectedSequenceId);
    bool MarkStarted(uint64 CallbackGeneration);
    bool Finish(uint64 CallbackGeneration, EHczsUltimateVideoFinish Result);
    bool ClearActive(uint64 ExpectedGeneration);
};

DECLARE_MULTICAST_DELEGATE_TwoParams(FOnHczsUltimateVideoReady, const FString&, UMediaTexture*);
DECLARE_MULTICAST_DELEGATE_OneParam(FOnHczsUltimateVideoStarted, const FString&);
DECLARE_MULTICAST_DELEGATE_ThreeParams(FOnHczsUltimateVideoFinished, const FString&, EHczsUltimateVideoFinish, const FString&);

/** Per-open callback relay retains the exact sender/generation through async dispatch. */
UCLASS(Transient)
class HCZS_API UHczsUltimateMediaCallbacks : public UObject
{
    GENERATED_BODY()
public:
    void Initialize(UHczsUltimateVideoPlayer* InOwner, UMediaPlayer* InPlayer, uint64 InGeneration);
    UFUNCTION() void Opened(FString Url);
    UFUNCTION() void OpenFailed(FString Url);
    UFUNCTION() void EndReached();
    UFUNCTION() void Closed();
    UFUNCTION() void Resumed();
private:
    UPROPERTY(Transient) TWeakObjectPtr<UHczsUltimateVideoPlayer> Owner;
    UPROPERTY(Transient) TWeakObjectPtr<UMediaPlayer> Player;
    uint64 Generation = 0;
    void Dispatch(EHczsUltimateMediaCallback Event);
};

/** Media only: caller owns source video-cue timing and freezing/restoring actors.
 * Never pauses the world, changes a battle state, or submits a gameplay command.
 */
UCLASS(ClassGroup=(HCZS), meta=(BlueprintSpawnableComponent))
class HCZS_API UHczsUltimateVideoPlayer : public UActorComponent
{
    GENERATED_BODY()
public:
    UHczsUltimateVideoPlayer();
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
    virtual void OnComponentDestroyed(bool bDestroyingHierarchy) override;

    /** Opens the staged original Elsa movie paused; Ready does not assert a painted frame. */
    bool PrepareElsa(const FString& SequenceId, float PlayRate = 1.0f, bool bMuted = false, float Volume = 1.0f);
    bool PlayPrepared(const FString& SequenceId);
    void Cancel(const FString& SequenceId);
    void Release();
    bool SetAudio(bool bMuted, float Volume);

    EHczsUltimateVideoState GetState() const { return Lifecycle.State; }
    const FString& GetSequenceId() const { return Lifecycle.SequenceId; }
    const FString& GetErrorMessage() const { return ErrorMessage; }
    /** Regular 2D output suitable for a Slate texture brush or UI material. */
    UMediaTexture* GetMediaTexture() const { return MediaTexture; }
    /** Read-only inspection interface; callers must not control the underlying player. */
    UMediaPlayer* GetMediaPlayer() const { return MediaPlayer; }
    bool HasDecodedVideoSurface() const;

    FOnHczsUltimateVideoReady OnReadyNative;
    FOnHczsUltimateVideoStarted OnStartedNative;
    /** Exactly one terminal callback per accepted sequence, including failure/scene exit. */
    FOnHczsUltimateVideoFinished OnFinishedNative;

private:
    friend class UHczsUltimateMediaCallbacks;
    UPROPERTY(Transient) TObjectPtr<UFileMediaSource> FileSource;
    UPROPERTY(Transient) TObjectPtr<UMediaPlayer> MediaPlayer;
    UPROPERTY(Transient) TObjectPtr<UMediaTexture> MediaTexture;
    UPROPERTY(Transient) TObjectPtr<UMediaSoundComponent> SoundComponent;
    UPROPERTY(Transient) TObjectPtr<UHczsUltimateMediaCallbacks> Callbacks;
    FHczsUltimateVideoLifecycle Lifecycle;
    FString ErrorMessage;
    float RequestedRate = 1.0f;
    float RequestedVolume = 1.0f;
    bool bRequestedMuted = false;
    bool bOpenedEventObserved = false;
    bool bDecodedSurfaceLogged = false;
    bool bEndingPlay = false;
    bool bOwnsWorldPause = false;
    TWeakObjectPtr<UWorld> PausedWorld;
    double DeadlineSeconds = 0.0;
    FTSTicker::FDelegateHandle WatchdogHandle;

    void HandleMediaEvent(uint64 Generation, UMediaPlayer* Sender, EHczsUltimateMediaCallback Event);
    void TryBecomeReady(uint64 Generation);
    void NotifyStarted(uint64 Generation);
    void Finish(uint64 Generation, EHczsUltimateVideoFinish Result, const FString& Message = FString());
    void CleanupMedia();
    void StopWatchdog();
    bool Watchdog(float DeltaSeconds);
    void ApplyAudio();
};
