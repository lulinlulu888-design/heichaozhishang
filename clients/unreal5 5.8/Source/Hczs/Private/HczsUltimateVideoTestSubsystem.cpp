#include "HczsUltimateVideoTestSubsystem.h"
#include "HczsUltimateVideoPlayer.h"

#include "Brushes/SlateColorBrush.h"
#include "Dom/JsonObject.h"
#include "Engine/GameInstance.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "HAL/PlatformFileManager.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformTime.h"
#include "ImageUtils.h"
#include "Kismet/GameplayStatics.h"
#include "MediaPlayer.h"
#include "MediaTexture.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "UnrealClient.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScaleBox.h"

struct FHczsUltimateVideoPaintObservation
{
    uint64 Serial = 0;
    FVector2D AbsoluteSize = FVector2D::ZeroVector;
    double MediaSeconds = 0.0;
    bool bDecodedSurface = false;
    TWeakObjectPtr<UHczsUltimateVideoPlayer> Video;
    TWeakObjectPtr<UMediaTexture> Texture;
};

namespace
{
constexpr int32 SourceWidth = 1560, SourceHeight = 960;
constexpr double CaptureSeconds = 0.8;
int64 UnixMs()
{
    const FDateTime Now = FDateTime::UtcNow();
    return Now.ToUnixTimestamp() * 1000 + Now.GetMillisecond();
}
bool AllowedReport(FString& Path)
{
    Path = Path.TrimQuotes();
    FPaths::NormalizeFilename(Path);
    Path = FPaths::ConvertRelativePathToFull(Path);
    if (!FPaths::CollapseRelativeDirectories(Path)) return false;
    FString Root = FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::ProjectDir(), TEXT("../..")));
    FPaths::CollapseRelativeDirectories(Root);
    const FString Allowed = FPaths::Combine(Root, TEXT("analysis/unreal/ultimate-video-test"));
    // A run must have its own child directory, not write directly in the test root.
    return FPaths::IsUnderDirectory(FPaths::GetPath(Path), Allowed) &&
        !FPaths::IsSamePath(FPaths::GetPath(Path), Allowed) && FPaths::GetExtension(Path).Equals(TEXT("json"), ESearchCase::IgnoreCase);
}
class SObservedUltimateImage final : public SImage
{
public:
    SLATE_BEGIN_ARGS(SObservedUltimateImage) {}
        SLATE_ARGUMENT(const FSlateBrush*, Brush)
        SLATE_ARGUMENT(TSharedPtr<FHczsUltimateVideoPaintObservation>, Observation)
    SLATE_END_ARGS()
    void Construct(const FArguments& Args)
    {
        Observation = Args._Observation; Brush = Args._Brush;
        SImage::Construct(SImage::FArguments().Image(Brush).ColorAndOpacity(FLinearColor::White));
        ForceVolatile(true);
    }
    virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& Geometry, const FSlateRect& Culling,
        FSlateWindowElementList& DrawElements, int32 Layer, const FWidgetStyle& Style, bool bEnabled) const override
    {
        const int32 Result = SImage::OnPaint(Args, Geometry, Culling, DrawElements, Layer, Style, bEnabled);
        if (Observation && Brush && Observation->Texture.IsValid() && Brush->GetResourceObject() == Observation->Texture.Get())
        {
            ++Observation->Serial;
            Observation->AbsoluteSize = FVector2D(Geometry.GetAbsoluteSize());
            const UHczsUltimateVideoPlayer* Player = Observation->Video.Get();
            Observation->bDecodedSurface = Player && Player->HasDecodedVideoSurface();
            Observation->MediaSeconds = Player && Player->GetMediaPlayer() ? Player->GetMediaPlayer()->GetTime().GetTotalSeconds() : -1.0;
        }
        return Result;
    }
private:
    const FSlateBrush* Brush = nullptr;
    TSharedPtr<FHczsUltimateVideoPaintObservation> Observation;
};
}

bool UHczsUltimateVideoTestSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
#if UE_BUILD_SHIPPING
    return false;
