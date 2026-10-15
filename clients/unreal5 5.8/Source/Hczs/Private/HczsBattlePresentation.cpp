#include "HczsBattlePresentation.h"
#include "HczsUltimateSequence.h"
#include "HczsWeaponSourceFx.h"

#include "Animation/AnimSequence.h"
#include "Animation/AnimSingleNodeInstance.h"
#include "Animation/Skeleton.h"
#include "Components/SceneComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "HczsGameInstance.h"
#include "HAL/PlatformTime.h"

namespace
{
    constexpr int32 MaxPresentationEvents = 128;
    constexpr int32 MaxPresentationSteps = 128;
    constexpr float SourceEntranceSeconds = 3.7f;
    constexpr float SourceEntranceEffectRatio = 0.144595f;
    bool IsDead(const FHczsScalar& Hp) { return Hp.Approximate <= 0.0; }
    int64 VisualUnixMs() { const FDateTime Now = FDateTime::UtcNow(); return Now.ToUnixTimestamp() * 1000 + Now.GetMillisecond(); }
}

bool FHczsBattleSourceHit::HasReached(float ActualPositionSeconds, float ActualLengthSeconds) const
{
    return EventName == TEXT("attack") && FMath::IsFinite(NormalizedProgress) && NormalizedProgress > 0 && NormalizedProgress < 1 &&
        FMath::IsFinite(SourceDurationSeconds) && SourceDurationSeconds > 0 && FMath::IsFinite(ActualLengthSeconds) &&
        ActualLengthSeconds > 0 && FMath::Abs(ActualLengthSeconds - SourceDurationSeconds) <= 0.002f &&
        FMath::IsFinite(ActualPositionSeconds) && ActualPositionSeconds >= 0 && ActualPositionSeconds <= ActualLengthSeconds + 0.002f &&
        ActualPositionSeconds / ActualLengthSeconds >= NormalizedProgress;
}

void FHczsCardVisualGate::Reset()
{
    BattleId.Reset(); RequestId.Reset(); CardId.Reset(); StartRevision = 0;
    bConfirmed = false; bReactionReleased = false;
    ExpectedReactionCount = 0; ReleasedReactionCount = 0;
}
bool FHczsCardVisualGate::Begin(const FHczsBattleView& View, const FHczsCardIntentVisual& Intent, int32 ReactionCount)
{
    if (!View.bIsValid || View.Status != TEXT("player-turn") || !Intent.bDispatched ||
        Intent.RequestId.IsEmpty() || Intent.CardId.IsEmpty() || Intent.BattleId != View.Id ||
        Intent.ExpectedRevision != View.Revision || !RequestId.IsEmpty() || ReactionCount < 1 || ReactionCount > 2) return false;
    BattleId = Intent.BattleId; RequestId = Intent.RequestId; CardId = Intent.CardId;
    StartRevision = Intent.ExpectedRevision; ExpectedReactionCount = ReactionCount; return true;
}
bool FHczsCardVisualGate::Matches(const FHczsBattleView& View, const FHczsBattleVisualReceipt& Receipt) const
{
    return !RequestId.IsEmpty() && View.bIsValid && View.Id == BattleId && View.Revision == StartRevision + 1 &&
        Receipt.bValid && Receipt.BattleId == BattleId && Receipt.ActionIndex == View.ActionIndex &&
        Receipt.ActionIndex == StartRevision && Receipt.Events.ContainsByPredicate([this](const FHczsBattleVisualEvent& E)
        { return E.Type == TEXT("CardPlayed") && E.CardId == CardId; });
}
bool FHczsCardVisualGate::ReleaseReaction(bool bImpactReached)
{
    return ReleaseReaction(0, bImpactReached);
}
bool FHczsCardVisualGate::ReleaseReaction(int32 Ordinal, bool bImpactReached)
{
    if (!bConfirmed || !bImpactReached || RequestId.IsEmpty() || Ordinal != ReleasedReactionCount ||
        Ordinal < 0 || Ordinal >= ExpectedReactionCount) return false;
    ++ReleasedReactionCount; bReactionReleased = ReleasedReactionCount == ExpectedReactionCount;
    return true;
}

void FHczsBattlePresentationCursor::Reset()
{
    BattleId.Reset(); DefinitionId.Reset(); ActionIndex = -1; Revision = 0;
}

EHczsVisualSnapshotDecision FHczsBattlePresentationCursor::Observe(const FHczsBattleView& View, const FHczsBattleVisualReceipt& Receipt)
{
    if (!View.bIsValid || View.Id.IsEmpty() || View.ActionIndex < 0 || View.ActionIndex > 1000000 ||
        View.Revision != View.ActionIndex + 1) return EHczsVisualSnapshotDecision::Ignore;
    if (BattleId != View.Id || DefinitionId != View.DefinitionId)
    {
        BattleId = View.Id; DefinitionId = View.DefinitionId; ActionIndex = View.ActionIndex; Revision = View.Revision;
        return EHczsVisualSnapshotDecision::Baseline;
    }
    if (View.Revision <= Revision || View.ActionIndex <= ActionIndex) return EHczsVisualSnapshotDecision::Ignore;
    ActionIndex = View.ActionIndex; Revision = View.Revision;
    if (!Receipt.bValid || Receipt.BattleId != View.Id || Receipt.ActionIndex != View.ActionIndex ||
        Receipt.Events.IsEmpty() || Receipt.Events.Num() > MaxPresentationEvents)
        return EHczsVisualSnapshotDecision::SynchronizeOnly;
    return EHczsVisualSnapshotDecision::PresentReceipt;
}

AHczsBattlePresentation::AHczsBattlePresentation()
{
    PrimaryActorTick.bCanEverTick = true;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("PresentationRoot"));
    UltimateSequence = CreateDefaultSubobject<UHczsUltimateSequence>(TEXT("UltimateSequence"));
    WeaponSourceFx = CreateDefaultSubobject<UHczsWeaponSourceFx>(TEXT("WeaponSourceFx"));
    Tags.Add(TEXT("HCZSBattlePresentation"));
}

void AHczsBattlePresentation::BeginPlay()
{
    Super::BeginPlay();
    UltimateSequence->OnFinishedNative.AddUObject(this, &AHczsBattlePresentation::UltimateFinished);
    EnsureSceneReady();
    Session = Cast<UHczsGameInstance>(GetGameInstance());
    if (Session)
    {
        IntentDispatchedHandle = Session->OnCardIntentDispatchedNative.AddUObject(this, &AHczsBattlePresentation::IntentDispatched);
        IntentSettledHandle = Session->OnCardIntentSettledNative.AddUObject(this, &AHczsBattlePresentation::IntentSettled);
    }
}

void AHczsBattlePresentation::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    if (Session)
    {
        Session->OnCardIntentDispatchedNative.Remove(IntentDispatchedHandle);
        Session->OnCardIntentSettledNative.Remove(IntentSettledHandle);
    }
    CancelPresentation(); Cursor.Reset();
    WeaponSourceFx->Release();
    Session = nullptr;
    OnPresentationChangedNative.Clear();
    Super::EndPlay(EndPlayReason);
}

