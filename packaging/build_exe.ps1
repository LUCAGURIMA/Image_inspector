param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$BuildVenvPython = Join-Path $Root "venv_build\Scripts\python.exe"
$DefaultVenvPython = Join-Path $Root "venv\Scripts\python.exe"
$Python = if (Test-Path $BuildVenvPython) { $BuildVenvPython } else { $DefaultVenvPython }
$Spec = Join-Path $PSScriptRoot "image_inspector.spec"
$DistApp = Join-Path $Root "dist\Image Inspector"
$env:YOLO_CONFIG_DIR = Join-Path $Root ".ultralytics"
New-Item -ItemType Directory -Force -Path $env:YOLO_CONFIG_DIR | Out-Null

if (!(Test-Path $Python)) {
    throw "Python da venv nao encontrado: $Python"
}

if ($Clean) {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $Root "build")
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $Root "dist")
}

Push-Location $Root
try {
    & $Python -m compileall image_inspector
    & $Python -m PyInstaller --clean --noconfirm $Spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller falhou com codigo $LASTEXITCODE"
    }

    New-Item -ItemType Directory -Force -Path (Join-Path $DistApp "models\inspection") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $DistApp "models\detection") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $DistApp "models\classification") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $DistApp "profiles") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $DistApp "data\inspections") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $DistApp "logs") | Out-Null

    Copy-Item -Force (Join-Path $Root "packaging\install_client.ps1") (Join-Path $Root "dist\install_client.ps1")
    Copy-Item -Force (Join-Path $Root "README.md") (Join-Path $Root "dist\README.md")

    Write-Host ""
    Write-Host "Build concluido:" -ForegroundColor Green
    Write-Host "  $DistApp"
    Write-Host ""
    Write-Host "Para instalar no cliente, copie a pasta dist e execute como Administrador:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File .\install_client.ps1"
}
finally {
    Pop-Location
}

