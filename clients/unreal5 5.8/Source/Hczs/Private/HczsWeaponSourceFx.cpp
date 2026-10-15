#include "HczsWeaponSourceFx.h"

#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace
{
    const FName OverlayTag(TEXT("HCZSWeaponSourceOverlay"));
    const FName TimeParameter(TEXT("EffectTime"));
    constexpr const TCHAR* MeshPath = TEXT("/Game/Recovered/Battle/Weapon/SourceFx/SM_WeaponOverlay.SM_WeaponOverlay");
    constexpr const TCHAR* MaterialPath = TEXT("/Game/Recovered/Battle/Weapon/SourceFx/M_WeaponFlow.M_WeaponFlow");

    bool ChainVisible(const USceneComponent* Component)
    {
        // Include parent component and actor flags. Attachment alone does not
        // propagate a different actor's SetActorHiddenInGame to this owner.
        int32 Depth = 0;
        for (auto* Current = Component; Current; Current = Current->GetAttachParent())
        {
            const auto* Actor = Current->GetOwner();
            if (++Depth > 128 || !IsValid(Current) || !Current->IsRegistered() ||
                !Current->GetVisibleFlag() || Current->bHiddenInGame ||
                !IsValid(Actor) || Actor->IsActorBeingDestroyed() || Actor->IsHidden()) return false;
        }
        return Component != nullptr;
    }

    TArray<TSharedPtr<FJsonValue>> Numbers(std::initializer_list<double> Values)
    {
        TArray<TSharedPtr<FJsonValue>> Result;
        for (const double Value : Values) Result.Add(MakeShared<FJsonValueNumber>(Value));
        return Result;
    }

    TSharedRef<FJsonObject> TransformJson(const FTransform& Transform)
    {
        auto Result = MakeShared<FJsonObject>();
        const FVector Position = Transform.GetTranslation(), Scale = Transform.GetScale3D();
        const FQuat Rotation = Transform.GetRotation();
        Result->SetArrayField(TEXT("translation"), Numbers({Position.X, Position.Y, Position.Z}));
        Result->SetArrayField(TEXT("rotation"), Numbers({Rotation.X, Rotation.Y, Rotation.Z, Rotation.W}));
        Result->SetArrayField(TEXT("scale"), Numbers({Scale.X, Scale.Y, Scale.Z}));
        return Result;
    }

    FString ObjectPath(const UObject* Object) { return IsValid(Object) ? Object->GetPathName() : FString(); }
}

UHczsWeaponSourceFx::UHczsWeaponSourceFx()
{
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.bStartWithTickEnabled = false;
    // Keep visibility/lifetime cleanup responsive during pause; EffectTime is
    // still sampled from paused world time, never from real time or DeltaTime.
    PrimaryComponentTick.bTickEvenWhenPaused = true;
    PrimaryComponentTick.TickGroup = TG_PostUpdateWork;
}

bool UHczsWeaponSourceFx::IsReady() const
{
    return bReady && !bEndingPlay && IsValid(Overlay) && Overlay->IsRegistered() &&
        IsValid(FlowMaterial) && SourcePlayer.IsValid() && SourceWeapon.IsValid() && SourceWeaponRoot.IsValid();
}

bool UHczsWeaponSourceFx::Fail(const FString& Reason)
{
    DestroyOverlay();
    Problem = Reason;
    UE_LOG(LogTemp, Warning, TEXT("HCZS weapon source overlay unavailable: %s"), *Reason);
    return false;
}

