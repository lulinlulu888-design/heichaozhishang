#include "HczsDungeonWidget.h"
#include "HczsPrologueAvg.h"
#include "HczsGameInstance.h"
#include "Engine/FontFace.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Rendering/DrawElementTypes.h"
#include "Framework/Application/SlateApplication.h"
#include "Fonts/FontMeasure.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/CoreStyle.h"
#include "InputCoreTypes.h"

namespace
{
const FVector2f DesignSize(1280, 720);
const TCHAR* Challenge3997Desc = TEXT("在未来的回忆里，这是她与艾尔莎的最后一战——阻止第三次黑潮。然而她们的队友已经……");
const TCHAR* Challenge3998Desc = TEXT("在未来的回忆里，这是她与艾尔莎的最后一战——阻止第三次黑潮。然而这次战斗……");
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

void UHczsDungeonWidget::NativeConstruct()
{
    Super::NativeConstruct();
    SetIsFocusable(true);
    SetVisibility(ESlateVisibility::Visible);
    Items.Reset(); ItemWrap.Reset(); Controls.Reset(); bSourceReady = false;
    Layout = LoadObject<UHczsHallLayoutAsset>(nullptr, TEXT("/Game/Recovered/Worldline/Dungeon/UI/DungeonLayout.DungeonLayout"));
    if (!Layout) return;
    TSharedPtr<FJsonObject> Root;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Layout->LayoutJson), Root) || !Root) return;
    double Challenge = 0;
    if (!Root->TryGetNumberField(TEXT("challengeId"), Challenge) || Challenge != 3997) return;
    TMap<FString, TSharedPtr<const FCompositeFont>> Fonts;
    for (const auto& Pair : Layout->Fonts)
    {
        if (!Pair.Value) continue;
        TSharedPtr<FCompositeFont> Composite = MakeShared<FCompositeFont>();
        FTypefaceEntry Entry; Entry.Name = TEXT("Regular"); Entry.Font = FFontData(Pair.Value);
        Composite->DefaultTypeface.Fonts.Add(Entry);
        Fonts.Add(Pair.Key, Composite);
    }
    const TArray<TSharedPtr<FJsonValue>>* DrawItems = nullptr;
    if (!Root->TryGetArrayField(TEXT("items"), DrawItems) || DrawItems->Num() > 256) return;
    for (const auto& Value : *DrawItems)
    {
        const auto Object = Value->AsObject();
        FString Kind; FHczsHallDrawItem Item;
        if (!Object || !Object->TryGetStringField(TEXT("kind"), Kind) || !ReadGeometry(Object, Item.Size, Item.Transform)) return;
        Item.bText = Kind == TEXT("text");
        Item.Color = ReadColor(Object, TEXT("color"));
        double Opacity = 1; Object->TryGetNumberField(TEXT("opacity"), Opacity);
        Item.Color.A *= FMath::Clamp(Opacity, 0.0, 1.0);
        bool bWrap = false;
        if (Item.bText)
        {
            FString FontId; double FontSize = 0, Horizontal = 0, Vertical = 0;
            if (!Object->TryGetStringField(TEXT("fontId"), FontId) || !Fonts.Contains(FontId)
                || !Object->TryGetStringField(TEXT("text"), Item.Text)
                || !Object->TryGetNumberField(TEXT("fontSize"), FontSize) || FontSize <= 0 || FontSize > 256) return;
            Item.Font = FSlateFontInfo(Fonts[FontId], FontSize * 72.0f / FontConstants::RenderDPI, TEXT("Regular"));
            if (Object->TryGetNumberField(TEXT("horizontalAlignment"), Horizontal)) Item.HorizontalAlignment = static_cast<int32>(Horizontal);
            if (Object->TryGetNumberField(TEXT("verticalAlignment"), Vertical)) Item.VerticalAlignment = static_cast<int32>(Vertical);
            Object->TryGetBoolField(TEXT("wrap"), bWrap);
        }
        else
        {
            FString SpriteId;
            if (!Object->TryGetStringField(TEXT("spriteId"), SpriteId) || !Layout->Sprites.Contains(SpriteId) || !Layout->Sprites[SpriteId]) return;
            Item.Brush = FSlateBrush();
            Item.Brush.SetResourceObject(Layout->Sprites[SpriteId]);
            Item.Brush.ImageSize = Item.Size;
            Item.Brush.DrawAs = ESlateBrushDrawType::Image;
        }
        Items.Add(Item); ItemWrap.Add(bWrap);
    }
    const TArray<TSharedPtr<FJsonValue>>* ControlValues = nullptr;
    if (!Root->TryGetArrayField(TEXT("controls"), ControlValues) || ControlValues->Num() > 8) return;
    for (const auto& Value : *ControlValues)
    {
        const auto Object = Value->AsObject();
        FControl Control;
        if (!Object || !Object->TryGetStringField(TEXT("action"), Control.Action) || !ReadGeometry(Object, Control.Size, Control.Transform)) return;
        Object->TryGetBoolField(TEXT("enabled"), Control.bEnabled);
        Controls.Add(Control);
    }
    bSourceReady = Items.Num() > 0;
}

