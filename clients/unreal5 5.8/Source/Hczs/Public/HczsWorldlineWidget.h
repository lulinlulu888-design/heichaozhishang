#pragma once

#include "CoreMinimal.h"
#include "HczsHallWidget.h"
#include "HczsWorldlineWidget.generated.h"

struct FHczsWorldlineSourceControl
{
    FString Action;
    FVector2f Size = FVector2f::ZeroVector;
    FSlateRenderTransform Transform;
    bool bEnabled = false;
};

/** Original MainLineStoryDialog static page, with no invented chapter progress. */
UCLASS()
class HCZS_API UHczsWorldlineWidget : public UUserWidget
{
    GENERATED_BODY()
public:
    FHczsHallEntryRequested OnBackRequested;
    FHczsHallEntryRequested OnLocalBattlePreviewRequested;
    /** Development read-only source preview; cannot submit a game intent. */
    void SetSourceInspection(bool bInspect);
    /** Nonshipping isolated acceptance only; routes down/up through its real Slate hit path. */
    bool DevelopmentClickControl(const FString& Action, bool bTouch = false);
    /** Read-only last actual paint diagnostic, never a claim of original runtime. */
    FString DevelopmentDescribeUI() const;
protected:
    virtual void NativeConstruct() override;
    virtual int32 NativePaint(const FPaintArgs& Args, const FGeometry& Geometry,
        const FSlateRect& CullingRect, FSlateWindowElementList& Elements, int32 LayerId,
        const FWidgetStyle& Style, bool bParentEnabled) const override;
    virtual FReply NativeOnMouseButtonDown(const FGeometry& Geometry, const FPointerEvent& Event) override;
    virtual FReply NativeOnTouchStarted(const FGeometry& Geometry, const FPointerEvent& Event) override;
    virtual FReply NativeOnKeyDown(const FGeometry& Geometry, const FKeyEvent& Event) override;
private:
    FReply PressAt(const FGeometry& Geometry, const FVector2D& AbsolutePosition, bool bTouch);
    UPROPERTY() TObjectPtr<UHczsHallLayoutAsset> Layout;
    TArray<FHczsHallDrawItem> Items;
    TArray<FString> ItemSpriteIds;
    TArray<FHczsWorldlineSourceControl> SourceControls;
    FSlateFontInfo AdapterFont;
    bool bSourceReady = false;
    bool bSourceFontReady = false;
    bool bSourceInspection = false;
    FSlateRect LocalPreviewRect = FSlateRect(985, 651, 1215, 698);
    mutable uint64 PaintSerial = 0;
    mutable TArray<FString> LastPaintedTexts;
    mutable TArray<FString> LastPaintedSpriteIds;
    mutable TArray<FHczsWorldlineSourceControl> LastPaintedControls;
    mutable FGeometry LastPaintGeometry;
    mutable FString LastPaintedMap;
    uint64 PointerSerial = 0;
    FString LastPointerAction;
    bool bLastPointerTouch = false;
    FVector2f LastPointerPoint = FVector2f::ZeroVector;
    FString Notice;
};
