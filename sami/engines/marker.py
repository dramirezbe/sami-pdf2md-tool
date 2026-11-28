"""Marker adapter with Torch layout and local llama.cpp inference."""
from __future__ import annotations

import os
import sys
import time
from contextlib import ExitStack
from pathlib import Path

from sami.contracts import ConversionRequest, EngineResult

_VLM_SETTINGS = (
    "LLAMA_CPP_BINARY", "LLAMA_CPP_NGL", "LLAMA_CPP_NO_MMPROJ_OFFLOAD",
    "LLAMA_CPP_EXTRA_ARGS", "SURYA_INFERENCE_PARALLEL",
    "SURYA_GGUF_LOCAL_MODEL_PATH", "SURYA_GGUF_LOCAL_MMPROJ_PATH",
    "TORCH_DEVICE", "FAST_DETECTOR_DEVICE", "SURYA_INFERENCE_URL",
    "FAST_LAYOUT_SERVER_URL", "OCR_ERROR_SERVER_URL",
)


def _count_blocks_by_type(document) -> dict[str, int]:
    """Count blocks per type across all pages after layout."""
    from collections import Counter
    counts = Counter()
    for page in document.pages:
        for block in page.children or []:
            counts[str(block.block_type).split(".")[-1]] += 1
    return dict(counts)


def _count_blocks_for_processor(document, processor) -> tuple[int, int]:
    """Count (pages_with_blocks, total_blocks) that a processor will touch."""
    block_types = getattr(processor, "block_types", None)
    if not block_types:
        return 0, 0
    pages_with = 0
    total = 0
    for page in document.pages:
        page_blocks = page.contained_blocks(document, block_types)
        if page_blocks:
            pages_with += 1
            total += len(page_blocks)
    return pages_with, total


