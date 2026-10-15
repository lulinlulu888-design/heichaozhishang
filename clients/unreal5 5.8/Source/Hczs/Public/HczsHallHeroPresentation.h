#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "GameFramework/Actor.h"
#include "HczsHallHeroPresentation.generated.h"

class USkeletalMesh;
class UAnimSequence;
class UMaterialInterface;
class ASkeletalMeshActor;
class UHczsGameInstance;

USTRUCT(BlueprintType)
struct FHczsHallHeroVisual
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere) FString Name;
    UPROPERTY(EditAnywhere) FString SourceGlbSha256;
    UPROPERTY(EditAnywhere) TSoftObjectPtr<USkeletalMesh> Mesh;
    UPROPERTY(EditAnywhere) TSoftObjectPtr<UAnimSequence> Idle;
    UPROPERTY(EditAnywhere) TArray<TSoftObjectPtr<UMaterialInterface>> Materials;
    UPROPERTY(EditAnywhere) FVector SourceScale = FVector::OneVector;
};

/** Reviewed source recovery inputs; independent of ownership or battle party. */
UCLASS()
class HCZS_API UHczsHallHeroCatalogAsset : public UDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere) FString SourceEvidenceSha256;
    UPROPERTY(EditAnywhere) TSoftObjectPtr<USkeletalMesh> BaseMesh;
    UPROPERTY(EditAnywhere) FVector BaseSourceScale = FVector::OneVector;
    UPROPERTY(EditAnywhere) TMap<int32, FHczsHallHeroVisual> Heroes;
};

/** Display a confirmed hall preference; never selects/saves a hero itself. */
UCLASS()
class HCZS_API AHczsHallHeroPresentation : public AActor
{
    GENERATED_BODY()
public:
    AHczsHallHeroPresentation();
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    UPROPERTY(EditAnywhere) TObjectPtr<UHczsHallHeroCatalogAsset> Catalog;
    UPROPERTY(BlueprintReadOnly) int32 DisplayedHeroId = 0;
    UPROPERTY(BlueprintReadOnly) FString LastProblem;
private:
    void SessionChanged();
    bool ApplyHero(int32 HeroId);
    UPROPERTY() TObjectPtr<UHczsGameInstance> Session;
    UPROPERTY() TObjectPtr<ASkeletalMeshActor> BaseHero;
    UPROPERTY() TObjectPtr<ASkeletalMeshActor> Replacement;
    FDelegateHandle StateHandle;
};