void AHczsBattlePresentation::IntentDispatched(const FHczsCardIntentVisual& Intent)
{
    if (!Session || !EnsureSceneReady() || !CanPresentBattle(Session->CurrentBattle) ||
        Session->Phase != EHczsSessionPhase::Battle || bPresentationBusy) return;
    if (Intent.CardId == TEXT("410104") && SceneAssets->SupportedEncounterId == TEXT("city-preview-10405"))
    {
        // Identity gate only: the count is not a mapping of ultimate hit events.
        if (!UltimateIntent.Begin(Session->CurrentBattle, Intent, 1)) return;
        DesiredSnapshot = Session->CurrentBattle;
        bUltimatePlaying = true; bUltimateIntentAborted = false; SetBusy(true);
        if (!UltimateSequence->PlayElsa(PlayerComponent, Intent.RequestId))
        { bUltimatePlaying = false; bUltimateIntentAborted = true; }
        return;
    }
    const auto* Sequence = SceneAssets->CardAnimationQueues.Find(Intent.CardId);
    if (!Sequence || Sequence->Clips.IsEmpty() || Sequence->Clips.Num() > MaxPresentationSteps ||
        !LocalCard.Begin(Session->CurrentBattle, Intent, Sequence->Clips.Num())) return;
    DesiredSnapshot = Session->CurrentBattle;
    LocalPlayerClips = Sequence->Clips; LocalPlayerClipIndex = 0;
    LocalImpactsReached.Init(false, LocalPlayerClips.Num()); LocalDamageEvents.Reset();
    bLocalClipHeldAtImpact = false; bLocalEnemyReacting = false;
    bWaitingForImpact = false; bLocalVisualAborted = false;
    SetBusy(true); PlayLocalPlayerClip();
    UE_LOG(LogTemp, Display, TEXT("HCZS card intent windup: request=%s revision=%lld atUnixMs=%lld; no predicted damage/state"),
        *Intent.RequestId, Intent.ExpectedRevision, VisualUnixMs());
}

void AHczsBattlePresentation::IntentSettled(const FString& RequestId, bool bConfirmed)
{
    if (UltimateIntent.RequestId == RequestId && !bConfirmed)
    {
        CancelPresentation();
        if (Session && CanPresentBattle(Session->CurrentBattle)) ApplyStablePose(Session->CurrentBattle);
        return;
    }
    if (LocalCard.RequestId != RequestId || bConfirmed) return;
    // Definite rejection/conflict or an unmatched latest state stops local-only visuals.
    // A transport failure stays unresolved in GI and does not invoke this callback.
    CancelPresentation();
    if (Session && CanPresentBattle(Session->CurrentBattle)) ApplyStablePose(Session->CurrentBattle);
}

void AHczsBattlePresentation::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (bEntrancePlaying)
    {
        // BeginPlay/map loading can precede the world's first delta. Starting
        // this clock in the first actor tick excludes that loading time.
        if (EntrancePhase == TEXT("waiting-hidden") && EntranceHiddenWorldStart < 0.0 &&
            Session && Session->IsFreshBattleEntranceActive(EntranceBattleId))
        {
            EntranceHiddenWorldStart = GetWorld()->GetTimeSeconds();
            EntranceHiddenRealStart = FPlatformTime::Seconds();
            GetWorldTimerManager().SetTimer(EntranceStartTimer, this, &AHczsBattlePresentation::StartEntranceClip, .5f, false);
            UE_LOG(LogTemp, Display, TEXT("HCZS entrance fresh-start: battle=%s source=fight_idle_show delay=0.5 worldTime=%.6f atUnixMs=%lld"),
                *EntranceBattleId, EntranceHiddenWorldStart, VisualUnixMs());
        }
        ObserveEntrance(); return;
    }
    ObserveLocalImpact();
    ReleaseLocalReaction();
}

float AHczsBattlePresentation::GetEntrancePosition() const
{
    const auto* Playback = PlayerComponent ? PlayerComponent->GetSingleNodeInstance() : nullptr;
    return bEntrancePlaying && Playback && Playback->GetAnimationAsset() == EntranceAnimation
        ? Playback->GetCurrentTime() : EntranceLastPosition;
}

bool AHczsBattlePresentation::TryPlayFreshEntrance(const FHczsBattleView& View)
{
    if (!Session) Session = Cast<UHczsGameInstance>(GetGameInstance());
    if (!Session || !Session->ConsumeFreshBattleEntrance(View.Id)) return false;
    EntranceBattleId = View.Id; EntranceLastPosition = 0; bEntranceEventEmitted = false;
    EntranceAnimation = LoadObject<UAnimSequence>(nullptr,
        TEXT("/Game/Recovered/Battle/Entrance/elsa_entrance.elsa_entrance"));
    if (!PlayerComponent || !SceneAssets || !SceneAssets->PlayerMesh || !EntranceAnimation ||
        EntranceAnimation->GetSkeleton() != SceneAssets->PlayerMesh->GetSkeleton() ||
        PlayerComponent->GetNumBones() != 180 || !FMath::IsFinite(EntranceAnimation->GetPlayLength()) ||
        FMath::Abs(EntranceAnimation->GetPlayLength() - SourceEntranceSeconds) > .002f)
    {
        EntrancePhase = TEXT("unavailable"); EntranceDiagnostic = TEXT("Source entrance asset, 180-bone battle skeleton or 3.7s duration mismatch; skipped.");
        Session->CompleteFreshBattleEntrance(EntranceBattleId);
        UE_LOG(LogTemp, Warning, TEXT("HCZS entrance unavailable: battle=%s; source entrance skipped, commands unlocked"), *View.Id);
        return false;
    }
    bEntrancePlaying = true; EntrancePhase = TEXT("waiting-hidden");
    EntranceHiddenWorldStart = -1.0; EntranceHiddenRealStart = -1.0; EntranceShowWorldStart = -1.0;
    EntranceDiagnostic = TEXT("Original BattleScene.playerShow: hidden, waiting 0.5 seconds.");
    EntranceDeadline = FPlatformTime::Seconds() + 6.5;
    // Source playerShow hides only our side. Entity6605 has no SHOW animation.
    SetSideVisible(false, false);
    SetBusy(true);
    UE_LOG(LogTemp, Display, TEXT("HCZS entrance prepared: battle=%s source=fight_idle_show waitingForFirstTick=1 atUnixMs=%lld"),
        *View.Id, VisualUnixMs());
    return true;
}

void AHczsBattlePresentation::StartEntranceClip()
{
    if (!bEntrancePlaying || EntrancePhase != TEXT("waiting-hidden") || EntranceHiddenWorldStart < 0.0) return;
    if (!Session || !Session->IsFreshBattleEntranceActive(EntranceBattleId) || !PlayerComponent || !EntranceAnimation)
    { StopEntrance(false, TEXT("session-or-source-changed")); return; }
    const double WorldNow = GetWorld()->GetTimeSeconds();
    const double HiddenElapsed = WorldNow - EntranceHiddenWorldStart;
    const double RealHiddenElapsed = FPlatformTime::Seconds() - EntranceHiddenRealStart;
    if (HiddenElapsed < .5 || RealHiddenElapsed < .5)
    {
        // TimerManager can consume the first loading delta after SetTimer.
        // Its callback is only a wake-up. A delayed loading delta can reach
        // the game clock a frame later too; it must not shorten the visible wait.
        GetWorldTimerManager().SetTimer(EntranceStartTimer, this, &AHczsBattlePresentation::StartEntranceClip,
            FMath::Max(.001f, static_cast<float>(FMath::Max(.5 - HiddenElapsed, .5 - RealHiddenElapsed))), false);
        return;
    }
    EntranceShowWorldStart = WorldNow;
    PlayerComponent->PlayAnimation(EntranceAnimation, false);
    PlayerComponent->SetPosition(0, false);
    PlayerComponent->SetPlayRate(1.0f);
    // Keep every authored translation, including the jump-in. No root-motion
    // extraction, upright correction or actor transform is applied here.
    EntrancePhase = TEXT("show-hidden"); EntranceDiagnostic = TEXT("Source SHOW playing; reveal after 0.01 seconds.");
    GetWorldTimerManager().SetTimer(EntranceVisibleTimer, this, &AHczsBattlePresentation::RevealEntrancePlayer, .01f, false);
    GetWorldTimerManager().SetTimer(EntranceFinishTimer, this, &AHczsBattlePresentation::CheckEntranceFinished,
        EntranceAnimation->GetPlayLength(), false);
    UE_LOG(LogTemp, Display, TEXT("HCZS entrance source SHOW: battle=%s duration=%.6f hiddenElapsed=%.6f worldTime=%.6f atUnixMs=%lld"),
        *EntranceBattleId, EntranceAnimation->GetPlayLength(), HiddenElapsed, WorldNow, VisualUnixMs());
}