#else
    FString Path;
    return Cast<UGameInstance>(Outer) && !IsRunningCommandlet() && !IsRunningDedicatedServer() &&
        FParse::Param(FCommandLine::Get(), TEXT("HczsUltimateVideoTest")) &&
        FParse::Value(FCommandLine::Get(), TEXT("HczsUltimateVideoTestReport="), Path) && AllowedReport(Path);
#endif
}

void UHczsUltimateVideoTestSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
#if !UE_BUILD_SHIPPING
    FParse::Value(FCommandLine::Get(), TEXT("HczsUltimateVideoTestReport="), ReportPath);
    if (!AllowedReport(ReportPath)) return;
    ScreenshotPath = FPaths::Combine(FPaths::GetPath(ReportPath), FPaths::GetBaseFilename(ReportPath) + TEXT("-frame-0800ms.png"));
    auto& Files = FPlatformFileManager::Get().GetPlatformFile();
    if (Files.FileExists(*ReportPath) || Files.FileExists(*ScreenshotPath))
    {
        UE_LOG(LogTemp, Error, TEXT("HCZS ultimate video test refuses to overwrite existing evidence: %s"), *ReportPath);
        FPlatformMisc::RequestExitWithStatus(false, 1); return;
    }
    Files.CreateDirectoryTree(*FPaths::GetPath(ReportPath));
    bInitialized = true;
    bPrepausedCase = FParse::Param(FCommandLine::Get(), TEXT("HczsUltimateVideoPrepaused"));
    bCancelCase = FParse::Param(FCommandLine::Get(), TEXT("HczsUltimateVideoCancel"));
    StartedAtUtc = FDateTime::UtcNow().ToIso8601(); StartedAtUnixMs = UnixMs();
    SequenceId = TEXT("media-acceptance-") + FGuid::NewGuid().ToString(EGuidFormats::DigitsWithHyphensLower);
    int32 ServerPort = -1;
    bNoBusinessServer = FParse::Value(FCommandLine::Get(), TEXT("HczsServerPort="), ServerPort) && ServerPort == 0;
    Deadline = FPlatformTime::Seconds() + 120.0;
    TickHandle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateUObject(this, &UHczsUltimateVideoTestSubsystem::TickTest), 0.01f);
    if (!bNoBusinessServer) Failure = TEXT("Media-only acceptance requires -HczsServerPort=0 so GameInstance bootstrap cannot reach a business server");
    UE_LOG(LogTemp, Display, TEXT("HCZS ultimate video acceptance initialized: report=%s"), *ReportPath);
#endif
}

void UHczsUltimateVideoTestSubsystem::RecordEvent(const TCHAR* Kind, const FString& Sequence)
{
    auto Event = MakeShared<FJsonObject>();
    Event->SetStringField(TEXT("kind"), Kind); Event->SetStringField(TEXT("sequenceId"), Sequence);
    Event->SetNumberField(TEXT("atUnixMs"), UnixMs()); Event->SetNumberField(TEXT("realSeconds"), FPlatformTime::Seconds());
    Events.Add(MakeShared<FJsonValueObject>(Event));
}

void UHczsUltimateVideoTestSubsystem::VideoReady(const FString& Sequence, UMediaTexture* Texture)
{
    ++ReadyCount; RecordEvent(TEXT("ready"), Sequence);
    if (Sequence != SequenceId || ReadyCount != 1 || !Texture || !Video || !Video->GetMediaPlayer())
    { Failure = TEXT("Invalid or duplicate real media Ready callback"); return; }
    UMediaPlayer* Player = Video->GetMediaPlayer();
    const int32 Track = Player->GetSelectedTrack(EMediaPlayerTrack::Video);
    const FIntPoint Size = Player->GetVideoTrackDimensions(Track, Player->GetTrackFormat(EMediaPlayerTrack::Video, Track));
    DurationSeconds = Player->GetDuration().GetTotalSeconds(); Decoder = Player->GetPlayerName().ToString();
    if (Size != FIntPoint(SourceWidth, SourceHeight) || DurationSeconds <= CaptureSeconds || Player->IsPlaying())
    { Failure = TEXT("Ready source dimensions/duration/paused state do not match the original Elsa movie"); return; }
    DisplayTexture = Texture;
}

