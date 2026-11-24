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

$arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
if ($arch -notin @('X64', 'Arm64')) {
    throw "Unsupported architecture: $arch. SAMI supports x64 and ARM64 on Windows."
}

if (-not $Source) {
    if ($PSScriptRoot -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'pyproject.toml'))) {
        $Source = $PSScriptRoot
    } else {
        $Source = 'git+https://github.com/dramirezbe/sami-pdf2md-tool.git'
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
if ($arch -eq 'X64' -and (Test-NvidiaCuda)) {
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

Write-Host 'SAMI installed. Try: sami paper.pdf --mode balanced'
Write-Host 'SAMI downloads the llama.cpp runtime and OCR models when it needs them.'
