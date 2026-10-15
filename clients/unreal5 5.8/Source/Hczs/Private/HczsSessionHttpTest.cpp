#include "HczsGameInstance.h"
#include "HczsSessionContract.h"
#include "Misc/AutomationTest.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "HAL/PlatformFileManager.h"
#include "HAL/PlatformTime.h"
#include "UObject/StrongObjectPtr.h"
#include "Engine/Engine.h"

#if WITH_DEV_AUTOMATION_TESTS
namespace
{
struct FHczsHttpRun
{
    FAutomationTestBase* Test;
    TStrongObjectPtr<UHczsGameInstance> Game;
    int32 Port, Step = 0, RetryCount = 0, WriteRetryCount = 0, ConfirmedReadRetryCount = 0, PlayAttempts = 0, TerminalActions = 0;
    double Deadline;
    FString ReportPath, ProfileId, BattleId, EncounterId = TEXT("city-preview-10405"), Failure;
    int64 BeforeRevision = 0, SavedRevision = 0;
    FHczsBattleView SavedView;
    bool bSawConflict = false, bRepeatPlayAfterConflict = false, bPassed = false, bDone = false;
    bool bOwnCardPlayed = false, bOwnTurnEnded = false, bRestored = false, bExplicitProfileSelection = false;
    bool bVisualCardReceipt = false, bRestoredWithoutVisualReplay = false, bHistoricalVisualSuppressed = false;
    bool bUltimateGenerated = false, bUltimateConfirmed = false;
    int32 UltimateDamageEvents = 0;
    explicit FHczsHttpRun(FAutomationTestBase* InTest, int32 InPort, const FString& InReportPath)
        : Test(InTest), Port(InPort), Deadline(FPlatformTime::Seconds() + 150.0), ReportPath(InReportPath) {}
    ~FHczsHttpRun() { CloseGame(); }
    void CloseGame() { if (Game.IsValid()) { Game->Shutdown(); Game.Reset(); } }
    bool OpenGame()
    {
        Game.Reset(NewObject<UHczsGameInstance>(GEngine));
        Game->OnStateChangedNative.AddLambda([this]
        {
            if (Game.IsValid() && Game->ErrorCode == TEXT("REVISION_CONFLICT"))
            { bSawConflict = true; if (Step == 5) bRepeatPlayAfterConflict = true; }
        });
        return Game->StartIsolatedTestSession(Port);
    }
    bool Finish(bool bSuccess, const FString& Reason = FString())
    {
        bDone = true; bPassed = bSuccess; Failure = Reason;
        if (!bSuccess) Test->AddError(Reason);
        auto Report = MakeShared<FJsonObject>();
        Report->SetBoolField(TEXT("passed"), bSuccess); Report->SetStringField(TEXT("mode"), TEXT("ue-native-http-session-not-ui-gameplay"));
        Report->SetStringField(TEXT("failure"), Reason); Report->SetNumberField(TEXT("port"), Port);
        Report->SetStringField(TEXT("profileId"), ProfileId); Report->SetStringField(TEXT("battleId"), BattleId);
        Report->SetBoolField(TEXT("explicitProfileSelection"), bExplicitProfileSelection);
        Report->SetBoolField(TEXT("cardPlayed"), bOwnCardPlayed); Report->SetBoolField(TEXT("turnEnded"), bOwnTurnEnded);
        Report->SetBoolField(TEXT("newGameInstanceRestored"), bRestored); Report->SetBoolField(TEXT("conflictReloaded"), bSawConflict);
        Report->SetNumberField(TEXT("pendingRetries"), RetryCount); Report->SetNumberField(TEXT("terminalActions"), TerminalActions);
        Report->SetNumberField(TEXT("unconfirmedWriteRetries"), WriteRetryCount);
        Report->SetNumberField(TEXT("confirmedReadRetries"), ConfirmedReadRetryCount);
        Report->SetBoolField(TEXT("visualCardReceiptConfirmedAfterGet"), bVisualCardReceipt);
        Report->SetBoolField(TEXT("restorationPresentedOnlyBaseline"), bRestoredWithoutVisualReplay);
        Report->SetBoolField(TEXT("historicalVisualReceiptSuppressed"), bHistoricalVisualSuppressed);
        Report->SetBoolField(TEXT("ultimateGeneratedInActualHand"), bUltimateGenerated);
        Report->SetBoolField(TEXT("ultimateReceiptConfirmedAfterGet"), bUltimateConfirmed);
        Report->SetNumberField(TEXT("ultimateDamageEvents"), UltimateDamageEvents);
        if (Game.IsValid() && Game->CurrentBattle.bIsValid)
        {
            Report->SetNumberField(TEXT("finalRevision"), static_cast<double>(Game->CurrentBattle.Revision));
            Report->SetStringField(TEXT("outcome"), Game->CurrentBattle.Status);
        }
        FPlatformFileManager::Get().GetPlatformFile().CreateDirectoryTree(*FPaths::GetPath(ReportPath));
        if (!FFileHelper::SaveStringToFile(HczsSessionContract::Serialize(Report), *ReportPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))
            Test->AddError(TEXT("Could not save isolated session test report"));
        CloseGame(); return true;
    }
    bool PlayAffordableCard()
    {
        if (FParse::Param(FCommandLine::Get(), TEXT("HczsSessionRequireUltimate")))
        {
            const FHczsHandCard* Best = nullptr;
            for (const auto& Card : Game->CurrentBattle.Hand)
            {
                if (Card.CardId == TEXT("410104")) bUltimateGenerated = true;
                if (Card.Cost > Game->CurrentBattle.Energy) continue;
                if (!Best || Card.CardId == TEXT("410104") || (Best->CardId != TEXT("410104") && Card.Cost < Best->Cost)) Best = &Card;
            }
            if (!Best) return false;
            BeforeRevision = Game->CurrentBattle.Revision; ++PlayAttempts;
            bRepeatPlayAfterConflict = false; Game->PlayCard(Best->InstanceId); return true;
        }
        for (const auto& Card : Game->CurrentBattle.Hand)
        {
            if (Card.Cost <= Game->CurrentBattle.Energy)
            {
                BeforeRevision = Game->CurrentBattle.Revision; ++PlayAttempts;
                bRepeatPlayAfterConflict = false; Game->PlayCard(Card.InstanceId); return true;
            }
        }
        return false;
    }
    bool Tick()
    {
        if (bDone) return true;
        if (FPlatformTime::Seconds() >= Deadline) return Finish(false, FString::Printf(TEXT("Native HTTP session timed out at step %d"), Step));
        if (!Game.IsValid()) { if (!OpenGame()) return Finish(false, TEXT("Isolation entry gate refused this test")); return false; }
        if (Game->bRequestInFlight) return false;
        if (Game->bBattleStateCurrent && HczsSessionContract::CanPublishVisualReceipt(Game->CurrentBattle, Game->LastVisualReceipt) &&
            Game->LastVisualReceipt.Events.ContainsByPredicate([](const FHczsBattleVisualEvent& E)
            { return E.Type == TEXT("CardPlayed") && E.CardId == TEXT("410104"); }))
        {
            bUltimateConfirmed = true;
            UltimateDamageEvents = Game->LastVisualReceipt.Events.FilterByPredicate([](const FHczsBattleVisualEvent& E)
            { return E.Type == TEXT("DamageApplied") && E.Target == TEXT("enemy"); }).Num();
        }
        if (Game->bHasPendingIntent)
        {
            if (!Game->bPendingIntentRetryable) return Finish(false, TEXT("Pending intent has no active request or retry path"));
            if (++RetryCount > 6) return Finish(false, TEXT("Repeated pending-intent retries exhausted"));
            if (Game->IsPendingReceiptConfirmed()) ++ConfirmedReadRetryCount; else ++WriteRetryCount;
            Game->RetryPendingIntent(); return false;
        }
        switch (Step)
        {
        case 0:
            if (!Game->bLocalServiceAvailable || Game->Phase != EHczsSessionPhase::ProfileSelection) return Finish(false, TEXT("Bootstrap did not reach explicit local profile selection"));
            // A fresh empty list is an additional write guard. Never use another user's existing profile.
            if (!Game->Profiles.IsEmpty() || !Game->SelectedProfileId.IsEmpty()) return Finish(false, TEXT("Refusing writes: isolated service is not a fresh empty database"));
            bExplicitProfileSelection = true; Step = 1;
            Game->CreateLocalProfile(TEXT("UE独立通信验收")); return false;
        case 1:
            if (Game->SelectedProfileId.IsEmpty() || Game->Phase != EHczsSessionPhase::Hall || !Game->HallPreference.bIsValid)
                return Finish(false, TEXT("Explicit profile creation/read failed"));
            ProfileId = Game->SelectedProfileId;
            if (!HczsSessionContract::IsUuid(ProfileId)) return Finish(false, TEXT("Created profile is not a canonical UUID"));
            Step = 2; Game->SaveHallHero(1); return false;
        case 2:
            if (!Game->HallPreference.bIsValid || Game->HallPreference.Revision != 1 || Game->HallPreference.SelectedHeroId != 1)
                return Finish(false, TEXT("Elsa hall preference was not read back from persistent state"));
            Step = 3; Game->SelectEncounter(EncounterId); return false;
        case 3:
            if (!Game->bEncounterScenarioReady || Game->SelectedEncounterId != EncounterId) return Finish(false, TEXT("Explicit encounter/scenario selection failed"));
            Step = 4; Game->CreateSelectedBattle(); return false;
        case 4:
            if (!Game->CurrentBattle.bIsValid || !Game->bBattleStateCurrent || Game->Phase != EHczsSessionPhase::Battle || Game->CurrentBattle.EncounterId != EncounterId)
                return Finish(false, TEXT("Created battle was not synchronized from the server"));
            BattleId = Game->CurrentBattle.Id; Step = 5;
            if (FParse::Param(FCommandLine::Get(), TEXT("HczsSessionExpectFaults")))
            {
                if (Game->CurrentBattle.ActionIndex < 1 || Game->LastVisualReceipt.bValid)
                    return Finish(false, TEXT("Historical creation receipt must not trigger visual events over the advanced GET"));
                bHistoricalVisualSuppressed = true;
            }
            if (!PlayAffordableCard()) return Finish(false, TEXT("Fixture has no affordable initial hand card"));
            return false;
        case 5:
            if (bRepeatPlayAfterConflict)
            {
                if (PlayAttempts >= 3 || !Game->bBattleStateCurrent || !PlayAffordableCard()) return Finish(false, TEXT("Could not submit a new intention after conflict reload"));
                return false;
            }
            if (!Game->bBattleStateCurrent || Game->CurrentBattle.Revision < BeforeRevision + 1 || !Game->LastEvents.ContainsByPredicate([](const FString& E) { return E.StartsWith(TEXT("已出牌")); }))
                return Finish(false, TEXT("Native play-card intention was not confirmed and read back"));
            if (!HczsSessionContract::CanPublishVisualReceipt(Game->CurrentBattle, Game->LastVisualReceipt) ||
                !Game->LastVisualReceipt.Events.ContainsByPredicate([](const FHczsBattleVisualEvent& E) { return E.Type == TEXT("CardPlayed") && !E.CardId.IsEmpty(); }))
                return Finish(false, TEXT("Validated play-card receipt was not published atomically after GET"));
            bVisualCardReceipt = true;
            bOwnCardPlayed = true; BeforeRevision = Game->CurrentBattle.Revision; Step = 6; Game->EndTurn(); return false;
        case 6:
            if (!Game->bBattleStateCurrent || Game->CurrentBattle.Revision < BeforeRevision + 1) return Finish(false, TEXT("Native end-turn intention was not saved"));
            bOwnTurnEnded = true; SavedView = Game->CurrentBattle; SavedRevision = SavedView.Revision;
            Step = 7; Game->ReturnToHall(); return false;
        case 7:
            if (Game->Phase != EHczsSessionPhase::Hall || !Game->Battles.ContainsByPredicate([this](const FHczsBattleSummary& B) { return B.Id == BattleId && B.Revision >= SavedRevision; }))
                return Finish(false, TEXT("Saved battle did not appear in the profile list"));
            CloseGame(); Step = 8;
            if (!OpenGame()) return Finish(false, TEXT("Fresh instance could not connect to the isolated service"));
            return false;
        case 8:
            if (!Game->bLocalServiceAvailable || Game->Phase != EHczsSessionPhase::ProfileSelection || !Game->SelectedProfileId.IsEmpty() ||
                !Game->Profiles.ContainsByPredicate([this](const FHczsLocalProfile& P) { return P.Id == ProfileId; }))
                return Finish(false, TEXT("Fresh instance must offer explicit selection instead of impersonating the first profile"));
            Step = 9; Game->SelectProfile(ProfileId); return false;
        case 9:
            if (Game->Phase != EHczsSessionPhase::Hall || !Game->HallPreference.bIsValid || Game->HallPreference.SelectedHeroId != 1 ||
                !Game->Battles.ContainsByPredicate([this](const FHczsBattleSummary& B) { return B.Id == BattleId; }))
                return Finish(false, TEXT("Persistent profile/hall/list restoration failed"));
            Step = 10; Game->ContinueBattle(BattleId); return false;
        case 10:
            if (!Game->bBattleStateCurrent || Game->CurrentBattle.Id != BattleId || Game->CurrentBattle.Revision != SavedRevision ||
                Game->CurrentBattle.DefinitionId != SavedView.DefinitionId || Game->CurrentBattle.PlayerHp.Decimal != SavedView.PlayerHp.Decimal ||
                Game->CurrentBattle.EnemyHp.Decimal != SavedView.EnemyHp.Decimal || Game->CurrentBattle.Energy != SavedView.Energy ||
                Game->CurrentBattle.Round != SavedView.Round || Game->CurrentBattle.Hand.Num() != SavedView.Hand.Num())
                return Finish(false, TEXT("Continued battle differs from the saved server state"));
            for (int32 I = 0; I < SavedView.Hand.Num(); ++I)
                if (SavedView.Hand[I].InstanceId != Game->CurrentBattle.Hand[I].InstanceId) return Finish(false, TEXT("Restored hand instance/order mismatch"));
            if (Game->LastVisualReceipt.bValid || !Game->LastVisualReceipt.Events.IsEmpty())
                return Finish(false, TEXT("Fresh continue must not reanimate historical receipt events"));
            bRestoredWithoutVisualReplay = true;
            bRestored = true; Step = 11; return false;
        case 11:
            if (!Game->bBattleStateCurrent) return Finish(false, TEXT("A synchronized state is required before each battle intention"));
            if (Game->CurrentBattle.Status != TEXT("player-turn"))
            {
                if (FParse::Param(FCommandLine::Get(), TEXT("HczsSessionRequireUltimate")) &&
                    (!bUltimateGenerated || !bUltimateConfirmed || UltimateDamageEvents < 1))
                    return Finish(false, TEXT("Actual HTTP battle ended without generating and confirming an ultimate"));
                if (FParse::Param(FCommandLine::Get(), TEXT("HczsSessionExpectFaults")) && (WriteRetryCount < 1 || ConfirmedReadRetryCount < 1 || !bSawConflict))
                    return Finish(false, TEXT("Requested network retry/CAS faults were not observed by UE"));
                return Finish(true);
            }
            if (++TerminalActions > 180) return Finish(false, TEXT("Fixture battle failed to reach a server-authored terminal state"));
            if (!PlayAffordableCard()) Game->EndTurn();
            return false;
        default: return Finish(false, TEXT("Unexpected native integration test state"));
        }
    }
};
class FHczsHttpCommand : public IAutomationLatentCommand
{
    TSharedRef<FHczsHttpRun> Run;
public:
    explicit FHczsHttpCommand(TSharedRef<FHczsHttpRun> InRun) : Run(MoveTemp(InRun)) {}
    virtual bool Update() override { return Run->Tick(); }
};
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsNativeHttpSessionTest, "Hczs.LocalSession.Http.PlaySaveResume", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsNativeHttpSessionTest::RunTest(const FString& Parameters)
{
    int32 Port = 0;
    if (!FParse::Param(FCommandLine::Get(), TEXT("HczsSessionIntegration")) || !FParse::Value(FCommandLine::Get(), TEXT("HczsServerPort="), Port) ||
        Port < 1 || Port > 65535 || Port == 7460)
    { AddWarning(TEXT("Skipped mutation test: pass explicit -HczsSessionIntegration -HczsServerPort=<dedicated test port>. No default service was used.")); return true; }
    FString Allowed = FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::ProjectDir(), TEXT("../../analysis/unreal/session-test")));
    FPaths::NormalizeDirectoryName(Allowed);
    FString Report;
    if (!FParse::Value(FCommandLine::Get(), TEXT("HczsSessionTestReport="), Report)) Report = FPaths::Combine(Allowed, TEXT("http-result.json"));
    Report = FPaths::ConvertRelativePathToFull(Report); FPaths::NormalizeFilename(Report);
    if (!Report.StartsWith(Allowed + TEXT("/"), ESearchCase::IgnoreCase))
    { AddError(TEXT("Native session report must be inside analysis/unreal/session-test")); return false; }
    ADD_LATENT_AUTOMATION_COMMAND(FHczsHttpCommand(MakeShared<FHczsHttpRun>(this, Port, Report)));
    return true;
}
#endif