void UHczsUltimateVideoTestSubsystem::VideoStarted(const FString& Sequence)
{
    ++StartedCount; RecordEvent(TEXT("started"), Sequence);
    if (Sequence != SequenceId || StartedCount != 1) Failure = TEXT("Invalid or duplicate real media Started callback");
    UWorld* World = GetGameInstance()->GetWorld();
    bPausedDuringVideo = UGameplayStatics::IsGamePaused(World);
    WorldTimeAtStart = World->GetTimeSeconds();
    if (!bPausedDuringVideo) Failure = TEXT("Movie started while world simulation was still advancing");
}

void UHczsUltimateVideoTestSubsystem::VideoFinished(const FString& Sequence, EHczsUltimateVideoFinish Result, const FString& Message)
{
    ++FinishedCount; RecordEvent(TEXT("finished"), Sequence);
    TerminalAt = FPlatformTime::Seconds();
    bTerminalCompleted = Result == EHczsUltimateVideoFinish::Completed;
    UWorld* World = GetGameInstance()->GetWorld();
    WorldTimeAtFinish = World->GetTimeSeconds();
    bResumedAfterVideo = !UGameplayStatics::IsGamePaused(World);
    if (bResumedAfterVideo == bPrepausedCase || FMath::Abs(WorldTimeAtFinish - WorldTimeAtStart) > 0.05)
        Failure = TEXT("Movie did not hold world simulation and restore it before completion");
    bTerminalExpected = bCancelCase ? Result == EHczsUltimateVideoFinish::Cancelled : bTerminalCompleted;
    if (Sequence != SequenceId || FinishedCount != 1 || !bTerminalExpected)
        Failure = FString::Printf(TEXT("Media terminal callback was not exactly one successful completion: %s"), *Message);
    // Only this fixture owns the pre-existing test pause; the player must retain it.
    if (bPrepausedCase) UGameplayStatics::SetGamePaused(World, false);
}

bool UHczsUltimateVideoTestSubsystem::MountVideo()
{
    UGameViewportClient* Viewport = GetGameInstance()->GetGameViewportClient();
    if (!Viewport || !DisplayTexture || !Video) return false;
    VideoBrush.DrawAs = ESlateBrushDrawType::Image;
    VideoBrush.ImageSize = FVector2f(SourceWidth, SourceHeight);
    VideoBrush.SetResourceObject(DisplayTexture);
    BlackBrush = FSlateColorBrush(FLinearColor::Black);
    Paint = MakeShared<FHczsUltimateVideoPaintObservation>(); Paint->Video = Video; Paint->Texture = DisplayTexture;
    Overlay = SNew(SBorder).BorderImage(&BlackBrush).Padding(0)
        .HAlign(HAlign_Fill).VAlign(VAlign_Fill).Visibility(EVisibility::HitTestInvisible)
        [SNew(SScaleBox).Stretch(EStretch::ScaleToFit).HAlign(HAlign_Center).VAlign(VAlign_Center)
            [SNew(SBox).WidthOverride(SourceWidth).HeightOverride(SourceHeight)
                [SNew(SObservedUltimateImage).Brush(&VideoBrush).Observation(Paint)]]];
    Viewport->AddViewportWidgetContent(Overlay.ToSharedRef(), 100000);
    return true;
}

