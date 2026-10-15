#include "HczsHallSunlightActor.h"

#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"

AHczsHallSunlightActor::AHczsHallSunlightActor()
{
    PrimaryActorTick.bCanEverTick = true;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("SunlightRoot"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Plane(TEXT("/Engine/BasicShapes/Plane.Plane"));
    for (int32 Index = 0; Index < ParticleLimit; ++Index)
    {
        const FName Name(*FString::Printf(TEXT("OriginalTextureParticle_%02d"), Index));
        UStaticMeshComponent* Mesh = CreateDefaultSubobject<UStaticMeshComponent>(Name);
        Mesh->SetupAttachment(RootComponent);
        Mesh->SetMobility(EComponentMobility::Movable);
        Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Mesh->SetGenerateOverlapEvents(false);
        Mesh->SetCastShadow(false);
        Mesh->SetVisibility(false);
        if (Plane.Succeeded())
        {
            Mesh->SetStaticMesh(Plane.Object);
        }
        ParticlePlanes.Add(Mesh);
    }
}

void AHczsHallSunlightActor::BeginPlay()
{
    Super::BeginPlay();
    ParticleState.SetNum(ParticleLimit);
    Random.Initialize(148274);
    if (!ParticleMaterial || SourceColorTimes.Num() != 7 || SourceParticleColors.Num() != SourceColorTimes.Num())
    {
        UE_LOG(LogTemp, Error, TEXT("HCZS: sunlight preview requires original texture material and seven source colour keys"));
        SetActorTickEnabled(false);
        return;
    }
    for (int32 Index = 0; Index < SourceColorTimes.Num(); ++Index)
    {
        if (!FMath::IsFinite(SourceColorTimes[Index]) ||
            (Index > 0 && SourceColorTimes[Index] <= SourceColorTimes[Index - 1]) ||
            (!FMath::IsFinite(SourceParticleColors[Index].R) || !FMath::IsFinite(SourceParticleColors[Index].G) ||
             !FMath::IsFinite(SourceParticleColors[Index].B) || !FMath::IsFinite(SourceParticleColors[Index].A)))
        {
            UE_LOG(LogTemp, Error, TEXT("HCZS: sunlight source colour curve is invalid"));
            SetActorTickEnabled(false);
            return;
        }
    }
    for (int32 Index = 0; Index < ParticleLimit; ++Index)
    {
        UMaterialInstanceDynamic* Dynamic = UMaterialInstanceDynamic::Create(ParticleMaterial, this);
        ParticleMaterials.Add(Dynamic);
        ParticlePlanes[Index]->SetMaterial(0, Dynamic);
        Dynamic->SetScalarParameterValue(TEXT("PreviewIntensity"), PreviewIntensity);
    }
    UE_LOG(LogTemp, Display, TEXT("HCZS: source sunlight preview ready; original texture, 20 cap, rate %.1f/s, lifespan %.2f-%.2f; emission box/interpolation/blend are temporary UE adaptations; source=%s"),
        ParticlesPerSecond, MinimumLifespan, MaximumLifespan, *SourceEffectSha256);
}

void AHczsHallSunlightActor::SpawnParticle()
{
    for (FPreviewParticle& Particle : ParticleState)
    {
        if (!Particle.bActive)
        {
            Particle.bActive = true;
            Particle.Age = 0;
            Particle.Lifespan = Random.FRandRange(MinimumLifespan, MaximumLifespan);
            Particle.Radius = Random.FRandRange(MinimumRadiusCm, MaximumRadiusCm);
            Particle.Position = GetActorLocation() + FVector(
                Random.FRandRange(-PreviewHalfExtents.X, PreviewHalfExtents.X),
                Random.FRandRange(-PreviewHalfExtents.Y, PreviewHalfExtents.Y),
                Random.FRandRange(-PreviewHalfExtents.Z, PreviewHalfExtents.Z));
            // Do not silently swap the original reversed Min=1/Max=-1 speed
            // fields. Gentle drift is an explicit visual-inspection choice.
            Particle.Velocity = FVector(Random.FRandRange(-4.f, 4.f), Random.FRandRange(-3.f, 3.f), Random.FRandRange(3.f, 8.f));
            return;
        }
    }
}

FLinearColor AHczsHallSunlightActor::SampleSourceParticleColor(float NormalizedAge) const
{
    if (NormalizedAge <= SourceColorTimes[0])
    {
        return SourceParticleColors[0];
    }
    for (int32 Index = 1; Index < SourceColorTimes.Num(); ++Index)
    {
        if (NormalizedAge <= SourceColorTimes[Index])
        {
            const float Blend = (NormalizedAge - SourceColorTimes[Index - 1]) /
                (SourceColorTimes[Index] - SourceColorTimes[Index - 1]);
            return FMath::Lerp(SourceParticleColors[Index - 1], SourceParticleColors[Index], Blend);
        }
    }
    return SourceParticleColors.Last();
}

void AHczsHallSunlightActor::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!FMath::IsFinite(DeltaSeconds) || DeltaSeconds <= 0 || ParticleMaterials.Num() != ParticleLimit)
    {
        return;
    }
    // A bounded step prevents a stall from producing a large invisible burst.
    const float Step = FMath::Min(DeltaSeconds, .25f);
    for (FPreviewParticle& Particle : ParticleState)
    {
        if (Particle.bActive)
        {
            Particle.Age += Step;
            Particle.bActive = Particle.Age < Particle.Lifespan;
            Particle.Position += Particle.Velocity * Step;
        }
    }
    SpawnRemainder += Step * FMath::Clamp(ParticlesPerSecond, 0.f, 10.f);
    const int32 Count = FMath::Min(FMath::FloorToInt(SpawnRemainder), ParticleLimit);
    SpawnRemainder -= Count;
    for (int32 Index = 0; Index < Count; ++Index)
    {
        SpawnParticle();
    }
    FVector ViewLocation;
    FRotator ViewRotation;
    APlayerController* Controller = GetWorld()->GetFirstPlayerController();
    if (!Controller)
    {
        return;
    }
    Controller->GetPlayerViewPoint(ViewLocation, ViewRotation);
    int32 ActiveCount = 0;
    for (int32 Index = 0; Index < ParticleLimit; ++Index)
    {
        const FPreviewParticle& Particle = ParticleState[Index];
        UStaticMeshComponent* Plane = ParticlePlanes[Index];
        Plane->SetVisibility(Particle.bActive);
        if (!Particle.bActive)
        {
            continue;
        }
        ++ActiveCount;
        Plane->SetWorldLocation(Particle.Position);
        // Engine Plane is in local XY; local +Z faces the camera. A flat
        // camera-facing plane avoids relying on any original DirType enum.
        Plane->SetWorldRotation(FRotationMatrix::MakeFromZ(ViewLocation - Particle.Position).Rotator());
        Plane->SetWorldScale3D(FVector(Particle.Radius * 2.f / 100.f));
        ParticleMaterials[Index]->SetVectorParameterValue(TEXT("SourceParticleColor"),
            SampleSourceParticleColor(Particle.Age / Particle.Lifespan));
    }
    StatisticsElapsed += Step;
    if (!bLoggedSteadyState && StatisticsElapsed >= 3)
    {
        UE_LOG(LogTemp, Display, TEXT("HCZS: sunlight preview steady state active=%d/20; camera-facing source-texture planes"), ActiveCount);
        bLoggedSteadyState = true;
    }
}
