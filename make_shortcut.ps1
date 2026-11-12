$ErrorActionPreference = 'Stop'

$proj = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = Join-Path $desktop 'SofaSay.lnk'

$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut($lnk)
$sc.TargetPath = Join-Path $proj '.venv\Scripts\pythonw.exe'
$sc.Arguments = '"' + (Join-Path $proj 'control_panel.py') + '"'
$sc.WorkingDirectory = $proj
$sc.WindowStyle = 1
$sc.Description = 'Start and stop SofaSay'

$icon = Join-Path $proj 'assets\sofa.ico'
$wow = 'C:\Program Files (x86)\World of Warcraft\_forever_\Wow.exe'
if (Test-Path $icon) {
    $sc.IconLocation = "$icon,0"
} elseif (Test-Path $wow) {
    $sc.IconLocation = "$wow,0"
} else {
    $sc.IconLocation = "$($sc.TargetPath),0"
}
$sc.Save()

Write-Host "Desktop shortcut created: $lnk"
