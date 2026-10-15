#include "HczsUltimateVideoPlayer.h"

#include "Async/Async.h"
#include "Containers/Ticker.h"
#include "Engine/World.h"
#include "FileMediaSource.h"
#include "GameFramework/Actor.h"
#include "HAL/PlatformTime.h"
#include "Kismet/GameplayStatics.h"
#include "MediaPlayer.h"
#include "MediaPlayerOptions.h"
#include "MediaSoundComponent.h"
#include "MediaTexture.h"
#include "Misc/Paths.h"
#include "UObject/StrongObjectPtr.h"

namespace
{
    constexpr double OpenTimeoutSeconds = 10.0;
    int64 VideoUnixMs()
    {
        const FDateTime Now = FDateTime::UtcNow();
        return Now.ToUnixTimestamp() * 1000 + Now.GetMillisecond();
    }
}

bool FHczsUltimateVideoLifecycle::IsActive() const
{
    return State == EHczsUltimateVideoState::Preparing || State == EHczsUltimateVideoState::Ready || State == EHczsUltimateVideoState::Playing;
}

bool FHczsUltimateVideoLifecycle::IsCurrent(uint64 CallbackGeneration) const
{
    return !SequenceId.IsEmpty() && CallbackGeneration == Generation && IsActive();
}

EHczsUltimateVideoBegin FHczsUltimateVideoLifecycle::Begin(const FString& NewSequenceId)
{
    if (NewSequenceId.IsEmpty() || NewSequenceId.Len() > 256 || RetiredSequences.Contains(NewSequenceId))
        return EHczsUltimateVideoBegin::Rejected;
    if (IsActive())
        return NewSequenceId == SequenceId ? EHczsUltimateVideoBegin::Idempotent : EHczsUltimateVideoBegin::Rejected;
    ++Generation; SequenceId = NewSequenceId; State = EHczsUltimateVideoState::Preparing;
    bStartedNotified = false;
    return EHczsUltimateVideoBegin::Fresh;
}

bool FHczsUltimateVideoLifecycle::MarkReady(uint64 CallbackGeneration)
{
    if (!IsCurrent(CallbackGeneration) || State != EHczsUltimateVideoState::Preparing) return false;
    State = EHczsUltimateVideoState::Ready; return true;
}

bool FHczsUltimateVideoLifecycle::RequestPlay(const FString& ExpectedSequenceId)
{
    if (ExpectedSequenceId != SequenceId || State != EHczsUltimateVideoState::Ready) return false;
    State = EHczsUltimateVideoState::Playing; return true;
}

bool FHczsUltimateVideoLifecycle::MarkStarted(uint64 CallbackGeneration)
{
    if (!IsCurrent(CallbackGeneration) || State != EHczsUltimateVideoState::Playing || bStartedNotified) return false;
    bStartedNotified = true; return true;
}

bool FHczsUltimateVideoLifecycle::Finish(uint64 CallbackGeneration, EHczsUltimateVideoFinish Result)
{
    if (!IsCurrent(CallbackGeneration)) return false;
    if (Result == EHczsUltimateVideoFinish::Completed && State != EHczsUltimateVideoState::Playing) return false;
    RetiredSequences.Add(SequenceId);
    State = Result == EHczsUltimateVideoFinish::Completed ? EHczsUltimateVideoState::Completed :
        Result == EHczsUltimateVideoFinish::Cancelled ? EHczsUltimateVideoState::Cancelled : EHczsUltimateVideoState::Failed;
    return true;
}

bool FHczsUltimateVideoLifecycle::ClearActive(uint64 ExpectedGeneration)
{
    if (ExpectedGeneration != Generation) return false;
    if (IsActive()) RetiredSequences.Add(SequenceId);
    ++Generation; SequenceId.Reset(); State = EHczsUltimateVideoState::Idle; bStartedNotified = false;
    return true;
}

