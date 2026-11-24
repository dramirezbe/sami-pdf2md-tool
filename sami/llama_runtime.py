"""Provision the local llama.cpp server and verify CUDA before using it."""
from __future__ import annotations

import ctypes
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

_RELEASES_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=1"


def _cuda_driver_version() -> tuple[int, int] | None:
    try:
        driver = (
            ctypes.WinDLL("nvcuda.dll")
            if os.name == "nt" else ctypes.CDLL("libcuda.so.1")
        )
        version = ctypes.c_int()
        if driver.cuInit(0) == 0 and driver.cuDriverGetVersion(ctypes.byref(version)) == 0:
            return version.value // 1000, version.value % 1000 // 10
    except (OSError, AttributeError):
        pass
    return None


def _asset_names() -> tuple[str, str, str] | None:
    arch = "arm64" if platform.machine().lower() in ("aarch64", "arm64") else "x64"
    system = platform.system()
    if system == "Linux":
        return f"-bin-ubuntu-{arch}.tar.gz", "ubuntu", arch
    if system == "Windows":
        return f"-bin-win-cpu-{arch}.zip", "win", arch
    if system == "Darwin":
        return f"-bin-macos-{arch}.tar.gz", "macos", arch
    return None


def _select_assets(assets, *, platform_id, arch, extension, driver_version):
    """Select a CUDA executable and its matching redistributable, if available."""
    candidates = {}
    pattern = re.compile(rf"-bin-{platform_id}-cuda-(\d+)\.(\d+)-{arch}{re.escape(extension)}$")
    for asset in assets:
        name = asset["name"]
        match = pattern.search(name)
        if match:
            version = tuple(map(int, match.groups()))
            candidates.setdefault(version, {})[name.startswith("cudart-")] = asset
    for version in sorted(candidates, reverse=True):
        pair = candidates[version]
        if version <= driver_version and len(pair) == 2:
            return pair[False], pair[True]
    return ()


def _server_env(binary: Path) -> dict:
    env = os.environ.copy()
    if os.name != "nt":
        paths = [str(binary.parent)]
        if env.get("LD_LIBRARY_PATH"):
            paths.append(env["LD_LIBRARY_PATH"])
        env["LD_LIBRARY_PATH"] = os.pathsep.join(paths)
    return env