void AHczsBattlePresentation::RevealEntrancePlayer()
{
    if (!bEntrancePlaying || EntrancePhase != TEXT("show-hidden") || EntranceShowWorldStart < 0.0) return;
    if (!Session || !Session->IsFreshBattleEntranceActive(EntranceBattleId))
    { StopEntrance(false, TEXT("session-changed-before-reveal")); return; }
    const double WorldNow = GetWorld()->GetTimeSeconds();
    const double ShowElapsed = WorldNow - EntranceShowWorldStart;
    if (ShowElapsed < .01)
    {
        GetWorldTimerManager().SetTimer(EntranceVisibleTimer, this, &AHczsBattlePresentation::RevealEntrancePlayer,
            FMath::Max(.001f, static_cast<float>(.01 - ShowElapsed)), false);
        return;
    }
    SetSideVisible(false, true); EntrancePhase = TEXT("show-visible");
    EntranceDiagnostic = TEXT("Original 3.7-second fight_idle_show; source event_1 effect not imported.");
    UE_LOG(LogTemp, Display, TEXT("HCZS entrance source visible: battle=%s showElapsed=%.6f worldTime=%.6f atUnixMs=%lld"),
        *EntranceBattleId, ShowElapsed, WorldNow, VisualUnixMs());
}

void AHczsBattlePresentation::ObserveEntrance()
{
    if (!bEntrancePlaying) return;
    if (!Session || !Session->IsFreshBattleEntranceActive(EntranceBattleId))
    { StopEntrance(false, TEXT("session-changed-or-entrance-permission-expired")); return; }
    if (FPlatformTime::Seconds() >= EntranceDeadline)
    { StopEntrance(false, TEXT("source-playback-watchdog")); return; }
    if (EntrancePhase == TEXT("waiting-hidden")) return;
    auto* Playback = PlayerComponent ? PlayerComponent->GetSingleNodeInstance() : nullptr;
    if (!Playback || !EntranceAnimation || Playback->GetAnimationAsset() != EntranceAnimation ||
        !FMath::IsFinite(Playback->GetCurrentTime()))
    { StopEntrance(false, TEXT("source-playback-interrupted")); return; }
    EntranceLastPosition = Playback->GetCurrentTime();
    if (!bEntranceEventEmitted && EntranceLastPosition / EntranceAnimation->GetPlayLength() >= SourceEntranceEffectRatio)
    {
        bEntranceEventEmitted = true;
        // Explicit source event hook. The original chuchang.sfx is not yet
        // imported, so do not substitute a generic flash or claim it played.
        UE_LOG(LogTemp, Display, TEXT("HCZS entrance source cue: battle=%s event=event_1 ratio=0.144595 position=%.6f socket=fx_center sfx=effects/player/001/fight_idle_show_chuchang.sfx effectPlayed=0 atUnixMs=%lld"),
            *EntranceBattleId, EntranceLastPosition, VisualUnixMs());
    }
    if (EntranceLastPosition >= EntranceAnimation->GetPlayLength() - .002f)
        StopEntrance(true, TEXT("source-SHOW-completed-to-idle_1"));
}

void AHczsBattlePresentation::CheckEntranceFinished()
{
    ObserveEntrance();
    // A timer is only a wake-up: completion follows the actual clip position.
    if (bEntrancePlaying)
        GetWorldTimerManager().SetTimer(EntranceFinishTimer, this, &AHczsBattlePresentation::CheckEntranceFinished, .02f, false);
}

void AHczsBattlePresentation::StopEntrance(bool bCompleted, const FString& Reason, bool bRestoreStablePose)
{
    if (!bEntrancePlaying) return;
    bEntrancePlaying = false;
    GetWorldTimerManager().ClearTimer(EntranceStartTimer);
    GetWorldTimerManager().ClearTimer(EntranceVisibleTimer);
    GetWorldTimerManager().ClearTimer(EntranceFinishTimer);
    if (Session) Session->CompleteFreshBattleEntrance(EntranceBattleId);
    EntranceDeadline = 0; EntranceHiddenWorldStart = -1.0; EntranceShowWorldStart = -1.0;
    EntrancePhase = bCompleted ? TEXT("complete") : TEXT("cancelled"); EntranceDiagnostic = Reason;
    if (bRestoreStablePose && bSceneReady) ApplyStablePose(DesiredSnapshot);
    SetBusy(false);
    UE_LOG(LogTemp, Display, TEXT("HCZS entrance finished: battle=%s completed=%d position=%.6f reason=%s atUnixMs=%lld"),
        *EntranceBattleId, bCompleted, EntranceLastPosition, *Reason, VisualUnixMs());
}

void AHczsBattlePresentation::ObserveLocalImpact()
{
    if (bLocalPlayerPlaying && LocalPlayerClips.IsValidIndex(LocalPlayerClipIndex) &&
        LocalImpactsReached.IsValidIndex(LocalPlayerClipIndex) && PlayerComponent)
    {
        const FString& Clip = LocalPlayerClips[LocalPlayerClipIndex];
        UAnimSequence* Animation = FindAnimation(false, Clip);
        auto* Playback = PlayerComponent->GetSingleNodeInstance();
        const auto* Hit = SceneAssets->PlayerHitEvents.Find(Clip);
        if (Animation && Hit && Playback && Playback->GetAnimationAsset() == Animation &&
            Animation->GetPlayLength() > 0 && !LocalImpactsReached[LocalPlayerClipIndex])
        {
            const float Progress = Playback->GetCurrentTime() / Animation->GetPlayLength();
            if (Hit->HasReached(Playback->GetCurrentTime(), Animation->GetPlayLength()))
            {
                LocalImpactsReached[LocalPlayerClipIndex] = true;
                UE_LOG(LogTemp, Display, TEXT("HCZS windup impact position: request=%s ordinal=%d clip=%s progress=%.6f sourceRatio=%.6f confirmed=%d atUnixMs=%lld"),
                    *LocalCard.RequestId, LocalPlayerClipIndex, *Clip, Progress, Hit->NormalizedProgress, LocalCard.bConfirmed, VisualUnixMs());
                // New-domain latency policy: hold this actual pose until authority
                // arrives. Never infer damage or race into the second strike.
                if (!LocalCard.bConfirmed)
                {
                    Playback->SetPlaying(false); bLocalClipHeldAtImpact = true;
                    GetWorldTimerManager().ClearTimer(LocalPlayerTimer);
                    UE_LOG(LogTemp, Display, TEXT("HCZS source impact held for authority: request=%s ordinal=%d atUnixMs=%lld"),
                        *LocalCard.RequestId, LocalPlayerClipIndex, VisualUnixMs());
                }
            }
        }
    }
}

