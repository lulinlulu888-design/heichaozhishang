#pragma once

#include "CoreMinimal.h"
#include "HczsSessionTypes.generated.h"

UENUM(BlueprintType)
enum class EHczsSessionPhase : uint8
{
    Connecting, ProfileSelection, Hall, Battle, Unavailable
};

/** Display data only. The original tagged decimal is kept; UE does not settle combat. */
USTRUCT(BlueprintType)
struct HCZS_API FHczsScalar
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) FString Decimal;
    UPROPERTY(BlueprintReadOnly) double Approximate = 0;
};

USTRUCT(BlueprintType)
struct HCZS_API FHczsLocalProfile
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) FString Id;
    UPROPERTY(BlueprintReadOnly) FString DisplayName;
    UPROPERTY(BlueprintReadOnly) int64 Revision = 0;
};

USTRUCT(BlueprintType)
struct HCZS_API FHczsEncounterSummary
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) FString Id;
    UPROPERTY(BlueprintReadOnly) FString Title;
    UPROPERTY(BlueprintReadOnly) FString Notice;
    UPROPERTY(BlueprintReadOnly) FString DefinitionId;
    UPROPERTY(BlueprintReadOnly) FString PlayerId;
    UPROPERTY(BlueprintReadOnly) FString EnemyId;
    UPROPERTY(BlueprintReadOnly) FString PlayerName;
    UPROPERTY(BlueprintReadOnly) FString EnemyName;
};

USTRUCT(BlueprintType)
struct HCZS_API FHczsBattleSummary
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) FString Id;
    UPROPERTY(BlueprintReadOnly) int64 Revision = 0;
    UPROPERTY(BlueprintReadOnly) FString DefinitionId;
    UPROPERTY(BlueprintReadOnly) FString Status;
    UPROPERTY(BlueprintReadOnly) int32 Round = 0;
};

USTRUCT(BlueprintType)
struct HCZS_API FHczsHandCard
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) FString InstanceId;
    UPROPERTY(BlueprintReadOnly) FString CardId;
    UPROPERTY(BlueprintReadOnly) FString Name;
    UPROPERTY(BlueprintReadOnly) int32 Cost = 0;
    UPROPERTY(BlueprintReadOnly) FString EffectsText;
    /** First opponent damage amount, the value card_table RPG_DESCRIPTION's %s shows. */
    UPROPERTY(BlueprintReadOnly) FString FirstDamage;
    /** Sum of all opponent damage amounts; the multi-hit ultimate's RPG_DEFAULT_FORMULA total. */
    UPROPERTY(BlueprintReadOnly) FString TotalDamage;
    UPROPERTY(BlueprintReadOnly) FString FirstShield;
    /** Party battles only: the deck entry's owner. Empty for single-character battles. */
    UPROPERTY(BlueprintReadOnly) FString OwnerId;
    UPROPERTY(BlueprintReadOnly) FString OwnerName;
    UPROPERTY(BlueprintReadOnly) int32 OwnerIndex = -1;
};

/** One server-authoritative party member of a hczs-battle-session-party-v1 battle. */
USTRUCT(BlueprintType)
struct HCZS_API FHczsPartyMemberView
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) FString Id;
    UPROPERTY(BlueprintReadOnly) FString Name;
    UPROPERTY(BlueprintReadOnly) FHczsScalar Hp;
    UPROPERTY(BlueprintReadOnly) FHczsScalar MaxHp;
    UPROPERTY(BlueprintReadOnly) FHczsScalar Shield;
    UPROPERTY(BlueprintReadOnly) FHczsScalar Attack;
    UPROPERTY(BlueprintReadOnly) int32 AttackBuff = 0;
};

/** Validated raw receipt events used by scene presentation; never parsed from UI text. */
USTRUCT(BlueprintType)
struct HCZS_API FHczsBattleVisualEvent
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) FString Type;
    UPROPERTY(BlueprintReadOnly) FString CardId;
    UPROPERTY(BlueprintReadOnly) FString SkillId;
    UPROPERTY(BlueprintReadOnly) FString Target;
    UPROPERTY(BlueprintReadOnly) FString InstanceId;
    UPROPERTY(BlueprintReadOnly) int32 Round = 0;
    /** Party battles: card owner (CardPlayed) or hit member (DamageApplied/MemberDefeated); -1 otherwise. */
    UPROPERTY(BlueprintReadOnly) int32 MemberIndex = -1;
};

USTRUCT(BlueprintType)
struct HCZS_API FHczsBattleVisualReceipt
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) FString BattleId;
    UPROPERTY(BlueprintReadOnly) int64 ActionIndex = -1;
    UPROPERTY(BlueprintReadOnly) TArray<FHczsBattleVisualEvent> Events;
    UPROPERTY(BlueprintReadOnly) bool bValid = false;
};

