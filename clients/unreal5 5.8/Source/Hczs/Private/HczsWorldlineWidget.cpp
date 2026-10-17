#include "HczsWorldlineWidget.h"
#include "HczsGameInstance.h"
#include "Engine/Texture2D.h"
#include "Engine/FontFace.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Rendering/DrawElementTypes.h"
#include "Framework/Application/SlateApplication.h"
#include "Fonts/FontMeasure.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/CoreStyle.h"
#include "InputCoreTypes.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Layout/WidgetPath.h"
#include "Widgets/SWindow.h"

namespace
{
const FVector2f DesignSize(1280, 720);
bool ReadNumbers(const TSharedPtr<FJsonObject>& Object, const TCHAR* Field, int32 Count, TArray<double>& Result)
{
    const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
    if (!Object || !Object->TryGetArrayField(Field, Values) || Values->Num() != Count) return false;
    for (const auto& Value : *Values)
    {
        double Number = 0;
        if (!Value->TryGetNumber(Number) || !FMath::IsFinite(Number)) return false;
        Result.Add(Number);
    }
    return true;
}
FLinearColor ReadColor(const TSharedPtr<FJsonObject>& Object, const TCHAR* Field)
{
    TArray<double> Values;
    if (!ReadNumbers(Object, Field, 4, Values)) return FLinearColor::White;
    return FLinearColor(Values[0], Values[1], Values[2], Values[3]);
}
bool ReadGeometry(const TSharedPtr<FJsonObject>& Object, FVector2f& Size, FSlateRenderTransform& Transform)
{
    TArray<double> Sizes, Matrix;
    const TSharedPtr<FJsonObject>* Geometry = nullptr;
    if (!ReadNumbers(Object, TEXT("size"), 2, Sizes) || !Object->TryGetObjectField(TEXT("geometry"), Geometry)
        || !ReadNumbers(*Geometry, TEXT("matrix"), 6, Matrix) || Sizes[0] < 0 || Sizes[1] < 0) return false;
    Size = FVector2f(Sizes[0], Sizes[1]);
    Transform = FSlateRenderTransform(FMatrix2x2(Matrix[0], Matrix[1], Matrix[2], Matrix[3]), FVector2f(Matrix[4], Matrix[5]));
    return true;
}
}

void UHczsWorldlineWidget::SetSourceInspection(bool bInspect)
{
#if !UE_BUILD_SHIPPING
    bSourceInspection = bInspect && FParse::Param(FCommandLine::Get(), TEXT("HczsWorldlineInspect"));
#else
    bSourceInspection = false;
#endif
}

