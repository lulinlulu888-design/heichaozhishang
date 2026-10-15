#include "HczsHallWidget.h"
#include "Engine/Texture2D.h"
#include "Engine/FontFace.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Rendering/DrawElementTypes.h"
#include "Framework/Application/SlateApplication.h"
#include "Fonts/FontMeasure.h"
#include "Rendering/SlateRenderer.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "HczsGameInstance.h"
#include "Styling/CoreStyle.h"
#include "Input/Reply.h"
#include "InputCoreTypes.h"
#include "Kismet/GameplayStatics.h"

namespace
{
bool Numbers(const TSharedPtr<FJsonObject>& Object, const TCHAR* Field, int32 Count, TArray<double>& Values)
{
    const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
    if (!Object->TryGetArrayField(Field, Array) || Array->Num() != Count) return false;
    for (const TSharedPtr<FJsonValue>& Value : *Array)
    {
        double Number = 0;
        if (!Value->TryGetNumber(Number) || !FMath::IsFinite(Number)) return false;
        Values.Add(Number);
    }
    return true;
}

FLinearColor Color(const TSharedPtr<FJsonObject>& Object, const TCHAR* Field)
{
    TArray<double> Values;
    if (!Numbers(Object, Field, 4, Values)) return FLinearColor::White;
    return FLinearColor(Values[0], Values[1], Values[2], Values[3]);
}
}