bool AHczsBattlePresentation::ReleaseLocalReaction()
{
    const int32 Ordinal = LocalCard.ReleasedReactionCount;
    if (bLocalClipHeldAtImpact && LocalCard.bConfirmed)
    {
        const auto* Playback = PlayerComponent ? PlayerComponent->GetSingleNodeInstance() : nullptr;
        UAnimSequence* Attack = LocalPlayerClips.IsValidIndex(LocalPlayerClipIndex) ? FindAnimation(false, LocalPlayerClips[LocalPlayerClipIndex]) : nullptr;
        if (!Playback || !Attack || Playback->GetAnimationAsset() != Attack)
        { CancelPresentation(); ApplyStablePose(DesiredSnapshot); return false; }
    }
    if (!bLocalVisualAborted && LocalDamageEvents.IsValidIndex(Ordinal) &&
        LocalImpactsReached.IsValidIndex(Ordinal) && LocalCard.ReleaseReaction(Ordinal, LocalImpactsReached[Ordinal]))
    {
        UAnimSequence* Hit = FindAnimation(true, TEXT("hit_1"));
        if (!Hit || !EnemyComponent) { CancelPresentation(); ApplyStablePose(DesiredSnapshot); return false; }
        // Source HpAction -> HIT state reEnter restarts its animation/timer. The
        // next attack ordinal may interrupt this hit; its length is not spacing.
        GetWorldTimerManager().ClearTimer(LocalEnemyTimer);
        SetSideVisible(true, true); EnemyComponent->PlayAnimation(Hit, false); EnemyComponent->SetPosition(0, false);
        bLocalEnemyReacting = true;
        LocalEnemyDeadline = GetWorld()->GetTimeSeconds() + Hit->GetPlayLength() * 2.0 + 1.0;
        GetWorldTimerManager().SetTimer(LocalEnemyTimer, this, &AHczsBattlePresentation::FinishLocalEnemyReaction, Hit->GetPlayLength(), false);
        UE_LOG(LogTemp, Display, TEXT("HCZS confirmed reaction released: request=%s actionIndex=%lld ordinal=%d clip=%s atUnixMs=%lld"),
            *LocalCard.RequestId, DesiredSnapshot.ActionIndex, Ordinal, *LocalPlayerClips[Ordinal], VisualUnixMs());
        bWaitingForImpact = LocalCard.ReleasedReactionCount < LocalDamageEvents.Num();
        if (bLocalClipHeldAtImpact)
        {
            auto* Playback = PlayerComponent ? PlayerComponent->GetSingleNodeInstance() : nullptr;
            UAnimSequence* Attack = LocalPlayerClips.IsValidIndex(LocalPlayerClipIndex) ? FindAnimation(false, LocalPlayerClips[LocalPlayerClipIndex]) : nullptr;
            if (!Playback || !Attack || Playback->GetAnimationAsset() != Attack)
            { CancelPresentation(); ApplyStablePose(DesiredSnapshot); return false; }
            Playback->SetPlaying(true); bLocalClipHeldAtImpact = false;
            const float Remaining = FMath::Max(0.02f, Attack->GetPlayLength() - Playback->GetCurrentTime());
            LocalClipDeadline = GetWorld()->GetTimeSeconds() + Remaining * 2.0 + 1.0;
            GetWorldTimerManager().SetTimer(LocalPlayerTimer, this, &AHczsBattlePresentation::FinishLocalPlayerClip, Remaining, false);
        }
        return true;
    }
    return false;
}

bool AHczsBattlePresentation::PrepareLocalReactions(const TArray<FHczsBattleVisualEvent>& Events)
{
    LocalDamageEvents.Reset();
    int32 CardCount = 0;
    for (const auto& Event : Events)
    {
        if (Event.Type == TEXT("CardPlayed"))
        { if (Event.CardId != LocalCard.CardId) return false; ++CardCount; }
        else if (Event.Type == TEXT("DamageApplied"))
        { if (Event.Target != TEXT("enemy")) return false; LocalDamageEvents.Add(Event); }
        else if (Event.Type == TEXT("EnemySkillUsed")) return false;
    }
    if (CardCount != 1 || LocalDamageEvents.Num() > LocalPlayerClips.Num()) return false;
    LocalCard.ExpectedReactionCount = LocalDamageEvents.Num();
    if (!LocalDamageEvents.IsEmpty() && LocalDamageEvents.Num() < LocalPlayerClips.Num())
    {
        // A terminal first strike can omit later authority events. Do not invent
        // those omitted stages merely because a second source clip is available.
        LocalPlayerClips.SetNum(LocalDamageEvents.Num()); LocalImpactsReached.SetNum(LocalDamageEvents.Num());
    }
    if (LocalDamageEvents.IsEmpty())
    {
        // No authoritative damage means no confirmed visual hit to release.
        CancelPresentation(); ApplyStablePose(DesiredSnapshot); return false;
    }
    return true;
}

void AHczsBattlePresentation::FinishLocalEnemyReaction()
{
    if (!bLocalEnemyReacting || !EnemyComponent) return;
    UAnimSequence* Hit = FindAnimation(true, TEXT("hit_1"));
    const auto* Playback = EnemyComponent->GetSingleNodeInstance();
    if (!Hit || !Playback || Playback->GetAnimationAsset() != Hit)
    { CancelPresentation(); ApplyStablePose(DesiredSnapshot); return; }
    if (Playback->GetCurrentTime() + 0.002f < Hit->GetPlayLength())
    {
        if (GetWorld()->GetTimeSeconds() < LocalEnemyDeadline)
        { GetWorldTimerManager().SetTimer(LocalEnemyTimer, this, &AHczsBattlePresentation::FinishLocalEnemyReaction, 0.02f, false); return; }
        CancelPresentation(); ApplyStablePose(DesiredSnapshot); return;
    }
    bLocalEnemyReacting = false;
    EnemyComponent->PlayAnimation(FindAnimation(true, TEXT("idle")), true);
    FinishVisualsIfIdle();
}

void AHczsBattlePresentation::PlayLocalPlayerClip()
{
    if (!LocalPlayerClips.IsValidIndex(LocalPlayerClipIndex))
    {
        bLocalPlayerPlaying = false;
        FinishVisualsIfIdle(); return;
    }
    UAnimSequence* Animation = FindAnimation(false, LocalPlayerClips[LocalPlayerClipIndex]);
    if (!Animation || !PlayerComponent || !FMath::IsFinite(Animation->GetPlayLength()) ||
        Animation->GetPlayLength() <= 0 || Animation->GetSkeleton() != SceneAssets->PlayerMesh->GetSkeleton())
    { CancelPresentation(true); ApplyStablePose(DesiredSnapshot); return; }
    bLocalPlayerPlaying = true; SetSideVisible(false, true);
    PlayerComponent->PlayAnimation(Animation, false); PlayerComponent->SetPosition(0, false);
    LocalClipDeadline = GetWorld()->GetTimeSeconds() + Animation->GetPlayLength() * 2.0 + 1.0;
    GetWorldTimerManager().SetTimer(LocalPlayerTimer, this, &AHczsBattlePresentation::FinishLocalPlayerClip, Animation->GetPlayLength(), false);
}