void UHczsWorldlineWidget::NativeConstruct()
{
    Super::NativeConstruct();
    SetIsFocusable(true);
    SetVisibility(ESlateVisibility::Visible);
    Items.Reset(); ItemSpriteIds.Reset(); SourceControls.Reset();
    bSourceReady = bSourceFontReady = false;
    AdapterFont = FCoreStyle::GetDefaultFontStyle(TEXT("Regular"), 18);
    Layout = LoadObject<UHczsHallLayoutAsset>(nullptr, TEXT("/Game/Recovered/Worldline/UI/WorldlineLayout.WorldlineLayout"));
    if (!Layout) return;
    TSharedPtr<FJsonObject> Root;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Layout->LayoutJson), Root) || !Root) return;
    const TSharedPtr<FJsonObject>* Progress = nullptr;
    bool bHasProgress = true;
    double Instances = -1;
    if (!Root->TryGetObjectField(TEXT("progressBinding"), Progress)
        || !(*Progress)->TryGetBoolField(TEXT("available"), bHasProgress)
        || !(*Progress)->TryGetNumberField(TEXT("chapterInstances"), Instances) || bHasProgress || Instances != 0) return;
    TMap<FString, TSharedPtr<const FCompositeFont>> Fonts;
    for (const auto& Pair : Layout->Fonts)
    {
        if (!Pair.Value) continue;
        TSharedPtr<FCompositeFont> Composite = MakeShared<FCompositeFont>();
        FTypefaceEntry Entry;
        Entry.Name = TEXT("Regular");
        Entry.Font = FFontData(Pair.Value);
        Composite->DefaultTypeface.Fonts.Add(Entry);
        Fonts.Add(Pair.Key, Composite);
        if (!bSourceFontReady)
        {
            AdapterFont = FSlateFontInfo(Composite, 21.0f * 72.0f / FontConstants::RenderDPI, TEXT("Regular"));
            bSourceFontReady = true;
        }
    }
    const TArray<TSharedPtr<FJsonValue>>* DrawItems = nullptr;
    if (!Root->TryGetArrayField(TEXT("items"), DrawItems) || DrawItems->Num() > 256) return;
    for (const auto& Value : *DrawItems)
    {
        const auto Object = Value->AsObject();
        FString Kind;
        FHczsHallDrawItem Item;
        if (!Object || !Object->TryGetStringField(TEXT("kind"), Kind) || !ReadGeometry(Object, Item.Size, Item.Transform)) return;
        Item.bText = Kind == TEXT("text");
        FString SpriteId;
        Item.Color = ReadColor(Object, TEXT("color"));
        double Opacity = 1;
        Object->TryGetNumberField(TEXT("opacity"), Opacity);
        Item.Color.A *= FMath::Clamp(Opacity, 0.0, 1.0);
        if (Item.bText)
        {
            FString FontId;
            double FontSize = 0, Horizontal = 0, Vertical = 0;
            if (!Object->TryGetStringField(TEXT("fontId"), FontId) || !Fonts.Contains(FontId)
                || !Object->TryGetStringField(TEXT("text"), Item.Text)
                || !Object->TryGetNumberField(TEXT("fontSize"), FontSize) || FontSize <= 0 || FontSize > 256) return;
            FFontOutlineSettings Outline;
            bool bOutline = false;
            Object->TryGetBoolField(TEXT("outlineEnabled"), bOutline);
            if (bOutline)
            {
                double Width = 0;
                Object->TryGetNumberField(TEXT("outlineSize"), Width);
                Outline.OutlineSize = FMath::Clamp(static_cast<int32>(Width), 0, 16);
                Outline.OutlineColor = ReadColor(Object, TEXT("outlineColor"));
            }
            Item.Font = FSlateFontInfo(Fonts[FontId], FontSize * 72.0f / FontConstants::RenderDPI, TEXT("Regular"), Outline);
            Object->TryGetNumberField(TEXT("horizontalAlignment"), Horizontal);
            Object->TryGetNumberField(TEXT("verticalAlignment"), Vertical);
            Item.HorizontalAlignment = static_cast<int32>(Horizontal);
            Item.VerticalAlignment = static_cast<int32>(Vertical);
            Object->TryGetBoolField(TEXT("shadowEnabled"), Item.bShadow);
            TArray<double> Shadow;
            if (ReadNumbers(Object, TEXT("shadowOffset"), 2, Shadow)) Item.ShadowOffset = FVector2f(Shadow[0], -Shadow[1]);
            Item.ShadowColor = ReadColor(Object, TEXT("shadowColor"));
        }
        else if (Kind == TEXT("sprite"))
        {
            if (!Object->TryGetStringField(TEXT("spriteId"), SpriteId) || !Layout->Sprites.Contains(SpriteId)
                || !Layout->Sprites[SpriteId]) return;
            Item.Brush.SetResourceObject(Layout->Sprites[SpriteId]);
            Item.Brush.ImageSize = Item.Size;
            Item.Brush.DrawAs = ESlateBrushDrawType::Image;
            bool FlipX = false, FlipY = false;
            Object->TryGetBoolField(TEXT("flipX"), FlipX); Object->TryGetBoolField(TEXT("flipY"), FlipY);
            Item.Brush.Mirroring = FlipX && FlipY ? ESlateBrushMirrorType::Both : FlipX ? ESlateBrushMirrorType::Horizontal : FlipY ? ESlateBrushMirrorType::Vertical : ESlateBrushMirrorType::NoMirror;
        }
        else return;
        const TArray<TSharedPtr<FJsonValue>>* Clips = nullptr;
        if (Object->TryGetArrayField(TEXT("clipGeometry"), Clips))
        {
            for (const auto& ClipValue : *Clips)
            {
                const auto Clip = ClipValue->AsObject();
                const TArray<TSharedPtr<FJsonValue>>* Corners = nullptr;
                if (!Clip || !Clip->TryGetArrayField(TEXT("corners"), Corners) || Corners->Num() != 4) return;
                TArray<FVector2f> Points;
                for (const auto& Corner : *Corners)
                {
                    const auto& XY = Corner->AsArray();
                    if (XY.Num() != 2) return;
                    Points.Add(FVector2f(XY[0]->AsNumber(), XY[1]->AsNumber()));
                }
                Item.Clips.Add(FSlateClippingZone(Points[0], Points[1], Points[3], Points[2]));
            }
        }
        Items.Add(Item); ItemSpriteIds.Add(SpriteId);
    }
    const TArray<TSharedPtr<FJsonValue>>* Controls = nullptr;
    if (!Root->TryGetArrayField(TEXT("controls"), Controls) || Controls->Num() > 8) return;
    for (const auto& Value : *Controls)
    {
        const auto Object = Value->AsObject();
        FHczsWorldlineSourceControl Control;
        if (!Object || !Object->TryGetStringField(TEXT("action"), Control.Action)
            || !ReadGeometry(Object, Control.Size, Control.Transform)) return;
        Object->TryGetBoolField(TEXT("enabled"), Control.bEnabled);
        SourceControls.Add(Control);
    }
    bSourceReady = bSourceFontReady && Items.Num() > 0;
    UE_LOG(LogTemp, Display, TEXT("HCZS original worldline static page ready=%s drawItems=%d chapterInstances=0"), bSourceReady ? TEXT("true") : TEXT("false"), Items.Num());
}

