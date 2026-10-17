#pragma once

#include "CoreMinimal.h"

struct FHczsPrologueAvgLine
{
    const TCHAR* Voice;
    /** Voice owner: 艾尔莎 / 未来 from the party HUD names, 终焉使者 from monster 2013 NAME. */
    const TCHAR* Speaker;
    const TCHAR* Text;
};

/** Dialogue 138 lines in source row order. Boss lines omit the #f(z:0) and #l markup. */
const TArrayView<const FHczsPrologueAvgLine> HczsPrologueAvg138();

/** -1 is closed. Each advance reveals the next line, then stays on the finished sentinel. */
int32 HczsAdvancePrologueAvg138(int32 Index);

/** Dialogue 134 narration rows 93-97 and 100 over avgBlack; #r is a line break. */
const TArrayView<const TCHAR* const> HczsPrologueAvg134();

/** Row 100 fills %s from RegisterName; the name input is not recovered, so the profile name stands in. */
FString HczsPrologueAvg134Line(int32 Index, const FString& PlayerName);
