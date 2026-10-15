#include "HczsUltimateSequence.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimSingleNodeInstance.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "Brushes/SlateColorBrush.h"
#include "Kismet/GameplayStatics.h"
#include "MediaTexture.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScaleBox.h"

namespace
{
// Original ailisha.ags SHA 12702cdb...8e729; source clip duration 7.2s.
constexpr float ElsaClipLength = 7.2f, VideoPosition = ElsaClipLength * 0.533333f;
struct FSourceUltimateCue { const TCHAR* Name; float Ratio; };
#include "HczsElsaUltimateEvents.inl"
}

UHczsUltimateSequence::UHczsUltimateSequence()
{
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.TickGroup = TG_PostUpdateWork;
}
bool UHczsUltimateSequence::IsActive() const
{
    return State == EHczsUltimateSequenceState::Animation || State == EHczsUltimateSequenceState::WaitingForVideo || State == EHczsUltimateSequenceState::Video;
}
float UHczsUltimateSequence::GetAnimationPosition() const
{
    const auto* Instance = Target ? Target->GetSingleNodeInstance() : nullptr;
    return Instance ? Instance->GetCurrentTime() : -1;
}
bool UHczsUltimateSequence::PlayElsa(USkeletalMeshComponent* Mesh, const FString& Id, bool bMuted)
{
    if (IsActive()) return SequenceId == Id && Target == Mesh;
    if (bEndingPlay || !IsRegistered() || !GetWorld() || !GetOwner() || Id.IsEmpty() || Id.Len() > 256 || Retired.Contains(Id) ||
        !Mesh || Mesh->GetWorld() != GetWorld() || UGameplayStatics::IsGamePaused(GetWorld())) return false;
    auto* Instance = Mesh->GetSingleNodeInstance();
    auto* Animation = LoadObject<UAnimSequence>(nullptr, TEXT("/Game/Recovered/Battle/ElsaUltimate/elsa-ultimate.elsa-ultimate"));
    if (!Instance || !Instance->GetCurrentAsset() || !Animation || !Mesh->GetSkeletalMeshAsset() ||
        Animation->GetSkeleton() != Mesh->GetSkeletalMeshAsset()->GetSkeleton() || FMath::Abs(Animation->GetPlayLength() - ElsaClipLength) > .001f) return false;
    Target = Mesh; Clip = Animation; SequenceId = Id;
    PreviousAnimation = Instance->GetCurrentAsset(); PreviousPosition = Instance->GetCurrentTime();
    PreviousRate = Instance->GetPlayRate(); bPreviousLooping = Instance->IsLooping(); bPreviousPlaying = Instance->IsPlaying();
    bPreviousPaused = Mesh->bPauseAnims;
    bPrepared = bVideoReady = bVideoDone = false; NextSourceCue = 0; FinalPosition = 0;
    bMutedSequence = bMuted; bHeldPose = false;
    Video = NewObject<UHczsUltimateVideoPlayer>(GetOwner(), NAME_None, RF_Transient);
    GetOwner()->AddInstanceComponent(Video); Video->RegisterComponent(); Video->SetAudio(bMuted, 1);
    Video->OnReadyNative.AddUObject(this, &UHczsUltimateSequence::Ready);
    Video->OnFinishedNative.AddUObject(this, &UHczsUltimateSequence::VideoEnded);
    State = EHczsUltimateSequenceState::Animation;
    Mesh->bPauseAnims = false; Mesh->PlayAnimation(Clip, false); Mesh->SetPlayRate(1); Mesh->SetPosition(0, false);
    while (NextSourceCue < UE_ARRAY_COUNT(ElsaSourceCues) && ElsaSourceCues[NextSourceCue].Ratio == 0)
    {
        const auto Cue = ElsaSourceCues[NextSourceCue++];
        OnCueNative.Broadcast(SequenceId, Cue.Name, 0);
        if (!IsActive() || SequenceId != Id) break;
    }
    return true;
}
void UHczsUltimateSequence::TickComponent(float Delta, ELevelTick Type, FActorComponentTickFunction* Tick)
{
    Super::TickComponent(Delta, Type, Tick);
    if (!IsActive()) return;
    const FString CurrentId = SequenceId;
    auto* Instance = Target ? Target->GetSingleNodeInstance() : nullptr;
    if (!Instance || Instance->GetCurrentAsset() != Clip)
    { Finish(EHczsUltimateSequenceState::Failed, TEXT("终结技角色动作被替换。")); return; }
    const float Position = Instance->GetCurrentTime();
    if (!bPrepared && Position >= VideoPosition - .2f)
    {
        bPrepared = true;
        if (!Video->PrepareElsa(SequenceId, 1, bMutedSequence, 1))
        { if (IsActive()) Finish(EHczsUltimateSequenceState::Failed, TEXT("终结技视频预加载失败。")); return; }
    }
    if (!IsActive() || SequenceId != CurrentId) return;
    // Clamp at the authored cue before processing any later events, including a long frame.
    const float EventPosition = !bVideoDone ? FMath::Min(Position, VideoPosition) :
        (Position >= ElsaClipLength - .001f ? ElsaClipLength : Position);
    while (NextSourceCue < UE_ARRAY_COUNT(ElsaSourceCues) && EventPosition >= ElsaClipLength * ElsaSourceCues[NextSourceCue].Ratio)
    {
        const auto Cue = ElsaSourceCues[NextSourceCue++];
        // Video must be announced only after holding the exact authored pose below.
        if (FCString::Strcmp(Cue.Name, TEXT("video")) == 0) continue;
        OnCueNative.Broadcast(SequenceId, Cue.Name, ElsaClipLength * Cue.Ratio);
        if (!IsActive() || SequenceId != CurrentId) return;
    }
    if (!bVideoDone && State == EHczsUltimateSequenceState::Animation && Position >= VideoPosition)
    {
        Target->SetPosition(VideoPosition, false); Target->TickAnimation(0, false); Target->RefreshBoneTransforms();
        Target->bPauseAnims = true; bHeldPose = true; State = EHczsUltimateSequenceState::WaitingForVideo;
        OnCueNative.Broadcast(SequenceId, TEXT("video"), VideoPosition);
        if (!IsActive() || SequenceId != CurrentId) return;
        BeginVideo();
    }
    if (SequenceId == CurrentId && State == EHczsUltimateSequenceState::Animation && bVideoDone && Position >= ElsaClipLength - .001f)
    { FinalPosition = Position; Finish(EHczsUltimateSequenceState::Completed); }
}
void UHczsUltimateSequence::Ready(const FString& Id, UMediaTexture* Texture)
{
    if (!IsActive() || Id != SequenceId) return;
    VideoTexture = Texture; bVideoReady = true; BeginVideo();
}
void UHczsUltimateSequence::BeginVideo()
{
    if (State != EHczsUltimateSequenceState::WaitingForVideo || !bVideoReady) return;
    auto* Viewport = GetWorld()->GetGameViewport();
    if (!Viewport || !VideoTexture) { Finish(EHczsUltimateSequenceState::Failed, TEXT("终结技视口不可用。")); return; }
    VideoBrush.DrawAs = ESlateBrushDrawType::Image; VideoBrush.ImageSize = FVector2f(1560, 960); VideoBrush.SetResourceObject(VideoTexture);
    BlackBrush = FSlateColorBrush(FLinearColor::Black);
    Overlay = SNew(SBorder).BorderImage(&BlackBrush).Padding(0)
        [SNew(SScaleBox).Stretch(EStretch::ScaleToFit)
            [SNew(SBox).WidthOverride(1560).HeightOverride(960)[SNew(SImage).Image(&VideoBrush)]]];
    Viewport->AddViewportWidgetContent(Overlay.ToSharedRef(), 100000);
    State = EHczsUltimateSequenceState::Video;
    if (!Video->PlayPrepared(SequenceId) && IsActive()) Finish(EHczsUltimateSequenceState::Failed, TEXT("终结技视频启动失败。"));
}
void UHczsUltimateSequence::RemoveOverlay()
{
    if (Overlay && GetWorld() && GetWorld()->GetGameViewport()) GetWorld()->GetGameViewport()->RemoveViewportWidgetContent(Overlay.ToSharedRef());
    Overlay.Reset(); VideoBrush.SetResourceObject(nullptr); VideoTexture = nullptr;
}
void UHczsUltimateSequence::VideoEnded(const FString& Id, EHczsUltimateVideoFinish Result, const FString& Error)
{
    if (!IsActive() || Id != SequenceId) return;
    RemoveOverlay();
    if (Result != EHczsUltimateVideoFinish::Completed) { Finish(EHczsUltimateSequenceState::Failed, Error); return; }
    if (State != EHczsUltimateSequenceState::Video || !Target) { Finish(EHczsUltimateSequenceState::Failed, TEXT("终结技回场状态无效。")); return; }
    bVideoDone = true; Target->bPauseAnims = false; bHeldPose = false; State = EHczsUltimateSequenceState::Animation;
    OnCueNative.Broadcast(SequenceId, TEXT("video-complete"), GetAnimationPosition());
}
void UHczsUltimateSequence::Finish(EHczsUltimateSequenceState Result, const FString& Error)
{
    if (!IsActive()) return;
    State = Result; Retired.Add(SequenceId);
    const FString FinishedId = SequenceId;
    RemoveOverlay();
    if (Video)
    {
        Video->OnReadyNative.RemoveAll(this); Video->OnFinishedNative.RemoveAll(this);
        Video->Release(); GetOwner()->RemoveInstanceComponent(Video); Video->DestroyComponent(); Video = nullptr;
    }
    if (Target)
    {
        if (bHeldPose) Target->bPauseAnims = bPreviousPaused;
        auto* Instance = Target->GetSingleNodeInstance();
        if (Instance && Instance->GetCurrentAsset() == Clip)
        {
            Target->PlayAnimation(PreviousAnimation, bPreviousLooping); Target->SetPosition(PreviousPosition, false); Target->SetPlayRate(PreviousRate);
            Target->GetSingleNodeInstance()->SetPlaying(bPreviousPlaying); Target->bPauseAnims = bPreviousPaused;
        }
    }
    Target = nullptr; Clip = nullptr; PreviousAnimation = nullptr;
    OnFinishedNative.Broadcast(FinishedId, Result == EHczsUltimateSequenceState::Completed, Error);
}
void UHczsUltimateSequence::Cancel() { Finish(EHczsUltimateSequenceState::Cancelled, TEXT("终结技已取消。")); }
void UHczsUltimateSequence::EndPlay(const EEndPlayReason::Type Reason)
{
    bEndingPlay = true; Cancel(); OnCueNative.Clear(); OnFinishedNative.Clear(); Super::EndPlay(Reason);
}
void UHczsUltimateSequence::OnComponentDestroyed(bool bDestroyingHierarchy)
{
    // Also cover components destroyed before BeginPlay; EndPlay is not guaranteed then.
    bEndingPlay = true; Cancel(); OnCueNative.Clear(); OnFinishedNative.Clear();
    Super::OnComponentDestroyed(bDestroyingHierarchy);
}