int32 UHczsWorldlineWidget::NativePaint(const FPaintArgs& Args, const FGeometry& Geometry,
    const FSlateRect& CullingRect, FSlateWindowElementList& Elements, int32 LayerId,
    const FWidgetStyle& Style, bool bParentEnabled) const
{
    int32 Layer = Super::NativePaint(Args, Geometry, CullingRect, Elements, LayerId, Style, bParentEnabled);
    ++PaintSerial; LastPaintedTexts.Reset(); LastPaintedSpriteIds.Reset(); LastPaintedControls.Reset();
    LastPaintGeometry = Geometry;
    LastPaintedMap = UGameplayStatics::GetCurrentLevelName(this, true);
    const FVector2f Available(Geometry.GetLocalSize());
    const float Scale = FMath::Min(Available.X / DesignSize.X, Available.Y / DesignSize.Y);
    if (Scale <= 0) return Layer;
    const FVector2f Offset = (Available - DesignSize * Scale) * 0.5f;
    const FGeometry Canvas = Geometry.MakeChild(DesignSize, FSlateLayoutTransform(Scale, Offset));
    FSlateDrawElement::MakeBox(Elements, ++Layer, Geometry.ToPaintGeometry(), FCoreStyle::Get().GetBrush(TEXT("WhiteBrush")), ESlateDrawEffect::None, FLinearColor::Black);
    if (bSourceReady)
    {
        for (int32 Index = 0; Index < Items.Num(); ++Index)
        {
            const auto& Item = Items[Index];
            for (const auto& Clip : Item.Clips)
                Elements.PushClip(FSlateClippingZone(Geometry.LocalToAbsolute(Offset + Clip.TopLeft * Scale),
                    Geometry.LocalToAbsolute(Offset + Clip.TopRight * Scale), Geometry.LocalToAbsolute(Offset + Clip.BottomLeft * Scale), Geometry.LocalToAbsolute(Offset + Clip.BottomRight * Scale)));
            const FGeometry ItemGeometry = Geometry.MakeChild(Item.Size, FSlateLayoutTransform(Scale, Offset), Item.Transform, FVector2f::ZeroVector);
            if (!Item.bText)
            {
                FSlateDrawElement::MakeBox(Elements, ++Layer, ItemGeometry.ToPaintGeometry(), &Item.Brush, ESlateDrawEffect::None, Item.Color);
                LastPaintedSpriteIds.Add(ItemSpriteIds[Index]);
            }
            else
            {
                const FVector2f TextSize(FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(Item.Text, Item.Font));
                FVector2f TextOffset = FVector2f::ZeroVector;
                if (Item.HorizontalAlignment == 1) TextOffset.X = (Item.Size.X - TextSize.X) / 2;
                else if (Item.HorizontalAlignment == 2) TextOffset.X = Item.Size.X - TextSize.X;
                if (Item.VerticalAlignment == 1) TextOffset.Y = (Item.Size.Y - TextSize.Y) / 2;
                else if (Item.VerticalAlignment == 2) TextOffset.Y = Item.Size.Y - TextSize.Y;
                if (Item.bShadow)
                    FSlateDrawElement::MakeText(Elements, ++Layer, ItemGeometry.MakeChild(TextSize, FSlateLayoutTransform(TextOffset + Item.ShadowOffset)).ToPaintGeometry(), Item.Text, Item.Font, ESlateDrawEffect::None, Item.ShadowColor);
                FSlateDrawElement::MakeText(Elements, ++Layer, ItemGeometry.MakeChild(TextSize, FSlateLayoutTransform(TextOffset)).ToPaintGeometry(), Item.Text, Item.Font, ESlateDrawEffect::None, Item.Color);
                LastPaintedTexts.Add(Item.Text);
            }
            for (int32 ClipIndex = 0; ClipIndex < Item.Clips.Num(); ++ClipIndex) Elements.PopClip();
        }
    }
    auto Text = [&](const FString& Label, const FVector2f& Center, FLinearColor Color)
    {
        const FVector2f TextSize(FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(Label, AdapterFont));
        FSlateDrawElement::MakeText(Elements, ++Layer, Canvas.MakeChild(TextSize, FSlateLayoutTransform(Center - TextSize / 2)).ToPaintGeometry(), Label, AdapterFont, ESlateDrawEffect::None, Color);
        LastPaintedTexts.Add(Label);
    };
    Text(bSourceReady ? TEXT("章节进度暂不可用") : TEXT("世界线资源尚未导入"), FVector2f(640, 348),
        bSourceReady ? FLinearColor(0.24f, 0.22f, 0.34f, 1) : FLinearColor(0.89f, 0.91f, 1.0f, 1));
    if (!Notice.IsEmpty()) Text(Notice, FVector2f(640, 390), FLinearColor(0.34f, 0.28f, 0.42f, 1));
    const UHczsGameInstance* Session = Cast<UHczsGameInstance>(GetGameInstance());
    const bool bBusy = bSourceInspection || !Session || Session->bRequestInFlight || Session->bHasPendingIntent;
    const FGeometry Prologue = Canvas.MakeChild(FVector2f(PrologueRect.GetSize()), FSlateLayoutTransform(FVector2f(PrologueRect.Left, PrologueRect.Top)));
    FSlateDrawElement::MakeBox(Elements, ++Layer, Prologue.ToPaintGeometry(), FCoreStyle::Get().GetBrush(TEXT("WhiteBrush")), ESlateDrawEffect::None,
        FLinearColor(0.90f, 0.91f, 1.0f, bBusy ? 0.35f : 0.90f));
    Text(TEXT("序章"), FVector2f((PrologueRect.Left + PrologueRect.Right) / 2, (PrologueRect.Top + PrologueRect.Bottom) / 2), FLinearColor(0.23f, 0.21f, 0.36f, bBusy ? 0.45f : 1));
    const FGeometry LocalPreview = Canvas.MakeChild(FVector2f(LocalPreviewRect.GetSize()), FSlateLayoutTransform(FVector2f(LocalPreviewRect.Left, LocalPreviewRect.Top)));
    FSlateDrawElement::MakeBox(Elements, ++Layer, LocalPreview.ToPaintGeometry(), FCoreStyle::Get().GetBrush(TEXT("WhiteBrush")), ESlateDrawEffect::None,
        FLinearColor(0.90f, 0.91f, 1.0f, bBusy ? 0.35f : 0.90f));
    Text(TEXT("本地战斗预览"), FVector2f((LocalPreviewRect.Left + LocalPreviewRect.Right) / 2, (LocalPreviewRect.Top + LocalPreviewRect.Bottom) / 2), FLinearColor(0.23f, 0.21f, 0.36f, bBusy ? 0.45f : 1));
    for (const auto& SourceControl : SourceControls)
    {
        auto Control = SourceControl;
        Control.bEnabled = Control.bEnabled && (bSourceInspection || !bBusy);
        LastPaintedControls.Add(Control);
    }
    FHczsWorldlineSourceControl PreviewControl;
    PreviewControl.Action = TEXT("local-battle-preview");
    PreviewControl.Size = FVector2f(LocalPreviewRect.GetSize());
    PreviewControl.Transform = FSlateRenderTransform(FVector2f(LocalPreviewRect.Left, LocalPreviewRect.Top));
    PreviewControl.bEnabled = !bBusy;
    LastPaintedControls.Add(PreviewControl);
    FHczsWorldlineSourceControl PrologueControl;
    PrologueControl.Action = TEXT("prologue-dungeon");
    PrologueControl.Size = FVector2f(PrologueRect.GetSize());
    PrologueControl.Transform = FSlateRenderTransform(FVector2f(PrologueRect.Left, PrologueRect.Top));
    PrologueControl.bEnabled = !bBusy;
    LastPaintedControls.Add(PrologueControl);
    return Layer;
}