void UHczsUltimateMediaCallbacks::Initialize(UHczsUltimateVideoPlayer* InOwner, UMediaPlayer* InPlayer, uint64 InGeneration)
{
    Owner = InOwner; Player = InPlayer; Generation = InGeneration;
}
void UHczsUltimateMediaCallbacks::Opened(FString Url) { Dispatch(EHczsUltimateMediaCallback::Opened); }
void UHczsUltimateMediaCallbacks::OpenFailed(FString Url) { Dispatch(EHczsUltimateMediaCallback::OpenFailed); }
void UHczsUltimateMediaCallbacks::EndReached() { Dispatch(EHczsUltimateMediaCallback::EndReached); }
void UHczsUltimateMediaCallbacks::Closed() { Dispatch(EHczsUltimateMediaCallback::Closed); }
void UHczsUltimateMediaCallbacks::Resumed() { Dispatch(EHczsUltimateMediaCallback::Resumed); }

void UHczsUltimateMediaCallbacks::Dispatch(EHczsUltimateMediaCallback Event)
{
    const TWeakObjectPtr<UHczsUltimateVideoPlayer> WeakOwner = Owner;
    const TWeakObjectPtr<UMediaPlayer> WeakSender = Player;
    const uint64 CallbackGeneration = Generation;
    auto Deliver = [WeakOwner, WeakSender, CallbackGeneration, Event]()
    {
        if (auto* Component = WeakOwner.Get())
            Component->HandleMediaEvent(CallbackGeneration, WeakSender.Get(), Event);
    };
    if (IsInGameThread()) Deliver(); else AsyncTask(ENamedThreads::GameThread, MoveTemp(Deliver));
}

UHczsUltimateVideoPlayer::UHczsUltimateVideoPlayer()
{
    PrimaryComponentTick.bCanEverTick = false;
}

