param(
    [string]$InstallDir = "$env:ProgramFiles\Image Inspector",
    [switch]$NoDesktopShortcut
)

$ErrorActionPreference = "Stop"
$SourceRoot = $PSScriptRoot
$SourceApp = Join-Path $SourceRoot "Image Inspector"
$ExeName = "Image Inspector.exe"
$TargetExe = Join-Path $InstallDir $ExeName

if (!(Test-Path $SourceApp)) {
    throw "Pasta do aplicativo nao encontrada: $SourceApp. Execute este script a partir da pasta dist gerada pelo build."
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Recurse -Force (Join-Path $SourceApp "*") $InstallDir

$Shell = New-Object -ComObject WScript.Shell
$StartMenuDir = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\Image Inspector"
New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null
$StartShortcut = Join-Path $StartMenuDir "Image Inspector.lnk"
$Shortcut = $Shell.CreateShortcut($StartShortcut)
$Shortcut.TargetPath = $TargetExe
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Description = "Image Inspector"
$Shortcut.Save()

if (!$NoDesktopShortcut) {
    $DesktopShortcut = Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "Image Inspector.lnk"
    $Shortcut = $Shell.CreateShortcut($DesktopShortcut)
    $Shortcut.TargetPath = $TargetExe
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.Description = "Image Inspector"
    $Shortcut.Save()
}

Write-Host "Instalacao concluida em: $InstallDir" -ForegroundColor Green
Write-Host "Atalho criado no Menu Iniciar e na Area de Trabalho."
