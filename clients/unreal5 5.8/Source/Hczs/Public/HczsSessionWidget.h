#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Engine/DataAsset.h"
#include "Styling/SlateBrush.h"
#include "Fonts/SlateFontInfo.h"
#include "HczsSourceUiTimeline.h"
#include "HczsSessionWidget.generated.h"

class UTexture2D;
class UFontFace;
class UHczsGameInstance;
class UHczsWorldlineWidget;
namespace HczsUiAudio { enum class ECue : uint8; }

/** Original APK UI pixels and Chinese typeface, separate from runtime game state. */
UCLASS()
class HCZS_API UHczsBattlePresentationAsset : public UDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere, Category="Recovered") FString SourceManifestSha256;
    UPROPERTY(EditAnywhere, Category="Recovered") FString LayoutJson;
    UPROPERTY(EditAnywhere, Category="Recovered") TMap<FString, TObjectPtr<UTexture2D>> Sprites;
    UPROPERTY(EditAnywhere, Category="Recovered") TObjectPtr<UFontFace> ChineseFont;
};

struct FHczsSessionControl
{
    FString Action;
    FString Value;
    FSlateRect Rect;
    FSlateRenderTransform Transform;
    bool bTransformed = false;
    bool bEnabled = true;
};

struct FHczsCardGestureEvent
{
    FString Kind;
    FVector2f Point = FVector2f::ZeroVector;
    bool bTargetHit = false;
    float UpwardDelta = 0;
    int64 AtUnixMs = 0;
};