void UHczsHallWidget::NativeConstruct()
{
    Super::NativeConstruct();
    Items.Reset();
    bHasWorldline = false;
    bProfileFontReady = false;
    SetVisibility(ESlateVisibility::Visible);
    const bool bAIIcons = FParse::Param(FCommandLine::Get(), TEXT("HczsHDIcons"));
    if (bAIIcons)
    {
        Layout = LoadObject<UHczsHallLayoutAsset>(nullptr, TEXT("/Game/Recovered/Hall/UI/AI/UnifiedV4/HallLayoutHDAll.HallLayoutHDAll"));
        if (!Layout)
            Layout = LoadObject<UHczsHallLayoutAsset>(nullptr, TEXT("/Game/Recovered/Hall/UI/AI/UnifiedV3/HallLayoutHDBalanced.HallLayoutHDBalanced"));
        if (!Layout)
            Layout = LoadObject<UHczsHallLayoutAsset>(nullptr, TEXT("/Game/Recovered/Hall/UI/AI/UnifiedV2/HallLayoutHDUnified.HallLayoutHDUnified"));
        if (!Layout)
            Layout = LoadObject<UHczsHallLayoutAsset>(nullptr, TEXT("/Game/Recovered/Hall/UI/AI/HallLayoutHD.HallLayoutHD"));
    }
    if (!Layout)
        Layout = LoadObject<UHczsHallLayoutAsset>(nullptr, TEXT("/Game/Recovered/Hall/UI/HallLayout.HallLayout"));
    if (!Layout) return;
    TSharedPtr<FJsonObject> Root;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Layout->LayoutJson), Root) || !Root) return;
    const TArray<TSharedPtr<FJsonValue>>* DrawItems = nullptr;
    if (!Root->TryGetArrayField(TEXT("items"), DrawItems) || DrawItems->Num() > 2048) return;
    TMap<FString, TSharedPtr<const FCompositeFont>> Fonts;
    for (const auto& Pair : Layout->Fonts)
    {
        TSharedPtr<FCompositeFont> Composite = MakeShared<FCompositeFont>();
        FTypefaceEntry Entry;
        Entry.Name = TEXT("Regular");
        Entry.Font = FFontData(Pair.Value);
        Composite->DefaultTypeface.Fonts.Add(Entry);
        Fonts.Add(Pair.Key, Composite);
    }
    for (const TSharedPtr<FJsonValue>& Value : *DrawItems)
    {
        const TSharedPtr<FJsonObject> Object = Value->AsObject();
        if (!Object) continue;
        TArray<double> Size, Matrix;
        const TSharedPtr<FJsonObject>* Geometry = nullptr;
        FString Kind;
        if (!Object->TryGetStringField(TEXT("kind"), Kind) || !Numbers(Object, TEXT("size"), 2, Size)
            || !Object->TryGetObjectField(TEXT("geometry"), Geometry)
            || !Numbers(*Geometry, TEXT("matrix"), 6, Matrix)) continue;
        FHczsHallDrawItem Item;
        Item.bText = Kind == TEXT("text");
        Item.Size = FVector2f(Size[0], Size[1]);
        Item.Transform = FSlateRenderTransform(FMatrix2x2(Matrix[0], Matrix[1], Matrix[2], Matrix[3]),
            FVector2f(Matrix[4], Matrix[5]));
        FString InstancePath;
        Object->TryGetStringField(TEXT("instancePath"), InstancePath);
        if (Kind == TEXT("sprite") && InstancePath == TEXT("Layer/Main/RightBottom/EnteranceStory/BattleStory/@HomeBattle_story_ext/Node/BtnStory"))
        {
            WorldlineSize = Item.Size;
            WorldlineTransform = Item.Transform;
            bHasWorldline = true;
        }
        const TArray<TSharedPtr<FJsonValue>>* ClipGeometries = nullptr;
        if (Object->TryGetArrayField(TEXT("clipGeometry"), ClipGeometries))
        {
            for (const TSharedPtr<FJsonValue>& ClipValue : *ClipGeometries)
            {
                const TSharedPtr<FJsonObject> Clip = ClipValue->AsObject();
                const TArray<TSharedPtr<FJsonValue>>* Corners = nullptr;
                if (!Clip || !Clip->TryGetArrayField(TEXT("corners"), Corners) || Corners->Num() != 4) continue;
                TArray<FVector2f> Points;
                for (const TSharedPtr<FJsonValue>& Corner : *Corners)
                {
                    const TArray<TSharedPtr<FJsonValue>>& Pair = Corner->AsArray();
                    if (Pair.Num() != 2) break;
                    Points.Add(FVector2f(Pair[0]->AsNumber(), Pair[1]->AsNumber()));
                }
                if (Points.Num() == 4)
                    Item.Clips.Add(FSlateClippingZone(Points[0], Points[1], Points[3], Points[2]));
            }
        }
        Item.Color = Color(Object, TEXT("color"));
        double Opacity = 1;
        Object->TryGetNumberField(TEXT("opacity"), Opacity);
        Item.Color.A *= FMath::Clamp(Opacity, 0.0, 1.0);
        if (Item.bText)
        {
            FString FontId;
            double FontSize = 0;
            if (!Object->TryGetStringField(TEXT("fontId"), FontId) || !Fonts.Contains(FontId)
                || !Object->TryGetStringField(TEXT("text"), Item.Text)
                || !Object->TryGetNumberField(TEXT("fontSize"), FontSize) || FontSize <= 0 || FontSize > 256) continue;
            FFontOutlineSettings Outline;
            bool bOutline = false;
            Object->TryGetBoolField(TEXT("outlineEnabled"), bOutline);
            if (bOutline)
            {
                double Width = 0;
                Object->TryGetNumberField(TEXT("outlineSize"), Width);
                Outline.OutlineSize = FMath::Clamp(int32(Width), 0, 16);
                Outline.OutlineColor = Color(Object, TEXT("outlineColor"));
            }
            // CSB sizes are pixels. Slate font sizes are points at RenderDPI.
            Item.Font = FSlateFontInfo(Fonts[FontId], FontSize * 72.0f / FontConstants::RenderDPI,
                TEXT("Regular"), Outline);
            if (!bProfileFontReady)
            {
                ProfileFont = FSlateFontInfo(Fonts[FontId], 18 * 72.0f / FontConstants::RenderDPI, TEXT("Regular"));
                bProfileFontReady = true;
            }
            double Horizontal = 0, Vertical = 0;
            Object->TryGetNumberField(TEXT("horizontalAlignment"), Horizontal);
            Object->TryGetNumberField(TEXT("verticalAlignment"), Vertical);
            Item.HorizontalAlignment = int32(Horizontal);
            Item.VerticalAlignment = int32(Vertical);
            Object->TryGetBoolField(TEXT("shadowEnabled"), Item.bShadow);
            TArray<double> ShadowOffset;
            if (Item.bShadow && Numbers(Object, TEXT("shadowOffset"), 2, ShadowOffset))
            {
                Item.ShadowOffset = FVector2f(ShadowOffset[0], -ShadowOffset[1]);
                Item.ShadowColor = Color(Object, TEXT("shadowColor"));
                Item.ShadowColor.A *= Item.Color.A;
            }
        }
        else if (Kind == TEXT("sprite"))
        {
            FString SpriteId;
            if (!Object->TryGetStringField(TEXT("spriteId"), SpriteId) || !Layout->Sprites.Contains(SpriteId)) continue;
            UTexture2D* Texture = Layout->Sprites[SpriteId];
            Item.Brush.SetResourceObject(Texture);
            Item.Brush.DrawAs = ESlateBrushDrawType::Image;
            Item.Brush.ImageSize = FVector2f(Texture->GetSizeX(), Texture->GetSizeY());
            bool bFlipX = false, bFlipY = false;
            Object->TryGetBoolField(TEXT("flipX"), bFlipX);
            Object->TryGetBoolField(TEXT("flipY"), bFlipY);
            Item.Brush.Mirroring = bFlipX ? (bFlipY ? ESlateBrushMirrorType::Both : ESlateBrushMirrorType::Horizontal)
                : (bFlipY ? ESlateBrushMirrorType::Vertical : ESlateBrushMirrorType::NoMirror);
        }
        else continue;
        Items.Add(MoveTemp(Item));
    }
    UE_LOG(LogTemp, Display, TEXT("HCZS: hall UI layout loaded %d items, %d textures, %d font faces; iconVariant=%s"),
        Items.Num(), Layout->Sprites.Num(), Layout->Fonts.Num(),
        *Layout->GetName());
}

