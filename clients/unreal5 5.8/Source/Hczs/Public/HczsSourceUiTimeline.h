#pragma once

#include "CoreMinimal.h"

// Pure source-CSB sampling. No world, timers, assets, Slate widgets, or mutable playback state.
namespace HczsSourceUiTimeline
{
struct HCZS_API FAffine2D
{
    double M00 = 1, M01 = 0, M10 = 0, M11 = 1, TX = 0, TY = 0;
    FVector2D TransformPoint(const FVector2D& Point) const;
};

struct HCZS_API FNode
{
    FString Name, ClassName, SpriteId;
    int32 ActionTag = 0, Parent = INDEX_NONE, ZOrder = 0;
    FVector2D Position = FVector2D::ZeroVector, Scale = FVector2D(1, 1);
    FVector2D RotationSkew = FVector2D::ZeroVector, Anchor = FVector2D::ZeroVector;
    FVector2D Size = FVector2D::ZeroVector;
    FLinearColor Color = FLinearColor::White;
    double Alpha = 255;
    bool bVisible = true, bFlipX = false, bFlipY = false;
    TArray<FString> Unsupported;
};

struct HCZS_API FFrame
{
    int32 Index = 0, EasingType = 0;
    bool bTween = true, bHasEasingPoints = false, BoolValue = false;
    TArray<double> Value;
    FString SpriteId;
};

struct HCZS_API FTrack
{
    FString Property;
    int32 NodeIndex = INDEX_NONE;
    bool bSupported = false;
    TArray<FFrame> Frames;
};

struct HCZS_API FClip
{
    double FramesPerSecond = 60, Speed = 1;
    int32 StartFrame = 0, EndFrame = 0;
    // Opt-in upstream compatibility is not evidence that the APK's fork is numerically identical.
    FString EasingPolicy = TEXT("linear-only");
    TArray<FNode> Nodes;
    TArray<FTrack> Tracks;
    TArray<FString> Unsupported, CompatibilityNotes;
    bool bValid = false;
    double DurationSeconds() const;
};

struct HCZS_API FNodeSample
{
    int32 NodeIndex = INDEX_NONE, ActionTag = 0, Parent = INDEX_NONE, ZOrder = 0;
    FString Name, ClassName, SpriteId;
    FVector2D Position = FVector2D::ZeroVector, Scale = FVector2D(1, 1);
    FVector2D RotationSkew = FVector2D::ZeroVector, Anchor = FVector2D::ZeroVector;
    FVector2D Size = FVector2D::ZeroVector;
    FLinearColor Tint = FLinearColor::White;
    bool bVisible = true, bTransformSupported = true;
    // Maps the sprite's top-left-origin, Y-down [0,width] x [0,height] quad to design pixels.
    // Includes sprite flips; children inherit the unflipped node transform instead.
    FAffine2D LocalToDesign;
    TArray<FString> Unsupported;
};

struct HCZS_API FSample
{
    double SourceFrame = 0;
    bool bFinished = false;
    TArray<FNodeSample> Nodes;
    // Cocos-style child traversal: negative local Z, own node, nonnegative local Z;
    // stable source order for equal Z. These are indices into Nodes, not sprite IDs.
    TArray<int32> DrawOrder;
    TArray<FString> Unsupported, CompatibilityNotes;
};

// Schema hczs-source-ui-timeline-v1; parent is a preceding node index or -1.
// Required clip: fps,speed,startFrame,endFrame,nodes,tracks.
// Required node: name,classname,action_tag,parent,position,scale,rotation_skew,
// anchor,size,alpha,color_argb[A,R,G,B],visible,flip_x,flip_y. Optional spriteId,z_order,unsupported.
// Track: property,action_tag,frames. Frame: index,tween,easing_type,kind,value;
// optional easing_points and spriteId (required for FileData). Unknown tracks stay unsupported.
// CColor changes RGB only; Alpha is independent. Before the first key, its value applies.
HCZS_API bool Parse(const FString& Json, FClip& OutClip, FString& OutError);
HCZS_API bool Evaluate(const FClip& Clip, double Seconds, const FVector2D& DesignOrigin,
    FSample& OutSample, FString& OutError);
}
