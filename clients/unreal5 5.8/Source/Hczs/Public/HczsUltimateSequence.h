#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Styling/SlateBrush.h"
#include "HczsUltimateVideoPlayer.h"
#include "HczsUltimateSequence.generated.h"

class USkeletalMeshComponent;
class UAnimSequence;
class UAnimationAsset;
class SWidget;
enum class EHczsUltimateSequenceState : uint8 { Idle, Animation, WaitingForVideo, Video, Completed, Failed, Cancelled };
DECLARE_MULTICAST_DELEGATE_ThreeParams(FHczsUltimateCue, const FString&, const FString&, float);
DECLARE_MULTICAST_DELEGATE_ThreeParams(FHczsUltimateSequenceFinished, const FString&, bool, const FString&);

/** Source-clip/video presentation only. Cue events never predict or mutate HP. */
UCLASS()
class HCZS_API UHczsUltimateSequence : public UActorComponent
{
    GENERATED_BODY()
public:
    UHczsUltimateSequence();
    bool PlayElsa(USkeletalMeshComponent* Mesh, const FString& Id, bool bMuted = false);
    void Cancel();
    virtual void TickComponent(float Delta, ELevelTick Type, FActorComponentTickFunction* Tick) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    virtual void OnComponentDestroyed(bool bDestroyingHierarchy) override;
    EHczsUltimateSequenceState GetState() const { return State; }
    UHczsUltimateVideoPlayer* GetVideo() const { return Video; }
    float GetAnimationPosition() const;
    float GetFinalPosition() const { return FinalPosition; }
    FHczsUltimateCue OnCueNative;
    FHczsUltimateSequenceFinished OnFinishedNative;
private:
    void Ready(const FString& Id, UMediaTexture* Texture);
    void VideoEnded(const FString& Id, EHczsUltimateVideoFinish Result, const FString& Error);
    void BeginVideo();
    void RemoveOverlay();
    void Finish(EHczsUltimateSequenceState Result, const FString& Error = FString());
    bool IsActive() const;
    UPROPERTY(Transient) TObjectPtr<USkeletalMeshComponent> Target;
    UPROPERTY(Transient) TObjectPtr<UAnimSequence> Clip;
    UPROPERTY(Transient) TObjectPtr<UAnimationAsset> PreviousAnimation;
    UPROPERTY(Transient) TObjectPtr<UHczsUltimateVideoPlayer> Video;
    UPROPERTY(Transient) TObjectPtr<UMediaTexture> VideoTexture;
    EHczsUltimateSequenceState State = EHczsUltimateSequenceState::Idle;
    FString SequenceId;
    TSet<FString> Retired;
    TSharedPtr<SWidget> Overlay;
    FSlateBrush VideoBrush, BlackBrush;
    float PreviousPosition = 0, PreviousRate = 1, FinalPosition = 0;
    bool bPreviousLooping = false, bPreviousPlaying = false, bPreviousPaused = false;
    bool bPrepared = false, bVideoReady = false, bVideoDone = false;
    bool bMutedSequence = false, bEndingPlay = false, bHeldPose = false;
    int32 NextSourceCue = 0;
};
