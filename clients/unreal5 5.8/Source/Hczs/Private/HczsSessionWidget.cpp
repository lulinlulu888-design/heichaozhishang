#include "HczsSessionWidget.h"
#include "HczsGameInstance.h"
#include "HczsSessionTypes.h"
#include "HczsWorldlineWidget.h"
#include "HczsBattlePresentation.h"
#include "HczsCardDeal.h"
#include "HczsUiAudio.h"
#include "HczsSessionContract.h"
#include "Kismet/GameplayStatics.h"
#include "Components/AudioComponent.h"
#include "Sound/SoundWave.h"
#include "Engine/FontFace.h"
#include "Engine/Texture2D.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Rendering/DrawElementTypes.h"
#include "Rendering/SlateRenderer.h"
#include "Textures/SlateShaderResource.h"
#include "Framework/Application/SlateApplication.h"
#include "Framework/Application/SlateUser.h"
#include "Fonts/FontMeasure.h"
#include "Styling/CoreStyle.h"
#include "Input/Reply.h"
#include "InputCoreTypes.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Layout/WidgetPath.h"
#include "Widgets/SWindow.h"
#include "Engine/World.h"
#include "TimerManager.h"
#include "EngineUtils.h"
#include "Engine/GameViewportClient.h"
#include "Engine/SkeletalMesh.h"
#include "Materials/MaterialInterface.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/PlayerController.h"
#include "UnrealClient.h"

namespace
{
const FVector2f DesignSize(1280, 720);
const FLinearColor Ink(0.025f, 0.04f, 0.085f, 0.94f);
const FLinearColor Accent(0.37f, 0.86f, 0.91f, 1);
const FLinearColor Warm(0.97f, 0.78f, 0.48f, 1);
const FLinearColor Muted(0.62f, 0.70f, 0.81f, 1);
const FLinearColor Light(0.95f, 0.97f, 1, 1);

#if !UE_BUILD_SHIPPING
bool IsIsolatedNativeUiTest()
{
    int32 Port = 0;
    return (FParse::Param(FCommandLine::Get(), TEXT("HczsUITest")) || FParse::Param(FCommandLine::Get(), TEXT("HczsMainlineUITest"))) &&
        FParse::Value(FCommandLine::Get(), TEXT("HczsServerPort="), Port) && Port > 0 && Port <= 65535 && Port != 7460;
}
#endif

bool HasRecoveredScene(const FHczsEncounterSummary& Encounter)
{
    const bool bTutorial = Encounter.Id == TEXT("tutorial-5000") && Encounter.DefinitionId.StartsWith(TEXT("tutorial-5000-"))
        && Encounter.PlayerId == TEXT("1") && Encounter.EnemyId == TEXT("991");
    const bool bCityPreview = Encounter.Id == TEXT("city-preview-10405") && Encounter.DefinitionId.StartsWith(TEXT("city-preview-10405-"))
        && Encounter.PlayerId == TEXT("1") && Encounter.EnemyId == TEXT("6605");
    const bool bBoss = Encounter.Id == TEXT("prologue-boss-1703") && Encounter.DefinitionId.StartsWith(TEXT("prologue-boss-1703-"))
        && Encounter.PlayerId == TEXT("party-1-3") && Encounter.EnemyId == TEXT("2013");
    return bTutorial || bCityPreview || bBoss;
}

bool HasRecoveredActors(const FHczsBattleView& Battle)
{
    return (Battle.PlayerId == TEXT("1") && Battle.EnemyId == TEXT("991")) ||
        (Battle.bIsParty && Battle.PlayerId == TEXT("party-1-3") && Battle.EnemyId == TEXT("2013") && Battle.EncounterId == TEXT("prologue-boss-1703")) ||
        (Battle.PlayerId == TEXT("1") && Battle.EnemyId == TEXT("6605") &&
         (Battle.EncounterId == TEXT("city-preview-10405") || Battle.DefinitionId.StartsWith(TEXT("city-preview-10405-"))));
}

FVector2f DesignPoint(const FGeometry& Geometry, const FVector2D& Absolute)
{
    const FVector2f Available(Geometry.GetLocalSize());
    const float Scale = FMath::Min(Available.X / DesignSize.X, Available.Y / DesignSize.Y);
    if (Scale <= 0) return FVector2f(-1, -1);
    return (FVector2f(Geometry.AbsoluteToLocal(Absolute)) - (Available - DesignSize * Scale) * 0.5f) / Scale;
}

bool Contains(const FHczsSessionControl& Control, const FVector2f& Point)
{
    const FVector2f Local = Control.bTransformed ? TransformPoint(Inverse(Control.Transform), Point) : Point;
    return Control.Rect.ContainsPoint(Local);
}

// UsefulFunctions.getSimpleNum with its default table, as CommonText.setSimpleNumTxt uses for
// head txt_hp: int() truncation, then one K/M/B step at or above 100000.
FString SimpleNum(double Value)
{
    struct FStep { double Need, Divide; int32 Digits; const TCHAR* Suffix; };
    static const FStep Steps[] = {{1, 1, 0, TEXT("")}, {1e5, 1e3, 1, TEXT("K")}, {1e6, 1e3, 0, TEXT("K")},
        {1e7, 1e6, 1, TEXT("M")}, {1e8, 1e6, 0, TEXT("M")}, {1e9, 1e6, 0, TEXT("M")}, {1e10, 1e9, 0, TEXT("B")}};
    const double Number = FMath::TruncToDouble(Value);
    const double Absolute = FMath::Abs(Number);
    int32 Index = INDEX_NONE;
    for (int32 Step = 0; Step < UE_ARRAY_COUNT(Steps); ++Step)
        if (Absolute >= Steps[Step].Need) Index = Step;
    if (Index == INDEX_NONE) return FString::Printf(TEXT("%.0f"), Number);
    const FStep& Step = Steps[Index];
    const double Scale = FMath::Pow(10.0, Step.Digits);
    const double Shown = FMath::TruncToDouble(Absolute * Scale / Step.Divide * (Number < 0 ? -1 : 1)) / Scale;
    if (Step.Digits == 0 || FMath::RoundToDouble(Shown * Scale) / Scale == FMath::TruncToDouble(Shown))
        return FString::Printf(TEXT("%.0f%s"), FMath::TruncToDouble(Shown), Step.Suffix);
    return FString::Printf(TEXT("%.*f%s"), Step.Digits, Shown, Step.Suffix);
}

struct FHudGroup
{
    FVector2f Offset = FVector2f::ZeroVector;
    float Opacity = 1;
    bool bFound = false;
};

// A source group node's displacement from its rest pose and cascaded opacity.
FHudGroup SampleHudGroup(const HczsSourceUiTimeline::FSample& Now, const HczsSourceUiTimeline::FSample& Rest, const TCHAR* Name)
{
    FHudGroup Group;
    for (int32 Index = 0; Index < Now.Nodes.Num() && Index < Rest.Nodes.Num(); ++Index)
        if (Now.Nodes[Index].Name == Name)
        {
            const auto& Node = Now.Nodes[Index];
            Group.Offset = FVector2f(Node.LocalToDesign.TransformPoint(FVector2D::ZeroVector)
                - Rest.Nodes[Index].LocalToDesign.TransformPoint(FVector2D::ZeroVector));
            Group.Opacity = Node.bVisible ? Node.Tint.A : 0;
            Group.bFound = true;
            break;
        }
    return Group;
}

class FSessionPainter
{
public:
    FGeometry Canvas;
    FSlateWindowElementList& Elements;
    int32 Layer;
    const TMap<FString, FSlateBrush>& Brushes;
    const TMap<FString, FVector4f>& IconAdjustments;
    TSharedPtr<const FCompositeFont> Font;
    TArray<FString>* PaintedTexts;
    TSet<FString>* PaintedSprites;
    bool bSmoothCard = false;
    float Opacity = 1;
    int32 OutlinePixels = 1;
    float OutlineAlpha = 0.72f;
    FSessionPainter(const FGeometry& InGeometry, FSlateWindowElementList& InElements, int32 InLayer,
        const TMap<FString, FSlateBrush>& InBrushes, const TMap<FString, FVector4f>& InAdjustments,
        TSharedPtr<const FCompositeFont> InFont, TArray<FString>* InPaintedTexts = nullptr,
        TSet<FString>* InPaintedSprites = nullptr)
        : Canvas(InGeometry), Elements(InElements), Layer(InLayer), Brushes(InBrushes),
          IconAdjustments(InAdjustments), Font(InFont), PaintedTexts(InPaintedTexts), PaintedSprites(InPaintedSprites) {}

    void Box(float X, float Y, float W, float H, FLinearColor Color)
    {
        Color.A *= Opacity;
        if (bSmoothCard && SmoothQuad(*FCoreStyle::Get().GetBrush(TEXT("WhiteBrush")), X, Y, W, H, Color)) return;
        FSlateDrawElement::MakeBox(Elements, ++Layer,
            Canvas.MakeChild(FVector2f(W, H), FSlateLayoutTransform(FVector2f(X, Y))).ToPaintGeometry(),
            FCoreStyle::Get().GetBrush(TEXT("WhiteBrush")), ESlateDrawEffect::None, Color);
    }

    bool SmoothQuad(const FSlateBrush& Brush, float X, float Y, float W, float H, FLinearColor Color)
    {
        const auto Resource = FSlateApplication::Get().GetRenderer()->GetResourceHandle(Brush);
        const auto* Proxy = Resource.GetResourceProxy();
        if (!Resource.IsValid() || !Proxy) return false;
        const auto Render = Canvas.GetAccumulatedRenderTransform();
        // Slate UI is composited after scene AA. Cover one physical pixel at
        // each rotated edge, rather than rounding the quad to whole pixels.
        const float Scale = TransformVector(Render, FVector2f(1, 0)).Size();
        const float HalfPixel = 0.5f / FMath::Max(Scale, 0.001f);
        const FVector2f UVStart = Proxy->StartUV;
        const FVector2f UVSize = Proxy->SizeUV;
        TArray<FSlateVertex> Vertices;
        TArray<SlateIndex> Indices{0, 1, 2, 0, 2, 3};
        for (int32 Ring = 0; Ring < 2; ++Ring)
        {
            const float Inset = Ring == 0 ? HalfPixel : -HalfPixel;
            const FVector2f Points[] = {{X + Inset, Y + Inset}, {X + W - Inset, Y + Inset},
                {X + W - Inset, Y + H - Inset}, {X + Inset, Y + H - Inset}};
            FColor VertexColor = Color.ToFColorSRGB();
            if (Ring == 1) VertexColor.A = 0;
            for (const auto& Point : Points)
            {
                const FVector2f Fraction(FMath::Clamp((Point.X - X) / W, 0.0f, 1.0f),
                    FMath::Clamp((Point.Y - Y) / H, 0.0f, 1.0f));
                const FVector2f UV = UVStart + UVSize * Fraction;
                Vertices.Add(FSlateVertex::Make<ESlateVertexRounding::Disabled>(Render, Point,
                    FVector4f(UV.X, UV.Y, 1, 1), FVector2f::ZeroVector, VertexColor));
            }
        }
        for (int32 Edge = 0; Edge < 4; ++Edge)
        {
            const SlateIndex A = Edge, B = (Edge + 1) % 4;
            Indices.Append({A, static_cast<SlateIndex>(A + 4), static_cast<SlateIndex>(B + 4),
                A, static_cast<SlateIndex>(B + 4), B});
        }
        FSlateDrawElement::MakeCustomVerts(Elements, ++Layer, Resource, Vertices, Indices,
            nullptr, 0, 0, ESlateDrawEffect::NoPixelSnapping);
        return true;
    }

    bool Image(const FString& Key, float X, float Y, float W, float H,
        FLinearColor Tint = FLinearColor::White, bool bFlipX = false, bool bSourceBox = false)
    {
        const FSlateBrush* Brush = Brushes.Find(Key);
        if (!Brush) return false;
        Tint.A *= Opacity;
        if (PaintedSprites) PaintedSprites->Add(Key);
        if (!bSourceBox)
            if (const FVector4f* Adjust = IconAdjustments.Find(Key))
            {
                X += W * Adjust->Z;
                Y += H * Adjust->W;
                W *= Adjust->X;
                H *= Adjust->Y;
            }
        if (bSmoothCard && SmoothQuad(*Brush, X, Y, W, H, Tint)) return true;
        const FGeometry Geometry = bFlipX
            ? Canvas.MakeChild(FVector2f(W, H), FSlateLayoutTransform(FVector2f(X, Y)),
                FSlateRenderTransform(FScale2D(-1.f, 1.f)), FVector2f(0.5f, 0.5f))
            : Canvas.MakeChild(FVector2f(W, H), FSlateLayoutTransform(FVector2f(X, Y)));
        FSlateDrawElement::MakeBox(Elements, ++Layer, Geometry.ToPaintGeometry(), Brush, ESlateDrawEffect::None, Tint);
        return true;
    }

    void Text(const FString& Text, float X, float Y, float W, float H, float Pixels,
        FLinearColor Color = Light, bool bCenter = false, bool bShadow = true)
    {
        if (Text.IsEmpty()) return;
        if (PaintedTexts) PaintedTexts->Add(Text);
        Color.A *= Opacity;
        FFontOutlineSettings Outline;
        Outline.OutlineSize = bShadow ? OutlinePixels : 0;
        Outline.OutlineColor = FLinearColor(0, 0, 0, OutlineAlpha * Opacity);
        FSlateFontInfo Info = Font ? FSlateFontInfo(Font, Pixels * 72.0f / FontConstants::RenderDPI,
            TEXT("Regular"), Outline) : FCoreStyle::GetDefaultFontStyle(TEXT("Regular"), FMath::RoundToInt(Pixels * 0.75f));
        const FVector2f Measured(FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(Text, Info));
        FVector2f Position(X + (bCenter ? (W - Measured.X) * 0.5f : 0), Y + (H - Measured.Y) * 0.5f);
        FSlateDrawElement::MakeText(Elements, ++Layer,
            Canvas.MakeChild(Measured, FSlateLayoutTransform(Position)).ToPaintGeometry(),
            Text, Info, bSmoothCard ? ESlateDrawEffect::NoPixelSnapping : ESlateDrawEffect::None, Color);
    }

    TArray<FString> WrapLines(const FString& Value, float W, float Pixels) const
    {
        FSlateFontInfo Info = Font ? FSlateFontInfo(Font, Pixels * 72.0f / FontConstants::RenderDPI, TEXT("Regular"))
            : FCoreStyle::GetDefaultFontStyle(TEXT("Regular"), FMath::RoundToInt(Pixels * 0.75f));
        const auto Measure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
        TArray<FString> Lines;
        FString Line;
        for (int32 Index = 0; Index < Value.Len(); ++Index)
        {
            const TCHAR Character = Value[Index];
            const FString Next = Line + FString::Chr(Character);
            if (Character == TEXT('\n') || (!Line.IsEmpty() && Measure->Measure(Next, Info).X > W))
            {
                Lines.Add(Line);
                Line.Reset();
                if (Character != TEXT('\n')) Line.AppendChar(Character);
            }
            else Line = Next;
        }
        if (!Line.IsEmpty()) Lines.Add(Line);
        return Lines;
    }

    void Wrapped(const FString& Value, float X, float Y, float W, float Pixels,
        int32 MaxLines, FLinearColor Color = Light, bool bShadow = true, float LineSpacing = 3)
    {
        const TArray<FString> Lines = WrapLines(Value, W, Pixels);
        for (int32 Index = 0; Index < FMath::Min(MaxLines, Lines.Num()); ++Index)
            Text(Lines[Index], X, Y + Index * (Pixels + LineSpacing), W, Pixels + LineSpacing,
                Pixels, Color, false, bShadow);
    }

    // PlayerHeadArea / MonsterHeadArea rest boxes from tools/audit_head_area_rest.py.
    // Slot is the project node's rest design origin. Boxes are post-flip; bFlipX mirrors pixels in place.
    void Health(const FString& Name, const FString& Portrait, const FHczsScalar& Hp,
        const FHczsScalar& Maximum, const FHczsScalar& Shield, FVector2D Slot, bool bEnemy)
    {
        const auto At = [Slot](double X, double Y) { return FVector2D(Slot.X + X, Slot.Y + Y); };
        const FVector2D Back = At(-77, 0), Front = At(-77, 24), Bar = At(-77, 77);
        const FVector2D PortraitBox = bEnemy ? At(-13, 2) : At(-78.5, -1);
        const FVector2D PortraitSize = bEnemy ? FVector2D(90, 90) : FVector2D(159, 93);
        const FVector2D NameBox = bEnemy ? At(-3, 56) : At(-74, 56);
        const FVector2D Number = At(-27, 76);
        const FVector2D ShieldIcon = bEnemy ? At(54, 86) : At(-82, 86);
        Image(TEXT("head-back"), Back.X, Back.Y, 154, 92, FLinearColor::White, bEnemy, true);
        if (!Portrait.IsEmpty())
            Image(Portrait, PortraitBox.X, PortraitBox.Y, PortraitSize.X, PortraitSize.Y, FLinearColor::White, !bEnemy, true);
        Image(TEXT("head-front"), Front.X, Front.Y, 154, 68, FLinearColor::White, bEnemy, true);
        Text(Name, NameBox.X, NameBox.Y, 77, 22, 18, bEnemy ? Warm : Accent);
        const FString BarKey = bEnemy ? TEXT("monster-hp") : TEXT("player-hp");
        Image(BarKey + TEXT("-bg"), Bar.X, Bar.Y, 154, 18, FLinearColor::White, bEnemy, true);
        const float Ratio = Maximum.Approximate > 0
            ? FMath::Clamp(Hp.Approximate / Maximum.Approximate, 0.0, 1.0) : 0;
        if (Ratio > 0)
        {
            const FVector2f ClipTL = Canvas.LocalToAbsolute(FVector2f(Bar.X, Bar.Y));
            const FVector2f ClipBR = Canvas.LocalToAbsolute(FVector2f(Bar.X + 154 * Ratio, Bar.Y + 18));
            Elements.PushClip(FSlateClippingZone(FSlateRect(ClipTL.X, ClipTL.Y, ClipBR.X, ClipBR.Y)));
            Image(BarKey, Bar.X, Bar.Y, 154, 18, FLinearColor::White, false, true);
            Elements.PopClip();
        }
        // txt_hp is the short number on the bar. The "/ max" string belongs to debug_hp and stays off.
        Text(SimpleNum(Hp.Approximate), Number.X, Number.Y, 54, 20, 16, Light, true);
        // PlayerHeadArea.setShieldPercent fills the track when shield > 0 and there is no
        // prognosis. MonsterBaseArea.refreshShield uses ceil(shield * 100 / maxHp). Direction 0
        // grows from the left. The preview bar and break icon stay off without those states.
        // Widget flipX negates scaleX around the anchor: the monster shield_bg anchored (1, .5)
        // at x -78 spans -78..66, and its LoadingBar children fill from the right.
        const FVector2D ShieldBar = bEnemy ? At(-78, 92) : At(-62, 92);
        const FVector2D ShieldSize = bEnemy ? FVector2D(144, 16) : FVector2D(140, 16);
        Image(TEXT("shield-bg"), ShieldBar.X, ShieldBar.Y, ShieldSize.X, ShieldSize.Y, FLinearColor::White, bEnemy, true);
        float ShieldFill = 0;
        if (bEnemy)
        {
            const double Denominator = Maximum.Approximate > 0 ? Maximum.Approximate : 1;
            ShieldFill = FMath::Max(0.0, FMath::CeilToFloat(Shield.Approximate * 100.0 / Denominator) / 100.0);
        }
        else if (Shield.Approximate > 0)
            ShieldFill = 1;
        if (ShieldFill > 0)
        {
            const double FillStart = bEnemy ? ShieldBar.X + ShieldSize.X * (1 - ShieldFill) : ShieldBar.X;
            const FVector2f ClipTL = Canvas.LocalToAbsolute(FVector2f(FillStart, ShieldBar.Y));
            const FVector2f ClipBR = Canvas.LocalToAbsolute(FVector2f(FillStart + ShieldSize.X * ShieldFill, ShieldBar.Y + ShieldSize.Y));
            Elements.PushClip(FSlateClippingZone(FSlateRect(ClipTL.X, ClipTL.Y, ClipBR.X, ClipBR.Y)));
            Image(TEXT("shield-fill"), ShieldBar.X, ShieldBar.Y, ShieldSize.X, ShieldSize.Y, FLinearColor::White, bEnemy, true);
            Elements.PopClip();
        }
        if (Shield.Approximate > 0)
            Image(TEXT("shield-icon"), ShieldIcon.X, ShieldIcon.Y, 32, 32, FLinearColor::White, false, true);
    }
};
}