bool UHczsUltimateVideoTestSubsystem::TickTest(float DeltaSeconds)
{
    if (bFinished) return false;
    if (!Failure.IsEmpty()) { FinishTest(false, Failure); return false; }
    const double Now = FPlatformTime::Seconds();
    if (Now >= Deadline) { FinishTest(false, TEXT("Real-time media acceptance deadline exceeded")); return false; }
    if (bAwaitingScreenshot && Now >= ScreenshotDeadline) { FinishTest(false, TEXT("Native viewport screenshot timed out")); return false; }
    if (Step == 0)
    {
        UWorld* World = GetGameInstance() ? GetGameInstance()->GetWorld() : nullptr;
        UGameViewportClient* Viewport = GetGameInstance() ? GetGameInstance()->GetGameViewportClient() : nullptr;
        if (!World || !World->HasBegunPlay() || !Viewport || !Viewport->Viewport) return true;
        MapName = World->GetMapName();
        if (World->WorldType != EWorldType::Game || !MapName.EndsWith(TEXT("L_ElsaHallFxPreview")))
        { FinishTest(false, TEXT("Run the explicit media test in the hall with -game, not an editor/PIE/business battle")); return false; }
        FActorSpawnParameters Params; Params.ObjectFlags |= RF_Transient;
        Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
        TestActor = World->SpawnActor<AActor>(AActor::StaticClass(), FTransform::Identity, Params);
        if (!TestActor) { FinishTest(false, TEXT("Cannot spawn the dedicated transient media test actor")); return false; }
        Video = NewObject<UHczsUltimateVideoPlayer>(TestActor, NAME_None, RF_Transient);
        TestActor->AddInstanceComponent(Video); Video->RegisterComponent();
        Video->OnReadyNative.AddUObject(this, &UHczsUltimateVideoTestSubsystem::VideoReady);
        Video->OnStartedNative.AddUObject(this, &UHczsUltimateVideoTestSubsystem::VideoStarted);
        Video->OnFinishedNative.AddUObject(this, &UHczsUltimateVideoTestSubsystem::VideoFinished);
        if (bPrepausedCase && !UGameplayStatics::SetGamePaused(World, true))
        { FinishTest(false, TEXT("Cannot establish pre-existing pause test case")); return false; }
        Step = 1;
        if (!Video->PrepareElsa(SequenceId, 1.0f, true, 1.0f))
        { if (Failure.IsEmpty()) Failure = TEXT("PrepareElsa rejected the original staged movie"); return true; }
        const UMediaPlayer* OriginalPlayer = Video->GetMediaPlayer();
        bDuplicatePrepareAccepted = Video->PrepareElsa(SequenceId, 1.0f, true, 1.0f) && Video->GetMediaPlayer() == OriginalPlayer;
        if (!bDuplicatePrepareAccepted) Failure = TEXT("Duplicate prepare did not retain the same media instance");
    }
    else if (Step == 1 && ReadyCount == 1 && Video && Video->GetState() == EHczsUltimateVideoState::Ready)
    {
        if (!MountVideo()) { FinishTest(false, TEXT("Cannot mount the decoded texture's Slate image")); return false; }
        Step = 2;
        if (!Video->PlayPrepared(SequenceId)) { Failure = TEXT("PlayPrepared rejected a ready movie"); return true; }
        bDuplicatePlayAccepted = Video->PlayPrepared(SequenceId);
        if (!bDuplicatePlayAccepted) Failure = TEXT("Repeated play of the active sequence was not idempotent");
    }
    else if (Step == 2)
    {
        if (bCancelCase && bScreenshotValid && !bAwaitingScreenshot && !bCancelIssued)
        { bCancelIssued = true; Video->Cancel(SequenceId); }
        if (!bAwaitingScreenshot && !Screenshot && Video && Video->GetMediaPlayer() && Paint &&
            Video->HasDecodedVideoSurface() && Paint->Serial > 0 && Paint->bDecodedSurface &&
            Video->GetMediaPlayer()->GetTime().GetTotalSeconds() >= CaptureSeconds && Paint->MediaSeconds >= CaptureSeconds - 0.1)
            CaptureFrame();
        if (FinishedCount > 0 && !bAwaitingScreenshot)
        {
            if (!bScreenshotValid) { FinishTest(false, TEXT("Movie ended without a decoded and actually painted video screenshot")); return false; }
            if (Now >= TerminalAt + 0.3)
            {
                bRetiredSequenceRejected = !Video->PrepareElsa(SequenceId, 1.0f, true, 1.0f);
                bRetiredPlayRejected = !Video->PlayPrepared(SequenceId);
                Video->Cancel(SequenceId); Video->Release();
                Step = 3; SettleUntil = Now + 0.3;
            }
        }
    }
    else if (Step == 3 && Now >= SettleUntil)
    {
        const bool bPassed = ReadyCount == 1 && StartedCount == 1 && FinishedCount == 1 && bTerminalExpected &&
            bDuplicatePrepareAccepted && bDuplicatePlayAccepted && bRetiredSequenceRejected && bRetiredPlayRejected && bScreenshotValid &&
            bPausedDuringVideo && bResumedAfterVideo != bPrepausedCase && GetGameInstance()->GetWorld()->GetTimeSeconds() > WorldTimeAtFinish;
        FinishTest(bPassed, bPassed ? FString() : TEXT("Native video callback/idempotency acceptance failed")); return false;
    }
    return true;
}

