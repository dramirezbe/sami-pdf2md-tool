#!/usr/bin/env python3
"""sami — Smart Automated Markdown Interpreter.

Convert PDF files to Markdown with figures extracted.
Converts PDFs locally with the fast or Marker engines.

For each input PDF, creates a folder with the same stem containing:
  - <stem>.md  (text + LaTeX equations + Markdown tables)
  - figure images referenced by the Markdown

Usage:
    sami paper.pdf                     # -> paper/paper.md + figures
    sami paper.pdf -o out/             # -> out/paper.md + figures
    sami a.pdf b.pdf                   # batch convert
    sami paper.pdf --mode fast         # fast mode
    sami paper.pdf --mode quality      # Marker balanced profile
    sami paper.pdf --json              # protocol 1 JSONL on stdout
    sami paper.pdf --flat              # no subfolder, output beside the PDF
    sami paper.pdf -q                  # quiet mode, minimal output

Exit codes: 0 success, 1 at least one PDF failed, 2 usage error.
"""
from __future__ import annotations

import argparse
import contextlib
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

import signal

from sami.contracts import (
    ConversionOptions,
    ConversionRequest,
    JobResult,
    RunResult,
)
from sami.events import EventSequencer
from sami.outputs import make_staging_dir, prepend_frontmatter, publish, reserve_stem

VALID_MODES = ("fast", "balanced", "quality")


# ---------------------------------------------------------------------------
# App home directory: ~/.sami/
# ---------------------------------------------------------------------------

def ensure_app_home() -> Path:
    """Create and return the sami home directory (~/.sami/)."""
    app_home = Path(os.environ.get("SAMI_HOME", Path.home() / ".sami"))
    app_home.mkdir(exist_ok=True)
    for name in ("cache", "config", "logs", "bin"):
        (app_home / name).mkdir(exist_ok=True)
    os.environ.setdefault("HF_HOME", str(app_home / "cache" / "huggingface"))
    os.environ.setdefault("TORCH_HOME", str(app_home / "cache" / "torch"))
    return app_home


def _signal_handler(signum, frame):
    signame = signal.Signals(signum).name
    print(f"\n[cleanup] Received {signame}, shutting down...", file=sys.stderr)
    sys.exit(128 + signum)


def _install_signal_handlers() -> None:
    """Install process handlers only while the CLI is actually running."""
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
_JSON_MODE = False
_ACTIVE_PROGRESS_CALLBACK = None


def log(msg: str, end: str = "\n", flush: bool = True) -> None:
    if not _QUIET:
        print(msg, end=end, flush=flush, file=sys.stderr if _JSON_MODE else sys.stdout)


def log_stage(pdf_name: str, stage: str, end: str = "\n", flush: bool = True) -> None:
    log(f"  [{pdf_name}] {stage}", end=end, flush=flush)


def log_stage_done(elapsed: float) -> None:
    log(f"  ✓ {elapsed:.1f}s")


def _marker_stage_logger(name: str, stage: str, end: str = "\n", flush: bool = True) -> None:
    log_stage(name, stage, end=end, flush=flush)
    if _ACTIVE_PROGRESS_CALLBACK is not None:
        _ACTIVE_PROGRESS_CALLBACK(stage)


def _marker_stage_done(elapsed: float) -> None:
    log_stage_done(elapsed)


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
# Health subcommand
# ---------------------------------------------------------------------------

