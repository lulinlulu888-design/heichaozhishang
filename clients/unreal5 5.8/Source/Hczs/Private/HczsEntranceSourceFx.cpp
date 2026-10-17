#include "HczsEntranceSourceFx.h"

#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/AutomationTest.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

// Source: effects/player/001/fight_idle_show_chuchang.sfx (sha256 4be30fdd...).
// Reconstruction rules, derived from the data and not from the native update loop:
//  - FxStartTime/FxLifeSpan are seconds; every curve's Frame.Time is normalised to its
//    own layer lifespan (all authored keys span 0..1).
//  - Ancestor dummies keep their last pose after their own lifespan; a child's own
//    lifespan decides visibility.
//  - Colour keys are A,R,G,B bytes; key alpha multiplies alphaMtl.
//  - Interpolator 0 is linear; single-key curves are constants. TrackType/DirType are ignored.
//  - Source (x, y-up, z) maps to UE (x, z, y) * 100, matching the glTF import of both
//    the player and these meshes; the GIM socket fx_center has no bone and an identity matrix.
//  - BindType=7 is treated as position-only: layers follow the player origin but keep world
//    axes. Inheriting the battle mesh's 90 degree yaw put the dummies' X scale on the depth axis
//    and made the ring about 4 character heights wide; the cached original entrance video
//    (03:39.3-03:39.8) shows about 2.5, which world axes reproduce.
namespace
{
    struct FKey { float T; float V; };
    struct FColourKey { float T; uint8 A, R, G, B; };
    struct FAxisCurves { TArray<FKey> X, Y, Z; };
    struct FDummy { const TCHAR* XPath; float Start, Life; FVector Pos; FAxisCurves Scale; };
    struct FLayer
    {
        const TCHAR* XPath; const TCHAR* Model; float Start, Life; FVector Pos;
        FAxisCurves Scale; float ScaleFrame;
        TArray<FDummy> Parents;
        TArray<FKey> AlphaMtl, Dissolve, Strength;
        TArray<FColourKey> Colour;
    };

    const TArray<FLayer>& Table()
    {
        static const TArray<FLayer> Value = {
            {TEXT("/FxGroup[1]/Dummy[1]/Dummy[1]/Model[1]"), TEXT("nengliangkuosan"), .05f, .7f, FVector::ZeroVector,
             {{{0, 1}}, {{0, .5f}}, {{0, 1}}}, .7f,
             {{TEXT("/FxGroup[1]/Dummy[1]"), 0, .5f, FVector(0, 0, -10), {{{0, .7f}}, {{0, 1}}, {{0, 1}}}},
              {TEXT("/FxGroup[1]/Dummy[1]/Dummy[1]"), 0, .5f, FVector(0, -.954676f, 0),
               {{{0, .3f}, {.1985f, .55f}, {1, .8f}}, {{0, 1}}, {{0, 1}}}}},
             {{.5f, 1}}, {{0, 0}, {.5985f, 0}, {1, 1}}, {},
             {{0, 127, 255, 170, 222}, {.1395f, 133, 255, 160, 205}, {.2193f, 138, 255, 48, 137},
              {.4867f, 138, 137, 14, 67}, {.7674f, 123, 75, 2, 39}, {1, 0, 0, 0, 0}}},
            {TEXT("/FxGroup[1]/Dummy[2]/Model[1]"), TEXT("fight_idle_show_smoke"), 0, .4f, FVector(0, -5, 0),
             {{{0, 1}}, {{0, 1}}, {{0, 1}}}, .9f,
             {{TEXT("/FxGroup[1]/Dummy[2]"), 0, .3f, FVector(0, 0, -10),
               {{{0, .3f}, {.1985f, .55f}, {1, .8f}}, {{0, 1}}, {{0, 1}}}}},
             {{0, 1}, {.1985f, 1}, {1, 0}}, {}, {},
             {{0, 120, 255, 210, 210}, {.1977f, 120, 255, 186, 194}, {.5515f, 63, 255, 38, 56}, {1, 0, 93, 0, 7}}},
            {TEXT("/FxGroup[1]/Dummy[3]/Model[1]"), TEXT("fight_idle_show_kuosan"), 0, .3f, FVector(0, -2, 0),
             {{{0, .8f}}, {{0, 1}, {.1985f, 2.7143f}, {1, 5}}, {{0, .8f}}}, .7f,
             {{TEXT("/FxGroup[1]/Dummy[3]"), 0, .25f, FVector(0, 0, -10),
               {{{0, .5f}, {.0992f, .7025f}, {1, .8f}}, {{0, 1}}, {{0, 1}}}}},
             {{0, 2}, {.1985f, 2}, {.3985f, .775f}, {1, 0}}, {}, {{.5f, 5}},
             {{0, 255, 254, 249, 255}, {.196f, 255, 255, 190, 223}, {.5f, 255, 255, 58, 143}, {1, 0, 89, 2, 35}}},
        };
        return Value;
    }

