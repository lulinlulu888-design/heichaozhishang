#include "HczsSourceUiTimeline.h"

#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#endif

namespace HczsSourceUiTimeline
{
namespace
{
using FObject = TSharedPtr<FJsonObject>;
using FValues = TArray<TSharedPtr<FJsonValue>>;

bool Number(const FObject& Object, const TCHAR* Key, double& Out)
{
    return Object->TryGetNumberField(Key, Out) && FMath::IsFinite(Out);
}

bool Integer(const FObject& Object, const TCHAR* Key, int32& Out)
{
    double Value = 0;
    if (!Number(Object, Key, Value) || Value < MIN_int32 || Value > MAX_int32 || FMath::FloorToDouble(Value) != Value)
        return false;
    Out = static_cast<int32>(Value);
    return true;
}

bool Numbers(const TSharedPtr<FJsonValue>& Json, int32 Count, TArray<double>& Out)
{
    const FValues* Values = nullptr;
    if (!Json.IsValid() || !Json->TryGetArray(Values) || Values->Num() != Count) return false;
    Out.Reset(Count);
    for (const auto& Item : *Values)
    {
        double Value = 0;
        if (!Item.IsValid() || !Item->TryGetNumber(Value) || !FMath::IsFinite(Value) || FMath::Abs(Value) > 10000000)
            return false;
        Out.Add(Value);
    }
    return true;
}

bool Vector(const FObject& Object, const TCHAR* Key, FVector2D& Out)
{
    TArray<double> Values;
    if (!Numbers(Object->TryGetField(Key), 2, Values)) return false;
    Out = FVector2D(Values[0], Values[1]);
    return true;
}

bool Strings(const FObject& Object, const TCHAR* Key, TArray<FString>& Out)
{
    if (!Object->HasField(Key)) return true;
    const FValues* Values = nullptr;
    if (!Object->TryGetArrayField(Key, Values) || Values->Num() > 1024) return false;
    for (const auto& Value : *Values)
    {
        FString Text;
        if (!Value->TryGetString(Text) || Text.Len() > 1024) return false;
        Out.AddUnique(Text);
    }
    return true;
}

bool ByteRange(double Value) { return Value >= 0 && Value <= 255; }

bool IsVectorTrack(const FString& Property)
{
    return Property == TEXT("Position") || Property == TEXT("Scale") ||
        Property == TEXT("RotationSkew") || Property == TEXT("AnchorPoint");
}

bool IsSupportedTrack(const FString& Property)
{
    return IsVectorTrack(Property) || Property == TEXT("Alpha") || Property == TEXT("CColor") ||
        Property == TEXT("VisibleForFrame") || Property == TEXT("FileData");
}

bool IsDiscrete(const FString& Property)
{
    return Property == TEXT("VisibleForFrame") || Property == TEXT("FileData");
}

bool SupportsEasing(const FClip& Clip, const FFrame& Frame)
{
    if (Frame.bHasEasingPoints) return false;
    if (Frame.EasingType == 0 || Frame.EasingType == 10000) return true;
    return Clip.EasingPolicy == TEXT("cocos2d-x-3.17.2") &&
        (Frame.EasingType == 1 || Frame.EasingType == 2 || Frame.EasingType == 14 ||
         Frame.EasingType == 19 || Frame.EasingType == 20);
}

double Ease(int32 Type, double T)
{
    // Explicit upstream compatibility: CCTweenFunction.{h,cpp}, cocos2d-x-3.17.2.
    // APK fork numerical equivalence is deliberately not claimed.
    switch (Type)
    {
    case 1: return 1 - FMath::Cos(T * UE_PI / 2);
    case 2: return FMath::Sin(T * UE_PI / 2);
    case 14: { const double R = 1 - T; return 1 - R * R * R * R * R; }
    case 19: return 1 - FMath::Sqrt(FMath::Max(0.0, 1 - T * T));
    case 20: return FMath::Sqrt(FMath::Max(0.0, 1 - (T - 1) * (T - 1)));
    default: return T;
    }
}

FAffine2D Compose(const FAffine2D& A, const FAffine2D& B)
{
    FAffine2D Out;
    Out.M00 = A.M00 * B.M00 + A.M01 * B.M10;
    Out.M01 = A.M00 * B.M01 + A.M01 * B.M11;
    Out.M10 = A.M10 * B.M00 + A.M11 * B.M10;
    Out.M11 = A.M10 * B.M01 + A.M11 * B.M11;
    Out.TX = A.M00 * B.TX + A.M01 * B.TY + A.TX;
    Out.TY = A.M10 * B.TX + A.M11 * B.TY + A.TY;
    return Out;
}

FAffine2D NodeTransform(const FNode& Node)
{
    const double Angle = Node.RotationSkew.X * UE_PI / 180;
    const double C = FMath::Cos(Angle), S = FMath::Sin(Angle);
    FAffine2D Out;
    // Positive source Z rotation is clockwise, before the final source Y-up -> Slate Y-down conversion.
    Out.M00 = C * Node.Scale.X; Out.M01 = S * Node.Scale.Y;
    Out.M10 = -S * Node.Scale.X; Out.M11 = C * Node.Scale.Y;
    Out.TX = Node.Position.X - Out.M00 * Node.Anchor.X * Node.Size.X - Out.M01 * Node.Anchor.Y * Node.Size.Y;
    Out.TY = Node.Position.Y - Out.M10 * Node.Anchor.X * Node.Size.X - Out.M11 * Node.Anchor.Y * Node.Size.Y;
    return Out;
}

bool FiniteTransform(const FAffine2D& Value)
{
    return FMath::IsFinite(Value.M00) && FMath::IsFinite(Value.M01) && FMath::IsFinite(Value.M10) &&
        FMath::IsFinite(Value.M11) && FMath::IsFinite(Value.TX) && FMath::IsFinite(Value.TY);
}

void SampleTrack(const FClip& Clip, const FTrack& Track, double SourceFrame, FNode& Node)
{
    int32 Left = 0;
    while (Left + 1 < Track.Frames.Num() && Track.Frames[Left + 1].Index <= SourceFrame) ++Left;
    const FFrame& A = Track.Frames[Left];
    const FFrame& B = Track.Frames[FMath::Min(Left + 1, Track.Frames.Num() - 1)];
    if (Track.Property == TEXT("FileData")) { Node.SpriteId = A.SpriteId; return; }
    if (Track.Property == TEXT("VisibleForFrame")) { Node.bVisible = A.BoolValue; return; }
    double T = 0;
    if (A.bTween && SourceFrame > A.Index && B.Index > A.Index && SupportsEasing(Clip, A))
        T = Ease(A.EasingType, FMath::Clamp((SourceFrame - A.Index) / (B.Index - A.Index), 0.0, 1.0));
    const auto Value = [&](int32 I) { return FMath::Lerp(A.Value[I], B.Value[I], T); };
    if (Track.Property == TEXT("Position")) Node.Position = FVector2D(Value(0), Value(1));
    else if (Track.Property == TEXT("Scale")) Node.Scale = FVector2D(Value(0), Value(1));
    else if (Track.Property == TEXT("RotationSkew")) Node.RotationSkew = FVector2D(Value(0), Value(1));
    else if (Track.Property == TEXT("AnchorPoint")) Node.Anchor = FVector2D(Value(0), Value(1));
    // Source ColorFrame/AlphaFrame store byte channels; CColor's serialized A is not an opacity track.
    else if (Track.Property == TEXT("Alpha")) Node.Alpha = FMath::FloorToDouble(Value(0));
    else if (Track.Property == TEXT("CColor")) Node.Color = FLinearColor(
        static_cast<float>(FMath::FloorToDouble(Value(1)) / 255),
        static_cast<float>(FMath::FloorToDouble(Value(2)) / 255),
        static_cast<float>(FMath::FloorToDouble(Value(3)) / 255), 1);
}
}

FVector2D FAffine2D::TransformPoint(const FVector2D& Point) const
{
    return FVector2D(M00 * Point.X + M01 * Point.Y + TX, M10 * Point.X + M11 * Point.Y + TY);
}

double FClip::DurationSeconds() const
{
    return FramesPerSecond > 0 && Speed > 0 ? (EndFrame - StartFrame) / FramesPerSecond / Speed : 0;
}

bool Parse(const FString& Json, FClip& OutClip, FString& OutError)
{
    OutClip = FClip(); OutError.Reset();
    const auto Fail = [&](const FString& Message) { OutError = Message; return false; };
    FObject Root;
    if (Json.Len() > 4 * 1024 * 1024 || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Root) || !Root.IsValid())
        return Fail(TEXT("Invalid or oversized source UI timeline JSON"));
    FString Schema;
    FClip Clip;
    if (!Root->TryGetStringField(TEXT("schema"), Schema) || Schema != TEXT("hczs-source-ui-timeline-v1") ||
        !Number(Root, TEXT("fps"), Clip.FramesPerSecond) || Clip.FramesPerSecond <= 0 || Clip.FramesPerSecond > 240 ||
        !Number(Root, TEXT("speed"), Clip.Speed) || Clip.Speed <= 0 || Clip.Speed > 100 ||
        !Integer(Root, TEXT("startFrame"), Clip.StartFrame) || !Integer(Root, TEXT("endFrame"), Clip.EndFrame) ||
        Clip.StartFrame < 0 || Clip.EndFrame < Clip.StartFrame || Clip.EndFrame > 1000000)
        return Fail(TEXT("Invalid source UI timeline header"));
    if (Root->HasField(TEXT("easingPolicy")) && !Root->TryGetStringField(TEXT("easingPolicy"), Clip.EasingPolicy))
        return Fail(TEXT("Invalid easing policy"));
    if (Clip.EasingPolicy != TEXT("linear-only") && Clip.EasingPolicy != TEXT("cocos2d-x-3.17.2"))
        return Fail(TEXT("Unknown easing policy"));
    if (!Strings(Root, TEXT("unsupported"), Clip.Unsupported)) return Fail(TEXT("Invalid unsupported metadata"));
    if (Clip.EasingPolicy == TEXT("cocos2d-x-3.17.2"))
        Clip.CompatibilityNotes.Add(TEXT("Upstream Cocos2d-x 3.17.2 easing compatibility; APK fork numerical equivalence not verified"));
    const FValues* Nodes = nullptr;
    const FValues* Tracks = nullptr;
    if (!Root->TryGetArrayField(TEXT("nodes"), Nodes) || Nodes->IsEmpty() || Nodes->Num() > 512 ||
        !Root->TryGetArrayField(TEXT("tracks"), Tracks) || Tracks->Num() > 4096)
        return Fail(TEXT("Invalid node/track arrays"));
    TMap<int32, int32> NodeByTag;
    for (int32 I = 0; I < Nodes->Num(); ++I)
    {
        const FObject* Object = nullptr;
        if (!(*Nodes)[I]->TryGetObject(Object)) return Fail(TEXT("Node must be an object"));
        FNode Node;
        TArray<double> Color;
        if (!(*Object)->TryGetStringField(TEXT("name"), Node.Name) || !(*Object)->TryGetStringField(TEXT("classname"), Node.ClassName) ||
            !Integer(*Object, TEXT("action_tag"), Node.ActionTag) || NodeByTag.Contains(Node.ActionTag) ||
            !Integer(*Object, TEXT("parent"), Node.Parent) || Node.Parent < INDEX_NONE || Node.Parent >= I ||
            !Vector(*Object, TEXT("position"), Node.Position) || !Vector(*Object, TEXT("scale"), Node.Scale) ||
            !Vector(*Object, TEXT("rotation_skew"), Node.RotationSkew) || !Vector(*Object, TEXT("anchor"), Node.Anchor) ||
            !Vector(*Object, TEXT("size"), Node.Size) || Node.Size.X < 0 || Node.Size.Y < 0 ||
            !Number(*Object, TEXT("alpha"), Node.Alpha) || !ByteRange(Node.Alpha) ||
            !Numbers((*Object)->TryGetField(TEXT("color_argb")), 4, Color) ||
            !(*Object)->TryGetBoolField(TEXT("visible"), Node.bVisible) ||
            !(*Object)->TryGetBoolField(TEXT("flip_x"), Node.bFlipX) || !(*Object)->TryGetBoolField(TEXT("flip_y"), Node.bFlipY))
            return Fail(FString::Printf(TEXT("Invalid node at index %d (including duplicate tag or nonpreceding parent)"), I));
        for (const double Channel : Color) if (!ByteRange(Channel)) return Fail(TEXT("Invalid node color channel"));
        Node.Color = FLinearColor(static_cast<float>(Color[1] / 255),
            static_cast<float>(Color[2] / 255), static_cast<float>(Color[3] / 255), 1);
        if (((*Object)->HasField(TEXT("spriteId")) && !(*Object)->TryGetStringField(TEXT("spriteId"), Node.SpriteId)) ||
            ((*Object)->HasField(TEXT("z_order")) && !Integer(*Object, TEXT("z_order"), Node.ZOrder)) ||
            !Strings(*Object, TEXT("unsupported"), Node.Unsupported)) return Fail(TEXT("Invalid optional node metadata"));
        if (Node.ClassName != TEXT("Node") && Node.ClassName != TEXT("SingleNode") && Node.ClassName != TEXT("Panel") &&
            Node.ClassName != TEXT("Sprite") && Node.ClassName != TEXT("ImageView") && Node.ClassName != TEXT("Text"))
            Node.Unsupported.AddUnique(TEXT("node-class:") + Node.ClassName);
        NodeByTag.Add(Node.ActionTag, I);
        Clip.Nodes.Add(MoveTemp(Node));
    }
    TSet<FString> TrackKeys;
    int32 TotalFrames = 0;
    for (const auto& JsonTrack : *Tracks)
    {
        const FObject* Object = nullptr;
        FTrack Track;
        int32 ActionTag = 0;
        const FValues* Frames = nullptr;
        if (!JsonTrack->TryGetObject(Object) || !(*Object)->TryGetStringField(TEXT("property"), Track.Property) ||
            !Integer(*Object, TEXT("action_tag"), ActionTag) || !NodeByTag.Contains(ActionTag) ||
            !(*Object)->TryGetArrayField(TEXT("frames"), Frames) || Frames->IsEmpty()) return Fail(TEXT("Invalid track target/frames"));
        TotalFrames += Frames->Num();
        if (TotalFrames > 32768) return Fail(TEXT("Too many source timeline frames"));
        Track.NodeIndex = NodeByTag[ActionTag];
        const FString Key = FString::Printf(TEXT("%d:%s"), ActionTag, *Track.Property);
        if (TrackKeys.Contains(Key)) return Fail(TEXT("Duplicate track for the same node property"));
        TrackKeys.Add(Key);
        Track.bSupported = IsSupportedTrack(Track.Property);
        if (!Track.bSupported) Clip.Nodes[Track.NodeIndex].Unsupported.AddUnique(TEXT("track:") + Track.Property);
        int32 PreviousIndex = -1;
        for (const auto& JsonFrame : *Frames)
        {
            const FObject* FrameObject = nullptr;
            FFrame Frame;
            if (!JsonFrame->TryGetObject(FrameObject) || !Integer(*FrameObject, TEXT("index"), Frame.Index) ||
                Frame.Index <= PreviousIndex || Frame.Index > 1000000 ||
                !(*FrameObject)->TryGetBoolField(TEXT("tween"), Frame.bTween) ||
                !Integer(*FrameObject, TEXT("easing_type"), Frame.EasingType)) return Fail(TEXT("Invalid or unordered keyframe"));
            PreviousIndex = Frame.Index;
            const FValues* Points = nullptr;
            if ((*FrameObject)->HasField(TEXT("easing_points")))
            {
                if (!(*FrameObject)->TryGetArrayField(TEXT("easing_points"), Points)) return Fail(TEXT("Invalid easing points"));
                Frame.bHasEasingPoints = !Points->IsEmpty();
            }
            if (Track.bSupported)
            {
                FString Kind;
                if (!(*FrameObject)->TryGetStringField(TEXT("kind"), Kind)) return Fail(TEXT("Missing supported frame kind"));
                const bool ExpectedKind =
                    (Track.Property == TEXT("Position") && Kind == TEXT("point")) ||
                    ((Track.Property == TEXT("Scale") || Track.Property == TEXT("RotationSkew") ||
                        Track.Property == TEXT("AnchorPoint")) && Kind == TEXT("scale")) ||
                    (Track.Property == TEXT("CColor") && Kind == TEXT("color")) ||
                    (Track.Property == TEXT("Alpha") && Kind == TEXT("int")) ||
                    (Track.Property == TEXT("VisibleForFrame") && Kind == TEXT("bool")) ||
                    (Track.Property == TEXT("FileData") && Kind == TEXT("texture"));
                if (!ExpectedKind) return Fail(TEXT("Mismatched supported frame kind: ") + Track.Property);
                const auto Value = (*FrameObject)->TryGetField(TEXT("value"));
                bool ValidValue = false;
                if (IsVectorTrack(Track.Property)) ValidValue = Numbers(Value, 2, Frame.Value);
                else if (Track.Property == TEXT("CColor"))
                {
                    ValidValue = Numbers(Value, 4, Frame.Value);
                    for (const double Channel : Frame.Value) ValidValue &= ByteRange(Channel);
                }
                else if (Track.Property == TEXT("Alpha"))
                {
                    double Alpha = 0;
                    ValidValue = Number(*FrameObject, TEXT("value"), Alpha) && ByteRange(Alpha);
                    Frame.Value.Add(Alpha);
                }
                else if (Track.Property == TEXT("VisibleForFrame")) ValidValue = Value.IsValid() && Value->TryGetBool(Frame.BoolValue);
                else if (Track.Property == TEXT("FileData"))
                    ValidValue = (*FrameObject)->TryGetStringField(TEXT("spriteId"), Frame.SpriteId) && !Frame.SpriteId.IsEmpty();
                if (!ValidValue) return Fail(TEXT("Invalid value for supported track: ") + Track.Property);
            }
            Track.Frames.Add(MoveTemp(Frame));
        }
        for (int32 I = 0; I + 1 < Track.Frames.Num(); ++I)
        {
            const FFrame& Frame = Track.Frames[I];
            if (Track.bSupported && !IsDiscrete(Track.Property) && Frame.bTween && !SupportsEasing(Clip, Frame))
                Clip.Nodes[Track.NodeIndex].Unsupported.AddUnique(FString::Printf(TEXT("easing:%d%s:%s:frame%d:held-until-next-key"),
                    Frame.EasingType, Frame.bHasEasingPoints ? TEXT("+custom-points") : TEXT(""), *Track.Property, Frame.Index));
        }
        Clip.Tracks.Add(MoveTemp(Track));
    }
    Clip.bValid = true;
    OutClip = MoveTemp(Clip);
    return true;
}

