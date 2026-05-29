param(
  [string]$Version = "0.1.0",
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$AppName = "CodexStatusWidget"
$EntryPoint = Join-Path $ProjectRoot "src\codex_status_widget\__main__.py"
$DistDir = Join-Path $ProjectRoot "dist"
$BuildDir = Join-Path $ProjectRoot "build"
$ReleaseName = "$AppName-v$Version-win64"
$ReleaseDir = Join-Path $DistDir $ReleaseName
$ZipPath = Join-Path $DistDir "$ReleaseName.zip"
$ExePath = Join-Path $DistDir "$AppName.exe"

if (-not (Test-Path $EntryPoint)) {
  throw "Entry point not found: $EntryPoint"
}

Push-Location $ProjectRoot
try {
  & $Python -m py_compile `
    ".\src\codex_status_widget\__init__.py" `
    ".\src\codex_status_widget\__main__.py" `
    ".\src\codex_status_widget\core.py" `
    ".\src\codex_status_widget\app_qt.py"
  if ($LASTEXITCODE -ne 0) {
    throw "Python compile check failed."
  }

  & $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name $AppName `
    --paths ".\src" `
    ".\src\codex_status_widget\__main__.py"

  if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
  }

  if (-not (Test-Path $ExePath)) {
    throw "Executable was not created: $ExePath"
  }

  if (Test-Path $ReleaseDir) {
    Remove-Item -LiteralPath $ReleaseDir -Recurse -Force
  }
  New-Item -ItemType Directory -Path $ReleaseDir | Out-Null

  Copy-Item -LiteralPath $ExePath -Destination (Join-Path $ReleaseDir "$AppName.exe") -Force
  Copy-Item -LiteralPath ".\run-codex-status-widget.cmd" -Destination $ReleaseDir -Force
  Copy-Item -LiteralPath ".\run-codex-status-widget-hidden.vbs" -Destination $ReleaseDir -Force
  Copy-Item -LiteralPath ".\README.md" -Destination $ReleaseDir -Force
  Copy-Item -LiteralPath ".\LICENSE" -Destination $ReleaseDir -Force
  Copy-Item -LiteralPath ".\CHANGELOG.md" -Destination $ReleaseDir -Force
  Copy-Item -LiteralPath ".\RELEASE_NOTES.md" -Destination $ReleaseDir -Force

  if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
  }
  Compress-Archive -Path (Join-Path $ReleaseDir "*") -DestinationPath $ZipPath -Force

  Write-Host "Built release package:" $ZipPath
}
finally {
  Pop-Location
}
