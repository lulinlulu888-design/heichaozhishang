#pragma once

#include "CoreMinimal.h"

// Source audio_event_table cues routed through ui_battle.bnk. Only the in-bank actor-mixer
// volume is applied; bus volume, filters and the master mix are not reproduced.
namespace HczsUiAudio
{
enum class ECue : uint8
{
    DrawCard,
    FapaiB
};

struct HCZS_API FCue
{
    const TCHAR* Key = TEXT("");
    const TCHAR* Event = TEXT("");
    TArray<uint32> Sources;
    float VolumeDb = 0;
    int32 AvoidRepeat = 0;
};

HCZS_API const FCue& Get(ECue Cue);
/** Uniform choice that never repeats Previous when the container avoids one repeat. */
HCZS_API int32 PickVariant(ECue Cue, int32 Previous, FRandomStream& Random);
HCZS_API FString SoundPath(uint32 SourceId);
HCZS_API float VolumeMultiplier(ECue Cue);
}
