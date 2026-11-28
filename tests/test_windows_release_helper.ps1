$ErrorActionPreference = 'Stop'
$script = Join-Path (Split-Path -Parent $PSScriptRoot) 'install.ps1'
function Invoke-WebRequest {
    param($Uri, $OutFile, [switch]$UseBasicParsing, $TimeoutSec)
    if ($Uri -notlike '*/releases/latest/download/cli-install-windows.ps1') {
        throw "Unexpected download: $Uri"
    }
    Set-Content -LiteralPath $OutFile -Value @'
param([switch]$Prepare)
$cliVersion = '0.4.3'
Write-Host "Helper invoked with Prepare=$Prepare"
'@
}
& $script -Component cli
Write-Host 'Latest release helper version was parsed and invoked.'
