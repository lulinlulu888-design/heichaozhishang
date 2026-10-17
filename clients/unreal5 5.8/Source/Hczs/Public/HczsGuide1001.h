#pragma once

#include "CoreMinimal.h"

/** guide_show_table anchor: FightDialog _cTouch hand area, a hand card, EnergyArea, or EndTurnArea Replace. */
enum class EHczsGuideAnchor : uint8 { None, Hand, Card, Energy, EndTurn };
/** GUIDE_DETAILS_TYPE 3 is D_OUT_CARD, 4 is D_END_ROUND; other steps wait for a tap. */
enum class EHczsGuideAdvance : uint8 { Tap, PlayCard, EndTurn };

struct FHczsGuideStep
{
    int32 Id;
    int32 NextId;
    float Delay;
    const TCHAR* Talker;
    const TCHAR* Text;
    float TextX;
    EHczsGuideAnchor Anchor;
    int32 CardIndex;
    float BoxX, BoxY, BoxWidth, BoxHeight;
    const TCHAR* Gesture;
    EHczsGuideAdvance Advance;
};

/** Guide group 1001 (序章-第一场战斗) steps 1850-1860 in guide_table order, text from guide_show_table. */
TArrayView<const FHczsGuideStep> HczsGuide1001Steps();

/**
 * Client-only guide progress for one tutorial battle. Triggers 1850/1858 use the source
 * battleRoundCount condition; trigger value 999 (1853-1857) is unresolved, so 1853 follows
 * the first card play and 1856 starts when round-1 energy reaches zero (reconstruction).
 */
struct HCZS_API FHczsGuide1001
{
    FString BattleId;
    int32 StepIndex = INDEX_NONE;
    double ShowAt = 0;
    int64 StepActionIndex = 0;
    int32 StepRound = 0;
    int64 LastActionIndex = 0;
    int32 LastRound = 0;
    bool bChainCard = false, bChainEnergy = false, bChainRound = false, bComplete = false;

    void Observe(const FString& Battle, const FString& Status, int32 Round, int32 Energy, int64 ActionIndex, double Now);
    const FHczsGuideStep* Current() const;
    bool IsVisible(double Now) const { return Current() && Now >= ShowAt; }
    /** Consumes a tap for a visible Tap step; action steps ignore taps. */
    bool Tap(double Now);
private:
    void Start(int32 Id, double Now);
    void Next(double Now);
};