void AHczsBattlePresentation::FinishLocalPlayerClip()
{
    if (!bLocalPlayerPlaying || bLocalClipHeldAtImpact) return;
    UAnimSequence* Animation = LocalPlayerClips.IsValidIndex(LocalPlayerClipIndex)
        ? FindAnimation(false, LocalPlayerClips[LocalPlayerClipIndex]) : nullptr;
    const auto* Playback = PlayerComponent ? PlayerComponent->GetSingleNodeInstance() : nullptr;
    if (!Animation || !Playback || Playback->GetAnimationAsset() != Animation)
    { CancelPresentation(true); ApplyStablePose(DesiredSnapshot); return; }
    // Timer callbacks can precede skeletal animation evaluation by a frame.
    // Wait for the real clip, never promote nominal elapsed time to a hit.
    if (Playback->GetCurrentTime() + 0.002f < Animation->GetPlayLength())
    {
        if (GetWorld()->GetTimeSeconds() < LocalClipDeadline)
        { GetWorldTimerManager().SetTimer(LocalPlayerTimer, this, &AHczsBattlePresentation::FinishLocalPlayerClip, 0.02f, false); return; }
        UE_LOG(LogTemp, Warning, TEXT("HCZS local windup stopped before its final pose; restore authoritative state without synthetic impact"));
        CancelPresentation(true); ApplyStablePose(DesiredSnapshot); return;
    }
    ObserveLocalImpact();
    ReleaseLocalReaction();
    if (bLocalClipHeldAtImpact || !bLocalPlayerPlaying) return;
    ++LocalPlayerClipIndex; PlayLocalPlayerClip();
}

void AHczsBattlePresentation::FinishVisualsIfIdle()
{
    if (bEntrancePlaying || bUltimatePlaying || bLocalPlayerPlaying || bWaitingForImpact || bLocalEnemyReacting) return;
    if (!UltimateIntent.RequestId.IsEmpty() && !UltimateIntent.bConfirmed) return;
    if (Queue.IsValidIndex(QueueIndex))
    {
        if (!GetWorldTimerManager().IsTimerActive(StepTimer)) PlayNextStep();
        return;
    }
    // Clear a completed confirmed sequence; unresolved transport retains its
    // intent identity and holds its actual attack pose until retry/rejection.
    ApplyStablePose(DesiredSnapshot); Queue.Reset(); QueueIndex = 0; UltimateIntent.Reset();
    if (LocalCard.bConfirmed) LocalCard.Reset();
    SetBusy(false);
}

bool AHczsBattlePresentation::EnsureSceneReady()
{
    if (bSceneReady) return true;
    if (!SceneAssets || !SceneAssets->PlayerMesh || !SceneAssets->EnemyMesh)
    {
        UE_LOG(LogTemp, Error, TEXT("HCZS battle presentation has no verified scene DataAsset/meshes")); return false;
    }
    auto Bind = [this](FName Tag, USkeletalMesh* Expected, TObjectPtr<USkeletalMeshComponent>& Out)
    {
        TArray<AActor*> Found; UGameplayStatics::GetAllActorsWithTag(GetWorld(), Tag, Found);
        if (Found.Num() != 1) return false;
        auto* Component = Found[0]->FindComponentByClass<USkeletalMeshComponent>();
        if (!Component || Component->GetSkeletalMeshAsset() != Expected) return false;
        Out = Component;
        Out->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
        return true;
    };
    if (!Bind(TEXT("HCZSBattlePlayer"), SceneAssets->PlayerMesh, PlayerComponent) ||
        !Bind(TEXT("HCZSBattleEnemy"), SceneAssets->EnemyMesh, EnemyComponent))
    {
        UE_LOG(LogTemp, Error, TEXT("HCZS battle actor tags or original mesh references are incomplete")); return false;
    }
    for (bool bEnemy : {false, true})
    {
        USkeleton* Expected = (bEnemy ? SceneAssets->EnemyMesh : SceneAssets->PlayerMesh)->GetSkeleton();
        for (const FString& Clip : {bEnemy ? FString(TEXT("idle")) : FString(TEXT("idle_1")),
                                   bEnemy ? FString(TEXT("hit_1")) : FString(TEXT("hit_2")), FString(TEXT("death"))})
        {
            UAnimSequence* Animation = FindAnimation(bEnemy, Clip);
            if (!Animation || Animation->GetSkeleton() != Expected || !FMath::IsFinite(Animation->GetPlayLength()) || Animation->GetPlayLength() <= 0)
            {
                UE_LOG(LogTemp, Error, TEXT("HCZS original battle animation is missing/incompatible: %s"), *Clip); return false;
            }
        }
    }
    if (SceneAssets->SourceHitTimingSHA256.Len() != 64)
    { UE_LOG(LogTemp, Error, TEXT("HCZS battle needs source hit-event manifest import")); return false; }
    for (const auto& Pair : SceneAssets->CardAnimationQueues)
    {
        if (Pair.Value.Clips.IsEmpty() || Pair.Value.Clips.Num() > 2) return false;
        for (const FString& Clip : Pair.Value.Clips)
        {
            UAnimSequence* Animation = FindAnimation(false, Clip);
            const auto* Hit = SceneAssets->PlayerHitEvents.Find(Clip);
            if (!Animation || !Hit || Hit->EventName != TEXT("attack") || !FMath::IsFinite(Hit->NormalizedProgress) ||
                Hit->NormalizedProgress <= 0 || Hit->NormalizedProgress >= 1 || !FMath::IsFinite(Hit->SourceDurationSeconds) ||
                FMath::Abs(Animation->GetPlayLength() - Hit->SourceDurationSeconds) > 0.002f)
            { UE_LOG(LogTemp, Error, TEXT("HCZS authored hit event missing/incompatible: %s"), *Clip); return false; }
        }
    }
    for (const auto& Pair : SceneAssets->EnemySkillClips)
        if (!FindAnimation(true, Pair.Value)) return false;
    TArray<AActor*> Weapons; UGameplayStatics::GetAllActorsWithTag(GetWorld(), TEXT("HCZSBattleWeapon"), Weapons);
    if (Weapons.Num() != 1) return false;
    WeaponActor = Weapons[0];
    // Independent original weapon001 overlay; it does not advance combat or
    // stand in for the separate weapon_dao particle group.
    WeaponSourceFx->Initialise(PlayerComponent, WeaponActor);
    PlayerComponent->PlayAnimation(FindAnimation(false, TEXT("idle_1")), true);
    EnemyComponent->PlayAnimation(FindAnimation(true, TEXT("idle")), true);
    bSceneReady = true;
    UE_LOG(LogTemp, Display, TEXT("HCZS battle presentation ready: encounter=%s enemy=%s"), *SceneAssets->SupportedEncounterId, *SceneAssets->EnemyId);
    return true;
}

UAnimSequence* AHczsBattlePresentation::FindAnimation(bool bEnemy, const FString& Clip) const
{
    if (!SceneAssets) return nullptr;
    const auto& Map = bEnemy ? SceneAssets->EnemyAnimations : SceneAssets->PlayerAnimations;
    const auto* Found = Map.Find(Clip);
    return Found ? Found->Get() : nullptr;
}

bool AHczsBattlePresentation::CanPresentBattle(const FHczsBattleView& View) const
{
    if (!SceneAssets || !View.bIsValid || View.PlayerId != SceneAssets->PlayerId || View.EnemyId != SceneAssets->EnemyId) return false;
    return View.EncounterId == SceneAssets->SupportedEncounterId ||
        (View.EncounterId.IsEmpty() && View.DefinitionId.StartsWith(SceneAssets->SupportedEncounterId + TEXT("-")));
}

