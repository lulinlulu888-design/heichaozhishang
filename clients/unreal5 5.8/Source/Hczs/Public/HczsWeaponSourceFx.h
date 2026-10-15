#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "HczsWeaponSourceFx.generated.h"

class USkeletalMeshComponent;
class USceneComponent;
class UStaticMeshComponent;
class UMaterialInstanceDynamic;

/** Original weapon001/lancer2 overlay only, not the separate weapon_dao SFX group. */
UCLASS(ClassGroup=(HCZS))
class HCZS_API UHczsWeaponSourceFx : public UActorComponent
{
    GENERATED_BODY()
public:
    UHczsWeaponSourceFx();

    /** The imported overlay must already be in the original prop1 local space. */
    UFUNCTION(BlueprintCallable, Category="HCZS|Recovered|WeaponFX")
    bool Initialise(USkeletalMeshComponent* Player, AActor* WeaponActor);

    UFUNCTION(BlueprintCallable, Category="HCZS|Recovered|WeaponFX") void Release();
    UFUNCTION(BlueprintPure, Category="HCZS|Recovered|WeaponFX") bool IsReady() const;
    UFUNCTION(BlueprintPure, Category="HCZS|Recovered|WeaponFX") FString GetProblem() const { return Problem; }
    UFUNCTION(BlueprintPure, Category="HCZS|Recovered|WeaponFX") UStaticMeshComponent* GetOverlayComponent() const { return Overlay; }
    UFUNCTION(BlueprintPure, Category="HCZS|Recovered|WeaponFX") UMaterialInstanceDynamic* GetDynamicMaterial() const { return FlowMaterial; }
    UFUNCTION(BlueprintPure, Category="HCZS|Recovered|WeaponFX") float GetEffectTime() const { return EffectTime; }
    UFUNCTION(BlueprintPure, Category="HCZS|Development") FString DevelopmentDescribe() const;

    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
    virtual void OnComponentDestroyed(bool bDestroyingHierarchy) override;

private:
    bool Synchronise();
    bool Fail(const FString& Reason);
    void DestroyOverlay();

    UPROPERTY(Transient) TWeakObjectPtr<USkeletalMeshComponent> SourcePlayer;
    UPROPERTY(Transient) TWeakObjectPtr<AActor> SourceWeapon;
    UPROPERTY(Transient) TWeakObjectPtr<USceneComponent> SourceWeaponRoot;
    UPROPERTY(Transient) TObjectPtr<UStaticMeshComponent> Overlay;
    UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> FlowMaterial;
    UPROPERTY(Transient) FString Problem = TEXT("武器流光尚未初始化。");
    float EffectTime = 0;
    bool bReady = false;
    bool bEndingPlay = false;
};