/** Playable reconstruction HUD; sends intents but never calculates game rules. */
UCLASS()
class HCZS_API UHczsSessionWidget : public UUserWidget
{
    GENERATED_BODY()
public:
    /** Hall buttons may open these panels; selecting a profile remains explicit. */
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void OpenProfileSelection();
    /** Original APK MainLineStoryDialog static page; no fabricated chapter state. */
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void OpenWorldlineSelection();
    /** Non-shipping, explicit -HczsWorldlineInspect source-only view; no profile selection. */
    void ShowWorldlineSourceInspection();
    /** Separate local battle-preview adapter, not the original worldline page. */
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void OpenEncounterSelection();
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void CloseSelection();
    /** Call before AddToViewport: true only in the actual recovered battle map. */
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void SetBattleScene(bool bInBattleScene);
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void SetSceneProblem(const FString& Reason);
    UFUNCTION(BlueprintCallable, Category="HCZS|Session") void SetPresentationBusy(bool bBusy);
    /** Development-only software pointer route. Requires explicit isolated UI-test flags. */
    UFUNCTION(BlueprintCallable, Category="HCZS|Test") bool DevelopmentClickControl(const FString& Action, const FString& Value = FString(), bool bTouch = false);
    /** Real down/move/up only; enemy/player/tap choose native scene bounds or the actual source hit. */
    UFUNCTION(BlueprintCallable, Category="HCZS|Test") bool DevelopmentDragCard(const FString& InstanceId, const FString& ReleaseTarget, bool bTouch = false,
        const FString& Phase = TEXT("begin"));
    /** Captures actual last paint controls/text/source texture references for acceptance. */
    UFUNCTION(BlueprintCallable, Category="HCZS|Test") FString DevelopmentDescribeUI() const;
    /** Explicit inspection-only original page paint observation for native screenshots. */
    FString DevelopmentDescribeWorldlineUI() const;
protected:
    virtual void NativeConstruct() override;
    virtual void NativeDestruct() override;
    virtual int32 NativePaint(const FPaintArgs& Args, const FGeometry& Geometry,
        const FSlateRect& CullingRect, FSlateWindowElementList& Elements, int32 LayerId,
        const FWidgetStyle& Style, bool bParentEnabled) const override;
    virtual FReply NativeOnMouseButtonDown(const FGeometry& Geometry, const FPointerEvent& Event) override;
    virtual FReply NativeOnMouseMove(const FGeometry& Geometry, const FPointerEvent& Event) override;
    virtual FReply NativeOnTouchStarted(const FGeometry& Geometry, const FPointerEvent& Event) override;
    virtual FReply NativeOnMouseButtonUp(const FGeometry& Geometry, const FPointerEvent& Event) override;
    virtual FReply NativeOnTouchMoved(const FGeometry& Geometry, const FPointerEvent& Event) override;
    virtual FReply NativeOnTouchEnded(const FGeometry& Geometry, const FPointerEvent& Event) override;
    virtual void NativeOnMouseCaptureLost(const FCaptureLostEvent& Event) override;
    virtual void NativeOnFocusLost(const FFocusEvent& Event) override;
    virtual FReply NativeOnKeyDown(const FGeometry& Geometry, const FKeyEvent& Event) override;
private:
    void SessionChanged();
    double FreshOpeningSeconds() const;
    void UpdateDealCues();
    void FinishRoundDeal(const FString& Reason);
    bool IsRoundDealActive() const { return !RoundDeal.Instances.IsEmpty(); }
    double RoundDealElapsed() const;
    void PlayUiCue(HczsUiAudio::ECue Cue, const FString& Reason);
    int32 PaintFreshOpening(const FGeometry& Canvas, FSlateWindowElementList& Elements, int32 Layer, double Seconds) const;
    FReply PressAt(const FGeometry& Geometry, const FPointerEvent& Event);
    void MoveCardGesture(const FGeometry& Geometry, const FPointerEvent& Event);
    FReply FinishCardGesture(const FGeometry& Geometry, const FPointerEvent& Event);
    void CancelCardGesture(const FString& Reason);
    bool CanDragCard(const FString& InstanceId) const;
    bool ProjectActorBounds(FName Tag, FSlateRect& DesignBounds) const;
    /** ModelUIArea anchors for the tagged enemy: model root and its root-relative ui_head socket, in design pixels. */
    bool ProjectEnemyHead(FVector2f& Root, FVector2f& Head) const;
    void RecordGestureEvent(const FString& Kind, const FVector2f& Point, bool bTargetHit = false);
    int32 PaintSourceTargetArrow(const FGeometry& Canvas, FSlateWindowElementList& Elements,
        int32 Layer, const FVector2f& Start, const FVector2f& End) const;
    void DispatchControl(const FHczsSessionControl& Control);
    void UpdateVisibility();
    void CloseWorldlineSelection();
    void OpenLocalPreviewFromWorldline();
    UPROPERTY() TObjectPtr<UHczsGameInstance> Session;
    UPROPERTY() TObjectPtr<UHczsBattlePresentationAsset> Presentation;
    UPROPERTY() TObjectPtr<UHczsBattlePresentationAsset> IconVariant;
    UPROPERTY() TObjectPtr<UHczsBattlePresentationAsset> EntrancePresentation;
    HczsSourceUiTimeline::FClip EliteOpening;
    TSharedPtr<class FJsonObject> EliteOpeningJson;
    mutable TArray<FString> LastOpeningNodes;
    mutable double LastOpeningSeconds = -1;
    mutable TArray<TSharedPtr<class FJsonValue>> LastDealtCards;
    /** FightMainPanel `In` and the nested OwnCardArea `In` it starts (FightPanel.onBattleStart). */
    HczsSourceUiTimeline::FClip HudIn, OwnCardIn;
    HczsSourceUiTimeline::FSample HudInRest, OwnCardInRest;
    mutable TSharedPtr<class FJsonObject> LastHudIn;
    /** Authoritative end-turn TurnStarted + CardDrawn cards replayed with the round-start _C_H flight. */
    struct FRoundDeal
    {
        FString BattleId;
        int64 ActionIndex = -1;
        int32 Round = 0;
        TArray<FString> Instances;
        double StartSeconds = -1;
    };
    FRoundDeal RoundDeal;
    FString HandledDealReceipt, LastRoundDealOutcome;
    FString OpeningCueBattle;
    bool bOpeningLandCuePlayed = false;
    int32 LastDrawCueVariant = -1;
    FRandomStream UiAudioRandom;
    TArray<TSharedPtr<class FJsonValue>> UiAudioLog;
    UPROPERTY() TObjectPtr<UHczsWorldlineWidget> WorldlineWidget;
    UPROPERTY() TArray<TObjectPtr<UObject>> TargetingResources;
    TSharedPtr<const FCompositeFont> CompositeFont;
    /** CommonRes/title.ttf, imported with the hall UI; NameLabelArea Txt uses it. */
    UPROPERTY() TObjectPtr<UFontFace> TitleFontFace;
    TSharedPtr<const FCompositeFont> TitleFont;
    /** FightCardEffects._showOperateUsableEffect fade start per hand card instance. */
    mutable TMap<FString, double> UsableOutlineSince;
    /** NameLabelArea._fadeIn start; negative while the label is hidden. */
    mutable double NameLabelSince = -1;
    /** IntentionItem.playAnimIn fade start for the current battle/round intent set. */
    mutable FString IntentionKey;
    mutable double IntentionSince = 0;
    TMap<FString, FSlateBrush> Brushes;
    /** ScaleXY/offsetXY maps full generated canvases onto original content bounds. */
    TMap<FString, FVector4f> IconDrawAdjustments;
    TMap<int32, TArray<FVector3f>> CardPlacements;
    FDelegateHandle StateChangedHandle;
    FTimerHandle DealTimer;
    mutable TArray<FHczsSessionControl> Controls;
    FString HoveredCard;
    int32 ProfilePage = 0;
    int32 BattlePage = 0;
    bool bProfilePanel = false;
    bool bEncounterPanel = false;
    bool bConfirmNewProfile = false;
    /** Set only by a user's explicit challenge-again click; consumed once. */
    bool bChallengeAfterScenario = false;
    FString RequestedChallengeEncounter;
    bool bBattleScene = false;
    bool bWorldlineInspection = false;
    bool bPresentationBusy = false;
    FString SceneProblem;
    mutable FGeometry LastPaintGeometry;
    mutable uint64 LastPaintSerial = 0;
    mutable TArray<FString> LastPaintedTexts;
    mutable TSet<FString> LastPaintedSprites;
    mutable FString LastPaintedMap;
    mutable bool bLastPaintedDragCue = false;
    uint64 PointerEventSerial = 0;
    FString LastPointerAction;
    FString LastPointerValue;
    bool bLastPointerTouch = false;
    FVector2f LastPointerPoint = FVector2f::ZeroVector;
    bool bCardGestureActive = false, bCardDraggedOut = false, bCardGestureTouch = false, bCardDetailOpen = false;
    int32 CardGesturePointer = -1, CardGestureUser = 0;
    FString CardGestureInstance, CardGestureBattle, SelectedCardInstance;
    int64 CardGestureRevision = 0;
    FVector2f CardGestureStart = FVector2f::ZeroVector, CardGesturePoint = FVector2f::ZeroVector;
    float CardGestureThreshold = 5;
    uint64 CardGestureSerial = 0;
    FString LastGestureOutcome, LastGestureReason, LastGestureTarget;
    TArray<FHczsCardGestureEvent> CardGestureEvents;
    FString CardGestureCardId;
    FSlateRect LastGestureTargetBounds = FSlateRect(0, 0, 0, 0);
    bool bLastGestureTargetBoundsValid = false, bLastGestureLostCapture = false;
    FVector2D DevelopmentDragAbsolute = FVector2D::ZeroVector;
};