void AHczsBattlePresentation::ApplySnapshot(const FHczsBattleView& View, const FHczsBattleVisualReceipt& Receipt)
{
    if (!EnsureSceneReady()) return;
    if (!CanPresentBattle(View))
    {
        CancelPresentation(); SetSideVisible(false, false); SetSideVisible(true, false); Cursor.Reset();
        if (!bUnsupportedLogged)
            UE_LOG(LogTemp, Warning, TEXT("HCZS scene cannot represent this encounter/actor identity; source actors remain hidden"));
        bUnsupportedLogged = true; return;
    }
    bUnsupportedLogged = false;
    const EHczsVisualSnapshotDecision Decision = Cursor.Observe(View, Receipt);
    if (Decision == EHczsVisualSnapshotDecision::Ignore) return;
    const bool bMatchingUltimate = Decision == EHczsVisualSnapshotDecision::PresentReceipt && UltimateIntent.Matches(View, Receipt);
    if (bMatchingUltimate)
    {
        UltimateIntent.bConfirmed = true; DesiredSnapshot = View;
        if (bUltimateIntentAborted) { CancelPresentation(); ApplyStablePose(View); return; }
        // Reactions still use the confirmed receipt queue. Do not invent an
        // eight-damage/nine-cue correspondence until that mapping is recovered.
        BuildQueue(View, Receipt.Events); QueueIndex = 0;
        SetBusy(bUltimatePlaying || !Queue.IsEmpty());
        if (!bUltimatePlaying) FinishVisualsIfIdle();
        return;
    }
    const bool bMatchingWindup = Decision == EHczsVisualSnapshotDecision::PresentReceipt && LocalCard.Matches(View, Receipt);
    if (!bMatchingWindup) CancelPresentation();
    else
    {
        LocalCard.bConfirmed = true;
        UE_LOG(LogTemp, Display, TEXT("HCZS visual receipt accepted: request=%s revision=%lld actionIndex=%lld atUnixMs=%lld"),
            *LocalCard.RequestId, View.Revision, View.ActionIndex, VisualUnixMs());
    }
    DesiredSnapshot = View;
    if (bMatchingWindup && bLocalVisualAborted)
    {
        // A stopped/interrupted local clip has already started once. Synchronize
        // authority without replaying it or inventing an unobserved impact.
        CancelPresentation(); ApplyStablePose(View); return;
    }
    if (Decision != EHczsVisualSnapshotDecision::PresentReceipt)
    {
        ApplyStablePose(View);
        if (Decision == EHczsVisualSnapshotDecision::Baseline && TryPlayFreshEntrance(View)) return;
        UE_LOG(LogTemp, Display, TEXT("HCZS battle visual baseline: actionIndex=%lld; no historical action replay"), View.ActionIndex);
        return;
    }
    if (bMatchingWindup && !PrepareLocalReactions(Receipt.Events))
    { CancelPresentation(); ApplyStablePose(View); return; }
    BuildQueue(View, Receipt.Events);
    QueueIndex = 0;
    bWaitingForImpact = bMatchingWindup && LocalCard.ReleasedReactionCount < LocalDamageEvents.Num();
    SetBusy(bLocalPlayerPlaying || bWaitingForImpact || bLocalEnemyReacting || !Queue.IsEmpty());
    UE_LOG(LogTemp, Display, TEXT("HCZS confirmed receipt visual sequence: actionIndex=%lld steps=%d; HP/round remain server-owned"), View.ActionIndex, Queue.Num());
    if (bMatchingWindup)
    {
        ReleaseLocalReaction(); FinishVisualsIfIdle();
    }
    else if (!Queue.IsEmpty()) PlayNextStep();
    else FinishVisualsIfIdle();
}

void AHczsBattlePresentation::QueueClip(bool bEnemy, const FString& Clip, bool bDeath)
{
    if (Queue.Num() >= MaxPresentationSteps || !FindAnimation(bEnemy, Clip)) return;
    Queue.Add(FHczsBattleAnimationStep{bEnemy, bDeath, Clip});
}

void AHczsBattlePresentation::BuildQueue(const FHczsBattleView& View, const TArray<FHczsBattleVisualEvent>& Events)
{
    Queue.Reset();
    for (const auto& Event : Events)
    {
        if (Event.Type == TEXT("CardPlayed"))
        {
            if (UltimateIntent.bConfirmed && Event.CardId == UltimateIntent.CardId) continue;
            if (LocalCard.bConfirmed && Event.CardId == LocalCard.CardId) continue;
            if (Event.CardId == TEXT("410104") && SceneAssets->SupportedEncounterId == TEXT("city-preview-10405"))
            {
                Queue.Add(FHczsBattleAnimationStep{false, false, TEXT("__elsa_ultimate_sequence")});
                continue;
            }
            const auto* Sequence = SceneAssets->CardAnimationQueues.Find(Event.CardId);
            if (Sequence) for (const FString& Clip : Sequence->Clips) QueueClip(false, Clip);
            else UE_LOG(LogTemp, Display, TEXT("HCZS card has no recovered animation mapping: %s"), *Event.CardId);
        }
        else if (Event.Type == TEXT("EnemySkillUsed"))
        {
            const auto* Clip = SceneAssets->EnemySkillClips.Find(Event.SkillId);
            if (Clip) QueueClip(true, *Clip);
            else UE_LOG(LogTemp, Display, TEXT("HCZS enemy skill has no recovered animation mapping: %s"), *Event.SkillId);
        }
        else if (Event.Type == TEXT("DamageApplied"))
        {
            if (LocalCard.bConfirmed && Event.Target == TEXT("enemy")) continue;
            if (Event.Target == TEXT("player")) QueueClip(false, TEXT("hit_2"));
            else if (Event.Target == TEXT("enemy")) QueueClip(true, TEXT("hit_1"));
        }
    }
    // Confirmed local card reactions are released separately at each clip's
    // authored attack event, not serialized by the hit animation's duration.
    if (IsDead(View.PlayerHp)) QueueClip(false, TEXT("death"), true);
    if (IsDead(View.EnemyHp)) QueueClip(true, TEXT("death"), true);
    bPlayerDeathPresented = false; bEnemyDeathPresented = false;
}

