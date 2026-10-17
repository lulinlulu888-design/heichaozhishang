#pragma once

#include "CoreMinimal.h"
#include "HczsHallWidget.h"
#include "HczsDungeonWidget.generated.h"

/** Original MainLineDungeonPanel info area over the recovered chess map. */
UCLASS()
class HCZS_API UHczsDungeonWidget : public UUserWidget
{
    GENERATED_BODY()
public:
    FHczsHallEntryRequested OnBackRequested;
    FHczsHallEntryRequested OnExploreRequested;
    /** Isolated UI tests only: routes a real Slate pointer press to the painted control centre. */
    UFUNCTION(BlueprintCallable, Category="HCZS|Development") bool DevelopmentPressControl(const FString& Action);
    UFUNCTION(BlueprintCallable, Category="HCZS|Development") FString DevelopmentDescribe() const;
protected:
    virtual void NativeConstruct() override;
    virtual int32 NativePaint(const FPaintArgs& Args, const FGeometry& Geometry,
        const FSlateRect& CullingRect, FSlateWindowElementList& Elements, int32 LayerId,
        const FWidgetStyle& Style, bool bParentEnabled) const override;
    virtual FReply NativeOnMouseButtonDown(const FGeometry& Geometry, const FPointerEvent& Event) override;
    virtual FReply NativeOnTouchStarted(const FGeometry& Geometry, const FPointerEvent& Event) override;
    virtual FReply NativeOnKeyDown(const FGeometry& Geometry, const FKeyEvent& Event) override;
private:
    FReply PressAt(const FGeometry& Geometry, const FVector2D& AbsolutePosition);
    UPROPERTY() TObjectPtr<UHczsHallLayoutAsset> Layout;
    TArray<FHczsHallDrawItem> Items;
    TArray<bool> ItemWrap;
    struct FControl { FString Action; FVector2f Size = FVector2f::ZeroVector; FSlateRenderTransform Transform; bool bEnabled = false; };
    TArray<FControl> Controls;
    bool bSourceReady = false;
    int32 Avg138Index = -1;
    uint64 PressSerial = 0;
    FString LastPressAction;
};