int32 UHczsHallWidget::NativePaint(const FPaintArgs& Args, const FGeometry& Geometry,
    const FSlateRect& CullingRect, FSlateWindowElementList& Elements, int32 LayerId,
    const FWidgetStyle& Style, bool bParentEnabled) const
{
    int32 Layer = Super::NativePaint(Args, Geometry, CullingRect, Elements, LayerId, Style, bParentEnabled);
    const FVector2f Available = Geometry.GetLocalSize();
    LastPaintGeometry = Geometry;
    bHasPaintGeometry = true;
    ++PaintSerial;
    LastPaintedTexts.Reset();
    const float Scale = FMath::Min(Available.X / DesignSize.X, Available.Y / DesignSize.Y);
    if (Scale <= 0) return Layer;
    const FVector2f Offset = (Available - DesignSize * Scale) * 0.5f;
    for (const FHczsHallDrawItem& Item : Items)
    {
        for (const FSlateClippingZone& Clip : Item.Clips)
        {
            Elements.PushClip(FSlateClippingZone(
                Geometry.LocalToAbsolute(Offset + Clip.TopLeft * Scale),
                Geometry.LocalToAbsolute(Offset + Clip.TopRight * Scale),
                Geometry.LocalToAbsolute(Offset + Clip.BottomLeft * Scale),
                Geometry.LocalToAbsolute(Offset + Clip.BottomRight * Scale)));
        }
        const FGeometry ItemGeometry = Geometry.MakeChild(Item.Size, FSlateLayoutTransform(Scale, Offset),
            Item.Transform, FVector2f::ZeroVector);
        if (!Item.bText)
        {
            FSlateDrawElement::MakeBox(Elements, ++Layer, ItemGeometry.ToPaintGeometry(), &Item.Brush,
                ESlateDrawEffect::None, Item.Color);
            for (int32 Index = 0; Index < Item.Clips.Num(); ++Index) Elements.PopClip();
            continue;
        }
        const FVector2f TextSize = FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(Item.Text, Item.Font);
        LastPaintedTexts.Add(Item.Text);
        FVector2f TextOffset = FVector2f::ZeroVector;
        if (Item.HorizontalAlignment == 1) TextOffset.X = (Item.Size.X - TextSize.X) * 0.5f;
        else if (Item.HorizontalAlignment == 2) TextOffset.X = Item.Size.X - TextSize.X;
        if (Item.VerticalAlignment == 1) TextOffset.Y = (Item.Size.Y - TextSize.Y) * 0.5f;
        else if (Item.VerticalAlignment == 2) TextOffset.Y = Item.Size.Y - TextSize.Y;
        if (Item.bShadow)
        {
            const FGeometry Shadow = ItemGeometry.MakeChild(TextSize, FSlateLayoutTransform(TextOffset + Item.ShadowOffset));
            FSlateDrawElement::MakeText(Elements, ++Layer, Shadow.ToPaintGeometry(), Item.Text, Item.Font,
                ESlateDrawEffect::None, Item.ShadowColor);
        }
        const FGeometry Text = ItemGeometry.MakeChild(TextSize, FSlateLayoutTransform(TextOffset));
        FSlateDrawElement::MakeText(Elements, ++Layer, Text.ToPaintGeometry(), Item.Text, Item.Font,
            ESlateDrawEffect::None, Item.Color);
        for (int32 Index = 0; Index < Item.Clips.Num(); ++Index) Elements.PopClip();
    }
    if (bProfileFontReady)
    {
        const UHczsGameInstance* Session = Cast<UHczsGameInstance>(GetGameInstance());
        FString Label = TEXT("选择本地档案");
        if (Session && !Session->SelectedProfileId.IsEmpty())
        {
            for (const FHczsLocalProfile& Profile : Session->Profiles)
                if (Profile.Id == Session->SelectedProfileId) { Label = Profile.DisplayName.Left(10) + TEXT(" · 切换"); break; }
        }
        const FGeometry Button = Geometry.MakeChild(FVector2f(ProfileRect.GetSize()), FSlateLayoutTransform(Scale, Offset),
            FSlateRenderTransform(FVector2f(ProfileRect.Left, ProfileRect.Top)), FVector2f::ZeroVector);
        FSlateDrawElement::MakeBox(Elements, ++Layer, Button.ToPaintGeometry(), FCoreStyle::Get().GetBrush(TEXT("WhiteBrush")),
            ESlateDrawEffect::None, FLinearColor(0.055f, 0.11f, 0.18f, 0.66f));
        const FVector2f TextSize(FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(Label, ProfileFont));
        LastPaintedTexts.Add(Label);
        Elements.PushClip(FSlateClippingZone(Button));
        const FGeometry Text = Button.MakeChild(TextSize, FSlateLayoutTransform(FVector2f(12, (38 - TextSize.Y) / 2)));
        FSlateDrawElement::MakeText(Elements, ++Layer, Text.ToPaintGeometry(), Label, ProfileFont, ESlateDrawEffect::None, FLinearColor::White);
        Elements.PopClip();
    }
    return Layer;
}