void AHczsBattlePresentation::PlayNextStep()
{
    if (!bPresentationBusy || bUltimatePlaying) return;
    if (!Queue.IsValidIndex(QueueIndex))
    {
        Queue.Reset(); QueueIndex = 0; FinishVisualsIfIdle(); return;
    }
    const auto& Step = Queue[QueueIndex];
    if (Step.Clip == TEXT("__elsa_ultimate_sequence"))
    {
        bUltimatePlaying = true;
        const FString Id = FString::Printf(TEXT("%s:%lld:%lld"), *DesiredSnapshot.Id, DesiredSnapshot.Revision, DesiredSnapshot.ActionIndex);
        if (!UltimateSequence->PlayElsa(PlayerComponent, Id))
        { bUltimatePlaying = false; CancelPresentation(); ApplyStablePose(DesiredSnapshot); }
        return;
    }
    UAnimSequence* Animation = FindAnimation(Step.bEnemy, Step.Clip);
    auto* Component = Step.bEnemy ? EnemyComponent.Get() : PlayerComponent.Get();
    if (!Animation || !Component || !FMath::IsFinite(Animation->GetPlayLength()) || Animation->GetPlayLength() <= 0)
    {
        UE_LOG(LogTemp, Error, TEXT("HCZS visual clip disappeared; restore authoritative stable pose"));
        CancelPresentation(); ApplyStablePose(DesiredSnapshot); return;
    }
    // Keep the other live side in its exact source idle. A finished death stays hidden.
    const bool bOtherEnemy = !Step.bEnemy;
    const bool bOtherDied = bOtherEnemy ? bEnemyDeathPresented : bPlayerDeathPresented;
    if (!bOtherDied && !(bLocalPlayerPlaying && !bOtherEnemy))
    {
        auto* Other = bOtherEnemy ? EnemyComponent.Get() : PlayerComponent.Get();
        Other->PlayAnimation(FindAnimation(bOtherEnemy, bOtherEnemy ? TEXT("idle") : TEXT("idle_1")), true);
    }
    bRunningEnemy = Step.bEnemy; bRunningDeath = Step.bDeath;
    SetSideVisible(Step.bEnemy, true);
    Component->PlayAnimation(Animation, false);
    Component->SetPosition(0, false);
    UE_LOG(LogTemp, Display, TEXT("HCZS source animation playing: side=%s clip=%s duration=%.6f"),
        Step.bEnemy ? TEXT("enemy") : TEXT("player"), *Step.Clip, Animation->GetPlayLength());
    GetWorldTimerManager().SetTimer(StepTimer, this, &AHczsBattlePresentation::FinishStep, Animation->GetPlayLength(), false);
}

void AHczsBattlePresentation::FinishStep()
{
    if (!bPresentationBusy || !Queue.IsValidIndex(QueueIndex)) return;
    if (bRunningDeath)
    {
        if (bRunningEnemy) bEnemyDeathPresented = true; else bPlayerDeathPresented = true;
        SetSideVisible(bRunningEnemy, false);
    }
    ++QueueIndex; PlayNextStep();
}

void AHczsBattlePresentation::CancelPresentation(bool bKeepUnconfirmedIntent)
{
    StopEntrance(false, TEXT("presentation-cancelled"), false);
    bUltimatePlaying = false;
    if (UltimateSequence) UltimateSequence->Cancel();
    UltimateIntent.Reset(); bUltimateIntentAborted = false;
    const bool bKeep = bKeepUnconfirmedIntent && !LocalCard.bConfirmed && !LocalCard.RequestId.IsEmpty();
    if (!LocalCard.RequestId.IsEmpty())
        UE_LOG(LogTemp, Display, TEXT("HCZS visual intent cleared: request=%s abortedPending=%d atUnixMs=%lld"),
            *LocalCard.RequestId, bKeep, VisualUnixMs());
    GetWorldTimerManager().ClearTimer(StepTimer);
    GetWorldTimerManager().ClearTimer(LocalPlayerTimer);
    GetWorldTimerManager().ClearTimer(LocalEnemyTimer);
    LocalPlayerClips.Reset(); LocalPlayerClipIndex = 0; LocalClipDeadline = 0.0;
    LocalImpactsReached.Reset(); LocalDamageEvents.Reset(); LocalEnemyDeadline = 0.0;
    bLocalClipHeldAtImpact = false; bLocalEnemyReacting = false;
    bLocalPlayerPlaying = false; bWaitingForImpact = false;
    bLocalVisualAborted = bKeep;
    if (!bKeep) LocalCard.Reset();
    Queue.Reset(); QueueIndex = 0; SetBusy(false);
}

void AHczsBattlePresentation::UltimateFinished(const FString& Id, bool bSuccess, const FString& Error)
{
    if (!bUltimatePlaying) return;
    bUltimatePlaying = false;
    if (!UltimateIntent.RequestId.IsEmpty())
    {
        bUltimateIntentAborted = !bSuccess;
        if (!UltimateIntent.bConfirmed) return; // Keep the request lock until authority resolves it.
        if (!bSuccess) { CancelPresentation(); ApplyStablePose(DesiredSnapshot); return; }
        FinishVisualsIfIdle();
        return;
    }
    if (!bSuccess)
    { CancelPresentation(); ApplyStablePose(DesiredSnapshot); return; }
    ++QueueIndex;
    PlayNextStep();
}

void AHczsBattlePresentation::SetSideVisible(bool bEnemy, bool bVisible)
{
    auto* Component = bEnemy ? EnemyComponent.Get() : PlayerComponent.Get();
    if (Component)
    {
        Component->SetVisibility(bVisible, true);
        Component->GetOwner()->SetActorHiddenInGame(!bVisible);
    }
    if (!bEnemy && WeaponActor) WeaponActor->SetActorHiddenInGame(!bVisible);
}

void AHczsBattlePresentation::ApplyStablePose(const FHczsBattleView& View)
{
    bPlayerDeathPresented = IsDead(View.PlayerHp); bEnemyDeathPresented = IsDead(View.EnemyHp);
    for (bool bEnemy : {false, true})
    {
        auto* Component = bEnemy ? EnemyComponent.Get() : PlayerComponent.Get();
        const bool bDead = bEnemy ? bEnemyDeathPresented : bPlayerDeathPresented;
        SetSideVisible(bEnemy, !bDead);
        if (Component)
        {
            if (bDead) Component->Stop();
            else Component->PlayAnimation(FindAnimation(bEnemy, bEnemy ? TEXT("idle") : TEXT("idle_1")), true);
        }
    }
}

