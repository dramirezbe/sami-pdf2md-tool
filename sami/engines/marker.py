"""Marker adapter retaining SAMI's existing conversion pipeline."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from sami.contracts import ConversionRequest, EngineResult

MIN_VRAM_GB_FOR_VLM = 8


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


def _gpu_vram_gb() -> float | None:
    """Return total VRAM in GiB for the default CUDA device, or None."""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
    except Exception:
        pass
    return None


def _resolve_mode(mode: str | None, logger) -> str | None:
    """Auto-select fast mode when GPU VRAM is too small for VLM."""
    if mode is not None:
        return mode
    vram = _gpu_vram_gb()
    if vram is not None and vram < MIN_VRAM_GB_FOR_VLM:
        logger(f"GPU VRAM: {vram:.1f} GB (< {MIN_VRAM_GB_FOR_VLM} GB minimum for VLM)")
        logger("Auto-selecting --mode fast (RF-DETR layout)")
        return "fast"
    return None


def build_converter(mode: str | None, *, cpu_config, logger, stage_logger, stage_done_logger):
    """Construct a Marker PDF->Markdown converter with verbose logging."""
    try:
        from marker.models import create_model_dict
        from marker.config.parser import ConfigParser
    except ImportError as exc:
        print(
            f"Marker is not available: {exc}\n"
            "Install with: pip install marker-pdf==2.0.0",
            file=sys.stderr,
        )
        sys.exit(2)

    import torch
    torch.set_num_threads(cpu_config["torch_threads"])

    mode = _resolve_mode(mode, logger)

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
    model_dict = create_model_dict()
    logger(f"Models loaded in {time.monotonic() - t0:.1f}s")
    logger(f"Mode: {mode or 'auto'}")

    VerboseConverter = _make_verbose_converter_cls(stage_logger, stage_done_logger)
    return VerboseConverter(
        config=config_parser.generate_config_dict(),
        artifact_dict=model_dict,
        processor_list=config_parser.get_processors(),
        renderer=config_parser.get_renderer(),
    )


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
) -> EngineResult:
    """Run SAMI's original Marker pipeline into the request staging directory."""
    from marker.output import text_from_rendered

    if marker_mode not in ("fast", "balanced"):
        raise ValueError(f"unsupported internal Marker mode: {marker_mode}")
    converter = build_converter(
        marker_mode,
        cpu_config=cpu_config,
        logger=logger,
        stage_logger=stage_logger,
        stage_done_logger=stage_done_logger,
    )
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