FReply UHczsHallWidget::PressAt(const FGeometry& Geometry, const FVector2D& AbsolutePosition, bool bTouch)
{
    const FVector2f Available(Geometry.GetLocalSize());
    const float Scale = FMath::Min(Available.X / DesignSize.X, Available.Y / DesignSize.Y);
    if (Scale <= 0) return FReply::Unhandled();
    const FVector2f Point = (FVector2f(Geometry.AbsoluteToLocal(AbsolutePosition)) - (Available - DesignSize * Scale) * 0.5f) / Scale;
    FString Action;
    if (ProfileRect.ContainsPoint(Point)) Action = TEXT("profile");
    else if (bHasWorldline)
    {
        const FVector2f Local = TransformPoint(Inverse(WorldlineTransform), Point);
        if (Local.X >= 0 && Local.Y >= 0 && Local.X <= WorldlineSize.X && Local.Y <= WorldlineSize.Y) Action = TEXT("worldline");
    }
    if (Action.IsEmpty()) return FReply::Unhandled();
    ++PointerSerial;
    LastPointerAction = Action;
    bLastPointerTouch = bTouch;
    if (Action == TEXT("profile")) OnProfileRequested.Broadcast();
    else OnWorldlineRequested.Broadcast();
    return FReply::Handled();
}

FReply UHczsHallWidget::NativeOnMouseButtonDown(const FGeometry& Geometry, const FPointerEvent& Event)
{
    if (Event.GetEffectingButton() == EKeys::LeftMouseButton) return PressAt(Geometry, Event.GetScreenSpacePosition(), false);
    return Super::NativeOnMouseButtonDown(Geometry, Event);
}

FReply UHczsHallWidget::NativeOnTouchStarted(const FGeometry& Geometry, const FPointerEvent& Event)
{
    return PressAt(Geometry, Event.GetScreenSpacePosition(), true);
}

bool UHczsHallWidget::DevelopmentClickControl(const FString& Action, bool bTouch)
{
#if UE_BUILD_SHIPPING
    return false;
#else
    int32 Port = 0;
    if (!FParse::Param(FCommandLine::Get(), TEXT("HczsUITest")) ||
        !FParse::Value(FCommandLine::Get(), TEXT("HczsServerPort="), Port) || Port <= 0 || Port > 65535 || Port == 7460 ||
        !FSlateApplication::IsInitialized() || !IsInViewport() || !bHasPaintGeometry || GetVisibility() != ESlateVisibility::Visible) return false;
    FVector2f Point;
    if (Action == TEXT("worldline") && bHasWorldline) Point = TransformPoint(WorldlineTransform, WorldlineSize * 0.5f);
    else if (Action == TEXT("profile")) Point = FVector2f((ProfileRect.Left + ProfileRect.Right) / 2, (ProfileRect.Top + ProfileRect.Bottom) / 2);
    else return false;
    FSlateApplication& Slate = FSlateApplication::Get();
    const TSharedPtr<SWidget> SlateWidget = GetCachedWidget();
    if (!SlateWidget) return false;
    const TSharedPtr<SWindow> Window = Slate.FindWidgetWindow(SlateWidget.ToSharedRef());
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
        // This overload is always touch; the final bool is pressed-button state.
        Slate.RoutePointerUpEvent(Path, FPointerEvent(0u, 7u, Absolute, Absolute, 0.0f, false));
    }
    else
    {
        Slate.RoutePointerDownEvent(Path, FPointerEvent(0u, Absolute, Absolute, TSet<FKey>{EKeys::LeftMouseButton}, EKeys::LeftMouseButton, 0, FModifierKeysState()));
        Slate.RoutePointerUpEvent(Path, FPointerEvent(0u, Absolute, Absolute, TSet<FKey>(), EKeys::LeftMouseButton, 0, FModifierKeysState()));
    }
    const bool Routed = PointerSerial > Before && LastPointerAction == Action && bLastPointerTouch == bTouch;
    UE_LOG(LogTemp, Display, TEXT("HCZS hall UI pointer: input=%s action=%s nativeHit=%s"), bTouch ? TEXT("touch") : TEXT("mouse"), *Action, Routed ? TEXT("true") : TEXT("false"));
    return Routed;