USTRUCT(BlueprintType)
struct HCZS_API FHczsBattleView
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) bool bIsValid = false;
    UPROPERTY(BlueprintReadOnly) FString Id;
    UPROPERTY(BlueprintReadOnly) FString ProfileId;
    UPROPERTY(BlueprintReadOnly) int64 Revision = 0;
    UPROPERTY(BlueprintReadOnly) int64 ActionIndex = 0;
    UPROPERTY(BlueprintReadOnly) FString DefinitionId;
    UPROPERTY(BlueprintReadOnly) FString EncounterId;
    UPROPERTY(BlueprintReadOnly) FString Title;
    UPROPERTY(BlueprintReadOnly) FString Notice;
    UPROPERTY(BlueprintReadOnly) FString PlayerName;
    UPROPERTY(BlueprintReadOnly) FString EnemyName;
    UPROPERTY(BlueprintReadOnly) FString PlayerId;
    UPROPERTY(BlueprintReadOnly) FString EnemyId;
    UPROPERTY(BlueprintReadOnly) FHczsScalar PlayerHp;
    UPROPERTY(BlueprintReadOnly) FHczsScalar PlayerMaxHp;
    UPROPERTY(BlueprintReadOnly) FHczsScalar PlayerShield;
    UPROPERTY(BlueprintReadOnly) FHczsScalar EnemyHp;
    UPROPERTY(BlueprintReadOnly) FHczsScalar EnemyMaxHp;
    UPROPERTY(BlueprintReadOnly) FHczsScalar EnemyShield;
    UPROPERTY(BlueprintReadOnly) int32 Round = 0;
    UPROPERTY(BlueprintReadOnly) int32 MaxRounds = 0;
    UPROPERTY(BlueprintReadOnly) int32 Energy = 0;
    UPROPERTY(BlueprintReadOnly) int32 EnergyPerRound = 0;
    UPROPERTY(BlueprintReadOnly) int32 PlayerBreakdown = 0;
    UPROPERTY(BlueprintReadOnly) int32 EnemyBreakdown = 0;
    UPROPERTY(BlueprintReadOnly) FString Status;
    UPROPERTY(BlueprintReadOnly) FString OutcomeReason;
    UPROPERTY(BlueprintReadOnly) TArray<FHczsHandCard> Hand;
    UPROPERTY(BlueprintReadOnly) FString EnemyIntentText;
    /** Scenario skill ids behind EnemyIntentText, in order. */
    UPROPERTY(BlueprintReadOnly) TArray<FString> EnemyIntentSkills;
    /** Per EnemyIntentSkills entry: the single opponent damage amount, or empty when the skill has none or several. */
    UPROPERTY(BlueprintReadOnly) TArray<FString> EnemyIntentDamage;
    UPROPERTY(BlueprintReadOnly) int32 DrawCount = 0;
    UPROPERTY(BlueprintReadOnly) int32 DiscardCount = 0;
    /** Party battles: Player* fields mirror Party[0], the animated combatant. */
    UPROPERTY(BlueprintReadOnly) bool bIsParty = false;
    UPROPERTY(BlueprintReadOnly) TArray<FHczsPartyMemberView> Party;
    UPROPERTY(BlueprintReadOnly) int32 EnemyAttackBuff = 0;
    UPROPERTY(BlueprintReadOnly) int32 RemovedCount = 0;
};

USTRUCT(BlueprintType)
struct HCZS_API FHczsHallPreference
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) bool bIsValid = false;
    UPROPERTY(BlueprintReadOnly) int64 Revision = 0;
    /** 0 is the UI representation of the API's null; it does not grant hero ownership. */
    UPROPERTY(BlueprintReadOnly) int32 SelectedHeroId = 0;
};

/** Optional local mainline adapter. These fields are server projections, never inferred rewards. */
USTRUCT(BlueprintType)
struct HCZS_API FHczsMainlineChallenge
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) int32 Id = 0;
    UPROPERTY(BlueprintReadOnly) FString Name;
    UPROPERTY(BlueprintReadOnly) FString Subtitle;
    UPROPERTY(BlueprintReadOnly) FString Status;
    UPROPERTY(BlueprintReadOnly) FString EncounterId;
    UPROPERTY(BlueprintReadOnly) bool bExecutable = false;
    /** False means activityDatas has no key. That is not a stored successTime of 0. */
    UPROPERTY(BlueprintReadOnly) bool bRecordPresent = false;
    /** -1 means the source key is absent. */
    UPROPERTY(BlueprintReadOnly) int32 SuccessTime = -1;
};

USTRUCT(BlueprintType)
struct HCZS_API FHczsMainlineProgress
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) bool bIsValid = false;
    UPROPERTY(BlueprintReadOnly) FString ProfileId;
    UPROPERTY(BlueprintReadOnly) FString ContentId;
    UPROPERTY(BlueprintReadOnly) int64 Revision = 0;
    UPROPERTY(BlueprintReadOnly) int64 UpdatedAt = -1;
    UPROPERTY(BlueprintReadOnly) bool bFirstChallengePassed = false;
    UPROPERTY(BlueprintReadOnly) bool bBossChallengePassed = false;
    UPROPERTY(BlueprintReadOnly) bool bActivityRecordPresent = false;
    /** The latest completion; earlier ones stay in CompletedBattleIds/CompletedAts in settle order. */
    UPROPERTY(BlueprintReadOnly) FString CompletedBattleId;
    UPROPERTY(BlueprintReadOnly) int64 CompletedBattleRevision = 0;
    UPROPERTY(BlueprintReadOnly) int64 CompletedAt = -1;
    UPROPERTY(BlueprintReadOnly) TArray<FString> CompletedBattleIds;
    UPROPERTY(BlueprintReadOnly) TArray<int64> CompletedBattleRevisions;
    UPROPERTY(BlueprintReadOnly) TArray<int64> CompletedAts;
    UPROPERTY(BlueprintReadOnly) TArray<FHczsMainlineChallenge> Challenges;
};
