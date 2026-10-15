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

/** Source-style temporary hall preview with explicit confirmation. */
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
    UPROPERTY(BlueprintReadOnly) bool bPreviewActive = false;
    UPROPERTY(BlueprintReadOnly) bool bPreviewSaving = false;
    UFUNCTION(BlueprintCallable) bool BeginPreview();
    UFUNCTION(BlueprintCallable) bool PreviewHero(int32 HeroId);
    UFUNCTION(BlueprintCallable) bool ConfirmPreview();
    UFUNCTION(BlueprintCallable) bool CancelPreview();
private:
    void SessionChanged();
    bool ApplyHero(int32 HeroId);
    UPROPERTY() TObjectPtr<UHczsGameInstance> Session;
    UPROPERTY() TObjectPtr<ASkeletalMeshActor> BaseHero;
    UPROPERTY() TObjectPtr<ASkeletalMeshActor> Replacement;
    FDelegateHandle StateHandle;
    FString PreviewProfile;
    int32 ConfirmedHeroId = 1;
    int32 SavingHeroId = 0;
    int64 PreviewRevision = 0;
};
