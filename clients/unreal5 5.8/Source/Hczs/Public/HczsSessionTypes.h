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
    UPROPERTY(BlueprintReadOnly) int32 PlayerBreakdown = 0;
    UPROPERTY(BlueprintReadOnly) int32 EnemyBreakdown = 0;
    UPROPERTY(BlueprintReadOnly) FString Status;
    UPROPERTY(BlueprintReadOnly) FString OutcomeReason;
    UPROPERTY(BlueprintReadOnly) TArray<FHczsHandCard> Hand;
    UPROPERTY(BlueprintReadOnly) FString EnemyIntentText;
    UPROPERTY(BlueprintReadOnly) int32 DrawCount = 0;
    UPROPERTY(BlueprintReadOnly) int32 DiscardCount = 0;
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
    UPROPERTY(BlueprintReadOnly) FString CompletedBattleId;
    UPROPERTY(BlueprintReadOnly) int64 CompletedBattleRevision = 0;
    UPROPERTY(BlueprintReadOnly) int64 CompletedAt = -1;
    UPROPERTY(BlueprintReadOnly) TArray<FHczsMainlineChallenge> Challenges;
};