void UHczsSessionWidget::NativeConstruct()
{
    Super::NativeConstruct();
    SetIsFocusable(true);
    UiAudioRandom.Initialize(int32(FPlatformTime::Cycles()));
    Presentation = LoadObject<UHczsBattlePresentationAsset>(nullptr,
        TEXT("/Game/Recovered/Battle/UI/BattlePresentation.BattlePresentation"));
    EntrancePresentation = LoadObject<UHczsBattlePresentationAsset>(nullptr,
        TEXT("/Game/Recovered/Battle/Entrance/UI/BattleEntrancePresentation.BattleEntrancePresentation"));
    if (EntrancePresentation)
    {
        TSharedPtr<FJsonObject> Root;
        if (FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(EntrancePresentation->LayoutJson), Root) && Root &&
            Root->GetStringField(TEXT("schema")) == TEXT("hczs-source-battle-opening-v1"))
        {
            EliteOpeningJson = Root->GetObjectField(TEXT("clips"))->GetObjectField(TEXT("elite"));
            FString Json, Error;
            FJsonSerializer::Serialize(EliteOpeningJson.ToSharedRef(), TJsonWriterFactory<>::Create(&Json));
            if (!HczsSourceUiTimeline::Parse(Json, EliteOpening, Error))
                UE_LOG(LogTemp, Error, TEXT("HCZS original opening timeline rejected: %s"), *Error);
            const auto LoadHudClip = [&Root](const TCHAR* Name, HczsSourceUiTimeline::FClip& Clip, HczsSourceUiTimeline::FSample& Rest)
            {
                const TSharedPtr<FJsonObject>* Object = nullptr;
                FString ClipJson, ClipError;
                if (!Root->GetObjectField(TEXT("clips"))->TryGetObjectField(Name, Object)) { UE_LOG(LogTemp, Error, TEXT("HCZS HUD In clip missing: %s"), Name); return; }
                FJsonSerializer::Serialize(Object->ToSharedRef(), TJsonWriterFactory<>::Create(&ClipJson));
                if (!HczsSourceUiTimeline::Parse(ClipJson, Clip, ClipError) ||
                    !HczsSourceUiTimeline::Evaluate(Clip, Clip.DurationSeconds(), FVector2D(0, 720), Rest, ClipError))
                {
                    Clip.bValid = false;
                    UE_LOG(LogTemp, Error, TEXT("HCZS HUD In clip %s rejected: %s"), Name, *ClipError);
                }
            };
            LoadHudClip(TEXT("hud"), HudIn, HudInRest);
            LoadHudClip(TEXT("ownCardAreaIn"), OwnCardIn, OwnCardInRest);
            for (const auto& Pair : EntrancePresentation->Sprites)
            {
                if (!Pair.Value) continue;
                FSlateBrush Brush; Brush.SetResourceObject(Pair.Value);
                Brush.DrawAs = ESlateBrushDrawType::Image;
                Brush.ImageSize = FVector2f(Pair.Value->GetSizeX(), Pair.Value->GetSizeY());
                Brushes.Add(TEXT("entrance-") + Pair.Key, Brush);
            }
        }
    }
    if (Presentation)
    {
        for (const auto& Pair : Presentation->Sprites)
        {
            if (!Pair.Value) continue;
            FSlateBrush Brush;
            Brush.SetResourceObject(Pair.Value);
            Brush.DrawAs = ESlateBrushDrawType::Image;
            Brush.ImageSize = FVector2f(Pair.Value->GetSizeX(), Pair.Value->GetSizeY());
            Brushes.Add(Pair.Key, Brush);
        }
        if (FParse::Param(FCommandLine::Get(), TEXT("HczsHDIcons")))
        {
            IconVariant = LoadObject<UHczsBattlePresentationAsset>(nullptr,
                TEXT("/Game/Recovered/Battle/UI/AI/BattlePresentationHD.BattlePresentationHD"));
            if (IconVariant)
            {
                const TSet<FString> IconKeys{TEXT("energy-icon"), TEXT("end-icon-normal"),
                    TEXT("end-icon-active"), TEXT("shield-icon"), TEXT("deck-icon"), TEXT("menu-icon"), TEXT("card-cost")};
                for (const auto& Pair : IconVariant->Sprites)
                {
                    if (!IconKeys.Contains(Pair.Key) || !Pair.Value) continue;
                    FSlateBrush Brush;
                    Brush.SetResourceObject(Pair.Value);
                    Brush.DrawAs = ESlateBrushDrawType::Image;
                    Brush.ImageSize = FVector2f(Pair.Value->GetSizeX(), Pair.Value->GetSizeY());
                    Brushes.Add(Pair.Key, Brush);
                }
                TSharedPtr<FJsonObject> VariantLayout;
                if (FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(IconVariant->LayoutJson), VariantLayout)
                    && VariantLayout)
                {
                    const TSharedPtr<FJsonObject>* Alignment = nullptr;
                    if (VariantLayout->TryGetObjectField(TEXT("iconAlignment"), Alignment))
                    {
                        for (const auto& Pair : (*Alignment)->Values)
                        {
                            const FString Key(*Pair.Key);
                            const TArray<TSharedPtr<FJsonValue>>* Numbers = nullptr;
                            if (!IconKeys.Contains(Key) || !Pair.Value->TryGetArray(Numbers) || Numbers->Num() != 4) continue;
                            TArray<double> V;
                            for (const auto& N : *Numbers)
                            {
                                double Number = 0;
                                if (!N->TryGetNumber(Number) || !FMath::IsFinite(Number)) break;
                                V.Add(Number);
                            }
                            if (V.Num() == 4 && V[0] > 0 && V[0] <= 8 && V[1] > 0 && V[1] <= 8
                                && FMath::Abs(V[2]) <= 2 && FMath::Abs(V[3]) <= 2)
                                IconDrawAdjustments.Add(Key, FVector4f(V[0], V[1], V[2], V[3]));
                        }
                    }
                }
                // Never substitute an entire generated canvas without a reviewed
                // alignment record. This also preserves source-size hitboxes.
                for (const FString& Key : IconKeys)
                {
                    if (IconDrawAdjustments.Contains(Key)) continue;
                    UTexture2D* Original = Presentation->Sprites.FindRef(Key);
                    if (!Original) continue;
                    FSlateBrush Brush;
                    Brush.SetResourceObject(Original);
                    Brush.DrawAs = ESlateBrushDrawType::Image;
                    Brush.ImageSize = FVector2f(Original->GetSizeX(), Original->GetSizeY());
                    Brushes.Add(Key, Brush);
                }
            }
        }
        if (Presentation->ChineseFont)
        {
            TSharedPtr<FCompositeFont> Composite = MakeShared<FCompositeFont>();
            FTypefaceEntry Entry;
            Entry.Name = TEXT("Regular");
            Entry.Font = FFontData(Presentation->ChineseFont);
            Composite->DefaultTypeface.Fonts.Add(Entry);
            CompositeFont = Composite;
        }
        TitleFontFace = LoadObject<UFontFace>(nullptr,
            TEXT("/Game/Recovered/Hall/UI/Fonts/FF_fe2867052dcb457b4a2c8a56.FF_fe2867052dcb457b4a2c8a56"));
        if (TitleFontFace)
        {
            TSharedPtr<FCompositeFont> Composite = MakeShared<FCompositeFont>();
            FTypefaceEntry Entry;
            Entry.Name = TEXT("Regular");
            Entry.Font = FFontData(TitleFontFace);
            Composite->DefaultTypeface.Fonts.Add(Entry);
            TitleFont = Composite;
        }
        TSharedPtr<FJsonObject> Layout;
        if (FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Presentation->LayoutJson), Layout) && Layout)
        {
            const TSharedPtr<FJsonObject>* Placements = nullptr;
            if (Layout->TryGetObjectField(TEXT("cardPlacements"), Placements))
            {
                for (const auto& Pair : (*Placements)->Values)
                {
                    const int32 Count = FCString::Atoi(*Pair.Key);
                    if (Count < 1 || Count > 10 || Pair.Value->AsArray().Num() != Count) continue;
                    TArray<FVector3f> Positions;
                    for (const auto& Value : Pair.Value->AsArray())
                    {
                        const auto Object = Value->AsObject();
                        double X = 0, Y = 0, Rotation = 0;
                        if (!Object || !Object->TryGetNumberField(TEXT("x"), X)
                            || !Object->TryGetNumberField(TEXT("y"), Y)
                            || !Object->TryGetNumberField(TEXT("rotation"), Rotation)
                            || !FMath::IsFinite(X) || !FMath::IsFinite(Y) || !FMath::IsFinite(Rotation)) break;
                        Positions.Add(FVector3f(X, Y, Rotation));
                    }
                    if (Positions.Num() == Count) CardPlacements.Add(Count, MoveTemp(Positions));
                }
            }
            const TSharedPtr<FJsonObject>* Faces = nullptr;
            if (Layout->TryGetObjectField(TEXT("cardFaces"), Faces))
                for (const auto& Pair : (*Faces)->Values)
                {
                    const auto Object = Pair.Value->AsObject();
                    FHczsCardFace Face; double Type = -1;
                    if (!Object || !Object->TryGetNumberField(TEXT("rarity"), Face.Rarity) ||
                        !Object->TryGetNumberField(TEXT("cardType"), Type) || (Type != 0 && Type != 7) ||
                        !Object->TryGetStringField(TEXT("description"), Face.Description)) continue;
                    FString Value;
                    if (Type == 7 && (!Object->TryGetStringField(TEXT("frame"), Face.Frame) ||
                        !Object->TryGetStringField(TEXT("descriptionValue"), Value) || Value != TEXT("total-damage"))) continue;
                    Face.bTotalDamage = Type == 7;
                    CardFaces.Add(FString(*Pair.Key), MoveTemp(Face));
                }
        }
    }
    else UE_LOG(LogTemp, Error, TEXT("HCZS: battle UI DataAsset missing; run verified battle UI importer"));
    // Independent original arrow assets; never replace the raw/HD presentation DataAsset.
    for (const auto& Pair : TMap<FString, FString>{
        {TEXT("target-arrow-head"), TEXT("/Game/Recovered/Battle/UI/Targeting/T_ArrowHead.T_ArrowHead")},
        {TEXT("target-arrow-ribbon"), TEXT("/Game/Recovered/Battle/UI/Targeting/M_SourceArrowRibbon.M_SourceArrowRibbon")}})
    {
        UObject* Resource = Pair.Key == TEXT("target-arrow-head")
            ? static_cast<UObject*>(LoadObject<UTexture2D>(nullptr, *Pair.Value))
            : static_cast<UObject*>(LoadObject<UMaterialInterface>(nullptr, *Pair.Value));
        if (!Resource) continue;
        TargetingResources.Add(Resource);
        FSlateBrush Brush;
        Brush.SetResourceObject(Resource); Brush.DrawAs = ESlateBrushDrawType::Image;
        Brush.ImageSize = Pair.Key == TEXT("target-arrow-head") ? FVector2f(256, 128) : DesignSize;
        Brushes.Add(Pair.Key, Brush);
    }
    Session = Cast<UHczsGameInstance>(GetGameInstance());
    if (Session)
        StateChangedHandle = Session->OnStateChangedNative.AddUObject(this, &UHczsSessionWidget::SessionChanged);
    if (UWorld* World = GetWorld())
        World->GetTimerManager().SetTimer(DealTimer, this, &UHczsSessionWidget::UpdateDealCues, 0.01f, true);
    UpdateVisibility();
    UE_LOG(LogTemp, Display, TEXT("HCZS: session UI ready; %d original sprites, sourceFont=%s, %d card arcs"),
        Brushes.Num(), CompositeFont.IsValid() ? TEXT("yes") : TEXT("missing"), CardPlacements.Num());
}

void UHczsSessionWidget::NativeDestruct()
{
    CancelCardGesture(TEXT("widget-destroyed"));
    CloseWorldlineSelection();
    if (UWorld* World = GetWorld()) World->GetTimerManager().ClearTimer(DealTimer);
    if (Session && StateChangedHandle.IsValid()) Session->OnStateChangedNative.Remove(StateChangedHandle);
    Super::NativeDestruct();
}

double UHczsSessionWidget::RoundDealElapsed() const
{
    return RoundDeal.StartSeconds >= 0 && GetWorld() ? GetWorld()->GetTimeSeconds() - RoundDeal.StartSeconds : -1.0;
}

void UHczsSessionWidget::FinishRoundDeal(const FString& Reason)
{
    if (!IsRoundDealActive()) return;
    LastRoundDealOutcome = Reason;
    UE_LOG(LogTemp, Display, TEXT("HCZS round-start deal ended: actionIndex=%lld cards=%d reason=%s"),
        RoundDeal.ActionIndex, RoundDeal.Instances.Num(), *Reason);
    RoundDeal = FRoundDeal();
    InvalidateLayoutAndVolatility();
}

void UHczsSessionWidget::PlayUiCue(HczsUiAudio::ECue Cue, const FString& Reason)
{
    using namespace HczsUiAudio;
    const FCue& Def = Get(Cue);
    const int32 Variant = PickVariant(Cue, Cue == ECue::DrawCard ? LastDrawCueVariant : -1, UiAudioRandom);
    if (Cue == ECue::DrawCard) LastDrawCueVariant = Variant;
    const uint32 Source = Def.Sources[Variant];
    USoundWave* Sound = LoadObject<USoundWave>(nullptr, *SoundPath(Source));
    UAudioComponent* Component = Sound ? UGameplayStatics::SpawnSound2D(this, Sound, VolumeMultiplier(Cue)) : nullptr;
    auto Row = MakeShared<FJsonObject>();
    Row->SetStringField(TEXT("cue"), Def.Key);
    Row->SetStringField(TEXT("event"), Def.Event);
    Row->SetNumberField(TEXT("source"), Source);
    Row->SetNumberField(TEXT("volumeDb"), Def.VolumeDb);
    Row->SetStringField(TEXT("reason"), Reason);
    Row->SetBoolField(TEXT("loaded"), Sound != nullptr);
    Row->SetBoolField(TEXT("playing"), Component && Component->IsPlaying());
    Row->SetNumberField(TEXT("worldSeconds"), GetWorld() ? GetWorld()->GetTimeSeconds() : -1.0);
    UiAudioLog.Add(MakeShared<FJsonValueObject>(Row));
    if (UiAudioLog.Num() > 32) UiAudioLog.RemoveAt(0, UiAudioLog.Num() - 32);
    if (!Sound) UE_LOG(LogTemp, Warning, TEXT("HCZS UI cue %s source %u is not imported"), Def.Key, Source);
}

void UHczsSessionWidget::UpdateDealCues()
{
    using HczsUiAudio::ECue;
    UWorld* World = GetWorld();
    if (!Session || !World || !bBattleScene || Session->Phase != EHczsSessionPhase::Battle || !Session->CurrentBattle.bIsValid)
    {
        FinishRoundDeal(TEXT("left-battle"));
        return;
    }
    const FHczsBattleView& Battle = Session->CurrentBattle;
    const int32 HandCount = Battle.Hand.Num();
    const double Opening = FreshOpeningSeconds();
    if (Opening >= 3.5 && OpeningCueBattle != Battle.Id && HandCount > 0 && HandCount <= 8)
    {
        OpeningCueBattle = Battle.Id;
        bOpeningLandCuePlayed = Opening >= 3.5 + HczsCardDeal::DispatchSeconds(HandCount);
        if (!bOpeningLandCuePlayed) PlayUiCue(ECue::DrawCard, TEXT("opening-first-draw"));
    }
    if (OpeningCueBattle == Battle.Id && !bOpeningLandCuePlayed && Opening >= 3.5 + HczsCardDeal::DispatchSeconds(HandCount))
    {
        bOpeningLandCuePlayed = true;
        PlayUiCue(ECue::FapaiB, TEXT("opening-last-dispatch-end"));
    }

    const FHczsBattleVisualReceipt& Receipt = Session->LastVisualReceipt;
    const FString ReceiptKey = FString::Printf(TEXT("%s:%lld"), *Receipt.BattleId, Receipt.ActionIndex);
    if (Receipt.bValid && HandledDealReceipt != ReceiptKey && HczsSessionContract::CanPublishVisualReceipt(Battle, Receipt))
    {
        HandledDealReceipt = ReceiptKey;
        FRoundDeal Next;
        bool bTurnStarted = false;
        for (const FHczsBattleVisualEvent& Event : Receipt.Events)
        {
            if (Event.Type == TEXT("TurnStarted") && Event.Round >= 2) { bTurnStarted = true; Next.Round = Event.Round; Next.Instances.Reset(); }
            else if (bTurnStarted && Event.Type == TEXT("CardDrawn")
                && Battle.Hand.ContainsByPredicate([&Event](const FHczsHandCard& C) { return C.InstanceId == Event.InstanceId; }))
                Next.Instances.AddUnique(Event.InstanceId);
        }
        if (bTurnStarted && !Next.Instances.IsEmpty() && Next.Instances.Num() <= 8 && Battle.Status == TEXT("player-turn"))
        {
            FinishRoundDeal(TEXT("superseded"));
            Next.BattleId = Battle.Id; Next.ActionIndex = Receipt.ActionIndex;
            RoundDeal = MoveTemp(Next);
            LastRoundDealOutcome = TEXT("armed");
            CancelCardGesture(TEXT("round-start-deal"));
            InvalidateLayoutAndVolatility();
        }
    }
    if (!IsRoundDealActive()) return;
    if (RoundDeal.BattleId != Battle.Id || RoundDeal.ActionIndex != Battle.ActionIndex)
    { FinishRoundDeal(TEXT("authority-advanced")); return; }
    if (RoundDeal.StartSeconds < 0)
    {
        if (bPresentationBusy || Session->bRequestInFlight) return;
        RoundDeal.StartSeconds = World->GetTimeSeconds();
        LastRoundDealOutcome = TEXT("dispatching");
        UE_LOG(LogTemp, Display, TEXT("HCZS round-start deal started: round=%d actionIndex=%lld cards=%d"),
            RoundDeal.Round, RoundDeal.ActionIndex, RoundDeal.Instances.Num());
        PlayUiCue(ECue::DrawCard, TEXT("round-start-draw"));
        InvalidateLayoutAndVolatility();
    }
    if (RoundDealElapsed() >= HczsCardDeal::DispatchSeconds(RoundDeal.Instances.Num()))
    {
        PlayUiCue(ECue::FapaiB, TEXT("round-last-dispatch-end"));
        FinishRoundDeal(TEXT("completed"));
    }
    if (IsRoundDealActive()) InvalidateLayoutAndVolatility();
}

void UHczsSessionWidget::OpenProfileSelection()
{
    if (!Session || Session->bRequestInFlight || Session->bHasPendingIntent) return;
    CloseWorldlineSelection();
    bProfilePanel = true;
    bEncounterPanel = false;
    bConfirmNewProfile = false;
    ProfilePage = 0;
    UpdateVisibility();
    SetKeyboardFocus();
}

