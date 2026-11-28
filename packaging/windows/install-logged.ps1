[CmdletBinding()]
param([Parameter(Mandatory = $true)][string] $Helper)

$logDirectory = Join-Path $env:LOCALAPPDATA 'SAMI'
$logPath = Join-Path $logDirectory 'installer.log'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
Start-Transcript -Path $logPath -Force | Out-Null
try {
    Write-Host "Installer log: $logPath"
    & $Helper -Prepare
    Write-Host 'SAMI installation completed.'
} catch {
    Write-Host "SAMI installation failed: $_"
    exit 1
} finally {
    Stop-Transcript | Out-Null
}