def _health_command(argv: list[str]) -> int:
    """Implement `sami health [--json]`.

    Reads ~/.sami/compatibility.json if present and performs lightweight
    path checks (< 1 s, no Torch/model loading).  Emits one JSON object to
    stdout if --json; otherwise prints a human-readable summary.

    Exit codes: 0 = ready/degraded, 3 = repair_required.
    """
    import json as _json
    emit_json = "--json" in argv

    app_home = Path(os.environ.get("SAMI_HOME", Path.home() / ".sami"))
    binary = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    bin_dir = app_home / "bin"
    candidates = [bin_dir / "cuda" / binary, bin_dir / "cpu" / binary, bin_dir / binary]
    configured = os.environ.get("LLAMA_CPP_BINARY") or shutil.which(binary)
    if configured:
        candidates.insert(0, Path(shutil.which(configured) or configured))
    llama_bin = next((path for path in candidates if path.is_file()), None)
    llama_ok = llama_bin is not None

    hf_cache = Path(os.environ.get("HF_HOME", app_home / "cache" / "huggingface"))

    from sami import __version__

    warnings: list[str] = []
    repair_reasons: list[str] = []

    # Check llama-server for quality mode
    if not llama_ok:
        warnings.append("llama-server not found — quality mode will attempt download on first use")

    # Check HF cache directory
    if not hf_cache.is_dir():
        warnings.append(f"HF cache missing: {hf_cache}")

    # Determine status
    if repair_reasons:
        status = "repair_required"
    elif warnings:
        status = "degraded"
    else:
        status = "ready"

    result = {
        "protocol_version": 1,
        "cli_version": __version__,
        "status": status,
        "modes": {
            "fast":     {"available": True,     "device": "cpu", "inference_server": False},
            "balanced": {"available": True,     "device": "cpu", "inference_server": False,
                         "note": "RF-DETR can use CUDA. OCR may start llama-server."},
            "quality":  {"available": llama_ok, "device": "cpu", "inference_server": True,
                         "note": "GPU offload scaled by VRAM at runtime"},
        },
        "paths": {
            "sami_home":    str(app_home),
            "llama_server": str(llama_bin) if llama_ok else None,
            "hf_cache":     str(hf_cache),
        },
        "warnings": warnings,
        "repair_reasons": repair_reasons,
    }

    if emit_json:
        print(_json.dumps(result), flush=True)
    else:
        print(f"sami {__version__} — {status.upper()}")
        print(f"  SAMI_HOME:    {app_home}")
        print(f"  llama-server: {'OK' if llama_ok else 'MISSING (quality mode will download on first use)'}")
        print(f"  HF cache:     {'OK' if hf_cache.is_dir() else 'MISSING'}")
        for w in warnings:
            print(f"  WARNING: {w}")
        for r in repair_reasons:
            print(f"  REPAIR: {r}")

    return 3 if status == "repair_required" else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _effective_device(engine: str, mode: str | None = None) -> str:
    if engine == "fast":
        return "cpu"
    configured = os.environ.get("TORCH_DEVICE", "").lower()
    fast_device = os.environ.get("FAST_DETECTOR_DEVICE", "").lower()
    backend = os.environ.get("SURYA_INFERENCE_BACKEND", "").lower()
    if configured == "cpu" or fast_device == "cpu":
        return "cpu"
    if mode != "balanced" and backend == "llamacpp" and os.environ.get("LLAMA_CPP_NGL", "0") == "0":
        return "cpu"
    try:
        import torch
        if torch.cuda.is_available():
            return "rocm" if getattr(torch.version, "hip", None) else "cuda"
    except Exception:
        pass
    return "cpu"


def main(argv: list[str] | None = None) -> int:
    with contextlib.ExitStack() as runtime:
        return _main(argv, runtime)


