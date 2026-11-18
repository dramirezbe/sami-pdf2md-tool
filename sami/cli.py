#!/usr/bin/env python3
"""sami — Smart Automated Markdown Interpreter.

Convert PDF files to Markdown with figures extracted.
Uses Marker for conversion: local, keyless, no API needed.

For each input PDF, creates a folder with the same stem containing:
  - <stem>.md  (text + LaTeX equations + Markdown tables)
  - figure images referenced by the Markdown

Usage:
    sami paper.pdf                     # -> paper/paper.md + figures
    sami paper.pdf -o out/             # -> out/paper.md + figures
    sami a.pdf b.pdf                   # batch convert
    sami paper.pdf --mode fast         # faster, lower quality
    sami paper.pdf --no-strip-refs     # keep the references section
    sami paper.pdf --flat              # no subfolder, output beside the PDF
    sami paper.pdf -q                  # quiet mode, minimal output

Exit codes: 0 success, 1 at least one PDF failed, 2 usage error.
"""
from __future__ import annotations

from sami.engines.marker import build_converter as build_marker_converter, write_figures

import argparse
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

import atexit
import signal

VALID_MODES = ("fast", "balanced")
MIN_VRAM_GB_FOR_VLM = 8


# ---------------------------------------------------------------------------
# App home directory: ~/.sami/
# ---------------------------------------------------------------------------

def ensure_app_home() -> Path:
    """Create and return the sami home directory (~/.sami/)."""
    app_home = Path(os.environ.get("SAMI_HOME", Path.home() / ".sami"))
    app_home.mkdir(exist_ok=True)
    (app_home / "cache").mkdir(exist_ok=True)
    (app_home / "config").mkdir(exist_ok=True)
    (app_home / "logs").mkdir(exist_ok=True)
    (app_home / "bin").mkdir(exist_ok=True)
    os.environ.setdefault("HF_HOME", str(app_home / "cache" / "huggingface"))
    os.environ.setdefault("TORCH_HOME", str(app_home / "cache" / "torch"))
    _ensure_llama_server(app_home)
    return app_home


# ---------------------------------------------------------------------------
# llama-server auto-provisioning
# ---------------------------------------------------------------------------

_LLAMA_CPP_RELEASES_API = (
    "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=1"
)


def _platform_asset_suffix() -> str | None:
    """Return the llama.cpp release asset suffix for this platform, or None."""
    import platform as _platform
    system = _platform.system()
    machine = _platform.machine().lower()
    if system == "Linux":
        if machine in ("aarch64", "arm64"):
            return "-ubuntu-arm64.tar.gz"
        return "-ubuntu-x64.tar.gz"
    if system == "Darwin":
        return "-macos-arm64.tar.gz" if machine == "arm64" else "-macos-x64.tar.gz"
    return None


