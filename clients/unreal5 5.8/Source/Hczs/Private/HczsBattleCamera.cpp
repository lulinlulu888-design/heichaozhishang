#include "HczsBattleCamera.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Misc/AutomationTest.h"

namespace HczsBattleCamera
{
namespace
{
// GameStartup.initGlobals aspectList order with ResolutionConst classes:
// SuperLongScreen, iPhoneX, iPhone (inherits CommonResolutionConst), iPad.
constexpr double ClassAspects[] = {2.58333, 2.1653, 1.777, 1.333};
constexpr double ClassFovs[] = {30.0, 35.65, 35.985, 46.75};
constexpr double PhoneFov = 35.985, PadFov = 46.75, VeryShortScreenFov = 55.0;
}

double ResolutionClassFov(double Aspect)
{
    double MinDelta = 10000;
    int32 Target = -1;
    for (int32 Index = 0; Index < UE_ARRAY_COUNT(ClassAspects); ++Index)
    {
        const double Delta = FMath::Abs(ClassAspects[Index] - Aspect);
        if (Delta < MinDelta) { MinDelta = Delta; Target = Index; }
    }
    return ClassFovs[Target];
}

double SourceVerticalFov(double Aspect)
{
    if (1.77777 - Aspect > 0.01 && Aspect - 1.33333 > 0.01)
        return PhoneFov + (PadFov - PhoneFov) / 0.44444 * (1.77777 - Aspect);
    if (Aspect < 1.33333 && FMath::Abs(1.33333 - Aspect) > FMath::Abs(Aspect - 1.0))
        return VeryShortScreenFov;
    return ResolutionClassFov(Aspect);
}

double HorizontalFov(double VerticalDegrees, double Aspect)
{
    return FMath::RadiansToDegrees(2.0 * FMath::Atan(FMath::Tan(FMath::DegreesToRadians(VerticalDegrees) * 0.5) * Aspect));
}

bool Apply(ACameraActor* Camera, const FIntPoint& ViewportSize)
{
    UCameraComponent* Component = Camera ? Camera->GetCameraComponent() : nullptr;
    if (!Component || ViewportSize.X <= 0 || ViewportSize.Y <= 0) return false;
    const double Aspect = double(ViewportSize.X) / ViewportSize.Y;
    // The source renders to the whole window; it has no letterbox constraint.
    Component->SetConstraintAspectRatio(false);
    Component->SetAspectRatio(Aspect);
    Component->SetFieldOfView(HorizontalFov(SourceVerticalFov(Aspect), Aspect));
    return true;
}
}

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsBattleCameraFovTest, "Hczs.Battle.Camera.SourceFov",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsBattleCameraFovTest::RunTest(const FString& Parameters)
{
    using namespace HczsBattleCamera;
    TestEqual(TEXT("Exact 16:9 is outside the interpolation band and uses iPhone/Common"), SourceVerticalFov(16.0 / 9), 35.985);
    TestEqual(TEXT("Exact 4:3 uses iPad"), SourceVerticalFov(4.0 / 3), 46.75);
    TestTrue(TEXT("3:2 interpolates linearly between iPhone and iPad"),
        FMath::IsNearlyEqual(SourceVerticalFov(1.5), 35.985 + 10.765 / 0.44444 * (1.77777 - 1.5), 1e-9));
    TestEqual(TEXT("iPhoneX aspect"), SourceVerticalFov(2.1653), 35.65);
    TestEqual(TEXT("20:9 snaps to iPhoneX"), SourceVerticalFov(20.0 / 9), 35.65);
    TestEqual(TEXT("1860:720 SuperLongScreen"), SourceVerticalFov(1860.0 / 720), 30.0);
    TestEqual(TEXT("Square is a very short screen"), SourceVerticalFov(1.0), 55.0);
    TestEqual(TEXT("Below 4:3 but nearer 4:3 keeps iPad"), SourceVerticalFov(1.3), 46.75);
    TestTrue(TEXT("4:3 and 16:9 both give about 60 degrees horizontal"),
        FMath::IsNearlyEqual(HorizontalFov(46.75, 4.0 / 3), 60.0, 0.2) &&
        FMath::IsNearlyEqual(HorizontalFov(35.985, 16.0 / 9), 60.0, 0.2));
    return true;
}
#endif
