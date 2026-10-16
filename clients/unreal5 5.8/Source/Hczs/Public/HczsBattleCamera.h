#pragma once

#include "CoreMinimal.h"

class ACameraActor;

/** Original battle camera projection: `CameraBase` takes only the scene preset
 * `camera_1` transform, then `CameraBattle` replaces its FOV by window aspect
 * using `ResolutionConst` classes chosen in `GameStartup.initGlobals`. */
namespace HczsBattleCamera
{
/** `Globals.ResolutionConst.BATTLE_CAMERA_FOV` for the nearest source aspect class. */
HCZS_API double ResolutionClassFov(double Aspect);
/** Final `CameraBattle.Fov` (NeoX vertical degrees) for a width/height aspect. */
HCZS_API double SourceVerticalFov(double Aspect);
HCZS_API double HorizontalFov(double VerticalDegrees, double Aspect);
/** Applies the source FOV for the given viewport size; returns false if unusable. */
HCZS_API bool Apply(ACameraActor* Camera, const FIntPoint& ViewportSize);
}
