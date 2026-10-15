param(
    [ValidateSet('build-web', 'build-windows', 'generate-windows', 'compile-windows', 'run-windows', 'build-android', 'generate-android', 'compile-android', 'open')]
    [string]$Action = 'build-web',
    [ValidateSet('standard', 'model')]
    [string]$WindowsVariant = 'standard',
    [ValidateSet('device', 'emulator')]
    [string]$AndroidVariant = 'device'
)
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$creator = Join-Path $workspace '.tools\cocos\3.8.8\CocosCreator.exe'
$project = Join-Path $workspace 'legacy\cocos-poc'
$windowsConfig = if ($WindowsVariant -eq 'model') { 'build-windows-model.json' } else { 'build-windows.json' }
$windowsOutput = if ($WindowsVariant -eq 'model') { 'build\windows-model' } else { 'build\windows' }
$androidConfig = if ($AndroidVariant -eq 'emulator') { 'build-android-emulator.json' } else { 'build-android.json' }
$androidOutput = if ($AndroidVariant -eq 'emulator') { 'build\android-emulator' } else { 'build\android' }
$evidence = Join-Path $workspace $(if ($Action -match 'windows') { if ($WindowsVariant -eq 'model') { 'analysis\cocos-native-model' } else { 'analysis\cocos-native' } } elseif ($Action -match 'android') { if ($AndroidVariant -eq 'emulator') { 'analysis\cocos-android-emulator' } else { 'analysis\cocos-android' } } else { 'analysis\cocos-toolchain' })
if (-not (Test-Path -LiteralPath $creator)) {
    throw 'Creator is missing. Run tools/setup_cocos.py with Python first.'
}
if (-not (Test-Path -LiteralPath (Join-Path $project 'package.json'))) {
    throw 'The proof project is missing. Run tools/create_cocos_poc.py first.'
}
$arguments = @('--project', ('"' + $project + '"'), ('--user-data-dir="' + (Join-Path $workspace '.tools\cocos\3.8.8\electron-user-data') + '"'))
if ($Action -eq 'open') {
    # Explicit manual editor launch for the person invoking this command.
    Start-Process -FilePath $creator -ArgumentList $arguments | Out-Null
    return
}
New-Item -ItemType Directory -Path $evidence -Force | Out-Null

function Save-ExportFingerprints([string]$ConfigName) {
    $sourcePaths = @('assets\ToolchainProof.ts', 'assets\RecoveredCharacterView.ts',
        'assets\PrologueSceneView.ts',
        'assets\PrologueLighting.ts',
        'assets\resources\recovered\prologue\lightmap.effect',
        'assets\resources\recovered\prologue\lightmaps.json',
        'assets\resources\recovered\prologue\provenance.json',
        'assets\resources\recovered\prologue\scene\scene.glb',
        'assets\resources\recovered\prologue\actor\actor.glb',
        'assets\resources\recovered\prologue\weapon\weapon.glb',
        'assets\resources\recovered\prologue\weapon-binding.json',
        'assets\resources\recovered\prologue\player-orientation.json',
        'assets\resources\recovered\prologue\enemy\enemy.glb',
        'assets\resources\recovered\prologue\cameras.json',
        'assets\TutorialBattleController.ts', 'assets\TutorialBattleView.ts',
        'assets\TargetArrowGeometry.ts',
        'assets\EnemyTurnPresentation.ts',
        'assets\EndTurnView.ts',
        'assets\VictoryTitleView.ts',
        'assets\resources\recovered\result-ui\victory-title.json',
        'assets\resources\recovered\result-ui\provenance.json',
        'assets\resources\recovered\end-turn\end-turn.json',
        'assets\CardSelectionView.ts', 'assets\resources\recovered\card-selection\selection.json',
        'assets\TargetArrowView.ts', 'assets\resources\recovered\target-arrow\provenance.json',
        'assets\resources\recovered\target-arrow\target-arrow.effect',
        'assets\resources\recovered\cards\provenance.json',
        'assets\resources\recovered\battle-ui\provenance.json',
        'assets\resources\recovered\card-frames\provenance.json',
        'assets\ToolchainProof.scene', 'assets\resources\recovered\models\elsa\elsa.glb',
        'assets\resources\recovered\models\enemy991\enemy991.glb',
        'settings\v2\packages\engine.json', 'asset-provenance.json', $ConfigName) |
        ForEach-Object { Join-Path $project $_ }
    $sourcePaths += Join-Path $project 'assets\CitySceneView.ts'
    $sourcePaths += @('assets\HallSceneView.ts', 'assets\HallLighting.ts', 'assets\ShiranuiFlames.ts') |
        ForEach-Object { Join-Path $project $_ }
    $sourcePaths += @(Get-ChildItem -LiteralPath (Join-Path $project 'assets\resources\recovered\hall') -File -Recurse | ForEach-Object { $_.FullName })
    $sourcePaths += Join-Path $project 'assets\resources\recovered\battle-ui\breakdown-icon.png'
    $sourcePaths += @(Get-ChildItem -LiteralPath (Join-Path $project 'assets\resources\recovered\city') -File -Recurse | ForEach-Object { $_.FullName })
    Get-FileHash -LiteralPath $sourcePaths -Algorithm SHA256 |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'export-source-fingerprints.json')
}