bool Evaluate(const FClip& Clip, double Seconds, const FVector2D& DesignOrigin, FSample& OutSample, FString& OutError)
{
    OutSample = FSample(); OutError.Reset();
    if (!Clip.bValid || !FMath::IsFinite(Seconds) || Seconds < 0 || !FMath::IsFinite(DesignOrigin.X) || !FMath::IsFinite(DesignOrigin.Y))
    { OutError = TEXT("Invalid clip, elapsed time, or design origin"); return false; }
    FSample Sample;
    Sample.bFinished = Seconds >= Clip.DurationSeconds();
    Sample.SourceFrame = Sample.bFinished ? Clip.EndFrame : Clip.StartFrame + Seconds * Clip.FramesPerSecond * Clip.Speed;
    Sample.Unsupported = Clip.Unsupported;
    Sample.CompatibilityNotes = Clip.CompatibilityNotes;
    TArray<FNode> State = Clip.Nodes;
    for (const FTrack& Track : Clip.Tracks)
        if (Track.bSupported) SampleTrack(Clip, Track, Sample.SourceFrame, State[Track.NodeIndex]);
    TArray<FAffine2D> SourceTransforms;
    TArray<TArray<int32>> Children;
    Children.SetNum(State.Num() + 1);
    FAffine2D SourceToDesign;
    SourceToDesign.M11 = -1; SourceToDesign.TX = DesignOrigin.X; SourceToDesign.TY = DesignOrigin.Y;
    for (int32 I = 0; I < State.Num(); ++I)
    {
        const FNode& Node = State[I];
        FNodeSample Result;
        Result.NodeIndex = I; Result.ActionTag = Node.ActionTag; Result.Parent = Node.Parent; Result.ZOrder = Node.ZOrder;
        Result.Name = Node.Name; Result.ClassName = Node.ClassName; Result.SpriteId = Node.SpriteId;
        Result.Position = Node.Position; Result.Scale = Node.Scale; Result.RotationSkew = Node.RotationSkew;
        Result.Anchor = Node.Anchor; Result.Size = Node.Size; Result.bVisible = Node.bVisible;
        Result.Tint = Node.Color; Result.Tint.A = static_cast<float>(Node.Alpha / 255);
        Result.Unsupported = Node.Unsupported;
        Result.bTransformSupported = FMath::IsNearlyEqual(Node.RotationSkew.X, Node.RotationSkew.Y, 0.000001);
        if (!Result.bTransformSupported) Result.Unsupported.AddUnique(TEXT("unequal-rotation-skew:transform-not-equivalent"));
        FAffine2D Global = NodeTransform(Node);
        if (Node.Parent != INDEX_NONE)
        {
            Global = Compose(SourceTransforms[Node.Parent], Global);
            const FNodeSample& Parent = Sample.Nodes[Node.Parent];
            Result.bVisible &= Parent.bVisible;
            Result.Tint *= Parent.Tint;
            Result.bTransformSupported &= Parent.bTransformSupported;
            if (!Parent.bTransformSupported) Result.Unsupported.AddUnique(TEXT("unsupported-parent-transform"));
        }
        SourceTransforms.Add(Global);
        FAffine2D QuadToSource;
        QuadToSource.M00 = Node.bFlipX ? -1 : 1;
        QuadToSource.TX = Node.bFlipX ? Node.Size.X : 0;
        QuadToSource.M11 = Node.bFlipY ? 1 : -1;
        QuadToSource.TY = Node.bFlipY ? 0 : Node.Size.Y;
        Result.LocalToDesign = Compose(SourceToDesign, Compose(Global, QuadToSource));
        if (!FiniteTransform(Result.LocalToDesign))
        { OutError = TEXT("Non-finite composed source UI transform"); return false; }
        for (const FString& Unsupported : Result.Unsupported)
            Sample.Unsupported.AddUnique(FString::Printf(TEXT("node%d:%s"), Node.ActionTag, *Unsupported));
        Children[Node.Parent == INDEX_NONE ? State.Num() : Node.Parent].Add(I);
        Sample.Nodes.Add(MoveTemp(Result));
    }
    for (auto& Siblings : Children)
        Siblings.StableSort([&](int32 A, int32 B) { return State[A].ZOrder < State[B].ZOrder; });
    TFunction<void(int32)> Visit = [&](int32 Index)
    {
        const TArray<int32>& NodeChildren = Children[Index];
        for (int32 Child : NodeChildren) if (State[Child].ZOrder < 0) Visit(Child);
        if (Index != State.Num()) Sample.DrawOrder.Add(Index);
        for (int32 Child : NodeChildren) if (State[Child].ZOrder >= 0) Visit(Child);
    };
    Visit(State.Num());
    OutSample = MoveTemp(Sample);
    return true;
}
}

