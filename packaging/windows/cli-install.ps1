[CmdletBinding()]
param([switch] $Prepare,[switch] $Quiet,[switch] $CheckOnly)
$ErrorActionPreference = 'Stop'
$cliVersion = '0.2.4'
$protocolVersion = 1
$wheelName = 'sami_pdf2md_tool-0.2.4-py3-none-any.whl'
$wheelUrl = "https://github.com/dramirezbe/sami-pdf2md-tool/releases/download/v$cliVersion/$wheelName"
$wheelSha256 = 'fe5d91d7aa2d9c21d191e8a7822851dd8658cae65fdbbda91ec25e7f1e123fe3'
$samiHome = if ($env:SAMI_HOME) { $env:SAMI_HOME } else { Join-Path $env:USERPROFILE '.sami' }
$recordPath = Join-Path $samiHome 'installation.json'
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
$uv = if ($uvCommand) { $uvCommand.Source } else { $null }

function Write-Step([string] $Message) {
    if (-not $Quiet) { Write-Host "[SAMI] $Message" }
}
function Get-Registration {
    if (Test-Path -LiteralPath $recordPath) {
        try { return Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json } catch { return $null }
    }
    return $null
}
function Get-Health([string] $Executable) {
    try {
        $lines = & $Executable health --json 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        return ($lines -join [Environment]::NewLine) | ConvertFrom-Json
    } catch { return $null }
}
function Test-Ready($Health) {
    if (-not $Health -or $Health.cli_version -ne $cliVersion -or $Health.protocol_version -ne $protocolVersion) { return $false }
    foreach ($mode in @('fast', 'balanced', 'quality')) {
        if (-not $Health.modes.$mode.available -or -not $Health.modes.$mode.ready) { return $false }
    }
    return $true
}
$registration = Get-Registration
$launcher = if ($registration -and $registration.executable) { [string]$registration.executable } else { $null }
$python = if ($registration -and $registration.python_executable) { [string]$registration.python_executable } else { $null }
$health = if ($launcher -and (Test-Path -LiteralPath $launcher)) { Get-Health $launcher } else { $null }

if ($health -and $health.cli_version -eq $cliVersion -and $health.protocol_version -eq $protocolVersion) {
    if ($CheckOnly -and -not (Test-Ready $health)) {
        throw 'The installed SAMI CLI is not ready. Run sami setup, then retry the UI installation.'
    }
    if (-not (Test-Ready $health) -and $Prepare) {
        Write-Step 'Validating local engines and preparing missing models...'
        & $launcher setup --json
        if ($LASTEXITCODE -ne 0) { throw "SAMI setup failed with exit code $LASTEXITCODE." }
        $health = Get-Health $launcher
    }
    if (Test-Ready $health) {
        Write-Step "SAMI CLI $cliVersion is ready."
        return
    }
}

if ($CheckOnly) {
    throw "SAMI CLI $cliVersion is required and must be healthy for UI-only installation. Install or repair the CLI, then retry."
}

Write-Step "Installing SAMI CLI $cliVersion..."
if (-not $uv) {
    Write-Step 'Installing the Python tool manager...'
    $installer = Invoke-RestMethod -Uri 'https://astral.sh/uv/install.ps1' -TimeoutSec 60
    & ([scriptblock]::Create($installer))
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    $uv = if ($uvCommand) { $uvCommand.Source } else { $null }
    if (-not $uv) {
        $candidate = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
        if (Test-Path -LiteralPath $candidate) { $uv = $candidate }
    }
    if (-not $uv) { throw 'Could not install uv.' }
}

$tempDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("sami-cli-" + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $tempDirectory
$wheel = Join-Path $tempDirectory $wheelName
try {
    Write-Step 'Downloading the verified SAMI CLI package...'
    Invoke-WebRequest -Uri $wheelUrl -OutFile $wheel -TimeoutSec 120
    $actualHash = (Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $wheelSha256) { throw 'The SAMI CLI package checksum does not match the release manifest.' }

    if ($python -and (Test-Path -LiteralPath $python)) {
        Write-Step 'Updating the registered Python environment...'
        & $uv pip install --python $python --upgrade $wheel
        if ($LASTEXITCODE -ne 0) { throw "SAMI CLI package installation failed with exit code $LASTEXITCODE." }
    } else {
        $toolDirectory = & $uv tool dir
        if ($LASTEXITCODE -ne 0) { throw 'Could not locate the uv tool environment.' }
        $python = Join-Path $toolDirectory 'sami-pdf2md-tool\Scripts\python.exe'
        $installArguments = @('tool', 'install', '--python', '3.12', '--force')
        $cuda = $false
        if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
            $cudaSummary = nvidia-smi 2>$null | Out-String
            $cudaVersion = [regex]::Match($cudaSummary, 'CUDA(?: UMD)? Version:\s*(\d+\.\d+)')
            $cuda = $LASTEXITCODE -eq 0 -and $cudaVersion.Success -and ([version]$cudaVersion.Groups[1].Value -ge [version]'13.2')
        }
        if ($cuda -and [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -eq 'X64') {
            $torchUrl = 'https://download.pytorch.org/whl/cu132/torch-2.14.1%2Bcu132-cp312-cp312-win_amd64.whl'
            $torchSha256 = '882a670a7e2a17f2eb351406dc4a235455fd9256ac737752de5f1279e2a1df8c'
            $installArguments += @(
                '--index', 'https://download.pytorch.org/whl/cu132',
                '--with', ('torch @ {0}#sha256={1}' -f $torchUrl, $torchSha256),
                '--with', 'torchvision==0.29.1+cu132'
            )
        }
        & $uv @installArguments $wheel
        if ($LASTEXITCODE -ne 0) { throw "SAMI CLI installation failed with exit code $LASTEXITCODE." }
        $binDirectory = & $uv tool dir --bin
        $launcher = Join-Path $binDirectory 'sami.exe'
        & $uv tool update-shell
        if ($LASTEXITCODE -ne 0) { throw "Could not update the CLI PATH (exit $LASTEXITCODE)." }
        if (($env:PATH -split ';') -notcontains $binDirectory) { $env:PATH = "$binDirectory;$env:PATH" }
    }

    if (-not $launcher) {
        $binDirectory = & $uv tool dir --bin
        $launcher = Join-Path $binDirectory 'sami.exe'
    }
    if (-not (Test-Path -LiteralPath $launcher)) { throw 'The installed SAMI CLI launcher could not be found.' }
    if ($python -and (Test-Path -LiteralPath $python)) {
        & $python -I -m sami.cli setup --register-only --executable $launcher
        if ($LASTEXITCODE -ne 0) { throw "SAMI launcher registration failed with exit code $LASTEXITCODE." }
    }
    if ($Prepare) {
        Write-Step 'Preparing models and validating the CPU modes...'
        & $launcher setup --json
        if ($LASTEXITCODE -ne 0) { throw "SAMI setup failed with exit code $LASTEXITCODE." }
    }
    $health = Get-Health $launcher
    if (-not (Test-Ready $health)) { throw 'SAMI CLI failed its final readiness check. Run sami doctor for diagnostics.' }
    Write-Step "SAMI CLI $cliVersion is ready."
} finally {
    Remove-Item -LiteralPath $tempDirectory -Recurse -Force -ErrorAction SilentlyContinue
}
