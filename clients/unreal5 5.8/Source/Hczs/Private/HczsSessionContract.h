#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "HczsSessionTypes.h"

/** Strict projection of our new HTTP contract. No original APK protocol claims. */
namespace HczsSessionContract
{
    struct FScenario
    {
        FString DefinitionId, EncounterId, Title, Notice, PlayerId, EnemyId, PlayerName, EnemyName;
        FHczsScalar PlayerMaxHp, EnemyMaxHp;
        TMap<FString, FHczsHandCard> Cards;
        TMap<FString, FString> EnemySkills;
        TArray<TArray<FString>> EnemyIntents;
        TArray<FString> EnemyFallback;
        TArray<TPair<FString, FString>> Deck;
        int32 MaxRounds = 0, HandLimit = 0, EnergyPerRound = 0;
        bool bHasBreakdown = false;
        bool bHasUltimates = false;
        FString UltimateOwnerId, UltimateCardId;
        int32 UltimatePointsRequired = 0, UltimateMaxPerRound = 0;
    };
    bool IsUuid(const FString& Id);
    bool IsId(const FString& Id, int32 MaximumLength = 128);
    bool ParseProfile(const TSharedPtr<FJsonObject>& Object, FHczsLocalProfile& Out);
    bool ParseProfiles(const TSharedPtr<FJsonObject>& Object, TArray<FHczsLocalProfile>& Out);
    bool ParseBootstrap(const TSharedPtr<FJsonObject>& Object, TArray<FHczsLocalProfile>& Out, bool& bAllowProfiles, bool& bAllowBattles);
    bool ParseHall(const TSharedPtr<FJsonObject>& Object, const FString& ProfileId, FHczsHallPreference& Out);
    bool ParseEncounters(const TSharedPtr<FJsonObject>& Object, TArray<FHczsEncounterSummary>& Out);
    bool ParseScenario(const TSharedPtr<FJsonObject>& Object, FScenario& Out);
    bool ParseBattleList(const TSharedPtr<FJsonObject>& Object, TArray<FHczsBattleSummary>& Out);
    bool ParseBattle(const TSharedPtr<FJsonObject>& Object, const FString& ProfileId, const FString& BattleId, FHczsBattleView& Out);
    bool ParseReceipt(const TSharedPtr<FJsonObject>& Object, const FString& ProfileId, const FString& BattleId,
        const FString& EncounterId, int64 ExpectedRevision, FHczsBattleView& Out, TArray<FString>& Events,
        const FString& ActionType = FString(), const FString& InstanceId = FString(), FHczsBattleVisualReceipt* VisualReceipt = nullptr);
    bool CanPublishVisualReceipt(const FHczsBattleView& Latest, const FHczsBattleVisualReceipt& Receipt);
    bool IsSessionSceneReady(EHczsSessionPhase RequiredPhase, EHczsSessionPhase Phase, const FString& SelectedProfileId,
        bool bProfileStateCurrent, const FHczsHallPreference& Hall, const FHczsBattleView& Battle,
        bool bBattleStateCurrent, bool bRequestInFlight, bool bHasPendingIntent);
    bool CanAcceptReply(uint64 CurrentEpoch, uint64 RequestEpoch, bool bShuttingDown, bool bRequestMatches);
    bool CanApplyBattleRevision(const FHczsBattleView& Existing, const FHczsBattleView& Incoming, int64 MinimumRevision);
    TSharedPtr<FJsonObject> Child(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key);
    FString Serialize(const TSharedPtr<FJsonObject>& Object);
    FString ServerErrorCode(const TSharedPtr<FJsonObject>& Object);
}
