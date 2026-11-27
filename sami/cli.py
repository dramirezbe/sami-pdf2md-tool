#!/usr/bin/env python3
"""sami — Smart Automated Markdown Interpreter.

Convert PDF files to Markdown with figures extracted.
Converts PDFs locally with the fast or Marker engines.

For each input PDF, creates a folder with the same stem containing:
  - <stem>.md  (text + LaTeX equations + Markdown tables)
  - figure images referenced by the Markdown

Usage:
    sami paper.pdf                     # -> paper/paper.md + figures
    sami paper.pdf -o out/             # -> out/paper/paper.md + figures
    sami a.pdf b.pdf                   # batch convert
    sami paper.pdf --mode fast         # fast mode
    sami paper.pdf --mode quality      # Marker with VLM layout
    sami paper.pdf --json              # protocol 1 JSONL on stdout
    sami paper.pdf --flat              # no subfolder, output beside the PDF
    sami paper.pdf -q                  # quiet mode, minimal output

Exit codes: 0 success, 1 incomplete batch, 2 usage error, 130 cancelled.
"""
from __future__ import annotations

import argparse
import contextlib
import io
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
    AccelerationError,
    ConversionOptions,
    ConversionRequest,
    JobResult,
    RunResult,
    REQUESTED_DEVICES,
)
from sami.events import EventSequencer, write_json_line
from sami.outputs import claim_stem, make_staging_dir, prepend_frontmatter, publish

VALID_MODES = ("fast", "balanced", "quality")


# ---------------------------------------------------------------------------
# App home directory: ~/.sami/
# ---------------------------------------------------------------------------

def ensure_app_home() -> Path:
    """Create and return the sami home directory (~/.sami/)."""
    app_home = Path(os.environ.get("SAMI_HOME", Path.home() / ".sami")).expanduser().resolve()
    app_home.mkdir(parents=True, exist_ok=True)
    for name in ("cache", "config", "logs", "bin"):
        (app_home / name).mkdir(exist_ok=True)
    os.environ.setdefault("HF_HOME", str(app_home / "cache" / "huggingface"))
    os.environ.setdefault("TORCH_HOME", str(app_home / "cache" / "torch"))
    return app_home