    float Evaluate(const TArray<FKey>& Keys, float U, float Default)
    {
        if (Keys.IsEmpty()) return Default;
        if (U <= Keys[0].T) return Keys[0].V;
        for (int32 Index = 1; Index < Keys.Num(); ++Index)
            if (U <= Keys[Index].T)
                return FMath::Lerp(Keys[Index - 1].V, Keys[Index].V, (U - Keys[Index - 1].T) / (Keys[Index].T - Keys[Index - 1].T));
        return Keys.Last().V;
    }

    FLinearColor EvaluateColour(const TArray<FColourKey>& Keys, float U)
    {
        auto Colour = [](const FColourKey& K) { return FLinearColor(K.R / 255.f, K.G / 255.f, K.B / 255.f, K.A / 255.f); };
        if (Keys.IsEmpty()) return FLinearColor::White;
        if (U <= Keys[0].T) return Colour(Keys[0]);
        for (int32 Index = 1; Index < Keys.Num(); ++Index)
            if (U <= Keys[Index].T)
                return FMath::Lerp(Colour(Keys[Index - 1]), Colour(Keys[Index]), (U - Keys[Index - 1].T) / (Keys[Index].T - Keys[Index - 1].T));
        return Colour(Keys.Last());
    }

    FVector EvaluateScale(const FAxisCurves& Curves, float U)
    {
        return FVector(Evaluate(Curves.X, U, 1), Evaluate(Curves.Y, U, 1), Evaluate(Curves.Z, U, 1));
    }

    FVector SourceToUnreal(const FVector& Source, float Units) { return FVector(Source.X, Source.Z, Source.Y) * Units; }

    FString ObjectPath(const UObject* Object) { return IsValid(Object) ? Object->GetPathName() : FString(); }

    TArray<TSharedPtr<FJsonValue>> Numbers(const FVector& Value)
    {
        return {MakeShared<FJsonValueNumber>(Value.X), MakeShared<FJsonValueNumber>(Value.Y), MakeShared<FJsonValueNumber>(Value.Z)};
    }
}

int32 HczsEntranceFxLayerCount() { return Table().Num(); }
FString HczsEntranceFxLayerModel(int32 Layer) { return Table().IsValidIndex(Layer) ? FString(Table()[Layer].Model) : FString(); }
FString HczsEntranceFxLayerSource(int32 Layer) { return Table().IsValidIndex(Layer) ? FString(Table()[Layer].XPath) : FString(); }

float HczsEntranceFxDuration()
{
    float Result = 0;
    for (const FLayer& Layer : Table()) Result = FMath::Max(Result, Layer.Start + Layer.Life);
    return Result;
}

bool HczsEntranceFxReconstructionEnabled()
{
    return FParse::Param(FCommandLine::Get(), TEXT("HczsEntranceFxReconstruction"));
}