void UHczsSessionWidget::OpenWorldlineSelection()
{
    if (!Session || Session->bRequestInFlight || Session->bHasPendingIntent || bBattleScene
        || Session->Phase != EHczsSessionPhase::Hall) return;
    if (Session->SelectedProfileId.IsEmpty()) { OpenProfileSelection(); return; }
    bProfilePanel = false;
    bEncounterPanel = false;
    bConfirmNewProfile = false;
    if (!WorldlineWidget)
    {
        WorldlineWidget = CreateWidget<UHczsWorldlineWidget>(GetOwningPlayer());
        if (!WorldlineWidget) return;
        WorldlineWidget->OnBackRequested.AddUObject(this, &UHczsSessionWidget::CloseWorldlineSelection);
        WorldlineWidget->OnLocalBattlePreviewRequested.AddUObject(this, &UHczsSessionWidget::OpenLocalPreviewFromWorldline);
        WorldlineWidget->OnPrologueDungeonRequested.AddUObject(this, &UHczsSessionWidget::EnterPrologueDungeon);
    }
    if (!WorldlineWidget->IsInViewport()) WorldlineWidget->AddToViewport(65);
    WorldlineWidget->SetSourceInspection(false);
    WorldlineWidget->SetVisibility(ESlateVisibility::Visible);
    WorldlineWidget->SetKeyboardFocus();
    UpdateVisibility();
}

void UHczsSessionWidget::ShowWorldlineSourceInspection()
{
#if !UE_BUILD_SHIPPING
    if (bBattleScene || !FParse::Param(FCommandLine::Get(), TEXT("HczsWorldlineInspect"))) return;
    if (!WorldlineWidget)
    {
        WorldlineWidget = CreateWidget<UHczsWorldlineWidget>(GetOwningPlayer());
        if (!WorldlineWidget) return;
        WorldlineWidget->OnBackRequested.AddUObject(this, &UHczsSessionWidget::CloseWorldlineSelection);
        WorldlineWidget->OnLocalBattlePreviewRequested.AddUObject(this, &UHczsSessionWidget::OpenLocalPreviewFromWorldline);
        WorldlineWidget->OnPrologueDungeonRequested.AddUObject(this, &UHczsSessionWidget::EnterPrologueDungeon);
    }
    bWorldlineInspection = true;
    WorldlineWidget->SetSourceInspection(true);
    if (!WorldlineWidget->IsInViewport()) WorldlineWidget->AddToViewport(65);
    WorldlineWidget->SetVisibility(ESlateVisibility::Visible);
    WorldlineWidget->SetKeyboardFocus();
    UpdateVisibility();
#endif
}

void UHczsSessionWidget::CloseWorldlineSelection()
{
    if (WorldlineWidget && WorldlineWidget->IsInViewport()) WorldlineWidget->RemoveFromParent();
    bWorldlineInspection = false;
    UpdateVisibility();
}

void UHczsSessionWidget::OpenLocalPreviewFromWorldline()
{
    CloseWorldlineSelection();
    OpenEncounterSelection();
}

void UHczsSessionWidget::EnterPrologueDungeon()
{
    CloseWorldlineSelection();
    if (Session) Session->EnterMainlineDungeon();
}

FString UHczsSessionWidget::DevelopmentDescribeWorldlineUI() const
{
#if UE_BUILD_SHIPPING
    return TEXT("{}");
#else
    if ((!FParse::Param(FCommandLine::Get(), TEXT("HczsWorldlineInspect"))
            && !IsIsolatedNativeUiTest())
        || !WorldlineWidget || !WorldlineWidget->IsInViewport()) return TEXT("{}");
    return WorldlineWidget->DevelopmentDescribeUI();
#endif
}

void UHczsSessionWidget::OpenEncounterSelection()
{
    if (!Session || Session->bRequestInFlight || Session->bHasPendingIntent) return;
    if (Session->SelectedProfileId.IsEmpty()) { OpenProfileSelection(); return; }
    CloseWorldlineSelection();
    bProfilePanel = false;
    bEncounterPanel = true;
    BattlePage = 0;
    UpdateVisibility();
    SetKeyboardFocus();
    Session->RefreshBattles();
}

void UHczsSessionWidget::CloseSelection()
{
    if (!Session || Session->bRequestInFlight || Session->bHasPendingIntent
        || Session->SelectedProfileId.IsEmpty()) return;
    bProfilePanel = false;
    bEncounterPanel = false;
    bConfirmNewProfile = false;
    CloseWorldlineSelection();
    UpdateVisibility();
}

void UHczsSessionWidget::SetBattleScene(bool bInBattleScene)
{
    CancelCardGesture(TEXT("scene-changed"));
    bBattleScene = bInBattleScene;
    if (bBattleScene) CloseWorldlineSelection();
    UpdateVisibility();
    InvalidateLayoutAndVolatility();
}

void UHczsSessionWidget::SetSceneProblem(const FString& Reason)
{
    if (SceneProblem == Reason) return;
    SceneProblem = Reason;
    if (!Reason.IsEmpty()) CancelCardGesture(TEXT("scene-unavailable"));
    UpdateVisibility();
    InvalidateLayoutAndVolatility();
}

void UHczsSessionWidget::SetPresentationBusy(bool bBusy)
{
    if (bPresentationBusy == bBusy) return;
    bPresentationBusy = bBusy;
    if (bBusy) CancelCardGesture(TEXT("presentation-busy"));
    InvalidateLayoutAndVolatility();
}

void UHczsSessionWidget::SessionChanged()
{
    if (!Session) return;
    CancelCardGesture(TEXT("state-refreshed"));
    SelectedCardInstance.Reset(); bCardDetailOpen = false;
    if (bChallengeAfterScenario && !Session->bRequestInFlight)
    {
        if (!Session->ErrorCode.IsEmpty() || Session->SelectedEncounterId != RequestedChallengeEncounter)
        {
            bChallengeAfterScenario = false;
            RequestedChallengeEncounter.Reset();
        }
        else if (Session->bEncounterScenarioReady)
        {
            bChallengeAfterScenario = false;
            RequestedChallengeEncounter.Reset();
            Session->CreateSelectedBattle();
        }
    }
    if (Session->Phase == EHczsSessionPhase::Battle)
    {
        CloseWorldlineSelection();
        bProfilePanel = false;
        bEncounterPanel = false;
    }
    else if (Session->Phase == EHczsSessionPhase::Hall && bProfilePanel && !Session->SelectedProfileId.IsEmpty())
        bProfilePanel = false;
    HoveredCard.Reset();
    UpdateVisibility();
    InvalidateLayoutAndVolatility();
}