bool UHczsUltimateVideoPlayer::PrepareElsa(const FString& SequenceId, float PlayRate, bool bMuted, float Volume)
{
    if (!ensure(IsInGameThread()) || bEndingPlay || !IsRegistered() || !GetOwner() || !GetWorld() || IsRunningDedicatedServer()) return false;
    if (!FMath::IsFinite(PlayRate) || PlayRate <= 0 || PlayRate > 4.0f || !FMath::IsFinite(Volume) || Volume < 0 || Volume > 1.0f)
    { ErrorMessage = TEXT("终结技视频播放参数无效。"); return false; }
    if (Lifecycle.IsActive() && SequenceId == Lifecycle.SequenceId &&
        (RequestedRate != PlayRate || RequestedVolume != Volume || bRequestedMuted != bMuted)) return false;
    const EHczsUltimateVideoBegin Begin = Lifecycle.Begin(SequenceId);
    if (Begin == EHczsUltimateVideoBegin::Rejected) return false;
    if (Begin == EHczsUltimateVideoBegin::Idempotent) return true;

    CleanupMedia(); ErrorMessage.Reset(); RequestedRate = PlayRate; RequestedVolume = Volume; bRequestedMuted = bMuted;
    bOpenedEventObserved = false; bDecodedSurfaceLogged = false;
    const uint64 Generation = Lifecycle.Generation;
    const FString MoviePath = FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::ProjectContentDir(), TEXT("Movies/Recovered/Ultimates/aiersha_1.mp4")));
    FileSource = NewObject<UFileMediaSource>(this, NAME_None, RF_Transient);
    FileSource->SetFilePath(MoviePath); FileSource->PrecacheFile = true;
    if (!FileSource->Validate())
    { Finish(Generation, EHczsUltimateVideoFinish::Failed, TEXT("未找到已恢复的艾尔莎终结技视频。")); return false; }

    MediaPlayer = NewObject<UMediaPlayer>(this, NAME_None, RF_Transient);
    MediaPlayer->PlayOnOpen = false; MediaPlayer->NativeAudioOut = false;
    MediaTexture = NewObject<UMediaTexture>(this, NAME_None, RF_Transient);
    MediaTexture->NewStyleOutput = true; MediaTexture->AutoClear = true;
    MediaTexture->ClearColor = FLinearColor::Black;
    MediaTexture->SetMediaPlayer(MediaPlayer); MediaTexture->UpdateResource();

    SoundComponent = NewObject<UMediaSoundComponent>(GetOwner(), NAME_None, RF_Transient);
    SoundComponent->SetAutoActivate(false); SoundComponent->bAllowSpatialization = false;
    SoundComponent->bIsUISound = true;
    SoundComponent->bStopWhenOwnerDestroyed = true; SoundComponent->SetVolumeMultiplier(0.0f);
    GetOwner()->AddInstanceComponent(SoundComponent);
    SoundComponent->SetMediaPlayer(MediaPlayer); SoundComponent->RegisterComponent(); SoundComponent->AddClockSink();
    Callbacks = NewObject<UHczsUltimateMediaCallbacks>(this, NAME_None, RF_Transient);
    Callbacks->Initialize(this, MediaPlayer, Generation);
    MediaPlayer->OnMediaOpened.AddDynamic(Callbacks, &UHczsUltimateMediaCallbacks::Opened);
    MediaPlayer->OnMediaOpenFailed.AddDynamic(Callbacks, &UHczsUltimateMediaCallbacks::OpenFailed);
    MediaPlayer->OnEndReached.AddDynamic(Callbacks, &UHczsUltimateMediaCallbacks::EndReached);
    MediaPlayer->OnMediaClosed.AddDynamic(Callbacks, &UHczsUltimateMediaCallbacks::Closed);
    MediaPlayer->OnPlaybackResumed.AddDynamic(Callbacks, &UHczsUltimateMediaCallbacks::Resumed);
    DeadlineSeconds = FPlatformTime::Seconds() + OpenTimeoutSeconds;
    WatchdogHandle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateWeakLambda(this,
        [this, Generation](float Delta) { return Lifecycle.IsCurrent(Generation) && Watchdog(Delta); }));
    FMediaPlayerOptions Options;
    Options.PlayOnOpen = EMediaPlayerOptionBooleanOverride::Disabled;
    Options.Loop = EMediaPlayerOptionBooleanOverride::Disabled;
    Options.SeekTime = FTimespan::Zero();
    // Opened/Ready callbacks may execute inside OpenSourceWithOptions. Keep the
    // exact objects alive and never overwrite a reentrant new sequence afterward.
    TStrongObjectPtr<UMediaPlayer> PlayerGuard(MediaPlayer);
    TStrongObjectPtr<UFileMediaSource> SourceGuard(FileSource);
    UE_LOG(LogTemp, Display, TEXT("HCZS ultimate video preparing: sequence=%s generation=%llu rate=%.3f atUnixMs=%lld"),
        *SequenceId, Generation, RequestedRate, VideoUnixMs());
    const bool bAccepted = PlayerGuard->OpenSourceWithOptions(SourceGuard.Get(), Options);
    if (!Lifecycle.IsCurrent(Generation) || MediaPlayer != PlayerGuard.Get()) return false;
    if (!bAccepted)
    { Finish(Generation, EHczsUltimateVideoFinish::Failed, TEXT("无法打开艾尔莎终结技视频。")); return false; }
    return true;
}

void UHczsUltimateVideoPlayer::TryBecomeReady(uint64 Generation)
{
    if (!Lifecycle.IsCurrent(Generation) || Lifecycle.State != EHczsUltimateVideoState::Preparing || !bOpenedEventObserved || !MediaPlayer) return;
    if (!MediaPlayer->IsReady()) return;
    const int32 Track = MediaPlayer->GetSelectedTrack(EMediaPlayerTrack::Video);
    if (Track < 0 || MediaPlayer->GetNumTracks(EMediaPlayerTrack::Video) < 1) return;
    const FIntPoint VideoSize = MediaPlayer->GetVideoTrackDimensions(Track, MediaPlayer->GetTrackFormat(EMediaPlayerTrack::Video, Track));
    if (VideoSize.X <= 2 || VideoSize.Y <= 2 || MediaPlayer->GetDuration() <= FTimespan::Zero()) return;
    if (!MediaPlayer->SupportsRate(RequestedRate, false))
    { Finish(Generation, EHczsUltimateVideoFinish::Failed, TEXT("当前视频解码器不支持所选播放速度。")); return; }
    if (MediaPlayer->IsPlaying() && !MediaPlayer->Pause())
    { Finish(Generation, EHczsUltimateVideoFinish::Failed, TEXT("终结技视频无法保持预加载状态。")); return; }
    if (!Lifecycle.MarkReady(Generation)) return;
    DeadlineSeconds = 0.0;
    ApplyAudio();
    const FString ReadyId = Lifecycle.SequenceId;
    TStrongObjectPtr<UMediaTexture> TextureGuard(MediaTexture);
    UE_LOG(LogTemp, Display, TEXT("HCZS ultimate video ready: sequence=%s size=%dx%d duration=%.6f audioTracks=%d decoder=%s atUnixMs=%lld; frame paint checked separately"),
        *ReadyId, VideoSize.X, VideoSize.Y, MediaPlayer->GetDuration().GetTotalSeconds(),
        MediaPlayer->GetNumTracks(EMediaPlayerTrack::Audio), *MediaPlayer->GetPlayerName().ToString(), VideoUnixMs());
    OnReadyNative.Broadcast(ReadyId, TextureGuard.Get());
}

