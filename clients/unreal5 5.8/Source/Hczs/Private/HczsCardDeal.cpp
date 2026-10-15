#include "HczsCardDeal.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include <limits>
#endif

namespace HczsCardDeal
{
namespace
{
constexpr double HalfPi = 1.57079632679489661923;

bool FinitePoint(const FVector2D& Point)
{
    return FMath::IsFinite(Point.X) && FMath::IsFinite(Point.Y);
}

double SineOut(double T) { return FMath::Sin(T * HalfPi); }
double SineIn(double T) { return 1 - FMath::Cos(T * HalfPi); }

FVector2D CubicBezier(const FVector2D& Start, const FVector2D& First,
    const FVector2D& Second, const FVector2D& End, double T)
{
    const double R = 1 - T;
    return Start * (R * R * R) + First * (3 * R * R * T) +
        Second * (3 * R * T * T) + End * (T * T * T);
}
}

const TCHAR* PhaseName(EPhase Phase)
{
    switch (Phase)
    {
    case EPhase::Waiting: return TEXT("waiting");
    case EPhase::FlyToCentre: return TEXT("fly-to-centre");
    case EPhase::CentreHold: return TEXT("centre-hold");
    case EPhase::DropToHand: return TEXT("drop-to-hand");
    case EPhase::Finished: return TEXT("finished");
    default: return TEXT("unknown");
    }
}

bool Sample(double ElapsedSinceDrawCall, int32 Index, int32 Count,
    const FVector2D& FitSize, double CardWidth, const FVector2D& OwnCardOrigin,
    const FVector2D& HandCenter, double HandAngle, FSample& Out, FString& Error)
{
    Out = FSample(); Error.Reset();
    if (Count < 1 || Count > 8 || Index < 0 || Index >= Count)
    {
        Error = TEXT("Round-start source deal requires Count 1..8 and a valid zero-based Index; negative-delay N>=9 is not verified");
        return false;
    }
    if (!FMath::IsFinite(ElapsedSinceDrawCall) || ElapsedSinceDrawCall < 0 ||
        !FinitePoint(FitSize) || FitSize.X <= 0 || FitSize.Y <= 0 ||
        !FMath::IsFinite(CardWidth) || CardWidth <= 0 || CardWidth > 1120 ||
        !FinitePoint(OwnCardOrigin) || !FinitePoint(HandCenter) ||
        !FMath::IsFinite(HandAngle) || HandAngle < -180 || HandAngle > 180)
    {
        Error = TEXT("Invalid source deal time, design geometry, card width, or fan angle");
        return false;
    }

    // calcOffset, module2487 lines137-148; DesignConst.getUnitMargin_Z=45,
    // getAllRange_Z=1120. This is distinct from the final fan geometry supplied by caller.
    double CentreOffset = 0;
    if (Count > 1)
    {
        double UnitWidth = CardWidth + 45;
        double AllWidth = UnitWidth * (Count - 1) + CardWidth;
        if (AllWidth > 1120)
        {
            AllWidth = 1120;
            UnitWidth = (AllWidth - CardWidth) / (Count - 1);
        }
        CentreOffset = -AllWidth / 2 + Index * UnitWidth + CardWidth / 2;
    }
    const FVector2D Start = OwnCardOrigin + FVector2D(-100 - FitSize.X / 2, -FitSize.Y / 2);
    const FVector2D Centre = OwnCardOrigin + FVector2D(CentreOffset, -FitSize.Y / 2);
    const double Delay = .05 * (Count - Index - 1) + .1;
    const double Flight = .05 * (Count - Index - 1) + .04;
    // Same source decimal durations, expressed as hundredths so an exact boundary
    // such as 1.15 is not classified as unfinished by an addition-rounding ULP.
    const double DropStart = (80.0 + Count) / 100;
    const double Hold = DropStart - Delay - Flight;
    const double Duration = (110.0 + Count) / 100;
    if (Hold < 0 || !FinitePoint(Start) || !FinitePoint(Centre))
    {
        Error = TEXT("Source deal geometry overflow or unsupported negative hold");
        return false;
    }

    FSample Result;
    Result.bVisible = true;
    if (ElapsedSinceDrawCall >= Duration)
    {
        Result.Position = HandCenter;
        Result.AngleZ = HandAngle;
        Result.bFinished = true;
        Result.Phase = EPhase::Finished;
    }
    else if (ElapsedSinceDrawCall < Delay)
    {
        Result.Position = Start;
        Result.Phase = EPhase::Waiting;
    }
    else if (ElapsedSinceDrawCall < Delay + Flight)
    {
        const double T = FMath::Clamp((ElapsedSinceDrawCall - Delay) / Flight, 0.0, 1.0);
        Result.Position = FMath::Lerp(Start, Centre, SineOut(T));
        Result.Phase = EPhase::FlyToCentre;
    }
    else if (ElapsedSinceDrawCall < DropStart)
    {
        Result.Position = Centre;
        Result.Phase = EPhase::CentreHold;
    }
    else
    {
        const double DropElapsed = ElapsedSinceDrawCall - DropStart;
        const double T = FMath::Clamp(DropElapsed / .3, 0.0, 1.0);
        const double CurveT = T * T * T * T; // EaseQuarticActionIn wraps the entire BezierTo.
        const double Direction = HandCenter.X < OwnCardOrigin.X ? -1 : 1;
        // Source Y is up; cp1's +15 becomes -15 in design/screen coordinates.
        const FVector2D First = Centre + FVector2D(Direction * 30, -15);
        const FVector2D Second = Centre + FVector2D(Direction * 60, 0);
        Result.Position = CubicBezier(Centre, First, Second, HandCenter, CurveT);
        if (DropElapsed < .15)
        {
            const double RotationT = SineOut(FMath::Clamp(DropElapsed / .15, 0.0, 1.0));
            Result.TiltX = -35 * RotationT;
            Result.AngleZ = HandAngle * RotationT;
        }
        else
        {
            Result.TiltX = FMath::Lerp(-35.0, 0.0,
                SineIn(FMath::Clamp((DropElapsed - .15) / .15, 0.0, 1.0)));
            Result.AngleZ = HandAngle;
        }
        Result.Phase = EPhase::DropToHand;
    }
    if (!FinitePoint(Result.Position))
    {
        Error = TEXT("Non-finite sampled source card position");
        return false;
    }
    Out = Result;
    return true;
}

bool Sample(double ElapsedSinceDrawCall, int32 Index, int32 Count,
    const FVector2D& FitSize, double CardWidth, const FVector2D& HandCenter,
    double HandAngle, FSample& Out, FString& Error)
{
    return Sample(ElapsedSinceDrawCall, Index, Count, FitSize, CardWidth,
        FVector2D(FitSize.X / 2, FitSize.Y), HandCenter, HandAngle, Out, Error);
}
}

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsCardDealTimingTest, "Hczs.SourceUI.CardDeal.SourceTimingAndPosition",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsCardDealTimingTest::RunTest(const FString& Parameters)
{
    using namespace HczsCardDeal;
    const FVector2D Fit(1280, 720), Hand(400, 650);
    FSample Out; FString Error;
    const auto At = [&](double Time) { return Sample(Time, 0, 5, Fit, 120, Hand, -12, Out, Error); };
    TestTrue(TEXT("Original source starts without embedding first-delay"), At(0));
    TestEqual(TEXT("Off-screen source start"), Out.Position, FVector2D(-100, 360));
    TestTrue(TEXT("Source opacity255 applies during off-screen delay"), Out.bVisible);
    TestTrue(TEXT("Phase waiting"), Out.Phase == EPhase::Waiting);
    At(.3 - 1e-8);
    TestEqual(TEXT("No movement before stagger deadline"), Out.Position, FVector2D(-100, 360));
    At(.3 + 1e-8);
    TestTrue(TEXT("Flight starts at .3 for N5 index0"), Out.Phase == EPhase::FlyToCentre);
    At(.42); // Half of source .24s flight, sin-out, centre offset -330.
    TestTrue(TEXT("Sine-out, not linear, flight midpoint"),
        Out.Position.Equals(FVector2D(189.9137802864845, 360), 0.000001));
    At(.54 + 1e-8);
    TestTrue(TEXT("Centre hold follows flight"), Out.Phase == EPhase::CentreHold);
    TestEqual(TEXT("Original 45px centre margin"), Out.Position, FVector2D(310, 360));
    At(.85 - 1e-8);
    TestEqual(TEXT("Centre remains fixed until common drop"), Out.Position, FVector2D(310, 360));
    At(.85 + 1e-8);
    TestTrue(TEXT("Common drop begins .8+.01N"), Out.Phase == EPhase::DropToHand);
    At(1.15);
    TestTrue(TEXT("Nominal completion 1.1+.01N; not reserved2+.01N"), Out.bFinished);
    TestEqual(TEXT("Exact final hand position"), Out.Position, Hand);
    TestEqual(TEXT("Exact final fan angle"), Out.AngleZ, -12.0);
    TestEqual(TEXT("No residual X tilt"), Out.TiltX, 0.0);
    At(100);
    TestEqual(TEXT("Late sample remains final"), Out.Position, Hand);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsCardDealCurveTest, "Hczs.SourceUI.CardDeal.SourceDropAndCoordinateSpace",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsCardDealCurveTest::RunTest(const FString& Parameters)
{
    using namespace HczsCardDeal;
    const FVector2D Fit(1280, 720);
    FSample Out; FString Error;
    TestTrue(TEXT("Sample single-card centre"), Sample(.5, 0, 1, Fit, 120, FVector2D(640, 650), 0, Out, Error));
    TestEqual(TEXT("Source zPos maps to screen centre"), Out.Position, FVector2D(640, 360));
    Sample(.5, 0, 1, Fit, 120, FVector2D(640, 682), FVector2D(640, 612), 0, Out, Error);
    TestEqual(TEXT("Caller explicit upward adaptation applies once"), Out.Position, FVector2D(640, 322));
    // N5 index0 at drop+.15: position Bezier uses u=(.5)^4=.0625,
    // while source RotateTo has already reached its first target (-35,0,-12).
    Sample(1.0, 0, 5, Fit, 120, FVector2D(400, 650), -12, Out, Error);
    TestTrue(TEXT("Quartic Bezier midpoint remains near centre-flight point"),
        Out.Position.Equals(FVector2D(304.4189453125, 357.598876953125), 0.000001));
    TestTrue(TEXT("Peak source X tilt"), FMath::IsNearlyEqual(Out.TiltX, -35.0, 0.000001));
    TestTrue(TEXT("Z angle reached before position arrival"), FMath::IsNearlyEqual(Out.AngleZ, -12.0, 0.000001));
    Sample(.925, 0, 5, Fit, 120, FVector2D(400, 650), -12, Out, Error);
    TestTrue(TEXT("First half tilt is sine-out"), FMath::IsNearlyEqual(Out.TiltX, -24.74873734152916, 0.000001));
    TestTrue(TEXT("First half fan rotation is sine-out"), FMath::IsNearlyEqual(Out.AngleZ, -8.48528137423857, 0.000001));
    Sample(1.075, 0, 5, Fit, 120, FVector2D(400, 650), -12, Out, Error);
    TestTrue(TEXT("Second half tilt returns via sine-in"), FMath::IsNearlyEqual(Out.TiltX, -24.74873734152916, 0.000001));
    TestEqual(TEXT("Second half fan angle does not rotate again"), Out.AngleZ, -12.0);
    Sample(.96, 0, 1, Fit, 120, FVector2D(640, 650), 0, Out, Error);
    TestTrue(TEXT("Exactly centred destination uses source right-side control points"), Out.Position.X > 640);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsCardDealBoundariesTest, "Hczs.SourceUI.CardDeal.BoundsAndStagger",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsCardDealBoundariesTest::RunTest(const FString& Parameters)
{
    using namespace HczsCardDeal;
    const FVector2D Fit(1280, 720), Hand(640, 650);
    FSample Out; FString Error;
    Sample(.2, 7, 8, Fit, 120, Hand, 0, Out, Error);
    TestTrue(TEXT("Last index flies first"), Out.Phase == EPhase::CentreHold);
    TestEqual(TEXT("1120px row-width clamp, last centre +500"), Out.Position, FVector2D(1140, 360));
    Sample(.2, 0, 8, Fit, 120, Hand, 0, Out, Error);
    TestTrue(TEXT("First index waits .45 for N8"), Out.Phase == EPhase::Waiting);
    Sample(.86, 0, 8, Fit, 120, Hand, 0, Out, Error);
    TestTrue(TEXT("N8 first card positive .04s hold"), Out.Phase == EPhase::CentreHold);
    TestEqual(TEXT("Clamped first centre -500"), Out.Position, FVector2D(140, 360));
    for (int32 Count = 1; Count <= 8; ++Count)
    {
        for (int32 Index = 0; Index < Count; ++Index)
        {
            TestTrue(TEXT("Every supported count/index samples"), Sample(.8 + .01 * Count + 1e-8, Index, Count, Fit, 120, Hand, 0, Out, Error));
            TestTrue(TEXT("All source cards share drop start"), Out.Phase == EPhase::DropToHand);
            Sample(1.1 + .01 * Count, Index, Count, Fit, 120, Hand, 0, Out, Error);
            TestTrue(TEXT("All source cards share completion"), Out.bFinished);
        }
    }
    TestFalse(TEXT("N9 negative source hold rejected"), Sample(0, 0, 9, Fit, 120, Hand, 0, Out, Error));
    TestFalse(TEXT("Failed sample does not leave visible stale data"), Out.bVisible);
    TestTrue(TEXT("Failure explains unsupported case"), !Error.IsEmpty());
    TestFalse(TEXT("Empty group is not a card"), Sample(0, 0, 0, Fit, 120, Hand, 0, Out, Error));
    TestFalse(TEXT("Index outside group rejected"), Sample(0, 5, 5, Fit, 120, Hand, 0, Out, Error));
    TestFalse(TEXT("Negative time is caller delay, not sampler time"), Sample(-.5, 0, 1, Fit, 120, Hand, 0, Out, Error));
    TestFalse(TEXT("Invalid fit size rejected"), Sample(0, 0, 1, FVector2D(0, 720), 120, Hand, 0, Out, Error));
    TestFalse(TEXT("Invalid width rejected"), Sample(0, 0, 1, Fit, 0, Hand, 0, Out, Error));
    TestFalse(TEXT("Nonfinite time rejected"), Sample(std::numeric_limits<double>::infinity(), 0, 1, Fit, 120, Hand, 0, Out, Error));
    TestFalse(TEXT("Nonfinite destination rejected"), Sample(0, 0, 1, Fit, 120,
        FVector2D(std::numeric_limits<double>::quiet_NaN(), 0), 0, Out, Error));
    TestFalse(TEXT("Unverified multi-turn angle rejected"), Sample(0, 0, 1, Fit, 120, Hand, 360, Out, Error));
    return true;
}
#endif
