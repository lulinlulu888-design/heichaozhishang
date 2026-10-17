#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "GameFramework/Actor.h"
#include "HczsSessionTypes.h"
#include "TimerManager.h"
#include "HczsBattlePresentation.generated.h"

class UAnimSequence;
class UAudioComponent;
class USkeletalMesh;
class USkeletalMeshComponent;
class UHczsGameInstance;
class UHczsUltimateSequence;
class UHczsWeaponSourceFx;
class UHczsEntranceSourceFx;
struct FHczsCardIntentVisual;

/** Original source clip names; actual imported UObject references live in the maps below. */
USTRUCT(BlueprintType)
struct HCZS_API FHczsBattleAnimationSequence
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Recovered") TArray<FString> Clips;
};

/** Authored .ags attack event for one exact original animation clip. */
USTRUCT(BlueprintType)
struct HCZS_API FHczsBattleSourceHit
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, Category="Recovered") float NormalizedProgress = 0.0f;
    UPROPERTY(EditAnywhere, Category="Recovered") float SourceDurationSeconds = 0.0f;
    UPROPERTY(EditAnywhere, Category="Recovered") FString EventName;
    UPROPERTY(EditAnywhere, Category="Recovered") FString RatioLiteral;
    bool HasReached(float ActualPositionSeconds, float ActualLengthSeconds) const;
};

/** Separate from the UI sprite DataAsset. Populated by verified full Editor import. */
UCLASS()
class HCZS_API UHczsBattleSceneAssets : public UDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere, Category="Recovered") FString SourceManifestSHA256;
    UPROPERTY(EditAnywhere, Category="Recovered") FString SourceMappingSHA256;
    UPROPERTY(EditAnywhere, Category="Recovered") FString SourceHitTimingSHA256;
    UPROPERTY(EditAnywhere, Category="Recovered") FString SceneNotice;
    UPROPERTY(EditAnywhere, Category="Recovered") FString SupportedEncounterId = TEXT("tutorial-5000");
    UPROPERTY(EditAnywhere, Category="Recovered") FString PlayerId = TEXT("1");
    UPROPERTY(EditAnywhere, Category="Recovered") FString EnemyId = TEXT("991");
    UPROPERTY(EditAnywhere, Category="Recovered") TObjectPtr<USkeletalMesh> PlayerMesh;
    UPROPERTY(EditAnywhere, Category="Recovered") TObjectPtr<USkeletalMesh> EnemyMesh;
    UPROPERTY(EditAnywhere, Category="Recovered") TMap<FString, TObjectPtr<UAnimSequence>> PlayerAnimations;
    UPROPERTY(EditAnywhere, Category="Recovered") TMap<FString, TObjectPtr<UAnimSequence>> EnemyAnimations;
    UPROPERTY(EditAnywhere, Category="Recovered") TMap<FString, FHczsBattleAnimationSequence> CardAnimationQueues;
    UPROPERTY(EditAnywhere, Category="Recovered") TMap<FString, FHczsBattleSourceHit> PlayerHitEvents;
    UPROPERTY(EditAnywhere, Category="Recovered") TMap<FString, FString> EnemySkillClips;
    /** Source SKILL_TARGET_SFX path. Named when the skill plays; the particle is not imported. */
    UPROPERTY(EditAnywhere, Category="Recovered") TMap<FString, FString> EnemySkillEffects;
    UPROPERTY(EditAnywhere, Category="Recovered") bool bOriginalTutorialStageRecovered = false;
    /** Optional second party member bound by the HCZSBattleAlly tag; -1 means no ally actor. */
    UPROPERTY(EditAnywhere, Category="Recovered") TObjectPtr<USkeletalMesh> AllyMesh;
    UPROPERTY(EditAnywhere, Category="Recovered") int32 AllyMemberIndex = -1;
    UPROPERTY(EditAnywhere, Category="Recovered") TMap<FString, TObjectPtr<UAnimSequence>> AllyAnimations;
    /** cardId -> clip via card SKILL_ID, skill timeline ANIMATION_LIST and entity ANIM_STATES_*. */
    UPROPERTY(EditAnywhere, Category="Recovered") TMap<FString, FString> AllyCardClips;
    /** clip -> gim trigger ObjectFileName. Named when the clip plays; the socket has no bone, so the particle is not shown. */
    UPROPERTY(EditAnywhere, Category="Recovered") TMap<FString, FString> AllyClipEffects;
};

DECLARE_MULTICAST_DELEGATE(FOnHczsBattlePresentationChanged);

enum class EHczsVisualSnapshotDecision : uint8 { Ignore, Baseline, PresentReceipt, SynchronizeOnly };