bool UHczsWeaponSourceFx::Initialise(USkeletalMeshComponent* Player, AActor* WeaponActor)
{
    if (!IsInGameThread()) return false;
    auto* Owner = GetOwner();
    auto* Root = IsValid(WeaponActor) ? WeaponActor->GetRootComponent() : nullptr;
    if (bEndingPlay || !IsRegistered() || !IsValid(Owner) || Owner->IsActorBeingDestroyed() ||
        !GetWorld() || !IsValid(Player) || !Player->IsRegistered() || !IsValid(WeaponActor) ||
        WeaponActor->IsActorBeingDestroyed() || !IsValid(Root) || !Root->IsRegistered() ||
        Player->GetWorld() != GetWorld() || WeaponActor->GetWorld() != GetWorld())
        return Fail(TEXT("武器流光需要当前世界中已注册的角色、武器和所属组件。"));
    if (Root->GetAttachParent() != Player || Root->GetAttachSocketName().IsNone() ||
        !Player->DoesSocketExist(Root->GetAttachSocketName()) || Root->GetRelativeTransform().ContainsNaN())
        return Fail(TEXT("原武器的角色骨骼挂接或相对变换无效，未增加任何位置补偿。"));

    if (IsReady() && SourcePlayer.Get() == Player && SourceWeapon.Get() == WeaponActor && SourceWeaponRoot.Get() == Root)
        return Synchronise();
    DestroyOverlay();

    // Managers may be recreated by their owner. Never create a second overlay
    // for an attachment already managed by another live component.
    for (USceneComponent* Child : Root->GetAttachParent()->GetAttachChildren())
        if (IsValid(Child) && Child->ComponentHasTag(OverlayTag) && Child->GetAttachSocketName() == Root->GetAttachSocketName())
            return Fail(TEXT("此武器挂点已有流光组件，未重复创建。"));

    UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, MeshPath);
    UMaterialInterface* Material = LoadObject<UMaterialInterface>(nullptr, MaterialPath);
    if (!Mesh || !Material || Mesh->GetStaticMaterials().Num() != 1)
        return Fail(TEXT("原武器流光网格或单槽材质尚未导入。"));
    TArray<FMaterialParameterInfo> Parameters; TArray<FGuid> ParameterIds;
    Material->GetAllScalarParameterInfo(Parameters, ParameterIds);
    if (!Parameters.ContainsByPredicate([](const FMaterialParameterInfo& Info)
        { return Info.Name == TimeParameter && Info.Association == EMaterialParameterAssociation::GlobalParameter; }))
        return Fail(TEXT("武器流光材质缺少 EffectTime 标量参数。"));

    SourcePlayer = Player; SourceWeapon = WeaponActor; SourceWeaponRoot = Root;
    Overlay = NewObject<UStaticMeshComponent>(Owner, NAME_None, RF_Transient);
    Owner->AddInstanceComponent(Overlay);
    Overlay->ComponentTags.Add(OverlayTag);
    Overlay->SetMobility(EComponentMobility::Movable);
    Overlay->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Overlay->SetGenerateOverlapEvents(false);
    Overlay->SetCanEverAffectNavigation(false);
    Overlay->SetCastShadow(false);
    Overlay->SetReceivesDecals(false);
    Overlay->SetOwnerNoSee(false);
    Overlay->SetOnlyOwnerSee(false);
    Overlay->SetVisibility(false);
    if (!Overlay->SetStaticMesh(Mesh)) return Fail(TEXT("原武器流光网格设置失败。"));
    FlowMaterial = UMaterialInstanceDynamic::Create(Material, Overlay);
    if (!FlowMaterial) return Fail(TEXT("武器流光动态材质创建失败。"));
    Overlay->SetMaterial(0, FlowMaterial);

    // Input vertices are prop1-local already. Copy relative/absolute settings,
    // preserving the parent's existing coordinate adapter and negative scale
    // exactly once. Do not also copy a world transform or a source unit scale.
    Overlay->SetupAttachment(Root->GetAttachParent(), Root->GetAttachSocketName());
    Overlay->SetAbsolute(Root->IsUsingAbsoluteLocation(), Root->IsUsingAbsoluteRotation(), Root->IsUsingAbsoluteScale());
    Overlay->SetRelativeTransform(Root->GetRelativeTransform());
    Overlay->RegisterComponent();
    if (!Overlay->IsRegistered() || Overlay->GetAttachParent() != Root->GetAttachParent() ||
        Overlay->GetAttachSocketName() != Root->GetAttachSocketName())
        return Fail(TEXT("武器流光注册或同父骨骼挂接失败。"));
    AddTickPrerequisiteComponent(Player); AddTickPrerequisiteComponent(Root);
    bReady = true;
    if (!Synchronise()) return false;
    Problem.Reset(); SetComponentTickEnabled(true);
    UE_LOG(LogTemp, Display, TEXT("HCZS weapon source overlay ready: mesh=%s socket=%s; weapon001 only"),
        *Mesh->GetPathName(), *Root->GetAttachSocketName().ToString());
    return true;
}