def _make_verbose_converter_cls(stage_logger, stage_done_logger):
    from marker.converters.pdf import PdfConverter
    from marker.builders.document import DocumentBuilder
    from marker.builders.layout import LayoutBuilder
    from marker.builders.line import LineBuilder
    from marker.builders.ocr import OcrBuilder
    from marker.builders.structure import StructureBuilder
    from marker.providers.registry import provider_from_filepath

    class VerboseConverter(PdfConverter):
        def __call__(self, filepath, pdf_name: str = ""):
            self._pdf_name = pdf_name or Path(filepath).name
            self._convert_t0 = time.monotonic()
            with self.filepath_to_str(filepath) as temp_path:
                document = self.build_document(temp_path)
                self.page_count = len(document.pages)

                t0 = time.monotonic()
                stage_logger(self._pdf_name, f"Rendering markdown ({self.page_count} pages)...", end="", flush=True)
                renderer = self.resolve_dependencies(self.renderer)
                rendered = renderer(document)
                stage_done_logger(time.monotonic() - t0)

            return rendered

        def build_document(self, filepath):
            name = self._pdf_name
            pipeline_t0 = time.monotonic()

            # Provider
            t0 = time.monotonic()
            stage_logger(name, "Reading PDF pages...", end="", flush=True)
            provider_cls = provider_from_filepath(filepath)
            provider = provider_cls(filepath, self.config)
            stage_done_logger(time.monotonic() - t0)

            n_pages = len(provider.page_range) if hasattr(provider, 'page_range') else 0
            stage_logger(name, f"  Pages: {n_pages}")

            # DocumentBuilder — we replicate its __call__ to log between stages
            doc_builder = self.resolve_dependencies(DocumentBuilder)

            t0 = time.monotonic()
            stage_logger(name, f"Building page structure ({n_pages} pages)...", end="", flush=True)
            document = doc_builder.build_document(provider)
            stage_done_logger(time.monotonic() - t0)

            # Layout
            t0 = time.monotonic()
            layout_builder = self.resolve_dependencies(LayoutBuilder)
            use_fast = getattr(layout_builder, 'use_fast_layout', lambda: False)()
            mode_label = "fast/rf-detr" if use_fast else "VLM"
            stage_logger(name, f"Layout detection ({mode_label}, {n_pages} pages)...", end="", flush=True)
            layout_builder(document, provider)
            stage_done_logger(time.monotonic() - t0)

            # Layout summary
            block_counts = _count_blocks_by_type(document)
            total_blocks = sum(block_counts.values())
            summary_parts = [f"{v} {k}" for k, v in sorted(block_counts.items(), key=lambda x: -x[1])[:6]]
            stage_logger(name, f"  Layout found {total_blocks} blocks: {', '.join(summary_parts)}")

            # Lines
            t0 = time.monotonic()
            line_builder = self.resolve_dependencies(LineBuilder)
            stage_logger(name, f"Line extraction ({n_pages} pages)...", end="", flush=True)
            line_builder(document, provider)
            stage_done_logger(time.monotonic() - t0)

            # Per-page OCR method summary
            ocr_pages = [p for p in document.pages if p.text_extraction_method == "surya"]
            text_pages = [p for p in document.pages if p.text_extraction_method != "surya"]
            stage_logger(name, f"  Text layer: {len(text_pages)} pages, needs OCR: {len(ocr_pages)} pages")

            # High-res rendering
            from marker.schema import BlockTypes
            highres_types = getattr(doc_builder, 'highres_block_types', None)
            if highres_types:
                need_highres = sum(
                    1 for page in document.pages
                    if any(block.block_type in highres_types for block in (page.children or []))
                )
            else:
                need_highres = n_pages
            t0 = time.monotonic()
            stage_logger(name, f"High-res page rendering ({need_highres} pages)...", end="", flush=True)
            doc_builder.render_highres(document, provider)
            stage_done_logger(time.monotonic() - t0)

            # OCR
            t0 = time.monotonic()
            if ocr_pages:
                stage_logger(name, f"OCR ({len(ocr_pages)}/{n_pages} pages need it)...", end="", flush=True)
            else:
                stage_logger(name, "OCR (skipped, all pages have text)...", end="", flush=True)
            ocr_builder = self.resolve_dependencies(OcrBuilder)
            ocr_builder(document, provider)
            stage_done_logger(time.monotonic() - t0)

            # Structure
            t0 = time.monotonic()
            stage_logger(name, "Structure building...", end="", flush=True)
            structure_builder = self.resolve_dependencies(StructureBuilder)
            structure_builder(document)
            stage_done_logger(time.monotonic() - t0)

            # Processors
            n_procs = len(self.processor_list)
            for idx, processor in enumerate(self.processor_list, 1):
                proc_name = type(processor).__name__
                pages_with, block_count = _count_blocks_for_processor(document, processor)

                # Build info string
                if block_count > 0:
                    info = f"{block_count} blocks on {pages_with} pages"
                else:
                    info = ""

                progress = f"[{idx}/{n_procs}]"
                if info:
                    label = f"{progress} {proc_name} ({info})..."
                else:
                    label = f"{progress} {proc_name}..."

                t0 = time.monotonic()
                stage_logger(name, label, end="", flush=True)
                processor(document)
                elapsed = time.monotonic() - t0
                stage_done_logger(elapsed)

            pipeline_elapsed = time.monotonic() - pipeline_t0
            stage_logger(name, f"  Pipeline complete: {n_pages} pages, "
                      f"{total_blocks} blocks in {pipeline_elapsed:.1f}s")

            return document

    return VerboseConverter


def _locate_gguf_paths(app_home: Path | None) -> tuple[str | None, str | None]:
    """Locate surya GGUF and mmproj files in SAMI_HOME or the standard HF cache.

    Returns (gguf_path, mmproj_path); either may be None if not found.
    Env overrides SURYA_GGUF_LOCAL_MODEL_PATH / SURYA_GGUF_LOCAL_MMPROJ_PATH
    take priority so users can point to custom paths.
    """
    gguf = os.environ.get("SURYA_GGUF_LOCAL_MODEL_PATH")
    mmproj = os.environ.get("SURYA_GGUF_LOCAL_MMPROJ_PATH")
    if gguf and mmproj:
        return gguf, mmproj

    # Standard HF hub cache: models--datalab-to--surya-ocr-2-gguf
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".sami" / "cache" / "huggingface"))
    hub = Path(os.environ.get("HF_HUB_CACHE", hf_home / "hub")) / "models--datalab-to--surya-ocr-2-gguf"

    if app_home:
        candidates = [hub, app_home / "cache" / "huggingface" / "hub" / "models--datalab-to--surya-ocr-2-gguf"]
    else:
        candidates = [hub]

    for base in candidates:
        snapshots = base / "snapshots"
        try:
            candidates = sorted(snapshots.iterdir(), reverse=True)
        except OSError:
            continue
        for snap in candidates:
            g = snap / "surya-2.gguf"
            m = snap / "surya-2-mmproj.gguf"
            if g.is_file() and m.is_file():
                return str(g), str(m)

    return None, None