FHczsEntranceFxSample HczsSampleEntranceFx(int32 LayerIndex, float Seconds)
{
    FHczsEntranceFxSample Result;
    if (!Table().IsValidIndex(LayerIndex) || !FMath::IsFinite(Seconds)) return Result;
    const FLayer& Layer = Table()[LayerIndex];
    const float Local = Seconds - Layer.Start;
    Result.bActive = Local >= 0 && Local < Layer.Life;
    const float U = FMath::Clamp(Local / Layer.Life, 0.f, 1.f);
    FVector Position = FVector::ZeroVector, Scale = FVector::OneVector;
    for (const FDummy& Parent : Layer.Parents)
    {
        Position += Scale * Parent.Pos;
        Scale *= EvaluateScale(Parent.Scale, FMath::Clamp((Seconds - Parent.Start) / Parent.Life, 0.f, 1.f));
    }
    Position += Scale * Layer.Pos;
    Scale *= EvaluateScale(Layer.Scale, U) * Layer.ScaleFrame;
    Result.Location = SourceToUnreal(Position, 100);
    Result.Scale = SourceToUnreal(Scale, 1);
    const FLinearColor Colour = EvaluateColour(Layer.Colour, U);
    Result.Tint = FLinearColor(Colour.R, Colour.G, Colour.B, 1);
    Result.Alpha = Evaluate(Layer.AlphaMtl, U, 1) * Colour.A;
    Result.bHasDissolve = !Layer.Dissolve.IsEmpty(); Result.Dissolve = Evaluate(Layer.Dissolve, U, 0);
    Result.bHasStrength = !Layer.Strength.IsEmpty(); Result.Strength = Evaluate(Layer.Strength, U, 0);
    return Result;
}

UHczsEntranceSourceFx::UHczsEntranceSourceFx()
{
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.bStartWithTickEnabled = false;
    PrimaryComponentTick.TickGroup = TG_PostUpdateWork;
}

bool UHczsEntranceSourceFx::Play(USkeletalMeshComponent* Player, const FString& InBattleId)
{
    Stop(TEXT("restarted"));
    auto* Owner = GetOwner();
    if (!IsRegistered() || !IsValid(Owner) || !GetWorld() || !IsValid(Player) || !Player->IsRegistered())
    { Outcome = TEXT("unavailable: player or owner not registered"); return false; }
    for (int32 Index = 0; Index < Table().Num(); ++Index)
    {
        const FString Name = Table()[Index].Model;
        const FString Base = TEXT("/Game/Recovered/Battle/Entrance/SourceModels/");
        auto* Mesh = LoadObject<UStaticMesh>(nullptr, *(Base + TEXT("SM_") + Name + TEXT(".SM_") + Name));
        auto* Material = LoadObject<UMaterialInterface>(nullptr, *(Base + TEXT("M_") + Name + TEXT(".M_") + Name));
        if (!Mesh || !Material || Mesh->GetStaticMaterials().Num() != 1)
        { DestroyLayers(); Outcome = TEXT("unavailable: imported entrance model missing ") + Name; return false; }
        auto* Component = NewObject<UStaticMeshComponent>(Owner, NAME_None, RF_Transient);
        Owner->AddInstanceComponent(Component);
        Component->SetMobility(EComponentMobility::Movable);
        Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Component->SetGenerateOverlapEvents(false);
        Component->SetCanEverAffectNavigation(false);
        Component->SetCastShadow(false);
        Component->SetReceivesDecals(false);
        Component->SetVisibility(false);
        Component->SetStaticMesh(Mesh);
        auto* Dynamic = UMaterialInstanceDynamic::Create(Material, Component);
        Component->SetMaterial(0, Dynamic);
        Component->SetupAttachment(Player);
        Component->SetAbsolute(true, true, true);
        Component->RegisterComponent();
        Layers.Add(Component); Materials.Add(Dynamic);
    }
    SourcePlayer = Player; BattleId = InBattleId; StartWorldTime = GetWorld()->GetTimeSeconds();
    bPlaying = true; ++PlayCount; MaxActiveLayers = 0; Outcome = TEXT("playing");
    Apply(0);
    SetComponentTickEnabled(true);
    UE_LOG(LogTemp, Display, TEXT("HCZS entrance source fx started: battle=%s layers=%d duration=%.3f mode=reconstruction"),
        *BattleId, Layers.Num(), HczsEntranceFxDuration());
    return true;
}

