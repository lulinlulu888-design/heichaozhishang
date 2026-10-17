#include "HczsSessionContract.h"
#include "Serialization/JsonWriter.h"
#include "Serialization/JsonSerializer.h"
#include <locale>
#include <sstream>

namespace HczsSessionContract
{
namespace
{
    constexpr double MaxSafeInteger = 9007199254740991.0;
    bool Exact(const TSharedPtr<FJsonObject>& O, std::initializer_list<const TCHAR*> Fields)
    {
        if (!O.IsValid() || O->Values.Num() != static_cast<int32>(Fields.size())) return false;
        for (const TCHAR* Field : Fields) if (!O->HasField(Field)) return false;
        return true;
    }
    // FJsonValueString::TryGetBool accepts "true"; contract flags must be JSON booleans.
    bool Bool(const TSharedPtr<FJsonObject>& O, const TCHAR* Field, bool& Out)
    {
        const TSharedPtr<FJsonValue> Value = O.IsValid() ? O->TryGetField(Field) : nullptr;
        if (!Value.IsValid() || Value->Type != EJson::Boolean) return false;
        Out = Value->AsBool();
        return true;
    }
    bool Text(const TSharedPtr<FJsonObject>& O, const TCHAR* Field, FString& Out, int32 Limit, bool bEmpty = false)
    {
        if (!O.IsValid() || !O->TryGetStringField(Field, Out) || Out.Len() > Limit || (!bEmpty && Out.IsEmpty())) return false;
        for (TCHAR C : Out) if (C < 32 || C == 127) return false;
        return true;
    }
    bool Integer(const TSharedPtr<FJsonObject>& O, const TCHAR* Field, int64& Out, int64 Min = 0, int64 Max = 9007199254740991LL)
    {
        double Value = 0;
        if (!O.IsValid() || !O->TryGetNumberField(Field, Value) || !FMath::IsFinite(Value) ||
            Value < static_cast<double>(Min) || Value > static_cast<double>(Max) || Value > MaxSafeInteger || FMath::FloorToDouble(Value) != Value) return false;
        Out = static_cast<int64>(Value); return true;
    }
    bool Counter(const TSharedPtr<FJsonObject>& O, const TCHAR* Field, int32& Out, int32 Min, int32 Max)
    {
        int64 Value = 0; if (!Integer(O, Field, Value, Min, Max)) return false;
        Out = static_cast<int32>(Value); return true;
    }
    const TArray<TSharedPtr<FJsonValue>>* Array(const TSharedPtr<FJsonObject>& O, const TCHAR* Field, int32 Limit)
    {
        const TArray<TSharedPtr<FJsonValue>>* Result = nullptr;
        return O.IsValid() && O->TryGetArrayField(Field, Result) && Result && Result->Num() <= Limit ? Result : nullptr;
    }
    TSharedPtr<FJsonObject> ObjectValue(const TSharedPtr<FJsonValue>& Value)
    {
        const TSharedPtr<FJsonObject>* O = nullptr;
        return Value.IsValid() && Value->TryGetObject(O) && O ? *O : nullptr;
    }
    bool DecimalInteger(const FString& S, int32 Limit)
    {
        if (S.IsEmpty() || S.Len() > Limit || (S.Len() > 1 && S[0] == '0')) return false;
        for (TCHAR C : S) if (C < '0' || C > '9') return false;
        return true;
    }
    bool ContentHash(const FString& S)
    {
        if (S.Len() != 64) return false;
        for (TCHAR C : S) if (!((C >= '0' && C <= '9') || (C >= 'a' && C <= 'f'))) return false;
        return true;
    }
    bool HexBinary64(const FString& Hex, double& Out)
    {
        // Decode the Python-style exact hexadecimal scalar without platform-dependent strtod hex support.
        if (!Hex.StartsWith(TEXT("0x")) || Hex.Len() > 32) return false;
        int32 P = INDEX_NONE; if (!Hex.FindChar('p', P) || P < 3) return false;
        FString Mantissa = Hex.Mid(2, P - 2), Exponent = Hex.Mid(P + 1);
        if (Exponent.Len() < 2 || (Exponent[0] != '+' && Exponent[0] != '-')) return false;
        for (int32 I = 1; I < Exponent.Len(); ++I) if (!FChar::IsDigit(Exponent[I])) return false;
        const int32 E = FCString::Atoi(*Exponent);
        if (E < -1074 || E > 1023) return false;
        bool bDot = false; int32 Digits = 0; double Acc = 0, Weight = 1;
        for (TCHAR C : Mantissa)
        {
            if (C == '.' && !bDot) { bDot = true; continue; }
            const int32 D = C >= '0' && C <= '9' ? C - '0' : C >= 'a' && C <= 'f' ? C - 'a' + 10 : -1;
            if (D < 0 || ++Digits > 14) return false;
            if (bDot) { Weight /= 16; Acc += D * Weight; } else Acc = Acc * 16 + D;
        }
        if (!bDot || Digits < 2) return false;
        Out = Acc * FMath::Pow(2.0, static_cast<double>(E));
        return FMath::IsFinite(Out) && Out >= 0;
    }
    bool Scalar(const TSharedPtr<FJsonObject>& O, FHczsScalar& Out)
    {
        FString Kind;
        if (!Text(O, TEXT("numeric_type"), Kind, 16) || !Text(O, TEXT("decimal"), Out.Decimal, 128)) return false;
        const FTCHARToUTF8 DecimalBytes(*Out.Decimal);
        // NDK r27 libc++ has no floating-point from_chars. A private classic locale
        // keeps decimal parsing independent of the device locale without changing it.
        if (Out.Decimal[0] == '+') return false;
        for (TCHAR C : Out.Decimal)
            if ((C < '0' || C > '9') && C != '.' && C != '+' && C != '-' && C != 'e' && C != 'E') return false;
        std::istringstream Parser(std::string(DecimalBytes.Get(), DecimalBytes.Length()));
        Parser.imbue(std::locale::classic());
        Parser >> std::noskipws >> Out.Approximate;
        if (Parser.fail() || !Parser.eof() || !FMath::IsFinite(Out.Approximate) || Out.Approximate < 0) return false;
        // Some standard libraries silently round an underflowing decimal to zero.
        if (Out.Approximate == 0)
            for (TCHAR C : Out.Decimal)
            {
                if (C == 'e' || C == 'E') break;
                if (C >= '1' && C <= '9') return false;
            }
        if (Kind == TEXT("integer"))
        {
            if (!Exact(O, {TEXT("numeric_type"), TEXT("decimal")}) || !DecimalInteger(Out.Decimal, 128)) return false;
        }
        else if (Kind == TEXT("binary64"))
        {
            FString Hex; double ExactValue = 0;
            if (!Exact(O, {TEXT("numeric_type"), TEXT("decimal"), TEXT("hex")}) || Out.Decimal.Len() > 64 ||
                !Text(O, TEXT("hex"), Hex, 32) || !HexBinary64(Hex, ExactValue)) return false;
            // Decimal syntax: only a number, never whitespace, nan, infinity or a culture-specific separator.
            for (TCHAR C : Out.Decimal) if (!FChar::IsDigit(C) && C != '.' && C != '+' && C != '-' && C != 'e' && C != 'E') return false;
            if (Out.Approximate != ExactValue) return false;
        }
        else return false;
        return true;
    }
    bool Timestamps(const TSharedPtr<FJsonObject>& O)
    {
        int64 Created = 0, Updated = 0;
        return Integer(O, TEXT("createdAt"), Created) && Integer(O, TEXT("updatedAt"), Updated) && Updated >= Created;
    }
    bool StringIds(const TArray<TSharedPtr<FJsonValue>>* Input, TArray<FString>& Out, bool bNonEmpty = false)
    {
        if (!Input || (bNonEmpty && Input->IsEmpty())) return false;
        for (const TSharedPtr<FJsonValue>& V : *Input)
        {
            FString Id; if (!V.IsValid() || !V->TryGetString(Id) || !IsId(Id)) return false;
            Out.Add(Id);
        }
        return true;
    }
    bool Effects(const TSharedPtr<FJsonObject>& O, bool bEnemy, bool bBreakdown, FString& Out, FString* FirstDamage = nullptr,
        FString* TotalDamage = nullptr)
    {
        const auto* Values = Array(O, TEXT("effects"), 32); if (!Values) return false;
        TArray<FString> Lines;
        int64 Total = 0; bool bAnyDamage = false;
        for (const auto& V : *Values)
        {
            const auto E = ObjectValue(V); FString Type, Target, Amount;
            if (!Text(E, TEXT("type"), Type, 24)) return false;
            if (Type == TEXT("damage") || Type == TEXT("shield") || (Type == TEXT("heal") && bBreakdown))
            {
                if (!Exact(E, {TEXT("type"), TEXT("target"), TEXT("amount")}) ||
                    !Text(E, TEXT("target"), Target, 16) || (Target != TEXT("self") && Target != TEXT("opponent")) ||
                    !Text(E, TEXT("amount"), Amount, 64) || !DecimalInteger(Amount, 64)) return false;
                if (FirstDamage && FirstDamage->IsEmpty() && Type == TEXT("damage") && Target == TEXT("opponent")) *FirstDamage = Amount;
                if (Type == TEXT("damage") && Target == TEXT("opponent"))
                {
                    const int64 Value = FCString::Atoi64(*Amount);
                    if (Value < 0 || Total > MAX_int64 - Value) return false;
                    Total += Value; bAnyDamage = true;
                }
                const TCHAR* Action = Type == TEXT("damage") ? TEXT("伤害") : Type == TEXT("shield") ? TEXT("护盾") : TEXT("恢复");
                Lines.Add(FString::Printf(TEXT("%s%s %s"), Target == TEXT("opponent") ? TEXT("对方") : TEXT("自身"), Action, *Amount));
            }
            else if (Type == TEXT("draw") && !bEnemy)
            {
                int32 Count = 0; if (!Exact(E, {TEXT("type"), TEXT("count")}) || !Counter(E, TEXT("count"), Count, 0, 64)) return false;
                Lines.Add(FString::Printf(TEXT("抽牌 %d"), Count));
            }
            else if (Type == TEXT("breakdown") && bBreakdown)
            {
                int32 Count = 0;
                if (!Exact(E, {TEXT("type"), TEXT("target"), TEXT("stacks")}) || !Text(E, TEXT("target"), Target, 16) ||
                    Target != TEXT("opponent") || !Counter(E, TEXT("stacks"), Count, 1, 999)) return false;
                Lines.Add(FString::Printf(TEXT("对方崩解 +%d"), Count));
            }
            else return false;
        }
        if (TotalDamage && bAnyDamage) *TotalDamage = FString::Printf(TEXT("%lld"), Total);
        Out = FString::Join(Lines, TEXT(" · ")); return true;
    }
    bool Status(const FString& S) { return S == TEXT("player-turn") || S == TEXT("won") || S == TEXT("lost"); }
    bool SameJson(const TSharedPtr<FJsonValue>& A, const TSharedPtr<FJsonValue>& B)
    {
        if (!A.IsValid() || !B.IsValid() || A->Type != B->Type) return false;
        switch (A->Type)
        {
        case EJson::Null: return true;
        case EJson::String: return A->AsString() == B->AsString();
        case EJson::Number: return A->AsNumber() == B->AsNumber();
        case EJson::Boolean: return A->AsBool() == B->AsBool();
        case EJson::Array:
            if (A->AsArray().Num() != B->AsArray().Num()) return false;
            for (int32 I = 0; I < A->AsArray().Num(); ++I) if (!SameJson(A->AsArray()[I], B->AsArray()[I])) return false;
            return true;
        case EJson::Object:
            if (A->AsObject()->Values.Num() != B->AsObject()->Values.Num()) return false;
            for (const auto& Entry : A->AsObject()->Values)
            {
                const auto* Other = B->AsObject()->Values.Find(Entry.Key); if (!Other || !SameJson(Entry.Value, *Other)) return false;
            }
            return true;
        default: return false;
        }
    }
}

TSharedPtr<FJsonObject> Child(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key)
{
    const TSharedPtr<FJsonObject>* Result = nullptr;
    return Object.IsValid() && Object->TryGetObjectField(Key, Result) && Result ? *Result : nullptr;
}
bool IsUuid(const FString& Id)
{
    if (Id.Len() != 36) return false;
    for (int32 I = 0; I < Id.Len(); ++I)
    {
        if (I == 8 || I == 13 || I == 18 || I == 23) { if (Id[I] != '-') return false; }
        else if (!((Id[I] >= '0' && Id[I] <= '9') || (Id[I] >= 'a' && Id[I] <= 'f'))) return false;
    }
    return true;
}
bool IsId(const FString& Id, int32 MaximumLength)
{
    if (Id.IsEmpty() || Id.Len() > MaximumLength) return false;
    for (int32 I = 0; I < Id.Len(); ++I)
    {
        const TCHAR C = Id[I]; const bool bAlphaNumeric = (C >= '0' && C <= '9') || (C >= 'A' && C <= 'Z') || (C >= 'a' && C <= 'z');
        if (!bAlphaNumeric && (I == 0 || (C != '.' && C != '_' && C != ':' && C != '-'))) return false;
    }
    return true;
}
bool ParseProfile(const TSharedPtr<FJsonObject>& O, FHczsLocalProfile& Out)
{
    if (!Exact(O, {TEXT("id"), TEXT("displayName"), TEXT("selectedCharacterId"), TEXT("revision"), TEXT("createdAt"), TEXT("updatedAt")}) ||
        !Text(O, TEXT("id"), Out.Id, 36) || !IsUuid(Out.Id) || !Text(O, TEXT("displayName"), Out.DisplayName, 80) ||
        !Integer(O, TEXT("revision"), Out.Revision, 1) || !Timestamps(O)) return false;
    int64 Hero = 0; const auto Value = O->TryGetField(TEXT("selectedCharacterId"));
    return Value.IsValid() && (Value->IsNull() || Integer(O, TEXT("selectedCharacterId"), Hero, 1, MAX_int32));
}
bool ParseProfiles(const TSharedPtr<FJsonObject>& O, TArray<FHczsLocalProfile>& Out)
{
    const auto* Values = Array(O, TEXT("profiles"), 10000); if (!Values) return false;
    TArray<FHczsLocalProfile> Parsed; TSet<FString> Ids;
    for (const auto& V : *Values)
    {
        FHczsLocalProfile P; if (!ParseProfile(ObjectValue(V), P) || Ids.Contains(P.Id)) return false;
        Ids.Add(P.Id); Parsed.Add(MoveTemp(P));
    }
    Out = MoveTemp(Parsed); return true;
}
bool ParseBootstrap(const TSharedPtr<FJsonObject>& O, TArray<FHczsLocalProfile>& Out, bool& bAllowProfiles, bool& bAllowBattles)
{
    FString Service, Storage; int64 Version = 0, SaveVersion = 0;
    bool bReady = false;
    if (!Text(O, TEXT("service"), Service, 40) || Service != TEXT("hczs-rebuild") ||
        !Integer(O, TEXT("apiVersion"), Version, 1, 1) || !Integer(O, TEXT("saveSchemaVersion"), SaveVersion, 1, 1) ||
        !Text(O, TEXT("storage"), Storage, 32) || (Storage != TEXT("mongodb") && Storage != TEXT("sqlite")) ||
        !Bool(O, TEXT("gameplayReady"), bReady) || !ParseProfiles(O, Out)) return false;
    const auto* Capabilities = Array(O, TEXT("capabilities"), 64); TArray<FString> Names;
    if (!StringIds(Capabilities, Names) || !Names.Contains(TEXT("local-profiles")) || !Names.Contains(TEXT("encounter-selection"))) return false;
    auto Settings = Child(Child(O, TEXT("operational")), TEXT("settings"));
    if (!Settings.IsValid() || !Bool(Settings, TEXT("allowNewProfiles"), bAllowProfiles) ||
        !Bool(Settings, TEXT("allowNewBattles"), bAllowBattles)) return false;
    const auto Endpoints = Child(O, TEXT("endpoints")); FString ProfilesEndpoint, EncountersEndpoint, BattlesEndpoint;
    return Text(Endpoints, TEXT("profiles"), ProfilesEndpoint, 100) && ProfilesEndpoint == TEXT("/api/rebuild/v1/profiles") &&
        Text(Endpoints, TEXT("encounters"), EncountersEndpoint, 100) && EncountersEndpoint == TEXT("/api/rebuild/v1/encounters") &&
        Text(Endpoints, TEXT("battles"), BattlesEndpoint, 100) && BattlesEndpoint == TEXT("/api/rebuild/v1/profiles/{profileId}/battles");
}
bool ParseMainlineCapability(const TSharedPtr<FJsonObject>& O, bool& bEnabled, FString& ContentId)
{
    TArray<FString> Names;
    if (!StringIds(Array(O, TEXT("capabilities"), 64), Names)) return false;
    bEnabled = false; ContentId.Reset();
    if (!Names.Contains(TEXT("mainline-progression"))) return true;
    FString Hash, ReadRoute, SettleRoute;
    if (!Text(Child(O, TEXT("content")), TEXT("mainlineId"), Hash, 64) || !ContentHash(Hash) ||
        !Text(Child(O, TEXT("endpoints")), TEXT("mainline"), ReadRoute, 100) || ReadRoute != TEXT("/api/rebuild/v1/profiles/{profileId}/mainline") ||
        !Text(Child(O, TEXT("endpoints")), TEXT("settlements"), SettleRoute, 100) || SettleRoute != TEXT("/api/rebuild/v1/profiles/{profileId}/mainline/settlements")) return false;
    bEnabled = true; ContentId = Hash; return true;
}
bool ParseMainline(const TSharedPtr<FJsonObject>& O, const FString& ProfileId, const FString& ContentId, FHczsMainlineProgress& Out)
{
    FHczsMainlineProgress P; int64 Activity = 0; FString Policy, Authority;
    if (!Exact(O, {TEXT("profileId"), TEXT("activityId"), TEXT("contentId"), TEXT("policy"), TEXT("revision"), TEXT("updatedAt"),
            TEXT("initialStateAuthority"), TEXT("activityDatas"), TEXT("challenges"), TEXT("completed")}) ||
        !Text(O, TEXT("profileId"), P.ProfileId, 36) || P.ProfileId != ProfileId || !IsUuid(P.ProfileId) ||
        !Text(O, TEXT("contentId"), P.ContentId, 64) || P.ContentId != ContentId || !ContentHash(P.ContentId) ||
        !Integer(O, TEXT("activityId"), Activity, 2, 2) || !Integer(O, TEXT("revision"), P.Revision, 0, 2) ||
        !Text(O, TEXT("policy"), Policy, 80) || Policy != TEXT("local-prologue-progress-v1") ||
        !Text(O, TEXT("initialStateAuthority"), Authority, 128) || Authority != TEXT("local-fresh-profile-policy; not recovered original account state")) return false;
    const auto* Completed = Array(O, TEXT("completed"), 2);
    const auto* Challenges = Array(O, TEXT("challenges"), 2);
    if (!Completed || Completed->Num() != P.Revision || !Challenges || Challenges->Num() != 2) return false;
    if (P.Revision == 0)
    {
        const auto Updated = O->TryGetField(TEXT("updatedAt")); if (!Updated.IsValid() || !Updated->IsNull()) return false;
        const auto Records = O->TryGetField(TEXT("activityDatas")); if (!Records.IsValid() || !Records->IsNull()) return false;
    }
    else
    {
        const auto Records = Child(O, TEXT("activityDatas"));
        const auto ActivityRecord = Child(Records, TEXT("2"));
        if (!Records.IsValid() || Records->Values.Num() != 1 || !ActivityRecord.IsValid() || ActivityRecord->Values.Num() != P.Revision ||
            !Integer(O, TEXT("updatedAt"), P.UpdatedAt)) return false;
        P.bActivityRecordPresent = true;
        int64 PreviousAt = 0;
        for (int32 Index = 0; Index < Completed->Num(); ++Index)
        {
            // Settlement order follows the single predecessor chain 3997 -> 3998.
            const int64 ChallengeId = 3997 + Index; int64 SuccessTime = 0, Challenge = 0, Revision = 0, At = 0; FString Battle;
            const auto Done = ObjectValue((*Completed)[Index]);
            if (!Integer(Child(ActivityRecord, *FString::Printf(TEXT("%lld"), ChallengeId)), TEXT("successTime"), SuccessTime, 1, 1) ||
                !Exact(Done, {TEXT("challengeId"), TEXT("battleId"), TEXT("battleRevision"), TEXT("completedAt")}) ||
                !Integer(Done, TEXT("challengeId"), Challenge, ChallengeId, ChallengeId) || !Text(Done, TEXT("battleId"), Battle, 36) || !IsUuid(Battle) ||
                P.CompletedBattleIds.Contains(Battle) || !Integer(Done, TEXT("battleRevision"), Revision, 1, 1000001) ||
                !Integer(Done, TEXT("completedAt"), At, PreviousAt, P.UpdatedAt)) return false;
            P.CompletedBattleIds.Add(Battle); P.CompletedBattleRevisions.Add(Revision); P.CompletedAts.Add(At); PreviousAt = At;
        }
        P.CompletedBattleId = P.CompletedBattleIds.Last(); P.CompletedBattleRevision = P.CompletedBattleRevisions.Last(); P.CompletedAt = P.CompletedAts.Last();
        P.bFirstChallengePassed = true; P.bBossChallengePassed = P.Revision == 2;
    }
    for (int32 Index = 0; Index < 2; ++Index)
    {
        const auto C = ObjectValue((*Challenges)[Index]); FHczsMainlineChallenge Challenge;
        int64 Battle = 0, Count = 0; bool bLoot = true;
        const bool bFirst = Index == 0;
        // 3998 is executable once the server binds the reconstructed prologue-boss-1703 encounter.
        const bool bBound = !bFirst && C.IsValid() && !C->HasField(TEXT("unavailableReason"));
        const bool bFields = (bFirst || bBound) ? Exact(C, {TEXT("id"), TEXT("name"), TEXT("subtitle"), TEXT("battleId"), TEXT("predecessors"), TEXT("hasLoot"),
            TEXT("status"), TEXT("recordPresent"), TEXT("successTime"), TEXT("encounterId"), TEXT("executable")}) : Exact(C, {TEXT("id"), TEXT("name"), TEXT("subtitle"), TEXT("battleId"),
            TEXT("predecessors"), TEXT("hasLoot"), TEXT("status"), TEXT("recordPresent"), TEXT("successTime"), TEXT("encounterId"), TEXT("executable"), TEXT("unavailableReason")});
        if (!bFields || !Counter(C, TEXT("id"), Challenge.Id, bFirst ? 3997 : 3998, bFirst ? 3997 : 3998) ||
            !Text(C, TEXT("name"), Challenge.Name, 128) || !Text(C, TEXT("subtitle"), Challenge.Subtitle, 128) ||
            !Integer(C, TEXT("battleId"), Battle, bFirst ? 5000 : 1703, bFirst ? 5000 : 1703) ||
            !Bool(C, TEXT("hasLoot"), bLoot) || bLoot || !Bool(C, TEXT("executable"), Challenge.bExecutable) || Challenge.bExecutable != (bFirst || bBound) ||
            !Text(C, TEXT("status"), Challenge.Status, 16) || !Bool(C, TEXT("recordPresent"), Challenge.bRecordPresent)) return false;
        const auto Success = C->TryGetField(TEXT("successTime"));
        if (Challenge.bRecordPresent)
        {
            if (!Integer(C, TEXT("successTime"), Count, 1, 1)) return false;
            Challenge.SuccessTime = static_cast<int32>(Count);
        }
        else if (!Success.IsValid() || !Success->IsNull() || Count != 0) return false;
        const bool bPassed = bFirst ? P.bFirstChallengePassed : P.bBossChallengePassed;
        const FString ExpectedStatus = bPassed ? TEXT("passed") : (bFirst || P.bFirstChallengePassed) ? TEXT("available") : TEXT("locked");
        if (Challenge.Status != ExpectedStatus || Challenge.bRecordPresent != bPassed || Challenge.SuccessTime != (bPassed ? 1 : -1)) return false;
        const auto* Predecessors = Array(C, TEXT("predecessors"), 1);
        if (!Predecessors || Predecessors->Num() != (bFirst ? 0 : 1)) return false;
        if (bFirst)
        {
            if (!Text(C, TEXT("encounterId"), Challenge.EncounterId, 80) || Challenge.EncounterId != TEXT("tutorial-5000")) return false;
        }
        else
        {
            double Previous = 0; FString Reason; const auto Encounter = C->TryGetField(TEXT("encounterId"));
            if (!(*Predecessors)[0]->TryGetNumber(Previous) || Previous != 3997 || !Encounter.IsValid()) return false;
            if (bBound)
            {
                if (!Text(C, TEXT("encounterId"), Challenge.EncounterId, 80) || Challenge.EncounterId != TEXT("prologue-boss-1703")) return false;
            }
            else if (!Encounter->IsNull() || P.bBossChallengePassed ||
                !Text(C, TEXT("unavailableReason"), Reason, 100) || Reason != TEXT("original-boss-mechanics-and-client-not-restored")) return false;
        }
        P.Challenges.Add(MoveTemp(Challenge));
    }
    P.bIsValid = true; Out = MoveTemp(P); return true;
}
bool ParseMainlineReceipt(const TSharedPtr<FJsonObject>& O, const FString& ProfileId, const FString& ContentId,
    const FString& BattleId, int64 BattleRevision, int64 ExpectedRevision, FHczsMainlineProgress& Out)
{
    bool bReplayed = false; FHczsMainlineProgress P;
    if (!Exact(O, {TEXT("campaign"), TEXT("settlement"), TEXT("rewards"), TEXT("replayed")}) || !Bool(O, TEXT("replayed"), bReplayed) ||
        !Array(O, TEXT("rewards"), 0) || !ParseMainline(Child(O, TEXT("campaign")), ProfileId, ContentId, P) ||
        P.Revision != ExpectedRevision + 1 || !P.bFirstChallengePassed || P.CompletedBattleId != BattleId || P.CompletedBattleRevision != BattleRevision) return false;
    const auto* Completed = Array(Child(O, TEXT("campaign")), TEXT("completed"), 2);
    if (!Completed || Completed->Num() != P.Revision || !SameJson(Completed->Last(), O->TryGetField(TEXT("settlement")))) return false;
    Out = MoveTemp(P); return true;
}
bool CanSettleMainlineBattle(const FHczsMainlineProgress& Progress, const FHczsBattleView& Battle)
{
    if (!Progress.bIsValid || !Battle.bIsValid || Battle.ProfileId != Progress.ProfileId || Battle.Status != TEXT("won") ||
        Battle.OutcomeReason != TEXT("enemy-defeated")) return false;
    if (Progress.Revision == 0 && !Progress.bFirstChallengePassed)
        return !Battle.bIsParty && Battle.EncounterId == TEXT("tutorial-5000") && Battle.PlayerId == TEXT("1") && Battle.EnemyId == TEXT("991");
    return Progress.Revision == 1 && Progress.bFirstChallengePassed && !Progress.bBossChallengePassed &&
        Progress.Challenges.Num() == 2 && Progress.Challenges[1].bExecutable && Progress.Challenges[1].EncounterId == TEXT("prologue-boss-1703") &&
        Battle.bIsParty && Battle.EncounterId == TEXT("prologue-boss-1703") && Battle.PlayerId == TEXT("party-1-3") && Battle.EnemyId == TEXT("2013") &&
        !Progress.CompletedBattleIds.Contains(Battle.Id);
}
bool CanApplyMainlineProgress(const FHczsMainlineProgress& Existing, const FHczsMainlineProgress& Incoming, int64 MinimumRevision)
{
    if (!Incoming.bIsValid || Incoming.Revision < MinimumRevision) return false;
    if (!Existing.bIsValid) return true;
    if (Incoming.ProfileId != Existing.ProfileId || Incoming.ContentId != Existing.ContentId || Incoming.Revision < Existing.Revision ||
        Incoming.UpdatedAt < Existing.UpdatedAt || Incoming.CompletedBattleIds.Num() < Existing.CompletedBattleIds.Num()) return false;
    // Completions are append-only: every confirmed record stays byte-identical.
    for (int32 I = 0; I < Existing.CompletedBattleIds.Num(); ++I)
        if (Incoming.CompletedBattleIds[I] != Existing.CompletedBattleIds[I] || Incoming.CompletedBattleRevisions[I] != Existing.CompletedBattleRevisions[I] ||
            Incoming.CompletedAts[I] != Existing.CompletedAts[I]) return false;
    return Incoming.Revision != Existing.Revision || (Incoming.CompletedBattleId == Existing.CompletedBattleId &&
        Incoming.CompletedBattleRevision == Existing.CompletedBattleRevision && Incoming.CompletedAt == Existing.CompletedAt);
}
bool ParseHall(const TSharedPtr<FJsonObject>& O, const FString& ProfileId, FHczsHallPreference& Out)
{
    FString Id;
    if (!Exact(O, {TEXT("profileId"), TEXT("revision"), TEXT("selectedHeroId"), TEXT("updatedAt")}) ||
        !Text(O, TEXT("profileId"), Id, 36) || Id != ProfileId || !Integer(O, TEXT("revision"), Out.Revision)) return false;
    const auto Hero = O->TryGetField(TEXT("selectedHeroId")), Updated = O->TryGetField(TEXT("updatedAt")); int64 Value = 0;
    if (!Hero.IsValid() || !Updated.IsValid()) return false;
    if (!Hero->IsNull()) { if (!Integer(O, TEXT("selectedHeroId"), Value, 1, MAX_int32)) return false; Out.SelectedHeroId = static_cast<int32>(Value); }
    else Out.SelectedHeroId = 0;
    if (Out.Revision == 0) { if (!Hero->IsNull() || !Updated->IsNull()) return false; }
    else if (!Integer(O, TEXT("updatedAt"), Value)) return false;
    Out.bIsValid = true; return true;
}
bool ParseEncounters(const TSharedPtr<FJsonObject>& O, TArray<FHczsEncounterSummary>& Out)
{
    int64 Schema = 0; bool bUnlock = false, bRewards = false; FString Policy, Default;
    if (!Integer(O, TEXT("schemaVersion"), Schema, 1, 1) || !Text(O, TEXT("selectionPolicy"), Policy, 80) ||
        Policy != TEXT("explicit-local-selection") || !Bool(O, TEXT("originalUnlockBehaviorVerified"), bUnlock) ||
        !Bool(O, TEXT("rewardsImplemented"), bRewards) || !Text(O, TEXT("defaultEncounterId"), Default, 80) || !IsId(Default, 80)) return false;
    const auto* Values = Array(O, TEXT("encounters"), 1000); if (!Values) return false;
    TArray<FHczsEncounterSummary> Parsed; TSet<FString> Ids;
    for (const auto& V : *Values)
    {
        const auto E = ObjectValue(V); FHczsEncounterSummary Entry;
        if (!Text(E, TEXT("id"), Entry.Id, 80) || !IsId(Entry.Id, 80) || Ids.Contains(Entry.Id) ||
            !Text(E, TEXT("title"), Entry.Title, 256) || !Text(E, TEXT("notice"), Entry.Notice, 4096, true) ||
            !Text(E, TEXT("definitionId"), Entry.DefinitionId, 128) || !IsId(Entry.DefinitionId) ||
            !Text(Child(E, TEXT("player")), TEXT("id"), Entry.PlayerId, 128) || !IsId(Entry.PlayerId) ||
            !Text(Child(E, TEXT("enemy")), TEXT("id"), Entry.EnemyId, 128) || !IsId(Entry.EnemyId) ||
            !Text(Child(E, TEXT("player")), TEXT("name"), Entry.PlayerName, 128) ||
            !Text(Child(E, TEXT("enemy")), TEXT("name"), Entry.EnemyName, 128)) return false;
        Ids.Add(Entry.Id); Parsed.Add(MoveTemp(Entry));
    }
    Out = MoveTemp(Parsed); return true;
}
int64 PartyDamagePreview(double Attack, int32 Factor, int32 Stacks, int32 PercentPerStack)
{
    // Same binary64 order as the server: base, then (1 + (stackFactor - 1)) buff.
    const double Base = Attack * static_cast<double>(Factor) / 100.0;
    const double StackFactor = 1.0 + static_cast<double>(static_cast<int64>(Stacks) * PercentPerStack) / 100.0;
    const double Value = Base * (1.0 + (StackFactor - 1.0));
    return Value <= 1.0 ? 1 : static_cast<int64>(FMath::FloorToDouble(Value));
}
int64 PartyShieldPreview(double Attack, int32 Factor)
{
    const double Value = Attack * static_cast<double>(Factor) / 100.0;
    return Value <= 0.0 ? 0 : static_cast<int64>(FMath::FloorToDouble(Value));
}
FString PartyEffectsText(const TArray<FPartyEffect>& Effects, double Attack, int32 Stacks, int32 PercentPerStack, FString* FirstDamage)
{
    TArray<FString> Lines;
    for (const FPartyEffect& E : Effects)
    {
        if (E.Type == TEXT("damage"))
        {
            const FString Amount = FString::Printf(TEXT("%lld"), PartyDamagePreview(Attack, E.Factor, Stacks, PercentPerStack));
            if (FirstDamage && FirstDamage->IsEmpty() && E.Target == TEXT("opponent")) *FirstDamage = Amount;
            if (E.Target == TEXT("opponent")) Lines.Add(TEXT("对方伤害 ") + Amount);
            else Lines.Add(E.Times > 1 ? FString::Printf(TEXT("首位伤害 %s ×%d"), *Amount, E.Times) : TEXT("首位伤害 ") + Amount);
        }
        else if (E.Type == TEXT("shield"))
            Lines.Add(FString::Printf(TEXT("%s护盾 %lld"), E.Target == TEXT("party") ? TEXT("全队") : TEXT("自身"), PartyShieldPreview(Attack, E.Factor)));
        else if (E.Type == TEXT("attackBuff"))
            Lines.Add(FString::Printf(TEXT("%s攻击强化 +%d层"), E.Target == TEXT("party") ? TEXT("全队") : TEXT("自身"), E.Stacks));
        else if (E.Type == TEXT("draw")) Lines.Add(FString::Printf(TEXT("抽牌 %d"), E.Count));
    }
    return FString::Join(Lines, TEXT(" · "));
}
namespace
{
    bool PartyEffects(const TSharedPtr<FJsonObject>& O, bool bEnemy, TArray<FPartyEffect>& Out)
    {
        const auto* Values = Array(O, TEXT("effects"), 32); if (!Values || Values->IsEmpty()) return false;
        for (const auto& V : *Values)
        {
            const auto E = ObjectValue(V); FPartyEffect Effect;
            if (!Text(E, TEXT("type"), Effect.Type, 24)) return false;
            if (Effect.Type == TEXT("damage") && !bEnemy)
            {
                if (!Exact(E, {TEXT("type"), TEXT("target"), TEXT("factor")}) || !Text(E, TEXT("target"), Effect.Target, 16) ||
                    Effect.Target != TEXT("opponent") || !Counter(E, TEXT("factor"), Effect.Factor, 0, 100000)) return false;
            }
            else if (Effect.Type == TEXT("damage"))
            {
                if (!Exact(E, {TEXT("type"), TEXT("target"), TEXT("factor"), TEXT("times")}) || !Text(E, TEXT("target"), Effect.Target, 16) ||
                    Effect.Target != TEXT("first-mid-last") || !Counter(E, TEXT("factor"), Effect.Factor, 0, 100000) ||
                    !Counter(E, TEXT("times"), Effect.Times, 1, 16)) return false;
            }
            else if (Effect.Type == TEXT("shield") && !bEnemy)
            {
                if (!Exact(E, {TEXT("type"), TEXT("target"), TEXT("factor")}) || !Text(E, TEXT("target"), Effect.Target, 16) ||
                    (Effect.Target != TEXT("self") && Effect.Target != TEXT("party")) || !Counter(E, TEXT("factor"), Effect.Factor, 0, 100000)) return false;
            }
            else if (Effect.Type == TEXT("attackBuff"))
            {
                if (!Exact(E, {TEXT("type"), TEXT("target"), TEXT("stacks")}) || !Text(E, TEXT("target"), Effect.Target, 16) ||
                    (Effect.Target != TEXT("self") && (bEnemy || Effect.Target != TEXT("party"))) ||
                    !Counter(E, TEXT("stacks"), Effect.Stacks, 1, 999)) return false;
            }
            else if (Effect.Type == TEXT("draw") && !bEnemy)
            {
                if (!Exact(E, {TEXT("type"), TEXT("count")}) || !Counter(E, TEXT("count"), Effect.Count, 0, 64)) return false;
            }
            else return false;
            Out.Add(MoveTemp(Effect));
        }
        return true;
    }
    bool Combatant(const TSharedPtr<FJsonObject>& O, FHczsPartyMemberView& Out)
    {
        return Exact(O, {TEXT("id"), TEXT("name"), TEXT("maxHp"), TEXT("attack")}) && Text(O, TEXT("id"), Out.Id, 128) && IsId(Out.Id) &&
            Text(O, TEXT("name"), Out.Name, 128) && Scalar(Child(O, TEXT("maxHp")), Out.MaxHp) && Out.MaxHp.Approximate > 0 &&
            Scalar(Child(O, TEXT("attack")), Out.Attack);
    }
}
bool ParsePartyScenario(const TSharedPtr<FJsonObject>& D, FScenario& S)
{
    if (!Exact(D, {TEXT("id"), TEXT("player"), TEXT("party"), TEXT("enemy"), TEXT("deck"), TEXT("cards"), TEXT("enemySkills"),
            TEXT("enemyIntents"), TEXT("enemyFallback"), TEXT("initialDraw"), TEXT("roundDraw"), TEXT("energyPerRound"),
            TEXT("handLimit"), TEXT("maxRounds"), TEXT("partyRules")})) return false;
    S.bIsParty = true;
    const auto Rules = Child(D, TEXT("partyRules")); FString Policy, Buff, Targeting;
    if (!Exact(Rules, {TEXT("policy"), TEXT("buffId"), TEXT("attackPercentPerStack"), TEXT("maxStacks"), TEXT("enemyTargeting")}) ||
        !Text(Rules, TEXT("policy"), Policy, 80) || Policy != TEXT("prologue-party-reconstruction-v1") ||
        !Text(Rules, TEXT("buffId"), Buff, 16) || Buff != TEXT("1001") ||
        !Counter(Rules, TEXT("attackPercentPerStack"), S.AttackPercentPerStack, 1, 100) ||
        !Counter(Rules, TEXT("maxStacks"), S.MaxStacks, 1, 999) ||
        !Text(Rules, TEXT("enemyTargeting"), Targeting, 40) || Targeting != TEXT("first-living-in-formation")) return false;
    const auto Player = Child(D, TEXT("player"));
    if (!Exact(Player, {TEXT("id"), TEXT("name")}) || !Text(Player, TEXT("id"), S.PlayerId, 128) || !IsId(S.PlayerId) ||
        !Text(Player, TEXT("name"), S.PlayerName, 128)) return false;
    FHczsPartyMemberView Enemy;
    if (!Combatant(Child(D, TEXT("enemy")), Enemy)) return false;
    S.EnemyId = Enemy.Id; S.EnemyName = Enemy.Name; S.EnemyMaxHp = Enemy.MaxHp; S.EnemyAttack = Enemy.Attack;
    const auto* Members = Array(D, TEXT("party"), 4); if (!Members || Members->IsEmpty()) return false;
    TSet<FString> MemberIds = {S.EnemyId, S.PlayerId};
    for (const auto& V : *Members)
    {
        FHczsPartyMemberView Member;
        if (!Combatant(ObjectValue(V), Member) || MemberIds.Contains(Member.Id)) return false;
        MemberIds.Add(Member.Id); S.Party.Add(MoveTemp(Member));
    }
    S.PlayerMaxHp = S.Party[0].MaxHp;
    auto Cards = Child(D, TEXT("cards")), Skills = Child(D, TEXT("enemySkills"));
    if (!Cards.IsValid() || Cards->Values.IsEmpty() || Cards->Values.Num() > 256 || !Skills.IsValid() || Skills->Values.IsEmpty() || Skills->Values.Num() > 128) return false;
    for (const auto& Entry : Cards->Values)
    {
        const FString Key(*Entry.Key); auto C = ObjectValue(Entry.Value); FHczsHandCard Card; Card.CardId = Key;
        TArray<FPartyEffect> Effects;
        if (!IsId(Key) || !Exact(C, {TEXT("name"), TEXT("cost"), TEXT("effects")}) || !Text(C, TEXT("name"), Card.Name, 128) ||
            !Counter(C, TEXT("cost"), Card.Cost, 0, 1000000) || !PartyEffects(C, false, Effects)) return false;
        S.Cards.Add(Key, MoveTemp(Card)); S.PartyCardEffects.Add(Key, MoveTemp(Effects));
    }
    for (const auto& Entry : Skills->Values)
    {
        const FString Key(*Entry.Key); auto Skill = ObjectValue(Entry.Value); TArray<FPartyEffect> Effects;
        if (!IsId(Key) || !Exact(Skill, {TEXT("effects")}) || !PartyEffects(Skill, true, Effects)) return false;
        S.EnemySkills.Add(Key, PartyEffectsText(Effects, S.EnemyAttack.Approximate, 0, S.AttackPercentPerStack));
        S.PartyEnemyEffects.Add(Key, MoveTemp(Effects));
    }
    const auto* Deck = Array(D, TEXT("deck"), 64); if (!Deck || Deck->IsEmpty()) return false;
    for (const auto& V : *Deck)
    {
        auto Entry = ObjectValue(V); FString Instance, Card, Owner;
        if (!Exact(Entry, {TEXT("instanceId"), TEXT("cardId"), TEXT("ownerId")}) || !Text(Entry, TEXT("instanceId"), Instance, 128) || !IsId(Instance) ||
            !Text(Entry, TEXT("cardId"), Card, 128) || !S.Cards.Contains(Card) || S.DeckOwners.Contains(Instance) ||
            !Text(Entry, TEXT("ownerId"), Owner, 128)) return false;
        const int32 OwnerIndex = S.Party.IndexOfByPredicate([&Owner](const FHczsPartyMemberView& M) { return M.Id == Owner; });
        if (OwnerIndex == INDEX_NONE) return false;
        S.DeckOwners.Add(Instance, OwnerIndex); S.Deck.Add(TPair<FString, FString>(Instance, Card));
    }
    const auto* Intents = Array(D, TEXT("enemyIntents"), 1000); if (!Intents) return false;
    for (const auto& V : *Intents)
    {
        const TArray<TSharedPtr<FJsonValue>>* Order = nullptr; TArray<FString> Names;
        if (!V.IsValid() || !V->TryGetArray(Order) || !Order || Order->Num() > 16 || !StringIds(Order, Names, true)) return false;
        for (const FString& Id : Names) if (!S.EnemySkills.Contains(Id)) return false;
        S.EnemyIntents.Add(MoveTemp(Names));
    }
    if (!StringIds(Array(D, TEXT("enemyFallback"), 16), S.EnemyFallback, true)) return false;
    for (const FString& Id : S.EnemyFallback) if (!S.EnemySkills.Contains(Id)) return false;
    int32 Initial = 0, Draw = 0;
    return Counter(D, TEXT("initialDraw"), Initial, 0, 64) && Counter(D, TEXT("roundDraw"), Draw, 0, 64) &&
        Counter(D, TEXT("handLimit"), S.HandLimit, 0, 64) && Counter(D, TEXT("energyPerRound"), S.EnergyPerRound, 0, 1000000) &&
        Counter(D, TEXT("maxRounds"), S.MaxRounds, 1, 1000);
}
bool ParseScenario(const TSharedPtr<FJsonObject>& O, FScenario& Out)
{
    FScenario S; auto D = Child(O, TEXT("definition"));
    if (!D.IsValid() || !Text(D, TEXT("id"), S.DefinitionId, 128) || !IsId(S.DefinitionId) ||
        !Text(O, TEXT("title"), S.Title, 256) || !Text(O, TEXT("notice"), S.Notice, 4096, true)) return false;
    if (O->HasField(TEXT("encounterId")) && (!Text(O, TEXT("encounterId"), S.EncounterId, 80) || !IsId(S.EncounterId, 80))) return false;
    if (D->HasField(TEXT("partyRules")))
    {
        if (!ParsePartyScenario(D, S)) return false;
        Out = MoveTemp(S); return true;
    }
    S.bHasBreakdown = D->HasField(TEXT("statusRules"));
    S.bHasUltimates = D->HasField(TEXT("ultimateRules"));
    if (S.bHasUltimates)
    {
        const auto Rules = Child(D, TEXT("ultimateRules")); FString Policy;
        if (!Exact(Rules, {TEXT("policy"), TEXT("ownerId"), TEXT("cardId"), TEXT("pointsRequired"), TEXT("maxPerRound")}) ||
            !Text(Rules, TEXT("policy"), Policy, 80) || Policy != TEXT("elsa-combo-reconstruction-v1") ||
            !Text(Rules, TEXT("ownerId"), S.UltimateOwnerId, 128) || S.UltimateOwnerId != TEXT("1") ||
            !Text(Rules, TEXT("cardId"), S.UltimateCardId, 128) || S.UltimateCardId != TEXT("410104") ||
            !Counter(Rules, TEXT("pointsRequired"), S.UltimatePointsRequired, 3, 3) ||
            !Counter(Rules, TEXT("maxPerRound"), S.UltimateMaxPerRound, 3, 3)) return false;
    }
    if (S.bHasBreakdown)
    {
        auto Rules = Child(D, TEXT("statusRules")); FString Policy; FHczsScalar PlayerAttack, EnemyAttack;
        if (!Exact(Rules, {TEXT("policy"), TEXT("attack")}) || !Text(Rules, TEXT("policy"), Policy, 80) ||
            Policy != TEXT("breakdown-reconstruction-v1") || !Exact(Child(Rules, TEXT("attack")), {TEXT("player"), TEXT("enemy")}) ||
            !Scalar(Child(Child(Rules, TEXT("attack")), TEXT("player")), PlayerAttack) ||
            !Scalar(Child(Child(Rules, TEXT("attack")), TEXT("enemy")), EnemyAttack)) return false;
    }
    const int32 ExpectedFields = 13 + (S.bHasBreakdown ? 1 : 0) + (S.bHasUltimates ? 1 : 0);
    if (D->Values.Num() != ExpectedFields) return false;
    auto Player = Child(D, TEXT("player")), Enemy = Child(D, TEXT("enemy"));
    if (!Exact(Player, {TEXT("id"), TEXT("name"), TEXT("maxHp")}) || !Exact(Enemy, {TEXT("id"), TEXT("name"), TEXT("maxHp")}) ||
        !Text(Player, TEXT("id"), S.PlayerId, 128) || !IsId(S.PlayerId) || !Text(Enemy, TEXT("id"), S.EnemyId, 128) || !IsId(S.EnemyId) ||
        S.PlayerId == S.EnemyId || !Text(Player, TEXT("name"), S.PlayerName, 128) || !Text(Enemy, TEXT("name"), S.EnemyName, 128) ||
        !Scalar(Child(Player, TEXT("maxHp")), S.PlayerMaxHp) || !Scalar(Child(Enemy, TEXT("maxHp")), S.EnemyMaxHp) ||
        S.PlayerMaxHp.Approximate <= 0 || S.EnemyMaxHp.Approximate <= 0) return false;
    auto Cards = Child(D, TEXT("cards")), Skills = Child(D, TEXT("enemySkills"));
    if (!Cards.IsValid() || Cards->Values.IsEmpty() || Cards->Values.Num() > 256 || !Skills.IsValid() || Skills->Values.IsEmpty() || Skills->Values.Num() > 128) return false;
    for (const auto& Entry : Cards->Values)
    {
        const FString Key(*Entry.Key);
        auto C = ObjectValue(Entry.Value); FHczsHandCard Card; Card.CardId = Key;
        const bool bFieldsValid = S.bHasUltimates ? Exact(C, {TEXT("name"), TEXT("cost"), TEXT("effects"), TEXT("ownerId"),
            TEXT("cardType"), TEXT("specialPoints"), TEXT("removeOnLeaveHand")}) : Exact(C, {TEXT("name"), TEXT("cost"), TEXT("effects")});
        if (!IsId(Key) || !bFieldsValid || !Text(C, TEXT("name"), Card.Name, 128) ||
            !Counter(C, TEXT("cost"), Card.Cost, 0, 1000000) || !Effects(C, false, S.bHasBreakdown, Card.EffectsText, &Card.FirstDamage, &Card.TotalDamage)) return false;
        if (S.bHasUltimates)
        {
            FString Owner; int32 Type = 0, Points = 0; bool bRemove = false;
            const bool bUltimate = Key == S.UltimateCardId;
            if (!Text(C, TEXT("ownerId"), Owner, 128) || Owner != S.UltimateOwnerId ||
                !Counter(C, TEXT("cardType"), Type, 0, 7) || Type == 4 || Type == 5 || (Type == 7) != bUltimate ||
                !Counter(C, TEXT("specialPoints"), Points, 0, 1) || Points != (bUltimate ? 0 : 1) ||
                !Bool(C, TEXT("removeOnLeaveHand"), bRemove) || bRemove != bUltimate ||
                (bUltimate && Card.Cost != 0)) return false;
        }
        S.Cards.Add(Key, MoveTemp(Card));
    }
    if (S.bHasUltimates && !S.Cards.Contains(S.UltimateCardId)) return false;
    for (const auto& Entry : Skills->Values)
    {
        const FString Key(*Entry.Key);
        auto Skill = ObjectValue(Entry.Value); FString Description;
        if (!IsId(Key) || !Exact(Skill, {TEXT("effects")}) || !Effects(Skill, true, S.bHasBreakdown, Description)) return false;
        S.EnemySkills.Add(Key, MoveTemp(Description));
        TArray<FString> Damage;
        for (const auto& V : *Array(Skill, TEXT("effects"), 32))
        {
            const auto E = ObjectValue(V); FString Type, Target, Amount;
            if (Text(E, TEXT("type"), Type, 24) && Type == TEXT("damage") && Text(E, TEXT("target"), Target, 16)
                && Target == TEXT("opponent") && Text(E, TEXT("amount"), Amount, 64)) Damage.Add(Amount);
        }
        if (Damage.Num() == 1) S.EnemySkillDamage.Add(Key, Damage[0]);
    }
    const auto* Deck = Array(D, TEXT("deck"), 64); if (!Deck || Deck->IsEmpty()) return false;
    TSet<FString> Instances;
    for (const auto& V : *Deck)
    {
        auto Entry = ObjectValue(V); FString Instance, Card;
        if (!Exact(Entry, {TEXT("instanceId"), TEXT("cardId")}) || !Text(Entry, TEXT("instanceId"), Instance, 128) || !IsId(Instance) ||
            !Text(Entry, TEXT("cardId"), Card, 128) || !S.Cards.Contains(Card) || Instances.Contains(Instance)) return false;
        if (S.bHasUltimates && (Instance.StartsWith(TEXT("ultimate:"), ESearchCase::CaseSensitive) || Card == S.UltimateCardId)) return false;
        Instances.Add(Instance); S.Deck.Add(TPair<FString, FString>(Instance, Card));
    }
    const auto* Intents = Array(D, TEXT("enemyIntents"), 1000); if (!Intents) return false;
    for (const auto& V : *Intents)
    {
        const TArray<TSharedPtr<FJsonValue>>* Order = nullptr; TArray<FString> Names;
        if (!V.IsValid() || !V->TryGetArray(Order) || !Order || Order->Num() > 16 || !StringIds(Order, Names, true)) return false;
        for (const FString& Id : Names) if (!S.EnemySkills.Contains(Id)) return false;
        S.EnemyIntents.Add(MoveTemp(Names));
    }
    if (!StringIds(Array(D, TEXT("enemyFallback"), 16), S.EnemyFallback, true)) return false;
    for (const FString& Id : S.EnemyFallback) if (!S.EnemySkills.Contains(Id)) return false;
    int32 Initial = 0, Draw = 0;
    if (!Counter(D, TEXT("initialDraw"), Initial, 0, 64) || !Counter(D, TEXT("roundDraw"), Draw, 0, 64) ||
        !Counter(D, TEXT("handLimit"), S.HandLimit, 0, 64) || !Counter(D, TEXT("energyPerRound"), S.EnergyPerRound, 0, 1000000) ||
        !Counter(D, TEXT("maxRounds"), S.MaxRounds, 1, 1000)) return false;
    Out = MoveTemp(S); return true;
}
bool ParseBattleList(const TSharedPtr<FJsonObject>& O, TArray<FHczsBattleSummary>& Out)
{
    const auto* Values = Array(O, TEXT("battles"), 10000); if (!Values) return false;
    TArray<FHczsBattleSummary> Parsed; TSet<FString> Ids;
    for (const auto& V : *Values)
    {
        auto B = ObjectValue(V); FHczsBattleSummary Entry;
        if (!Exact(B, {TEXT("id"), TEXT("revision"), TEXT("definitionId"), TEXT("status"), TEXT("round"), TEXT("createdAt"), TEXT("updatedAt")}) ||
            !Text(B, TEXT("id"), Entry.Id, 36) || !IsUuid(Entry.Id) || Ids.Contains(Entry.Id) || !Integer(B, TEXT("revision"), Entry.Revision, 1, 1000001) ||
            !Text(B, TEXT("definitionId"), Entry.DefinitionId, 128) || !IsId(Entry.DefinitionId) ||
            !Text(B, TEXT("status"), Entry.Status, 24) || !Status(Entry.Status) || !Counter(B, TEXT("round"), Entry.Round, 1, 1000) || !Timestamps(B)) return false;
        Ids.Add(Entry.Id); Parsed.Add(MoveTemp(Entry));
    }
    Out = MoveTemp(Parsed); return true;
}
namespace
{
    bool Combat(const TSharedPtr<FJsonObject>& O, int32 MaxStacks, FHczsScalar& Hp, FHczsScalar& Shield, int32& Buff)
    {
        return Exact(O, {TEXT("hp"), TEXT("shield"), TEXT("attackBuff")}) && Scalar(Child(O, TEXT("hp")), Hp) &&
            Scalar(Child(O, TEXT("shield")), Shield) && Counter(O, TEXT("attackBuff"), Buff, 0, MaxStacks);
    }
    bool ParsePartyState(const TSharedPtr<FJsonObject>& State, const FScenario& Scenario, FHczsBattleView& B, FHczsBattleView& Out)
    {
        FString Format; int64 Action = 0;
        if (!Exact(State, {TEXT("format"), TEXT("definitionId"), TEXT("round"), TEXT("status"), TEXT("outcomeReason"), TEXT("energy"),
                TEXT("party"), TEXT("enemy"), TEXT("cards"), TEXT("piles"), TEXT("rng"), TEXT("actionIndex")}) ||
            !Text(State, TEXT("format"), Format, 40) || Format != TEXT("hczs-battle-session-party-v1") ||
            !Text(State, TEXT("definitionId"), B.DefinitionId, 128) || B.DefinitionId != Scenario.DefinitionId ||
            !Counter(State, TEXT("round"), B.Round, 1, Scenario.MaxRounds) || !Counter(State, TEXT("energy"), B.Energy, 0, Scenario.EnergyPerRound) ||
            !Integer(State, TEXT("actionIndex"), Action, 0, 1000000) || Action + 1 != B.Revision ||
            !Text(State, TEXT("status"), B.Status, 24) || !Status(B.Status)) return false;
        B.ActionIndex = Action;
        const auto* Members = Array(State, TEXT("party"), 4);
        if (!Members || Members->Num() != Scenario.Party.Num()) return false;
        int32 Living = 0;
        for (int32 I = 0; I < Members->Num(); ++I)
        {
            FHczsPartyMemberView Member = Scenario.Party[I];
            if (!Combat(ObjectValue((*Members)[I]), Scenario.MaxStacks, Member.Hp, Member.Shield, Member.AttackBuff) ||
                Member.Hp.Approximate > Member.MaxHp.Approximate) return false;
            if (Member.Hp.Approximate > 0) ++Living;
            B.Party.Add(MoveTemp(Member));
        }
        if (!Combat(Child(State, TEXT("enemy")), Scenario.MaxStacks, B.EnemyHp, B.EnemyShield, B.EnemyAttackBuff) ||
            B.EnemyHp.Approximate > Scenario.EnemyMaxHp.Approximate) return false;
        const auto Outcome = State->TryGetField(TEXT("outcomeReason")); if (!Outcome.IsValid()) return false;
        if (B.Status == TEXT("player-turn"))
        {
            if (!Outcome->IsNull() || Living == 0 || B.EnemyHp.Approximate <= 0) return false;
        }
        else
        {
            if (!Text(State, TEXT("outcomeReason"), B.OutcomeReason, 40)) return false;
            if (B.Status == TEXT("won")) { if (B.OutcomeReason != TEXT("enemy-defeated") || B.EnemyHp.Approximate != 0 || Living == 0) return false; }
            else if (B.EnemyHp.Approximate <= 0 || !((B.OutcomeReason == TEXT("party-defeated") && Living == 0) ||
                (B.OutcomeReason == TEXT("round-limit") && Living > 0 && B.Round == Scenario.MaxRounds))) return false;
        }
        const auto* Registry = Array(State, TEXT("cards"), Scenario.Deck.Num());
        if (!Registry || Registry->Num() != Scenario.Deck.Num()) return false;
        TMap<FString, FString> InstanceCards;
        for (int32 I = 0; I < Registry->Num(); ++I)
        {
            auto C = ObjectValue((*Registry)[I]); FString Instance, Card, Owner;
            if (!Exact(C, {TEXT("instanceId"), TEXT("cardId"), TEXT("ownerId")}) || !Text(C, TEXT("instanceId"), Instance, 128) ||
                !Text(C, TEXT("cardId"), Card, 128) || !Text(C, TEXT("ownerId"), Owner, 128) || Instance != Scenario.Deck[I].Key ||
                Card != Scenario.Deck[I].Value || Owner != Scenario.Party[Scenario.DeckOwners[Instance]].Id) return false;
            InstanceCards.Add(Instance, Card);
        }
        auto Piles = Child(State, TEXT("piles"));
        if (!Exact(Piles, {TEXT("hand"), TEXT("draw"), TEXT("discard"), TEXT("removed")})) return false;
        TSet<FString> Seen;
        for (const TCHAR* Zone : {TEXT("hand"), TEXT("draw"), TEXT("discard"), TEXT("removed")})
        {
            const FString ZoneName(Zone);
            TArray<FString> Members2; if (!StringIds(Array(Piles, Zone, 64), Members2)) return false;
            if (ZoneName == TEXT("hand") && Members2.Num() > Scenario.HandLimit) return false;
            for (const FString& Instance : Members2)
            {
                const FString* CardId = InstanceCards.Find(Instance); if (!CardId || Seen.Contains(Instance)) return false;
                const int32 OwnerIndex = Scenario.DeckOwners[Instance];
                // A defeated member's cards, and only those, leave play.
                if ((ZoneName == TEXT("removed")) != (B.Party[OwnerIndex].Hp.Approximate == 0)) return false;
                Seen.Add(Instance);
                if (ZoneName == TEXT("hand"))
                {
                    const FHczsPartyMemberView& Owner = B.Party[OwnerIndex];
                    FHczsHandCard Card = Scenario.Cards[*CardId]; Card.InstanceId = Instance;
                    Card.OwnerId = Owner.Id; Card.OwnerName = Owner.Name; Card.OwnerIndex = OwnerIndex;
                    Card.EffectsText = PartyEffectsText(Scenario.PartyCardEffects[*CardId], Owner.Attack.Approximate, Owner.AttackBuff,
                        Scenario.AttackPercentPerStack, &Card.FirstDamage);
                    B.Hand.Add(MoveTemp(Card));
                }
            }
            if (ZoneName == TEXT("draw")) B.DrawCount = Members2.Num();
            if (ZoneName == TEXT("discard")) B.DiscardCount = Members2.Num();
            if (ZoneName == TEXT("removed")) B.RemovedCount = Members2.Num();
        }
        if (Seen.Num() != Registry->Num()) return false;
        auto Rng = Child(State, TEXT("rng")); FString Algorithm; int64 RandomState = 0;
        if (!Exact(Rng, {TEXT("algorithm"), TEXT("state")}) || !Text(Rng, TEXT("algorithm"), Algorithm, 32) ||
            Algorithm != TEXT("mulberry32-v1") || !Integer(Rng, TEXT("state"), RandomState, 0, 4294967295LL)) return false;
        const TArray<FString>& Intent = Scenario.EnemyIntents.IsValidIndex(B.Round - 1) ? Scenario.EnemyIntents[B.Round - 1] : Scenario.EnemyFallback;
        TArray<FString> Descriptions;
        for (const FString& Skill : Intent)
        {
            const TArray<FPartyEffect>& Effects = Scenario.PartyEnemyEffects[Skill];
            Descriptions.Add(PartyEffectsText(Effects, Scenario.EnemyAttack.Approximate, B.EnemyAttackBuff, Scenario.AttackPercentPerStack));
            const FPartyEffect* Hit = Effects.Num() == 1 && Effects[0].Type == TEXT("damage") ? &Effects[0] : nullptr;
            B.EnemyIntentDamage.Add(Hit ? FString::Printf(TEXT("%lld"), PartyDamagePreview(Scenario.EnemyAttack.Approximate, Hit->Factor,
                B.EnemyAttackBuff, Scenario.AttackPercentPerStack)) : FString());
        }
        B.EnemyIntentText = FString::Join(Descriptions, TEXT(" / "));
        B.EnemyIntentSkills = Intent;
        B.bIsParty = true;
        B.PlayerHp = B.Party[0].Hp; B.PlayerShield = B.Party[0].Shield; B.PlayerMaxHp = B.Party[0].MaxHp;
        B.EncounterId = Scenario.EncounterId; B.Title = Scenario.Title; B.Notice = Scenario.Notice;
        B.PlayerId = Scenario.PlayerId; B.EnemyId = Scenario.EnemyId; B.PlayerName = Scenario.PlayerName; B.EnemyName = Scenario.EnemyName;
        B.EnemyMaxHp = Scenario.EnemyMaxHp; B.MaxRounds = Scenario.MaxRounds; B.EnergyPerRound = Scenario.EnergyPerRound;
        B.bIsValid = true; Out = MoveTemp(B); return true;
    }
}
bool ParseBattle(const TSharedPtr<FJsonObject>& O, const FString& ProfileId, const FString& BattleId, FHczsBattleView& Out)
{
    FHczsBattleView B; FScenario Scenario;
    if (!Exact(O, {TEXT("id"), TEXT("profileId"), TEXT("revision"), TEXT("scenario"), TEXT("state"), TEXT("createdAt"), TEXT("updatedAt")}) ||
        !Text(O, TEXT("id"), B.Id, 36) || !IsUuid(B.Id) || (!BattleId.IsEmpty() && B.Id != BattleId) ||
        !Text(O, TEXT("profileId"), B.ProfileId, 36) || B.ProfileId != ProfileId || !IsUuid(B.ProfileId) ||
        !Integer(O, TEXT("revision"), B.Revision, 1, 1000001) || !Timestamps(O) || !ParseScenario(Child(O, TEXT("scenario")), Scenario)) return false;
    if (Scenario.bIsParty) return ParsePartyState(Child(O, TEXT("state")), Scenario, B, Out);
    auto State = Child(O, TEXT("state")); FString Format; int64 Action = 0;
    if (!State.IsValid() || State->Values.Num() != 12 + (Scenario.bHasBreakdown ? 1 : 0) + (Scenario.bHasUltimates ? 1 : 0) ||
        !Text(State, TEXT("format"), Format, 40) || Format != (Scenario.bHasUltimates ? TEXT("hczs-battle-session-v3") :
            Scenario.bHasBreakdown ? TEXT("hczs-battle-session-v2") : TEXT("hczs-battle-session-v1")) ||
        !Text(State, TEXT("definitionId"), B.DefinitionId, 128) || B.DefinitionId != Scenario.DefinitionId ||
        !Counter(State, TEXT("round"), B.Round, 1, Scenario.MaxRounds) || !Counter(State, TEXT("energy"), B.Energy, 0, Scenario.EnergyPerRound) ||
        !Integer(State, TEXT("actionIndex"), Action, 0, 1000000) || Action + 1 != B.Revision ||
        !Text(State, TEXT("status"), B.Status, 24) || !Status(B.Status)) return false;
    B.ActionIndex = Action;
    auto Player = Child(State, TEXT("player")), Enemy = Child(State, TEXT("enemy"));
    if (!Exact(Player, {TEXT("hp"), TEXT("shield")}) || !Exact(Enemy, {TEXT("hp"), TEXT("shield")}) ||
        !Scalar(Child(Player, TEXT("hp")), B.PlayerHp) || !Scalar(Child(Player, TEXT("shield")), B.PlayerShield) ||
        !Scalar(Child(Enemy, TEXT("hp")), B.EnemyHp) || !Scalar(Child(Enemy, TEXT("shield")), B.EnemyShield) ||
        B.PlayerHp.Approximate > Scenario.PlayerMaxHp.Approximate || B.EnemyHp.Approximate > Scenario.EnemyMaxHp.Approximate) return false;
    const auto Outcome = State->TryGetField(TEXT("outcomeReason")); if (!Outcome.IsValid()) return false;
    if (B.Status == TEXT("player-turn"))
    {
        if (!Outcome->IsNull() || B.PlayerHp.Approximate <= 0 || B.EnemyHp.Approximate <= 0) return false;
    }
    else
    {
        if (!Text(State, TEXT("outcomeReason"), B.OutcomeReason, 40)) return false;
        if (B.Status == TEXT("won")) { if (B.OutcomeReason != TEXT("enemy-defeated") || B.EnemyHp.Approximate != 0 || B.PlayerHp.Approximate <= 0) return false; }
        else if (B.EnemyHp.Approximate <= 0 || !((B.OutcomeReason == TEXT("player-defeated") && B.PlayerHp.Approximate == 0) ||
            (B.OutcomeReason == TEXT("round-limit") && B.PlayerHp.Approximate > 0 && B.Round == Scenario.MaxRounds))) return false;
    }
    if (Scenario.bHasBreakdown)
    {
        auto Breakdown = Child(State, TEXT("breakdown"));
        if (!Exact(Breakdown, {TEXT("player"), TEXT("enemy")}) || !Counter(Breakdown, TEXT("player"), B.PlayerBreakdown, 0, 999) ||
            !Counter(Breakdown, TEXT("enemy"), B.EnemyBreakdown, 0, 999)) return false;
    }
    int32 GeneratedTotal = 0;
    if (Scenario.bHasUltimates)
    {
        const auto Ultimate = Child(State, TEXT("ultimate")); int32 Points = 0, GeneratedThisRound = 0;
        if (!Exact(Ultimate, {TEXT("chainOwnerId"), TEXT("points"), TEXT("generatedThisRound"), TEXT("generatedTotal")}) ||
            !Counter(Ultimate, TEXT("points"), Points, 0, Scenario.UltimatePointsRequired - 1) ||
            !Counter(Ultimate, TEXT("generatedThisRound"), GeneratedThisRound, 0, Scenario.UltimateMaxPerRound) ||
            !Counter(Ultimate, TEXT("generatedTotal"), GeneratedTotal, 0, B.Round * Scenario.UltimateMaxPerRound) ||
            GeneratedThisRound > GeneratedTotal || GeneratedTotal - GeneratedThisRound > (B.Round - 1) * Scenario.UltimateMaxPerRound ||
            (GeneratedThisRound == Scenario.UltimateMaxPerRound && Points != 0)) return false;
        const auto Owner = Ultimate->TryGetField(TEXT("chainOwnerId")); FString OwnerId;
        if (!Owner.IsValid() || (Points == 0 ? !Owner->IsNull() :
            (!Text(Ultimate, TEXT("chainOwnerId"), OwnerId, 128) || OwnerId != Scenario.UltimateOwnerId))) return false;
    }
    const int32 RegistryLimit = Scenario.Deck.Num() + (Scenario.bHasUltimates ? Scenario.MaxRounds * Scenario.UltimateMaxPerRound : 0);
    const auto* Registry = Array(State, TEXT("cards"), RegistryLimit);
    if (!Registry || Registry->Num() != Scenario.Deck.Num() + GeneratedTotal) return false;
    TMap<FString, FString> InstanceCards;
    for (int32 I = 0; I < Registry->Num(); ++I)
    {
        auto C = ObjectValue((*Registry)[I]); FString Instance, Card;
        const FString ExpectedInstance = I < Scenario.Deck.Num() ? Scenario.Deck[I].Key : FString::Printf(TEXT("ultimate:%d"), I - Scenario.Deck.Num() + 1);
        const FString ExpectedCard = I < Scenario.Deck.Num() ? Scenario.Deck[I].Value : Scenario.UltimateCardId;
        if (!Exact(C, {TEXT("instanceId"), TEXT("cardId")}) || !Text(C, TEXT("instanceId"), Instance, 128) ||
            !Text(C, TEXT("cardId"), Card, 128) || Instance != ExpectedInstance || Card != ExpectedCard) return false;
        InstanceCards.Add(Instance, Card);
    }
    auto Piles = Child(State, TEXT("piles"));
    if (!Exact(Piles, {TEXT("hand"), TEXT("draw"), TEXT("discard"), TEXT("exhausted"), TEXT("powerUsed"), TEXT("removed")})) return false;
    TSet<FString> Seen;
    for (const TCHAR* Zone : {TEXT("hand"), TEXT("draw"), TEXT("discard"), TEXT("exhausted"), TEXT("powerUsed"), TEXT("removed")})
    {
        const FString ZoneName(Zone);
        TArray<FString> Members; if (!StringIds(Array(Piles, Zone, ZoneName == TEXT("removed") ? RegistryLimit : 64), Members)) return false;
        if ((FString(Zone) == TEXT("hand") && Members.Num() > Scenario.HandLimit) ||
            ((ZoneName == TEXT("exhausted") || ZoneName == TEXT("powerUsed") || (ZoneName == TEXT("removed") && !Scenario.bHasUltimates)) && !Members.IsEmpty())) return false;
        for (const FString& Instance : Members)
        {
            const FString* CardId = InstanceCards.Find(Instance); if (!CardId || Seen.Contains(Instance)) return false;
            if (Scenario.bHasUltimates && (Instance.StartsWith(TEXT("ultimate:"), ESearchCase::CaseSensitive) ?
                (ZoneName != TEXT("hand") && ZoneName != TEXT("removed")) : ZoneName == TEXT("removed"))) return false;
            Seen.Add(Instance);
            if (FString(Zone) == TEXT("hand")) { auto Card = Scenario.Cards[*CardId]; Card.InstanceId = Instance; B.Hand.Add(MoveTemp(Card)); }
        }
        if (FString(Zone) == TEXT("draw")) B.DrawCount = Members.Num();
        if (FString(Zone) == TEXT("discard")) B.DiscardCount = Members.Num();
    }
    if (Seen.Num() != Registry->Num()) return false;
    auto Rng = Child(State, TEXT("rng")); FString Algorithm; int64 RandomState = 0;
    if (!Exact(Rng, {TEXT("algorithm"), TEXT("state")}) || !Text(Rng, TEXT("algorithm"), Algorithm, 32) ||
        Algorithm != TEXT("mulberry32-v1") || !Integer(Rng, TEXT("state"), RandomState, 0, 4294967295LL)) return false;
    const TArray<FString>& Intent = Scenario.EnemyIntents.IsValidIndex(B.Round - 1) ? Scenario.EnemyIntents[B.Round - 1] : Scenario.EnemyFallback;
    TArray<FString> IntentDescriptions; for (const FString& Skill : Intent) IntentDescriptions.Add(Scenario.EnemySkills[Skill]);
    B.EnemyIntentText = FString::Join(IntentDescriptions, TEXT(" / "));
    B.EnemyIntentSkills = Intent;
    for (const FString& Skill : Intent)
    {
        const FString* Damage = Scenario.EnemySkillDamage.Find(Skill);
        B.EnemyIntentDamage.Add(Damage ? *Damage : FString());
    }
    B.EncounterId = Scenario.EncounterId; B.Title = Scenario.Title; B.Notice = Scenario.Notice;
    B.PlayerId = Scenario.PlayerId; B.EnemyId = Scenario.EnemyId; B.PlayerName = Scenario.PlayerName; B.EnemyName = Scenario.EnemyName;
    B.PlayerMaxHp = Scenario.PlayerMaxHp; B.EnemyMaxHp = Scenario.EnemyMaxHp; B.MaxRounds = Scenario.MaxRounds;
    B.EnergyPerRound = Scenario.EnergyPerRound;
    B.bIsValid = true; Out = MoveTemp(B); return true;
}
bool ParseReceipt(const TSharedPtr<FJsonObject>& O, const FString& ProfileId, const FString& BattleId,
    const FString& EncounterId, int64 ExpectedRevision, FHczsBattleView& Out, TArray<FString>& Events,
    const FString& ActionType, const FString& InstanceId, FHczsBattleVisualReceipt* VisualReceipt)
{
    if (VisualReceipt) *VisualReceipt = FHczsBattleVisualReceipt();
    bool bReplayed = false;
    if (!Exact(O, {TEXT("battle"), TEXT("events"), TEXT("replayed")}) || !Bool(O, TEXT("replayed"), bReplayed) ||
        !ParseBattle(Child(O, TEXT("battle")), ProfileId, BattleId, Out) || Out.Revision != ExpectedRevision + 1 ||
        (!EncounterId.IsEmpty() && Out.EncounterId != EncounterId)) return false;
    const auto* Values = Array(O, TEXT("events"), 100000); if (!Values || Values->IsEmpty()) return false;
    auto First = ObjectValue((*Values)[0]); FString FirstType;
    if (!Text(First, TEXT("type"), FirstType, 40)) return false;
    if (ExpectedRevision == 0)
    {
        FString Definition; int64 Seed = 0;
        if (FirstType != TEXT("BattleStarted") || !Text(First, TEXT("definitionId"), Definition, 128) || Definition != Out.DefinitionId ||
            !Integer(First, TEXT("seed"), Seed, 0, 4294967295LL)) return false;
    }
    else if (ActionType == TEXT("play-card"))
    {
        FString PlayedInstance;
        if (FirstType != TEXT("CardPlayed") || !Text(First, TEXT("instanceId"), PlayedInstance, 128) || PlayedInstance != InstanceId) return false;
    }
    auto Last = ObjectValue(Values->Last()); FString LastType;
    if (!Text(Last, TEXT("type"), LastType, 40) || LastType != TEXT("StateUpdated") ||
        !SameJson(Last->TryGetField(TEXT("state")), Child(O, TEXT("battle"))->TryGetField(TEXT("state")))) return false;
    TArray<FString> Descriptions;
    FHczsBattleVisualReceipt Visual;
    auto Definition = Child(Child(Child(O, TEXT("battle")), TEXT("scenario")), TEXT("definition"));
    auto CardDefinitions = Child(Definition, TEXT("cards"));
    auto SkillDefinitions = Child(Definition, TEXT("enemySkills"));
    // ParseBattle already validated the exact base-deck prefix and each generated instance.
    const auto* Registry = Array(Child(Child(O, TEXT("battle")), TEXT("state")), TEXT("cards"), 3064);
    int32 PlayedCount = 0;
    const bool bParty = Out.bIsParty;
    const TSet<FString> Allowed = bParty ? TSet<FString>{TEXT("DiscardRecycled"), TEXT("CardDrawn"), TEXT("BattleEnded"), TEXT("ShieldAdded"),
        TEXT("DamageApplied"), TEXT("EnergyChanged"), TEXT("ShieldCleared"), TEXT("StateUpdated"), TEXT("BattleStarted"), TEXT("TurnStarted"),
        TEXT("CardPlayed"), TEXT("CardMoved"), TEXT("EnemySkillUsed"), TEXT("BuffChanged"), TEXT("MemberDefeated")} :
        TSet<FString>{TEXT("DiscardRecycled"), TEXT("CardDrawn"), TEXT("BattleEnded"), TEXT("BreakdownChanged"), TEXT("HealthRestored"),
        TEXT("ShieldAdded"), TEXT("DamageApplied"), TEXT("BreakdownTriggered"), TEXT("EnergyChanged"), TEXT("ShieldCleared"), TEXT("StateUpdated"),
        TEXT("BattleStarted"), TEXT("TurnStarted"), TEXT("CardPlayed"), TEXT("CardMoved"), TEXT("EnemySkillUsed")};
    const int32 PartySize = Out.Party.Num();
    for (const auto& V : *Values)
    {
        auto E = ObjectValue(V); FString Type; if (!Text(E, TEXT("type"), Type, 40) || !Allowed.Contains(Type)) return false;
        if (ExpectedRevision > 0 && (Type == TEXT("BattleStarted") || (ActionType == TEXT("end-turn") && Type == TEXT("CardPlayed")))) return false;
        if (bParty && Type == TEXT("CardPlayed"))
        {
            FString Card, Instance, Owner; int32 Cost = 0, DefinitionCost = 0, OwnerIndex = 0;
            if (!Exact(E, {TEXT("type"), TEXT("instanceId"), TEXT("cardId"), TEXT("cost"), TEXT("ownerIndex")}) || !Text(E, TEXT("cardId"), Card, 128) ||
                !Text(E, TEXT("instanceId"), Instance, 128) || !Counter(E, TEXT("cost"), Cost, 0, 1000000) ||
                !Counter(E, TEXT("ownerIndex"), OwnerIndex, 0, PartySize - 1) ||
                !Counter(Child(CardDefinitions, *Card), TEXT("cost"), DefinitionCost, 0, 1000000) || Cost != DefinitionCost || !Registry ||
                !Registry->ContainsByPredicate([&](const TSharedPtr<FJsonValue>& D)
                { const auto R = ObjectValue(D); FString I, C, W; return Text(R, TEXT("instanceId"), I, 128) && Text(R, TEXT("cardId"), C, 128) &&
                    Text(R, TEXT("ownerId"), W, 128) && I == Instance && C == Card && W == Out.Party[OwnerIndex].Id; })) return false;
            ++PlayedCount;
            Descriptions.Add(FString::Printf(TEXT("%s出牌 · %s"), *Out.Party[OwnerIndex].Name, *Card));
            FHczsBattleVisualEvent VEvent; VEvent.Type = Type; VEvent.CardId = Card; VEvent.MemberIndex = OwnerIndex; Visual.Events.Add(MoveTemp(VEvent));
        }
        else if (bParty && Type == TEXT("DamageApplied"))
        {
            FString Target, Actor, Amount, Skill; FHczsScalar Lost, Absorbed, PreviousHp, FinalHp, PreviousShield, FinalShield;
            int32 EffectIndex = 0, Member = -1, ActorIndex = 0, HitIndex = 0;
            if (!Text(E, TEXT("actor"), Actor, 16) || !Text(E, TEXT("target"), Target, 16)) return false;
            if (Actor == TEXT("party"))
            {
                if (!Exact(E, {TEXT("type"), TEXT("actor"), TEXT("actorIndex"), TEXT("target"), TEXT("effectIndex"), TEXT("amount"), TEXT("absorbed"),
                    TEXT("hpLost"), TEXT("previousHp"), TEXT("finalHp"), TEXT("previousShield"), TEXT("finalShield")}) || Target != TEXT("enemy") ||
                    !Counter(E, TEXT("actorIndex"), ActorIndex, 0, PartySize - 1)) return false;
            }
            else if (Actor == TEXT("enemy"))
            {
                if (!Exact(E, {TEXT("type"), TEXT("actor"), TEXT("skillId"), TEXT("effectIndex"), TEXT("hitIndex"), TEXT("target"), TEXT("memberIndex"),
                    TEXT("amount"), TEXT("absorbed"), TEXT("hpLost"), TEXT("previousHp"), TEXT("finalHp"), TEXT("previousShield"), TEXT("finalShield")}) ||
                    Target != TEXT("party") || !Text(E, TEXT("skillId"), Skill, 128) || !SkillDefinitions.IsValid() || !SkillDefinitions->HasField(*Skill) ||
                    !Counter(E, TEXT("hitIndex"), HitIndex, 0, 15) || !Counter(E, TEXT("memberIndex"), Member, 0, PartySize - 1)) return false;
            }
            else return false;
            if (!Text(E, TEXT("amount"), Amount, 64) || !DecimalInteger(Amount, 64) || !Counter(E, TEXT("effectIndex"), EffectIndex, 0, 31) ||
                !Scalar(Child(E, TEXT("hpLost")), Lost) || !Scalar(Child(E, TEXT("absorbed")), Absorbed) ||
                !Scalar(Child(E, TEXT("previousHp")), PreviousHp) || !Scalar(Child(E, TEXT("finalHp")), FinalHp) ||
                !Scalar(Child(E, TEXT("previousShield")), PreviousShield) || !Scalar(Child(E, TEXT("finalShield")), FinalShield)) return false;
            Descriptions.Add(Member < 0 ? FString::Printf(TEXT("敌方生命 -%s"), *Lost.Decimal)
                : FString::Printf(TEXT("%s生命 -%s"), *Out.Party[Member].Name, *Lost.Decimal));
            // The scene animates party member 0 as its player actor; other members have no recovered hit clip here.
            FHczsBattleVisualEvent VEvent; VEvent.Type = Type; VEvent.MemberIndex = Member;
            VEvent.Target = Member < 0 ? TEXT("enemy") : Member == 0 ? TEXT("player") : FString::Printf(TEXT("party-%d"), Member);
            Visual.Events.Add(MoveTemp(VEvent));
        }
        else if (bParty && Type == TEXT("BuffChanged"))
        {
            FString Actor, Target, Buff, Skill; int32 EffectIndex = 0, Index = 0, Previous = 0, Final = 0, Member = -1;
            if (!Text(E, TEXT("actor"), Actor, 16) || !Text(E, TEXT("target"), Target, 16) || !Text(E, TEXT("buffId"), Buff, 16) || Buff != TEXT("1001") ||
                !Counter(E, TEXT("effectIndex"), EffectIndex, 0, 31) || !Counter(E, TEXT("previousStacks"), Previous, 0, 999) ||
                !Counter(E, TEXT("finalStacks"), Final, Previous, 999)) return false;
            const bool bShape = Actor == TEXT("party") ? Target == TEXT("party") &&
                Exact(E, {TEXT("type"), TEXT("actor"), TEXT("actorIndex"), TEXT("effectIndex"), TEXT("target"), TEXT("memberIndex"), TEXT("buffId"),
                    TEXT("previousStacks"), TEXT("finalStacks")}) && Counter(E, TEXT("actorIndex"), Index, 0, PartySize - 1) &&
                    Counter(E, TEXT("memberIndex"), Member, 0, PartySize - 1) :
                Actor == TEXT("enemy") && Target == TEXT("enemy") &&
                Exact(E, {TEXT("type"), TEXT("actor"), TEXT("skillId"), TEXT("effectIndex"), TEXT("target"), TEXT("buffId"),
                    TEXT("previousStacks"), TEXT("finalStacks")}) && Text(E, TEXT("skillId"), Skill, 128) &&
                    SkillDefinitions.IsValid() && SkillDefinitions->HasField(*Skill);
            if (!bShape) return false;
            Descriptions.Add(FString::Printf(TEXT("%s攻击强化 %d层"), Member < 0 ? TEXT("敌方") : *Out.Party[Member].Name, Final));
        }
        else if (Type == TEXT("MemberDefeated"))
        {
            FString MemberId; int32 Member = 0;
            if (!Exact(E, {TEXT("type"), TEXT("memberIndex"), TEXT("memberId")}) || !Counter(E, TEXT("memberIndex"), Member, 0, PartySize - 1) ||
                !Text(E, TEXT("memberId"), MemberId, 128) || MemberId != Out.Party[Member].Id || Out.Party[Member].Hp.Approximate != 0) return false;
            Descriptions.Add(FString::Printf(TEXT("%s倒下"), *Out.Party[Member].Name));
            FHczsBattleVisualEvent VEvent; VEvent.Type = Type; VEvent.MemberIndex = Member; Visual.Events.Add(MoveTemp(VEvent));
        }
        else if (bParty && Type == TEXT("CardMoved"))
        {
            FString Instance, From, To;
            if (!Exact(E, {TEXT("type"), TEXT("instanceId"), TEXT("from"), TEXT("to")}) || !Text(E, TEXT("instanceId"), Instance, 128) || !Registry ||
                !Registry->ContainsByPredicate([&Instance](const TSharedPtr<FJsonValue>& D) { FString I; return Text(ObjectValue(D), TEXT("instanceId"), I, 128) && I == Instance; }) ||
                !Text(E, TEXT("from"), From, 16) || !Text(E, TEXT("to"), To, 16)) return false;
            const bool bDiscard = To == TEXT("discard") && (From == TEXT("hand") || From == TEXT("in-flight"));
            const bool bRemoved = To == TEXT("removed") && (From == TEXT("hand") || From == TEXT("draw") || From == TEXT("discard"));
            if (!bDiscard && !bRemoved) return false;
        }
        else if (Type == TEXT("CardPlayed"))
        {
            FString Card, Instance; int32 Cost = 0, DefinitionCost = 0;
            if (!Exact(E, {TEXT("type"), TEXT("instanceId"), TEXT("cardId"), TEXT("cost")}) || !Text(E, TEXT("cardId"), Card, 128) ||
                !Text(E, TEXT("instanceId"), Instance, 128) || !Counter(E, TEXT("cost"), Cost, 0, 1000000) ||
                !Counter(Child(CardDefinitions, *Card), TEXT("cost"), DefinitionCost, 0, 1000000) || Cost != DefinitionCost || !Registry ||
                !Registry->ContainsByPredicate([&Card, &Instance](const TSharedPtr<FJsonValue>& D)
                { const auto O = ObjectValue(D); FString I, C; return Text(O, TEXT("instanceId"), I, 128) && Text(O, TEXT("cardId"), C, 128) && I == Instance && C == Card; })) return false;
            ++PlayedCount;
            Descriptions.Add(FString::Printf(TEXT("已出牌 · %s"), *Card));
            FHczsBattleVisualEvent VEvent; VEvent.Type = Type; VEvent.CardId = Card; Visual.Events.Add(MoveTemp(VEvent));
        }
        else if (Type == TEXT("CardDrawn") || Type == TEXT("CardMoved"))
        {
            FString Instance;
            if (!Text(E, TEXT("instanceId"), Instance, 128) || !Registry) return false;
            const auto* Registered = Registry->FindByPredicate([&Instance](const TSharedPtr<FJsonValue>& Entry)
            { FString Id; return Text(ObjectValue(Entry), TEXT("instanceId"), Id, 128) && Id == Instance; });
            if (!Registered) return false;
            const bool bUltimate = Definition->HasField(TEXT("ultimateRules")) && Instance.StartsWith(TEXT("ultimate:"), ESearchCase::CaseSensitive);
            if (Type == TEXT("CardDrawn"))
            {
                if (E->HasField(TEXT("generated")))
                {
                    bool bGenerated = false;
                    if (!Exact(E, {TEXT("type"), TEXT("instanceId"), TEXT("generated")}) ||
                        !Bool(E, TEXT("generated"), bGenerated) || !bGenerated || !bUltimate) return false;
                }
                else if (!Exact(E, {TEXT("type"), TEXT("instanceId")}) || bUltimate) return false;
                FHczsBattleVisualEvent VEvent; VEvent.Type = Type; VEvent.InstanceId = Instance; Visual.Events.Add(MoveTemp(VEvent));
            }
            else
            {
                FString From, To;
                if (!Exact(E, {TEXT("type"), TEXT("instanceId"), TEXT("from"), TEXT("to")}) ||
                    !Text(E, TEXT("from"), From, 16) || (From != TEXT("hand") && From != TEXT("in-flight")) ||
                    !Text(E, TEXT("to"), To, 16) || To != (bUltimate ? TEXT("removed") : TEXT("discard"))) return false;
            }
        }
        else if (Type == TEXT("EnemySkillUsed"))
        {
            FString Skill; int32 Round = 0;
            if (!Exact(E, {TEXT("type"), TEXT("skillId"), TEXT("round")}) || !Text(E, TEXT("skillId"), Skill, 128) ||
                !SkillDefinitions.IsValid() || !SkillDefinitions->HasField(*Skill) || !Counter(E, TEXT("round"), Round, 1, Out.MaxRounds)) return false;
            Descriptions.Add(FString::Printf(TEXT("敌方行动 · %s"), *Skill));
            FHczsBattleVisualEvent VEvent; VEvent.Type = Type; VEvent.SkillId = Skill; Visual.Events.Add(MoveTemp(VEvent));
        }
        else if (Type == TEXT("DamageApplied"))
        {
            FString Target, Actor, Amount; FHczsScalar Lost, Absorbed, PreviousHp, FinalHp, PreviousShield, FinalShield; int32 EffectIndex = 0;
            if (!Exact(E, {TEXT("type"), TEXT("actor"), TEXT("target"), TEXT("effectIndex"), TEXT("amount"), TEXT("absorbed"), TEXT("hpLost"),
                TEXT("previousHp"), TEXT("finalHp"), TEXT("previousShield"), TEXT("finalShield")}) ||
                !Text(E, TEXT("target"), Target, 16) || (Target != TEXT("player") && Target != TEXT("enemy")) ||
                !Text(E, TEXT("actor"), Actor, 16) || (Actor != TEXT("player") && Actor != TEXT("enemy")) ||
                !Text(E, TEXT("amount"), Amount, 64) || !DecimalInteger(Amount, 64) || !Counter(E, TEXT("effectIndex"), EffectIndex, 0, 31) ||
                !Scalar(Child(E, TEXT("hpLost")), Lost) || !Scalar(Child(E, TEXT("absorbed")), Absorbed) ||
                !Scalar(Child(E, TEXT("previousHp")), PreviousHp) || !Scalar(Child(E, TEXT("finalHp")), FinalHp) ||
                !Scalar(Child(E, TEXT("previousShield")), PreviousShield) || !Scalar(Child(E, TEXT("finalShield")), FinalShield)) return false;
            Descriptions.Add(FString::Printf(TEXT("%s生命 -%s"), Target == TEXT("player") ? TEXT("本方") : TEXT("敌方"), *Lost.Decimal));
            FHczsBattleVisualEvent VEvent; VEvent.Type = Type; VEvent.Target = Target; Visual.Events.Add(MoveTemp(VEvent));
        }
        else if (Type == TEXT("TurnStarted"))
        {
            int32 Round = 0; if (!Counter(E, TEXT("round"), Round, 1, 1000)) return false;
            Descriptions.Add(FString::Printf(TEXT("第 %d 回合"), Round));
            FHczsBattleVisualEvent VEvent; VEvent.Type = Type; VEvent.Round = Round; Visual.Events.Add(MoveTemp(VEvent));
        }
        else if (Type == TEXT("BattleEnded")) Descriptions.Add(Out.Status == TEXT("won") ? TEXT("战斗胜利") : TEXT("战斗失败"));
        else if (Type == TEXT("BattleStarted")) Descriptions.Add(TEXT("战斗已创建并保存"));
        if (Descriptions.Num() > 64) Descriptions.RemoveAt(0, Descriptions.Num() - 64);
    }
    if ((ExpectedRevision == 0 && PlayedCount != 0) || (ActionType == TEXT("play-card") && PlayedCount != 1) ||
        (ActionType == TEXT("end-turn") && PlayedCount != 0)) return false;
    Visual.BattleId = Out.Id; Visual.ActionIndex = Out.ActionIndex; Visual.bValid = true;
    if (VisualReceipt) *VisualReceipt = MoveTemp(Visual);
    Events = MoveTemp(Descriptions); return true;
}
bool CanPublishVisualReceipt(const FHczsBattleView& Latest, const FHczsBattleVisualReceipt& Receipt)
{
    return Latest.bIsValid && Receipt.bValid && Latest.Id == Receipt.BattleId && Latest.ActionIndex == Receipt.ActionIndex;
}
bool IsSessionSceneReady(EHczsSessionPhase RequiredPhase, EHczsSessionPhase Phase, const FString& SelectedProfileId,
    bool bProfileStateCurrent, const FHczsHallPreference& Hall, const FHczsBattleView& Battle,
    bool bBattleStateCurrent, bool bRequestInFlight, bool bHasPendingIntent)
{
    if (RequiredPhase != Phase || !bProfileStateCurrent || !IsUuid(SelectedProfileId) || bRequestInFlight || bHasPendingIntent) return false;
    if (RequiredPhase == EHczsSessionPhase::Hall) return Hall.bIsValid;
    if (RequiredPhase == EHczsSessionPhase::Battle) return Battle.bIsValid && bBattleStateCurrent && Battle.ProfileId == SelectedProfileId;
    return false;
}
bool CanAcceptReply(uint64 CurrentEpoch, uint64 RequestEpoch, bool bShuttingDown, bool bRequestMatches)
{
    return !bShuttingDown && CurrentEpoch == RequestEpoch && bRequestMatches;
}
bool CanApplyBattleRevision(const FHczsBattleView& Existing, const FHczsBattleView& Incoming, int64 MinimumRevision)
{
    return Incoming.bIsValid && Incoming.Revision >= MinimumRevision &&
        (!Existing.bIsValid || Existing.Id != Incoming.Id || (Incoming.Revision >= Existing.Revision && Incoming.DefinitionId == Existing.DefinitionId));
}
FString Serialize(const TSharedPtr<FJsonObject>& O)
{
    FString Text; const auto Writer = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text);
    FJsonSerializer::Serialize(O.ToSharedRef(), Writer); return Text;
}
FString ServerErrorCode(const TSharedPtr<FJsonObject>& O)
{
    FString Code; return Text(Child(O, TEXT("error")), TEXT("code"), Code, 80) && IsId(Code, 80) ? Code : TEXT("UNEXPECTED_RESPONSE");
}
}