FReply UHczsWorldlineWidget::PressAt(const FGeometry& Geometry, const FVector2D& AbsolutePosition, bool bTouch)
{
    const UHczsGameInstance* Session = Cast<UHczsGameInstance>(GetGameInstance());
    if (!bSourceInspection && (!Session || Session->bRequestInFlight || Session->bHasPendingIntent)) return FReply::Handled();
    const FVector2f Available(Geometry.GetLocalSize());
    const float Scale = FMath::Min(Available.X / DesignSize.X, Available.Y / DesignSize.Y);
    if (Scale <= 0) return FReply::Handled();
    const FVector2f Point = (FVector2f(Geometry.AbsoluteToLocal(AbsolutePosition)) - (Available - DesignSize * Scale) * 0.5f) / Scale;
    if (LocalPreviewRect.ContainsPoint(Point))
    {
        if (bSourceInspection) return FReply::Handled();
        ++PointerSerial; LastPointerAction = TEXT("local-battle-preview"); bLastPointerTouch = bTouch; LastPointerPoint = Point;
        OnLocalBattlePreviewRequested.Broadcast();
        return FReply::Handled();
    }
    if (PrologueRect.ContainsPoint(Point))
    {
        if (bSourceInspection) return FReply::Handled();
        ++PointerSerial; LastPointerAction = TEXT("prologue-dungeon"); bLastPointerTouch = bTouch; LastPointerPoint = Point;
        OnPrologueDungeonRequested.Broadcast();
        return FReply::Handled();
    }
    for (const auto& Control : SourceControls)
    {
        const FVector2f Local = TransformPoint(Inverse(Control.Transform), Point);
        if (Local.X < 0 || Local.Y < 0 || Local.X > Control.Size.X || Local.Y > Control.Size.Y) continue;
        if (Control.Action == TEXT("back") && Control.bEnabled)
        {
            ++PointerSerial; LastPointerAction = Control.Action; bLastPointerTouch = bTouch; LastPointerPoint = Point;
            OnBackRequested.Broadcast();
        }
        else if (Control.Action == TEXT("branch-unavailable")) Notice = TEXT("世界碎片暂不可用");
        else if (Control.Action == TEXT("info-unavailable")) Notice = TEXT("章节进度暂不可用");
        return FReply::Handled();
    }
    // Consume the original page surface, so input cannot reach hidden hall buttons.
    return FReply::Handled();
}