#endif
}

FString UHczsHallWidget::DevelopmentDescribeUI() const
{
#if UE_BUILD_SHIPPING
    return TEXT("{}");
#else
    if (!FParse::Param(FCommandLine::Get(), TEXT("HczsUITest"))) return TEXT("{}");
    auto Root = MakeShared<FJsonObject>();
    Root->SetStringField(TEXT("mode"), TEXT("actual-nativepaint-and-slate-pointer-observation"));
    Root->SetStringField(TEXT("map"), UGameplayStatics::GetCurrentLevelName(this, true));
    Root->SetNumberField(TEXT("paintSerial"), static_cast<double>(PaintSerial));
    Root->SetBoolField(TEXT("visible"), GetVisibility() == ESlateVisibility::Visible && IsInViewport());
    Root->SetBoolField(TEXT("battleScene"), false);
    Root->SetBoolField(TEXT("sourceChineseFont"), bProfileFontReady);
    Root->SetStringField(TEXT("lastPointerAction"), LastPointerAction);
    Root->SetStringField(TEXT("lastPointerValue"), TEXT(""));
    Root->SetBoolField(TEXT("lastPointerTouch"), bLastPointerTouch);
    Root->SetNumberField(TEXT("pointerEventSerial"), static_cast<double>(PointerSerial));
    TArray<TSharedPtr<FJsonValue>> Texts;
    for (const FString& Text : LastPaintedTexts) Texts.Add(MakeShared<FJsonValueString>(Text));
    Root->SetArrayField(TEXT("renderedTexts"), Texts);
    TArray<TSharedPtr<FJsonValue>> Controls;
    auto AddControl = [&Controls](const FString& Action, const FSlateRect& Rect)
    {
        auto Row = MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("action"), Action); Row->SetStringField(TEXT("value"), TEXT(""));
        Row->SetBoolField(TEXT("enabled"), true); Row->SetBoolField(TEXT("transformed"), false);
        TArray<TSharedPtr<FJsonValue>> Bounds;
        for (float Value : {Rect.Left, Rect.Top, Rect.Right, Rect.Bottom}) Bounds.Add(MakeShared<FJsonValueNumber>(Value));
        Row->SetArrayField(TEXT("rect"), Bounds); Controls.Add(MakeShared<FJsonValueObject>(Row));
    };
    AddControl(TEXT("profile"), ProfileRect);
    if (bHasWorldline)
    {
        const FVector2f Origin = TransformPoint(WorldlineTransform, FVector2f::ZeroVector);
        const FVector2f End = TransformPoint(WorldlineTransform, WorldlineSize);
        AddControl(TEXT("worldline"), FSlateRect(Origin.X, Origin.Y, End.X, End.Y));
    }
    Root->SetArrayField(TEXT("controls"), Controls);
    if (const UHczsGameInstance* Session = Cast<UHczsGameInstance>(GetGameInstance()))
    {
        Root->SetNumberField(TEXT("phase"), static_cast<int32>(Session->Phase));
        Root->SetStringField(TEXT("profileId"), Session->SelectedProfileId);
        Root->SetStringField(TEXT("battleId"), Session->CurrentBattle.Id);
        Root->SetBoolField(TEXT("pending"), Session->bRequestInFlight || Session->bHasPendingIntent);
    }
    FString Result;
    FJsonSerializer::Serialize(Root, TJsonWriterFactory<>::Create(&Result));
    return Result;
#endif
}
