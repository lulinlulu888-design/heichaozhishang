#include "HczsHallHeroPresentation.h"
#include "HczsGameInstance.h"
#include "Animation/AnimSequence.h"
#include "Animation/SkeletalMeshActor.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Materials/MaterialInterface.h"

AHczsHallHeroPresentation::AHczsHallHeroPresentation()
{
    PrimaryActorTick.bCanEverTick = false;
}

void AHczsHallHeroPresentation::BeginPlay()
{
    Super::BeginPlay();
    Session = Cast<UHczsGameInstance>(GetGameInstance());
    USkeletalMesh* BaseMesh = Catalog ? Catalog->BaseMesh.LoadSynchronous() : nullptr;
    if (BaseMesh)
    {
        for (TActorIterator<ASkeletalMeshActor> It(GetWorld()); It; ++It)
        {
            if (It->GetSkeletalMeshComponent()->GetSkeletalMeshAsset() != BaseMesh) continue;
            if (BaseHero) { BaseHero = nullptr; LastProblem = TEXT("大厅角色锚点不唯一。"); break; }
            BaseHero = *It;
        }
    }
    if (!Catalog || !BaseHero)
    {
        if (LastProblem.IsEmpty()) LastProblem = TEXT("大厅角色资源尚未载入。");
        UE_LOG(LogTemp, Error, TEXT("HCZS hall hero: %s"), *LastProblem);
        return;
    }
    DisplayedHeroId = 1;
    if (Session) StateHandle = Session->OnStateChangedNative.AddUObject(this, &AHczsHallHeroPresentation::SessionChanged);
    SessionChanged();
}

void AHczsHallHeroPresentation::SessionChanged()
{
    // A PATCH receipt is followed by an authoritative GET in GameInstance.
    // Pending requests never preview or commit a different display selection.
    if (!Session || !Session->IsHallSceneReady()) return;
    const int32 Requested = Session->HallPreference.SelectedHeroId == 0 ? 1 : Session->HallPreference.SelectedHeroId;
    if (Requested == DisplayedHeroId) { LastProblem.Reset(); return; }
    if (!ApplyHero(Requested))
        UE_LOG(LogTemp, Warning, TEXT("HCZS hall hero requested=%d displayed=%d: %s"), Requested, DisplayedHeroId, *LastProblem);
}

bool AHczsHallHeroPresentation::ApplyHero(int32 HeroId)
{
    if (!IsValid(BaseHero) || !Catalog) { LastProblem = TEXT("大厅角色锚点已失效。"); return false; }
    if (HeroId == 1)
    {
        if (Replacement) { Replacement->Destroy(); Replacement = nullptr; }
        BaseHero->SetActorHiddenInGame(false);
        DisplayedHeroId = 1;
        LastProblem.Reset();
        UE_LOG(LogTemp, Display, TEXT("HCZS hall hero displayed=1"));
        return true;
    }
    const FHczsHallHeroVisual* Visual = Catalog->Heroes.Find(HeroId);
    if (!Visual) { LastProblem = TEXT("该角色尚未接入当前大厅显示。"); return false; }
    USkeletalMesh* Mesh = Visual->Mesh.LoadSynchronous();
    UAnimSequence* Idle = Visual->Idle.LoadSynchronous();
    if (!Mesh || !Idle || Mesh->GetSkeleton() != Idle->GetSkeleton() || Visual->Materials.Num() != Mesh->GetMaterials().Num())
    { LastProblem = TEXT("角色模型、动作或材质未完整载入。"); return false; }
    TArray<UMaterialInterface*> Materials;
    for (const auto& Reference : Visual->Materials)
    {
        UMaterialInterface* Material = Reference.LoadSynchronous();
        if (!Material) { LastProblem = TEXT("角色材质未完整载入。"); return false; }
        Materials.Add(Material);
    }
    if (Catalog->BaseSourceScale.GetMin() <= 0 || Visual->SourceScale.GetMin() <= 0)
    { LastProblem = TEXT("角色缩放配置无效。"); return false; }
    FTransform Transform = BaseHero->GetActorTransform();
    Transform.SetScale3D(Transform.GetScale3D() / Catalog->BaseSourceScale * Visual->SourceScale);
    FActorSpawnParameters Parameters;
    Parameters.Owner = this;
    Parameters.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    ASkeletalMeshActor* Candidate = GetWorld()->SpawnActor<ASkeletalMeshActor>(ASkeletalMeshActor::StaticClass(), Transform, Parameters);
    if (!Candidate) { LastProblem = TEXT("无法创建大厅角色。"); return false; }
    USkeletalMeshComponent* Component = Candidate->GetSkeletalMeshComponent();
    Component->SetSkeletalMeshAsset(Mesh);
    for (int32 Slot = 0; Slot < Materials.Num(); ++Slot) Component->SetMaterial(Slot, Materials[Slot]);
    Component->SetCastShadow(false);
    Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Component->PlayAnimation(Idle, true);
    // Publish only after all assets are valid, preserving the old actor on error.
    if (Replacement) Replacement->Destroy();
    Replacement = Candidate;
    BaseHero->SetActorHiddenInGame(true);
    DisplayedHeroId = HeroId;
    LastProblem.Reset();
    UE_LOG(LogTemp, Display, TEXT("HCZS hall hero displayed=%d source=%s"), HeroId, *Visual->SourceGlbSha256);
    return true;
}

void AHczsHallHeroPresentation::EndPlay(const EEndPlayReason::Type Reason)
{
    if (Session && StateHandle.IsValid()) Session->OnStateChangedNative.Remove(StateHandle);
    if (Replacement) { Replacement->Destroy(); Replacement = nullptr; }
    Super::EndPlay(Reason);
}
