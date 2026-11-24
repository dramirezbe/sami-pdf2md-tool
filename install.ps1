#Requires -Version 5.1
# SAMI_UPGRADE_V1
[CmdletBinding()]
param(
    [string] $Source,
    [string] $UpgradePython,
    [string] $UpgradeIndex
)

$ErrorActionPreference = 'Stop'

if ($UpgradePython) {
    if (-not $Source) {
        throw 'Run sami upgrade from the installed CLI.'
    }
    $upgradeArgs = @('pip', 'install', '--python', $UpgradePython, '--upgrade-package', 'sami-pdf2md-tool')
    if ($UpgradeIndex) {
        $upgradeArgs += @('--index', $UpgradeIndex)
    }
    Write-Host 'Updating SAMI in its existing environment...'
    uv @upgradeArgs $Source
    if ($LASTEXITCODE -ne 0) {
        throw "SAMI upgrade failed (exit $LASTEXITCODE)."
    }
    & $UpgradePython -I -m sami.cli setup --register-only
    if ($LASTEXITCODE -ne 0) {
        throw "SAMI launcher registration failed (exit $LASTEXITCODE)."
    }
    Write-Host 'SAMI upgraded.'
    return
}

function Test-NvidiaCuda {
    if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
        return $false
    }
    try {
        $summary = nvidia-smi 2>$null | Out-String
    } catch {
        return $false
    }
    if ($LASTEXITCODE -ne 0) {
        return $false
    }
    $reported = [regex]::Match($summary, 'CUDA(?: UMD)? Version:\s*(\d+\.\d+)')
    return $reported.Success -and ([version]$reported.Groups[1].Value -ge [version]'13.2')
}

try {
    $samiArch = [string][System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
} catch {
    $samiArch = ''
}
if (-not $samiArch) {
    $samiArch = $env:PROCESSOR_ARCHITEW6432
    if (-not $samiArch) {
        $samiArch = $env:PROCESSOR_ARCHITECTURE
    }
}
if ($samiArch -eq 'AMD64') {
    $samiArch = 'X64'
}
if ($samiArch -notin @('X64', 'Arm64')) {
    if (-not $samiArch) { $samiArch = 'unknown' }
    throw "Unsupported architecture: $samiArch. SAMI supports x64 and ARM64 on Windows."
}

if (-not $Source) {
    $Source = 'https://github.com/dramirezbe/sami-pdf2md-tool/archive/refs/heads/main.zip'
    if ($MyInvocation.MyCommand.Path -and $PSScriptRoot) {
        if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'pyproject.toml')) {
            $Source = $PSScriptRoot
        }
    }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host 'Installing uv...'
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if ($LASTEXITCODE -ne 0) {
        throw "uv installation failed (exit $LASTEXITCODE)."
    }
    $env:PATH = "$(Join-Path $env:USERPROFILE '.local\bin');$env:PATH"
    $null = Get-Command uv -ErrorAction Stop
}

$installArgs = @('tool', 'install', '--force', '--python', '3.12')
if ($samiArch -eq 'X64' -and (Test-NvidiaCuda)) {
    # Pin the matching Windows wheels. Use the direct PyTorch host for the
    # large torch wheel and verify it against the hash in the CUDA 13.2 index.
    $torchUrl = 'https://download.pytorch.org/whl/cu132/torch-2.14.1%2Bcu132-cp312-cp312-win_amd64.whl'
    $torchSha256 = '882a670a7e2a17f2eb351406dc4a235455fd9256ac737752de5f1279e2a1df8c'
    $installArgs += @(
        '--index', 'https://download.pytorch.org/whl/cu132',
        '--with', "torch @ ${torchUrl}#sha256=$torchSha256",
        '--with', 'torchvision==0.29.1+cu132'
    )
    Write-Host 'Installing SAMI with PyTorch CUDA 13.2...'
} else {
    Write-Host 'Installing SAMI with the default PyTorch dependencies...'
}

uv @installArgs $Source
if ($LASTEXITCODE -ne 0) {
    throw "SAMI installation failed (exit $LASTEXITCODE)."
}

$binDir = uv tool dir --bin
if ($LASTEXITCODE -ne 0 -or -not $binDir) {
    throw 'Could not locate the uv tool executable directory.'
}
uv tool update-shell
if ($LASTEXITCODE -ne 0) {
    throw "Could not update PATH for uv tools (exit $LASTEXITCODE)."
}
if (($env:PATH -split ';') -notcontains $binDir) {
    $env:PATH = "$binDir;$env:PATH"
}

$samiLauncher = Join-Path $binDir 'sami.exe'
& $samiLauncher setup --register-only --executable $samiLauncher
if ($LASTEXITCODE -ne 0) {
    throw "SAMI launcher registration failed (exit $LASTEXITCODE)."
}

Write-Host 'SAMI installed. Run sami setup to prepare and verify all modes.'