def _install_signal_handlers(control) -> None:
    """Route terminal interruption and GUI cancellation through the same state."""
    signal.signal(signal.SIGTERM, control.signal)
    signal.signal(signal.SIGINT, control.signal)


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
    from sami.diagnostics import management_command

    return management_command("health", argv)


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
    global _QUIET, _JSON_MODE
    from sami import __version__

    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] == "health":
        return _health_command(raw_argv[1:])
    if raw_argv and raw_argv[0] == "upgrade":
        from sami.upgrade import upgrade_command

        return upgrade_command(raw_argv[1:])
    if raw_argv and raw_argv[0] in ("doctor", "setup"):
        from sami.diagnostics import management_command

        return management_command(raw_argv[0], raw_argv[1:])
    if raw_argv and raw_argv[0] == "convert":
        raw_argv.pop(0)

    parser = argparse.ArgumentParser(
        prog="sami",
        description="Convert PDFs and folders to Markdown with extracted figures.",
        epilog="Commands: convert, health, doctor, setup, upgrade.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("pdf", nargs="+", metavar="INPUT", help="PDF file(s) or folders")
    parser.add_argument("-o", "--output", metavar="DIR", help="output directory (default: beside each PDF)")
    parser.add_argument("--mode", choices=VALID_MODES, default="balanced")
    parser.add_argument("--device", choices=REQUESTED_DEVICES, default="auto")
    parser.add_argument("--recursive", action="store_true", help="include PDF files in subfolders")
    parser.add_argument("--no-strip-refs", action="store_true", help="compatibility option; references are preserved")
    parser.add_argument("--flat", action="store_true", help="write directly to the output directory")
    parser.add_argument("-q", "--quiet", action="store_true", help="minimal output")
    parser.add_argument("--json", action="store_true", help="emit protocol 1 JSON Lines on stdout")
    parser.add_argument("--control-stdin", action="store_true", help="accept protocol 1 cancellation commands on stdin")
    options_end = raw_argv.index("--") if "--" in raw_argv else len(raw_argv)
    if "--json" in raw_argv[:options_end]:
        parser_stderr = io.StringIO()
        try:
            with contextlib.redirect_stderr(parser_stderr):
                args = parser.parse_args(raw_argv)
        except SystemExit as exc:
            if exc.code != 2:
                raise
            detail = parser_stderr.getvalue()
            print(detail, end="", file=sys.stderr)
            run_id = uuid.uuid4().hex
            result = RunResult(run_id=run_id, results=(), exit_code=2)
            event = EventSequencer(run_id).create("run_finished", {
                "totals": result.totals, "duration_seconds": 0, "exit_code": 2,
                "input_issue_count": 0, "error": {"code": "INVALID_ARGUMENTS", "message": detail.strip()},
            })
            write_json_line(sys.stdout, event.to_json_line())
            return 2
    else:
        args = parser.parse_args(raw_argv)
    _QUIET = args.quiet
    _JSON_MODE = args.json

    from sami.control import RunControl
    from sami.inputs import discover_inputs

    run_id = uuid.uuid4().hex
    sequencer = EventSequencer(run_id)
    control = RunControl(run_id)
    event_stdout = sys.stdout
    start = time.monotonic()
    pdfs, issues = discover_inputs(args.pdf, recursive=args.recursive)

    def emit(event: str, data: dict, *, job_id: str | None = None, attempt: int | None = None) -> None:
        if args.json:
            write_json_line(
                event_stdout,
                sequencer.create(event, data, job_id=job_id, attempt=attempt).to_json_line(),
            )

    def finish(results, exit_code: int) -> int:
        run = RunResult(run_id=run_id, results=tuple(results), exit_code=exit_code)
        elapsed = time.monotonic() - start
        emit("run_finished", {
            "totals": run.totals, "duration_seconds": elapsed, "exit_code": exit_code,
            "input_issue_count": len(issues),
        })
        log(f"Summary: {run.totals['succeeded']} converted, {run.totals['partial']} partial, "
            f"{run.totals['failed']} failed, {run.totals['cancelled']} cancelled ({elapsed:.1f}s)")
        return exit_code

    emit("run_started", {
        "mode": args.mode, "default_mode": "balanced", "version": __version__,
        "requested_device": args.device,
    })
    emit("inputs_resolved", {"count": len(pdfs), "inputs": [str(pdf) for pdf in pdfs], "issues": issues})
    for issue in issues:
        print(f"{issue['path']}: {issue['message']}", file=sys.stderr)
    if not pdfs:
        return finish([], 2)

    for signum in (signal.SIGTERM, signal.SIGINT):
        runtime.callback(signal.signal, signum, signal.getsignal(signum))
    runtime.callback(control.close)
    _install_signal_handlers(control)
    jobs = [(pdf, uuid.uuid4().hex) for pdf in pdfs]
    results: list[JobResult] = []
    with contextlib.ExitStack() as engines, contextlib.ExitStack() as claims:
        try:
            if args.control_stdin:
                control.read_stdin()
            control.check()
            _convert_batch(args, jobs, results, control, engines, claims, emit)
            control.check()
        except KeyboardInterrupt:
            control.close()
            from sami.engines import select_engine

            print("\n[cleanup] Conversion cancelled.", file=sys.stderr)
            for pdf, job_id in jobs[len(results):]:
                active = control.active
                device, attempt, seconds = (
                    (active[1], active[2], time.monotonic() - active[3])
                    if active and job_id == active[0] else ("cpu", 0, 0.0)
                )
                result = JobResult(
                    job_id=job_id, input_path=pdf, mode=args.mode,
                    engine=select_engine(args.mode).engine, device=device, status="cancelled",
                    duration_seconds=seconds, attempts=max(attempt, 1),
                )
                results.append(result)
                emit("job_finished", {"result": result.to_wire(), "started": bool(attempt)},
                     job_id=job_id, attempt=max(attempt, 1))
            exit_code = 130
        except (Exception, SystemExit) as exc:
            control.close()
            from sami.engines import select_engine

            print(f"FAILED: {exc}", file=sys.stderr)
            for pdf, job_id in jobs[len(results):]:
                failure = JobResult(
                    job_id=job_id, input_path=pdf, mode=args.mode, device="cpu",
                    engine=select_engine(args.mode).engine, status="failed",
                    errors=({"code": "BATCH_INITIALIZATION_ERROR", "message": str(exc)},),
                )
                results.append(failure)
                emit("job_finished", {"result": failure.to_wire()}, job_id=job_id, attempt=1)
            exit_code = 1
        else:
            exit_code = int(bool(issues or any(r.status in ("failed", "partial") for r in results)))
        finally:
            control.close()
    return finish(results, exit_code)


@contextlib.contextmanager
def _cpu_environment():
    """Configure a CPU attempt while preserving the user's environment."""
    with contextlib.ExitStack() as restore:
        for key, value in {
            "TORCH_DEVICE": "cpu", "FAST_DETECTOR_DEVICE": "cpu", "LLAMA_CPP_NGL": "0",
            "SURYA_INFERENCE_BACKEND": "llamacpp", "LLAMA_CPP_NO_MMPROJ_OFFLOAD": "true",
            "SURYA_INFERENCE_URL": "", "FAST_LAYOUT_SERVER_URL": "", "OCR_ERROR_SERVER_URL": "",
            "LLAMA_CPP_EXTRA_ARGS": "",
        }.items():
            if key in os.environ:
                restore.callback(os.environ.__setitem__, key, os.environ[key])
            else:
                restore.callback(os.environ.pop, key, None)
            os.environ[key] = value
        yield


def _gpu_failure(exc: BaseException) -> bool:
    """Distinguish accelerator failures from bad PDFs and publication errors."""
    while exc is not None:
        if isinstance(exc, AccelerationError) or exc.__class__.__name__ == "OutOfMemoryError":
            return True
        if re.search(
            r"cuda error|cuda out of memory|cudaMalloc|CUDA_ERROR_|cublas_status_|"
            r"hip error|hip out of memory|hipMalloc|hipError|"
            r"GPU (?:out of memory|allocation failed)|(?:CUDA|HIP)\d.*(?:allocat|out of memory).*fail",
            str(exc), re.IGNORECASE,
        ):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def _convert_batch(args, jobs, results, control, engines, claims, emit):
    global _ACTIVE_PROGRESS_CALLBACK
    from sami import __version__
    from sami.engines import convert as convert_engine, select_engine

    selection = select_engine(args.mode)
    app_home = ensure_app_home()
    cpu_config = _configure_cpu()
    device = _effective_device(selection.engine, args.mode)
    requested = args.device
    force_cpu = requested == "cpu" or (
        requested in ("cuda", "rocm") and device != requested
        and not (args.mode == "quality" and requested == "cuda")
    )
    if force_cpu:
        device = "cpu"
    converter = None
    init_error = None
    log(f"sami: {len(jobs)} file(s) queued")

    for index, (pdf, job_id) in enumerate(jobs, 1):
        control.check()
        started = time.monotonic()
        control.active = (job_id, device, 1, started)
        emit("job_started", {
            "input": str(pdf), "index": index, "total": len(jobs),
            "engine": selection.engine, "device": device,
        }, job_id=job_id, attempt=1)
        warnings = []
        fallback_from = requested if requested in ("cuda", "rocm") and force_cpu else None

        def fallback_warning(previous, reason, attempt):
            warning = {
                "code": "GPU_FALLBACK_CPU", "message": reason,
                "previous_device": previous, "device": "cpu",
            }
            warnings.append(warning)
            emit("warning", warning, job_id=job_id, attempt=attempt)
            print(f"WARNING: {reason}", file=sys.stderr)

        if fallback_from:
            fallback_warning(fallback_from, f"{fallback_from} is unavailable in this mode. Using CPU.", 1)
        out_dir = Path(args.output).resolve() if args.output else pdf.parent
        stem = None

        for attempt in (1, 2):
            control.check()
            control.active = (job_id, device, attempt, started)
            staging = None
            initializing = False
            converting = False
            try:
                if init_error:
                    initializing = True
                    raise init_error

                def progress(stage):
                    control.check()
                    emit("job_progress", {"stage": stage.strip(), "completed": None, "total": None},
                         job_id=job_id, attempt=attempt)

                _ACTIVE_PROGRESS_CALLBACK = progress
                if selection.engine == "marker" and converter is None:
                    initializing = True
                    if force_cpu:
                        engines.enter_context(_cpu_environment())
                    from sami.engines.marker import build_converter

                    with contextlib.redirect_stdout(sys.stderr if args.json else sys.stdout):
                        converter = build_converter(
                            selection.profile, cpu_config=cpu_config, logger=log,
                            stage_logger=_marker_stage_logger, stage_done_logger=_marker_stage_done,
                            app_home=app_home, runtime=engines, cancel_event=control.cancelled,
                        )
                    if args.mode == "quality" and os.environ.get("SURYA_INFERENCE_BACKEND") == "llamacpp":
                        device = "cuda" if converter.sami_vlm_cuda else "cpu"
                    if not warnings and device == "cpu" and requested in ("cuda", "rocm"):
                        fallback_warning(requested, f"{requested} runtime is unavailable. Using CPU.", attempt)
                    initializing = False

                control.active = (job_id, device, attempt, started)
                out_dir.mkdir(parents=True, exist_ok=True)
                if stem is None:
                    with control.publishing():
                        stem = claims.enter_context(claim_stem(pdf, out_dir, args.flat))
                control.check()
                # A signal between creating the directory and binding it would orphan it.
                with control.publishing():
                    staging = make_staging_dir(out_dir, stem)
                control.check()
                request = ConversionRequest(
                    job_id=job_id, input_path=pdf, mode=args.mode,
                    options=ConversionOptions(device=requested), staging_dir=staging,
                    device=device, attempt=attempt,
                )
                converting = True
                with contextlib.redirect_stdout(sys.stderr if args.json else sys.stdout):
                    result = convert_engine(
                        request, cpu_config=cpu_config if selection.engine == "marker" else None,
                        logger=log if selection.engine == "marker" else None,
                        stage_logger=_marker_stage_logger if selection.engine == "marker" else None,
                        stage_done_logger=_marker_stage_done if selection.engine == "marker" else None,
                        converter=converter, app_home=app_home,
                    )
                converting = False
                control.check()
                for warning in (*result.warnings, *result.gaps):
                    warnings.append(warning)
                    emit("warning", warning, job_id=job_id, attempt=attempt)
                markdown = prepend_frontmatter(result.markdown, source=pdf, version=__version__)
                (staging / f"{stem}.md").write_text(markdown, encoding="utf-8")
                control.check()
                with control.publishing():
                    published = publish(staging, stem, out_dir, args.flat)
                    finished = JobResult(
                        job_id=job_id, input_path=pdf, mode=args.mode, engine=selection.engine,
                        device=device, status="partial" if result.gaps else "succeeded",
                        output_paths=(published["md_path"], *published["resource_paths"]),
                        warnings=tuple(warnings), duration_seconds=time.monotonic() - started, attempts=attempt,
                    )
                    results.append(finished)
                    emit("job_finished", {"result": finished.to_wire()}, job_id=job_id, attempt=attempt)
                log(f"  [{pdf.name}] Done: {result.processed_pages} pages → {published['md_path']}")
                break
            except (Exception, SystemExit) as exc:
                control.check()
                gpu = device if device != "cpu" else ("cuda" if getattr(converter, "sami_vlm_cuda", False) else "cpu")
                if (
                    (initializing or converting) and selection.engine == "marker" and not force_cpu
                    and (gpu != "cpu" or isinstance(exc, AccelerationError)) and _gpu_failure(exc)
                ):
                    if gpu == "cpu":
                        gpu = requested if requested in ("cuda", "rocm") else "cuda"
                    reason = f"{gpu} conversion failed. Retrying in CPU with the same mode. {exc}"
                    emit("job_retrying", {"previous_device": gpu, "device": "cpu", "reason": str(exc)},
                         job_id=job_id, attempt=attempt + 1)
                    fallback_warning(gpu, reason, attempt + 1)
                    engines.close()
                    converter = None
                    device, force_cpu = "cpu", True
                    continue
                if initializing:
                    init_error = exc
                    engines.close()
                    converter = None
                print(f"FAILED: {pdf.name}: {exc}", file=sys.stderr)
                code = "ENGINE_INITIALIZATION_ERROR" if initializing else "CONVERSION_ERROR"
                with control.publishing():
                    failed = JobResult(
                        job_id=job_id, input_path=pdf, mode=args.mode, engine=selection.engine,
                        device=device, status="failed", warnings=tuple(warnings),
                        errors=({"code": getattr(exc, "code", code), "message": str(exc)},),
                        duration_seconds=time.monotonic() - started, attempts=attempt,
                    )
                    results.append(failed)
                    emit("job_finished", {"result": failed.to_wire()}, job_id=job_id, attempt=attempt)
                break
            finally:
                _ACTIVE_PROGRESS_CALLBACK = None
                if staging is not None:
                    # A repeated interrupt must not cut the cleanup short.
                    with control.publishing():
                        shutil.rmtree(staging, ignore_errors=True)
    control.active = None


if __name__ == "__main__":
    raise SystemExit(main())