def _download_llama_server(bin_dir: Path) -> Path | None:
    """Download the llama-server binary from GitHub releases into bin_dir."""
    import json
    import tarfile
    import urllib.request

    suffix = _platform_asset_suffix()
    if suffix is None:
        return None

    log("llama-server not found, downloading from llama.cpp releases...")
    try:
        req = urllib.request.Request(
            _LLAMA_CPP_RELEASES_API,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            releases = json.loads(resp.read())
    except Exception as exc:
        log(f"  Failed to query llama.cpp releases: {exc}")
        return None

    if not releases:
        return None

    asset_url = None
    for asset in releases[0].get("assets", []):
        name = asset["name"]
        if name.endswith(suffix) and not any(
            x in name for x in ("cuda", "rocm", "sycl", "vulkan", "openvino", "snapdragon")
        ):
            asset_url = asset["browser_download_url"]
            break

    if not asset_url:
        log(f"  No matching llama.cpp asset found for suffix {suffix}")
        return None

    log(f"  Downloading: {asset_url.split('/')[-1]}")
    try:
        tarball = bin_dir / "llama-server.tar.gz"
        urllib.request.urlretrieve(asset_url, tarball)

        with tarfile.open(tarball, "r:gz") as tf:
            members_to_extract = []
            for member in tf.getmembers():
                basename = Path(member.name).name
                if basename.startswith("llama-server") or basename.startswith("lib"):
                    member.name = basename
                    members_to_extract.append(member)
            tf.extractall(path=bin_dir, members=members_to_extract)

        tarball.unlink()

        server_bin = bin_dir / "llama-server"
        if server_bin.is_file():
            server_bin.chmod(server_bin.stat().st_mode | 0o111)
            log(f"  llama-server installed: {server_bin}")
            return server_bin
    except Exception as exc:
        log(f"  Failed to download/extract llama-server: {exc}")

    return None


def _ensure_llama_server(app_home: Path) -> None:
    """Make sure llama-server is available; download if needed."""
    if os.environ.get("LLAMA_CPP_BINARY") and (
        Path(os.environ["LLAMA_CPP_BINARY"]).is_file()
        or shutil.which(os.environ["LLAMA_CPP_BINARY"])
    ):
        return

    if shutil.which("llama-server"):
        return

    local_bin = app_home / "bin" / "llama-server"
    if local_bin.is_file():
        os.environ["LLAMA_CPP_BINARY"] = str(local_bin)
        ld_path = str(app_home / "bin")
        os.environ["LD_LIBRARY_PATH"] = (
            f"{ld_path}:{os.environ['LD_LIBRARY_PATH']}"
            if os.environ.get("LD_LIBRARY_PATH") else ld_path
        )
        return

    result = _download_llama_server(app_home / "bin")
    if result:
        os.environ["LLAMA_CPP_BINARY"] = str(result)
        ld_path = str(app_home / "bin")
        os.environ["LD_LIBRARY_PATH"] = (
            f"{ld_path}:{os.environ['LD_LIBRARY_PATH']}"
            if os.environ.get("LD_LIBRARY_PATH") else ld_path
        )

# ---------------------------------------------------------------------------
# Process cleanup: ensure llama-server and other child processes don't orphan
# ---------------------------------------------------------------------------

_CHILD_PIDS: set[int] = set()
_OUR_PID = os.getpid()
_CLEANING_UP = False


def _collect_llama_pids() -> set[int]:
    """Find llama-server processes that are children of this process."""
    pids = set()
    try:
        import psutil
        current = psutil.Process(_OUR_PID)
        for child in current.children(recursive=True):
            try:
                if "llama" in child.name().lower() or "llama" in " ".join(child.cmdline()).lower():
                    pids.add(child.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass
    return pids


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, OSError):
        return False


def _graceful_kill(pid: int, name: str = "child", timeout: float = 8.0) -> bool:
    """SIGTERM → wait → SIGKILL a single process. Returns True if it was killed."""
    if not _is_alive(pid):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        return False

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _is_alive(pid):
            log(f"[cleanup] Stopped {name} (pid {pid})")
            return True
        time.sleep(0.3)

    try:
        os.kill(pid, signal.SIGKILL)
        log(f"[cleanup] Force-killed {name} (pid {pid})")
        return True
    except (ProcessLookupError, OSError):
        return False


def _cleanup_all() -> None:
    """Kill tracked children + any orphan llama-server processes we spawned."""
    global _CLEANING_UP
    if _CLEANING_UP:
        return
    _CLEANING_UP = True

    orphans = _collect_llama_pids()
    all_pids = _CHILD_PIDS | orphans

    killed = set()
    for pid in all_pids:
        if _graceful_kill(pid, name="llama-server"):
            killed.add(pid)

    # Final sweep for anything that respawned or was missed
    for pid in _collect_llama_pids() - killed:
        _graceful_kill(pid, name="llama-server", timeout=3.0)

    # Suppress surya's atexit from printing redundant kill messages
    # by silencing the marker/surya logger
    try:
        import logging
        for name in ("marker", "surya", "surya.inference"):
            logging.getLogger(name).setLevel(logging.CRITICAL)
    except Exception:
        pass


def _signal_handler(signum, frame):
    """Handle SIGTERM/SIGINT: clean up children then exit."""
    signame = signal.Signals(signum).name
    print(f"\n[cleanup] Received {signame}, shutting down...", file=sys.stderr)
    _cleanup_all()
    sys.exit(128 + signum)


def _install_signal_handlers() -> None:
    """Install process handlers only while the CLI is actually running."""
    atexit.register(_cleanup_all)
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

# ---------------------------------------------------------------------------
# CPU auto-tuning: use ~90% of available cores, leave headroom for the OS
# ---------------------------------------------------------------------------

def _configure_cpu() -> dict:
    """Detect cores and set thread/worker counts for ~90% utilization."""
    physical = os.cpu_count() or 4
    # psutil gives physical cores (no hyperthreads); fall back to os.cpu_count
    try:
        import psutil
        physical = psutil.cpu_count(logical=False) or physical
    except ImportError:
        pass

    target = max(1, int(physical * 0.9))
    torch_threads = max(1, target)
    pdftext_workers = max(1, min(target, physical))
    omp_threads = str(max(1, target))
    postproc_workers = max(1, min(8, target))

    os.environ.setdefault("OMP_NUM_THREADS", omp_threads)
    os.environ.setdefault("MKL_NUM_THREADS", omp_threads)
    os.environ.setdefault("OPENBLAS_NUM_THREADS", omp_threads)
    os.environ.setdefault("FAST_LAYOUT_NUM_THREADS", str(torch_threads))
    os.environ.setdefault("DETECTOR_POSTPROCESSING_CPU_WORKERS", str(postproc_workers))

    return {
        "physical_cores": physical,
        "target_threads": target,
        "torch_threads": torch_threads,
        "pdftext_workers": pdftext_workers,
    }


_HEADING_LINE = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)
_REFERENCES_TITLE = re.compile(
    r"^(?:\d+\.?\s*)?(?:references|bibliography|referencias|bibliograf[ií]a)\b",
    re.IGNORECASE,
)
_MARKDOWN_DECOR = re.compile(r"[*_`~]|<[^>]+>")

# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

_QUIET = False


def log(msg: str, end: str = "\n", flush: bool = True) -> None:
    if not _QUIET:
        print(msg, end=end, flush=flush)


def log_stage(pdf_name: str, stage: str, end: str = "\n", flush: bool = True) -> None:
    log(f"  [{pdf_name}] {stage}", end=end, flush=flush)


def log_stage_done(elapsed: float) -> None:
    log(f"  ✓ {elapsed:.1f}s")


def _fmt_size(nbytes: int) -> str:
    if nbytes < 1024:
        return f"{nbytes} B"
    if nbytes < 1024 * 1024:
        return f"{nbytes / 1024:.1f} KB"
    return f"{nbytes / (1024 * 1024):.1f} MB"


def _page_count(pdf: Path) -> int | None:
    try:
        import pypdfium2
        doc = pypdfium2.PdfDocument(pdf)
        try:
            return len(doc)
        finally:
            doc.close()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# References stripping (pure text, no deps)
# ---------------------------------------------------------------------------

def _is_references_heading(match: "re.Match[str]") -> bool:
    title = _MARKDOWN_DECOR.sub("", match.group(1)).strip()
    return bool(_REFERENCES_TITLE.match(title))


def strip_references(text: str) -> str:
    """Drop every references/bibliography section from Markdown text."""
    headings = list(_HEADING_LINE.finditer(text))
    if not headings:
        return text

    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(headings):
        if not _is_references_heading(headings[index]):
            index += 1
            continue
        run_end = index
        while (run_end + 1 < len(headings)
               and _is_references_heading(headings[run_end + 1])):
            run_end += 1
        after = headings[run_end + 1] if run_end + 1 < len(headings) else None
        spans.append((headings[index].start(),
                      after.start() if after else len(text)))
        index = run_end + 1

    if not spans:
        return text

    kept: list[str] = []
    cursor = 0
    for begin, finish in spans:
        kept.append(text[cursor:begin].rstrip())
        cursor = finish
    if cursor < len(text):
        kept.append(text[cursor:])
    return "\n\n".join(part for part in kept if part) + (
        "\n" if not kept[-1].endswith("\n") else ""
    )


# ---------------------------------------------------------------------------
# Verbose converter: subclass PdfConverter to log each pipeline stage
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

