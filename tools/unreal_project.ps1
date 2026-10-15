param(
    [ValidateSet('build','open','preview','import','verify')][string]$Action='preview',
    [ValidateSet('elsa','shiranui')][string]$Hero='elsa',
    [ValidateSet('base','lighting','fx')][string]$View='fx',
    [switch]$Capture,
    [switch]$OriginalIcons,
    [switch]$ShowEngineMessages,
    [string]$EngineRoot='D:\Program Files\Epic Games\UE_5.8'
)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskClientRoot=Join-Path $taskRoot 'clients\unreal5 5.8'
if(!(Test-Path -LiteralPath (Join-Path $taskClientRoot 'Hczs.uproject'))){$taskClientRoot=Join-Path $taskRoot 'clients\unreal5'}
$taskProject=Join-Path $taskClientRoot 'Hczs.uproject'
if(!(Test-Path -LiteralPath $taskProject)){throw 'The UE5.8 Hczs project descriptor is missing.'}
$taskLogs=Join-Path $taskRoot 'runtime\unreal'
New-Item -ItemType Directory -Path $taskLogs -Force | Out-Null
$taskVersion=Get-Content (Join-Path $EngineRoot 'Engine\Build\Build.version') -Raw | ConvertFrom-Json
if($taskVersion.MajorVersion -ne 5 -or $taskVersion.MinorVersion -ne 8){throw 'This project is verified with UE 5.8; inspect compatibility before changing engines.'}
if($Action -eq 'build'){
    & (Join-Path $EngineRoot 'Engine\Build\BatchFiles\Build.bat') HczsEditor Win64 Development "-Project=$taskProject" -WaitMutex -NoHotReloadFromIDE -NoUBA
    if($LASTEXITCODE -ne 0){throw "Unreal build failed: $LASTEXITCODE"}
    return
}
if($Action -in @('import','verify')){
    $taskScript=if($Action -eq 'import'){'import_recovered_assets.py'}else{'verify_imported_assets.py'}
    $taskOriginalApply=$env:HCZS_UE_IMPORT_APPLY
    $taskOriginalIds=$env:HCZS_UE_IMPORT_IDS
    $taskOriginalSuffix=$env:HCZS_UE_REPORT_SUFFIX
    try{
        $env:HCZS_UE_IMPORT_IDS=if($Hero -eq 'elsa'){'elsa'}else{'shiranui,shiranui_weapon'}
        $env:HCZS_UE_REPORT_SUFFIX=$Hero
        if($Action -eq 'import'){
            $env:HCZS_UE_IMPORT_APPLY='1'
            if(!(Test-Path (Join-Path $taskClientRoot 'Content\Recovered\Hall\Maps\L_RecoveredHall.umap'))){$env:HCZS_UE_IMPORT_IDS='hall_scene,'+$env:HCZS_UE_IMPORT_IDS}
        }
        & (Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe') $taskProject -run=pythonscript "-script=$(Join-Path $taskRoot "tools\unreal\$taskScript")" -unattended -nosplash -NoSound "-abslog=$(Join-Path $taskLogs "$Action-$Hero.log")"
        if($LASTEXITCODE -ne 0){throw "Unreal $Action failed: $LASTEXITCODE"}
    }finally{$env:HCZS_UE_IMPORT_APPLY=$taskOriginalApply; $env:HCZS_UE_IMPORT_IDS=$taskOriginalIds; $env:HCZS_UE_REPORT_SUFFIX=$taskOriginalSuffix}
    return
}
$taskMapName=if($Hero -eq 'elsa'){'L_ElsaHallAlignedPreview'}else{'L_ShiranuiHallPreview'}
if($Hero -eq 'elsa' -and $View -ne 'base'){
    $taskCandidate=if($View -eq 'fx'){'L_ElsaHallFxPreview'}else{'L_ElsaHallLightingPreview'}
    if(Test-Path -LiteralPath (Join-Path $taskClientRoot ('Content\Recovered\Hall\Maps\'+$taskCandidate+'.umap'))){$taskMapName=$taskCandidate}
}
$taskMap='/Game/Recovered/Hall/Maps/'+$taskMapName
$taskMapFile=Join-Path $taskClientRoot ('Content\Recovered\Hall\Maps\'+$taskMapName+'.umap')
if(!(Test-Path -LiteralPath $taskMapFile)){throw 'Run the verified import and setup_unreal_hall.py first; the generated preview map is missing.'}
$taskArguments=@(('"'+$taskProject+'"'),$taskMap,'-nosplash',('-abslog="'+(Join-Path $taskLogs "$Action-$Hero.log")+'"'))
if(!$OriginalIcons -and (Test-Path -LiteralPath (Join-Path $taskClientRoot 'Content\Recovered\Hall\UI\AI\HallLayoutHD.uasset'))){$taskArguments+='-HczsHDIcons'}
if($Action -eq 'preview'){
    $taskArguments+=@('-game','-windowed','-ResX=1600','-ResY=900','-NoSound')
    if(!$ShowEngineMessages){$taskArguments+='-ExecCmds="DisableAllScreenMessages"'}
    if($Capture){
        $taskViewSuffix=if($taskMapName -eq 'L_ElsaHallFxPreview'){'-fx'}elseif($taskMapName -eq 'L_ElsaHallLightingPreview'){'-lighting'}else{''}
        $taskCaptureFile=Join-Path $taskRoot ('analysis\unreal\plan\hall-'+$Hero+$taskViewSuffix+'-render.png')
        $taskArguments+=('-HczsCapture="'+$taskCaptureFile+'"')
    }
}
if($Action -eq 'open' -and $Hero -eq 'elsa'){
    $taskEditorScript=Join-Path $taskRoot 'tools\open_unreal_hall_editor.py'
    $taskArguments+=('-ExecutePythonScript="'+$taskEditorScript+'"')
}
$taskPriorOpenMap=$env:HCZS_UE_OPEN_MAP
try{
    $env:HCZS_UE_OPEN_MAP=$taskMap
    $taskProcess=Start-Process -FilePath (Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe') -ArgumentList $taskArguments -PassThru
}finally{$env:HCZS_UE_OPEN_MAP=$taskPriorOpenMap}
Write-Output "Unreal $Action started, PID=$($taskProcess.Id), engine=$($taskVersion.MajorVersion).$($taskVersion.MinorVersion).$($taskVersion.PatchVersion)"