function Invoke-CreatorBuild([string]$ConfigName, [string]$Stage, [string]$LogName) {
    if ($Stage -eq 'build') { Save-ExportFingerprints $ConfigName }
    $buildArguments = $arguments + @('--build', ('"configPath=' + (Join-Path $project $ConfigName) + ';stage=' + $Stage + '"'))
    $process = Start-Process -FilePath $creator -ArgumentList $buildArguments -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $evidence "$LogName.stdout.log") `
        -RedirectStandardError (Join-Path $evidence "$LogName.stderr.log")
    # Wait for Creator itself. Start-Process -Wait can also wait indefinitely for
    # native tool console hosts after Creator has already finished.
    $null = $process.Handle
    $process.WaitForExit()
    $process.ExitCode | Set-Content -LiteralPath (Join-Path $evidence "$LogName.exit-code.txt")
    if ($process.ExitCode -ne 36) {
        throw "Creator $Stage returned $($process.ExitCode); see $evidence\$LogName.*.log"
    }
}

if ($Action -match 'android') {
    $android = (Get-Content -LiteralPath (Join-Path $project $androidConfig) -Raw | ConvertFrom-Json).packages.android
    $java = Join-Path $android.javaHome 'bin\java.exe'
    $cmakeRoot = Join-Path (Split-Path -Parent $creator) 'resources\tools\cmake'
    $ninjaRoot = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja'
    foreach ($required in @($java, (Join-Path $android.sdkPath 'platforms\android-36\android.jar'),
        (Join-Path $android.sdkPath 'build-tools\35.0.0\aapt2.exe'), (Join-Path $android.ndkPath 'source.properties'),
        (Join-Path $cmakeRoot 'bin\cmake.exe'), (Join-Path $ninjaRoot 'ninja.exe'))) {
        if (-not (Test-Path -LiteralPath $required)) { throw "Missing existing Android build prerequisite: $required" }
    }
    if ($Action -in @('build-android', 'generate-android')) {
        Invoke-CreatorBuild $androidConfig 'build' 'generate-android'
        Write-Output 'Android assets and Gradle project exported; APK compilation is a separate step.'
    }
    if ($Action -eq 'generate-android') { return }
    $androidProject = Join-Path $project (Join-Path $androidOutput 'proj')
    $androidAppGradle = Join-Path $project 'native\engine\android\app\build.gradle'
    $wrapperJar = Join-Path $androidProject 'gradle\wrapper\gradle-wrapper.jar'
    if (-not (Test-Path -LiteralPath $wrapperJar)) { throw 'Android export is missing. Run generate-android or build-android first.' }
    $wrapperProperties = Join-Path $androidProject 'gradle\wrapper\gradle-wrapper.properties'
    $wrapperText = Get-Content -LiteralPath $wrapperProperties -Raw
    if ($wrapperText -notmatch 'gradle-8\.11\.1-bin\.zip') { throw 'Unexpected Gradle distribution; verify its version and official checksum first.' }
    $wrapperText = $wrapperText -replace '(?m)^distributionSha256Sum=.*\r?\n?', ''
    ($wrapperText.TrimEnd() + "`ndistributionSha256Sum=f397b287023acdba1e9f6fc5ea72d22dd63669d59ed4a289a29b1a76eee151c6`n") |
        Set-Content -LiteralPath $wrapperProperties -Encoding utf8
    # AGP supports an explicit local CMake installation. Reuse Creator's 3.24.3
    # and the existing Ninja instead of downloading a second SDK CMake.
    $appGradleText = Get-Content -LiteralPath $androidAppGradle -Raw
    if ($appGradleText -notmatch 'version "3\.(22\.1|24\.3)"') { throw 'Unexpected Android CMake version; inspect the project before changing it.' }
    $appGradleText = $appGradleText.Replace('version "3.22.1"', 'version "3.24.3"')
    if ($appGradleText -notmatch 'ANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES') {
        $appGradleText = $appGradleText.Replace('"-DANDROID_ARM_NEON=TRUE"', '"-DANDROID_ARM_NEON=TRUE", "-DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON"')
    }
    $appGradleText | Set-Content -LiteralPath $androidAppGradle -Encoding utf8
    $localProperties = Join-Path $androidProject 'local.properties'
    $localText = if (Test-Path -LiteralPath $localProperties) { Get-Content -LiteralPath $localProperties -Raw } else { '' }
    $localText = $localText -replace '(?m)^cmake\.dir=.*\r?\n?', ''
    ($localText.TrimEnd() + "`ncmake.dir=" + $cmakeRoot.Replace('\', '/') + "`n") | Set-Content -LiteralPath $localProperties -Encoding utf8
    $gradleHome = Join-Path $workspace '.tools\gradle'
    $gradleArguments = @(('-Dgradle.user.home="' + $gradleHome + '"'), '-classpath', ('"' + $wrapperJar + '"'),
        'org.gradle.wrapper.GradleWrapperMain', '--no-daemon', '--console=plain', '--max-workers=8',
        '-Pandroid.builder.sdkDownload=false', '-PPROP_BUILD_TOOLS_VERSION=35.0.0', 'assembleDebug')
    # AGP's incremental ZIP writer can retain a superseded uncompressed .so as
    # unused bytes. Recreate only this generated APK to keep the output compact.
    $previousApk = Join-Path $androidProject 'build\hczs-cocos-poc\outputs\apk\debug\hczs-cocos-poc-debug.apk'
    if (Test-Path -LiteralPath $previousApk -PathType Leaf) { Remove-Item -LiteralPath $previousApk }
    $gradleProcess = Start-Process -FilePath $java -ArgumentList $gradleArguments -WorkingDirectory $androidProject -WindowStyle Hidden -PassThru `
        -Environment @{ 'JAVA_HOME' = $android.javaHome; 'GRADLE_USER_HOME' = $gradleHome; 'PATH' = "$ninjaRoot;$env:PATH"; 'CMAKE_BUILD_PARALLEL_LEVEL' = '8' } `
        -RedirectStandardOutput (Join-Path $evidence 'compile-android.stdout.log') `
        -RedirectStandardError (Join-Path $evidence 'compile-android.stderr.log')
    $null = $gradleProcess.Handle
    $gradleProcess.WaitForExit()
    $gradleProcess.ExitCode | Set-Content -LiteralPath (Join-Path $evidence 'compile-android.exit-code.txt')
    if ($gradleProcess.ExitCode -ne 0) { throw "Gradle returned $($gradleProcess.ExitCode); see $evidence\compile-android.*.log" }
    $apks = @(Get-ChildItem -LiteralPath $androidProject -Filter '*-debug.apk' -File -Recurse)
    if ($apks.Count -ne 1) { throw "Expected exactly one debug APK, found $($apks.Count). Inspect Android output." }
    Get-FileHash -LiteralPath $apks[0].FullName -Algorithm SHA256 | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'apk-sha256.json')
    Write-Output "Android APK compiled: $($apks[0].FullName)"
    return
}