def _configure_vlm_backend(logger, app_home: Path | None) -> bool:
    """Choose the llama.cpp runtime and offload settings for this run."""
    backend = os.environ.setdefault("SURYA_INFERENCE_BACKEND", "llamacpp")
    if backend != "llamacpp" or os.environ.get("SURYA_INFERENCE_URL"):
        logger(f"VLM backend: {backend}")
        return False

    requested = os.environ.get("LLAMA_CPP_NGL")
    layers = int(requested) if requested is not None else None
    if layers is None and os.environ.get("TORCH_DEVICE", "").lower() == "cpu":
        layers = 0

    # None delegates layer placement to llama.cpp. The live VRAM measurement
    # then happens at model load, after any RF-DETR CUDA allocations.
    from sami.llama_runtime import ensure_server, supports_vram_fit

    home = app_home or Path(os.environ.get("SAMI_HOME", Path.home() / ".sami"))
    binary, use_cuda = ensure_server(home, want_cuda=layers != 0, logger=logger)
    if use_cuda and layers is None and not (binary and supports_vram_fit(binary)):
        logger("llama-server lacks automatic VRAM fitting. VLM will use CPU.")
        use_cuda = False

    ngl = (999 if layers < 0 else layers) if use_cuda and layers is not None else 0
    os.environ["LLAMA_CPP_NGL"] = str(ngl)
    extra = os.environ.get("LLAMA_CPP_EXTRA_ARGS", "")
    if use_cuda and layers is None:
        # Surya's setting only accepts integers. The last flag takes precedence.
        os.environ["LLAMA_CPP_EXTRA_ARGS"] = f"--n-gpu-layers auto --fit on {extra}".strip()
    elif not use_cuda:
        os.environ.setdefault("LLAMA_CPP_NO_MMPROJ_OFFLOAD", "true")
        os.environ["LLAMA_CPP_EXTRA_ARGS"] = f"--device none {extra}".strip()
    elif 0 < ngl <= 8:
        # Keep the vision encoder and KV cache on the host for 4 GiB GPUs.
        os.environ.setdefault("SURYA_INFERENCE_PARALLEL", "1")
        os.environ.setdefault("LLAMA_CPP_NO_MMPROJ_OFFLOAD", "true")
        os.environ["LLAMA_CPP_EXTRA_ARGS"] = f"--no-kv-offload {extra}".strip()

    gguf, mmproj = _locate_gguf_paths(app_home)
    if gguf and mmproj:
        os.environ.setdefault("SURYA_GGUF_LOCAL_MODEL_PATH", gguf)
        os.environ.setdefault("SURYA_GGUF_LOCAL_MMPROJ_PATH", mmproj)

    if use_cuda and layers is None:
        logger("VLM backend: local llama.cpp, CUDA (automatic layer fitting)")
    else:
        logger(f"VLM backend: local llama.cpp, {'CUDA' if use_cuda else 'CPU'} (-ngl {ngl})")
    return use_cuda


