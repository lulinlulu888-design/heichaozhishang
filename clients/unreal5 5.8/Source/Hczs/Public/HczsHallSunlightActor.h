#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "HczsHallSunlightActor.generated.h"

class UMaterialInterface;
class UMaterialInstanceDynamic;
class UStaticMeshComponent;

/** Original home sunlight texture/colour keys with a bounded UE preview simulation. */
UCLASS()
class HCZS_API AHczsHallSunlightActor : public AActor
{
    GENERATED_BODY()
public:
    AHczsHallSunlightActor();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;

    UPROPERTY(EditAnywhere, Category="Recovered Sunlight")
    TObjectPtr<UMaterialInterface> ParticleMaterial;

    UPROPERTY(EditAnywhere, Category="Recovered Sunlight")
    FVector OriginalEmitterPosition = FVector::ZeroVector;

    UPROPERTY(EditAnywhere, Category="Recovered Sunlight")
    FVector PreviewHalfExtents = FVector(420, 100, 350);

    UPROPERTY(EditAnywhere, Category="Recovered Sunlight")
    float ParticlesPerSecond = 10;

    UPROPERTY(EditAnywhere, Category="Recovered Sunlight")
    float MinimumLifespan = 1.5f;

    UPROPERTY(EditAnywhere, Category="Recovered Sunlight")
    float MaximumLifespan = 2.f;

    UPROPERTY(EditAnywhere, Category="Recovered Sunlight")
    float MinimumRadiusCm = 5.85022f;

    UPROPERTY(EditAnywhere, Category="Recovered Sunlight")
    float MaximumRadiusCm = 17.55066f;

    UPROPERTY(EditAnywhere, Category="Recovered Sunlight")
    float PreviewIntensity = 4.f;

    UPROPERTY(EditAnywhere, Category="Recovered Sunlight")
    TArray<float> SourceColorTimes;

    UPROPERTY(EditAnywhere, Category="Recovered Sunlight")
    TArray<FLinearColor> SourceParticleColors;

    UPROPERTY(EditAnywhere, Category="Recovered Sunlight")
    FString SourceEffectSha256;

private:
    struct FPreviewParticle
    {
        bool bActive = false;
        float Age = 0;
        float Lifespan = 1;
        float Radius = 1;
        FVector Position = FVector::ZeroVector;
        FVector Velocity = FVector::ZeroVector;
    };

    static constexpr int32 ParticleLimit = 20;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> ParticlePlanes;
    UPROPERTY() TArray<TObjectPtr<UMaterialInstanceDynamic>> ParticleMaterials;
    TArray<FPreviewParticle> ParticleState;
    FRandomStream Random;
    float SpawnRemainder = 0;
    double StatisticsElapsed = 0;
    bool bLoggedSteadyState = false;
    void SpawnParticle();
    FLinearColor SampleSourceParticleColor(float NormalizedAge) const;
};