bool UHczsUltimateVideoPlayer::PlayPrepared(const FString& SequenceId)
{
    if (!ensure(IsInGameThread()) || bEndingPlay || !MediaPlayer || SequenceId != Lifecycle.SequenceId) return false;
    if (Lifecycle.State == EHczsUltimateVideoState::Playing) return true;
    if (!Lifecycle.RequestPlay(SequenceId)) return false;
    const uint64 Generation = Lifecycle.Generation;
    TStrongObjectPtr<UMediaPlayer> PlayerGuard(MediaPlayer);
    DeadlineSeconds = FPlatformTime::Seconds() + FMath::Max(10.0, PlayerGuard->GetDuration().GetTotalSeconds() / RequestedRate + 5.0);
    UWorld* World = GetWorld();
    if (!World)
    { Finish(Generation, EHczsUltimateVideoFinish::Failed, TEXT("终结技场景已关闭。")); return false; }
    // UE adaptation of native global-speed suspension: preserve an existing
    // pause and leave time dilation and animation positions unchanged.
    if (!UGameplayStatics::IsGamePaused(World))
    {
        if (!UGameplayStatics::SetGamePaused(World, true))
        { Finish(Generation, EHczsUltimateVideoFinish::Failed, TEXT("无法暂停终结技所在场景。")); return false; }
        PausedWorld = World; bOwnsWorldPause = true;
    }
    if (SoundComponent) { SoundComponent->Start(); SoundComponent->UpdatePlayer(); }
    ApplyAudio();
    if (!PlayerGuard->SetRate(RequestedRate))
    {
        if (Lifecycle.IsCurrent(Generation)) Finish(Generation, EHczsUltimateVideoFinish::Failed, TEXT("终结技视频无法开始播放。"));
        return false;
    }
    if (!Lifecycle.IsCurrent(Generation) || MediaPlayer != PlayerGuard.Get()) return false;
    if (PlayerGuard->IsPlaying()) NotifyStarted(Generation);
    return true;
}

void UHczsUltimateVideoPlayer::NotifyStarted(uint64 Generation)
{
    if (!Lifecycle.MarkStarted(Generation)) return;
    const FString StartedId = Lifecycle.SequenceId;
    UE_LOG(LogTemp, Display, TEXT("HCZS ultimate video started: sequence=%s rate=%.3f atUnixMs=%lld"), *StartedId, RequestedRate, VideoUnixMs());
    OnStartedNative.Broadcast(StartedId);
}

void UHczsUltimateVideoPlayer::HandleMediaEvent(uint64 Generation, UMediaPlayer* Sender, EHczsUltimateMediaCallback Event)
{
    if (bEndingPlay || !Lifecycle.IsCurrent(Generation) || !Sender || MediaPlayer != Sender) return;
    switch (Event)
    {
    case EHczsUltimateMediaCallback::Opened:
        bOpenedEventObserved = true; TryBecomeReady(Generation); break;
    case EHczsUltimateMediaCallback::OpenFailed:
        Finish(Generation, EHczsUltimateVideoFinish::Failed, TEXT("艾尔莎终结技视频解码失败。")); break;
    case EHczsUltimateMediaCallback::EndReached:
        if (Lifecycle.State == EHczsUltimateVideoState::Playing) Finish(Generation, EHczsUltimateVideoFinish::Completed);
        break;
    case EHczsUltimateMediaCallback::Closed:
        Finish(Generation, EHczsUltimateVideoFinish::Failed, TEXT("终结技视频被意外关闭。")); break;
    case EHczsUltimateMediaCallback::Resumed:
        if (Sender->IsPlaying()) NotifyStarted(Generation);
        break;
    }
}