int32 UHczsDungeonWidget::NativePaint(const FPaintArgs& Args, const FGeometry& Geometry,
    const FSlateRect& CullingRect, FSlateWindowElementList& Elements, int32 LayerId,
    const FWidgetStyle& Style, bool bParentEnabled) const
{
    int32 Layer = Super::NativePaint(Args, Geometry, CullingRect, Elements, LayerId, Style, bParentEnabled);
    const FVector2f Available(Geometry.GetLocalSize());
    const float Scale = FMath::Min(Available.X / DesignSize.X, Available.Y / DesignSize.Y);
    if (Scale <= 0) return Layer;
    const FVector2f Offset = (Available - DesignSize * Scale) * 0.5f;
    if (!bSourceReady)
    {
        const FSlateFontInfo Font = FCoreStyle::GetDefaultFontStyle(TEXT("Regular"), 18);
        FSlateDrawElement::MakeText(Elements, ++Layer, Geometry.ToPaintGeometry(FVector2f(400, 40), FSlateLayoutTransform(FVector2f(24, 24))),
            TEXT("序章"), Font, ESlateDrawEffect::None, FLinearColor::White);
        return Layer;
    }
    const auto Measure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
    const UHczsGameInstance* Session = Cast<UHczsGameInstance>(GetGameInstance());
    const bool bBossUnlocked = Session && Session->MainlineProgress.bIsValid && Session->MainlineProgress.bFirstChallengePassed;
    for (int32 Index = 0; Index < Items.Num(); ++Index)
    {
        const auto& Item = Items[Index];
        const FGeometry ItemGeometry = Geometry.MakeChild(Item.Size, FSlateLayoutTransform(Scale, Offset), Item.Transform, FVector2f::ZeroVector);
        if (!Item.bText)
        {
            FSlateDrawElement::MakeBox(Elements, ++Layer, ItemGeometry.ToPaintGeometry(), &Item.Brush, ESlateDrawEffect::None, Item.Color);
            continue;
        }
        FString Remaining = Item.Text;
        if (bBossUnlocked && Remaining == Challenge3997Desc) Remaining = Challenge3998Desc;
        float LineTop = 0;
        const float LineHeight = Measure->GetMaxCharacterHeight(Item.Font);
        while (!Remaining.IsEmpty() && LineTop + LineHeight <= Item.Size.Y + 1)
        {
            FString Line = Remaining;
            if (ItemWrap[Index])
            {
                int32 Count = Remaining.Len();
                while (Count > 1 && Measure->Measure(Remaining.Left(Count), Item.Font).X > Item.Size.X) --Count;
                Line = Remaining.Left(Count);
                Remaining.RightChopInline(Count);
            }
            else Remaining.Reset();
            const FVector2f TextSize(Measure->Measure(Line, Item.Font));
            FVector2f TextOffset(0, LineTop);
            if (!ItemWrap[Index])
            {
                if (Item.HorizontalAlignment == 1) TextOffset.X = (Item.Size.X - TextSize.X) / 2;
                else if (Item.HorizontalAlignment == 2) TextOffset.X = Item.Size.X - TextSize.X;
                if (Item.VerticalAlignment == 1) TextOffset.Y = (Item.Size.Y - TextSize.Y) / 2;
                else if (Item.VerticalAlignment == 2) TextOffset.Y = Item.Size.Y - TextSize.Y;
            }
            FSlateDrawElement::MakeText(Elements, ++Layer, ItemGeometry.MakeChild(TextSize, FSlateLayoutTransform(TextOffset)).ToPaintGeometry(),
                Line, Item.Font, ESlateDrawEffect::None, Item.Color);
            LineTop += LineHeight;
        }
    }
    const FHczsHallDrawItem* NoticeItem = Items.FindByPredicate([](const FHczsHallDrawItem& Item) { return Item.bText; });
    if (bBossUnlocked && NoticeItem)
    {
        FSlateFontInfo Font = NoticeItem->Font;
        Font.Size = 11;
        const bool bAvgFinished = Avg138Index >= HczsPrologueAvg138().Num();
        const FHczsMainlineProgress& Progress = Session->MainlineProgress;
        const bool bBossBound = Progress.Challenges.Num() == 2 && Progress.Challenges[1].bExecutable;
        const FString Notice = Progress.bBossChallengePassed ? TEXT("3998 已通关 · 序章首领战完成") :
            !bBossBound ? (bAvgFinished ? TEXT("AVG138 已按序播完，1703 仍未开打") : TEXT("3998 已解锁，首领战尚未恢复")) :
            bAvgFinished ? TEXT("AVG138 已播完 · 点击探索进入首领战") : TEXT("3998 已解锁 · 首领战规则为重建");
        const FVector2f TextSize(Measure->Measure(Notice, Font));
        const FGeometry NoticeGeometry = Geometry.MakeChild(TextSize, FSlateLayoutTransform(Scale, Offset + FVector2f(1240 - TextSize.X, 694) * Scale));
        FSlateDrawElement::MakeText(Elements, ++Layer, NoticeGeometry.ToPaintGeometry(), Notice, Font, ESlateDrawEffect::None, FLinearColor::White);
    }
    const auto Dialogue = HczsPrologueAvg138();
    if (Avg138Index >= 0 && Avg138Index < Dialogue.Num())
    {
        // The band stops short of the explore button (x >= 940); long rows wrap to a second line.
        const FSlateFontInfo Font = FCoreStyle::GetDefaultFontStyle(TEXT("Regular"), 18);
        const FVector2f Band(820, 96);
        const FGeometry BandGeometry = Geometry.MakeChild(Band, FSlateLayoutTransform(Scale, Offset + FVector2f(90, 594) * Scale));
        FSlateDrawElement::MakeBox(Elements, ++Layer, BandGeometry.ToPaintGeometry(), FCoreStyle::Get().GetBrush(TEXT("WhiteBrush")),
            ESlateDrawEffect::None, FLinearColor(0.02f, 0.02f, 0.03f, 0.88f));
        const FSlateFontInfo NameFont = FCoreStyle::GetDefaultFontStyle(TEXT("Bold"), 16);
        FSlateDrawElement::MakeText(Elements, ++Layer, BandGeometry.ToPaintGeometry(FVector2f(780, 22), FSlateLayoutTransform(FVector2f(20, 8))),
            Dialogue[Avg138Index].Speaker, NameFont, ESlateDrawEffect::None, FLinearColor(0.55f, 0.85f, 1.0f));
        FString Remaining = Dialogue[Avg138Index].Text;
        for (float Top = 36; !Remaining.IsEmpty() && Top < 90; Top += 26)
        {
            int32 Count = Remaining.Len();
            while (Count > 1 && Measure->Measure(Remaining.Left(Count), Font).X > 780) --Count;
            FSlateDrawElement::MakeText(Elements, ++Layer, BandGeometry.ToPaintGeometry(FVector2f(780, 26), FSlateLayoutTransform(FVector2f(20, Top))),
                Remaining.Left(Count), Font, ESlateDrawEffect::None, FLinearColor::White);
            Remaining.RightChopInline(Count);
        }
    }
    if (Session && Session->bAvg134Pending)
    {
        // Row 93 swaps to the avgBlack background; the narration is centred white text.
        FSlateDrawElement::MakeBox(Elements, ++Layer, Geometry.ToPaintGeometry(), FCoreStyle::Get().GetBrush(TEXT("WhiteBrush")),
            ESlateDrawEffect::None, FLinearColor::Black);
        const FSlateFontInfo Font = FCoreStyle::GetDefaultFontStyle(TEXT("Regular"), 22);
        const float LineHeight = Measure->GetMaxCharacterHeight(Font) * 1.5f;
        TArray<FString> Lines;
        HczsPrologueAvg134Line(FMath::Max(Avg134Index, 0), PlayerName()).ParseIntoArrayLines(Lines);
        float Top = 360 - Lines.Num() * LineHeight * 0.5f;
        for (const FString& Line : Lines)
        {
            const FVector2f TextSize(Measure->Measure(Line, Font));
            const FGeometry LineGeometry = Geometry.MakeChild(TextSize, FSlateLayoutTransform(Scale, Offset + FVector2f(640 - TextSize.X * 0.5f, Top) * Scale));
            FSlateDrawElement::MakeText(Elements, ++Layer, LineGeometry.ToPaintGeometry(), Line, Font, ESlateDrawEffect::None, FLinearColor::White);
            Top += LineHeight;
        }
    }
    return Layer;
}

