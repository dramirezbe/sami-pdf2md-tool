"""Installation registration, offline health checks, and explicit model preparation."""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import uuid

from sami import __version__
from sami.contracts import MODES
from sami.events import PROTOCOL_VERSION, write_json_line

_SCHEMA_VERSION = 1
_FAST_DEPS = ("pymupdf", "pdfplumber")
_MARKER_DEPS = ("marker-pdf", "surya-ocr", "torch", "psutil", "six")
_LAYOUT_REPO = "datalab-to/surya_layout2"
_OCR_CHECKPOINT = "ocr_error_detection/2025_02_18"


def app_home() -> Path:
    return Path(os.environ.get("SAMI_HOME", Path.home() / ".sami")).expanduser().resolve()


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_record(path: Path) -> dict | None:
    try:
        with path.open("rb") as stream:
            data = json.loads(stream.read(1024 * 1024))
        if isinstance(data, dict) and type(data.get("schema_version")) is int and data["schema_version"] == _SCHEMA_VERSION:
            return data
    except (OSError, ValueError):
        pass
    return None


def _write_record(path: Path, value: dict) -> None:
    fd, name = tempfile.mkstemp(prefix=f".{path.stem}-", dir=path.parent)
    pending = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)


def register_installation(home: Path, executable: Path) -> dict:
    executable = executable.expanduser().absolute()
    if not executable.is_file():
        raise FileNotFoundError(f"SAMI launcher is missing: {executable}")
    home.mkdir(parents=True, exist_ok=True)
    path = home / "installation.json"
    previous = _read_record(path) or {}
    record = {
        "schema_version": _SCHEMA_VERSION,
        "installation_id": previous.get("installation_id") or uuid.uuid4().hex,
        "cli_version": __version__,
        "protocol_version": PROTOCOL_VERSION,
        "executable": str(executable),
        "python_executable": str(Path(sys.executable).absolute()),
        "sami_home": str(home),
        "registered_at": _timestamp(),
    }
    _write_record(path, record)
    return record


def _launcher(explicit: Path | None, home: Path) -> Path:
    if explicit is not None:
        return explicit
    invoked = Path(sys.argv[0])
    if invoked.name.lower() in ("sami", "sami.exe") and invoked.is_file():
        return invoked
    record = _read_record(home / "installation.json") or {}
    if record.get("executable") and Path(record["executable"]).is_file():
        return Path(record["executable"])
    candidate = Path(sys.executable).with_name("sami.exe" if os.name == "nt" else "sami")
    if candidate.is_file():
        return candidate
    if installed := shutil.which(candidate.name):
        return Path(installed)
    raise FileNotFoundError("SAMI launcher was not found. Run setup from the installed CLI.")


def _has_header(path: Path | None, prefixes: tuple[bytes, ...]) -> bool:
    if path is None:
        return False
    try:
        with path.open("rb") as stream:
            return stream.read(4).startswith(prefixes)
    except OSError:
        return False


