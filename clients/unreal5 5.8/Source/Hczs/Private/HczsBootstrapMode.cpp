#include "HczsBootstrapMode.h"
#include "HczsGameInstance.h"
#include "Engine/World.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/DirectionalLight.h"
#include "Components/StaticMeshComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/InputComponent.h"
#include "GameFramework/SpectatorPawn.h"
#include "InputCoreTypes.h"
#include "Camera/CameraActor.h"
#include "EngineUtils.h"
#include "TimerManager.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "UnrealClient.h"
#include "Engine/GameViewportClient.h"
#include "Widgets/SWindow.h"
#include "RHIResources.h"
#include "HczsHallWidget.h"
#include "HczsSessionWidget.h"
#include "ImageUtils.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/PlatformFileManager.h"

AHczsBootstrapMode::AHczsBootstrapMode()
{
    DefaultPawnClass = ASpectatorPawn::StaticClass();
    PlayerControllerClass = AHczsBootstrapController::StaticClass();
    HUDClass = AHczsBootstrapHUD::StaticClass();
}

void AHczsBootstrapMode::BeginPlay()
{
    Super::BeginPlay();
    if (!GetWorld()->GetMapName().EndsWith(TEXT("Entry"))) return;
    // Engine primitives are only orientation markers, never claimed as recovered assets.
    UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
    if (!Cube) return;
    auto SpawnBox = [this, Cube](const FVector& Position, const FVector& Scale)
    {
        AStaticMeshActor* Box = GetWorld()->SpawnActor<AStaticMeshActor>(Position, FRotator::ZeroRotator);
        if (!Box) return;
        Box->SetMobility(EComponentMobility::Movable);
        Box->GetStaticMeshComponent()->SetStaticMesh(Cube);
        Box->SetActorScale3D(Scale);
    };
    SpawnBox(FVector(500, 0, -150), FVector(20, 20, 0.1));
    SpawnBox(FVector(500, -300, -50), FVector(1, 1, 2));
    SpawnBox(FVector(750, 100, -100), FVector(1, 1, 1));
    ADirectionalLight* Light = GetWorld()->SpawnActor<ADirectionalLight>(FVector::ZeroVector, FRotator(-45, -25, 0));
    if (Light) Light->GetLightComponent()->SetIntensity(3.0f);
}

void AHczsBootstrapController::SetupInputComponent()
{
    Super::SetupInputComponent();
    if (InputComponent) InputComponent->BindKey(EKeys::H, IE_Pressed, this, &AHczsBootstrapController::RefreshStatus);
}

void AHczsBootstrapController::RefreshStatus()
{
    if (UHczsGameInstance* Instance = Cast<UHczsGameInstance>(GetGameInstance())) Instance->RefreshLocalStatus();
}

void AHczsBootstrapHUD::DrawHUD()
{
    Super::DrawHUD();
    DrawText(TEXT("HCZS UE5 bootstrap | WASD + mouse: spectator | H: retry local status"), FLinearColor::White, 24, 24);
    DrawText(TEXT("Engine primitives only. Original game content and controls are not restored."), FLinearColor::Yellow, 24, 48);
    if (UHczsGameInstance* Instance = Cast<UHczsGameInstance>(GetGameInstance()))
        DrawText(Instance->LocalStatus, Instance->bLocalServiceAvailable ? FLinearColor::Green : FLinearColor::Yellow, 24, 72);
}

// The camera is placed by the reproducible asset inspection-map script.
AHczsRecoveredHallMode::AHczsRecoveredHallMode()
{
    DefaultPawnClass = nullptr;
    HUDClass = nullptr;
}