void UHczsEntranceSourceFx::Apply(float Seconds)
{
    LastSeconds = Seconds;
    const USkeletalMeshComponent* Player = SourcePlayer.Get();
    if (!Player) return;
    const FVector Origin = Player->GetComponentLocation();
    const float PlayerScale = FMath::Abs(Player->GetComponentScale().X);
    int32 Active = 0;
    for (int32 Index = 0; Index < Layers.Num(); ++Index)
    {
        const FHczsEntranceFxSample Sample = HczsSampleEntranceFx(Index, Seconds);
        UStaticMeshComponent* Component = Layers[Index];
        UMaterialInstanceDynamic* Material = Materials[Index];
        if (!IsValid(Component) || !IsValid(Material)) continue;
        Component->SetVisibility(Sample.bActive);
        Component->SetHiddenInGame(!Sample.bActive);
        if (!Sample.bActive) continue;
        ++Active;
        Component->SetWorldLocationAndRotation(Origin + Sample.Location * PlayerScale, FRotator::ZeroRotator);
        Component->SetWorldScale3D(Sample.Scale * PlayerScale);
        Material->SetScalarParameterValue(TEXT("EffectTime"), Seconds);
        Material->SetScalarParameterValue(TEXT("SourceAlpha"), Sample.Alpha);
        Material->SetVectorParameterValue(TEXT("SourceTint"), Sample.Tint);
        if (Sample.bHasDissolve) Material->SetScalarParameterValue(TEXT("SourceDissolve"), Sample.Dissolve);
        if (Sample.bHasStrength) Material->SetScalarParameterValue(TEXT("SourceStrength"), Sample.Strength);
    }
    MaxActiveLayers = FMath::Max(MaxActiveLayers, Active);
}

void UHczsEntranceSourceFx::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
    if (!bPlaying || !GetWorld()) return;
    if (!SourcePlayer.IsValid()) { Stop(TEXT("player-released")); return; }
    const float Seconds = static_cast<float>(GetWorld()->GetTimeSeconds() - StartWorldTime);
    if (Seconds >= HczsEntranceFxDuration()) { Stop(TEXT("complete")); return; }
    Apply(Seconds);
}

void UHczsEntranceSourceFx::Stop(const FString& Reason)
{
    if (!bPlaying && Layers.IsEmpty()) return;
    const bool bWasPlaying = bPlaying;
    DestroyLayers();
    if (bWasPlaying)
    {
        Outcome = Reason;
        UE_LOG(LogTemp, Display, TEXT("HCZS entrance source fx finished: battle=%s reason=%s seconds=%.3f maxActiveLayers=%d"),
            *BattleId, *Reason, LastSeconds, MaxActiveLayers);
    }
}

void UHczsEntranceSourceFx::DestroyLayers()
{
    bPlaying = false; SetComponentTickEnabled(false);
    for (UStaticMeshComponent* Component : Layers)
        if (IsValid(Component))
        {
            if (auto* Actor = Component->GetOwner()) Actor->RemoveInstanceComponent(Component);
            Component->DestroyComponent();
        }
    Layers.Reset(); Materials.Reset(); SourcePlayer.Reset();
}

void UHczsEntranceSourceFx::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    Stop(TEXT("end-play"));
    Super::EndPlay(EndPlayReason);
}