bool UHczsWeaponSourceFx::Synchronise()
{
    auto* Player = SourcePlayer.Get(); auto* Weapon = SourceWeapon.Get(); auto* Root = SourceWeaponRoot.Get();
    if (!IsReady() || !GetWorld() || !IsValid(GetOwner()) || GetOwner()->IsActorBeingDestroyed() ||
        Weapon->IsActorBeingDestroyed() || Weapon->GetRootComponent() != Root ||
        !Root->IsRegistered() || !Player->IsRegistered() || Root->GetAttachParent() != Player ||
        Root->GetAttachSocketName().IsNone() || !Player->DoesSocketExist(Root->GetAttachSocketName()) ||
        Root->GetRelativeTransform().ContainsNaN())
        return Fail(TEXT("原武器或角色挂接已失效，流光已清理。"));

    if (Overlay->GetAttachParent() != Root->GetAttachParent() || Overlay->GetAttachSocketName() != Root->GetAttachSocketName())
    {
        for (USceneComponent* Child : Root->GetAttachParent()->GetAttachChildren())
            if (IsValid(Child) && Child != Overlay && Child->ComponentHasTag(OverlayTag) && Child->GetAttachSocketName() == Root->GetAttachSocketName())
                return Fail(TEXT("原武器的新挂点已有流光组件，未重复挂接。"));
        if (!Overlay->AttachToComponent(Root->GetAttachParent(), FAttachmentTransformRules::KeepRelativeTransform, Root->GetAttachSocketName()))
            return Fail(TEXT("武器流光无法跟随原挂点变化，已清理。"));
    }
    if (Overlay->IsUsingAbsoluteLocation() != Root->IsUsingAbsoluteLocation() ||
        Overlay->IsUsingAbsoluteRotation() != Root->IsUsingAbsoluteRotation() || Overlay->IsUsingAbsoluteScale() != Root->IsUsingAbsoluteScale())
        Overlay->SetAbsolute(Root->IsUsingAbsoluteLocation(), Root->IsUsingAbsoluteRotation(), Root->IsUsingAbsoluteScale());
    if (!Overlay->GetRelativeTransform().Equals(Root->GetRelativeTransform(), 0.000001))
        Overlay->SetRelativeTransform(Root->GetRelativeTransform());

    const bool bVisible = ChainVisible(Root) && ChainVisible(Player) && !GetOwner()->IsHidden();
    Overlay->SetVisibility(bVisible); Overlay->SetHiddenInGame(!bVisible);
    const double WorldTime = GetWorld()->GetTimeSeconds();
    if (!FMath::IsFinite(WorldTime) || WorldTime < 0) return Fail(TEXT("游戏时间无效，武器流光已清理。"));
    EffectTime = static_cast<float>(WorldTime);
    FlowMaterial->SetScalarParameterValue(TimeParameter, EffectTime);
    return true;
}

void UHczsWeaponSourceFx::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
    if (bReady) Synchronise();
}

void UHczsWeaponSourceFx::DestroyOverlay()
{
    bReady = false; SetComponentTickEnabled(false);
    if (auto* Player = SourcePlayer.Get()) RemoveTickPrerequisiteComponent(Player);
    if (auto* Root = SourceWeaponRoot.Get()) RemoveTickPrerequisiteComponent(Root);
    UStaticMeshComponent* OldOverlay = Overlay;
    Overlay = nullptr; FlowMaterial = nullptr;
    SourcePlayer.Reset(); SourceWeapon.Reset(); SourceWeaponRoot.Reset(); EffectTime = 0;
    if (IsValid(OldOverlay))
    {
        OldOverlay->SetVisibility(false); OldOverlay->SetHiddenInGame(true);
        if (auto* Actor = OldOverlay->GetOwner()) Actor->RemoveInstanceComponent(OldOverlay);
        OldOverlay->DestroyComponent();
    }
}

