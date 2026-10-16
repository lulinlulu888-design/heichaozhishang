#pragma once

#include "CoreMinimal.h"

// Pure round-start _C_H flight from APK CardStates.py (2487), lines 324-374.
// Does not schedule the first-draw .5s delay, change input, or mutate a battle.
namespace HczsCardDeal
{
enum class EPhase : uint8
{
    Waiting,
    FlyToCentre,
    CentreHold,
    DropToHand,
    Finished
};

struct HCZS_API FSample
{
    FVector2D Position = FVector2D::ZeroVector;
    double AngleZ = 0;
    double TiltX = 0;
    bool bVisible = false;
    bool bFinished = false;
    EPhase Phase = EPhase::Waiting;
};

HCZS_API const TCHAR* PhaseName(EPhase Phase);

/** Nominal completion of the whole _C_H dispatch after the draw call (last-index onLastDispatchEnd). */
inline double DispatchSeconds(int32 Count) { return 1.1 + .01 * Count; }

// Index is zero-based, Count is 1..8. N>=9 can produce a negative source DelayTime;
// its native scheduling is unverified and is rejected instead of silently clamped.
// FitSize and CardWidth are source design units. HandCenter is the final card centre
// in screen/design coordinates (X right, Y down); HandAngle is the source/Slate
// clockwise fan angle in degrees, restricted to the unambiguous [-180,180] range.
// OwnCardOrigin maps OwnCardArea/Main/MiddleBottom/Base local (0,0) to the screen.
// In the source 1280x720 layout it is (640,720), so local zPos(0,360) is (640,360).
// A caller adapting the hand upward to origin (640,682) gets centre-flight Y=322;
// that 38px adaptation is not an original flight offset and is never hard-coded here.
// Source sets opacity255 at t=0; waiting cards remain visible at their off-screen start.
HCZS_API bool Sample(double ElapsedSinceDrawCall, int32 Index, int32 Count,
    const FVector2D& FitSize, double CardWidth, const FVector2D& OwnCardOrigin,
    const FVector2D& HandCenter, double HandAngle, FSample& Out, FString& Error);

// Convenience overload using the original bottom-centre root, without layout adaptation.
HCZS_API bool Sample(double ElapsedSinceDrawCall, int32 Index, int32 Count,
    const FVector2D& FitSize, double CardWidth, const FVector2D& HandCenter,
    double HandAngle, FSample& Out, FString& Error);
}