if ($Action -eq 'build-web') {
    Invoke-CreatorBuild 'build-web.json' 'build' 'build-web'
    $index = Join-Path $project 'build\web-desktop\index.html'
    if (-not (Test-Path -LiteralPath $index)) {
        throw 'Creator reported success but the expected index.html is absent.'
    }
    Write-Output "Creator build succeeded (exit code 36): $index"
    return
}
if ($Action -in @('build-windows', 'generate-windows')) {
    Invoke-CreatorBuild $windowsConfig 'build' 'generate-windows'
    Write-Output 'Windows assets and native project exported; compilation is a separate step.'
}
if ($Action -eq 'generate-windows') { return }
if ($Action -in @('build-windows', 'compile-windows')) {
    $cmake = Join-Path (Split-Path -Parent $creator) 'resources\tools\cmake\bin\cmake.exe'
    $nativeSource = Join-Path $project 'native\engine\win64'
    $nativeOutput = Join-Path $project $windowsOutput
    if (-not (Test-Path -LiteralPath (Join-Path $nativeOutput 'proj\cfg.cmake'))) {
        throw 'The Windows export is missing. Run generate-windows or build-windows first.'
    }
    # Reconfigure explicitly so a new project-local native option is picked up
    # even when the previous CMake generation did not know about localCfg.cmake.
    $configureArguments = @('-S', ('"' + $nativeSource + '"'), '-B', ('"' + (Join-Path $nativeOutput 'proj') + '"'),
        ('-DRES_DIR="' + $nativeOutput.Replace('\', '/') + '"'), '-DAPP_NAME=hczs-cocos-poc', '-DLAUNCH_TYPE=Debug')
    $configure = Start-Process -FilePath $cmake -ArgumentList $configureArguments -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $evidence 'configure-windows.stdout.log') `
        -RedirectStandardError (Join-Path $evidence 'configure-windows.stderr.log')
    $null = $configure.Handle
    $configure.WaitForExit()
    $configure.ExitCode | Set-Content -LiteralPath (Join-Path $evidence 'configure-windows.exit-code.txt')
    if ($configure.ExitCode -ne 0) {
        throw "CMake configuration failed ($($configure.ExitCode)); see $evidence\configure-windows.*.log"
    }
    Invoke-CreatorBuild $windowsConfig 'make' 'compile-windows'
}
$executables = @(Get-ChildItem -LiteralPath (Join-Path $project $windowsOutput) -Recurse -Filter 'hczs-cocos-poc.exe' -File)
if ($executables.Count -ne 1) {
    throw "Expected exactly one hczs-cocos-poc.exe, found $($executables.Count). Inspect native build logs."
}
$executable = $executables[0].FullName
if ($Action -eq 'run-windows') {
    # This action opens the interactive game. Build/editor helper processes above
    # stay hidden; hiding this window prevents normal visual/input verification.
    $running = Start-Process -FilePath $executable -WorkingDirectory (Split-Path -Parent $executable) -WindowStyle Normal -PassThru `
        -RedirectStandardOutput (Join-Path $evidence 'run-windows.stdout.log') `
        -RedirectStandardError (Join-Path $evidence 'run-windows.stderr.log')
    $running.Id | Set-Content -LiteralPath (Join-Path $evidence 'run-windows.pid')
    Write-Output "Native executable started (PID $($running.Id)): $executable"
    return
}
Get-FileHash -LiteralPath $executable -Algorithm SHA256 | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'executable-sha256.json')
Write-Output "Windows native executable compiled: $executable"