/** Pure gate: retries, reads and continuation never replay a previously observed action. */
struct HCZS_API FHczsBattlePresentationCursor
{
    FString BattleId;
    FString DefinitionId;
    int64 ActionIndex = -1;
    int64 Revision = 0;
    EHczsVisualSnapshotDecision Observe(const FHczsBattleView& View, const FHczsBattleVisualReceipt& Receipt);
    void Reset();
};

struct FHczsBattleAnimationStep
{
    bool bEnemy = false;
    bool bDeath = false;
    FString Clip;
    bool bAlly = false;
};

/** Pure intent identity gate. Confirmation authorizes reactions, never predictions. */
struct HCZS_API FHczsCardVisualGate
{
    FString BattleId, RequestId, CardId;
    int64 StartRevision = 0;
    bool bConfirmed = false;
    bool bReactionReleased = false;
    int32 ExpectedReactionCount = 0;
    int32 ReleasedReactionCount = 0;
    bool Begin(const FHczsBattleView& View, const FHczsCardIntentVisual& Intent, int32 ReactionCount = 1);
    bool Matches(const FHczsBattleView& View, const FHczsBattleVisualReceipt& Receipt) const;
    bool ReleaseReaction(bool bImpactReached);
    bool ReleaseReaction(int32 Ordinal, bool bImpactReached);
    void Reset();
};

/** Visuals only. Never submits a command, changes HP, or advances a battle state. */
UCLASS()
class HCZS_API AHczsBattlePresentation : public AActor
{
    GENERATED_BODY()
public:
    AHczsBattlePresentation();
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
    virtual void Tick(float DeltaSeconds) override;

    /** Caller supplies a successfully parsed authoritative GET and its matching confirmed receipt. */
    void ApplySnapshot(const FHczsBattleView& View, const FHczsBattleVisualReceipt& Receipt);
    UFUNCTION(BlueprintPure, Category="HCZS|Presentation") bool IsPresentationBusy() const { return bPresentationBusy; }
    UFUNCTION(BlueprintPure, Category="HCZS|Presentation") bool IsSceneReady() const { return bSceneReady; }
    UFUNCTION(BlueprintPure, Category="HCZS|Presentation") bool IsEntrancePlaying() const { return bEntrancePlaying; }
    UFUNCTION(BlueprintPure, Category="HCZS|Presentation") float GetEntrancePosition() const;
    /** Fresh-only source BattleBeginAction UI clock; reconnects return -1. */
    double GetFreshOpeningSeconds(const FString& BattleId) const;
    UFUNCTION(BlueprintPure, Category="HCZS|Presentation") FString GetEntrancePhase() const { return EntrancePhase; }
    UFUNCTION(BlueprintPure, Category="HCZS|Presentation") FString GetEntranceDiagnostic() const { return EntranceDiagnostic; }
    bool CanPresentBattle(const FHczsBattleView& View) const;
    UHczsUltimateSequence* GetUltimateSequence() const { return UltimateSequence; }
    UFUNCTION(BlueprintPure, Category="HCZS|Presentation") UHczsWeaponSourceFx* GetWeaponSourceFx() const { return WeaponSourceFx; }
    UFUNCTION(BlueprintPure, Category="HCZS|Presentation") UHczsEntranceSourceFx* GetEntranceSourceFx() const { return EntranceSourceFx; }
    FOnHczsBattlePresentationChanged OnPresentationChangedNative;