FReply UHczsWorldlineWidget::NativeOnMouseButtonDown(const FGeometry& Geometry, const FPointerEvent& Event)
{
    return Event.GetEffectingButton() == EKeys::LeftMouseButton ? PressAt(Geometry, Event.GetScreenSpacePosition(), false) : FReply::Handled();
}
FReply UHczsWorldlineWidget::NativeOnTouchStarted(const FGeometry& Geometry, const FPointerEvent& Event)
{
    return PressAt(Geometry, Event.GetScreenSpacePosition(), Event.IsTouchEvent());
}

bool UHczsWorldlineWidget::DevelopmentClickControl(const FString& Action, bool bTouch)
{
#if UE_BUILD_SHIPPING
    return false;
#else
    int32 Port = 0;
    if (!FParse::Param(FCommandLine::Get(), TEXT("HczsUITest"))
        || !FParse::Value(FCommandLine::Get(), TEXT("HczsServerPort="), Port)
        || Port <= 0 || Port > 65535 || Port == 7460 || bSourceInspection
        || !FSlateApplication::IsInitialized() || PaintSerial == 0 || !IsInViewport()
        || GetVisibility() != ESlateVisibility::Visible) return false;
    const auto* Match = LastPaintedControls.FindByPredicate([&Action](const FHczsWorldlineSourceControl& Control)
        { return Control.Action == Action && Control.bEnabled; });
    if (!Match) return false;
    const auto Control = *Match;
    const FVector2f Point = TransformPoint(Control.Transform, Control.Size * 0.5f);
    const auto SlateWidget = GetCachedWidget();
    if (!SlateWidget) return false;
    FSlateApplication& Slate = FSlateApplication::Get();
    const auto Window = Slate.FindWidgetWindow(SlateWidget.ToSharedRef());
    if (!Window || Window->IsWindowMinimized()) return false;
    FWidgetPath DesktopPath;
    if (!Slate.GeneratePathToWidgetUnchecked(SlateWidget.ToSharedRef(), DesktopPath)) return false;
    const auto Arranged = DesktopPath.FindArrangedWidget(SlateWidget.ToSharedRef());
    if (!Arranged.IsSet()) return false;
    const FGeometry& DesktopGeometry = Arranged.GetValue().Geometry;
    const FVector2f Available(DesktopGeometry.GetLocalSize());
    const float Scale = FMath::Min(Available.X / DesignSize.X, Available.Y / DesignSize.Y);
    if (Scale <= 0) return false;
    const FVector2D Absolute = DesktopGeometry.LocalToAbsolute((Available - DesignSize * Scale) * 0.5f + Point * Scale);
    const TArray<TSharedRef<SWindow>> Windows{Window.ToSharedRef()};
    const FWidgetPath Path = Slate.LocateWindowUnderMouse(Absolute, Windows, false, 0);
    if (!Path.IsValid() || !Path.ContainsWidget(SlateWidget.Get())) return false;
    const uint64 Before = PointerSerial;
    if (bTouch)
    {
        Slate.RoutePointerDownEvent(Path, FPointerEvent(0u, 7u, Absolute, Absolute, 1.0f, true));
        // This overload is always touch. The boolean is pressed-button state.
        Slate.RoutePointerUpEvent(Path, FPointerEvent(0u, 7u, Absolute, Absolute, 0.0f, false));
    }
    else
    {
        Slate.RoutePointerDownEvent(Path, FPointerEvent(0u, Absolute, Absolute, TSet<FKey>{EKeys::LeftMouseButton}, EKeys::LeftMouseButton, 0, FModifierKeysState()));
        Slate.RoutePointerUpEvent(Path, FPointerEvent(0u, Absolute, Absolute, TSet<FKey>(), EKeys::LeftMouseButton, 0, FModifierKeysState()));
    }
    const bool Routed = PointerSerial > Before && LastPointerAction == Action && bLastPointerTouch == bTouch;
    UE_LOG(LogTemp, Display, TEXT("HCZS worldline UI pointer: input=%s action=%s nativeHit=%s map=%s design=(%.1f,%.1f)"),
        bTouch ? TEXT("touch") : TEXT("mouse"), *Action, Routed ? TEXT("true") : TEXT("false"), *LastPaintedMap, Point.X, Point.Y);
    return Routed;
#endif
}
FReply UHczsWorldlineWidget::NativeOnKeyDown(const FGeometry& Geometry, const FKeyEvent& Event)
{
    const UHczsGameInstance* Session = Cast<UHczsGameInstance>(GetGameInstance());
    if (Event.GetKey() == EKeys::Escape && (bSourceInspection || (Session && !Session->bRequestInFlight && !Session->bHasPendingIntent)))
    {
        OnBackRequested.Broadcast();
        return FReply::Handled();
    }
    return Super::NativeOnKeyDown(Geometry, Event);
}