FString UHczsDungeonWidget::PlayerName() const
{
    const UHczsGameInstance* Session = Cast<UHczsGameInstance>(GetGameInstance());
    const FHczsLocalProfile* Profile = Session ? Session->Profiles.FindByPredicate(
        [Session](const FHczsLocalProfile& P) { return P.Id == Session->SelectedProfileId; }) : nullptr;
    return Profile ? Profile->DisplayName : FString();
}

FReply UHczsDungeonWidget::PressAt(const FGeometry& Geometry, const FVector2D& AbsolutePosition)
{
    UHczsGameInstance* Session = Cast<UHczsGameInstance>(GetGameInstance());
    if (Session && (Session->bRequestInFlight || Session->bHasPendingIntent)) return FReply::Handled();
    const FVector2f Available(Geometry.GetLocalSize());
    const float Scale = FMath::Min(Available.X / DesignSize.X, Available.Y / DesignSize.Y);
    if (Scale <= 0 || !bSourceReady) return FReply::Handled();
    if (Session && Session->bAvg134Pending)
    {
        ++PressSerial; LastPressAction = TEXT("avg134");
        Avg134Index = FMath::Max(Avg134Index, 0) + 1;
        if (Avg134Index >= HczsPrologueAvg134().Num()) { Avg134Index = -1; Session->CompleteAvg134(); }
        return FReply::Handled();
    }
    const FVector2f Point = (FVector2f(Geometry.AbsoluteToLocal(AbsolutePosition)) - (Available - DesignSize * Scale) * 0.5f) / Scale;
    for (const auto& Control : Controls)
    {
        const FVector2f Local = TransformPoint(Inverse(Control.Transform), Point);
        if (!Control.bEnabled || Local.X < 0 || Local.Y < 0 || Local.X > Control.Size.X || Local.Y > Control.Size.Y) continue;
        ++PressSerial; LastPressAction = Control.Action;
        if (Control.Action == TEXT("back")) OnBackRequested.Broadcast();
        else if (Control.Action == TEXT("explore"))
        {
            const bool bBossUnlocked = Session && Session->MainlineProgress.bIsValid && Session->MainlineProgress.bFirstChallengePassed;
            const bool bAvgFinished = Avg138Index >= HczsPrologueAvg138().Num();
            if (!bBossUnlocked) OnExploreRequested.Broadcast();
            else if (!bAvgFinished && !Session->MainlineProgress.bBossChallengePassed) Avg138Index = HczsAdvancePrologueAvg138(Avg138Index);
            // AVG138 precedes battle 1703; the mode ignores this unless 3998 is bound and not yet passed.
            else OnExploreRequested.Broadcast();
        }
        return FReply::Handled();
    }
    return FReply::Unhandled();
}

