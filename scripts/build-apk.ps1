# Builds the debug-signed APK and publishes it to the website's download link.
# Set the backend address in web\.env.production first.
$ErrorActionPreference = "Stop"
$web = Join-Path $PSScriptRoot "..\web"
$env:JAVA_HOME = "C:\dev\jdk21"
$env:ANDROID_HOME = "C:\dev\android-sdk"
if (-not (Test-Path "$env:JAVA_HOME\bin\java.exe")) { throw "Run scripts\setup-android-toolchain.ps1 first." }
if (-not (Test-Path "$web\.env.production")) { Write-Warning "web\.env.production is missing; the APK will have no default server address." }

Push-Location $web
try {
    npm run cap:sync
    if ($LASTEXITCODE -ne 0) { throw "Web build failed" }
    Push-Location android
    .\gradlew.bat assembleDebug
    if ($LASTEXITCODE -ne 0) { throw "Gradle build failed" }
    Pop-Location
    New-Item -ItemType Directory -Force "public\downloads", "dist\downloads" | Out-Null
    Copy-Item "android\app\build\outputs\apk\debug\app-debug.apk" "public\downloads\grocery-price-finder.apk"
    Copy-Item "android\app\build\outputs\apk\debug\app-debug.apk" "dist\downloads\grocery-price-finder.apk"
    Write-Host "APK ready: web\public\downloads\grocery-price-finder.apk"
} finally {
    Pop-Location
}