def _main(argv: list[str] | None, runtime: contextlib.ExitStack) -> int:
    global _QUIET, _JSON_MODE, _ACTIVE_PROGRESS_CALLBACK

    # Dispatch subcommands before building the main parser.
    raw_argv = argv if argv is not None else sys.argv[1:]
    if raw_argv and raw_argv[0] == "health":
        return _health_command(raw_argv[1:])
    if raw_argv and raw_argv[0] == "upgrade":
        from sami.upgrade import upgrade_command

        return upgrade_command(raw_argv[1:])

    parser = argparse.ArgumentParser(
        prog="sami",
        description="Convert PDF files to Markdown with extracted figures.",
        epilog="Use 'sami upgrade' to update the installed CLI.",
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
        "--mode", choices=VALID_MODES, default="balanced",
        help="conversion mode: fast, Marker balanced, or Marker quality (default: balanced)",
    )
    parser.add_argument(
        "--no-strip-refs", action="store_true",
        help="accepted for compatibility; references are retained by all modes",
    )
    parser.add_argument(
        "--flat", action="store_true",
        help="don't create a subfolder per PDF; write .md + figures directly into the output dir",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="minimal output, no per-stage logging",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit protocol 1 JSON Lines events on stdout",
    )
    args = parser.parse_args(argv)
    _QUIET = args.quiet
    _JSON_MODE = args.json
    event_stdout = sys.stdout

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
    pdfs = list(dict.fromkeys(pdfs))

    from sami.engines import convert as convert_engine, select_engine

    mode = args.mode
    selection = select_engine(mode)
    app_home = ensure_app_home()
    for signum in (signal.SIGTERM, signal.SIGINT):
        runtime.callback(signal.signal, signum, signal.getsignal(signum))
    _install_signal_handlers()
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    cpu_config = _configure_cpu()
    from sami import __version__
    run_id = uuid.uuid4().hex
    sequencer = EventSequencer(run_id)

    def emit(event: str, data: dict, *, job_id: str | None = None, attempt: int | None = None) -> None:
        if args.json:
            print(
                sequencer.create(event, data, job_id=job_id, attempt=attempt).to_json_line(),
                file=event_stdout,
                flush=True,
            )

    emit("run_started", {"mode": mode, "default_mode": "balanced", "version": __version__})
    emit("inputs_resolved", {"count": len(pdfs), "inputs": [str(pdf) for pdf in pdfs], "issues": []})
    log(f"sami: {len(pdfs)} file(s) queued")
    total_t0 = time.monotonic()
    effective_device = _effective_device(selection.engine, mode)
    converter = None
    if selection.engine == "marker":
        from sami.engines.marker import build_converter
        try:
            with contextlib.redirect_stdout(sys.stderr if args.json else sys.stdout):
                converter = build_converter(
                    selection.profile,
                    cpu_config=cpu_config,
                    logger=log,
                    stage_logger=_marker_stage_logger,
                    stage_done_logger=_marker_stage_done,
                    app_home=app_home,
                    runtime=runtime,
                )
            if (
                mode == "quality" and os.environ.get("SURYA_INFERENCE_BACKEND") == "llamacpp"
                and not os.environ.get("SURYA_INFERENCE_URL")
            ):
                effective_device = "cuda" if converter.sami_vlm_cuda else "cpu"
        except (Exception, SystemExit) as exc:
            runtime.close()
            failed: list[JobResult] = []
            for pdf in pdfs:
                job_id = uuid.uuid4().hex
                emit("job_started", {
                    "input": str(pdf), "engine": selection.engine,
                    "device": effective_device,
                }, job_id=job_id, attempt=1)
                result = JobResult(
                    job_id=job_id,
                    input_path=pdf,
                    mode=mode,
                    engine=selection.engine,
                    device=effective_device,
                    status="failed",
                    errors=({
                        "code": "ENGINE_INITIALIZATION_ERROR",
                        "message": str(exc),
                    },),
                    duration_seconds=0,
                )
                failed.append(result)
                emit("job_finished", {"result": result.to_wire()}, job_id=job_id, attempt=1)
            code = 2 if isinstance(exc, SystemExit) else 1
            run = RunResult(run_id=run_id, results=tuple(failed), exit_code=code)
            emit("run_finished", {
                "totals": run.totals, "duration_seconds": 0, "exit_code": code,
            })
            return code

    results: list[JobResult] = []
    # Track the active job so KeyboardInterrupt can emit a terminal event.
    _active_job_id: str | None = None
    _active_job_started: float | None = None
    _claimed_stems: set[str] = set()

    try:
        for i, pdf in enumerate(pdfs, 1):
            job_id = uuid.uuid4().hex
            _active_job_id = job_id
            _active_job_started = None
            if len(pdfs) > 1:
                log(f"\n[{i}/{len(pdfs)}]")
            out_dir = Path(args.output).resolve() if args.output else pdf.parent
            started = time.monotonic()
            _active_job_started = started
            staging: Path | None = None
            emit("job_started", {
                "input": str(pdf), "index": i, "total": len(pdfs),
                "engine": selection.engine, "device": effective_device,
            }, job_id=job_id, attempt=1)

            def stage_progress(_name: str, stage: str, **_kwargs) -> None:
                emit("job_progress", {
                    "stage": stage.strip(), "completed": None, "total": None,
                }, job_id=job_id, attempt=1)

            def stage_done(_elapsed: float) -> None:
                log_stage_done(_elapsed)

            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                # Reserve output identity before staging so another concurrent
                # sami process doesn't claim the same stem.
                stem = reserve_stem(pdf, out_dir, args.flat, claimed=_claimed_stems)
                staging = make_staging_dir(out_dir, stem)
                request = ConversionRequest(
                    job_id=job_id,
                    input_path=pdf,
                    mode=mode,
                    options=ConversionOptions(),
                    staging_dir=staging,
                    device=effective_device,
                    attempt=1,
                )
                _ACTIVE_PROGRESS_CALLBACK = lambda stage: stage_progress(pdf.name, stage)
                with contextlib.redirect_stdout(sys.stderr if args.json else sys.stdout):
                    engine_result = convert_engine(
                        request,
                        cpu_config=cpu_config if selection.engine == "marker" else None,
                        logger=log if selection.engine == "marker" else None,
                        stage_logger=stage_progress if selection.engine == "marker" else None,
                        stage_done_logger=stage_done if selection.engine == "marker" else None,
                        converter=converter,
                        app_home=app_home,
                    )
                # Write markdown with sami front-matter into staging.
                from sami import __version__ as _ver
                md_name = f"{stem}.md"
                markdown_with_fm = prepend_frontmatter(
                    engine_result.markdown, source=pdf, version=_ver
                )
                (staging / md_name).write_text(markdown_with_fm, encoding="utf-8")
                # Publish atomically.
                pub = publish(staging, stem, out_dir, args.flat)
                md_path: Path = pub["md_path"]
                resource_paths: list[Path] = pub["resource_paths"]
                staging = None  # published; don't remove in finally
                status = "partial" if engine_result.gaps else "succeeded"
                result = JobResult(
                    job_id=job_id,
                    input_path=pdf,
                    mode=mode,
                    engine=selection.engine,
                    device=effective_device,
                    status=status,
                    output_paths=(md_path, *resource_paths),
                    warnings=engine_result.warnings,
                    duration_seconds=time.monotonic() - started,
                    attempts=1,
                )
                for warning in engine_result.warnings:
                    emit("warning", warning, job_id=job_id, attempt=1)
                results.append(result)
                emit("job_finished", {"result": result.to_wire()}, job_id=job_id, attempt=1)
                log(f"  [{pdf.name}] Done: {engine_result.processed_pages} pages → {md_path}")
            except Exception as exc:
                print(f"FAILED: {pdf.name}: {exc}", file=sys.stderr)
                result = JobResult(
                    job_id=job_id,
                    input_path=pdf,
                    mode=mode,
                    engine=selection.engine,
                    device=effective_device,
                    status="failed",
                    errors=({"code": getattr(exc, "code", "CONVERSION_ERROR"), "message": str(exc)},),
                    duration_seconds=time.monotonic() - started,
                )
                results.append(result)
                emit("job_finished", {"result": result.to_wire()}, job_id=job_id, attempt=1)
            finally:
                _ACTIVE_PROGRESS_CALLBACK = None
                _active_job_id = None
                if staging is not None:
                    shutil.rmtree(staging, ignore_errors=True)
    except KeyboardInterrupt:
        print("\n[cleanup] Interrupted by user", file=sys.stderr)
        # Emit a cancelled terminal event for the job that was interrupted
        # so JSONL consumers always get a terminal event per job.
        if _active_job_id is not None:
            cancelled_result = JobResult(
                job_id=_active_job_id,
                input_path=pdfs[len(results)],
                mode=mode,
                engine=selection.engine,
                device=effective_device,
                status="cancelled",
                duration_seconds=time.monotonic() - (_active_job_started or total_t0),
            )
            results.append(cancelled_result)
            emit("job_finished", {"result": cancelled_result.to_wire()},
                 job_id=_active_job_id, attempt=1)
        exit_code = 130
    finally:
        runtime.close()

    total_elapsed = time.monotonic() - total_t0
    if 'exit_code' not in locals():
        exit_code = 1 if any(result.status == "failed" for result in results) else 0
    run_result = RunResult(run_id=run_id, results=tuple(results), exit_code=exit_code)
    emit("run_finished", {
        "totals": run_result.totals,
        "duration_seconds": total_elapsed,
        "exit_code": exit_code,
    })
    log(f"\n{'=' * 60}")
    log(f"  Summary: {run_result.totals['succeeded'] + run_result.totals['partial']} converted, "
        f"{run_result.totals['failed']} failed")
    log(f"  Total time: {total_elapsed:.1f}s")
    log(f"{'=' * 60}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