def _probe_server(binary: Path, flag: str) -> str:
    try:
        probe = subprocess.run(
            [str(binary), flag], env=_server_env(binary),
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return f"{probe.stdout}\n{probe.stderr}" if probe.returncode == 0 else ""


def _has_cuda(binary: Path) -> bool:
    return bool(re.search(r"^\s*CUDA\d+:", _probe_server(binary, "--list-devices"), re.MULTILINE))


def supports_vram_fit(binary: Path) -> bool:
    help_text = _probe_server(binary, "--help")
    return "--fit " in help_text and "--n-gpu-layers " in help_text and "'auto'" in help_text


def _keep_asset_file(name: str) -> bool:
    return name.startswith(("llama-server", "lib")) or name.endswith(".dll")


def _extract_asset(asset, target: Path, logger) -> None:
    name = asset["name"]
    logger(f"  Downloading: {name}")
    archive = target / name
    with urllib.request.urlopen(asset["browser_download_url"], timeout=60) as source:
        with archive.open("wb") as destination:
            shutil.copyfileobj(source, destination)
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                basename = Path(member.filename).name
                if not member.is_dir() and _keep_asset_file(basename):
                    member.filename = basename
                    bundle.extract(member, target)
    else:
        with tarfile.open(archive, "r:gz") as bundle:
            members = []
            for member in bundle.getmembers():
                basename = Path(member.name).name
                if not member.isdir() and _keep_asset_file(basename):
                    member.name = basename
                    members.append(member)
            bundle.extractall(target, members=members, filter="data")
    archive.unlink()


def _fetch_assets() -> list:
    request = urllib.request.Request(_RELEASES_API, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        releases = json.load(response)
    return releases[0].get("assets", []) if releases else []


def _activate(binary: Path, cuda: bool) -> tuple[Path, bool]:
    binary = binary.resolve()
    os.environ["LLAMA_CPP_BINARY"] = str(binary)
    if os.name != "nt":
        os.environ["LD_LIBRARY_PATH"] = _server_env(binary)["LD_LIBRARY_PATH"]
    return binary, cuda


def _install_assets(assets, binary: Path, logger, *, require_cuda=False) -> None:
    """Publish the complete release atomically into a variant-specific directory."""
    with tempfile.TemporaryDirectory(dir=binary.parent.parent, prefix=".llama-") as work:
        stage = Path(work) / "runtime"
        stage.mkdir()
        for asset in assets:
            _extract_asset(asset, stage, logger)
        staged_binary = stage / binary.name
        staged_binary.chmod(staged_binary.stat().st_mode | 0o111)
        if require_cuda and not _has_cuda(staged_binary):
            raise RuntimeError("llama-server did not enumerate a CUDA device")
        try:
            stage.rename(binary.parent)
        except OSError:
            # Another run may already have installed the same variant.
            if not binary.is_file() or (require_cuda and not _has_cuda(binary)):
                raise


def ensure_server(app_home: Path, *, want_cuda: bool, logger) -> tuple[Path | None, bool]:
    """Use a configured server or provision a verified CUDA build with CPU fallback."""
    bin_dir = app_home / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    binary_name = "llama-server.exe" if os.name == "nt" else "llama-server"
    cpu_binary = bin_dir / "cpu" / binary_name
    cuda_binary = bin_dir / "cuda" / binary_name

    configured = os.environ.get("LLAMA_CPP_BINARY")
    if configured:
        path = Path(shutil.which(configured) or configured).expanduser().resolve()
        if path.is_file():
            return _activate(path, want_cuda and _has_cuda(path))

    on_path = shutil.which(binary_name)
    if want_cuda and on_path and _has_cuda(Path(on_path)):
        return _activate(Path(on_path), True)
    if want_cuda and cuda_binary.is_file() and _has_cuda(cuda_binary):
        return _activate(cuda_binary, True)

    cpu_candidates = [cpu_binary, bin_dir / binary_name]
    if on_path:
        cpu_candidates.insert(0, Path(on_path))
    cpu = next((candidate for candidate in cpu_candidates if candidate.is_file()), None)
    if not want_cuda:
        if cpu is not None:
            return _activate(cpu, False)
        if cuda_binary.is_file() and _has_cuda(cuda_binary):
            return _activate(cuda_binary, False)

    platform_assets = _asset_names()
    driver = _cuda_driver_version() if want_cuda and not cuda_binary.parent.exists() else None
    try:
        if platform_assets and (driver or cpu is None):
            cpu_suffix, platform_id, arch = platform_assets
            extension = ".zip" if platform_id == "win" else ".tar.gz"
            assets = _fetch_assets()
            if driver:
                cuda_assets = _select_assets(
                    assets, platform_id=platform_id, arch=arch,
                    extension=extension, driver_version=driver,
                )
                if cuda_assets:
                    try:
                        _install_assets(cuda_assets, cuda_binary, logger, require_cuda=True)
                        return _activate(cuda_binary, True)
                    except (OSError, RuntimeError, tarfile.TarError, zipfile.BadZipFile) as exc:
                        logger(f"  CUDA llama-server setup failed: {exc}")
            if cpu is None:
                cpu_asset = next(
                    (asset for asset in assets if asset["name"].endswith(cpu_suffix)), None
                )
                if cpu_asset:
                    _install_assets((cpu_asset,), cpu_binary, logger)
                    cpu = cpu_binary
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
        logger(f"  llama-server setup failed: {exc}")
    if want_cuda:
        logger("  CUDA llama-server unavailable. VLM will use CPU.")
    if cpu:
        return _activate(cpu, False)
    return None, False