void UHczsUltimateVideoTestSubsystem::CaptureFrame()
{
    RequestedFrameSeconds = Video->GetMediaPlayer()->GetTime().GetTotalSeconds();
    if (RequestedFrameSeconds > CaptureSeconds + 0.75)
    { Failure = TEXT("Decoded frame missed the bounded 0.8-second capture window"); return; }
    RequestedPaintSerial = Paint->Serial;
    Screenshot = MakeShared<FJsonObject>();
    Screenshot->SetStringField(TEXT("path"), ScreenshotPath);
    Screenshot->SetNumberField(TEXT("requestedMediaSeconds"), RequestedFrameSeconds);
    Screenshot->SetNumberField(TEXT("requestedAtUnixMs"), UnixMs());
    Screenshot->SetNumberField(TEXT("requestedPaintSerial"), RequestedPaintSerial);
    Screenshot->SetBoolField(TEXT("decodedSurfaceAtRequest"), Video->HasDecodedVideoSurface());
    bAwaitingScreenshot = true; ScreenshotDeadline = FPlatformTime::Seconds() + 10.0;
    ScreenshotHandle = UGameViewportClient::OnScreenshotCaptured().AddUObject(this, &UHczsUltimateVideoTestSubsystem::ScreenshotCaptured);
    FScreenshotRequest::RequestScreenshot(ScreenshotPath, true, false);
}

