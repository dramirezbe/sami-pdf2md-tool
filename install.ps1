#Requires -Version 5.1
# SAMI_UPGRADE_V1
[CmdletBinding()]
param(
    [ValidateSet('all', 'cli', 'ui')]
    [string] $Component = 'all',
    [string] $Source,
    [string] $UpgradePython,
    [string] $UpgradeIndex
)

$ErrorActionPreference = 'Stop'
$repository = 'dramirezbe/sami-pdf2md-tool'
$uiVersion = '0.3.1'

function Get-SamiArchitecture {
    try { $architecture = [string][System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture }
    catch { $architecture = '' }
    if (-not $architecture) { $architecture = $env:PROCESSOR_ARCHITEW6432 }
    if (-not $architecture) { $architecture = $env:PROCESSOR_ARCHITECTURE }
    if ($architecture -eq 'AMD64') { return 'X64' }
    return $architecture
}

function Ensure-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) { return }
    Write-Host 'Installing uv...'
    $uvInstaller = Invoke-RestMethod -Uri 'https://astral.sh/uv/install.ps1' -TimeoutSec 60
    & ([scriptblock]::Create($uvInstaller))
    $env:PATH = "$(Join-Path $env:USERPROFILE '.local\bin');$env:PATH"
    $null = Get-Command uv -ErrorAction Stop
}

if ($UpgradePython) {
    if (-not $Source) {
        throw 'Run sami upgrade from the installed CLI.'
    }
    $upgradeArgs = @('pip', 'install', '--python', $UpgradePython, '--upgrade-package', 'sami-pdf2md-tool')
    if ($UpgradeIndex) { $upgradeArgs += @('--index', $UpgradeIndex) }
    Write-Host 'Updating SAMI in its existing environment...'
    uv @upgradeArgs $Source
    if ($LASTEXITCODE -ne 0) { throw "SAMI upgrade failed (exit $LASTEXITCODE)." }
    & $UpgradePython -I -m sami.cli setup --register-only
    if ($LASTEXITCODE -ne 0) { throw "SAMI launcher registration failed (exit $LASTEXITCODE)." }
    Write-Host 'SAMI upgraded.'
    return
}

$temporaryDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("sami-install-" + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $temporaryDirectory
try {
    if ($Source) {
        Ensure-Uv
        Write-Host 'Installing SAMI from the requested source...'
        $installArgs = @('tool', 'install', '--python', '3.12', '--force')
        $architecture = Get-SamiArchitecture
        $cuda = $false
        if ($architecture -eq 'X64' -and (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
            $summary = nvidia-smi 2>$null | Out-String
            $reported = [regex]::Match($summary, 'CUDA(?: UMD)? Version:\s*(\d+\.\d+)')
            $cuda = $LASTEXITCODE -eq 0 -and $reported.Success -and ([version]$reported.Groups[1].Value -ge [version]'13.2')
        }
        if ($cuda) {
            $torchUrl = 'https://download.pytorch.org/whl/cu132/torch-2.14.1%2Bcu132-cp312-cp312-win_amd64.whl'
            $torchSha256 = '882a670a7e2a17f2eb351406dc4a235455fd9256ac737752de5f1279e2a1df8c'
            $installArgs += @(
                '--index', 'https://download.pytorch.org/whl/cu132',
                '--with', "torch @ ${torchUrl}#sha256=$torchSha256",
                '--with', 'torchvision==0.29.1+cu132'
            )
            Write-Host 'Installing SAMI with PyTorch CUDA 13.2...'
        }
        & uv @installArgs $Source
        if ($LASTEXITCODE -ne 0) { throw "SAMI installation failed (exit $LASTEXITCODE)." }
        $binDirectory = (uv tool dir --bin).Trim()
        $launcher = Join-Path $binDirectory 'sami.exe'
        uv tool update-shell
        if ($LASTEXITCODE -ne 0) { throw "Could not update the CLI PATH (exit $LASTEXITCODE)." }
        if (($env:PATH -split ';') -notcontains $binDirectory) { $env:PATH = "$binDirectory;$env:PATH" }
        & $launcher setup --register-only --executable $launcher
        if ($LASTEXITCODE -ne 0) { throw "SAMI launcher registration failed (exit $LASTEXITCODE)." }
        return
    }

    $helper = $null
    if ($PSScriptRoot) {
        foreach ($relativePath in @('packaging\windows\cli-install.ps1', 'cli-install-windows.ps1')) {
            $candidate = Join-Path $PSScriptRoot $relativePath
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { $helper = $candidate; break }
        }
    }
    if (-not $helper) {
        $helper = Join-Path $temporaryDirectory 'cli-install.ps1'
        $helperUrl = "https://raw.githubusercontent.com/$repository/main/packaging/windows/cli-install.ps1"
        Write-Host 'Fetching the shared CLI installation steps...'
        Invoke-WebRequest -UseBasicParsing -Uri $helperUrl -OutFile $helper -TimeoutSec 60
    }

    if ($Component -in @('cli', 'all')) {
        & $helper -Prepare
        if ($LASTEXITCODE -ne 0) { throw "SAMI CLI installation failed (exit $LASTEXITCODE)." }
    }

    if ($Component -in @('ui', 'all')) {
        $architecture = Get-SamiArchitecture
        if ($architecture -ne 'X64') {
            if ($Component -eq 'all') {
                Write-Warning 'The SAMI CLI is ready. The SAMI desktop installer currently supports Windows x64 only.'
                return
            }
            throw 'The SAMI desktop installer currently supports Windows x64 only.'
        }
        if ($Component -eq 'ui') {
            & $helper -CheckOnly
            if ($LASTEXITCODE -ne 0) { throw 'UI-only installation requires a healthy, matching SAMI CLI.' }
        }
        $asset = "SAMI-$uiVersion-win-x64-setup.exe"
        $releaseUrl = "https://github.com/$repository/releases/download/v$uiVersion"
        $releaseApi = "https://api.github.com/repos/$repository/releases/tags/v$uiVersion"
        $installer = Join-Path $temporaryDirectory $asset
        $sumFile = Join-Path $temporaryDirectory 'SHA256SUMS'
        try {
            $null = Invoke-RestMethod -UseBasicParsing -Uri $releaseApi -TimeoutSec 20
        } catch {
            $statusCode = $null
            if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
                $statusCode = [int]$_.Exception.Response.StatusCode
            }
            if ($statusCode -eq 404) {
                $message = "The SAMI $uiVersion desktop release is not published yet."
                if ($Component -eq 'all') {
                    Write-Warning "SAMI CLI is ready. $message"
                    return
                }
                throw $message
            }
            throw
        }
        Write-Host 'Downloading the SAMI desktop app...'
        Invoke-WebRequest -UseBasicParsing -Uri "$releaseUrl/$asset" -OutFile $installer -TimeoutSec 300
        Invoke-WebRequest -UseBasicParsing -Uri "$releaseUrl/SHA256SUMS" -OutFile $sumFile -TimeoutSec 60
        $expected = Select-String -Path $sumFile -Pattern ("^([0-9a-fA-F]{64})\s+\*?" + [regex]::Escape($asset) + '$') |
            Select-Object -First 1
        if (-not $expected) { throw 'The desktop app checksum is missing from SHA256SUMS.' }
        $actual = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash
        if ($actual -ne $expected.Matches[0].Groups[1].Value) {
            throw 'The desktop app checksum does not match the release.'
        }
        Write-Host 'Starting the verified SAMI desktop installer...'
        $process = Start-Process -FilePath $installer -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "SAMI desktop installation failed (exit $($process.ExitCode))." }
    }
} finally {
    Remove-Item -LiteralPath $temporaryDirectory -Recurse -Force -ErrorAction SilentlyContinue
}