void UHczsSessionWidget::UpdateVisibility()
{
    if (bWorldlineInspection) { SetVisibility(ESlateVisibility::Collapsed); return; }
    const bool bVisible = !Session || bProfilePanel || bEncounterPanel
        || Session->Phase != EHczsSessionPhase::Hall || Session->bHasPendingIntent || bBattleScene;
    SetVisibility(bVisible ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
}

double UHczsSessionWidget::FreshOpeningSeconds() const
{
    if (!Session || !GetWorld() || Session->Phase != EHczsSessionPhase::Battle || !bBattleScene ||
        Session->CurrentBattle.EncounterId != TEXT("tutorial-5000") || Session->CurrentBattle.EnemyId != TEXT("991")) return -1;
    for (TActorIterator<AHczsBattlePresentation> It(GetWorld()); It; ++It)
        return It->GetFreshOpeningSeconds(Session->CurrentBattle.Id);
    return -1;
}

int32 UHczsSessionWidget::PaintFreshOpening(const FGeometry& Canvas, FSlateWindowElementList& Elements,
    int32 Layer, double Seconds) const
{
    // Source 6601: popup at +1s; 991 difficulty_type=1 selects elite / In.
    // Local adapter anchors BattleBeginAction to first fresh scene tick. This
    // does not claim recovery of the original multi-action scheduler.
    if (Seconds < 1 || Seconds >= 3 || !EliteOpening.bValid || !EliteOpeningJson) return Layer;
    HczsSourceUiTimeline::FSample Sample; FString Error;
    if (!HczsSourceUiTimeline::Evaluate(EliteOpening, Seconds - 1, FVector2D(640, 360), Sample, Error)) return Layer;
    const auto& Metadata = EliteOpeningJson->GetArrayField(TEXT("nodes"));
    for (int32 Index : Sample.DrawOrder)
    {
        const auto& Node = Sample.Nodes[Index];
        if (!Node.bVisible || !Node.bTransformSupported || Node.Tint.A <= 0 || Node.Size.X <= 0 || Node.Size.Y <= 0) continue;
        const auto Json = Metadata[Index]->AsObject();
        bool bUnrendered = false;
        for (const auto& Limitation : EliteOpening.Nodes[Index].Unsupported)
            if (Limitation == TEXT("source-custom-shader-not-rendered") || Limitation == TEXT("source-additive-blend-not-rendered")) bUnrendered = true;
        if (bUnrendered) continue; // Never draw a shader texture as an opaque rectangle.
        const auto& M = Node.LocalToDesign;
        const FMatrix2x2 Matrix(static_cast<float>(M.M00), static_cast<float>(M.M10),
            static_cast<float>(M.M01), static_cast<float>(M.M11));
        const FGeometry Child = Canvas.MakeChild(FVector2f(Node.Size), FSlateLayoutTransform(),
            FSlateRenderTransform(Matrix, FVector2f(M.TX, M.TY)), FVector2f::ZeroVector);
        FSessionPainter P(Child, Elements, Layer, Brushes, IconDrawAdjustments, CompositeFont,
            &LastPaintedTexts, &LastPaintedSprites);
        if (!Node.SpriteId.IsEmpty()) P.Image(TEXT("entrance-") + Node.SpriteId, 0, 0, Node.Size.X, Node.Size.Y, Node.Tint);
        else if (Node.ClassName == TEXT("Text"))
        {
            FString Text;
            if (Json->TryGetStringField(TEXT("text"), Text))
                P.Text(Text, 0, 0, Node.Size.X, Node.Size.Y, Json->GetIntegerField(TEXT("font_size")), Node.Tint, true, false);
        }
        if (P.Layer > Layer) LastOpeningNodes.Add(Node.Name);
        Layer = P.Layer;
    }
    return Layer;
}

int32 UHczsSessionWidget::NativePaint(const FPaintArgs& Args, const FGeometry& Geometry,
    const FSlateRect& CullingRect, FSlateWindowElementList& Elements, int32 LayerId,
    const FWidgetStyle& Style, bool bParentEnabled) const
{
    const int32 InitialLayer = Super::NativePaint(Args, Geometry, CullingRect, Elements, LayerId, Style, bParentEnabled);
    Controls.Reset();
    LastPaintGeometry = Geometry;
    ++LastPaintSerial;
    LastPaintedTexts.Reset();
    LastOpeningNodes.Reset();
    LastDealtCards.Reset();
    LastHudIn.Reset();
    LastOpeningSeconds = FreshOpeningSeconds();
    bLastPaintedDragCue = false;
    LastPaintedSprites.Reset();
    LastPaintedMap = GetWorld() ? GetWorld()->GetMapName() : FString();
    const FVector2f Available(Geometry.GetLocalSize());
    const float Scale = FMath::Min(Available.X / DesignSize.X, Available.Y / DesignSize.Y);
    if (Scale <= 0) return InitialLayer;
    const FGeometry Canvas = Geometry.MakeChild(DesignSize,
        FSlateLayoutTransform(Scale, (Available - DesignSize * Scale) * 0.5f));
    FSessionPainter P(Canvas, Elements, InitialLayer, Brushes, IconDrawAdjustments, CompositeFont,
        &LastPaintedTexts, &LastPaintedSprites);
    const bool bBusy = !Session || Session->bRequestInFlight || Session->bHasPendingIntent || bPresentationBusy || IsRoundDealActive();
    auto Button = [&](const FString& Action, const FString& Value, const FString& Label,
        float X, float Y, float W, float H, bool Enabled = true, bool Primary = false)
    {
        const bool Active = Enabled && !bBusy;
        P.Box(X, Y, W, H, Active ? (Primary ? FLinearColor(0.045f, 0.34f, 0.39f, 0.96f)
            : FLinearColor(0.12f, 0.17f, 0.25f, 0.96f)) : FLinearColor(0.08f, 0.10f, 0.14f, 0.84f));
        P.Box(X, Y + H - 2, W, 2, Active ? (Primary ? Accent : Muted) : FLinearColor(0.2f, 0.25f, 0.3f, 0.6f));
        P.Text(Label, X, Y, W, H, 17, Active ? Light : Muted, true);
        FHczsSessionControl Control;
        Control.Action = Action;
        Control.Value = Value;
        Control.Rect = FSlateRect(X, Y, X + W, Y + H);
        Control.bEnabled = Active;
        Controls.Add(Control);
    };
    if (!Session)
    {
        P.Box(0, 0, 1280, 720, Ink);
        P.Text(TEXT("无法加载本地会话"), 240, 320, 800, 50, 26, Light, true);
        return P.Layer;
    }
    if (Session->Phase == EHczsSessionPhase::Battle && (!SceneProblem.IsEmpty()
        || (Session->CurrentBattle.bIsValid && !HasRecoveredActors(Session->CurrentBattle))))
    {
        P.Box(0, 0, 1280, 720, FLinearColor(0.015f, 0.02f, 0.04f, 0.91f));
        P.Text(TEXT("战斗场景尚未恢复"), 290, 213, 700, 57, 31, Warm, true);
        const FString Reason = SceneProblem.IsEmpty()
            ? TEXT("这场战斗所需角色或敌方资源尚未接入。存档已保留，可返回大厅选择序章首战。") : SceneProblem;
        P.Wrapped(Reason, 325, 290, 630, 20, 4, Light);
        if (Session->CurrentBattle.bIsValid)
            P.Text(FString::Printf(TEXT("%s  ·  第 %d 回合  ·  记录已保存"),
                *Session->CurrentBattle.EnemyName, Session->CurrentBattle.Round),
                326, 386, 628, 28, 17, Muted, true);
        Button(TEXT("hall"), TEXT(""), TEXT("返回大厅"), 340, 429, 250, 49, true, true);
        Button(TEXT("refresh-battle"), TEXT(""), TEXT("重新读取"), 690, 429, 250, 49);
        return P.Layer;
    }
    const bool bEnteringBattle = Session->Phase == EHczsSessionPhase::Battle && !bBattleScene;
    const bool bReturningHall = Session->Phase == EHczsSessionPhase::Hall && bBattleScene;
    if (bEnteringBattle || bReturningHall)
    {
        P.Box(0, 0, 1280, 720, FLinearColor(0.015f, 0.02f, 0.04f, 0.91f));
        P.Text(bEnteringBattle ? TEXT("正在进入战场…") : TEXT("正在返回大厅…"),
            340, 304, 600, 70, 29, Accent, true);
        return P.Layer;
    }
    const bool bBattle = Session->Phase == EHczsSessionPhase::Battle && Session->CurrentBattle.bIsValid && bBattleScene;
    if (bBattle)
    {
        const FHczsBattleView& Battle = Session->CurrentBattle;
        if (LastOpeningSeconds >= 0 && LastOpeningSeconds < 2)
            return PaintFreshOpening(Canvas, Elements, P.Layer, LastOpeningSeconds);
        const bool bPlaying = Battle.Status == TEXT("player-turn");
        // FightPanel.onBattleStart opens the HUD (+2 s on the local opening clock) and plays
        // FightMainPanel `In`, which starts OwnCardArea `In` on the same frame.
        const double HudSeconds = LastOpeningSeconds >= 2 ? LastOpeningSeconds - 2 : -1;
        HczsSourceUiTimeline::FSample HudNow = HudInRest, CardNow = OwnCardInRest;
        FString HudError;
        if (HudSeconds >= 0 && HudIn.bValid && !HczsSourceUiTimeline::Evaluate(HudIn, HudSeconds, FVector2D(0, 720), HudNow, HudError))
            HudNow = HudInRest;
        if (HudSeconds >= 0 && OwnCardIn.bValid && !HczsSourceUiTimeline::Evaluate(OwnCardIn, HudSeconds, FVector2D(0, 720), CardNow, HudError))
            CardNow = OwnCardInRest;
        LastHudIn = MakeShared<FJsonObject>();
        LastHudIn->SetNumberField(TEXT("seconds"), HudSeconds);
        LastHudIn->SetBoolField(TEXT("valid"), HudIn.bValid && OwnCardIn.bValid);
        LastHudIn->SetBoolField(TEXT("finished"), HudSeconds < 0 || HudSeconds >= HudIn.DurationSeconds());
        auto HudGroups = MakeShared<FJsonObject>();
        const auto Group = [&](const HczsSourceUiTimeline::FSample& Now, const HczsSourceUiTimeline::FSample& Rest, const TCHAR* Name)
        {
            const FHudGroup Value = SampleHudGroup(Now, Rest, Name);
            auto Row = MakeShared<FJsonObject>();
            Row->SetBoolField(TEXT("found"), Value.bFound);
            Row->SetNumberField(TEXT("dx"), Value.Offset.X); Row->SetNumberField(TEXT("dy"), Value.Offset.Y);
            Row->SetNumberField(TEXT("opacity"), Value.Opacity);
            HudGroups->SetObjectField(Name, Row);
            FSessionPainter Q(Canvas.MakeChild(DesignSize, FSlateLayoutTransform(Value.Offset)), Elements, P.Layer,
                Brushes, IconDrawAdjustments, CompositeFont, &LastPaintedTexts, &LastPaintedSprites);
            Q.Opacity = Value.Opacity;
            return Q;
        };
        int32 MasksPainted = 0;
        for (const TCHAR* Mask : {TEXT("bg_mask_top2"), TEXT("bg_mask_top1"), TEXT("bg_mask_buttom")})
            for (const auto& Node : HudNow.Nodes)
                if (Node.Name == Mask && Node.bVisible && Node.Tint.A > 0 && !Node.SpriteId.IsEmpty())
                {
                    const auto& M = Node.LocalToDesign;
                    const FGeometry Child = Canvas.MakeChild(FVector2f(Node.Size), FSlateLayoutTransform(),
                        FSlateRenderTransform(FMatrix2x2(float(M.M00), float(M.M10), float(M.M01), float(M.M11)), FVector2f(M.TX, M.TY)),
                        FVector2f::ZeroVector);
                    FSessionPainter MaskPainter(Child, Elements, P.Layer, Brushes, IconDrawAdjustments, CompositeFont, nullptr, &LastPaintedSprites);
                    if (MaskPainter.Image(TEXT("entrance-") + Node.SpriteId, 0, 0, Node.Size.X, Node.Size.Y, Node.Tint)) ++MasksPainted;
                    P.Layer = MaskPainter.Layer;
                }
        LastHudIn->SetNumberField(TEXT("masksPainted"), MasksPainted);
        LastHudIn->SetObjectField(TEXT("groups"), HudGroups);
        {
            FSessionPainter Heads = Group(HudNow, HudInRest, TEXT("EnterancePlayerHeads"));
            const auto LeftSlot = [this](int32 Index)
            {
                // PlayerHeadArea slots HPArea_left_1..3 sit at x 120/290/460 in EnterancePlayerHeads.
                FVector2D Area(120 + 170 * Index, 0);
                const FString Name = FString::Printf(TEXT("HPArea_left_%d"), Index + 1);
                for (const auto& Node : HudInRest.Nodes)
                    if (Node.Name == Name) Area = Node.LocalToDesign.TransformPoint(FVector2D::ZeroVector);
                return Area;
            };
            if (!Battle.bIsParty)
                Heads.Health(Battle.PlayerName, Battle.PlayerId == TEXT("1") ? TEXT("player-1") : TEXT(""),
                    Battle.PlayerHp, Battle.PlayerMaxHp, Battle.PlayerShield, LeftSlot(0), false);
            for (int32 Index = 0; Battle.bIsParty && Index < Battle.Party.Num() && Index < 3; ++Index)
            {
                const FHczsPartyMemberView& Member = Battle.Party[Index];
                const FVector2D Area = LeftSlot(Index);
                const FString Portrait = TEXT("player-") + Member.Id;
                Heads.Health(Member.Name, Brushes.Contains(Portrait) ? Portrait : FString(), Member.Hp, Member.MaxHp, Member.Shield, Area, false);
                // Buff 1001 (攻击强化) stacks: reconstruction readout, the source buff icon row is not wired.
                if (Member.AttackBuff > 0)
                    Heads.Text(FString::Printf(TEXT("攻击强化 %d层"), Member.AttackBuff), Area.X - 77, Area.Y + 110, 154, 20, 15, Warm, true);
                if (Member.Hp.Approximate <= 0)
                    Heads.Box(Area.X - 77, Area.Y, 154, 108, FLinearColor(0.02f, 0.02f, 0.03f, 0.62f));
            }
            P.Layer = Heads.Layer;
        }
        {
            FSessionPainter Heads = Group(HudNow, HudInRest, TEXT("EnteranceMonsterHeads"));
            FVector2D EnemySlot(1160, 0);
            for (const auto& Node : HudInRest.Nodes)
                if (Node.Name == TEXT("HPArea_right_1"))
                    EnemySlot = Node.LocalToDesign.TransformPoint(FVector2D::ZeroVector);
            Heads.Health(Battle.EnemyName, Battle.EnemyId == TEXT("991") ? TEXT("monster-991") : TEXT(""),
                Battle.EnemyHp, Battle.EnemyMaxHp, Battle.EnemyShield, EnemySlot, true);
            if (Battle.bIsParty && Battle.EnemyAttackBuff > 0)
                Heads.Text(FString::Printf(TEXT("攻击强化 %d层"), Battle.EnemyAttackBuff), EnemySlot.X - 77, EnemySlot.Y + 110, 154, 20, 15, Warm, true);
            P.Layer = Heads.Layer;
        }
        {
            FSessionPainter Round = Group(HudNow, HudInRest, TEXT("RoundNode"));
            // TopRoundArea Text_1, parented under TopInfoArea Node_round at design (0, 148).
            FVector2D RoundSlot(640, 0);
            for (const auto& Node : HudInRest.Nodes)
                if (Node.Name == TEXT("RoundNode"))
                    RoundSlot = Node.LocalToDesign.TransformPoint(FVector2D::ZeroVector);
            const FVector2D RoundOrigin = RoundSlot + FVector2D(0, 148);
            const FVector2D RoundText = RoundOrigin + FVector2D(-48.5, -10.5);
            Round.Image(TEXT("round-bg"), RoundOrigin.X - 62.5, RoundOrigin.Y - 14, 125, 28, FLinearColor::White, false, true);
            Round.Text(FString::Printf(TEXT("第%d回合"), Battle.Round), RoundText.X, RoundText.Y, 97, 21, 20, Accent, true);
            // Battle 5000 has MaxRoundFail 30 and no RoundSuccess, so getBattleRoundSuccess returns 30.
            // The plate shows that limit minus BattleRound. Total damage stays hidden: ShowTotalDamaga defaults false.
            // The <=3 warning tint is a timeline color, not the static white text, so it stays unwired.
            if (Battle.EncounterId == TEXT("tutorial-5000"))
            {
                const int32 RemainingTurns = 30 - Battle.Round;
                Round.Image(TEXT("top-info-bg"), 545, 1, 192, 34, FLinearColor::White, false, true);
                Round.Image(TEXT("top-info-icon"), 595, 9, 20, 18, FLinearColor::White, false, true);
                Round.Text(FString::FromInt(RemainingTurns), 629.5f, 8, 23, 20, 20, FLinearColor::White, false);
            }
            P.Layer = Round.Layer;
        }
        // IntentionArea on ModelUIArea: skill_table SKILL_INTENTIONS sends 990/991 to monster_intention_table
        // 102 (attack, every MELEE tier is attack_ad3) and 992 to 2 (防御). Other encounters keep the text line.
        {
            struct FIntentItem { const TCHAR* Icon; FString Label; };
            TArray<FIntentItem> Items;
            for (int32 I = 0; I < Battle.EnemyIntentSkills.Num(); ++I)
            {
                const FString& Skill = Battle.EnemyIntentSkills[I];
                const FString Damage = Battle.EnemyIntentDamage.IsValidIndex(I) ? Battle.EnemyIntentDamage[I] : FString();
                if ((Skill == TEXT("990") || Skill == TEXT("991")) && !Damage.IsEmpty())
                    Items.Add({TEXT("intention-attack"), SimpleNum(FCString::Atod(*Damage))});
                else if (Skill == TEXT("992")) Items.Add({TEXT("intention-defense"), TEXT("防御")});
                else { Items.Reset(); break; }
            }
            FVector2f Root, Head;
            if (Battle.Status == TEXT("player-turn") && !Items.IsEmpty() && ProjectEnemyHead(Root, Head))
            {
                const FString Key = FString::Printf(TEXT("%s:%d:%s"), *Battle.Id, Battle.Round, *FString::Join(Battle.EnemyIntentSkills, TEXT(",")));
                const double Now = FSlateApplication::Get().GetCurrentTime();
                if (Key != IntentionKey) { IntentionKey = Key; IntentionSince = Now; }
                FSessionPainter Intent(Canvas, Elements, P.Layer, Brushes, IconDrawAdjustments, CompositeFont,
                    &LastPaintedTexts, &LastPaintedSprites);
                Intent.Opacity = FMath::Clamp(float(Now - IntentionSince) / 0.3f, 0.0f, 1.0f);
                Intent.OutlinePixels = 2; Intent.OutlineAlpha = 1;
                // setEntityPosition: area at (root.x, head.y + 30); arrange: item i at
                // x = -(60n+46)/2 + 23 + 60i + 30, y = IntentionItem.y(40) + 20. Cocos y-up, so subtract here.
                const int32 N = Items.Num();
                for (int32 I = 0; I < N; ++I)
                {
                    const FVector2f C(Root.X - (60.f * N + 46) / 2 + 53 + 60.f * I, Head.Y - 30 - 60);
                    Intent.Image(TEXT("intention-bg"), C.X - 26, C.Y - 26, 52, 52, FLinearColor::White, false, true);
                    // sprite_light shares the Intention_NL texture with a normal premultiplied blend.
                    Intent.Image(Items[I].Icon, C.X - 43, C.Y - 49, 86, 98, FLinearColor::White, false, true);
                    Intent.Image(Items[I].Icon, C.X - 43, C.Y - 49, 86, 98, FLinearColor::White, false, true);
                    Intent.Text(Items[I].Label, C.X + 6, C.Y, 85, 24, 20, FLinearColor::White, false, true);
                }
                P.Layer = Intent.Layer;
            }
            else if (Items.IsEmpty()) P.Wrapped(Battle.EnemyIntentText, 946, 139, 300, 16, 3, Warm);
        }
        {
            FSessionPainter Energy = Group(CardNow, OwnCardInRest, TEXT("Energy"));
            FVector2D EnergySlot(0, 555);
            for (const auto& Node : OwnCardInRest.Nodes)
                if (Node.Name == TEXT("Energy"))
                    EnergySlot = Node.LocalToDesign.TransformPoint(FVector2D::ZeroVector);
            const FVector2D EnergyBg = EnergySlot + FVector2D(-96, -39);
            const FVector2D EnergyIcon = EnergySlot + FVector2D(6.58, -37.27);
            // EnergyNumArea: txt_num1 current, txt_cut "/", txt_num2 energyPerRound.
            const FVector2D EnergyOrigin = EnergySlot + FVector2D(80, 15);
            Energy.Image(TEXT("energy-bg"), EnergyBg.X, EnergyBg.Y, 226, 78, FLinearColor::White, false, true);
            Energy.Image(TEXT("energy-icon"), EnergyIcon.X, EnergyIcon.Y, 58, 66, FLinearColor::White, false, true);
            Energy.Text(FString::FromInt(Battle.Energy), EnergyOrigin.X - 26.5, EnergyOrigin.Y - 19, 21, 32, 32, Accent, true);
            Energy.Text(TEXT("/"), EnergyOrigin.X - 5.5, EnergyOrigin.Y - 13, 11, 26, 26, Light, true);
            Energy.Text(FString::FromInt(Battle.EnergyPerRound), EnergyOrigin.X + 2.5, EnergyOrigin.Y - 13, 18, 26, 26, Light, true);
            P.Layer = Energy.Layer;
        }
        {
            FSessionPainter Deck = Group(CardNow, OwnCardInRest, TEXT("Panel_LeftDown"));
            // btn_card_ext under DeckNode (118, 70): Img_hand 56x56 and Text_deposit "牌堆".
            FVector2D DeckSlot(118, 650);
            for (const auto& Node : OwnCardInRest.Nodes)
                if (Node.Name == TEXT("DeckNode"))
                    DeckSlot = Node.LocalToDesign.TransformPoint(FVector2D::ZeroVector);
            Deck.Image(TEXT("deck-icon"), DeckSlot.X - 28, DeckSlot.Y - 28, 56, 56, FLinearColor::White, false, true);
            Deck.Text(TEXT("牌堆"), DeckSlot.X - 21.5, DeckSlot.Y + 20, 43, 20, 20, Light, true);
            // btn_menu_ext under MeauNode (44, 70): img_btn_return 56x56 and the configured "菜单" label.
            FVector2D MenuSlot(44, 650);
            for (const auto& Node : OwnCardInRest.Nodes)
                if (Node.Name == TEXT("MeauNode"))
                    MenuSlot = Node.LocalToDesign.TransformPoint(FVector2D::ZeroVector);
            Deck.Image(TEXT("menu-icon"), MenuSlot.X - 27.28, MenuSlot.Y - 30.88, 56, 56, FLinearColor::White, false, true);
            // FightSideBtnArea on LeftDown: Chat (44, 400) and Record (44, 330). Icons only; clicks do not open chat or history.
            P.Image(TEXT("chat-icon"), 16, 292, 56, 56, FLinearColor::White, false, true);
            P.Image(TEXT("record-icon"), 16, 362, 56, 56, FLinearColor::White, false, true);
            // Battle 5000 leaves Auto_Battle_Ban and Speed_Battle_Ban unset, so both buttons show after battle start.
            // Clicks do not change speed or start auto fight. The reconstructed end button sits above this row.
            P.Image(TEXT("speed-icon"), 1136, 622, 56, 56, FLinearColor::White, false, true);
            P.Image(TEXT("auto-icon"), 1208, 622, 56, 56, FLinearColor::White, false, true);
            P.Text(TEXT("自动"), 1215, 670, 42, 20, 20, Light, true);
            Deck.Text(TEXT("菜单"), MenuSlot.X - 21.5, MenuSlot.Y + 20, 43, 20, 20, Light, true);
            P.Layer = Deck.Layer;
        }
        Button(TEXT("hall"), TEXT(""), TEXT("返回大厅"), 180, 666, 143, 32);
        Button(TEXT("refresh-battle"), TEXT(""), TEXT("刷新战斗"), 1105, 138, 143, 32);
        if (bPlaying)
        {
            const TArray<FVector3f>* Placements = CardPlacements.Find(Battle.Hand.Num());
            TArray<int32> CardDrawOrder;
            for (int32 Index = 0; Index < Battle.Hand.Num() && Index < 10; ++Index)
                if (Battle.Hand[Index].InstanceId != HoveredCard && Battle.Hand[Index].InstanceId != SelectedCardInstance)
                    CardDrawOrder.Add(Index);
            // APK FightCard.setZOrder uses 200 for the selected card. Paint
            // it last and add its hit control last so visual and input order agree.
            for (const FString& Focused : {HoveredCard, SelectedCardInstance})
            {
                const int32 Index = Battle.Hand.IndexOfByPredicate([&Focused](const FHczsHandCard& Card) { return Card.InstanceId == Focused; });
                if (Index >= 0 && Index < 10) CardDrawOrder.AddUnique(Index);
            }
            for (auto It = UsableOutlineSince.CreateIterator(); It; ++It)
                if (!Battle.Hand.ContainsByPredicate([&It](const FHczsHandCard& Card) { return Card.InstanceId == It.Key(); }))
                    It.RemoveCurrent();
            const double PaintSeconds = FSlateApplication::Get().GetCurrentTime();
            for (int32 Index : CardDrawOrder)
            {
                const FHczsHandCard& Card = Battle.Hand[Index];
                const bool bHover = HoveredCard == Card.InstanceId || SelectedCardInstance == Card.InstanceId;
                const FVector3f Placement = Placements && Placements->IsValidIndex(Index) ? (*Placements)[Index]
                    : FVector3f((Index - (Battle.Hand.Num() - 1) * 0.5f) * 90, 90, 0);
                FVector2f Center(640 + Placement.X, 720 - Placement.Y - (bHover ? 28 : 0));
                float Angle = Placement.Z, Tilt = 0;
                const bool bOpeningDispatch = LastOpeningSeconds >= 0 && Battle.Hand.Num() <= 8 &&
                    LastOpeningSeconds < 3.5 + HczsCardDeal::DispatchSeconds(Battle.Hand.Num());
                const int32 RoundDealIndex = bOpeningDispatch ? INDEX_NONE : RoundDeal.Instances.IndexOfByKey(Card.InstanceId);
                const bool bDispatching = bOpeningDispatch || RoundDealIndex != INDEX_NONE;
                const double DealElapsed = bOpeningDispatch ? LastOpeningSeconds - 3.5 : RoundDealElapsed();
                // Drawn cards stay in the pile until the enemy presentation releases the draw action.
                if (bDispatching && DealElapsed < 0) continue;
                if (bDispatching)
                {
                    HczsCardDeal::FSample Deal; FString Error;
                    if (HczsCardDeal::Sample(DealElapsed, bOpeningDispatch ? Index : RoundDealIndex,
                        bOpeningDispatch ? Battle.Hand.Num() : RoundDeal.Instances.Num(),
                        FVector2D(1280, 720), 126, FVector2D(640, 720), FVector2D(Center), Angle, Deal, Error))
                    {
                        auto Row = MakeShared<FJsonObject>();
                        Row->SetStringField(TEXT("route"), bOpeningDispatch ? TEXT("opening") : TEXT("round-start"));
                        Row->SetStringField(TEXT("instanceId"), Card.InstanceId);
                        Row->SetNumberField(TEXT("elapsed"), DealElapsed);
                        Row->SetNumberField(TEXT("index"), Index);
                        Row->SetNumberField(TEXT("x"), Deal.Position.X); Row->SetNumberField(TEXT("y"), Deal.Position.Y);
                        Row->SetNumberField(TEXT("angle"), Deal.AngleZ); Row->SetNumberField(TEXT("tilt"), Deal.TiltX);
                        Row->SetStringField(TEXT("phase"), HczsCardDeal::PhaseName(Deal.Phase)); Row->SetBoolField(TEXT("visible"), Deal.bVisible);
                        LastDealtCards.Add(MakeShared<FJsonValueObject>(Row));
                        if (!Deal.bVisible) continue;
                        Center = FVector2f(Deal.Position); Angle = Deal.AngleZ; Tilt = Deal.TiltX;
                    }
                    else UE_LOG(LogTemp, Warning, TEXT("HCZS source card dispatch rejected: %s"), *Error);
                }
                // Orthographic projection of the authored X tilt. Original
                // Cocos perspective is not recovered by this Slate adapter.
                const FMatrix2x2 CardLinear = Concatenate(FScale2D(1.0f, FMath::Cos(FMath::DegreesToRadians(Tilt))),
                    FQuat2D(FMath::DegreesToRadians(Angle)));
                const FSlateRenderTransform Transform(CardLinear, Center - TransformPoint(CardLinear, FVector2f(63, 83)));
                const FGeometry CardGeometry = Canvas.MakeChild(FVector2f(126, 166), FSlateLayoutTransform(), Transform, FVector2f::ZeroVector);
                FSessionPainter C(CardGeometry, Elements, P.Layer, Brushes, IconDrawAdjustments, CompositeFont,
                    &LastPaintedTexts, &LastPaintedSprites);
                C.bSmoothCard = true;
                const bool bCardEnabled = !bBusy && CanDragCard(Card.InstanceId);
                const FLinearColor Tint(1, 1, 1, (bDispatching || bCardEnabled) ? 1.0f : 0.56f);
                // FightSmallCard nodes are centred on the 126x166 card at scale 1. Usable,
                // CharImage_NL_S and Face_NL_S therefore sit at (-28, -34) 182x234 and (2, 4) 120x120.
                // The local Cost <= Energy check stands in for the server cardInfo.canUse flag.
                // Party hands are not CharPos-sorted on the server, so each run of one owner gets a label.
                const FString OwnerLabel = Battle.bIsParty ? Card.OwnerName : Battle.PlayerName;
                const bool bGroupStart = Index == 0 || (Battle.bIsParty && Battle.Hand[Index - 1].OwnerIndex != Card.OwnerIndex);
                if (bGroupStart)
                {
                    // CardBaseArea._updateNameLabel seeks the first hand card of each CharPos group;
                    // NameLabelArea hides it while that card is dispatching. Root sits at card
                    // (-getCardWidth/2 - 4, getCardHeight/2 + 3) and follows the card rotation.
                    if (bDispatching || OwnerLabel.IsEmpty()) { if (Index == 0) NameLabelSince = -1; }
                    else
                    {
                        if (NameLabelSince < 0) NameLabelSince = PaintSeconds;
                        FSessionPainter Label(CardGeometry, Elements, C.Layer, Brushes, IconDrawAdjustments,
                            TitleFont ? TitleFont : CompositeFont, &LastPaintedTexts, &LastPaintedSprites);
                        Label.bSmoothCard = true;
                        Label.Opacity = FMath::Clamp(float(PaintSeconds - NameLabelSince) / 0.2f, 0.0f, 1.0f);
                        // getPlayerNameForFightCard stacks CharName vertically; names over five glyphs use 18px.
                        // The 19x46 two-line Txt sets a 23px line at 22px, and taller text stretches bg.
                        const int32 Glyphs = OwnerLabel.Len();
                        const float FontPixels = Glyphs > 5 ? 18 : 22;
                        const float LineHeight = 23 * FontPixels / 22;
                        const float BgHeight = 100 + FMath::Max(0.0f, Glyphs * LineHeight - 46);
                        Label.Image(TEXT("card-owner-bg"), -36, -3, 32, BgHeight);
                        // Mark (-16, -17) at 0.75 holds Power_water_*Area's 150px drop at 0.59.
                        // The reference battle shows the purple MID mark; CharPos is not sent to this client.
                        const float Mark = 150 * 0.59f * 0.75f;
                        Label.Image(TEXT("card-owner-mark-1"), -20 - Mark * 0.5f, 14 - Mark * 0.5f, Mark, Mark);
                        for (int32 Glyph = 0; Glyph < Glyphs; ++Glyph)
                            Label.Text(OwnerLabel.Mid(Glyph, 1), -36, 33 + Glyph * LineHeight, 30, LineHeight,
                                FontPixels, FLinearColor::White, true, false);
                        C.Layer = Label.Layer;
                    }
                }
                const FString CardArt = TEXT("card-") + Card.CardId;
                const bool bHasArt = Brushes.Contains(CardArt);
                const FHczsCardFace* Face = CardFaces.Find(Card.CardId);
                const FString FrameKey = Face ? Face->Frame : TEXT("card-frame-attack");
                if (bHasArt && !bDispatching && bCardEnabled && SelectedCardInstance != Card.InstanceId)
                {
                    const double Since = UsableOutlineSince.FindOrAdd(Card.InstanceId, PaintSeconds);
                    const float Fade = FMath::Clamp(float(PaintSeconds - Since) / 0.1f, 0.0f, 1.0f);
                    C.Image(TEXT("card-usable-light"), -28, -34, 182, 234, FLinearColor(1, 1, 1, Fade));
                }
                else UsableOutlineSince.Remove(Card.InstanceId);
                if (bHover) C.Box(-3, -3, 132, 172, FLinearColor(Accent.R, Accent.G, Accent.B, 0.85f));
                if (!bHasArt) C.Box(2, 2, 122, 162, FLinearColor(0.94f, 0.95f, 0.97f, 1));
                if (bHasArt)
                {
                    C.Image(CardArt, 2, 4, 120, 120, Tint);
                    const FSlateBrush* Frame = Brushes.Find(FrameKey);
                    if (Frame)
                    {
                        LastPaintedSprites.Add(FrameKey);
                        const FSlateRenderTransform FrameTransform(FQuat2D(PI * 0.5f), FVector2f(154, -34));
                        FSessionPainter FramePainter(CardGeometry.MakeChild(FVector2f(234, 182),
                            FSlateLayoutTransform(), FrameTransform, FVector2f::ZeroVector),
                            Elements, C.Layer, Brushes, IconDrawAdjustments, CompositeFont);
                        FramePainter.SmoothQuad(*Frame, 0, 0, 234, 182, Tint);
                        C.Layer = FramePainter.Layer;
                    }
                }
                else C.Box(7, 113, 112, 51, FLinearColor(0.94f, 0.95f, 0.97f, 1));
                if (Face)
                {
                    // rare_bg (0,-20) 120x120 at 0.5 holds Ssr_NL at its centre; img_infobar anchored (.5, 1)
                    // at (-46, 62) 48x94 at 0.6 holds img_type at (24, 52). Card-centre Cocos coordinates.
                    C.Image(TEXT("card-rarity-bg"), 33, 73, 60, 60, Tint, false, true);
                    C.Image(FString::Printf(TEXT("card-rarity-%d"), Face->Rarity), 33, 73, 60, 60, Tint, false, true);
                    C.Image(TEXT("card-type-bar-attack"), 2.6f, 21, 28.8f, 56.4f, Tint, false, true);
                    C.Image(TEXT("card-type-icon-attack"), 5, 34.2f, 24, 24, Tint, false, true);
                }
                C.Image(TEXT("card-cost"), -5, -9, 32, 38, Tint);
                C.Text(FString::FromInt(Card.Cost), -5, -7, 32, 32, 23, Light, true);
                // APK FightSmallCard: Name_S center (0,-40), 16px; Descr top
                // (0,-50), 102x24 at 12px, relative to the 126x166 card center.
                C.Text(Card.Name, 7, 115, 112, 16, 16, FLinearColor(67 / 255.0f, 53 / 255.0f, 85 / 255.0f, 1), true, false);
                const FLinearColor DescrColor(54 / 255.0f, 52 / 255.0f, 85 / 255.0f, 1);
                const FString& DescriptionValue = Face && Face->bTotalDamage ? Card.TotalDamage : Card.FirstDamage;
                if (Face && !DescriptionValue.IsEmpty())
                {
                    const TArray<FString> Lines = C.WrapLines(Face->Description.Replace(TEXT("%s"), *DescriptionValue), 102, 12);
                    for (int32 Line = 0; Line < FMath::Min(2, Lines.Num()); ++Line)
                        C.Text(Lines[Line], 12, 133 + Line * 12, 102, 12, 12, DescrColor, true, false);
                }
                else C.Wrapped(Card.EffectsText.Replace(TEXT(" · "), TEXT("\n")), 12, 133, 102, 12, 2, DescrColor, false, 0);
                P.Layer = C.Layer;
                FHczsSessionControl Control;
                Control.Action = TEXT("play-card");
                Control.Value = Card.InstanceId;
                Control.Rect = FSlateRect(0, 0, 126, 166);
                Control.Transform = Transform;
                Control.bTransformed = true;
                Control.bEnabled = bCardEnabled;
                Controls.Add(Control);
            }
            const bool bEnd = !bBusy && Session->CanSubmitBattleIntent();
            {
                // EndArea_ext Node_s1 at the RightBottom/EnteranceFEndTurn rest origin (1280, 555), in
                // the state black_in (frames 5-27) ends on: bg_s1 226x78 from (-108, -39) runs past the
                // right edge as in the source, icon_s1 back at scale 1 centred at (-46, -12), glow alpha 0.
                // Dimming while a request is pending is a reconstruction; Node_s2 white_* states are off.
                FSessionPainter EndArea = Group(CardNow, OwnCardInRest, TEXT("EndTurnArea"));
                const float EndAlpha = bEnd ? 1.0f : 0.5f;
                EndArea.Image(TEXT("end-bg"), 1172, 516, 226, 78, FLinearColor(1, 1, 1, EndAlpha), false, true);
                EndArea.Image(TEXT("end-icon-normal"), 1192, 501, 84, 84, FLinearColor(1, 1, 1, EndAlpha), false, true);
                EndArea.Text(TEXT("回合结束"), 1189, 562.5f, 82, 21, 20, FLinearColor(1, 1, 1, EndAlpha), true);
                P.Layer = EndArea.Layer;
            }
            FHczsSessionControl End;
            End.Action = TEXT("end-turn");
            // btn's Replace panel: 100x80 anchored (1, .5) at the EndArea origin.
            End.Rect = FSlateRect(1180, 515, 1280, 595);
            End.bEnabled = bEnd;
            Controls.Add(End);
            if (Battle.Hand.IsEmpty()) P.Text(TEXT("本回合已无手牌"), 385, 584, 510, 50, 23, Muted, true);
            else if (!bPresentationBusy) P.Text(TEXT("拖牌到敌方 · 松手出牌"), 390, 485, 500, 24, 17, Accent, true);
            if (bCardDetailOpen)
                if (const auto* Selected = Battle.Hand.FindByPredicate([this](const FHczsHandCard& C) { return C.InstanceId == SelectedCardInstance; }))
                {
                    const TArray<FString> DescriptionLines = P.WrapLines(Selected->EffectsText, 528, 14);
                    const float DetailHeight = FMath::Max(58.0f, 34.0f + DescriptionLines.Num() * 17);
                    const float DetailTop = 479 - DetailHeight;
                    P.Box(360, DetailTop, 560, DetailHeight, FLinearColor(0.025f, 0.04f, 0.075f, 0.91f));
                    P.Text(Selected->Name + TEXT(" · ") + FString::FromInt(Selected->Cost) + TEXT("能量"), 376, DetailTop + 4, 528, 24, 17, Light, true);
                    for (int32 Line = 0; Line < DescriptionLines.Num(); ++Line)
                        P.Text(DescriptionLines[Line], 376, DetailTop + 29 + Line * 17, 528, 17, 14, Light);
                }
            if (bCardGestureActive && bCardDraggedOut)
            {
                FVector2f ArrowStart = CardGestureStart;
                const int32 CardIndex = Battle.Hand.IndexOfByPredicate([this](const FHczsHandCard& C) { return C.InstanceId == CardGestureInstance; });
                if (const auto* NormalPlacements = CardPlacements.Find(Battle.Hand.Num()))
                    if (NormalPlacements->IsValidIndex(CardIndex))
                        ArrowStart = FVector2f(640 + (*NormalPlacements)[CardIndex].X, 720 - (*NormalPlacements)[CardIndex].Y);
                const int32 BeforeArrow = P.Layer;
                P.Layer = PaintSourceTargetArrow(Canvas, Elements, P.Layer, ArrowStart, CardGesturePoint);
                bLastPaintedDragCue = P.Layer > BeforeArrow;
            }
            // Guide group 1001: CONDITION MazeId 3997 (entered from the dungeon) and expires with the first 5000 win.
            bGuideShown = false;
            if (Battle.EncounterId == TEXT("tutorial-5000") && Session->bInMainlineDungeon &&
                Session->MainlineProgress.bIsValid && !Session->MainlineProgress.bFirstChallengePassed)
            {
                const double Now = FSlateApplication::Get().GetCurrentTime();
                Guide.Observe(Battle.Id, Battle.Status, Battle.Round, Battle.Energy, Battle.ActionIndex, Now);
                const FHczsGuideStep* Step = Guide.Current();
                const bool bOpeningDispatch = LastOpeningSeconds >= 0 && LastOpeningSeconds < 3.5 + HczsCardDeal::DispatchSeconds(Battle.Hand.Num());
                if (Step && Guide.IsVisible(Now) && !bBusy && !bPresentationBusy && !bOpeningDispatch && !bCardGestureActive)
                {
                    bGuideShown = true;
                    // Anchor centres in design pixels; guide_show_table offsets are Cocos y-up.
                    FVector2f Centre(640, 615), Size(Step->BoxWidth, Step->BoxHeight);
                    bool bHole = true;
                    if (Step->Anchor == EHczsGuideAnchor::Card && !Battle.Hand.IsEmpty())
                    {
                        const int32 Index = FMath::Clamp(Step->CardIndex, 0, Battle.Hand.Num() - 1);
                        const FVector3f Placement = Placements && Placements->IsValidIndex(Index) ? (*Placements)[Index]
                            : FVector3f((Index - (Battle.Hand.Num() - 1) * 0.5f) * 90, 90, 0);
                        Centre = FVector2f(640 + Placement.X, 720 - Placement.Y);
                        if (Size.X <= 0) Size = FVector2f(126, 166);
                    }
                    else if (Step->Anchor == EHczsGuideAnchor::Energy)
                    {
                        FVector2D EnergySlot(0, 555);
                        for (const auto& Node : OwnCardInRest.Nodes)
                            if (Node.Name == TEXT("Energy")) EnergySlot = Node.LocalToDesign.TransformPoint(FVector2D::ZeroVector);
                        Centre = FVector2f(EnergySlot);
                    }
                    else if (Step->Anchor == EHczsGuideAnchor::EndTurn) { Centre = FVector2f(1230, 555); Size = FVector2f(100, 80); }
                    else if (Step->Anchor != EHczsGuideAnchor::Hand) bHole = false;
                    Centre += FVector2f(Step->BoxX, -Step->BoxY);
                    const FSlateRect Hole(Centre - Size * 0.5f, Centre + Size * 0.5f);
                    const FLinearColor Mask(0, 0, 0, 0.55f);
                    if (bHole)
                    {
                        P.Box(0, 0, 1280, Hole.Top, Mask);
                        P.Box(0, Hole.Bottom, 1280, 720 - Hole.Bottom, Mask);
                        P.Box(0, Hole.Top, Hole.Left, Hole.Bottom - Hole.Top, Mask);
                        P.Box(Hole.Right, Hole.Top, 1280 - Hole.Right, Hole.Bottom - Hole.Top, Mask);
                        const float Pulse = 0.55f + 0.45f * FMath::Sin(float(Now) * 2 * PI);
                        const FLinearColor Edge(Accent.R, Accent.G, Accent.B, Pulse);
                        P.Box(Hole.Left - 3, Hole.Top - 3, Hole.Right - Hole.Left + 6, 3, Edge);
                        P.Box(Hole.Left - 3, Hole.Bottom, Hole.Right - Hole.Left + 6, 3, Edge);
                        P.Box(Hole.Left - 3, Hole.Top, 3, Hole.Bottom - Hole.Top, Edge);
                        P.Box(Hole.Right, Hole.Top, 3, Hole.Bottom - Hole.Top, Edge);
                    }
                    else P.Box(0, 0, 1280, 720, Mask);
                    FVector2f Root, Head;
                    // GuideGesture_ext.csb is not imported; the swipe reuses the source target arrow toward the enemy.
                    if (Step->Gesture && FCString::Strcmp(Step->Gesture, TEXT("swipe")) == 0 && ProjectEnemyHead(Root, Head))
                    {
                        const float Phase = FMath::Fmod(float(Now), 1.2f) / 1.2f;
                        P.Layer = PaintSourceTargetArrow(Canvas, Elements, P.Layer, Centre, FMath::Lerp(Centre, FVector2f(Root.X, Head.Y + 60), Phase));
                    }
                    // Bubble sits at the _cTouch hand centre plus the source X / Y 170 offset.
                    const FVector2f Bubble(FMath::Clamp(640 + Step->TextX, 340.0f, 940.0f), 615 - 170);
                    P.Box(Bubble.X - 300, Bubble.Y - 36, 600, 72, FLinearColor(0.02f, 0.03f, 0.06f, 0.92f));
                    P.Box(Bubble.X - 300, Bubble.Y - 36, 4, 72, Accent);
                    if (Step->Talker) P.Text(Step->Talker, Bubble.X - 284, Bubble.Y - 34, 200, 22, 16, Accent);
                    P.Wrapped(Step->Text, Bubble.X - 284, Bubble.Y - (Step->Talker ? 10 : 22), 568, 20, 2, Light);
                    FHczsSessionControl Next;
                    Next.Action = TEXT("guide-next");
                    Next.Rect = FSlateRect(Bubble.X - 300, Bubble.Y - 36, Bubble.X + 300, Bubble.Y + 36);
                    Next.bEnabled = Step->Advance == EHczsGuideAdvance::Tap;
                    Controls.Add(Next);
                }
            }
        }
        else
        {
            const bool bBossResult = Battle.bIsParty && Battle.EncounterId == TEXT("prologue-boss-1703") &&
                Battle.PlayerId == TEXT("party-1-3") && Battle.EnemyId == TEXT("2013");
            const bool bMainlineResult = Session->bHasMainlineProgression && Battle.Status == TEXT("won") && (bBossResult ||
                (Battle.EncounterId == TEXT("tutorial-5000") && Battle.PlayerId == TEXT("1") && Battle.EnemyId == TEXT("991")));
            P.Box(270, 205, 740, bMainlineResult ? 395 : 300, FLinearColor(0.015f, 0.024f, 0.05f, 0.89f));
            if (Battle.Status == TEXT("won"))
            {
                P.Image(TEXT("victory-glow"), 392, 222, 496, 173);
                P.Image(TEXT("victory-title"), 403, 227, 474, 153);
                P.Text(TEXT("战斗胜利"), 440, 378, 400, 39, 27, Warm, true);
            }
            else P.Text(TEXT("战斗失败"), 440, 292, 400, 65, 42, Muted, true);
            const FString ResultMessage = !bMainlineResult ? TEXT("战斗记录已保存") :
                !Session->bMainlineStateCurrent ? TEXT("战斗已保存 · 主线进度尚未同步") :
                bBossResult ? (Session->MainlineProgress.bBossChallengePassed ? TEXT("序章首领战已通关 · 3998 的 successTime 为 1") : TEXT("战斗已保存 · 请确认序章首领战通关")) :
                Session->MainlineProgress.bFirstChallengePassed ? TEXT("序章首战已通关 · 首领战可从副本继续") : TEXT("战斗已保存 · 请确认序章首战通关");
            P.Text(ResultMessage, 340, 422, 600, 25, 17, Muted, true);
            const bool bEncounterAvailable = Session->Encounters.ContainsByPredicate([&Battle](const FHczsEncounterSummary& E)
                { return E.Id == Battle.EncounterId && HasRecoveredScene(E); });
            Button(TEXT("challenge-again"), TEXT(""), TEXT("再战一次"), 407, 458, 210, 46,
                Session->bAllowNewBattles && bEncounterAvailable, true);
            Button(TEXT("hall"), TEXT(""), TEXT("返回大厅"), 661, 458, 210, 46);
            if (bMainlineResult)
            {
                const bool bPassed = Session->bMainlineStateCurrent && (bBossResult ? Session->MainlineProgress.bBossChallengePassed
                    : Session->MainlineProgress.bFirstChallengePassed);
                Button(TEXT("settle-mainline"), TEXT(""), bPassed ? TEXT("已记录通关") : bBossResult ? TEXT("确认序章首领战通关") : TEXT("确认序章首战通关"),
                    407, 516, 250, 43, Session->CanConfirmMainlineVictory(), true);
                Button(TEXT("refresh-mainline"), TEXT(""), TEXT("读取最新进度"), 681, 516, 190, 43);
                P.Text(TEXT("本地主线进度适配 · 本次不发放奖励"), 340, 568, 600, 22, 14, Muted, true);
            }
        }
        P.Layer = PaintFreshOpening(Canvas, Elements, P.Layer, LastOpeningSeconds);
    }
    else if (bEncounterPanel && !Session->SelectedProfileId.IsEmpty())
    {
        P.Box(0, 0, 1280, 720, FLinearColor(0.015f, 0.02f, 0.04f, 0.60f));
        P.Box(180, 86, 920, 540, Ink);
        P.Text(Session->bHasMainlineProgression ? TEXT("本地选关与主线进度") : TEXT("本地战斗预览"), 220, 114, 620, 45, 32, Light);
        const FString ProgressMessage = !Session->bHasMainlineProgression ? TEXT("选择恢复样例或继续本地战斗") :
            !Session->bMainlineStateCurrent ? TEXT("主线进度未同步 · 请读取最新进度") :
            Session->MainlineProgress.bBossChallengePassed ? TEXT("3997 与 3998 的 successTime 均为 1") :
            Session->MainlineProgress.bFirstChallengePassed ? TEXT("3997 的 successTime 为 1 · 3998 尚无记录") : TEXT("序章尚无 activityDatas 记录 · 不预填 successTime 0");
        P.Text(ProgressMessage, 223, 163, 800, 24, 17, Muted);
        if (Session->bHasMainlineProgression)
            Button(TEXT("refresh-mainline"), TEXT(""), TEXT("读取最新进度"), 878, 120, 177, 35);
        P.Box(680, 208, 1, 320, FLinearColor(0.2f, 0.3f, 0.4f, 0.75f));
        for (int32 Index = 0; Index < Session->Encounters.Num() && Index < 4; ++Index)
        {
            const FHczsEncounterSummary& Encounter = Session->Encounters[Index];
            const bool Selected = Session->SelectedEncounterId == Encounter.Id;
            const bool AvailableScene = HasRecoveredScene(Encounter);
            const float Y = 216 + Index * 78;
            Button(TEXT("select-encounter"), Encounter.Id, Encounter.Title, 224, Y, 408, 45, AvailableScene, Selected);
            const FString SceneLine = !AvailableScene ? TEXT("场景待恢复")
                : Encounter.Id == TEXT("city-preview-10405") ? TEXT("本地预览 · 允许终结技 · 不是序章解锁")
                : Encounter.PlayerName + TEXT("  ·  ") + Encounter.EnemyName;
            P.Text(SceneLine, 235, Y + 46, 390, 20, 14, Muted);
        }
        if (Session->Encounters.IsEmpty()) P.Text(TEXT("暂无已开放的关卡"), 227, 245, 400, 40, 21, Muted);
        P.Text(TEXT("战斗记录"), 712, 211, 346, 30, 22, Accent);
        const int32 PageCount = FMath::Max(1, (Session->Battles.Num() + 3) / 4);
        const int32 Page = FMath::Clamp(BattlePage, 0, PageCount - 1);
        for (int32 Index = Page * 4; Index < FMath::Min(Page * 4 + 4, Session->Battles.Num()); ++Index)
        {
            const FHczsBattleSummary& Battle = Session->Battles[Index];
            const bool AvailableScene = Battle.DefinitionId.StartsWith(TEXT("tutorial-5000-"))
                || Battle.DefinitionId.StartsWith(TEXT("city-preview-10405-"));
            const FString Status = Battle.Status == TEXT("player-turn") ? TEXT("继续")
                : Battle.Status == TEXT("won") ? TEXT("已胜利") : TEXT("已结束");
            Button(AvailableScene ? TEXT("continue-battle") : TEXT("inspect-battle"), Battle.Id,
                AvailableScene ? FString::Printf(TEXT("%s  ·  第 %d 回合"), *Status, Battle.Round)
                    : TEXT("读取记录 · 场景待恢复"),
                710, 257 + (Index - Page * 4) * 54, 346, 42);
        }
        if (Session->Battles.IsEmpty()) P.Text(TEXT("还没有战斗记录"), 715, 285, 330, 40, 19, Muted);
        if (PageCount > 1)
            Button(TEXT("battle-page"), TEXT(""), FString::Printf(TEXT("%d / %d   下一页"), Page + 1, PageCount),
                792, 490, 180, 33);
        Button(TEXT("close-selection"), TEXT(""), TEXT("返回大厅"), 224, 559, 170, 44);
        const bool SelectedSceneReady = Session->Encounters.ContainsByPredicate([this](const FHczsEncounterSummary& E)
            { return E.Id == Session->SelectedEncounterId && HasRecoveredScene(E); });
        Button(TEXT("new-battle"), TEXT(""), TEXT("开始战斗"), 848, 552, 207, 51,
            SelectedSceneReady && Session->bEncounterScenarioReady && Session->bAllowNewBattles, true);
    }
    else
    {
        P.Box(0, 0, 1280, 720, FLinearColor(0.015f, 0.02f, 0.04f, 0.60f));
        P.Box(250, 115, 780, 485, Ink);
        P.Text(TEXT("重逢之时"), 290, 139, 610, 43, 31, Light);
        P.Text(TEXT("选择本地档案"), 292, 190, 590, 28, 20, Accent);
        if (Session->Phase == EHczsSessionPhase::Connecting)
            P.Text(TEXT("正在连接本地服务…"), 320, 290, 640, 44, 22, Muted, true);
        else if (!Session->bLocalServiceAvailable)
            P.Text(TEXT("本地服务暂不可用"), 320, 290, 640, 44, 22, Muted, true);
        else if (bConfirmNewProfile)
        {
            P.Text(TEXT("创建一个新的“本地旅人”档案"), 320, 274, 640, 40, 25, Light, true);
            P.Text(TEXT("现有档案会保留，新档案使用独立进度。"), 320, 326, 640, 30, 18, Muted, true);
            Button(TEXT("cancel-new-profile"), TEXT(""), TEXT("返回选择"), 330, 405, 230, 48);
            Button(TEXT("create-profile"), TEXT(""), TEXT("创建并进入大厅"), 637, 405, 303, 48, Session->bAllowNewProfiles, true);
        }
        else
        {
            const int32 PageCount = FMath::Max(1, (Session->Profiles.Num() + 3) / 4);
            const int32 Page = FMath::Clamp(ProfilePage, 0, PageCount - 1);
            for (int32 Index = Page * 4; Index < FMath::Min(Page * 4 + 4, Session->Profiles.Num()); ++Index)
            {
                const FHczsLocalProfile& Profile = Session->Profiles[Index];
                Button(TEXT("select-profile"), Profile.Id, Profile.DisplayName, 292,
                    237 + (Index - Page * 4) * 55, 695, 43, true, Profile.Id == Session->SelectedProfileId);
            }
            if (Session->Profiles.IsEmpty()) P.Text(TEXT("还没有本地档案，创建后即可进入大厅"), 310, 295, 660, 42, 21, Muted, true);
            if (PageCount > 1)
                Button(TEXT("profile-page"), TEXT(""), FString::Printf(TEXT("%d / %d   下一页"), Page + 1, PageCount),
                    785, 476, 200, 30);
            Button(TEXT("confirm-new-profile"), TEXT(""), TEXT("新建本地档案"), 292, 529, 249, 43, Session->bAllowNewProfiles, true);
            if (!Session->SelectedProfileId.IsEmpty())
                Button(TEXT("close-selection"), TEXT(""), TEXT("返回大厅"), 583, 529, 196, 43);
        }
        // GET refresh is also available when the local server is unavailable.
        const bool RefreshEnabled = !Session->bRequestInFlight && !Session->bHasPendingIntent;
        const bool OriginalBusy = bBusy;
        Button(TEXT("refresh-bootstrap"), TEXT(""), TEXT("刷新连接 / 档案"), 811, 529, 175, 43, RefreshEnabled);
        if (!OriginalBusy && !Controls.IsEmpty()) Controls.Last().bEnabled = RefreshEnabled;
    }
    // Routine battle state is already visible in the HUD. Keep the hand's
    // original bottom footprint free; actionable errors go above the playfield.
    const bool bBattleHUD = bBattleScene && Session->Phase == EHczsSessionPhase::Battle;
    if (!Session->UserMessage.IsEmpty() && (!bBattleHUD || !Session->ErrorCode.IsEmpty()) && !Session->bHasPendingIntent)
    {
        const float MessageY = bBattleHUD ? 162.0f : 675.0f;
        P.Box(280, MessageY, 720, 32, FLinearColor(0.015f, 0.02f, 0.04f, 0.87f));
        P.Text(Session->UserMessage, 292, MessageY + 2, 696, 27, 15,
            Session->ErrorCode.IsEmpty() ? Muted : Warm, true);
    }
    if (Session->bRequestInFlight)
    {
        P.Box(464, 115, 352, 38, FLinearColor(0.015f, 0.024f, 0.05f, 0.91f));
        P.Text(TEXT("正在与本地服务同步…"), 465, 117, 350, 34, 18, Accent, true);
    }
    else if (bPresentationBusy && !Session->IsBattleEntranceLocked())
        P.Text(TEXT("正在播放战斗动作…"), 464, 117, 352, 34, 18, Accent, true);
    else if (Session->bHasPendingIntent)
    {
        P.Box(0, 0, 1280, 720, FLinearColor(0.015f, 0.02f, 0.04f, 0.57f));
        P.Box(360, 259, 560, 194, Ink);
        P.Text(TEXT("操作结果尚未确认"), 385, 280, 510, 40, 25, Warm, true);
        P.Wrapped(Session->UserMessage, 395, 329, 490, 17, 2, Muted);
        // Retrying reuses the bridge's exact request ID, revision and body.
        FHczsSessionControl Retry;
        Retry.Action = TEXT("retry-intent");
        Retry.Rect = FSlateRect(480, 391, 800, 433);
        Retry.bEnabled = Session->bPendingIntentRetryable;
        P.Box(480, 391, 320, 42, FLinearColor(0.045f, 0.34f, 0.39f, 0.98f));
        P.Text(Retry.bEnabled ? TEXT("确认同一次操作") : TEXT("刷新档案后手动选择"),
            480, 391, 320, 42, 18, Retry.bEnabled ? Light : Muted, true);
        Controls.Reset();
        Controls.Add(Retry);
    }
    return P.Layer;
}

int32 UHczsSessionWidget::PaintSourceTargetArrow(const FGeometry& Canvas, FSlateWindowElementList& Elements,
    int32 Layer, const FVector2f& Start, const FVector2f& End) const
{
    const auto* Ribbon = Brushes.Find(TEXT("target-arrow-ribbon"));
    const auto* Head = Brushes.Find(TEXT("target-arrow-head"));
    if (!Ribbon || !Head || !FSlateApplication::IsInitialized()) return Layer;
    // Ordinary static evidence: native-target-arrow-evidence c93740/c93d28.
    // Source Y-up, 160/20 widths, 60 pairs, tangent helper's divisor 3.14.
    // UE UI material/blending is an adaptation, not verified APK execution.
    const FVector2f A(Start.X, DesignSize.Y - Start.Y), B(End.X, DesignSize.Y - End.Y);
    const FVector2f Delta = B - A;
    const float Length = Delta.Size();
    if (!FMath::IsFinite(Length) || Length < 0.1f) return Layer;
    const float SourcePi = 3.14f;
    auto Tangent = [&](float Fraction)
    {
        const float Height = Delta.X * 0.25f;
        const float Slope = 4 * Height / Length - 8 * Height * Fraction / Length;
        return (FMath::Atan2(Slope, 1.0f) + FMath::Atan2(Delta.Y, Delta.X)) * 180 / SourcePi;
    };
    const float EndRadians = Tangent(1.0f) * SourcePi / 180;
    const FVector2f HalfEnd(10 * FMath::Sin(EndRadians), -10 * FMath::Cos(EndRadians));
    const FVector2f RightStart = A + FVector2f(80, 0), LeftStart = A - FVector2f(80, 0);
    const FVector2f RightEnd = B + HalfEnd, LeftEnd = B - HalfEnd;
    auto SidePoint = [](const FVector2f& From, const FVector2f& To, float T)
    {
        const FVector2f D = To - From;
        const float L = D.Size();
        if (L < 0.1f) return From;
        const float Displacement = (D.X / 4) * (1 - 4 * FMath::Square(T - 0.5f));
        return From + D * T + FVector2f(-D.Y / L, D.X / L) * Displacement;
    };
    TArray<FSlateVertex> Vertices;
    TArray<SlateIndex> Indices;
    Vertices.Reserve(120); Indices.Reserve(354);
    const FSlateRenderTransform Render = Canvas.GetAccumulatedRenderTransform();
    for (int32 Pair = 0; Pair < 60; ++Pair)
    {
        const float T = static_cast<float>(Pair + 1) / 60;
        const float V = static_cast<float>(Pair) / 119; // native pair index / total vertices - 1
        for (int32 Side = 0; Side < 2; ++Side)
        {
            const FVector2f Source = Side == 0 ? SidePoint(RightStart, RightEnd, T) : SidePoint(LeftStart, LeftEnd, T);
            const FVector2f Point(Source.X, DesignSize.Y - Source.Y);
            const FVector2f UV(static_cast<float>(Side), V);
            Vertices.Add(FSlateVertex::Make<ESlateVertexRounding::Disabled>(Render, Point,
                FVector4f(UV.X, UV.Y, 1, 1), UV, FColor::White));
        }
    }
    for (int32 Index = 0; Index < 118; ++Index)
    {
        Indices.Add(static_cast<SlateIndex>(Index));
        Indices.Add(static_cast<SlateIndex>(Index + 1));
        Indices.Add(static_cast<SlateIndex>(Index + 2));
    }
    const auto Resource = FSlateApplication::Get().GetRenderer()->GetResourceHandle(*Ribbon);
    if (!Resource.IsValid()) return Layer;
    FSlateDrawElement::MakeCustomVerts(Elements, ++Layer, Resource, Vertices, Indices, nullptr, 0, 0);
    LastPaintedSprites.Add(TEXT("target-arrow-ribbon"));
    // Source TargetIndicator scales arrowhead by .7; native N+1 tangent supplies its orientation.
    const FVector2f Size(256 * 0.7f, 128 * 0.7f);
    const FQuat2D Rotation(FMath::DegreesToRadians(-Tangent(21.0f / 20)));
    const FSlateRenderTransform Transform(Rotation, End - TransformPoint(Rotation, Size * 0.5f));
    FSlateDrawElement::MakeBox(Elements, ++Layer, Canvas.MakeChild(Size, FSlateLayoutTransform(),
        Transform, FVector2f::ZeroVector).ToPaintGeometry(), Head, ESlateDrawEffect::None, FLinearColor::White);
    LastPaintedSprites.Add(TEXT("target-arrow-head"));
    return Layer;
}

bool UHczsSessionWidget::CanDragCard(const FString& InstanceId) const
{
    if (!Session || !bBattleScene || !SceneProblem.IsEmpty() || bPresentationBusy || IsRoundDealActive() || !Session->CanSubmitBattleIntent()
        || !HasRecoveredActors(Session->CurrentBattle)) return false;
    const auto* Card = Session->CurrentBattle.Hand.FindByPredicate([&InstanceId](const FHczsHandCard& C) { return C.InstanceId == InstanceId; });
    return Card && Card->Cost <= Session->CurrentBattle.Energy && Brushes.Contains(TEXT("card-") + Card->CardId);
}

bool UHczsSessionWidget::ProjectActorBounds(FName Tag, FSlateRect& DesignBounds) const
{
    UWorld* World = GetWorld();
    APlayerController* Controller = GetOwningPlayer();
    auto* Client = World ? World->GetGameViewport() : nullptr;
    if (!World || !Controller || !Client || !Client->Viewport || LastPaintSerial == 0) return false;
    const FIntPoint View = Client->Viewport->GetSizeXY();
    if (View.X <= 0 || View.Y <= 0) return false;
    const FVector2f Available(LastPaintGeometry.GetLocalSize());
    const float Scale = FMath::Min(Available.X / DesignSize.X, Available.Y / DesignSize.Y);
    if (Scale <= 0) return false;
    const FVector2f Offset = (Available - DesignSize * Scale) * 0.5f;
    int32 Matches = 0;
    FSlateRect Bounds(0, 0, 0, 0);
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        if (!It->ActorHasTag(Tag)) continue;
        ++Matches;
        const auto* Component = It->FindComponentByClass<USkeletalMeshComponent>();
        if (It->IsHidden() || !Component || !Component->IsVisible() || Component->bHiddenInGame
            || !Component->GetSkeletalMeshAsset()) return false;
        const FBox Box = Component->Bounds.GetBox();
        if (!Box.IsValid) return false;
        FVector2f Min(TNumericLimits<float>::Max(), TNumericLimits<float>::Max());
        FVector2f Max(-TNumericLimits<float>::Max(), -TNumericLimits<float>::Max());
        for (int32 Corner = 0; Corner < 8; ++Corner)
        {
            const FVector Location((Corner & 1) ? Box.Max.X : Box.Min.X, (Corner & 2) ? Box.Max.Y : Box.Min.Y, (Corner & 4) ? Box.Max.Z : Box.Min.Z);
            FVector2D Screen = FVector2D::ZeroVector;
            if (!Controller->ProjectWorldLocationToScreen(Location, Screen, false)) return false;
            // World projection is in viewport pixels; native widget geometry may use Slate DPI units.
            const FVector2f Point = (FVector2f(Screen.X * Available.X / View.X, Screen.Y * Available.Y / View.Y) - Offset) / Scale;
            Min.X = FMath::Min(Min.X, Point.X); Min.Y = FMath::Min(Min.Y, Point.Y);
            Max.X = FMath::Max(Max.X, Point.X); Max.Y = FMath::Max(Max.Y, Point.Y);
        }
        Bounds = FSlateRect(FMath::Clamp(Min.X, 0.0f, DesignSize.X), FMath::Clamp(Min.Y, 0.0f, DesignSize.Y),
            FMath::Clamp(Max.X, 0.0f, DesignSize.X), FMath::Clamp(Max.Y, 0.0f, DesignSize.Y));
    }
    if (Matches != 1 || Bounds.GetSize().X <= 0 || Bounds.GetSize().Y <= 0) return false;
    DesignBounds = Bounds;
    return true;
}