bool UHczsUltimateVideoPlayer::HasDecodedVideoSurface() const
{
    if (!MediaTexture || !MediaPlayer || !Lifecycle.IsActive()) return false;
    const int32 Track = MediaPlayer->GetSelectedTrack(EMediaPlayerTrack::Video);
    if (Track < 0) return false;
    const FIntPoint Expected = MediaPlayer->GetVideoTrackDimensions(Track, MediaPlayer->GetTrackFormat(EMediaPlayerTrack::Video, Track));
    // Engine's clear target is 2x2. This checks a decoded output surface, not a
    // Slate NativePaint call or a screenshot containing the original pixels.
    return Expected.X > 2 && Expected.Y > 2 && MediaTexture->GetWidth() == Expected.X && MediaTexture->GetHeight() == Expected.Y;
}

bool UHczsUltimateVideoPlayer::Watchdog(float DeltaSeconds)
{
    if (bEndingPlay || !Lifecycle.IsActive()) { WatchdogHandle.Reset(); return false; }
    const uint64 Generation = Lifecycle.Generation;
    if (!MediaPlayer || MediaPlayer->HasError())
    { Finish(Generation, EHczsUltimateVideoFinish::Failed, TEXT("终结技视频播放失败。")); return false; }
    TryBecomeReady(Generation);
    if (!Lifecycle.IsCurrent(Generation)) return false;
    if (Lifecycle.State == EHczsUltimateVideoState::Playing && MediaPlayer->IsPlaying()) NotifyStarted(Generation);
    if (!Lifecycle.IsCurrent(Generation)) return false;
    if (!bDecodedSurfaceLogged && HasDecodedVideoSurface())
    {
        bDecodedSurfaceLogged = true;
        UE_LOG(LogTemp, Display, TEXT("HCZS ultimate video decoded surface: sequence=%s size=%dx%d position=%.6f atUnixMs=%lld"),
            *Lifecycle.SequenceId, MediaTexture->GetWidth(), MediaTexture->GetHeight(), MediaPlayer->GetTime().GetTotalSeconds(), VideoUnixMs());
    }
    if (DeadlineSeconds > 0 && FPlatformTime::Seconds() >= DeadlineSeconds)
    { Finish(Generation, EHczsUltimateVideoFinish::Failed, TEXT("终结技视频加载或播放超时。")); return false; }
    return true;
}

bool UHczsUltimateVideoPlayer::SetAudio(bool bMuted, float Volume)
{
    if (!ensure(IsInGameThread()) || !FMath::IsFinite(Volume) || Volume < 0 || Volume > 1.0f) return false;
    bRequestedMuted = bMuted; RequestedVolume = Volume; ApplyAudio(); return true;
}

void UHczsUltimateVideoPlayer::ApplyAudio()
{
    if (SoundComponent) SoundComponent->SetVolumeMultiplier(
        Lifecycle.State == EHczsUltimateVideoState::Playing && !bRequestedMuted ? RequestedVolume : 0.0f);
}

void UHczsUltimateVideoPlayer::Finish(uint64 Generation, EHczsUltimateVideoFinish Result, const FString& Message)
{
    if (!Lifecycle.Finish(Generation, Result)) return;
    const FString FinishedId = Lifecycle.SequenceId;
    const FString FinishedMessage = Message;
    ErrorMessage = FinishedMessage;
    CleanupMedia();
    UE_LOG(LogTemp, Display, TEXT("HCZS ultimate video finished: sequence=%s result=%d atUnixMs=%lld"), *FinishedId, static_cast<int32>(Result), VideoUnixMs());
    // All resources/callbacks have been cleared first. A listener may safely
    // prepare another sequence here; no old cleanup runs after the broadcast.
    OnFinishedNative.Broadcast(FinishedId, Result, FinishedMessage);
}

