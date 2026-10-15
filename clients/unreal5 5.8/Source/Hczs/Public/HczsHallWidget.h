#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "Blueprint/UserWidget.h"
#include "Styling/SlateBrush.h"
#include "Fonts/SlateFontInfo.h"
#include "Layout/Clipping.h"
#include "HczsHallWidget.generated.h"

class UTexture2D;
class UFontFace;
class AHczsHallHeroPresentation;
DECLARE_MULTICAST_DELEGATE(FHczsHallEntryRequested);

/** Generated from verified original CSB layouts and extracted APK images/fonts. */
UCLASS()
class HCZS_API UHczsHallLayoutAsset : public UDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere, Category="Recovered") FString LayoutJson;
    UPROPERTY(EditAnywhere, Category="Recovered") FString SourceLayoutSha256;
    UPROPERTY(EditAnywhere, Category="Recovered") TMap<FString, TObjectPtr<UTexture2D>> Sprites;
    UPROPERTY(EditAnywhere, Category="Recovered") TMap<FString, TObjectPtr<UFontFace>> Fonts;
};

struct FHczsHallDrawItem
{
    bool bText = false;
    FVector2f Size = FVector2f::ZeroVector;
    FSlateRenderTransform Transform;
    FSlateBrush Brush;
    FSlateFontInfo Font;
    FLinearColor Color = FLinearColor::White;
    FString Text;
    int32 HorizontalAlignment = 0;
    int32 VerticalAlignment = 0;
    bool bShadow = false;
    FVector2f ShadowOffset = FVector2f::ZeroVector;
    FLinearColor ShadowColor;
    TArray<FSlateClippingZone> Clips;
    int32 HeroId = 0;
    bool bSelectedOnly = false;
};

/** Source-layout presentation only; no original login or economy simulation. */
UCLASS()
class HCZS_API UHczsHallWidget : public UUserWidget
{
    GENERATED_BODY()
public:
    FHczsHallEntryRequested OnProfileRequested;
    FHczsHallEntryRequested OnWorldlineRequested;
    /** Software pointer route to a previously painted real hall hitbox. */
    UFUNCTION(BlueprintCallable, Category="HCZS|Test") bool DevelopmentClickControl(const FString& Action, bool bTouch = false);
    UFUNCTION(BlueprintCallable, Category="HCZS|Test") FString DevelopmentDescribeUI() const;
    UFUNCTION(BlueprintCallable, Category="HCZS|Test") bool DevelopmentCaptureFrame(const FString& Filename);
protected:
    virtual void NativeConstruct() override;
    virtual int32 NativePaint(const FPaintArgs& Args, const FGeometry& Geometry,
        const FSlateRect& CullingRect, FSlateWindowElementList& Elements, int32 LayerId,
        const FWidgetStyle& Style, bool bParentEnabled) const override;
    virtual FReply NativeOnMouseButtonDown(const FGeometry& Geometry, const FPointerEvent& Event) override;
    virtual FReply NativeOnTouchStarted(const FGeometry& Geometry, const FPointerEvent& Event) override;
private:
    void LoadDrawItems(UHczsHallLayoutAsset* Source, TArray<FHczsHallDrawItem>& Destination, bool bHallBindings);
    AHczsHallHeroPresentation* HeroPresenter() const;
    FReply PressAt(const FGeometry& Geometry, const FVector2D& AbsolutePosition, bool bTouch);
    UPROPERTY() TObjectPtr<UHczsHallLayoutAsset> Layout;
    TArray<FHczsHallDrawItem> Items;
    UPROPERTY() TObjectPtr<UHczsHallLayoutAsset> PickerLayout;
    TArray<FHczsHallDrawItem> PickerItems;
    TMap<FString, FSlateRect> PickerControls;
    TMap<int32, FString> PickerHeroes;
    FVector2f DesignSize = FVector2f(1280, 720);
    FVector2f WorldlineSize = FVector2f::ZeroVector;
    FSlateRenderTransform WorldlineTransform;
    bool bHasWorldline = false;
    FSlateFontInfo ProfileFont;
    bool bProfileFontReady = false;
    FSlateRect ProfileRect = FSlateRect(22, 18, 258, 56);
    FSlateRect HeroEntryRect = FSlateRect(270, 18, 460, 56);
    mutable FGeometry LastPaintGeometry;
    mutable bool bHasPaintGeometry = false;
    mutable uint64 PaintSerial = 0;
    mutable TArray<FString> LastPaintedTexts;
    uint64 PointerSerial = 0;
    FString LastPointerAction;
    bool bLastPointerTouch = false;
};