bool UHczsSessionWidget::ProjectEnemyHead(FVector2f& Root, FVector2f& Head) const
{
    const UWorld* World = GetWorld();
    APlayerController* Controller = GetOwningPlayer();
    auto* Client = World ? World->GetGameViewport() : nullptr;
    if (!World || !Controller || !Client || !Client->Viewport) return false;
    const FIntPoint View = Client->Viewport->GetSizeXY();
    const FVector2f Available(LastPaintGeometry.GetLocalSize());
    const float Scale = FMath::Min(Available.X / DesignSize.X, Available.Y / DesignSize.Y);
    if (View.X <= 0 || View.Y <= 0 || Scale <= 0) return false;
    const FVector2f Offset = (Available - DesignSize * Scale) * 0.5f;
    const USkeletalMeshComponent* Component = nullptr;
    for (TActorIterator<AActor> It(World); It; ++It)
        if (It->ActorHasTag(TEXT("HCZSBattleEnemy")))
        {
            if (Component) return false;
            Component = It->FindComponentByClass<USkeletalMeshComponent>();
        }
    // 991's GIM ui_head has no BoneName, so it is MatrixToBone translation (0.997159, 18.78299, -1.169679)
    // from the model root; the cube import maps source (x, y, z) to component (100x, 100z, 100y).
    if (!Component || !Component->IsVisible() || !Component->GetSkeletalMeshAsset()
        || Component->GetSkeletalMeshAsset()->GetPathName() != TEXT("/Game/Recovered/Battle/Cube/cube_battle.cube_battle")) return false;
    const FTransform& Model = Component->GetComponentTransform();
    auto Project = [&](const FVector& Location, FVector2f& Out)
    {
        FVector2D Screen;
        if (!Controller->ProjectWorldLocationToScreen(Location, Screen, false)) return false;
        Out = (FVector2f(Screen.X * Available.X / View.X, Screen.Y * Available.Y / View.Y) - Offset) / Scale;
        return true;
    };
    return Project(Model.GetLocation(), Root) && Project(Model.TransformPosition(FVector(99.7159, -116.9679, 1878.299)), Head);
}