FString UHczsWorldlineWidget::DevelopmentDescribeUI() const
{
#if UE_BUILD_SHIPPING
    return TEXT("{}");
#else
    auto Root = MakeShared<FJsonObject>();
    const bool bUITest = FParse::Param(FCommandLine::Get(), TEXT("HczsUITest"));
    if (!bUITest && !FParse::Param(FCommandLine::Get(), TEXT("HczsWorldlineInspect"))) return TEXT("{}");
    Root->SetStringField(TEXT("mode"), bUITest ? TEXT("actual-nativepaint-and-slate-pointer-observation") : TEXT("original-worldline-static-source-page"));
    Root->SetStringField(TEXT("map"), LastPaintedMap);
    Root->SetBoolField(TEXT("originalSourcePage"), true);
    Root->SetBoolField(TEXT("battleScene"), false);
    Root->SetBoolField(TEXT("visible"), IsInViewport() && GetVisibility() == ESlateVisibility::Visible);
    Root->SetBoolField(TEXT("sourceReady"), bSourceReady);
    Root->SetBoolField(TEXT("sourceChineseFont"), bSourceFontReady);
    Root->SetBoolField(TEXT("progressAvailable"), false);
    Root->SetBoolField(TEXT("readOnlySourceInspection"), bSourceInspection);
    Root->SetNumberField(TEXT("chapterInstances"), 0);
    Root->SetNumberField(TEXT("paintSerial"), static_cast<double>(PaintSerial));
    Root->SetStringField(TEXT("sourceLayoutSha256"), Layout ? Layout->SourceLayoutSha256 : TEXT(""));
    Root->SetStringField(TEXT("lastPointerAction"), LastPointerAction);
    Root->SetStringField(TEXT("lastPointerValue"), TEXT(""));
    Root->SetBoolField(TEXT("lastPointerTouch"), bLastPointerTouch);
    Root->SetNumberField(TEXT("pointerEventSerial"), static_cast<double>(PointerSerial));
    TArray<TSharedPtr<FJsonValue>> Sprites, Texts;
    for (const auto& Id : LastPaintedSpriteIds) Sprites.Add(MakeShared<FJsonValueString>(Id));
    for (const auto& Label : LastPaintedTexts) Texts.Add(MakeShared<FJsonValueString>(Label));
    Root->SetArrayField(TEXT("actualPaintedSprites"), Sprites);
    Root->SetArrayField(TEXT("renderedTexts"), Texts);
    TArray<TSharedPtr<FJsonValue>> Controls;
    for (const auto& Control : LastPaintedControls)
    {
        auto Row = MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("action"), Control.Action); Row->SetStringField(TEXT("value"), TEXT(""));
        Row->SetBoolField(TEXT("enabled"), Control.bEnabled); Row->SetBoolField(TEXT("transformed"), false);
        const FVector2f Start = TransformPoint(Control.Transform, FVector2f::ZeroVector);
        const FVector2f End = TransformPoint(Control.Transform, Control.Size);
        TArray<TSharedPtr<FJsonValue>> Bounds;
        for (float N : {Start.X, Start.Y, End.X, End.Y}) Bounds.Add(MakeShared<FJsonValueNumber>(N));
        Row->SetArrayField(TEXT("rect"), Bounds); Controls.Add(MakeShared<FJsonValueObject>(Row));
    }
    Root->SetArrayField(TEXT("controls"), Controls);
    auto Resources = MakeShared<FJsonObject>();
    for (int32 Index = 0; Index < Items.Num(); ++Index)
        if (!Items[Index].bText && LastPaintedSpriteIds.Contains(ItemSpriteIds[Index]))
            if (const UObject* Resource = Items[Index].Brush.GetResourceObject()) Resources->SetStringField(ItemSpriteIds[Index], Resource->GetPathName());
    Root->SetObjectField(TEXT("paintResources"), Resources);
    if (const auto* Session = Cast<UHczsGameInstance>(GetGameInstance()))
    {
        Root->SetNumberField(TEXT("phase"), static_cast<int32>(Session->Phase));
        Root->SetStringField(TEXT("profileId"), Session->SelectedProfileId);
        Root->SetStringField(TEXT("battleId"), Session->CurrentBattle.Id);
        Root->SetNumberField(TEXT("revision"), static_cast<double>(Session->CurrentBattle.Revision));
        Root->SetNumberField(TEXT("actionIndex"), static_cast<double>(Session->CurrentBattle.ActionIndex));
        Root->SetStringField(TEXT("playerId"), Session->CurrentBattle.PlayerId);
        Root->SetStringField(TEXT("enemyId"), Session->CurrentBattle.EnemyId);
        Root->SetBoolField(TEXT("pending"), Session->bRequestInFlight || Session->bHasPendingIntent);
        Root->SetBoolField(TEXT("profileStateCurrent"), Session->bProfileStateCurrent);
        Root->SetBoolField(TEXT("battleStateCurrent"), Session->bBattleStateCurrent);
    }
    FString Result;
    FJsonSerializer::Serialize(Root, TJsonWriterFactory<>::Create(&Result));
    return Result;
#endif
}
