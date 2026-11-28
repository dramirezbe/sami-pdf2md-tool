$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$oldLocalAppData = $env:LOCALAPPDATA
$tempDir = Join-Path ([IO.Path]::GetTempPath()) ("sami-installer-test-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempDir | Out-Null
try {
    $env:LOCALAPPDATA = $tempDir
    $helper = Join-Path $tempDir 'failing-helper.ps1'
    Set-Content -LiteralPath $helper -Value 'param([switch]$Prepare); Write-Host "detail before failure"; throw "test installer failure"'
    $wrapper = Join-Path $root 'packaging\windows\install-logged.ps1'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wrapper -Helper $helper
    if ($LASTEXITCODE -eq 0) { throw 'Expected the wrapper to report the failure.' }
    $log = Get-Content -Raw -LiteralPath (Join-Path $tempDir 'SAMI\installer.log')
    if ($log -notmatch 'detail before failure' -or $log -notmatch 'test installer failure') {
        throw 'The installer log did not capture the failure.'
    }
    Write-Host 'Windows installer failure is reported and logged.'
    # The native helper failed as expected; do not leak its exit code into CI.
    $global:LASTEXITCODE = 0
} finally {
    $env:LOCALAPPDATA = $oldLocalAppData
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
