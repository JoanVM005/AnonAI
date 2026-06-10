$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = Resolve-Path (Join-Path $ScriptDir "..")
$ProjectDir = Resolve-Path (Join-Path $AppDir "..")
$BuildEnv = Join-Path $AppDir ".build_env"
$ModelPath = Join-Path $ProjectDir "Model\runs\radiograph_phi_detection\augmented\weights\best.pt"
$SpecPath = Join-Path $ScriptDir "anonrad_ai.spec"
$InnoScript = Join-Path $ScriptDir "installer_windows_inno.iss"

if (-not (Test-Path $ModelPath)) {
  throw "Missing YOLO model: $ModelPath"
}

Set-Location $AppDir

py -3 -m venv $BuildEnv
& "$BuildEnv\Scripts\python.exe" -m pip install --upgrade pip
& "$BuildEnv\Scripts\python.exe" -m pip install -r requirements.txt -r packaging\requirements-build.txt

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& "$BuildEnv\Scripts\pyinstaller.exe" --noconfirm $SpecPath

$Iscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
if ($Iscc) {
  & $Iscc.Source $InnoScript
  Write-Host "Created installer in: packaging\Output"
} else {
  Write-Host "PyInstaller bundle created in: dist\AnonRad AI"
  Write-Host "Install Inno Setup and rerun this script to create a Windows installer."
}
