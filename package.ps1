# Builds the shareable ZIP in dist\.
#   powershell -ExecutionPolicy Bypass -File package.ps1
param([string]$Version = '1.0.0')

$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$name = "WoWVoiceChat-$Version"
$dist = Join-Path $root 'dist'
$stage = Join-Path $dist $name
$zip = Join-Path $dist "$name.zip"

if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
if (Test-Path $zip) { Remove-Item $zip -Force }
New-Item -ItemType Directory -Path $stage -Force | Out-Null

$files = @(
    'main.py',
    'control_panel.py',
    'selftest.py',
    'setup.bat',
    'run.bat',
    'panel.bat',
    'make_shortcut.ps1',
    'requirements.txt',
    'README.md',
    'LICENSE'
)

foreach ($file in $files) {
    $source = Join-Path $root $file
    if (-not (Test-Path $source)) { throw "Missing required file: $file" }
    Copy-Item $source (Join-Path $stage $file)
}

foreach ($folder in @('wowvoice', 'addon')) {
    $source = Join-Path $root $folder
    if (-not (Test-Path $source)) { throw "Missing required folder: $folder" }
    $target = Join-Path $stage $folder
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    Get-ChildItem $source -Recurse -File |
        Where-Object { $_.FullName -notmatch '__pycache__' -and $_.Extension -ne '.pyc' } |
        ForEach-Object {
            $relative = $_.FullName.Substring($source.Length).TrimStart('\')
            $destination = Join-Path $target $relative
            $parent = Split-Path $destination -Parent
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
            Copy-Item $_.FullName $destination
        }
}

# Personal settings and caches must never ship.
foreach ($forbidden in @('config.json', '.venv', 'wow-voicechat.log', 'wow-voicechat.pid')) {
    if (Test-Path (Join-Path $stage $forbidden)) {
        throw "Refusing to package personal data: $forbidden"
    }
}

Compress-Archive -Path $stage -DestinationPath $zip -CompressionLevel Optimal
Remove-Item $stage -Recurse -Force

$size = [math]::Round((Get-Item $zip).Length / 1KB, 1)
Write-Host "Built $zip ($size KB)"
Write-Host 'Upload this ZIP as a GitHub release asset.'