void UHczsSessionWidget::RecordGestureEvent(const FString& Kind, const FVector2f& Point, bool bTargetHit)
{
    FHczsCardGestureEvent Event;
    Event.Kind = Kind; Event.Point = Point; Event.bTargetHit = bTargetHit;
    Event.UpwardDelta = CardGestureStart.Y - Point.Y;
    const FDateTime Now = FDateTime::UtcNow();
    Event.AtUnixMs = Now.ToUnixTimestamp() * 1000 + Now.GetMillisecond();
    if (CardGestureEvents.Num() < 256) CardGestureEvents.Add(Event);
}

void UHczsSessionWidget::CancelCardGesture(const FString& Reason)
{
    if (!bCardGestureActive) return;
    RecordGestureEvent(TEXT("cancel"), CardGesturePoint);
    LastGestureOutcome = TEXT("cancelled"); LastGestureReason = Reason; LastGestureTarget.Reset();
    bLastGestureLostCapture = Reason == TEXT("capture-lost"); bLastPointerTouch = bCardGestureTouch;
    LastPointerAction = TEXT("cancel-card-drag"); LastPointerValue = CardGestureInstance;
    bCardGestureActive = false; bCardDraggedOut = false;
    LastPointerPoint = CardGesturePoint; ++PointerEventSerial;
    // Clear first: releasing this pointer may synchronously re-enter capture-lost.
    if (FSlateApplication::IsInitialized())
        if (const auto Widget = GetCachedWidget())
            if (Widget->HasMouseCaptureByUser(CardGestureUser, CardGesturePointer))
                if (const auto User = FSlateApplication::Get().GetUser(CardGestureUser))
                    User->ReleaseCapture(static_cast<uint32>(CardGesturePointer));
    SelectedCardInstance.Reset(); bCardDetailOpen = false;
    InvalidateLayoutAndVolatility();
}

