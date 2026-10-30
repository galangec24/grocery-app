# Publishes an app update. GitHub then builds, signs and releases the APK.
#   .\scripts\release.ps1 1.1.0 "Added price alerts`nFaster search"
# The notes become the "What's new" text inside the app.
param(
    [Parameter(Mandatory)][ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version,
    [Parameter(Mandatory)][string]$Notes
)
$ErrorActionPreference = "Stop"
$tag = "v$Version"
if (git tag -l $tag) { throw "$tag already exists." }
if (git status --porcelain) { throw "Commit your changes before releasing." }
git tag -a $tag -m $Notes
git push origin $tag
Write-Host "Release started: https://github.com/galangec24/grocery-app/actions"