void UHczsWeaponSourceFx::Release()
{
    DestroyOverlay(); Problem = TEXT("武器流光已释放。");
}

void UHczsWeaponSourceFx::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    bEndingPlay = true; Release(); Super::EndPlay(EndPlayReason);
}

void UHczsWeaponSourceFx::OnComponentDestroyed(bool bDestroyingHierarchy)
{
    bEndingPlay = true; Release(); Super::OnComponentDestroyed(bDestroyingHierarchy);
}

FString UHczsWeaponSourceFx::DevelopmentDescribe() const
{
    auto Result = MakeShared<FJsonObject>();
    Result->SetNumberField(TEXT("schemaVersion"), 1);
    Result->SetStringField(TEXT("mode"), TEXT("weapon001-source-overlay"));
    Result->SetBoolField(TEXT("ready"), IsReady()); Result->SetStringField(TEXT("problem"), Problem);
    Result->SetBoolField(TEXT("weaponDaoGroupImplemented"), false);
    Result->SetStringField(TEXT("owner"), ObjectPath(GetOwner()));
    Result->SetStringField(TEXT("player"), ObjectPath(SourcePlayer.Get()));
    Result->SetStringField(TEXT("sourceWeapon"), ObjectPath(SourceWeapon.Get()));
    Result->SetStringField(TEXT("sourceRoot"), ObjectPath(SourceWeaponRoot.Get()));
    Result->SetNumberField(TEXT("effectTime"), EffectTime);
    Result->SetNumberField(TEXT("worldTime"), GetWorld() ? GetWorld()->GetTimeSeconds() : 0);
    Result->SetBoolField(TEXT("worldPaused"), GetWorld() && UGameplayStatics::IsGamePaused(GetWorld()));
    Result->SetStringField(TEXT("component"), ObjectPath(Overlay));
    Result->SetStringField(TEXT("material"), ObjectPath(FlowMaterial));
    if (IsValid(Overlay))
    {
        Result->SetStringField(TEXT("mesh"), ObjectPath(Overlay->GetStaticMesh()));
        Result->SetStringField(TEXT("actualMaterial"), ObjectPath(Overlay->GetMaterial(0)));
        Result->SetStringField(TEXT("attachParent"), ObjectPath(Overlay->GetAttachParent()));
        Result->SetStringField(TEXT("attachSocket"), Overlay->GetAttachSocketName().ToString());
        Result->SetObjectField(TEXT("relativeTransform"), TransformJson(Overlay->GetRelativeTransform()));
        Result->SetObjectField(TEXT("worldTransform"), TransformJson(Overlay->GetComponentTransform()));
        Result->SetBoolField(TEXT("visible"), Overlay->GetVisibleFlag());
        Result->SetBoolField(TEXT("hiddenInGame"), Overlay->bHiddenInGame);
        Result->SetBoolField(TEXT("absoluteLocation"), Overlay->IsUsingAbsoluteLocation());
        Result->SetBoolField(TEXT("absoluteRotation"), Overlay->IsUsingAbsoluteRotation());
        Result->SetBoolField(TEXT("absoluteScale"), Overlay->IsUsingAbsoluteScale());
    }
    if (const auto* Root = SourceWeaponRoot.Get())
    {
        Result->SetObjectField(TEXT("sourceRelativeTransform"), TransformJson(Root->GetRelativeTransform()));
        Result->SetBoolField(TEXT("sourceChainVisible"), ChainVisible(Root));
    }
    if (IsValid(FlowMaterial)) Result->SetNumberField(TEXT("materialEffectTime"), FlowMaterial->K2_GetScalarParameterValue(TimeParameter));
    FString Text; auto Writer = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text);
    FJsonSerializer::Serialize(Result, Writer); return Text;
}