void UHczsUltimateVideoPlayer::Cancel(const FString& SequenceId)
{
    if (!ensure(IsInGameThread()) || SequenceId != Lifecycle.SequenceId) return;
    Finish(Lifecycle.Generation, EHczsUltimateVideoFinish::Cancelled);
}

void UHczsUltimateVideoPlayer::Release()
{
    if (!ensure(IsInGameThread())) return;
    const uint64 Generation = Lifecycle.Generation;
    if (Lifecycle.IsActive()) Finish(Generation, EHczsUltimateVideoFinish::Cancelled); else CleanupMedia();
    // The finished delegate may have begun a new sequence. Do not clear it.
    Lifecycle.ClearActive(Generation);
}

void UHczsUltimateVideoPlayer::StopWatchdog()
{
    if (WatchdogHandle.IsValid())
    {
        const FTSTicker::FDelegateHandle Handle = WatchdogHandle;
        WatchdogHandle.Reset(); FTSTicker::RemoveTicker(Handle);
    }
}

void UHczsUltimateVideoPlayer::CleanupMedia()
{
    StopWatchdog(); DeadlineSeconds = 0.0;
    const bool bResumeWorld = bOwnsWorldPause;
    const TWeakObjectPtr<UWorld> WorldToResume = PausedWorld;
    bOwnsWorldPause = false; PausedWorld.Reset();
    // Detach member ownership before calls that can broadcast engine delegates.
    // A callback that begins another sequence must not have its objects cleared
    // by the tail of this old Close/Destroy operation.
    TStrongObjectPtr<UMediaPlayer> OldPlayer(MediaPlayer.Get());
    TStrongObjectPtr<UMediaTexture> OldTexture(MediaTexture.Get());
    TStrongObjectPtr<UHczsUltimateMediaCallbacks> OldCallbacks(Callbacks.Get());
    TStrongObjectPtr<UMediaSoundComponent> OldSound(SoundComponent.Get());
    Callbacks = nullptr; SoundComponent = nullptr; MediaTexture = nullptr; MediaPlayer = nullptr; FileSource = nullptr;
    bOpenedEventObserved = false; bDecodedSurfaceLogged = false;
    if (OldPlayer && OldCallbacks)
    {
        OldPlayer->OnMediaOpened.RemoveDynamic(OldCallbacks.Get(), &UHczsUltimateMediaCallbacks::Opened);
        OldPlayer->OnMediaOpenFailed.RemoveDynamic(OldCallbacks.Get(), &UHczsUltimateMediaCallbacks::OpenFailed);
        OldPlayer->OnEndReached.RemoveDynamic(OldCallbacks.Get(), &UHczsUltimateMediaCallbacks::EndReached);
        OldPlayer->OnMediaClosed.RemoveDynamic(OldCallbacks.Get(), &UHczsUltimateMediaCallbacks::Closed);
        OldPlayer->OnPlaybackResumed.RemoveDynamic(OldCallbacks.Get(), &UHczsUltimateMediaCallbacks::Resumed);
    }
    if (OldSound)
    {
        OldSound->SetVolumeMultiplier(0.0f); OldSound->Stop(); OldSound->RemoveClockSink();
        OldSound->SetMediaPlayer(nullptr);
        if (AActor* SoundOwner = OldSound->GetOwner()) SoundOwner->RemoveInstanceComponent(OldSound.Get());
        OldSound->DestroyComponent();
    }
    if (OldTexture) OldTexture->SetMediaPlayer(nullptr);
    if (OldPlayer) OldPlayer->Close();
    if (bResumeWorld && WorldToResume.IsValid()) UGameplayStatics::SetGamePaused(WorldToResume.Get(), false);
}

void UHczsUltimateVideoPlayer::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    bEndingPlay = true; Release();
    OnReadyNative.Clear(); OnStartedNative.Clear(); OnFinishedNative.Clear();
    Super::EndPlay(EndPlayReason);
}