def convert_pdf(
    converter, pdf_path: Path, output_dir: Path, strip_refs: bool, flat: bool
) -> Path:
    """Convert one PDF to Markdown + figures, transactionally."""
    from marker.output import text_from_rendered

    name = pdf_path.name
    size = pdf_path.stat().st_size
    pages = _page_count(pdf_path)

    log(f"\n{'=' * 60}")
    log(f"  File:  {pdf_path}")
    log(f"  Size:  {_fmt_size(size)}" + (f"  ({pages} pages)" if pages else ""))
    log(f"{'=' * 60}")

    total_t0 = time.monotonic()

    if flat:
        dest = output_dir
    else:
        dest = output_dir / pdf_path.stem
    dest.mkdir(parents=True, exist_ok=True)

    staging = Path(tempfile.mkdtemp(
        prefix=f".{pdf_path.stem}-pdf2md-", dir=dest.parent
    ))
    try:
        rendered = converter(str(pdf_path), pdf_name=name)

        t0 = time.monotonic()
        log_stage(name, "Extracting text and images...", end="", flush=True)
        text, _ext, images = text_from_rendered(rendered)
        log_stage_done(time.monotonic() - t0)

        if strip_refs:
            t0 = time.monotonic()
            orig_len = len(text)
            text = strip_references(text)
            stripped = orig_len - len(text)
            log_stage(name, f"Stripping references... removed {_fmt_size(stripped)}", end="", flush=True)
            log_stage_done(time.monotonic() - t0)

        fig_count = 0
        if images:
            t0 = time.monotonic()
            log_stage(name, f"Writing {len(images)} figure(s)...", end="", flush=True)
            fig_count = write_figures(images, staging)
            log_stage_done(time.monotonic() - t0)

        md_name = f"{pdf_path.stem}.md"
        (staging / md_name).write_text(text, encoding="utf-8")
        md_size = len(text.encode("utf-8"))

        for produced in sorted(staging.iterdir()):
            shutil.move(str(produced), str(dest / produced.name))

        total_elapsed = time.monotonic() - total_t0
        result_path = dest / md_name

        log(f"  [{name}] Done: {converter.page_count} pages → {result_path}")
        log(f"  [{name}] Output: {_fmt_size(md_size)} markdown, {fig_count} figure(s)")
        log(f"  [{name}] Total time: {total_elapsed:.1f}s "
            f"({total_elapsed / (converter.page_count or 1):.1f}s/page)")

    except Exception:
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return result_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="sami",
        description="Convert PDF files to Markdown with extracted figures.",
    )
    from sami import __version__
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}",
    )
    parser.add_argument("pdf", nargs="+", help="PDF file(s) to convert")
    parser.add_argument(
        "-o", "--output", metavar="DIR", default=None,
        help="output directory (default: beside each PDF)",
    )
    parser.add_argument(
        "--mode", choices=VALID_MODES, default=None,
        help="conversion quality: fast or balanced (default: auto by device)",
    )
    parser.add_argument(
        "--no-strip-refs", action="store_true",
        help="keep the references/bibliography section",
    )
    parser.add_argument(
        "--flat", action="store_true",
        help="don't create a subfolder per PDF; write .md + figures directly into the output dir",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="minimal output, no per-stage logging",
    )
    args = parser.parse_args()
    strip_refs = not args.no_strip_refs

    global _QUIET
    _QUIET = args.quiet

    pdfs: list[Path] = []
    for raw in args.pdf:
        p = Path(raw).expanduser().resolve()
        if not p.is_file():
            print(f"Not a file: {raw}", file=sys.stderr)
            return 2
        if p.suffix.lower() != ".pdf":
            print(f"Not a PDF: {raw}", file=sys.stderr)
            return 2
        pdfs.append(p)

    ensure_app_home()
    _install_signal_handlers()
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    cpu_config = _configure_cpu()
    log(f"sami: {len(pdfs)} file(s) queued")
    total_t0 = time.monotonic()

    converter = build_marker_converter(
        args.mode, cpu_config=cpu_config, logger=log,
        stage_logger=log_stage, stage_done_logger=log_stage_done,
    )

    # Snapshot child PIDs after model load (llama-server spawns here)
    _CHILD_PIDS.update(_collect_llama_pids())

    done = 0
    failed = 0
    total_pages = 0
    try:
        for i, pdf in enumerate(pdfs, 1):
            if len(pdfs) > 1:
                log(f"\n[{i}/{len(pdfs)}]")
            out_dir = Path(args.output).resolve() if args.output else pdf.parent
            try:
                md = convert_pdf(converter, pdf, out_dir, strip_refs, args.flat)
                total_pages += converter.page_count or 0
                done += 1
            except Exception as exc:
                failed += 1
                print(f"FAILED: {pdf.name}: {exc}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\n[cleanup] Interrupted by user", file=sys.stderr)
        _cleanup_all()
        return 130
    except BaseException:
        _cleanup_all()
        raise
    finally:
        # Always attempt graceful cleanup of inference servers
        _cleanup_all()

    total_elapsed = time.monotonic() - total_t0
    log(f"\n{'=' * 60}")
    log(f"  Summary: {done} converted, {failed} failed, {total_pages} total pages")
    log(f"  Total time: {total_elapsed:.1f}s")
    if total_pages > 0:
        log(f"  Throughput: {total_elapsed / total_pages:.1f}s/page")
    log(f"{'=' * 60}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
