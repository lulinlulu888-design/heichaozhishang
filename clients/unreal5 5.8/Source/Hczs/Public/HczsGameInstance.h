#pragma once

#include "CoreMinimal.h"
#include "Engine/GameInstance.h"
#include "Interfaces/IHttpRequest.h"
#include "HczsSessionTypes.h"
#include "HczsGameInstance.generated.h"

class FJsonObject;
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FHczsSessionChanged);
DECLARE_MULTICAST_DELEGATE(FOnHczsSessionChanged);

/** Local intent cue only; contains no predicted HP, damage, RNG or outcome. */
struct FHczsCardIntentVisual
{
    FString RequestId;
    FString BattleId;
    FString CardId;
    int64 ExpectedRevision = 0;
    bool bDispatched = false;
};
DECLARE_MULTICAST_DELEGATE_OneParam(FOnHczsCardIntentDispatched, const FHczsCardIntentVisual&);
DECLARE_MULTICAST_DELEGATE_TwoParams(FOnHczsCardIntentSettled, const FString&, bool);

/** Explicit local reconstruction session, never an original-account login. */
UCLASS(Config=Game)
class HCZS_API UHczsGameInstance : public UGameInstance
{
    GENERATED_BODY()
public:
    virtual void Init() override;
    virtual void Shutdown() override;

    UFUNCTION(BlueprintCallable, Category="HCZS|Local") void RefreshLocalStatus();
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void RefreshBootstrap();
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void RefreshProfilesAfterUncertainCreation();
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void SelectProfile(const FString& ProfileId);
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void CreateLocalProfile(const FString& DisplayName);
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void SelectEncounter(const FString& EncounterId);
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void RefreshBattles();
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void ContinueBattle(const FString& BattleId);
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void RefreshCurrentBattle();
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void CreateSelectedBattle();
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void PlayCard(const FString& InstanceId);
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void EndTurn();
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void RetryPendingIntent();
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void ReturnToHall();
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void SaveHallHero(int32 HeroId);
    UFUNCTION(BlueprintPure, Category="HCZS|Session") bool CanSubmitBattleIntent() const;
    UFUNCTION(BlueprintPure, Category="HCZS|Session") bool IsPendingReceiptConfirmed() const;
    UFUNCTION(BlueprintPure, Category="HCZS|Session") bool IsHallSceneReady() const;
    UFUNCTION(BlueprintPure, Category="HCZS|Session") bool IsBattleSceneReady() const;
#if WITH_DEV_AUTOMATION_TESTS
    /** Native test entry only: requires explicit isolation flag and a non-production port. */
    bool StartIsolatedTestSession(int32 Port);
#endif

    UPROPERTY(BlueprintAssignable, Category="HCZS|Session") FHczsSessionChanged OnStateChanged;
    FOnHczsSessionChanged OnStateChangedNative;
    FOnHczsCardIntentDispatched OnCardIntentDispatchedNative;
    FOnHczsCardIntentSettled OnCardIntentSettledNative;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") EHczsSessionPhase Phase = EHczsSessionPhase::Connecting;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") TArray<FHczsLocalProfile> Profiles;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") TArray<FHczsEncounterSummary> Encounters;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") TArray<FHczsBattleSummary> Battles;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") FString SelectedProfileId;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") FString SelectedEncounterId;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") FHczsBattleView CurrentBattle;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") FHczsHallPreference HallPreference;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") TArray<FString> LastEvents;
    /** Published atomically only after the latest GET matches this validated receipt. */
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") FHczsBattleVisualReceipt LastVisualReceipt;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") FString UserMessage;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") FString ErrorCode;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") bool bRequestInFlight = false;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") bool bHasPendingIntent = false;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") bool bPendingIntentRetryable = false;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") bool bBattleStateCurrent = false;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") bool bProfileStateCurrent = false;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") bool bEncounterScenarioReady = false;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") bool bAllowNewProfiles = false;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Session") bool bAllowNewBattles = false;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Local") FString LocalStatus = TEXT("尚未连接");
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Local") bool bLocalServiceAvailable = false;
    UPROPERTY(BlueprintReadOnly, Category="HCZS|Local") bool bOriginalGameplayReady = false;

private:
    UPROPERTY(Config) int32 LocalServerPort = 7460;
    FHttpRequestPtr PendingRequest;
    uint64 SessionEpoch = 0;
    bool bShuttingDown = false;
    bool bIsIsolatedAutomationSession = false;
    FString SelectedDefinitionId;
    FString SelectedPlayerId;
    FString SelectedEnemyId;
    int64 MinimumBattleRevision = 0;
    FString PendingIntentKind;
    FString PendingIntentRoute;
    FString PendingIntentVerb;
    FString PendingIntentBody;
    FString PendingIntentProfile;
    FString PendingIntentBattle;
    FString PendingIntentEncounter;
    int64 PendingIntentRevision = 0;
    bool bPendingReceiptConfirmed = false;
    FString ConfirmedBattleId;
    int64 ConfirmedBattleRevision = 0;
    FHczsBattleVisualReceipt PendingVisualReceipt;
    FHczsCardIntentVisual PendingCardVisual;
    using FReply = TFunction<void(TSharedPtr<FJsonObject>, int32, const FString&)>;

    void Fetch(const FString& RequestPhase, const FString& Verb, const FString& Route, const FString& Body, FReply Completion);
    void Notify();
    void Fail(const FString& Code, const FString& Message);
    bool CanStartRead();
    void ReadSelectedProfile();
    void ReadHall(bool bThenLoadBattles = false);
    void ReadEncounters();
    void ReadBattle(const FString& BattleId, bool bAfterReceipt = false);
    void BeginIntent(const FString& Kind, const FString& Verb, const FString& Route, const FString& Body, int64 ExpectedRevision);
    void SendPendingIntent();
    void ClearPendingIntent(bool bConfirmedCard = false);
    void StartBattleAction(const FString& Type, const FString& InstanceId);
    FString ProfilesRoute() const;
    FString BattlesRoute() const;
    FString FriendlyError(int32 HttpCode, const FString& Code) const;
};