bool UHczsDungeonWidget::DevelopmentPressControl(const FString& Action)
{
#if UE_BUILD_SHIPPING
    return false;
#else
    int32 Port = 0;
    if (!FParse::Param(FCommandLine::Get(), TEXT("HczsMainlineUITest")) || !FParse::Value(FCommandLine::Get(), TEXT("HczsServerPort="), Port)
        || Port <= 0 || Port > 65535 || Port == 7460 || !FSlateApplication::IsInitialized() || !bSourceReady || !IsInViewport()) return false;
    const UHczsGameInstance* Session = Cast<UHczsGameInstance>(GetGameInstance());
    const bool bAvg134 = Action == TEXT("avg134");
    if (bAvg134 && !(Session && Session->bAvg134Pending)) return false;
    const FControl* Control = Controls.FindByPredicate([&Action](const FControl& C) { return C.Action == Action && C.bEnabled; });
    const TSharedPtr<SWidget> SlateWidget = GetCachedWidget();
    if ((!Control && !bAvg134) || !SlateWidget) return false;
    FSlateApplication& Slate = FSlateApplication::Get();
    const TSharedPtr<SWindow> Window = Slate.FindWidgetWindow(SlateWidget.ToSharedRef());
    FWidgetPath DesktopPath;
    if (!Window || Window->IsWindowMinimized() || !Slate.GeneratePathToWidgetUnchecked(SlateWidget.ToSharedRef(), DesktopPath)) return false;
    const auto Arranged = DesktopPath.FindArrangedWidget(SlateWidget.ToSharedRef());
    if (!Arranged.IsSet()) return false;
    const FGeometry& Geometry = Arranged.GetValue().Geometry;
    const FVector2f Available(Geometry.GetLocalSize());
    const float Scale = FMath::Min(Available.X / DesignSize.X, Available.Y / DesignSize.Y);
    if (Scale <= 0) return false;
    const FVector2f Point = bAvg134 ? DesignSize * 0.5f : TransformPoint(Control->Transform, Control->Size * 0.5f);
    const FVector2f Absolute = Geometry.LocalToAbsolute((Available - DesignSize * Scale) * 0.5f + Point * Scale);
    TArray<TSharedRef<SWindow>> Windows{Window.ToSharedRef()};
    FWidgetPath Path = Slate.LocateWindowUnderMouse(Absolute, Windows, false, 0);
    const bool bContains = Path.IsValid() && Path.ContainsWidget(SlateWidget.Get());
    const uint64 Before = PressSerial;
    bool bHandled = false;
    if (bContains)
    {
        TSet<FKey> Buttons{EKeys::LeftMouseButton};
        bHandled = Slate.RoutePointerDownEvent(Path, FPointerEvent(0u, Absolute, Absolute, Buttons, EKeys::LeftMouseButton, 0, FModifierKeysState())).IsEventHandled();
        Slate.RoutePointerUpEvent(Path, FPointerEvent(0u, Absolute, Absolute, TSet<FKey>(), EKeys::LeftMouseButton, 0, FModifierKeysState()));
    }
    const bool bRouted = PressSerial == Before + 1 && LastPressAction == Action;
    UE_LOG(LogTemp, Display, TEXT("HCZS dungeon pointer: action=%s design=(%.1f,%.1f) absolute=(%.1f,%.1f) geometry=(%.1f,%.1f) containsWidget=%d handled=%d leaf=%s routed=%d"),
        *Action, Point.X, Point.Y, Absolute.X, Absolute.Y, Available.X, Available.Y, bContains, bHandled,
        Path.IsValid() ? *Path.Widgets.Last().Widget->GetTypeAsString() : TEXT("none"), bRouted);
    return bRouted;
#endif
}

