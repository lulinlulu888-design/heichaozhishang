#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "HczsEntranceSourceFx.generated.h"

class USkeletalMeshComponent;
class UStaticMeshComponent;
class UMaterialInstanceDynamic;

/** One model layer of fight_idle_show_chuchang.sfx: UE world-axis offset from the player origin. */
struct HCZS_API FHczsEntranceFxSample
{
    bool bActive = false;
    FVector Location = FVector::ZeroVector;
    FVector Scale = FVector::OneVector;
    FLinearColor Tint = FLinearColor::Black;
    float Alpha = 0;
    bool bHasDissolve = false;
    float Dissolve = 0;
    bool bHasStrength = false;
    float Strength = 0;
};

HCZS_API int32 HczsEntranceFxLayerCount();
HCZS_API FString HczsEntranceFxLayerModel(int32 Layer);
HCZS_API FString HczsEntranceFxLayerSource(int32 Layer);
/** Seconds since the source event_1 cue; reconstruction semantics are documented in the table. */
HCZS_API FHczsEntranceFxSample HczsSampleEntranceFx(int32 Layer, float Seconds);
HCZS_API float HczsEntranceFxDuration();
/** Off by default: the native SFX timeline is reconstructed from data, not verified against libclient. */
HCZS_API bool HczsEntranceFxReconstructionEnabled();

/**
 * Reconstruction of the three exported model layers of fight_idle_show_chuchang.sfx.
 * Sprites, particle systems, FxCamera shake and the energy column are not played.
 */
UCLASS(ClassGroup=(HCZS))
class HCZS_API UHczsEntranceSourceFx : public UActorComponent
{
    GENERATED_BODY()
public:
    UHczsEntranceSourceFx();

    bool Play(USkeletalMeshComponent* Player, const FString& BattleId);
    void Stop(const FString& Reason);
    UFUNCTION(BlueprintPure, Category="HCZS|Recovered|EntranceFX") bool IsPlaying() const { return bPlaying; }
    UFUNCTION(BlueprintPure, Category="HCZS|Development") FString DevelopmentDescribe() const;

    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
    void Apply(float Seconds);
    void DestroyLayers();

    UPROPERTY(Transient) TArray<TObjectPtr<UStaticMeshComponent>> Layers;
    UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInstanceDynamic>> Materials;
    TWeakObjectPtr<USkeletalMeshComponent> SourcePlayer;
    FString BattleId;
    FString Outcome = TEXT("idle");
    double StartWorldTime = -1.0;
    float LastSeconds = 0;
    int32 PlayCount = 0;
    int32 MaxActiveLayers = 0;
    bool bPlaying = false;
};
