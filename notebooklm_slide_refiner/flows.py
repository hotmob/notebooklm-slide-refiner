"""Prefect flow orchestration."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import fitz
from prefect import flow
from prefect.task_runners import ConcurrentTaskRunner

from notebooklm_slide_refiner.manifest import ManifestEntry, ManifestWriter
from notebooklm_slide_refiner.render import Resolution, parse_pages
from notebooklm_slide_refiner.tasks import assemble_ppt_task, refine_page_task, render_page_task

LOGGER = logging.getLogger("notebooklm_slide_refiner.flow")


@flow(name="build_deck_flow", task_runner=ConcurrentTaskRunner())
def build_deck_flow(
    input_pdf: Path,
    out_dir: Path,
    resolution: Resolution,
    dpi: int | None = None,
    concurrency: int = 5,
    rps: float = 2.0,
    skip_refine: bool = False,
    pages: str | None = None,
    remove_corner_marks: bool = True,
    keep_temp: bool = True,
) -> None:
    """Render PDF pages, optionally refine images, and assemble PPTX."""

    if not input_pdf.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_pdf}")

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "pages" / "raw"
    enhanced_dir = out_dir / "pages" / "enhanced"
    manifest_path = out_dir / "manifest.jsonl"
    rate_limit_path = out_dir / ".rate_limit"

    dpi_value = dpi or 200

    with fitz.open(input_pdf) as doc:
        total_pages = doc.page_count

    page_indices = list(parse_pages(pages, total_pages))
    if not page_indices:
        LOGGER.warning("No pages selected for processing.")
        return

    manifest = ManifestWriter(manifest_path)

    render_futures: dict[int, tuple[Path, int, str]] = {}
    for page_index in page_indices:
        raw_path = raw_dir / f"page_{page_index + 1:04d}.png"
        if raw_path.exists():
            render_futures[page_index] = (raw_path, 0, "skipped_render")
        else:
            future = render_page_task.submit(
                pdf_path=input_pdf,
                page_index=page_index,
                raw_path=raw_path,
                dpi=dpi_value,
                resolution=resolution,
                background_mode="black",
            )
            render_futures[page_index] = (future, 0, "rendered")  # type: ignore[assignment]

    render_results: dict[int, tuple[Path, int, str]] = {}
    for page_index, result in render_futures.items():
        if isinstance(result[0], Path):
            render_results[page_index] = result
        else:
            future = result[0]
            raw_path, duration_ms = future.result()
            render_results[page_index] = (raw_path, duration_ms, "rendered")

    refine_futures: dict[int, tuple[Path, int, str]] = {}
    if skip_refine:
        for page_index in page_indices:
            raw_path, _render_duration, _render_status = render_results[page_index]
            refine_futures[page_index] = (raw_path, 0, "skip_refine")
    else:
        for page_index in page_indices:
            raw_path, render_duration, _render_status = render_results[page_index]
            enhanced_path = enhanced_dir / f"page_{page_index + 1:04d}.png"
            if enhanced_path.exists():
                refine_futures[page_index] = (enhanced_path, 0, "skipped_refine")
                continue
            refine_futures[page_index] = (raw_path, render_duration, "pending")

        pending_pages = [p for p, data in refine_futures.items() if data[2] == "pending"]
        for i in range(0, len(pending_pages), max(concurrency, 1)):
            batch = pending_pages[i : i + max(concurrency, 1)]
            batch_futures = {}
            for page_index in batch:
                raw_path, render_duration, _status = render_results[page_index]
                enhanced_path = enhanced_dir / f"page_{page_index + 1:04d}.png"
                future = refine_page_task.submit(
                    raw_path=raw_path,
                    enhanced_path=enhanced_path,
                    remove_corner_marks=remove_corner_marks,
                    rps=rps,
                    rate_limit_path=rate_limit_path,
                )
                batch_futures[page_index] = (future, render_duration)
            for page_index, (future, render_duration) in batch_futures.items():
                enhanced_path, refine_duration = future.result()
                refine_futures[page_index] = (enhanced_path, refine_duration, "refined")

    failures: list[ManifestEntry] = []
    image_paths: list[Path] = []

    for page_index in page_indices:
        raw_path, render_duration, _render_status = render_results[page_index]
        start_time = time.monotonic()
        try:
            result = refine_futures[page_index]
            if isinstance(result[0], Path):
                enhanced_path = result[0]
                refine_duration = result[1]
                status = result[2]
            duration_ms = render_duration + refine_duration
            entry = ManifestEntry(
                page_index=page_index,
                raw_path=str(raw_path),
                enhanced_path=str(enhanced_path) if not skip_refine else None,
                status=status,
                duration_ms=duration_ms,
                error=None,
            )
            manifest.append(entry)
            image_paths.append(enhanced_path)
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((time.monotonic() - start_time) * 1000)
            entry = ManifestEntry(
                page_index=page_index,
                raw_path=str(raw_path),
                enhanced_path=None,
                status="failed",
                duration_ms=duration_ms,
                error=str(exc),
            )
            manifest.append(entry)
            failures.append(entry)

    if failures:
        LOGGER.error("Refine failures: %s", [f.page_index + 1 for f in failures])

    if not image_paths:
        LOGGER.error("No images available to assemble PPTX.")
        return

    if skip_refine:
        image_paths = [render_results[i][0] for i in page_indices]

    pptx_path = out_dir / "deck.pptx"
    assemble_ppt_task(image_paths=image_paths, pptx_path=pptx_path, resolution=resolution)

    if not keep_temp:
        for path in raw_dir.glob("*.png"):
            path.unlink(missing_ok=True)
        for path in enhanced_dir.glob("*.png"):
            path.unlink(missing_ok=True)
