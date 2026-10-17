#pragma once

#include "CoreMinimal.h"

struct FHczsPrologueAvgLine
{
    const TCHAR* Voice;
    const TCHAR* Text;
};

/** Dialogue 138 lines in source row order. Boss lines omit the #f(z:0) and #l markup. */
const TArrayView<const FHczsPrologueAvgLine> HczsPrologueAvg138();

/** -1 is closed. Each advance reveals the next line, then stays on the finished sentinel. */
int32 HczsAdvancePrologueAvg138(int32 Index);
