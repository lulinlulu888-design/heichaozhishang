param(
    [ValidateSet('validate','build','package')][string]$Action='validate',
    [ValidateSet('arm64','x64')][string]$Architecture='arm64',
    [string]$EngineRoot='D:/Program Files/Epic Games/UE_5.8',
    [string]$SdkRoot='D:/Android/Sdk',
    [string]$JavaRoot='C:/Program Files/Microsoft/jdk-17.0.19.10-hotspot'
)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskProject=Join-Path $taskRoot 'clients/unreal5 5.8/Hczs.uproject'
$taskSdk=Get-Content (Join-Path $EngineRoot 'Engine/Config/Android/Android_SDK.json') -Raw | ConvertFrom-Json
$taskNdk=Join-Path $SdkRoot ('ndk/'+$taskSdk.ndk)
foreach($taskRequired in @($taskProject,(Join-Path $JavaRoot 'bin/java.exe'),(Join-Path $taskNdk 'source.properties'),(Join-Path $SdkRoot ('build-tools/'+$taskSdk.'build-tools'+'/aapt2.exe')))){
    if(!(Test-Path -LiteralPath $taskRequired)){throw "Missing prerequisite: $taskRequired"}
}
$taskLogs=Join-Path $taskRoot 'analysis/unreal/android-build'
New-Item -ItemType Directory -Path $taskLogs -Force | Out-Null
$taskLog=Join-Path $taskLogs ($Action+'-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.log')
$taskSaved=@{}
foreach($taskName in @('ANDROID_HOME','ANDROID_SDK_ROOT','JAVA_HOME','NDKROOT','NDK_HOME')){
    $taskSaved[$taskName]=[Environment]::GetEnvironmentVariable($taskName,'Process')
}
try{
    $env:ANDROID_HOME=$SdkRoot
    $env:ANDROID_SDK_ROOT=$SdkRoot
    $env:JAVA_HOME=$JavaRoot
    $env:NDKROOT=$taskNdk
    $env:NDK_HOME=$taskNdk
    $taskBuild=Join-Path $EngineRoot 'Engine/Build/BatchFiles/Build.bat'
    if($Action -eq 'validate'){
        & $taskBuild -Mode=ValidatePlatforms -Platforms=Android -OutputSDKs "-Log=$taskLog"
        if($LASTEXITCODE -ne 0){throw "Platform validation failed; see $taskLog"}
        if(!(Select-String -LiteralPath $taskLog -SimpleMatch 'Android VALID')){throw "Android validation did not report VALID; see $taskLog"}
    }elseif($Action -eq 'package'){
        $taskArchive=Join-Path $taskRoot ('runtime/dist/unreal-android-'+$Architecture+'-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
        & (Join-Path $EngineRoot 'Engine/Build/BatchFiles/RunUAT.bat') BuildCookRun "-project=$taskProject" -noP4 -unattended -platform=Android "-clientarchitecture=$Architecture" -cookflavor=ASTC -clientconfig=Development -build -cook -stage -pak -package -archive "-archivedirectory=$taskArchive" '-AdditionalCookerOptions=-DDC=InstalledNoZenLocalFallback' 2>&1 | Tee-Object -FilePath $taskLog
        if($LASTEXITCODE -ne 0){throw "Android packaging failed; see $taskLog"}
        Write-Output "Archive: $taskArchive"
    }else{
        if(!(Test-Path -LiteralPath (Join-Path $EngineRoot 'Engine/Build/Android/Java'))){throw 'Install the Android optional component for this engine in Epic Games Launcher first.'}
        & $taskBuild Hczs Android Development "-Project=$taskProject" "-Architecture=$Architecture" -WaitMutex -NoHotReloadFromIDE -NoUBA "-Log=$taskLog"
        if($LASTEXITCODE -ne 0){throw "Android project build failed; see $taskLog"}
    }
    Write-Output "Completed $Action. Log: $taskLog. This does not verify packaging or Android runtime behavior."
}finally{
    foreach($taskName in $taskSaved.Keys){[Environment]::SetEnvironmentVariable($taskName,$taskSaved[$taskName],'Process')}
}