FString UHczsDungeonWidget::DevelopmentDescribe() const
{
    const TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
    Root->SetBoolField(TEXT("sourceReady"), bSourceReady);
    Root->SetNumberField(TEXT("avg138Index"), Avg138Index);
    Root->SetNumberField(TEXT("avg138Count"), HczsPrologueAvg138().Num());
    const UHczsGameInstance* Session = Cast<UHczsGameInstance>(GetGameInstance());
    Root->SetBoolField(TEXT("avg134Pending"), Session && Session->bAvg134Pending);
    Root->SetNumberField(TEXT("avg134Index"), Avg134Index);
    Root->SetNumberField(TEXT("avg134Count"), HczsPrologueAvg134().Num());
    Root->SetStringField(TEXT("avg134Line"), Session && Session->bAvg134Pending ? HczsPrologueAvg134Line(FMath::Max(Avg134Index, 0), PlayerName()) : FString());
    Root->SetNumberField(TEXT("pressSerial"), static_cast<double>(PressSerial));
    Root->SetStringField(TEXT("lastPressAction"), LastPressAction);
    TArray<TSharedPtr<FJsonValue>> Actions;
    for (const FControl& Control : Controls)
        if (Control.bEnabled) Actions.Add(MakeShared<FJsonValueString>(Control.Action));
    Root->SetArrayField(TEXT("enabledControls"), Actions);
    FString Out;
    FJsonSerializer::Serialize(Root, TJsonWriterFactory<>::Create(&Out));
    return Out;
}

FReply UHczsDungeonWidget::NativeOnMouseButtonDown(const FGeometry& Geometry, const FPointerEvent& Event)
{
    return Event.GetEffectingButton() == EKeys::LeftMouseButton ? PressAt(Geometry, Event.GetScreenSpacePosition()) : FReply::Unhandled();
}

FReply UHczsDungeonWidget::NativeOnTouchStarted(const FGeometry& Geometry, const FPointerEvent& Event)
{
    return PressAt(Geometry, Event.GetScreenSpacePosition());
}

FReply UHczsDungeonWidget::NativeOnKeyDown(const FGeometry& Geometry, const FKeyEvent& Event)
{
    if (Event.GetKey() == EKeys::Escape)
    {
        OnBackRequested.Broadcast();
        return FReply::Handled();
    }
    return Super::NativeOnKeyDown(Geometry, Event);
}