void AHczsRecoveredHallMode::BeginPlay()
{
    Super::BeginPlay();
    if (APlayerController* Controller = GetWorld()->GetFirstPlayerController())
    {
        HallWidget = CreateWidget<UHczsHallWidget>(Controller);
        if (HallWidget)
        {
            HallWidget->OnProfileRequested.AddUObject(SessionWidget, &UHczsSessionWidget::OpenProfileSelection);
            HallWidget->OnWorldlineRequested.AddUObject(SessionWidget, &UHczsSessionWidget::OpenWorldlineSelection);
            HallWidget->AddToViewport(0);
        }
        Controller->bShowMouseCursor = true;
    }
#if !UE_BUILD_SHIPPING
    if (SessionWidget && FParse::Param(FCommandLine::Get(), TEXT("HczsWorldlineInspect")))
        SessionWidget->ShowWorldlineSourceInspection();
#endif
    for (TActorIterator<ACameraActor> It(GetWorld()); It; ++It)
    {
        if (It->ActorHasTag(TEXT("HCZSInspectionCamera")))
        {
            if (APlayerController* Controller = GetWorld()->GetFirstPlayerController())
                Controller->SetViewTarget(*It);
            break;
        }
    }
    FString CapturePath;
    if (FParse::Value(FCommandLine::Get(), TEXT("HczsCapture="), CapturePath))
    {
        CapturePath = CapturePath.TrimQuotes();
        FPaths::NormalizeFilename(CapturePath);
        CapturePath = FPaths::ConvertRelativePathToFull(CapturePath);
        IFileManager::Get().MakeDirectory(*FPaths::GetPath(CapturePath), true);
        GetWorld()->GetTimerManager().SetTimer(InspectionCaptureTimer,
            FTimerDelegate::CreateWeakLambda(this, [this, CapturePath]()
        {
            // Clearing this timer releases its delegate and captured FString.
            // Keep a local copy before clearing it once the viewport is ready.
            const FString OutputPath = CapturePath;
            UGameViewportClient* Client = GetWorld()->GetGameViewport();
            if (!Client || !Client->Viewport) return;
            const TSharedPtr<SWindow> Window = Client->GetWindow();
            if (!Window.IsValid() || Window->IsWindowMinimized()) return;
            const FIntPoint ViewSize = Client->Viewport->GetSizeXY();
            const FTextureRHIRef Texture = Client->Viewport->GetRenderTargetTexture();
            const FIntPoint TargetSize = Client->Viewport->GetRenderTargetTextureSizeXY();
            // A minimized/resizing DX12 swapchain can be 8x8 while the viewport
            // still reports its previous full size. Never read beyond that buffer.
            // Direct-to-swapchain viewports have no game-thread texture object.
            // Use their cached RTT dimensions, and inspect a texture when present.
            if (ViewSize.X < 64 || ViewSize.Y < 64 || TargetSize != ViewSize
                || (Texture.IsValid() && Texture->GetDesc().Extent != ViewSize)) return;
            GetWorld()->GetTimerManager().ClearTimer(InspectionCaptureTimer);
            UE_LOG(LogTemp, Display, TEXT("HCZS: native lighting unbuilt objects=%u"), GetWorld()->NumLightingUnbuiltObjects);
            // Capture only when explicitly requested by the development helper.
            // Save the actual Slate viewport pixels and report the write result.
            UGameViewportClient::OnScreenshotCaptured().AddWeakLambda(this,
                [this, OutputPath](int32 Width, int32 Height, const TArray<FColor>& Pixels)
            {
                TArray64<uint8> Png;
                FImageUtils::PNGCompressImageArray(Width, Height, TArrayView64<const FColor>(Pixels.GetData(), Pixels.Num()), Png);
                const bool bSaved = FFileHelper::SaveArrayToFile(Png, *OutputPath);
                // Observe the source page that actually painted this native frame.
                // This helper never selects a profile or submits a game intent.
                if (bSaved && SessionWidget)
                {
                    const FString Observation = SessionWidget->DevelopmentDescribeWorldlineUI();
                    if (Observation != TEXT("{}"))
                    {
                        const bool bObservationSaved = FFileHelper::SaveStringToFile(Observation,
                            *(OutputPath + TEXT(".ui.json")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
                        UE_LOG(LogTemp, Display, TEXT("HCZS: worldline paint observation saved=%s"),
                            bObservationSaved ? TEXT("true") : TEXT("false"));
                    }
                }
                UE_LOG(LogTemp, Display, TEXT("HCZS: hall screenshot saved=%s %dx%d path=%s"),
                    bSaved ? TEXT("true") : TEXT("false"), Width, Height, *OutputPath);
                UGameViewportClient::OnScreenshotCaptured().RemoveAll(this);
            });
            UE_LOG(LogTemp, Display, TEXT("HCZS: requesting visible hall/UI screenshot %dx%d path=%s"), ViewSize.X, ViewSize.Y, *OutputPath);
            FScreenshotRequest::RequestScreenshot(OutputPath, true, false);
        }), 1.0f, true, 12.0f);
    }
}

void AHczsRecoveredHallMode::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    if (HallWidget) HallWidget->RemoveFromParent();
    UGameViewportClient::OnScreenshotCaptured().RemoveAll(this);
    GetWorld()->GetTimerManager().ClearTimer(InspectionCaptureTimer);
    Super::EndPlay(EndPlayReason);
}