def _file_present(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _llama_binary(home: Path) -> Path | None:
    name = "llama-server.exe" if os.name == "nt" else "llama-server"
    directory = home / "bin"
    candidates = [directory / variant / name for variant in ("cuda", "cpu", "")]
    configured = os.environ.get("LLAMA_CPP_BINARY") or shutil.which(name)
    if configured:
        candidates.insert(0, Path(shutil.which(configured) or configured))
    prefixes = (b"MZ", b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf")
    return next((p for p in candidates if _has_header(p, prefixes)), None)


def _layout_files(hf_home: Path) -> tuple[Path, ...]:
    location = os.environ.get("FAST_LAYOUT_MODEL_CHECKPOINT", f"hf://{_LAYOUT_REPO}")
    if location.startswith("hf://"):
        parts = location.removeprefix("hf://").split("/")
        repo = "--".join(parts[:2])
        hub = Path(os.environ.get("HF_HUB_CACHE", hf_home / "hub"))
        snapshots = hub / f"models--{repo}" / "snapshots"
        try:
            paths = [path.joinpath(*parts[2:]) for path in sorted(snapshots.iterdir(), reverse=True)]
        except OSError:
            paths = []
    else:
        paths = [Path(location)]
    for folder in paths:
        files = (folder / "config.json", folder / "rfdetr_layout.pth")
        if all(_file_present(file) for file in files):
            return files
    return ()


def _ocr_files() -> tuple[Path, ...]:
    model_cache = os.environ.get("MODEL_CACHE_DIR")
    if model_cache is None:
        try:
            from platformdirs import user_cache_dir
        except ImportError:
            return ()
        model_cache = str(Path(user_cache_dir("datalab")) / "models")
    checkpoint = os.environ.get("OCR_ERROR_MODEL_CHECKPOINT", f"s3://{_OCR_CHECKPOINT}")
    folder = Path(model_cache) / checkpoint.removeprefix("s3://") if checkpoint.startswith("s3://") else Path(checkpoint)
    files = tuple(folder / name for name in ("config.json", "model.safetensors", "tokenizer.json"))
    return files if all(_file_present(file) for file in files) else ()


def _missing_packages(names: tuple[str, ...]) -> list[str]:
    missing = []
    for name in names:
        try:
            metadata.version(name)
        except metadata.PackageNotFoundError:
            missing.append(name)
    return missing


def _inventory(home: Path) -> dict:
    from sami.engines.marker import _locate_gguf_paths

    hf_home = Path(os.environ.get("HF_HOME", home / "cache" / "huggingface"))
    llama = _llama_binary(home)
    gguf = tuple(Path(p) for p in _locate_gguf_paths(home) if p)
    if len(gguf) != 2 or not all(_has_header(p, (b"GGUF",)) for p in gguf):
        gguf = ()
    layout = _layout_files(hf_home)
    ocr = _ocr_files()
    fingerprint = {}
    for file in (*((llama,) if llama else ()), *gguf, *layout, *ocr):
        try:
            stat = file.stat()
            fingerprint[str(file.absolute())] = [stat.st_size, stat.st_mtime_ns]
        except OSError:
            pass
    return {
        "llama": llama, "gguf": gguf, "layout": layout, "ocr": ocr,
        "hf_home": hf_home, "fingerprint": fingerprint,
    }


def health(home: Path) -> dict:
    inventory = _inventory(home)
    registration_path = home / "installation.json"
    installation = _read_record(registration_path)
    profile = _read_record(home / "compatibility.json") or {}
    warnings = []
    repair_reasons = []

    fast_missing = _missing_packages(_FAST_DEPS)
    marker_missing = _missing_packages(_MARKER_DEPS)
    if fast_missing or marker_missing:
        repair_reasons.append(f"Missing CLI packages: {', '.join(fast_missing + marker_missing)}")
    if not installation:
        if registration_path.exists():
            repair_reasons.append("Installation record is invalid. Run sami setup.")
        else:
            warnings.append("Installation is not registered. Run sami setup.")
    else:
        executable = installation.get("executable")
        identity = installation.get("installation_id")
        if not isinstance(identity, str) or not identity or installation.get("protocol_version") != PROTOCOL_VERSION:
            repair_reasons.append("Installation identity or protocol is invalid. Run sami setup.")
        if not isinstance(executable, str) or not Path(executable).is_absolute() or not Path(executable).is_file():
            repair_reasons.append("Registered launcher is unavailable. Run sami setup.")
        elif installation.get("cli_version") != __version__:
            warnings.append("Installation record is from another CLI version. Run sami setup.")

    inventory_notes = {
        "llama": "llama-server is missing or invalid.",
        "gguf": "Surya GGUF model files are missing or invalid.",
        "layout": "The RF-DETR layout model is incomplete.",
        "ocr": "The OCR error detection model is incomplete.",
    }
    for key, message in inventory_notes.items():
        if not inventory[key]:
            warnings.append(message)
    available = {
        "fast": not fast_missing,
        "balanced": not marker_missing and bool(inventory["layout"] and inventory["ocr"]),
        "quality": not marker_missing and bool(inventory["llama"] and inventory["gguf"] and inventory["ocr"]),
    }
    installation_id = installation.get("installation_id") if installation else None
    validated = bool(
        installation_id
        and profile.get("installation_id") == installation_id
        and profile.get("cli_version") == __version__
        and profile.get("fingerprint") == inventory["fingerprint"]
    )
    checks = profile.get("modes") if validated else None
    validated = bool(
        validated and isinstance(checks, dict)
        and all(isinstance(checks.get(mode), dict) for mode in MODES)
        and all(isinstance(profile.get(key), list) and all(isinstance(item, str) for item in profile[key])
                for key in ("warnings", "failures"))
    )
    if not validated:
        checks = {}
        warnings.append("CPU readiness has not been verified for this installation. Run sami setup.")
    if validated:
        warnings.extend(profile.get("warnings", []))
        repair_reasons.extend(profile.get("failures", []))
    modes = {
        mode: {
            "available": available[mode],
            "ready": available[mode] and checks.get(mode, {}).get("cpu") is True,
            "device": checks.get(mode, {}).get("device", "cpu" if mode == "fast" else None),
            "inference_server": mode == "quality",
        }
        for mode in MODES
    }
    status = (
        "repair_required" if repair_reasons else
        "degraded" if warnings or not all(mode["ready"] for mode in modes.values()) else "ready"
    )
    return {
        "protocol_version": PROTOCOL_VERSION,
        "installation_id": installation_id,
        "cli_version": __version__,
        "status": status,
        "selected_device": modes["balanced"]["device"],
        "modes": modes,
        "paths": {
            "sami_home": str(home),
            "executable": installation.get("executable") if installation else None,
            "llama_server": str(inventory["llama"]) if inventory["llama"] else None,
            "hf_cache": str(inventory["hf_home"]),
        },
        "warnings": warnings,
        "repair_reasons": repair_reasons,
    }


def _prepare_models(home: Path) -> None:
    from sami.llama_runtime import ensure_server
    from surya.settings import settings
    from surya.common.s3 import download_directory
    from surya.common.rfdetr_torch import resolve_model_dir
    from surya.inference.backends.llamacpp import _download_gguf_files

    def progress(message):
        print(message, file=sys.stderr, flush=True)

    progress("Preparing llama-server...")
    binary, _ = ensure_server(home, want_cuda=True, logger=progress)
    if binary is None:
        raise RuntimeError("Could not prepare a usable llama-server.")
    inventory = _inventory(home)
    if not inventory["layout"]:
        progress("Preparing the RF-DETR layout model...")
        resolve_model_dir(settings.FAST_LAYOUT_MODEL_CHECKPOINT)
    if not inventory["ocr"] and settings.OCR_ERROR_MODEL_CHECKPOINT.startswith("s3://"):
        progress("Preparing the OCR error detection model...")
        checkpoint = settings.OCR_ERROR_MODEL_CHECKPOINT.removeprefix("s3://")
        destination = Path(settings.MODEL_CACHE_DIR) / checkpoint
        destination.mkdir(parents=True, exist_ok=True)
        download_directory(checkpoint, str(destination))
    if not inventory["gguf"]:
        progress("Preparing the Surya GGUF models...")
        _download_gguf_files()


def _smoke(pdf: Path, output: Path, mode: str, device: str) -> dict:
    print(f"Checking {mode} on {device}...", file=sys.stderr, flush=True)
    run = subprocess.run(
        [sys.executable, "-m", "sami.cli", "convert", str(pdf), "-o", str(output),
         "--mode", mode, "--device", device, "--json", "--quiet"],
        stdout=subprocess.PIPE, text=True, encoding="utf-8", env=dict(os.environ, PYTHONUTF8="1"),
    )
    for line in run.stdout.splitlines():
        event = json.loads(line)
        if event["event"] == "job_finished":
            return event["data"]["result"]
    raise RuntimeError(f"{mode} validation returned exit {run.returncode} without a document result.")


def prepare(home: Path, installation: dict) -> None:
    from sami.hardware import gpu_info

    report = {
        "schema_version": _SCHEMA_VERSION, "installation_id": installation["installation_id"],
        "cli_version": __version__, "validated_at": _timestamp(),
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "hardware": {}, "modes": {}, "warnings": [], "failures": [],
    }
    try:
        import pymupdf

        _prepare_models(home)
        report["hardware"] = hardware = gpu_info()
        with tempfile.TemporaryDirectory(prefix="sami-setup-") as directory:
            work = Path(directory)
            pdf = work / "readiness.pdf"
            with pymupdf.open() as document:
                page = document.new_page()
                page.insert_text((72, 100), "SAMI runtime readiness check")
                page.insert_text((72, 132), "This temporary document checks local PDF conversion.")
                document.save(pdf)
            for mode in MODES:
                result = _smoke(pdf, work / f"cpu-{mode}", mode, "cpu")
                cpu = result["status"] == "succeeded" and result["device"] == "cpu"
                mode_check = {"cpu": cpu, "device": "cpu" if cpu else None}
                report["modes"][mode] = mode_check
                if not cpu:
                    report["failures"].append(f"{mode} CPU validation failed: {result['errors'] or result['status']}")
                elif mode != "fast" and (hardware["physical_gpu"] or hardware["torch_cuda"]):
                    try:
                        accelerated = _smoke(pdf, work / f"auto-{mode}", mode, "auto")
                        if accelerated["status"] == "succeeded":
                            mode_check["device"] = accelerated["device"]
                        if mode_check["device"] == "cpu":
                            report["warnings"].append(f"{mode} is ready on CPU. GPU validation did not succeed.")
                    except (OSError, ValueError, RuntimeError) as exc:
                        report["warnings"].append(f"{mode} is ready on CPU. GPU validation failed: {exc}")
    except (Exception, SystemExit) as exc:
        report["failures"].append(f"Setup failed: {exc}")
    for mode in MODES:
        report["modes"].setdefault(mode, {"cpu": False, "device": None})
    report["fingerprint"] = _inventory(home)["fingerprint"]
    path = home / "compatibility.json"
    if previous := _read_record(path):
        _write_record(home / "compatibility.previous.json", previous)
    _write_record(path, report)


def management_command(command: str, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=f"sami {command}")
    parser.add_argument("--json", action="store_true", help="emit one JSON object")
    if command == "setup":
        parser.add_argument("--register-only", action="store_true", help="record the installed launcher without downloads")
        parser.add_argument("--executable", type=Path, help="absolute path of the launcher to register")
        parser.add_argument("--force", action="store_true", help="repeat validation for a ready installation")
    args = parser.parse_args(argv)
    home = app_home()
    if command == "setup":
        try:
            from sami.cli import ensure_app_home

            ensure_app_home()
            installation = register_installation(home, _launcher(args.executable, home))
            if not args.register_only and (args.force or health(home)["status"] != "ready"):
                with contextlib.redirect_stdout(sys.stderr):
                    prepare(home, installation)
        except (OSError, ValueError) as exc:
            print(f"Setup failed: {exc}", file=sys.stderr)
            if args.json:
                write_json_line(sys.stdout, json.dumps({"status": "repair_required", "repair_reasons": [str(exc)]}))
            return 1

    result = health(home)
    if command == "doctor":
        result["installation"] = _read_record(home / "installation.json")
        result["compatibility"] = _read_record(home / "compatibility.json")
    if command == "setup" and args.register_only and not args.json:
        print(f"SAMI launcher registered at {result['paths']['executable']}.")
        return 0
    if args.json:
        write_json_line(sys.stdout, json.dumps(result, ensure_ascii=False))
    else:
        print(f"sami {__version__} — {result['status'].upper()}")
        print(f"  SAMI_HOME:    {home}")
        print("  llama-server: " + ("OK" if result["paths"]["llama_server"] else "MISSING"))
        print("  HF cache:     " + ("OK" if Path(result["paths"]["hf_cache"]).is_dir() else "MISSING"))
        if command == "doctor":
            print(f"  CLI launcher: {result['paths']['executable'] or 'unregistered'}")
            profile = result["compatibility"] or {}
            print(f"  Last setup:   {profile.get('validated_at', 'unverified')}")
            for mode, status in result["modes"].items():
                print(f"  {mode}: {status['device'] or 'unverified'}")
        for warning in result["warnings"]:
            print(f"  WARNING: {warning}")
        for reason in result["repair_reasons"]:
            print(f"  REPAIR: {reason}")
    if command == "setup":
        return int(not args.register_only and not all(m["ready"] for m in result["modes"].values()))
    return 3 if result["status"] == "repair_required" else 0