def build_converter(
    mode: str | None, *, cpu_config, logger, stage_logger, stage_done_logger,
    app_home: Path | None = None, runtime: ExitStack | None = None, cancel_event=None,
):
    """Construct a Marker PDF-to-Markdown converter."""
    from sami.hardware import describe_gpu, gpu_info

    if runtime is not None:
        for key in (*_VLM_SETTINGS, "SURYA_INFERENCE_BACKEND", "LD_LIBRARY_PATH"):
            if key in os.environ:
                runtime.callback(os.environ.__setitem__, key, os.environ[key])
            else:
                runtime.callback(os.environ.pop, key, None)

    try:
        from marker.models import create_model_dict
        from marker.config.parser import ConfigParser
        from surya.settings import settings
    except ImportError as exc:
        print(
            f"Marker is not available: {exc}\n"
            "Install with: pip install marker-pdf==2.0.0",
            file=sys.stderr,
        )
        sys.exit(2)

    logger(f"GPU: {describe_gpu(gpu_info())}")
    use_cuda = _configure_vlm_backend(logger, app_home)
    # Surya reads the environment at import time. Update the settings instance
    # that its backend uses before creating any predictors.
    for key in _VLM_SETTINGS:
        if key in os.environ:
            value = os.environ[key]
            if key in ("LLAMA_CPP_NGL", "SURYA_INFERENCE_PARALLEL"):
                value = int(value)
            elif key == "LLAMA_CPP_NO_MMPROJ_OFFLOAD":
                value = value.lower() in ("1", "true", "yes", "on")
            if runtime is not None:
                runtime.callback(setattr, settings, key, getattr(settings, key))
            setattr(settings, key, value)

    if runtime is not None:
        from sami.processes import managed_surya_servers
        runtime.enter_context(managed_surya_servers(cancel_event))

    import torch
    torch.set_num_threads(cpu_config["torch_threads"])

    cli: dict = {
        "output_format": "markdown",
        "pdftext_workers": cpu_config["pdftext_workers"],
    }
    if mode:
        cli["mode"] = mode
    config_parser = ConfigParser(cli)

    logger(f"CPU: {cpu_config['physical_cores']} physical cores, "
        f"using {cpu_config['target_threads']} threads (~90%)")
    logger("Loading Marker models...")
    t0 = time.monotonic()
    model_dict = create_model_dict(inference_backend=os.environ["SURYA_INFERENCE_BACKEND"])
    logger(f"Models loaded in {time.monotonic() - t0:.1f}s")
    logger(f"Mode: {mode or 'auto (RF-DETR)'}")

    VerboseConverter = _make_verbose_converter_cls(stage_logger, stage_done_logger)
    converter = VerboseConverter(
        config=config_parser.generate_config_dict(),
        artifact_dict=model_dict,
        processor_list=config_parser.get_processors(),
        renderer=config_parser.get_renderer(),
    )
    converter.sami_vlm_cuda = use_cuda
    return converter


# ---------------------------------------------------------------------------
# Figure writing
# ---------------------------------------------------------------------------

def write_figures(images: dict, folder: Path) -> int:
    count = 0
    for name, image in images.items():
        is_png = name.lower().endswith(".png")
        fmt = "PNG" if is_png else "JPEG"
        if fmt == "JPEG" and image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        image.save(folder / name, format=fmt)
        count += 1
    return count


def convert(
    request: ConversionRequest,
    *,
    marker_mode: str,
    cpu_config: dict,
    logger,
    stage_logger,
    stage_done_logger,
    converter=None,
    app_home: Path | None = None,
) -> EngineResult:
    """Run SAMI's original Marker pipeline into the request staging directory."""
    if marker_mode not in ("fast", "balanced"):
        raise ValueError(f"unsupported internal Marker mode: {marker_mode}")
    with ExitStack() as runtime:
        if converter is None:
            converter = build_converter(
                marker_mode,
                cpu_config=cpu_config,
                logger=logger,
                stage_logger=stage_logger,
                stage_done_logger=stage_done_logger,
                app_home=app_home,
                runtime=runtime,
            )
        from marker.output import text_from_rendered

        from sami.engines.pdftext_unicode import repair_pdftext_unicode

        with repair_pdftext_unicode():
            rendered = converter(str(request.input_path), pdf_name=request.input_path.name)
        markdown, _extension, images = text_from_rendered(rendered)
        request.staging_dir.mkdir(parents=True, exist_ok=True)
        write_figures(images, request.staging_dir)
        resources = tuple(
            sorted(path.relative_to(request.staging_dir) for path in request.staging_dir.rglob("*") if path.is_file())
        )
        return EngineResult(
            markdown=markdown,
            resources=resources,
            processed_pages=converter.page_count or 0,
            metrics={
                "engine": "marker",
                "marker_mode": marker_mode,
                "images": len(images),
            },
        )