FReply UHczsSessionWidget::PressAt(const FGeometry& Geometry, const FPointerEvent& Event)
{
    if (bCardGestureActive) return FReply::Handled();
    const FVector2f Point = DesignPoint(Geometry, Event.GetScreenSpacePosition());
#if !UE_BUILD_SHIPPING
    if (IsIsolatedNativeUiTest())
        UE_LOG(LogTemp, Display, TEXT("HCZS native down: design=(%.1f,%.1f) absolute=(%.1f,%.1f) geometry=(%.1f,%.1f) controls=%d touch=%d key=%s"),
            Point.X, Point.Y, Event.GetScreenSpacePosition().X, Event.GetScreenSpacePosition().Y,
            Geometry.GetLocalSize().X, Geometry.GetLocalSize().Y, Controls.Num(), Event.IsTouchEvent(), *Event.GetEffectingButton().ToString());
#endif
    if (const FHczsGuideStep* Step = bGuideShown ? Guide.Current() : nullptr)
    {
        const int32 Hit = Controls.FindLastByPredicate([this, &Point](const FHczsSessionControl& C) { return Contains(C, Point); });
        const FString HitAction = Hit != INDEX_NONE ? Controls[Hit].Action : FString();
        const bool bAllowed = (Step->Advance == EHczsGuideAdvance::PlayCard && HitAction == TEXT("play-card")) ||
            (Step->Advance == EHczsGuideAdvance::EndTurn && HitAction == TEXT("end-turn"));
        if (!bAllowed)
        {
            if (Step->Advance == EHczsGuideAdvance::Tap && Guide.Tap(FSlateApplication::Get().GetCurrentTime()))
            {
                ++PointerEventSerial;
                LastPointerAction = TEXT("guide-next"); LastPointerValue.Reset(); LastPointerPoint = Point;
                InvalidateLayoutAndVolatility();
            }
            return FReply::Handled();
        }
    }
    for (int32 Index = Controls.Num() - 1; Index >= 0; --Index)
    {
        if (!Contains(Controls[Index], Point)) continue;
        const FHczsSessionControl Control = Controls[Index];
        ++PointerEventSerial;
        LastPointerAction = Control.Action;
        LastPointerValue = Control.Value;
        LastPointerPoint = Point;
        if (Control.Action == TEXT("play-card"))
        {
            if (!Control.bEnabled || !CanDragCard(Control.Value)) return FReply::Handled();
            bCardGestureActive = true; bCardDraggedOut = false;
            bCardGestureTouch = Event.IsTouchEvent(); CardGesturePointer = Event.GetPointerIndex(); CardGestureUser = Event.GetUserIndex();
            CardGestureInstance = Control.Value; CardGestureBattle = Session->CurrentBattle.Id;
            CardGestureRevision = Session->CurrentBattle.Revision;
            const auto* Card = Session->CurrentBattle.Hand.FindByPredicate([&Control](const FHczsHandCard& C) { return C.InstanceId == Control.Value; });
            CardGestureCardId = Card ? Card->CardId : FString();
            CardGestureStart = CardGesturePoint = Point; ++CardGestureSerial;
            // APK 3273:[19,52]0x0f..0x52; DesignConst938:[115]/[116] gives 5/30 source pixels.
            CardGestureThreshold = bCardDetailOpen ? 30.0f : 5.0f;
            CardGestureEvents.Reset(); LastGestureOutcome = TEXT("tracking"); LastGestureReason.Reset(); LastGestureTarget.Reset();
            bLastGestureTargetBoundsValid = false; bLastGestureLostCapture = false;
            RecordGestureEvent(TEXT("start"), Point);
            SelectedCardInstance = Control.Value;
            LastPointerAction = TEXT("card-gesture-start");
            InvalidateLayoutAndVolatility();
            return FReply::Handled().CaptureMouse(TakeWidget()).SetUserFocus(TakeWidget());
        }
        if (Control.bEnabled) DispatchControl(Control);
        return FReply::Handled();
    }
    return FReply::Handled();
}

FReply UHczsSessionWidget::NativeOnMouseButtonDown(const FGeometry& Geometry, const FPointerEvent& Event)
{
    if (Event.GetEffectingButton() == EKeys::LeftMouseButton)
    {
        bLastPointerTouch = false;
        return PressAt(Geometry, Event);
    }
    return Super::NativeOnMouseButtonDown(Geometry, Event);
}

FReply UHczsSessionWidget::NativeOnTouchStarted(const FGeometry& Geometry, const FPointerEvent& Event)
{
    bLastPointerTouch = Event.IsTouchEvent();
    return PressAt(Geometry, Event);
}

void UHczsSessionWidget::MoveCardGesture(const FGeometry& Geometry, const FPointerEvent& Event)
{
    if (!bCardGestureActive || CardGestureUser != Event.GetUserIndex()
        || CardGesturePointer != Event.GetPointerIndex() || bCardGestureTouch != Event.IsTouchEvent()) return;
    if (!CanDragCard(CardGestureInstance) || Session->CurrentBattle.Id != CardGestureBattle || Session->CurrentBattle.Revision != CardGestureRevision)
    { CancelCardGesture(TEXT("obsolete-state")); return; }
    CardGesturePoint = DesignPoint(Geometry, Event.GetScreenSpacePosition());
    bCardDraggedOut = bCardDraggedOut || CardGestureStart.Y - CardGesturePoint.Y >= CardGestureThreshold;
    FSlateRect Target(0, 0, 0, 0);
    bLastGestureTargetBoundsValid = ProjectActorBounds(TEXT("HCZSBattleEnemy"), Target);
    if (bLastGestureTargetBoundsValid) LastGestureTargetBounds = Target;
    RecordGestureEvent(TEXT("move"), CardGesturePoint, bLastGestureTargetBoundsValid && Target.ContainsPoint(CardGesturePoint));
    InvalidateLayoutAndVolatility();
}

FReply UHczsSessionWidget::FinishCardGesture(const FGeometry& Geometry, const FPointerEvent& Event)
{
    if (!bCardGestureActive || CardGestureUser != Event.GetUserIndex()
        || CardGesturePointer != Event.GetPointerIndex() || bCardGestureTouch != Event.IsTouchEvent()) return FReply::Unhandled();
    CardGesturePoint = DesignPoint(Geometry, Event.GetScreenSpacePosition());
    const bool bInside = FSlateRect(0, 0, DesignSize.X, DesignSize.Y).ContainsPoint(CardGesturePoint);
    FSlateRect Target(0, 0, 0, 0);
    bLastGestureTargetBoundsValid = ProjectActorBounds(TEXT("HCZSBattleEnemy"), Target);
    if (bLastGestureTargetBoundsValid) LastGestureTargetBounds = Target;
    const bool bTarget = bLastGestureTargetBoundsValid && Target.ContainsPoint(CardGesturePoint);
    const bool bCurrent = CanDragCard(CardGestureInstance) && Session->CurrentBattle.Id == CardGestureBattle && Session->CurrentBattle.Revision == CardGestureRevision;
    const bool bWasDraggedOut = bCardDraggedOut;
    const bool bMoved = bWasDraggedOut && CardGestureStart.Y - CardGesturePoint.Y >= CardGestureThreshold;
    // APK3273:[19,54]0x54..0x81 uses out-card + source bottom-origin y>100.
    // Genuine UE cancel/capture loss never calls this physical-release path.
    const bool bReleaseZone = DesignSize.Y - CardGesturePoint.Y > 100;
    RecordGestureEvent(TEXT("release"), CardGesturePoint, bTarget);
    bCardGestureActive = false; bCardDraggedOut = false; // clear before synchronous GI notification/retry paths
    LastPointerValue = CardGestureInstance; LastPointerPoint = CardGesturePoint; ++PointerEventSerial;
    bLastPointerTouch = bCardGestureTouch;
    if (!bWasDraggedOut && !bMoved && bInside && bCurrent)
    {
        LastGestureOutcome = TEXT("tap"); LastGestureReason = TEXT("below-drag-threshold");
        LastPointerAction = TEXT("tap-card"); bCardDetailOpen = true;
    }
    else if (!bInside || !bCurrent || !bReleaseZone || !bTarget || !bMoved)
    {
        LastGestureOutcome = TEXT("rejected");
        LastGestureReason = !bInside ? TEXT("outside") : !bCurrent ? TEXT("obsolete-state") : !bMoved ? TEXT("below-drag-threshold") : !bReleaseZone ? TEXT("release-zone") : TEXT("invalid-target");
        LastPointerAction = TEXT("rejected-card-drag"); SelectedCardInstance.Reset(); bCardDetailOpen = false;
    }
    else
    {
        LastGestureOutcome = TEXT("submitted"); LastGestureReason.Reset(); LastGestureTarget = Session->CurrentBattle.EnemyId;
        LastPointerAction = TEXT("play-card"); SelectedCardInstance.Reset(); bCardDetailOpen = false;
        // Fixed single enemy new-domain API. No fabricated legacy entity tID or client damage calculation.
        Session->PlayCard(CardGestureInstance);
    }
    InvalidateLayoutAndVolatility();
    return FReply::Handled().ReleaseMouseCapture();
}

FReply UHczsSessionWidget::NativeOnMouseButtonUp(const FGeometry& Geometry, const FPointerEvent& Event)
{
    if (Event.GetEffectingButton() == EKeys::LeftMouseButton && bCardGestureActive) return FinishCardGesture(Geometry, Event);
    return Super::NativeOnMouseButtonUp(Geometry, Event);
}
FReply UHczsSessionWidget::NativeOnTouchMoved(const FGeometry& Geometry, const FPointerEvent& Event)
{
    MoveCardGesture(Geometry, Event); return FReply::Handled();
}
FReply UHczsSessionWidget::NativeOnTouchEnded(const FGeometry& Geometry, const FPointerEvent& Event)
{
    return FinishCardGesture(Geometry, Event);
}
void UHczsSessionWidget::NativeOnMouseCaptureLost(const FCaptureLostEvent& Event)
{
    CancelCardGesture(TEXT("capture-lost")); Super::NativeOnMouseCaptureLost(Event);
}
void UHczsSessionWidget::NativeOnFocusLost(const FFocusEvent& Event)
{
    CancelCardGesture(TEXT("focus-lost")); Super::NativeOnFocusLost(Event);
}

bool UHczsSessionWidget::DevelopmentClickControl(const FString& Action, const FString& Value, bool bTouch)
{
#if UE_BUILD_SHIPPING
    return false;
#else
    if (Action == TEXT("play-card")) return false; // cards require genuine move/up, never a click submit
    if (!IsIsolatedNativeUiTest() || !FSlateApplication::IsInitialized()
        || LastPaintSerial == 0 || !IsInViewport() || GetVisibility() != ESlateVisibility::Visible) return false;
    const FHczsSessionControl* Match = Controls.FindByPredicate([&Action, &Value](const FHczsSessionControl& C)
        { return C.Action == Action && C.Value == Value && C.bEnabled; });
    if (!Match) return false;
    const FHczsSessionControl Control = *Match;
    FVector2f Point((Control.Rect.Left + Control.Rect.Right) * 0.5f,
        (Control.Rect.Top + Control.Rect.Bottom) * 0.5f);
    if (Control.bTransformed) Point = TransformPoint(Control.Transform, Point);
    const TSharedPtr<SWidget> SlateWidget = GetCachedWidget();
    if (!SlateWidget) return false;
    FSlateApplication& Slate = FSlateApplication::Get();
    const TSharedPtr<SWindow> Window = Slate.FindWidgetWindow(SlateWidget.ToSharedRef());
    if (!Window || Window->IsWindowMinimized()) return false;
    FWidgetPath DesktopPath;
    if (!Slate.GeneratePathToWidgetUnchecked(SlateWidget.ToSharedRef(), DesktopPath)) return false;
    const auto Arranged = DesktopPath.FindArrangedWidget(SlateWidget.ToSharedRef());
    if (!Arranged.IsSet()) return false;
    // NativePaint is window relative; routed pointer geometry is desktop relative.
    const FGeometry& DesktopGeometry = Arranged.GetValue().Geometry;
    const FVector2f Available(DesktopGeometry.GetLocalSize());
    const float Scale = FMath::Min(Available.X / DesignSize.X, Available.Y / DesignSize.Y);
    if (Scale <= 0) return false;
    const FVector2f Absolute = DesktopGeometry.LocalToAbsolute((Available - DesignSize * Scale) * 0.5f + Point * Scale);
    TArray<TSharedRef<SWindow>> Windows{Window.ToSharedRef()};
    FWidgetPath Path = Slate.LocateWindowUnderMouse(Absolute, Windows, false, 0);
    if (!Path.IsValid() || !Path.ContainsWidget(SlateWidget.Get())) return false;
    const uint64 Before = PointerEventSerial;
    bool bDownHandled = false;
    if (bTouch)
    {
        const FPointerEvent Down(0u, 7u, Absolute, Absolute, 1.0f, true);
        // This constructor is always a touch event; its boolean is pressed state.
        const FPointerEvent Up(0u, 7u, Absolute, Absolute, 0.0f, false);
        bDownHandled = Slate.RoutePointerDownEvent(Path, Down).IsEventHandled();
        Slate.RoutePointerUpEvent(Path, Up);
    }
    else
    {
        TSet<FKey> Buttons{EKeys::LeftMouseButton};
        const FPointerEvent Down(0u, Absolute, Absolute, Buttons, EKeys::LeftMouseButton, 0, FModifierKeysState());
        const FPointerEvent Up(0u, Absolute, Absolute, TSet<FKey>(), EKeys::LeftMouseButton, 0, FModifierKeysState());
        bDownHandled = Slate.RoutePointerDownEvent(Path, Down).IsEventHandled();
        Slate.RoutePointerUpEvent(Path, Up);
    }
    const bool Routed = PointerEventSerial > Before && LastPointerAction == Action
        && LastPointerValue == Value && bLastPointerTouch == bTouch;
    UE_LOG(LogTemp, Display, TEXT("HCZS UI pointer: input=%s action=%s nativeHit=%s map=%s design=(%.1f,%.1f) serial=%llu->%llu lastAction=%s lastValue=%s actualPoint=(%.1f,%.1f) absolute=(%.1f,%.1f) paintGeometry=(%.1f,%.1f) leaf=%s handled=%d windowMode=%d"),
        bTouch ? TEXT("touch") : TEXT("mouse"), *Action, Routed ? TEXT("true") : TEXT("false"),
        *LastPaintedMap, Point.X, Point.Y, Before, PointerEventSerial, *LastPointerAction, *LastPointerValue,
        LastPointerPoint.X, LastPointerPoint.Y, Absolute.X, Absolute.Y, Available.X, Available.Y,
        *Path.Widgets.Last().Widget->GetTypeAsString(), bDownHandled, static_cast<int32>(Window->GetWindowMode()));
    return Routed;
#endif
}

bool UHczsSessionWidget::DevelopmentDragCard(const FString& InstanceId, const FString& ReleaseTarget, bool bTouch, const FString& Phase)
{
#if UE_BUILD_SHIPPING
    return false;
#else
    if (!IsIsolatedNativeUiTest() || !FSlateApplication::IsInitialized() || !IsInViewport()
        || GetVisibility() != ESlateVisibility::Visible || LastPaintSerial == 0) return false;
    const auto Widget = GetCachedWidget();
    if (!Widget) return false;
    auto& Slate = FSlateApplication::Get();
    const auto Window = Slate.FindWidgetWindow(Widget.ToSharedRef());
    if (!Window || Window->IsWindowMinimized()) return false;
    const TArray<TSharedRef<SWindow>> Windows{Window.ToSharedRef()};
    FWidgetPath DesktopPath;
    if (!Slate.GeneratePathToWidgetUnchecked(Widget.ToSharedRef(), DesktopPath)) return false;
    const auto Arranged = DesktopPath.FindArrangedWidget(Widget.ToSharedRef());
    if (!Arranged.IsSet()) return false;
    const FGeometry& DesktopGeometry = Arranged.GetValue().Geometry;
    const FVector2f Available(DesktopGeometry.GetLocalSize());
    const float Scale = FMath::Min(Available.X / DesignSize.X, Available.Y / DesignSize.Y);
    if (Scale <= 0) return false;
    auto AbsolutePoint = [&](FVector2f Point) { return DesktopGeometry.LocalToAbsolute((Available - DesignSize * Scale) * 0.5f + Point * Scale); };
    if (Phase == TEXT("begin"))
    {
        if (bCardGestureActive || !CanDragCard(InstanceId)) return false;
        const auto* Match = Controls.FindByPredicate([&InstanceId](const FHczsSessionControl& C) { return C.Action == TEXT("play-card") && C.Value == InstanceId && C.bEnabled; });
        if (!Match) return false;
        FVector2f Start = FVector2f::ZeroVector;
        bool Found = false;
        for (float Y : {30.0f, 70.0f, 110.0f})
        {
            for (float X : {63.0f, 22.0f, 103.0f})
            {
                const FVector2f Point = TransformPoint(Match->Transform, FVector2f(X, Y));
                for (int32 Index = Controls.Num() - 1; Index >= 0; --Index)
                {
                    if (!Contains(Controls[Index], Point)) continue;
                    Found = Controls[Index].Action == TEXT("play-card") && Controls[Index].Value == InstanceId;
                    break;
                }
                if (Found) { Start = Point; break; }
            }
            if (Found) break;
        }
        if (!Found) return false;
        DevelopmentDragAbsolute = AbsolutePoint(Start);
        const auto Path = Slate.LocateWindowUnderMouse(DevelopmentDragAbsolute, Windows, false, 0);
        if (!Path.IsValid() || !Path.ContainsWidget(Widget.Get())) return false;
        if (bTouch) Slate.RoutePointerDownEvent(Path, FPointerEvent(0u, 7u, DevelopmentDragAbsolute, DevelopmentDragAbsolute, 1.0f, true));
        else Slate.RoutePointerDownEvent(Path, FPointerEvent(0u, DevelopmentDragAbsolute, DevelopmentDragAbsolute, TSet<FKey>{EKeys::LeftMouseButton}, EKeys::LeftMouseButton, 0, FModifierKeysState()));
        return bCardGestureActive && CardGestureInstance == InstanceId && bCardGestureTouch == bTouch;
    }
    if (CardGestureInstance != InstanceId || bCardGestureTouch != bTouch) return false;
    if (Phase == TEXT("move"))
    {
        if (!bCardGestureActive) return false;
        FVector2f End = CardGestureStart;
        if (ReleaseTarget == TEXT("outside")) End = FVector2f(DesignSize.X / 2, -35);
        else if (ReleaseTarget != TEXT("tap"))
        {
            FSlateRect Target(0, 0, 0, 0);
            if (!ProjectActorBounds(ReleaseTarget == TEXT("player") ? FName(TEXT("HCZSBattlePlayer")) : FName(TEXT("HCZSBattleEnemy")), Target)) return false;
            End = FVector2f((Target.Left + Target.Right) / 2, (Target.Top + Target.Bottom) / 2);
        }
        const FVector2D Next = AbsolutePoint(End);
        const auto Path = Slate.LocateWindowUnderMouse(Next, Windows, false, 0);
        const int32 Before = CardGestureEvents.Num();
        if (bTouch) Slate.RoutePointerMoveEvent(Path, FPointerEvent(0u, 7u, Next, DevelopmentDragAbsolute, 1.0f, true), false);
        else Slate.RoutePointerMoveEvent(Path, FPointerEvent(0u, Next, DevelopmentDragAbsolute, TSet<FKey>{EKeys::LeftMouseButton}, EKeys::Invalid, 0, FModifierKeysState()), false);
        DevelopmentDragAbsolute = Next;
        return CardGestureEvents.Num() > Before;
    }
    if (Phase == TEXT("focus-lost"))
    {
        if (!bCardGestureActive) return false;
        Slate.ClearAllUserFocus(EFocusCause::Cleared);
        return !bCardGestureActive && LastGestureOutcome == TEXT("cancelled") && LastGestureReason == TEXT("focus-lost");
    }
    if (Phase != TEXT("release")) return false;
    if (ReleaseTarget == TEXT("cancel"))
        if (const auto User = Slate.GetUser(CardGestureUser)) User->ReleaseCapture(static_cast<uint32>(CardGesturePointer)); // emits actual native capture loss
    const auto Path = Slate.LocateWindowUnderMouse(DevelopmentDragAbsolute, Windows, false, 0);
    if (bTouch) Slate.RoutePointerUpEvent(Path, FPointerEvent(0u, 7u, DevelopmentDragAbsolute, DevelopmentDragAbsolute, 0.0f, false));
    else Slate.RoutePointerUpEvent(Path, FPointerEvent(0u, DevelopmentDragAbsolute, DevelopmentDragAbsolute, TSet<FKey>(), EKeys::LeftMouseButton, 0, FModifierKeysState()));
    return !bCardGestureActive && LastGestureOutcome != TEXT("tracking");
#endif
}

