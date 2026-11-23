#Requires -Version 5.1
<#
.SYNOPSIS
    Windows installer for sami CLI 0.2.0.

.DESCRIPTION
    Installs uv, sami, and llama-server.exe into %LOCALAPPDATA%\SAMI.
    Idempotent: safe to run multiple times. Does not require administrator privileges.

.NOTES
    See packaging/runtime-manifest.json for pinned dependency versions.
#>

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# 1. Architecture detection
# ---------------------------------------------------------------------------
$arch = $env:PROCESSOR_ARCHITECTURE
if ($arch -eq "AMD64") {
    $platform = "win-x64"
    $llamaSuffix = "-bin-win-llama-server-x64.zip"
} elseif ($arch -eq "ARM64") {
    $platform = "win-arm64"
    $llamaSuffix = "-bin-win-llama-server-arm64.zip"
} else {
    Write-Error "Unsupported architecture: $arch. sami supports x64 and arm64 on Windows."
    exit 1
}

Write-Host "Detected architecture: $arch ($platform)"

# ---------------------------------------------------------------------------
# 2. SAMI_HOME and directory structure
# ---------------------------------------------------------------------------
$SamiHome = "$env:LOCALAPPDATA\SAMI"
$env:SAMI_HOME = $SamiHome

$dirs = @(
    "$SamiHome\bin",
    "$SamiHome\cache\huggingface",
    "$SamiHome\config",
    "$SamiHome\logs"
)

foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "Created: $dir"
    }
}

# ---------------------------------------------------------------------------
# 3. Install uv (if not already on PATH)
# ---------------------------------------------------------------------------
$uvInstalled = $false
try {
    $null = Get-Command uv -ErrorAction Stop
    Write-Host "uv already installed: $(uv --version)"
    $uvInstalled = $true
} catch {
    Write-Host "uv not found. Installing..."
}

if (-not $uvInstalled) {
    try {
        $uvInstaller = "$env:TEMP\uv-install.ps1"
        Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -OutFile $uvInstaller -UseBasicParsing
        & $uvInstaller
        Remove-Item $uvInstaller -Force -ErrorAction SilentlyContinue

        # Add uv to current process PATH
        $uvBinDir = "$env:USERPROFILE\.local\bin"
        if (Test-Path $uvBinDir) {
            $env:PATH = "$uvBinDir;$env:PATH"
            Write-Host "Added $uvBinDir to current process PATH."
        }

        $null = Get-Command uv -ErrorAction Stop
        Write-Host "uv installed successfully: $(uv --version)"
    } catch {
        Write-Error "Failed to install uv: $_"
        exit 1
    }
}

# ---------------------------------------------------------------------------
# 4. Install sami via uv
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Installing sami..."
Write-Host "NOTE: This step installs marker-pdf==2.0.0 as a dependency."
Write-Host "      The 'sami' package reference below is a placeholder for sami 0.2.0."
Write-Host "      Once published to PyPI, this command will work as-is."
Write-Host "      Until then, run: uv tool install --python 3.12 -e <path-to-sami-clone>"
Write-Host ""

try {
    # Placeholder install command for when sami 0.2.0 is published to PyPI.
    # For development installs, use: uv tool install --python 3.12 -e .
    uv tool install --python 3.12 "marker-pdf==2.0.0" sami
    Write-Host "sami installed."
} catch {
    Write-Warning "sami package install step failed (expected if not yet published to PyPI)."
    Write-Warning "For development: cd into the repo and run: uv tool install --python 3.12 -e ."
}

# ---------------------------------------------------------------------------
# 5. Download llama-server.exe
# ---------------------------------------------------------------------------
$llamaBin = "$SamiHome\bin\llama-server.exe"

if (Test-Path $llamaBin) {
    Write-Host "llama-server.exe already present at $llamaBin — skipping download."
} else {
    Write-Host "Fetching latest llama.cpp release metadata..."
    try {
        $headers = @{ "User-Agent" = "sami-installer/0.2.0" }
        $releasesUrl = "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=1"
        $releases = Invoke-RestMethod -Uri $releasesUrl -Headers $headers -UseBasicParsing

        if ($releases.Count -eq 0) {
            throw "No releases returned from GitHub API."
        }

        $latestRelease = $releases[0]
        Write-Host "Latest release: $($latestRelease.tag_name)"

        $asset = $latestRelease.assets | Where-Object { $_.name -like "*$llamaSuffix" } | Select-Object -First 1

        if (-not $asset) {
            throw "No asset found matching suffix '$llamaSuffix' in release $($latestRelease.tag_name)."
        }

        $downloadUrl = $asset.browser_download_url
        $zipPath = "$env:TEMP\llama-server-$platform.zip"

        Write-Host "Downloading $($asset.name)..."
        Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath -UseBasicParsing

        # Extract llama-server.exe from the ZIP
        $extractDir = "$env:TEMP\llama-server-extract-$platform"
        if (Test-Path $extractDir) {
            Remove-Item $extractDir -Recurse -Force
        }
        Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

        # Find the binary inside the extracted archive
        $binaryPath = Get-ChildItem -Path $extractDir -Recurse -Filter "llama-server.exe" |
                      Select-Object -First 1 -ExpandProperty FullName

        if (-not $binaryPath) {
            throw "llama-server.exe not found inside the downloaded archive."
        }

        Copy-Item -Path $binaryPath -Destination $llamaBin -Force

        # Cleanup temp files
        Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
        Remove-Item $extractDir -Recurse -Force -ErrorAction SilentlyContinue

        Write-Host "llama-server.exe installed to: $llamaBin"
    } catch {
        Write-Warning "Failed to download llama-server.exe: $_"
        Write-Warning "You can manually download from: https://github.com/ggml-org/llama.cpp/releases"
        Write-Warning "Place llama-server.exe in: $SamiHome\bin\"
    }
}

# ---------------------------------------------------------------------------
# 6. Configure user PATH permanently
# ---------------------------------------------------------------------------
$samiBin = "$SamiHome\bin"
$currentUserPath = [Environment]::GetEnvironmentVariable("PATH", "User")

if ($currentUserPath -split ";" | Where-Object { $_ -eq $samiBin }) {
    Write-Host "$samiBin is already in the user PATH."
} else {
    $newPath = if ($currentUserPath) { "$currentUserPath;$samiBin" } else { $samiBin }
    [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    Write-Host "Added $samiBin to user PATH (permanent)."
    # Also update current process PATH
    $env:PATH = "$env:PATH;$samiBin"
}

# ---------------------------------------------------------------------------
# 7. Summary
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "============================================================"
Write-Host " sami installation complete"
Write-Host "============================================================"
Write-Host " SAMI_HOME : $SamiHome"
Write-Host " Platform  : $platform"
Write-Host ""
Write-Host " Directories created:"
foreach ($dir in $dirs) {
    Write-Host "   $dir"
}
Write-Host ""
Write-Host " llama-server.exe : $llamaBin"
Write-Host ""
Write-Host " IMPORTANT: Restart your terminal (or open a new PowerShell"
Write-Host " window) for the PATH changes to take effect."
Write-Host ""
Write-Host " To set SAMI_HOME permanently, add this to your profile:"
Write-Host "   [Environment]::SetEnvironmentVariable('SAMI_HOME', '$SamiHome', 'User')"
Write-Host "============================================================"
