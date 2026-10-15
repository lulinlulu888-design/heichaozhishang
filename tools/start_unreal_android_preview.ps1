param(
    [string]$Serial='emulator-5556',
    [ValidateRange(1,65535)][int]$ServerPort=7460,
    [switch]$HallEnvironmentComparison,
    [switch]$HallSourceSunComparison,
    [string]$Adb='D:/Android/Sdk/platform-tools/adb.exe'
)
$ErrorActionPreference='Stop'
if($HallEnvironmentComparison -and $HallSourceSunComparison){throw 'Choose one hall comparison at a time.'}
function Invoke-HczsAdb {
    & $Adb -s $Serial @args
    if($LASTEXITCODE -ne 0){throw "ADB command failed: $args"}
}
$taskAbi=Invoke-HczsAdb shell getprop ro.product.cpu.abilist
if($Serial -notmatch '^emulator-' -or $taskAbi.Trim() -ne 'x86_64'){
    throw 'This launcher is verified only for the x86_64 Android emulator. Device render settings require separate verification.'
}
$taskPackage=Invoke-HczsAdb shell pm path com.YourCompany.Hczs
if(!$taskPackage){throw 'Install the packaged Hczs x64 APK and its matching OBB first.'}
Invoke-HczsAdb reverse "tcp:$ServerPort" "tcp:$ServerPort"
# The emulator profile disables Vulkan despite reporting Vulkan support. ES 3.1
# is insufficient for this UE release. Occlusion queries trigger a null UAV in
# the current mobile base pass; disable that optimization only for this preview.
$taskCommandLine="-DPCVars=r.Android.DisableVulkanSupport=0,r.AllowOcclusionQueries=0 -HczsServerPort=$ServerPort"
if($HallEnvironmentComparison){
    # Diagnostic entry map only; returning from battle retains the normal hall.
    $taskCommandLine='/Game/Recovered/Hall/Maps/L_ElsaHallSourceSHComparisonV2 '+$taskCommandLine
}
if($HallSourceSunComparison){
    $taskCommandLine='/Game/Recovered/Hall/Maps/L_ElsaHallSourceSunComparison '+$taskCommandLine
}
Invoke-HczsAdb shell am force-stop com.YourCompany.Hczs
Invoke-HczsAdb shell am start -n com.YourCompany.Hczs/com.epicgames.unreal.GameActivity --es cmdline "'$taskCommandLine'"
Write-Output 'Launch requested. Verify the screen and runtime logs before claiming successful gameplay.'