void UHczsUltimateVideoTestSubsystem::ScreenshotCaptured(int32 Width, int32 Height, const TArray<FColor>& Pixels)
{
    UGameViewportClient::OnScreenshotCaptured().Remove(ScreenshotHandle); ScreenshotHandle.Reset();
    if (!bAwaitingScreenshot || bFinished || !Screenshot) return;
    bAwaitingScreenshot = false;
    if (Width < 64 || Height < 64 || Width > 8192 || Height > 8192 || static_cast<int64>(Width) * Height != Pixels.Num())
    { Failure = TEXT("Native viewport capture has invalid pixel dimensions"); return; }
    TArray64<uint8> Png;
    FImageUtils::PNGCompressImageArray(Width, Height, TArrayView64<const FColor>(Pixels.GetData(), Pixels.Num()), Png);
    if (Png.IsEmpty() || !FFileHelper::SaveArrayToFile(Png, *ScreenshotPath))
    { Failure = TEXT("Cannot save actual viewport PNG evidence"); return; }
    const double Scale = FMath::Min(static_cast<double>(Width) / SourceWidth, static_cast<double>(Height) / SourceHeight);
    const double Left = (Width - SourceWidth * Scale) * 0.5, Top = (Height - SourceHeight * Scale) * 0.5;
    int64 InnerCount = 0, NonBlack = 0, BarCount = 0, BlackBars = 0;
    int32 MinLuma = 765, MaxLuma = 0;
    for (int32 Y = 0; Y < Height; ++Y) for (int32 X = 0; X < Width; ++X)
    {
        const FColor& Pixel = Pixels[Y * Width + X]; const int32 Luma = Pixel.R + Pixel.G + Pixel.B;
        if (X >= Left + 3 && X < Width - Left - 3 && Y >= Top + 3 && Y < Height - Top - 3)
        { ++InnerCount; NonBlack += Luma > 30 ? 1 : 0; MinLuma = FMath::Min(MinLuma, Luma); MaxLuma = FMath::Max(MaxLuma, Luma); }
        else if (X < Left - 3 || X > Width - Left + 3 || Y < Top - 3 || Y > Height - Top + 3)
        { ++BarCount; BlackBars += Luma <= 30 ? 1 : 0; }
    }
    const double NonBlackRatio = InnerCount ? static_cast<double>(NonBlack) / InnerCount : 0.0;
    const double BlackBarRatio = BarCount ? static_cast<double>(BlackBars) / BarCount : 1.0;
    const double PaintedAspect = Paint && Paint->AbsoluteSize.Y > 0 ? Paint->AbsoluteSize.X / Paint->AbsoluteSize.Y : 0.0;
    Screenshot->SetNumberField(TEXT("width"), Width); Screenshot->SetNumberField(TEXT("height"), Height);
    Screenshot->SetNumberField(TEXT("capturedAtUnixMs"), UnixMs());
    Screenshot->SetNumberField(TEXT("paintSerial"), Paint ? Paint->Serial : 0);
    Screenshot->SetNumberField(TEXT("paintedMediaSeconds"), Paint ? Paint->MediaSeconds : -1);
    Screenshot->SetNumberField(TEXT("paintedAspectRatio"), PaintedAspect);
    Screenshot->SetNumberField(TEXT("videoNonBlackRatio"), NonBlackRatio);
    Screenshot->SetNumberField(TEXT("videoLumaRange"), MaxLuma - MinLuma);
    Screenshot->SetNumberField(TEXT("letterboxBlackRatio"), BlackBarRatio);
    Screenshot->SetBoolField(TEXT("actualSImagePaint"), Paint && Paint->Serial > RequestedPaintSerial);
    Screenshot->SetBoolField(TEXT("nativeViewportPixels"), true);
    bScreenshotValid = Paint && Paint->Serial > RequestedPaintSerial && Paint->bDecodedSurface &&
        Paint->MediaSeconds >= CaptureSeconds - 0.1 && Paint->MediaSeconds <= CaptureSeconds + 0.75 &&
        FMath::Abs(PaintedAspect - static_cast<double>(SourceWidth) / SourceHeight) < 0.005 &&
        NonBlackRatio > 0.005 && MaxLuma - MinLuma > 20 && BlackBarRatio >= 0.98;
    Screenshot->SetBoolField(TEXT("passed"), bScreenshotValid);
    if (!bScreenshotValid) Failure = TEXT("Screenshot did not prove a decoded SImage video frame with preserved aspect and black letterbox");
}