FString UHczsEntranceSourceFx::DevelopmentDescribe() const
{
    auto Result = MakeShared<FJsonObject>();
    Result->SetStringField(TEXT("mode"), TEXT("reconstruction"));
    Result->SetStringField(TEXT("source"), TEXT("effects/player/001/fight_idle_show_chuchang.sfx"));
    Result->SetBoolField(TEXT("enabled"), HczsEntranceFxReconstructionEnabled());
    Result->SetBoolField(TEXT("playing"), bPlaying);
    Result->SetStringField(TEXT("outcome"), Outcome);
    Result->SetStringField(TEXT("battleId"), BattleId);
    Result->SetNumberField(TEXT("seconds"), LastSeconds);
    Result->SetNumberField(TEXT("duration"), HczsEntranceFxDuration());
    Result->SetNumberField(TEXT("playCount"), PlayCount);
    Result->SetNumberField(TEXT("maxActiveLayers"), MaxActiveLayers);
    if (const auto* Player = SourcePlayer.Get())
    {
        Result->SetArrayField(TEXT("playerOrigin"), Numbers(Player->GetComponentLocation()));
        Result->SetArrayField(TEXT("playerBoundsOrigin"), Numbers(Player->Bounds.Origin));
        Result->SetArrayField(TEXT("playerBoundsExtent"), Numbers(Player->Bounds.BoxExtent));
        if (Player->GetBoneIndex(TEXT("bip001-pelvis")) != INDEX_NONE)
            Result->SetArrayField(TEXT("pelvisWorld"), Numbers(Player->GetBoneLocation(TEXT("bip001-pelvis"))));
    }
    TArray<TSharedPtr<FJsonValue>> Rows;
    for (int32 Index = 0; Index < Layers.Num(); ++Index)
    {
        const UStaticMeshComponent* Component = Layers[Index];
        auto Row = MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("model"), HczsEntranceFxLayerModel(Index));
        Row->SetStringField(TEXT("source"), HczsEntranceFxLayerSource(Index));
        if (IsValid(Component))
        {
            Row->SetBoolField(TEXT("visible"), Component->GetVisibleFlag() && !Component->bHiddenInGame);
            Row->SetStringField(TEXT("attachParent"), ObjectPath(Component->GetAttachParent()));
            Row->SetBoolField(TEXT("worldAxes"), Component->IsUsingAbsoluteRotation());
            Row->SetArrayField(TEXT("worldLocation"), Numbers(Component->GetComponentLocation()));
            Row->SetArrayField(TEXT("worldScale"), Numbers(Component->GetComponentScale()));
            Row->SetArrayField(TEXT("worldRotation"), Numbers(Component->GetComponentRotation().Euler()));
            if (const auto* Parent = Component->GetAttachParent())
            {
                Row->SetArrayField(TEXT("parentLocation"), Numbers(Parent->GetComponentLocation()));
                Row->SetArrayField(TEXT("parentRotation"), Numbers(Parent->GetComponentRotation().Euler()));
            }
        }
        if (Materials.IsValidIndex(Index) && IsValid(Materials[Index]))
            Row->SetNumberField(TEXT("alpha"), Materials[Index]->K2_GetScalarParameterValue(TEXT("SourceAlpha")));
        Rows.Add(MakeShared<FJsonValueObject>(Row));
    }
    Result->SetArrayField(TEXT("layers"), Rows);
    FString Text; auto Writer = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text);
    FJsonSerializer::Serialize(Result, Writer); return Text;
}

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHczsEntranceSourceFxTest, "Hczs.Battle.EntranceSourceFx",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHczsEntranceSourceFxTest::RunTest(const FString&)
{
    TestEqual(TEXT("three exported model layers"), HczsEntranceFxLayerCount(), 3);
    TestTrue(TEXT("group ends with the longest model layer"), FMath::IsNearlyEqual(HczsEntranceFxDuration(), .75f));
    TestFalse(TEXT("energy ring waits for its 0.05 s start"), HczsSampleEntranceFx(0, .04f).bActive);
    const FHczsEntranceFxSample Ring = HczsSampleEntranceFx(0, .3f);
    TestTrue(TEXT("energy ring active"), Ring.bActive);
    // Parent dummy clamps at its 0.5 s end: X = 0.7 * 0.8 * 1 * 0.7 = 0.392.
    TestTrue(TEXT("ancestor scale x"), FMath::IsNearlyEqual(Ring.Scale.X, .7f * (.55f + (.8f - .55f) * ((.6f - .1985f) / .8015f)) * .7f, 1e-4f));
    TestTrue(TEXT("source y-up maps to UE z scale"), FMath::IsNearlyEqual(Ring.Scale.Z, .5f * .7f, 1e-5f));
    TestTrue(TEXT("dummy z offset maps to UE y"), FMath::IsNearlyEqual(Ring.Location.Y, -1000.f, 1e-3f));
    TestTrue(TEXT("nested dummy offset scales with ancestor"), FMath::IsNearlyEqual(Ring.Location.Z, -95.4676f, 1e-3f));
    const FHczsEntranceFxSample Column = HczsSampleEntranceFx(2, .15f);
    TestTrue(TEXT("kuosan height grows over normalised time"), FMath::IsNearlyEqual(Column.Scale.Z / .7f, 2.7143f + (5 - 2.7143f) * ((.5f - .1985f) / .8015f), 1e-3f));
    TestTrue(TEXT("kuosan strength constant"), Column.bHasStrength && FMath::IsNearlyEqual(Column.Strength, 5.f));
    TestTrue(TEXT("ARGB alpha multiplies alphaMtl"), FMath::IsNearlyEqual(Column.Alpha, FMath::Lerp(.775f, 0.f, (.5f - .3985f) / .6015f), 1e-3f));
    TestFalse(TEXT("smoke ends at its own lifespan"), HczsSampleEntranceFx(1, .4f).bActive);
    TestTrue(TEXT("final colour fully transparent"), HczsSampleEntranceFx(0, .7499f).Alpha < .01f);
    return true;
}
#endif
