param(
    [switch]$Clean,
    [string]$RuntimeVenv = "venv_build"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "$RuntimeVenv\Scripts\python.exe"
$PortableRoot = Join-Path $Root "dist_portable"
$AppDir = Join-Path $PortableRoot "Image Inspector"

if (!(Test-Path $Python)) {
    throw "Runtime nao encontrado: $Python. Crie a venv_build e instale packaging\requirements-client.txt antes."
}

if ($Clean) {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $PortableRoot
}

New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
Copy-Item -Recurse -Force (Join-Path $Root "image_inspector") $AppDir
Copy-Item -Force (Join-Path $Root "README.md") $AppDir
Copy-Item -Recurse -Force (Join-Path $Root $RuntimeVenv) (Join-Path $AppDir "runtime")

foreach ($dir in @(
    "models\inspection",
    "models\detection",
    "models\classification",
    "profiles",
    "data\inspections",
    "logs"
)) {
    New-Item -ItemType Directory -Force -Path (Join-Path $AppDir $dir) | Out-Null
}

$cmd = @"
@echo off
setlocal
set APP_DIR=%~dp0
set YOLO_CONFIG_DIR=%APP_DIR%.ultralytics
if not exist "%YOLO_CONFIG_DIR%" mkdir "%YOLO_CONFIG_DIR%"
"%APP_DIR%runtime\Scripts\pythonw.exe" -m image_inspector.app
endlocal
"@
Set-Content -LiteralPath (Join-Path $AppDir "Image Inspector.cmd") -Value $cmd -Encoding ASCII

$vbs = @"
Set shell = CreateObject(""WScript.Shell"")
Set fso = CreateObject(""Scripting.FileSystemObject"")
appDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = appDir
shell.Run Chr(34) & appDir & ""\Image Inspector.cmd"" & Chr(34), 0, False
"@
Set-Content -LiteralPath (Join-Path $AppDir "Image Inspector.vbs") -Value $vbs -Encoding ASCII

$install = @"
param(
    [string]`$InstallDir = "`$env:ProgramFiles\Image Inspector",
    [switch]`$NoDesktopShortcut
)

`$ErrorActionPreference = "Stop"
`$SourceApp = `$PSScriptRoot
New-Item -ItemType Directory -Force -Path `$InstallDir | Out-Null
Copy-Item -Recurse -Force (Join-Path `$SourceApp "*") `$InstallDir

`$Shell = New-Object -ComObject WScript.Shell
`$Target = Join-Path `$InstallDir "Image Inspector.vbs"
`$StartMenuDir = Join-Path `$env:ProgramData "Microsoft\Windows\Start Menu\Programs\Image Inspector"
New-Item -ItemType Directory -Force -Path `$StartMenuDir | Out-Null
`$StartShortcut = Join-Path `$StartMenuDir "Image Inspector.lnk"
`$Shortcut = `$Shell.CreateShortcut(`$StartShortcut)
`$Shortcut.TargetPath = "wscript.exe"
`$Shortcut.Arguments = Chr(34) + `$Target + Chr(34)
`$Shortcut.WorkingDirectory = `$InstallDir
`$Shortcut.Description = "Image Inspector"
`$Shortcut.Save()

if (!`$NoDesktopShortcut) {
    `$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "Image Inspector.lnk"
    `$Shortcut = `$Shell.CreateShortcut(`$DesktopShortcut)
    `$Shortcut.TargetPath = "wscript.exe"
    `$Shortcut.Arguments = Chr(34) + `$Target + Chr(34)
    `$Shortcut.WorkingDirectory = `$InstallDir
    `$Shortcut.Description = "Image Inspector"
    `$Shortcut.Save()
}

Write-Host "Instalacao portatil concluida em: `$InstallDir" -ForegroundColor Green
"@
Set-Content -LiteralPath (Join-Path $AppDir "install_portable_client.ps1") -Value $install -Encoding UTF8

Write-Host "Pacote portatil criado em:" -ForegroundColor Green
Write-Host "  $AppDir"
Write-Host ""
Write-Host "Teste local:"
Write-Host "  & '$AppDir\Image Inspector.cmd'"
Write-Host ""
Write-Host "No cliente, execute como Administrador dentro da pasta Image Inspector:"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\install_portable_client.ps1"
