# Installs a portable JDK 21 and Android SDK into C:\dev (about 2.5 GB, more during builds).
# Nothing is added to your system PATH or environment variables.
$ErrorActionPreference = "Stop"
$root = "C:\dev"
New-Item -ItemType Directory -Force $root | Out-Null

if (-not (Test-Path "$root\jdk21\bin\java.exe")) {
    Write-Host "Downloading JDK 21..."
    Invoke-WebRequest "https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse" -OutFile "$root\jdk.zip"
    Expand-Archive "$root\jdk.zip" $root
    Remove-Item "$root\jdk.zip"
    Rename-Item (Get-ChildItem $root -Directory -Filter "jdk-21*").FullName "jdk21"
}

$sdk = "$root\android-sdk"
if (-not (Test-Path "$sdk\cmdline-tools\latest\bin\sdkmanager.bat")) {
    Write-Host "Downloading Android command-line tools..."
    $xml = (Invoke-WebRequest "https://dl.google.com/android/repository/repository2-3.xml" -UseBasicParsing).Content
    $file = [regex]::Matches($xml, "commandlinetools-win-\d+_latest\.zip") | ForEach-Object { $_.Value } | Sort-Object -Unique | Select-Object -Last 1
    Invoke-WebRequest "https://dl.google.com/android/repository/$file" -OutFile "$root\clt.zip"
    New-Item -ItemType Directory -Force "$sdk\cmdline-tools" | Out-Null
    Expand-Archive "$root\clt.zip" "$sdk\cmdline-tools"
    Remove-Item "$root\clt.zip"
    Rename-Item "$sdk\cmdline-tools\cmdline-tools" "latest"
}

$env:JAVA_HOME = "$root\jdk21"
$env:ANDROID_HOME = $sdk
Write-Host "Installing Android platform and build tools (accepts the SDK licenses)..."
"y`ny`ny`ny`ny`ny`ny`ny`ny`ny`n" | & "$sdk\cmdline-tools\latest\bin\sdkmanager.bat" --licenses | Out-Null
& "$sdk\cmdline-tools\latest\bin\sdkmanager.bat" "platform-tools" "platforms;android-36" "build-tools;36.0.0"
Write-Host "Done. Next run scripts\build-apk.ps1"