void AHczsBattlePresentation::SetBusy(bool bBusy)
{
    if (bPresentationBusy == bBusy) return;
    bPresentationBusy = bBusy; OnPresentationChangedNative.Broadcast();
}

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsBattlePresentationGateTest, "Hczs.Session.BattlePresentationGate",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsBattlePresentationGateTest::RunTest(const FString& Parameters)
{
    FHczsBattlePresentationCursor Gate;
    FHczsBattleView View; View.bIsValid = true; View.Id = TEXT("battle-a"); View.DefinitionId = TEXT("tutorial-a");
    View.ActionIndex = 5; View.Revision = 6;
    FHczsBattleVisualReceipt Receipt; Receipt.bValid = true; Receipt.BattleId = View.Id; Receipt.ActionIndex = 5;
    FHczsBattleVisualEvent Card; Card.Type = TEXT("CardPlayed"); Card.CardId = TEXT("110001"); Receipt.Events.Add(Card);
    TestTrue(TEXT("continuation builds baseline despite retained events"), Gate.Observe(View, Receipt) == EHczsVisualSnapshotDecision::Baseline);
    TestTrue(TEXT("repeat GET/receipt cannot replay"), Gate.Observe(View, Receipt) == EHczsVisualSnapshotDecision::Ignore);
    View.ActionIndex = 6; View.Revision = 7; Receipt.ActionIndex = 6;
    TestTrue(TEXT("one matching newly confirmed receipt is presented"), Gate.Observe(View, Receipt) == EHczsVisualSnapshotDecision::PresentReceipt);
    TestTrue(TEXT("same action is presented at most once"), Gate.Observe(View, Receipt) == EHczsVisualSnapshotDecision::Ignore);
    View.ActionIndex = 7; View.Revision = 8;
    TestTrue(TEXT("stale receipt only synchronizes current authoritative pose"), Gate.Observe(View, Receipt) == EHczsVisualSnapshotDecision::SynchronizeOnly);
    View.ActionIndex = 6; View.Revision = 7;
    TestTrue(TEXT("older state cannot rewind gate"), Gate.Observe(View, Receipt) == EHczsVisualSnapshotDecision::Ignore);
    View.Id = TEXT("battle-b"); View.ActionIndex = 0; View.Revision = 1;
    TestTrue(TEXT("new battle resets presentation baseline"), Gate.Observe(View, Receipt) == EHczsVisualSnapshotDecision::Baseline);
    View.ActionIndex = 1; View.Revision = 2; Receipt.ActionIndex = 1;
    TestTrue(TEXT("another battle's receipt is never consumed"), Gate.Observe(View, Receipt) == EHczsVisualSnapshotDecision::SynchronizeOnly);
    View.ActionIndex = 2; View.Revision = 99;
    TestTrue(TEXT("inconsistent state identity ignored"), Gate.Observe(View, Receipt) == EHczsVisualSnapshotDecision::Ignore);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsCardVisualTimingGateTest, "Hczs.Session.CardVisualTimingGate",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsCardVisualTimingGateTest::RunTest(const FString& Parameters)
{
    FHczsBattleView Before; Before.bIsValid = true; Before.Id = TEXT("battle-a");
    Before.Status = TEXT("player-turn"); Before.Revision = 1; Before.ActionIndex = 0;
    FHczsCardIntentVisual Intent; Intent.RequestId = TEXT("request-a"); Intent.BattleId = Before.Id;
    Intent.CardId = TEXT("110001"); Intent.ExpectedRevision = 1; Intent.bDispatched = true;
    FHczsCardVisualGate Gate;
    TestTrue(TEXT("accepted local send can begin before any receipt"), Gate.Begin(Before, Intent));
    TestFalse(TEXT("transport retry cannot restart windup"), Gate.Begin(Before, Intent));
    TestFalse(TEXT("impact without authority cannot cause hit/death"), Gate.ReleaseReaction(true));
    FHczsBattleView After = Before; After.Revision = 2; After.ActionIndex = 1;
    FHczsBattleVisualReceipt Receipt; Receipt.bValid = true; Receipt.BattleId = Before.Id; Receipt.ActionIndex = 1;
    FHczsBattleVisualEvent Card; Card.Type = TEXT("CardPlayed"); Card.CardId = Intent.CardId; Receipt.Events.Add(Card);
    TestTrue(TEXT("late exact receipt matches already played local intent"), Gate.Matches(After, Receipt));
    Gate.bConfirmed = true;
    TestFalse(TEXT("early confirmation waits for actual attack progress"), Gate.ReleaseReaction(false));
    TestTrue(TEXT("confirmed impact releases reactions once"), Gate.ReleaseReaction(true));
    TestFalse(TEXT("duplicate receipt cannot repeat reaction"), Gate.ReleaseReaction(true));
    Receipt.ActionIndex = 0;
    TestFalse(TEXT("historical receipt never matches a current intent"), Gate.Matches(After, Receipt));
    Receipt.ActionIndex = 1; After.Id = TEXT("another-battle");
    TestFalse(TEXT("scene/battle identity prevents late cross-scene reaction"), Gate.Matches(After, Receipt));
    Gate.Reset();
    TestFalse(TEXT("definite rejection/reset suppresses late reaction"), Gate.ReleaseReaction(true));
    Intent.bDispatched = false;
    TestFalse(TEXT("request not accepted by HTTP cannot preview"), Gate.Begin(Before, Intent));
    Intent.bDispatched = true; Intent.ExpectedRevision = 2;
    TestFalse(TEXT("obsolete release cannot begin"), Gate.Begin(Before, Intent));
    Intent.ExpectedRevision = 1; Intent.RequestId = TEXT("request-b");
    TestTrue(TEXT("fresh explicit action after rejection is allowed"), Gate.Begin(Before, Intent));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsSourceHitClockTest, "Hczs.Session.SourceHitClock",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsSourceHitClockTest::RunTest(const FString& Parameters)
{
    FHczsBattleSourceHit Hit; Hit.EventName = TEXT("attack"); Hit.NormalizedProgress = 0.230700f;
    Hit.SourceDurationSeconds = 0.8666667f;
    TestFalse(TEXT("ordinary source slash cannot hit before its authored event"), Hit.HasReached(0.19f, Hit.SourceDurationSeconds));
    TestTrue(TEXT("source slash crosses event before the old halfway adapter"), Hit.HasReached(0.201f, Hit.SourceDurationSeconds));
    TestFalse(TEXT("unmatched clip duration cannot impersonate source progress"), Hit.HasReached(0.8f, 1.2f));
    TestFalse(TEXT("invalid position never produces an impact"), Hit.HasReached(-1.0f, Hit.SourceDurationSeconds));
    TestFalse(TEXT("nominal time beyond actual clip is not a playback observation"), Hit.HasReached(3.0f, Hit.SourceDurationSeconds));
    Hit.EventName = TEXT("vo");
    TestFalse(TEXT("voice cue cannot become a damage event"), Hit.HasReached(0.7f, Hit.SourceDurationSeconds));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsMultiHitTimingGateTest, "Hczs.Session.MultiHitTimingGate",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsMultiHitTimingGateTest::RunTest(const FString& Parameters)
{
    FHczsBattleView Before; Before.bIsValid = true; Before.Id = TEXT("two-hit-battle");
    Before.Status = TEXT("player-turn"); Before.Revision = 7; Before.ActionIndex = 6;
    FHczsCardIntentVisual Intent; Intent.bDispatched = true; Intent.RequestId = TEXT("two-hit-request");
    Intent.BattleId = Before.Id; Intent.CardId = TEXT("410101"); Intent.ExpectedRevision = Before.Revision;
    FHczsCardVisualGate Gate;
    TestTrue(TEXT("two-hit intent starts with one identity"), Gate.Begin(Before, Intent, 2));
    TestFalse(TEXT("first impact during delayed authority has no reaction"), Gate.ReleaseReaction(0, true));
    Gate.bConfirmed = true;
    TestFalse(TEXT("second impact cannot overtake the first ordinal"), Gate.ReleaseReaction(1, true));
    TestTrue(TEXT("authority releases first impact exactly once"), Gate.ReleaseReaction(0, true));
    TestFalse(TEXT("first clip confirmation cannot release second impact early"), Gate.ReleaseReaction(1, false));
    TestFalse(TEXT("duplicate first reaction is rejected while second is pending"), Gate.ReleaseReaction(0, true));
    TestTrue(TEXT("second actual clip impact releases its own ordinal"), Gate.ReleaseReaction(1, true));
    TestFalse(TEXT("no third hit from the unused animation list candidate"), Gate.ReleaseReaction(2, true));
    TestFalse(TEXT("transport retry never replays either stage"), Gate.Begin(Before, Intent, 2));
    TestTrue(TEXT("both confirmed ordinals are completed"), Gate.bReactionReleased);
    Gate.Reset();
    TestFalse(TEXT("scene destruction/rejection suppresses late ordinal"), Gate.ReleaseReaction(1, true));
    TestTrue(TEXT("fresh explicit action can start after reset"), Gate.Begin(Before, Intent, 2));
    Gate.ExpectedReactionCount = 1; Gate.bConfirmed = true;
    TestTrue(TEXT("terminal first damage event is presented once"), Gate.ReleaseReaction(0, true));
    TestFalse(TEXT("missing terminal second damage must not be manufactured"), Gate.ReleaseReaction(1, true));
    return true;
}
#endif