FString UHczsSessionWidget::DevelopmentDescribeUI() const
{
#if UE_BUILD_SHIPPING
    return TEXT("{}");
#else
    if (!IsIsolatedNativeUiTest()) return TEXT("{}");
    auto Root = MakeShared<FJsonObject>();
    Root->SetStringField(TEXT("mode"), TEXT("actual-nativepaint-and-slate-pointer-observation"));
    Root->SetStringField(TEXT("map"), LastPaintedMap);
    Root->SetNumberField(TEXT("paintSerial"), static_cast<double>(LastPaintSerial));
    Root->SetBoolField(TEXT("battleScene"), bBattleScene);
    Root->SetNumberField(TEXT("openingSeconds"), LastOpeningSeconds);
    Root->SetNumberField(TEXT("openingPaintedNodes"), LastOpeningNodes.Num());
    Root->SetBoolField(TEXT("openingTimelineValid"), EliteOpening.bValid);
    Root->SetArrayField(TEXT("dealtCards"), LastDealtCards);
    if (LastHudIn) Root->SetObjectField(TEXT("hudIn"), LastHudIn);
    {
        auto Deal = MakeShared<FJsonObject>();
        Deal->SetBoolField(TEXT("active"), IsRoundDealActive());
        Deal->SetStringField(TEXT("outcome"), LastRoundDealOutcome);
        Deal->SetStringField(TEXT("handledReceipt"), HandledDealReceipt);
        Deal->SetNumberField(TEXT("actionIndex"), RoundDeal.ActionIndex);
        Deal->SetNumberField(TEXT("round"), RoundDeal.Round);
        Deal->SetNumberField(TEXT("elapsed"), RoundDealElapsed());
        Deal->SetNumberField(TEXT("dispatchSeconds"), HczsCardDeal::DispatchSeconds(RoundDeal.Instances.Num()));
        TArray<TSharedPtr<FJsonValue>> Instances;
        for (const FString& Id : RoundDeal.Instances) Instances.Add(MakeShared<FJsonValueString>(Id));
        Deal->SetArrayField(TEXT("instances"), Instances);
        Root->SetObjectField(TEXT("roundDeal"), Deal);
        Root->SetArrayField(TEXT("uiAudio"), UiAudioLog);
    }
    Root->SetNumberField(TEXT("sourceOwnCardOriginY"), 720);
    Root->SetStringField(TEXT("dealClockPolicy"), TEXT("local-BattleBegin3s-plus-original-first-delay0.5s"));
    Root->SetBoolField(TEXT("originalCardPerspectiveRecovered"), false);
    Root->SetBoolField(TEXT("dragPreviewPainted"), bLastPaintedDragCue);
    Root->SetBoolField(TEXT("sourceArrowResourcesReady"), Brushes.Contains(TEXT("target-arrow-ribbon")) && Brushes.Contains(TEXT("target-arrow-head")));
    Root->SetStringField(TEXT("sourceArrowGeometry"), TEXT("apk-native-parabolic-60x2"));
    Root->SetBoolField(TEXT("originalArrowRuntimeEquivalent"), false);
    Root->SetBoolField(TEXT("presentationBusy"), bPresentationBusy);
    Root->SetStringField(TEXT("sceneProblem"), SceneProblem);
    Root->SetBoolField(TEXT("visible"), GetVisibility() == ESlateVisibility::Visible);
    Root->SetBoolField(TEXT("sourceChineseFont"), CompositeFont.IsValid());
    Root->SetBoolField(TEXT("hdIconVariant"), IconVariant != nullptr);
    Root->SetNumberField(TEXT("hdIconsWithOriginalFootprint"), IconDrawAdjustments.Num());
    Root->SetStringField(TEXT("lastPointerAction"), LastPointerAction);
    Root->SetStringField(TEXT("lastPointerValue"), LastPointerValue);
    Root->SetBoolField(TEXT("lastPointerTouch"), bLastPointerTouch);
    Root->SetNumberField(TEXT("pointerEventSerial"), static_cast<double>(PointerEventSerial));
    TArray<TSharedPtr<FJsonValue>> Texts;
    for (const FString& Text : LastPaintedTexts) Texts.Add(MakeShared<FJsonValueString>(Text));
    Root->SetArrayField(TEXT("renderedTexts"), Texts);
    TArray<FString> SortedSprites = LastPaintedSprites.Array();
    SortedSprites.Sort();
    TArray<TSharedPtr<FJsonValue>> Painted;
    for (const FString& Key : SortedSprites) Painted.Add(MakeShared<FJsonValueString>(Key));
    Root->SetArrayField(TEXT("actualPaintedSprites"), Painted);
    TArray<TSharedPtr<FJsonValue>> Hitboxes;
    for (const auto& Control : Controls)
    {
        auto Row = MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("action"), Control.Action);
        Row->SetStringField(TEXT("value"), Control.Value);
        Row->SetBoolField(TEXT("enabled"), Control.bEnabled);
        Row->SetBoolField(TEXT("transformed"), Control.bTransformed);
        TArray<TSharedPtr<FJsonValue>> Bounds;
        for (float N : {Control.Rect.Left, Control.Rect.Top, Control.Rect.Right, Control.Rect.Bottom})
            Bounds.Add(MakeShared<FJsonValueNumber>(N));
        Row->SetArrayField(TEXT("rect"), Bounds);
        Hitboxes.Add(MakeShared<FJsonValueObject>(Row));
    }
    Root->SetArrayField(TEXT("controls"), Hitboxes);
    auto Assets = MakeShared<FJsonObject>();
    for (const auto& Pair : Brushes)
        if (const UObject* Resource = Pair.Value.GetResourceObject()) Assets->SetStringField(Pair.Key, Resource->GetPathName());
    Root->SetObjectField(TEXT("paintResources"), Assets);
    auto Gesture = MakeShared<FJsonObject>();
    Gesture->SetNumberField(TEXT("serial"), static_cast<double>(CardGestureSerial));
    Gesture->SetStringField(TEXT("cardInstanceId"), CardGestureInstance);
    Gesture->SetStringField(TEXT("cardId"), CardGestureCardId);
    Gesture->SetStringField(TEXT("battleId"), CardGestureBattle);
    Gesture->SetNumberField(TEXT("startRevision"), static_cast<double>(CardGestureRevision));
    Gesture->SetBoolField(TEXT("isTouch"), bCardGestureTouch);
    Gesture->SetNumberField(TEXT("pointerIndex"), CardGesturePointer);
    Gesture->SetNumberField(TEXT("threshold"), CardGestureThreshold);
    Gesture->SetBoolField(TEXT("active"), bCardGestureActive);
    Gesture->SetBoolField(TEXT("lostCapture"), bLastGestureLostCapture);
    Gesture->SetStringField(TEXT("outcome"), LastGestureOutcome);
    Gesture->SetStringField(TEXT("reason"), LastGestureReason);
    Gesture->SetStringField(TEXT("targetId"), LastGestureTarget);
    auto TargetProjection = MakeShared<FJsonObject>();
    TargetProjection->SetStringField(TEXT("actorTag"), TEXT("HCZSBattleEnemy"));
    TargetProjection->SetStringField(TEXT("actorId"), Session ? Session->CurrentBattle.EnemyId : FString());
    TargetProjection->SetStringField(TEXT("source"), TEXT("native-bounds-eight-corners"));
    TargetProjection->SetBoolField(TEXT("valid"), bLastGestureTargetBoundsValid);
    TArray<TSharedPtr<FJsonValue>> TargetBounds;
    for (float N : {LastGestureTargetBounds.Left, LastGestureTargetBounds.Top, LastGestureTargetBounds.Right, LastGestureTargetBounds.Bottom}) TargetBounds.Add(MakeShared<FJsonValueNumber>(N));
    TargetProjection->SetArrayField(TEXT("bounds"), TargetBounds);
    if (GetWorld()) for (TActorIterator<AActor> It(GetWorld()); It; ++It)
        if (It->ActorHasTag(TEXT("HCZSBattleEnemy")))
            if (const auto* Mesh = It->FindComponentByClass<USkeletalMeshComponent>())
                if (Mesh->GetSkeletalMeshAsset()) TargetProjection->SetStringField(TEXT("mesh"), Mesh->GetSkeletalMeshAsset()->GetPathName());
    Gesture->SetObjectField(TEXT("targetProjection"), TargetProjection);
    TArray<TSharedPtr<FJsonValue>> GestureEvents;
    for (const auto& Event : CardGestureEvents)
    {
        auto Row = MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("kind"), Event.Kind); Row->SetBoolField(TEXT("targetHit"), Event.bTargetHit);
        Row->SetNumberField(TEXT("upwardDelta"), Event.UpwardDelta); Row->SetNumberField(TEXT("atUnixMs"), static_cast<double>(Event.AtUnixMs));
        Row->SetArrayField(TEXT("point"), {MakeShared<FJsonValueNumber>(Event.Point.X), MakeShared<FJsonValueNumber>(Event.Point.Y)});
        GestureEvents.Add(MakeShared<FJsonValueObject>(Row));
    }
    Gesture->SetArrayField(TEXT("events"), GestureEvents);
    Root->SetObjectField(TEXT("lastGesture"), Gesture);
    if (Session)
    {
        Root->SetNumberField(TEXT("phase"), static_cast<int32>(Session->Phase));
        Root->SetStringField(TEXT("profileId"), Session->SelectedProfileId);
        Root->SetStringField(TEXT("battleId"), Session->CurrentBattle.Id);
        Root->SetStringField(TEXT("playerId"), Session->CurrentBattle.PlayerId);
        Root->SetStringField(TEXT("enemyId"), Session->CurrentBattle.EnemyId);
        Root->SetStringField(TEXT("selectedEncounterId"), Session->SelectedEncounterId);
        Root->SetNumberField(TEXT("revision"), static_cast<double>(Session->CurrentBattle.Revision));
        Root->SetNumberField(TEXT("actionIndex"), static_cast<double>(Session->CurrentBattle.ActionIndex));
        Root->SetNumberField(TEXT("handCount"), Session->CurrentBattle.Hand.Num());
        Root->SetStringField(TEXT("serverPlayerHp"), Session->CurrentBattle.PlayerHp.Decimal);
        Root->SetStringField(TEXT("serverEnemyHp"), Session->CurrentBattle.EnemyHp.Decimal);
        Root->SetStringField(TEXT("serverStatus"), Session->CurrentBattle.Status);
        Root->SetStringField(TEXT("encounterId"), Session->CurrentBattle.EncounterId);
        Root->SetNumberField(TEXT("round"), Session->CurrentBattle.Round);
        Root->SetNumberField(TEXT("energy"), Session->CurrentBattle.Energy);
        Root->SetBoolField(TEXT("party"), Session->CurrentBattle.bIsParty);
        Root->SetNumberField(TEXT("enemyAttackBuff"), Session->CurrentBattle.EnemyAttackBuff);
        Root->SetStringField(TEXT("enemyIntentText"), Session->CurrentBattle.EnemyIntentText);
        TArray<TSharedPtr<FJsonValue>> Members, HandRows;
        for (const auto& Member : Session->CurrentBattle.Party)
        {
            auto Row = MakeShared<FJsonObject>(); Row->SetStringField(TEXT("id"), Member.Id); Row->SetStringField(TEXT("hp"), Member.Hp.Decimal);
            Row->SetStringField(TEXT("shield"), Member.Shield.Decimal); Row->SetNumberField(TEXT("attackBuff"), Member.AttackBuff);
            Members.Add(MakeShared<FJsonValueObject>(Row));
        }
        for (const auto& Card : Session->CurrentBattle.Hand)
        {
            auto Row = MakeShared<FJsonObject>(); Row->SetStringField(TEXT("instanceId"), Card.InstanceId); Row->SetStringField(TEXT("cardId"), Card.CardId);
            Row->SetNumberField(TEXT("cost"), Card.Cost); Row->SetStringField(TEXT("ownerId"), Card.OwnerId);
            Row->SetStringField(TEXT("effects"), Card.EffectsText); Row->SetStringField(TEXT("firstDamage"), Card.FirstDamage);
            Row->SetStringField(TEXT("totalDamage"), Card.TotalDamage);
            HandRows.Add(MakeShared<FJsonValueObject>(Row));
        }
        Root->SetArrayField(TEXT("partyMembers"), Members);
        Root->SetArrayField(TEXT("hand"), HandRows);
        auto GuideRow = MakeShared<FJsonObject>();
        const FHczsGuideStep* GuideStep = Guide.Current();
        GuideRow->SetNumberField(TEXT("stepId"), GuideStep ? GuideStep->Id : -1);
        GuideRow->SetBoolField(TEXT("shown"), bGuideShown);
        GuideRow->SetStringField(TEXT("advance"), !GuideStep ? TEXT("") : GuideStep->Advance == EHczsGuideAdvance::Tap ? TEXT("tap")
            : GuideStep->Advance == EHczsGuideAdvance::PlayCard ? TEXT("play-card") : TEXT("end-turn"));
        GuideRow->SetBoolField(TEXT("complete"), Guide.bComplete);
        GuideRow->SetStringField(TEXT("battleId"), Guide.BattleId);
        Root->SetObjectField(TEXT("guide"), GuideRow);
        Root->SetBoolField(TEXT("pending"), Session->bRequestInFlight || Session->bHasPendingIntent);
        Root->SetBoolField(TEXT("profileStateCurrent"), Session->bProfileStateCurrent);
        Root->SetBoolField(TEXT("battleStateCurrent"), Session->bBattleStateCurrent);
        auto Mainline = MakeShared<FJsonObject>();
        Mainline->SetBoolField(TEXT("enabled"), Session->bHasMainlineProgression);
        Mainline->SetBoolField(TEXT("current"), Session->bMainlineStateCurrent);
        Mainline->SetBoolField(TEXT("canConfirm"), Session->CanConfirmMainlineVictory() && !bPresentationBusy);
        Mainline->SetStringField(TEXT("profileId"), Session->MainlineProgress.ProfileId);
        Mainline->SetStringField(TEXT("contentId"), Session->MainlineProgress.ContentId);
        Mainline->SetNumberField(TEXT("revision"), static_cast<double>(Session->MainlineProgress.Revision));
        Mainline->SetBoolField(TEXT("firstChallengePassed"), Session->MainlineProgress.bFirstChallengePassed);
        Mainline->SetBoolField(TEXT("bossChallengePassed"), Session->MainlineProgress.bBossChallengePassed);
        Mainline->SetStringField(TEXT("completedBattleId"), Session->MainlineProgress.CompletedBattleId);
        TArray<TSharedPtr<FJsonValue>> Challenges;
        for (const auto& Challenge : Session->MainlineProgress.Challenges)
        {
            auto Row = MakeShared<FJsonObject>(); Row->SetNumberField(TEXT("id"), Challenge.Id);
            Row->SetStringField(TEXT("status"), Challenge.Status); Row->SetBoolField(TEXT("executable"), Challenge.bExecutable);
            Row->SetBoolField(TEXT("recordPresent"), Challenge.bRecordPresent);
            if (Challenge.bRecordPresent) Row->SetNumberField(TEXT("successTime"), Challenge.SuccessTime);
            else Row->SetField(TEXT("successTime"), MakeShared<FJsonValueNull>());
            Challenges.Add(MakeShared<FJsonValueObject>(Row));
        }
        Mainline->SetArrayField(TEXT("challenges"), Challenges); Root->SetObjectField(TEXT("mainline"), Mainline);
    }
    FString Result;
    FJsonSerializer::Serialize(Root, TJsonWriterFactory<>::Create(&Result));
    return Result;
#endif
}

FReply UHczsSessionWidget::NativeOnMouseMove(const FGeometry& Geometry, const FPointerEvent& Event)
{
    if (bCardGestureActive) { MoveCardGesture(Geometry, Event); return FReply::Handled(); }
    const FVector2f Point = DesignPoint(Geometry, Event.GetScreenSpacePosition());
    FString Next;
    for (int32 Index = Controls.Num() - 1; Index >= 0; --Index)
    {
        if (Controls[Index].Action == TEXT("play-card") && Contains(Controls[Index], Point))
        {
            Next = Controls[Index].Value;
            break;
        }
    }
    if (Next != HoveredCard) { HoveredCard = Next; InvalidateLayoutAndVolatility(); }
    return FReply::Handled();
}

FReply UHczsSessionWidget::NativeOnKeyDown(const FGeometry& Geometry, const FKeyEvent& Event)
{
    if (Event.GetKey() == EKeys::Escape)
    {
        CancelCardGesture(TEXT("escape")); SelectedCardInstance.Reset(); bCardDetailOpen = false;
        CloseSelection();
        return FReply::Handled();
    }
    return Super::NativeOnKeyDown(Geometry, Event);
}

bool UHczsSessionWidget::DevelopmentPressControl(const FString& Action)
{
#if UE_BUILD_SHIPPING
    return false;
#else
    if (!FParse::Param(FCommandLine::Get(), TEXT("HczsMainlineUITest")) || !IsInViewport()) return false;
    const FHczsSessionControl* Control = Controls.FindByPredicate([&Action](const FHczsSessionControl& C) { return C.Action == Action && C.bEnabled; });
    if (!Control) return false;
    const FHczsSessionControl Copy = *Control;
    DispatchControl(Copy);
    return true;
#endif
}

void UHczsSessionWidget::DispatchControl(const FHczsSessionControl& Control)
{
    if (!Session) return;
    const FString& Action = Control.Action;
    if (Action == TEXT("retry-intent")) { Session->RetryPendingIntent(); return; }
    if (Session->bRequestInFlight || Session->bHasPendingIntent || bPresentationBusy) return;
    if (Action == TEXT("select-profile")) Session->SelectProfile(Control.Value);
    else if (Action == TEXT("confirm-new-profile")) { bConfirmNewProfile = true; InvalidateLayoutAndVolatility(); }
    else if (Action == TEXT("cancel-new-profile")) { bConfirmNewProfile = false; InvalidateLayoutAndVolatility(); }
    else if (Action == TEXT("create-profile")) Session->CreateLocalProfile(TEXT("本地旅人"));
    else if (Action == TEXT("select-encounter")) Session->SelectEncounter(Control.Value);
    else if (Action == TEXT("new-battle")) Session->CreateSelectedBattle();
    else if (Action == TEXT("continue-battle") || Action == TEXT("inspect-battle")) Session->ContinueBattle(Control.Value);
    else if (Action == TEXT("end-turn")) Session->EndTurn();
    else if (Action == TEXT("refresh-bootstrap")) Session->RefreshBootstrap();
    else if (Action == TEXT("refresh-battle") && Session->CurrentBattle.bIsValid) Session->RefreshCurrentBattle();
    else if (Action == TEXT("settle-mainline")) Session->ConfirmMainlineVictory();
    else if (Action == TEXT("refresh-mainline")) Session->RefreshMainline();
    else if (Action == TEXT("close-selection")) CloseSelection();
    else if (Action == TEXT("hall")) Session->ReturnToHall();
    else if (Action == TEXT("challenge-again"))
    {
        RequestedChallengeEncounter = Session->CurrentBattle.EncounterId;
        bChallengeAfterScenario = true;
        Session->SelectEncounter(RequestedChallengeEncounter);
    }
    else if (Action == TEXT("profile-page"))
    {
        ProfilePage = (ProfilePage + 1) % FMath::Max(1, (Session->Profiles.Num() + 3) / 4);
        InvalidateLayoutAndVolatility();
    }
    else if (Action == TEXT("battle-page"))
    {
        BattlePage = (BattlePage + 1) % FMath::Max(1, (Session->Battles.Num() + 3) / 4);
        InvalidateLayoutAndVolatility();
    }
}