bool UHczsUltimateVideoTestSubsystem::SaveReport(bool bPassed, const FString& Reason)
{
    auto Object = MakeShared<FJsonObject>();
    Object->SetStringField(TEXT("schema"), TEXT("hczs-ultimate-video-native-acceptance-v1"));
    Object->SetBoolField(TEXT("passed"), bPassed); Object->SetStringField(TEXT("failure"), Reason);
    Object->SetStringField(TEXT("sequenceId"), SequenceId); Object->SetStringField(TEXT("map"), MapName);
    Object->SetStringField(TEXT("startedAtUtc"), StartedAtUtc); Object->SetNumberField(TEXT("startedAtUnixMs"), StartedAtUnixMs);
    Object->SetNumberField(TEXT("finishedAtUnixMs"), UnixMs()); Object->SetNumberField(TEXT("ueProcessId"), FPlatformProcess::GetCurrentProcessId());
    Object->SetStringField(TEXT("movie"), TEXT("Content/Movies/Recovered/Ultimates/aiersha_1.mp4"));
    Object->SetNumberField(TEXT("sourceWidth"), SourceWidth); Object->SetNumberField(TEXT("sourceHeight"), SourceHeight);
    Object->SetNumberField(TEXT("durationSeconds"), DurationSeconds); Object->SetStringField(TEXT("decoder"), Decoder);
    Object->SetNumberField(TEXT("readyCount"), ReadyCount); Object->SetNumberField(TEXT("startedCount"), StartedCount);
    Object->SetNumberField(TEXT("finishedCount"), FinishedCount); Object->SetBoolField(TEXT("completed"), bTerminalCompleted);
    Object->SetBoolField(TEXT("duplicatePrepareIdempotent"), bDuplicatePrepareAccepted);
    Object->SetBoolField(TEXT("worldPausedDuringVideo"), bPausedDuringVideo);
    Object->SetBoolField(TEXT("prepausedCase"), bPrepausedCase);
    Object->SetBoolField(TEXT("cancelCase"), bCancelCase);
    Object->SetBoolField(TEXT("expectedTerminal"), bTerminalExpected);
    Object->SetBoolField(TEXT("worldResumedBeforeCompletion"), bResumedAfterVideo);
    Object->SetNumberField(TEXT("worldTimeDuringVideo"), WorldTimeAtFinish - WorldTimeAtStart);
    Object->SetBoolField(TEXT("duplicatePlayIdempotent"), bDuplicatePlayAccepted);
    Object->SetBoolField(TEXT("retiredPrepareRejected"), bRetiredSequenceRejected);
    Object->SetBoolField(TEXT("retiredPlayRejected"), bRetiredPlayRejected);
    Object->SetBoolField(TEXT("releaseAndCancelDidNotRepeatFinish"), Step == 3 && FinishedCount == 1);
    if (Screenshot) Object->SetObjectField(TEXT("screenshot"), Screenshot);
    Object->SetArrayField(TEXT("events"), Events);
    auto Scope = MakeShared<FJsonObject>();
    Scope->SetBoolField(TEXT("serverPortExplicitlyDisabled"), bNoBusinessServer);
    Scope->SetBoolField(TEXT("profileOrBattleCommandsIssued"), false);
    Scope->SetBoolField(TEXT("audioAudibilityVerified"), false); Scope->SetBoolField(TEXT("mutedForAcceptance"), true);
    Scope->SetBoolField(TEXT("readyTreatedAsVisible"), false); Scope->SetBoolField(TEXT("inBattleCueIntegrationVerified"), false);
    Scope->SetBoolField(TEXT("humanVisualReviewVerified"), false);
    Object->SetObjectField(TEXT("scope"), Scope);
    FString Text; FJsonSerializer::Serialize(Object, TJsonWriterFactory<>::Create(&Text));
    return FFileHelper::SaveStringToFile(Text, *ReportPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
}

void UHczsUltimateVideoTestSubsystem::FinishTest(bool bPassed, const FString& Reason)
{
    if (bFinished) return;
    bFinished = true;
    const bool bSaved = SaveReport(bPassed, Reason);
    UE_LOG(LogTemp, Display, TEXT("HCZS ultimate video acceptance finished: passed=%d saved=%d reason=%s report=%s"), bPassed, bSaved, *Reason, *ReportPath);
    Cleanup();
    FPlatformMisc::RequestExitWithStatus(false, bPassed && bSaved ? 0 : 1);
}

void UHczsUltimateVideoTestSubsystem::Cleanup()
{
    if (ScreenshotHandle.IsValid()) UGameViewportClient::OnScreenshotCaptured().Remove(ScreenshotHandle);
    ScreenshotHandle.Reset(); bAwaitingScreenshot = false;
    if (Overlay && GetGameInstance() && GetGameInstance()->GetGameViewportClient())
        GetGameInstance()->GetGameViewportClient()->RemoveViewportWidgetContent(Overlay.ToSharedRef());
    Overlay.Reset(); Paint.Reset(); VideoBrush.SetResourceObject(nullptr); DisplayTexture = nullptr;
    if (Video)
    {
        Video->OnReadyNative.RemoveAll(this); Video->OnStartedNative.RemoveAll(this); Video->OnFinishedNative.RemoveAll(this);
        Video->Release(); Video->DestroyComponent(); Video = nullptr;
    }
    if (TestActor) { TestActor->Destroy(); TestActor = nullptr; }
}

void UHczsUltimateVideoTestSubsystem::Deinitialize()
{
    if (TickHandle.IsValid()) FTSTicker::RemoveTicker(TickHandle);
    TickHandle.Reset();
    if (bInitialized && !bFinished) { bFinished = true; SaveReport(false, TEXT("Game instance ended before native media acceptance completed")); }
    Cleanup(); Super::Deinitialize();
}