    UPROPERTY(EditAnywhere, Category="Recovered") TObjectPtr<UHczsBattleSceneAssets> SceneAssets;

private:
    UPROPERTY() TObjectPtr<UAnimSequence> EntranceAnimation;
    bool bEntrancePlaying = false;
    bool bEntranceEventEmitted = false;
    bool bEntranceSoundPlayed = false;
    bool bAllyShowSoundPlayed = false;
    FString PendingAllyCue;
    FTimerHandle AllyCueTimer;
    UPROPERTY() TObjectPtr<UAudioComponent> EntranceSound;
    UPROPERTY() TArray<TObjectPtr<UAudioComponent>> AllyCueSounds;
    void PlayAllyCue(const FString& Clip, const FString& Event, uint32 SourceId, float VolumeDb, const TCHAR* AssetPath, float Position);
    void TryPlayPendingAllyCue();
    void StopAllyCues();
    FString EntranceBattleId;
    FString EntrancePhase = TEXT("none");
    FString EntranceDiagnostic;
    int32 FirstDealCount = 0;
    float EntranceLastPosition = 0.0f;
    double EntranceDeadline = 0.0;
    double OpeningWorldStart = -1.0;
    double EntranceHiddenWorldStart = -1.0;
    double EntranceHiddenRealStart = -1.0;
    double EntranceShowWorldStart = -1.0;
    FTimerHandle EntranceStartTimer, EntranceVisibleTimer, EntranceFinishTimer;
    bool TryPlayFreshEntrance(const FHczsBattleView& View);
    void StartEntranceClip();
    void RevealEntrancePlayer();
    void ObserveEntrance();
    void CheckEntranceFinished();
    void StopEntrance(bool bCompleted, const FString& Reason, bool bRestoreStablePose = true);
    UPROPERTY() TObjectPtr<UHczsUltimateSequence> UltimateSequence;
    UPROPERTY() TObjectPtr<UHczsWeaponSourceFx> WeaponSourceFx;
    UPROPERTY() TObjectPtr<UHczsEntranceSourceFx> EntranceSourceFx;
    bool bUltimatePlaying = false;
    FHczsCardVisualGate UltimateIntent;
    bool bUltimateIntentAborted = false;
    void UltimateFinished(const FString& Id, bool bSuccess, const FString& Error);
    void UltimateCue(const FString& Id, const FString& Cue, float Position);
    void ReleaseUltimateReactions(const FString& Cue);
    /** Reconstruction: each attack-prefix cue advances one confirmed enemy damage (SkillUseAction.casterAnimEvent -> playNextAction). */
    int32 UltimateAttackCues = 0, UltimateDamageCount = -1, UltimateReactionsReleased = 0;
    TArray<FString> UltimateCueLog;
    UPROPERTY() TObjectPtr<USkeletalMeshComponent> PlayerComponent;
    UPROPERTY() TObjectPtr<USkeletalMeshComponent> EnemyComponent;
    UPROPERTY() TObjectPtr<AActor> WeaponActor;
    UPROPERTY() TObjectPtr<USkeletalMeshComponent> AllyComponent;
    bool bAllyDeathPresented = false;
    bool bRunningAlly = false;
    double AllyShowUntil = -1.0;
    FTimerHandle AllyShowTimer;
    UAnimSequence* FindAllyAnimation(const FString& Clip) const;
    void QueueAllyClip(const FString& Clip, bool bDeath = false);
    void SetAllyVisible(bool bVisible);
    void RestoreAllyIdle();
    bool IsAllyDead(const FHczsBattleView& View) const;
    FHczsBattlePresentationCursor Cursor;
    TArray<FHczsBattleAnimationStep> Queue;
    FTimerHandle StepTimer;
    FHczsBattleView DesiredSnapshot;
    int32 QueueIndex = 0;
    bool bSceneReady = false;
    bool bPresentationBusy = false;
    bool bRunningEnemy = false;
    bool bRunningDeath = false;
    bool bPlayerDeathPresented = false;
    bool bEnemyDeathPresented = false;
    bool bUnsupportedLogged = false;
    UPROPERTY() TObjectPtr<UHczsGameInstance> Session;
    FDelegateHandle IntentDispatchedHandle, IntentSettledHandle, IntentUncertainHandle;
    FHczsCardVisualGate LocalCard;
    TArray<FString> LocalPlayerClips;
    int32 LocalPlayerClipIndex = 0;
    double LocalClipDeadline = 0.0;
    FTimerHandle LocalPlayerTimer;
    bool bLocalPlayerPlaying = false;
    bool bWaitingForImpact = false;
    bool bLocalVisualAborted = false;
    bool bLocalClipHeldAtImpact = false;
    bool bLocalEnemyReacting = false;
    TArray<bool> LocalImpactsReached;
    TArray<FHczsBattleVisualEvent> LocalDamageEvents;
    FTimerHandle LocalEnemyTimer;
    double LocalEnemyDeadline = 0.0;

    bool EnsureSceneReady();
    UAnimSequence* FindAnimation(bool bEnemy, const FString& Clip) const;
    void BuildQueue(const FHczsBattleView& View, const TArray<FHczsBattleVisualEvent>& Events);
    void QueueClip(bool bEnemy, const FString& Clip, bool bDeath = false);
    void PlayNextStep();
    void FinishStep();
    void CancelPresentation(bool bKeepUnconfirmedIntent = false);
    void ApplyStablePose(const FHczsBattleView& View);
    void SetSideVisible(bool bEnemy, bool bVisible);
    void SetBusy(bool bBusy);
    void IntentDispatched(const FHczsCardIntentVisual& Intent);
    void IntentSettled(const FString& RequestId, bool bConfirmed);
    void IntentUncertain(const FString& RequestId);
    void PlayLocalPlayerClip();
    void FinishLocalPlayerClip();
    void FinishVisualsIfIdle();
    void ObserveLocalImpact();
    bool ReleaseLocalReaction();
    bool PrepareLocalReactions(const TArray<FHczsBattleVisualEvent>& Events);
    void FinishLocalEnemyReaction();
};