void UHczsUltimateVideoPlayer::OnComponentDestroyed(bool bDestroyingHierarchy)
{
    bEndingPlay = true; Release();
    OnReadyNative.Clear(); OnStartedNative.Clear(); OnFinishedNative.Clear();
    Super::OnComponentDestroyed(bDestroyingHierarchy);
}

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsUltimateVideoLifecycleTest, "Hczs.Session.UltimateVideoLifecycle",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsUltimateVideoLifecycleTest::RunTest(const FString& Parameters)
{
    FHczsUltimateVideoLifecycle Gate;
    TestTrue(TEXT("fresh sequence opens once"), Gate.Begin(TEXT("video-a")) == EHczsUltimateVideoBegin::Fresh);
    const uint64 A = Gate.Generation;
    TestTrue(TEXT("repeat prepare does not replace decoder"), Gate.Begin(TEXT("video-a")) == EHczsUltimateVideoBegin::Idempotent);
    TestTrue(TEXT("another active sequence is rejected"), Gate.Begin(TEXT("video-b")) == EHczsUltimateVideoBegin::Rejected);
    TestFalse(TEXT("cannot play before async Ready"), Gate.RequestPlay(TEXT("video-a")));
    TestFalse(TEXT("end event during preparation cannot report playback completed"), Gate.Finish(A, EHczsUltimateVideoFinish::Completed));
    TestFalse(TEXT("another decoder's late callback cannot ready this sequence"), Gate.MarkReady(A + 1));
    TestTrue(TEXT("opened media becomes Ready once"), Gate.MarkReady(A));
    TestFalse(TEXT("duplicate Opened has no duplicate ready notification"), Gate.MarkReady(A));
    TestFalse(TEXT("another sequence cannot acquire playback"), Gate.RequestPlay(TEXT("video-b")));
    TestTrue(TEXT("explicit cue starts prepared video"), Gate.RequestPlay(TEXT("video-a")));
    TestTrue(TEXT("engine resumed notifies once"), Gate.MarkStarted(A));
    TestFalse(TEXT("repeated resumed/ticker observation does not repeat Started"), Gate.MarkStarted(A));
    TestTrue(TEXT("natural end has one terminal transition"), Gate.Finish(A, EHczsUltimateVideoFinish::Completed));
    TestFalse(TEXT("Closed/failure after natural end has no second finish"), Gate.Finish(A, EHczsUltimateVideoFinish::Failed));
    TestTrue(TEXT("same completed sequence cannot replay"), Gate.Begin(TEXT("video-a")) == EHczsUltimateVideoBegin::Rejected);
    TestTrue(TEXT("a new explicit sequence can run in finish callback"), Gate.Begin(TEXT("video-b")) == EHczsUltimateVideoBegin::Fresh);
    const uint64 B = Gate.Generation;
    TestFalse(TEXT("old callback cannot finish reentrant new sequence"), Gate.Finish(A, EHczsUltimateVideoFinish::Failed));
    TestFalse(TEXT("old release cannot clear reentrant new sequence"), Gate.ClearActive(A));
    TestTrue(TEXT("cancel during prepare transitions once"), Gate.Finish(B, EHczsUltimateVideoFinish::Cancelled));
    TestFalse(TEXT("Opened after cancellation cannot freeze actors"), Gate.MarkReady(B));
    Gate.ClearActive(B);
    TestTrue(TEXT("release resets active state"), Gate.State == EHczsUltimateVideoState::Idle);
    TestTrue(TEXT("retired sequence remains retired after release"), Gate.Begin(TEXT("video-a")) == EHczsUltimateVideoBegin::Rejected);
    TestTrue(TEXT("third sequence permits failure recovery"), Gate.Begin(TEXT("video-c")) == EHczsUltimateVideoBegin::Fresh);
    TestTrue(TEXT("immediate OpenSource false can terminate without OpenFailed event"), Gate.Finish(Gate.Generation, EHczsUltimateVideoFinish::Failed));
    TestFalse(TEXT("missing/delayed open callback cannot recover failed sequence"), Gate.MarkReady(Gate.Generation));
    return true;
}
#endif