#if WITH_DEV_AUTOMATION_TESTS
namespace
{
FString TimelineFixture(const FString& Nodes, const FString& Tracks, const FString& Policy = TEXT("linear-only"))
{
    return FString::Printf(TEXT("{\"schema\":\"hczs-source-ui-timeline-v1\",\"fps\":60,\"speed\":0.5,\"startFrame\":5,\"endFrame\":65,\"easingPolicy\":\"%s\",\"nodes\":[%s],\"tracks\":[%s]}"),
        *Policy, *Nodes, *Tracks);
}

FString TimelineNode(int32 Tag, int32 Parent = -1)
{
    return FString::Printf(TEXT("{\"name\":\"node\",\"classname\":\"Sprite\",\"action_tag\":%d,\"parent\":%d,\"position\":[0,0],\"scale\":[1,1],\"rotation_skew\":[0,0],\"anchor\":[0,0],\"size\":[10,20],\"alpha\":255,\"color_argb\":[255,255,255,255],\"visible\":true,\"flip_x\":false,\"flip_y\":false,\"spriteId\":\"base\"}"), Tag, Parent);
}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsSourceUiKeysTest, "Hczs.SourceUI.Timeline.SourceKeysAndStepTracks",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsSourceUiKeysTest::RunTest(const FString& Parameters)
{
    using namespace HczsSourceUiTimeline;
    // Small excerpt of elite/In S_Glow source keys (tag 1019405898), not a synthetic fade.
    const FString Tracks = TEXT(R"JSON(
      {"property":"Position","action_tag":1019405898,"frames":[
        {"index":19,"tween":true,"easing_type":0,"kind":"point","value":[121,114]}]},
      {"property":"Alpha","action_tag":1019405898,"frames":[
        {"index":15,"tween":true,"easing_type":0,"kind":"int","value":0},
        {"index":16,"tween":true,"easing_type":0,"kind":"int","value":255},
        {"index":25,"tween":true,"easing_type":0,"kind":"int","value":255},
        {"index":26,"tween":true,"easing_type":0,"kind":"int","value":0}]},
      {"property":"FileData","action_tag":1019405898,"frames":[
        {"index":16,"tween":true,"easing_type":20,"kind":"texture","spriteId":"sprite_b0e5e3ad3a7c948f"},
        {"index":17,"tween":true,"easing_type":20,"kind":"texture","spriteId":"sprite_1fe3fc6a5d01704b"}]},
      {"property":"VisibleForFrame","action_tag":1019405898,"frames":[
        {"index":15,"tween":true,"easing_type":20,"kind":"bool","value":false},
        {"index":16,"tween":true,"easing_type":20,"kind":"bool","value":true}]}
    )JSON");
    FClip Clip; FSample Sample; FString Error;
    if (!TestTrue(TEXT("Parse source key excerpt"), Parse(TimelineFixture(TimelineNode(1019405898), Tracks), Clip, Error)))
    { AddError(Error); return false; }
    TestEqual(TEXT("Elite In duration uses 60 fps and speed .5"), Clip.DurationSeconds(), 2.0);
    if (!TestTrue(TEXT("Sample start"), Evaluate(Clip, 0, FVector2D::ZeroVector, Sample, Error))) return false;
    TestEqual(TEXT("In starts at source frame 5"), Sample.SourceFrame, 5.0);
    TestEqual(TEXT("Before first key uses first key position"), Sample.Nodes[0].Position, FVector2D(121, 114));
    TestEqual(TEXT("Before first texture key uses first texture"), Sample.Nodes[0].SpriteId, FString(TEXT("sprite_b0e5e3ad3a7c948f")));
    Evaluate(Clip, (15.5 - 5) / 30, FVector2D::ZeroVector, Sample, Error);
    TestFalse(TEXT("Visibility does not interpolate"), Sample.Nodes[0].bVisible);
    TestTrue(TEXT("Alpha interpolates with source byte truncation"), FMath::IsNearlyEqual(Sample.Nodes[0].Tint.A, 127.0f / 255));
    Evaluate(Clip, (16.5 - 5) / 30, FVector2D::ZeroVector, Sample, Error);
    TestTrue(TEXT("Visibility switches at exact key"), Sample.Nodes[0].bVisible);
    TestEqual(TEXT("Texture held between keys despite tween/easing"), Sample.Nodes[0].SpriteId, FString(TEXT("sprite_b0e5e3ad3a7c948f")));
    Evaluate(Clip, (17.0 - 5) / 30, FVector2D::ZeroVector, Sample, Error);
    TestEqual(TEXT("Texture switches at exact key"), Sample.Nodes[0].SpriteId, FString(TEXT("sprite_1fe3fc6a5d01704b")));
    Evaluate(Clip, 200, FVector2D::ZeroVector, Sample, Error);
    TestTrue(TEXT("Finished"), Sample.bFinished);
    TestEqual(TEXT("Clamped last frame"), Sample.SourceFrame, 65.0);
    TestEqual(TEXT("Last alpha key holds"), Sample.Nodes[0].Tint.A, 0.0f);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsSourceUiTreeTest, "Hczs.SourceUI.Timeline.ParentTransformsAndVisibility",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsSourceUiTreeTest::RunTest(const FString& Parameters)
{
    using namespace HczsSourceUiTimeline;
    FString Parent = TimelineNode(1);
    Parent.ReplaceInline(TEXT("\"position\":[0,0]"), TEXT("\"position\":[100,50]"));
    Parent.ReplaceInline(TEXT("\"scale\":[1,1]"), TEXT("\"scale\":[2,3]"));
    Parent.ReplaceInline(TEXT("\"anchor\":[0,0]"), TEXT("\"anchor\":[0.5,0.5]"));
    Parent.ReplaceInline(TEXT("\"alpha\":255"), TEXT("\"alpha\":128"));
    Parent.ReplaceInline(TEXT("[255,255,255,255]"), TEXT("[255,128,255,64]"));
    Parent.ReplaceInline(TEXT("\"flip_x\":false"), TEXT("\"flip_x\":true"));
    FString Child = TimelineNode(2, 0);
    Child.ReplaceInline(TEXT("\"position\":[0,0]"), TEXT("\"position\":[5,6]"));
    Child.ReplaceInline(TEXT("\"alpha\":255"), TEXT("\"alpha\":128"));
    FString NegativeChild = TimelineNode(3, 0);
    NegativeChild.ReplaceInline(TEXT("\"spriteId\":\"base\""), TEXT("\"spriteId\":\"base\",\"z_order\":-1"));
    FClip Clip; FSample Sample; FString Error;
    if (!TestTrue(TEXT("Parse parent tree"), Parse(TimelineFixture(Parent + TEXT(",") + Child + TEXT(",") + NegativeChild, TEXT("")), Clip, Error))) return false;
    Evaluate(Clip, 0, FVector2D(1000, 500), Sample, Error);
    TestEqual(TEXT("Parent anchor and flipped top-left"), Sample.Nodes[0].LocalToDesign.TransformPoint(FVector2D::ZeroVector), FVector2D(1110, 420));
    TestEqual(TEXT("Child inherits parent transform but not image flip"), Sample.Nodes[1].LocalToDesign.TransformPoint(FVector2D::ZeroVector), FVector2D(1100, 402));
    TestTrue(TEXT("Parent alpha multiplied"), FMath::IsNearlyEqual(Sample.Nodes[1].Tint.A, (128.f / 255) * (128.f / 255)));
    TestTrue(TEXT("Parent RGB multiplied"), FMath::IsNearlyEqual(Sample.Nodes[1].Tint.R, 128.f / 255));
    TestEqual(TEXT("Negative child paints before parent"), Sample.DrawOrder[0], 2);
    TestEqual(TEXT("Parent paints before nonnegative child"), Sample.DrawOrder[1], 0);
    Clip.Nodes[0].bVisible = false;
    Evaluate(Clip, 0, FVector2D::ZeroVector, Sample, Error);
    TestFalse(TEXT("Hidden parent hides child"), Sample.Nodes[1].bVisible);
    Clip.Nodes[0].bVisible = true; Clip.Nodes[0].RotationSkew = FVector2D(90, 90);
    Clip.Nodes[0].Scale = FVector2D(1, 1); Clip.Nodes[0].Anchor = FVector2D::ZeroVector;
    Clip.Nodes[0].Position = FVector2D::ZeroVector; Clip.Nodes[0].bFlipX = false;
    Evaluate(Clip, 0, FVector2D::ZeroVector, Sample, Error);
    TestTrue(TEXT("Clockwise source rotation maps to clockwise design quad"),
        Sample.Nodes[0].LocalToDesign.TransformPoint(FVector2D(10, 20)).Equals(FVector2D(0, 10), 0.000001));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsSourceUiPolicyTest, "Hczs.SourceUI.Timeline.UnsupportedAndValidation",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHczsSourceUiPolicyTest::RunTest(const FString& Parameters)
{
    using namespace HczsSourceUiTimeline;
    const FString Tracks = TEXT(R"JSON(
      {"property":"Position","action_tag":1,"frames":[
        {"index":5,"tween":true,"easing_type":14,"kind":"point","value":[0,0]},
        {"index":65,"tween":true,"easing_type":0,"kind":"point","value":[100,20]}]},
      {"property":"Splendor_Light","action_tag":1,"frames":[
        {"index":5,"tween":true,"easing_type":0,"kind":"fork_float_vector","value":[1]}]}
    )JSON");
    FClip Clip; FSample Sample; FString Error;
    TestTrue(TEXT("Unknown shader track retained"), Parse(TimelineFixture(TimelineNode(1), Tracks), Clip, Error));
    Evaluate(Clip, 1, FVector2D::ZeroVector, Sample, Error);
    TestEqual(TEXT("Unknown nonlinear easing is held, not linearized"), Sample.Nodes[0].Position, FVector2D::ZeroVector);
    TestTrue(TEXT("Both limitations observable"), Sample.Unsupported.Num() >= 2);
    TestTrue(TEXT("Explicit upstream compatibility"), Parse(TimelineFixture(TimelineNode(1), Tracks, TEXT("cocos2d-x-3.17.2")), Clip, Error));
    Evaluate(Clip, 1, FVector2D::ZeroVector, Sample, Error);
    TestEqual(TEXT("Quint out halfway"), Sample.Nodes[0].Position.X, 96.875);
    TestTrue(TEXT("Compatibility not claimed as verified APK equivalence"), !Sample.CompatibilityNotes.IsEmpty());
    const FString StepTracks = Tracks.Replace(TEXT("\"tween\":true"), TEXT("\"tween\":false"));
    TestTrue(TEXT("Non-tween numeric track parses"), Parse(TimelineFixture(TimelineNode(1), StepTracks, TEXT("cocos2d-x-3.17.2")), Clip, Error));
    Evaluate(Clip, 1, FVector2D::ZeroVector, Sample, Error);
    TestEqual(TEXT("Non-tween numeric value is held"), Sample.Nodes[0].Position, FVector2D::ZeroVector);
    const FString CustomTracks = Tracks.Replace(TEXT("\"easing_type\":14"), TEXT("\"easing_type\":-1,\"easing_points\":[[0,0],[1,1]]"));
    TestTrue(TEXT("Unknown custom easing parses with limitation"), Parse(TimelineFixture(TimelineNode(1), CustomTracks, TEXT("cocos2d-x-3.17.2")), Clip, Error));
    Evaluate(Clip, 1, FVector2D::ZeroVector, Sample, Error);
    TestEqual(TEXT("Custom easing is not silently approximated"), Sample.Nodes[0].Position, FVector2D::ZeroVector);
    const FString ColorTrack = TEXT(R"JSON({"property":"CColor","action_tag":1,"frames":[
      {"index":5,"tween":true,"easing_type":0,"kind":"color","value":[0,255,0,255]},
      {"index":65,"tween":true,"easing_type":0,"kind":"color","value":[0,0,255,255]}]})JSON");
    TestTrue(TEXT("RGB source track parses"), Parse(TimelineFixture(TimelineNode(1), ColorTrack), Clip, Error));
    Evaluate(Clip, 1, FVector2D::ZeroVector, Sample, Error);
    TestTrue(TEXT("RGB interpolation truncates source byte"), FMath::IsNearlyEqual(Sample.Nodes[0].Tint.R, 127.f / 255));
    TestEqual(TEXT("Serialized CColor A does not replace node opacity"), Sample.Nodes[0].Tint.A, 1.f);
    Clip.Nodes[0].RotationSkew = FVector2D(30, 45);
    Evaluate(Clip, 1, FVector2D::ZeroVector, Sample, Error);
    TestFalse(TEXT("Unequal rotation/skew cannot silently draw as equivalent"), Sample.Nodes[0].bTransformSupported);
    TestFalse(TEXT("Nonpreceding parent rejected"), Parse(TimelineFixture(TimelineNode(1, 0), TEXT("")), Clip, Error));
    TestFalse(TEXT("Duplicate action tags rejected"), Parse(TimelineFixture(TimelineNode(1) + TEXT(",") + TimelineNode(1), TEXT("")), Clip, Error));
    TestFalse(TEXT("Unknown policy rejected"), Parse(TimelineFixture(TimelineNode(1), Tracks, TEXT("guess")), Clip, Error));
    const FString BadOrder = Tracks.Replace(TEXT("\"index\":65"), TEXT("\"index\":5"));
    TestFalse(TEXT("Duplicate frame rejected"), Parse(TimelineFixture(TimelineNode(1), BadOrder), Clip, Error));
    const FString BadKind = Tracks.Replace(TEXT("\"kind\":\"point\""), TEXT("\"kind\":\"bool\""));
    TestFalse(TEXT("Wrong property value type rejected"), Parse(TimelineFixture(TimelineNode(1), BadKind), Clip, Error));
    TestTrue(TEXT("Valid clip again"), Parse(TimelineFixture(TimelineNode(1), TEXT("")), Clip, Error));
    TestFalse(TEXT("Negative elapsed rejected"), Evaluate(Clip, -1, FVector2D::ZeroVector, Sample, Error));
    TestFalse(TEXT("Invalid JSON resets clip"), Parse(TEXT("{}"), Clip, Error));
    TestFalse(TEXT("Failed parse cannot be evaluated"), Evaluate(Clip, 0, FVector2D::ZeroVector, Sample, Error));
    return true;
}
#endif
