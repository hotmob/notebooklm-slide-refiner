"""Prefect flow orchestration."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import anyio
import fitz
from prefect import flow, task
from prefect.tasks import exponential_backoff

from notebooklm_slide_refiner.assemble import assemble_pptx
from notebooklm_slide_refiner.manifest import ManifestEntry, ManifestWriter
from notebooklm_slide_refiner.render import render_pdf_page
from notebooklm_slide_refiner.utils import Resolution, parse_pages

LOGGER = logging.getLogger("notebooklm_slide_refiner.flow")


@dataclass(frozen=True)
class RenderOutcome:
    page_index: int
    raw_path: Path
    duration_ms: int
    status: str


@dataclass(frozen=True)
class RefineOutcome:
    page_index: int
    enhanced_path: Path | None
    output_path: Path
    duration_ms: int
    status: str
    error: str | None


@dataclass(frozen=True)
class FlowOutcome:
    failures: list[int]
    pptx_path: Path | None


class TokenBucket:
    def __init__(self, rate: float) -> None:
        self.rate = rate
        self.capacity = max(1.0, rate)
        self.tokens = self.capacity
        self.updated_at = time.monotonic()
        self._lock = anyio.Lock()

    async def acquire(self) -> None:
        if self.rate <= 0:
            return
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self.updated_at
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.updated_at = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                wait_time = (1 - self.tokens) / self.rate
            await anyio.sleep(wait_time)


@task(name="render_page_task")
def render_page_task(
    pdf_path: Path,
    page_index: int,
    raw_path: Path,
    dpi: int,
    resolution: Resolution,
    background: str,
) -> tuple[Path, int]:
    """Render a single PDF page into a raw PNG."""

    start = time.monotonic()
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    image = render_pdf_page(
        pdf_path=pdf_path,
        page_index=page_index,
        dpi=dpi,
        resolution=resolution,
        background=background,
    )
    image.save(raw_path, format="PNG")
    duration_ms = int((time.monotonic() - start) * 1000)
    return raw_path, duration_ms


@task(
    name="refine_page_task",
    retries=5,
    retry_delay_seconds=exponential_backoff(backoff_factor=2),
)
def refine_page_task(
    raw_path: Path,
    enhanced_path: Path,
    prompt: str,
    project: str,
    location: str,
) -> tuple[Path, int]:
    """Refine a raw PNG into an enhanced PNG via Vertex."""

    start = time.monotonic()
    try:
        from notebooklm_slide_refiner.vertex_refine import (
            VertexConfig,
            VertexRefineError,
            is_retryable_error,
            refine_with_vertex,
        )

        refine_with_vertex(
            raw_path=raw_path,
            enhanced_path=enhanced_path,
            prompt=prompt,
            config=VertexConfig(project=project, location=location),
        )
    except VertexRefineError as exc:
        if not is_retryable_error(exc):
            raise
        raise
    duration_ms = int((time.monotonic() - start) * 1000)
    return enhanced_path, duration_ms


@task(name="assemble_ppt_task")
def assemble_ppt_task(
    image_paths: list[Path],
    pptx_path: Path,
    resolution: Resolution,
) -> Path:
    """Assemble PPTX from image paths."""

    assemble_pptx(image_paths, pptx_path, resolution)
    return pptx_path


@flow(name="build_deck_flow")
async def build_deck_flow(
    input_pdf: Path,
    out_dir: Path,
    resolution: Resolution,
    dpi: int = 200,
    concurrency: int = 5,
    rps: float = 2.0,
    skip_refine: bool = False,
    pages: str | None = None,
    remove_corner_marks: bool = True,
    background: str = "black",
    allow_partial: bool = False,
) -> FlowOutcome:
    """Render PDF pages, optionally refine images, and assemble PPTX."""

    if not input_pdf.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_pdf}")

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "pages" / "raw"
    enhanced_dir = out_dir / "pages" / "enhanced"
    manifest_path = out_dir / "manifest.jsonl"

    with fitz.open(input_pdf) as doc:
        total_pages = doc.page_count

    page_indices = parse_pages(pages, total_pages)
    if not page_indices:
        raise ValueError("No pages selected for processing.")

    manifest = ManifestWriter(manifest_path)

    render_outcomes: list[RenderOutcome] = []
    render_failures: dict[int, str] = {}

    for page_index in page_indices:
        raw_path = raw_dir / f"page_{page_index + 1:04d}.png"
        if raw_path.exists():
            render_outcomes.append(
                RenderOutcome(
                    page_index=page_index,
                    raw_path=raw_path,
                    duration_ms=0,
                    status="skipped_render",
                )
            )
            continue
        try:
            rendered_path, duration_ms = render_page_task(
                pdf_path=input_pdf,
                page_index=page_index,
                raw_path=raw_path,
                dpi=dpi,
                resolution=resolution,
                background=background,
            )
            render_outcomes.append(
                RenderOutcome(
                    page_index=page_index,
                    raw_path=rendered_path,
                    duration_ms=duration_ms,
                    status="rendered",
                )
            )
        except Exception as exc:  # noqa: BLE001
            render_failures[page_index] = str(exc)
            render_outcomes.append(
                RenderOutcome(
                    page_index=page_index,
                    raw_path=raw_path,
                    duration_ms=0,
                    status="failed",
                )
            )

    render_map = {outcome.page_index: outcome for outcome in render_outcomes}

    refine_outcomes: list[RefineOutcome] = []
    failures: list[int] = [idx for idx in render_failures]

    if skip_refine:
        for outcome in render_outcomes:
            if outcome.page_index in render_failures:
                refine_outcomes.append(
                    RefineOutcome(
                        page_index=outcome.page_index,
                        enhanced_path=None,
                        output_path=outcome.raw_path,
                        duration_ms=0,
                        status="failed",
                        error=render_failures[outcome.page_index],
                    )
                )
                continue
            refine_outcomes.append(
                RefineOutcome(
                    page_index=outcome.page_index,
                    enhanced_path=None,
                    output_path=outcome.raw_path,
                    duration_ms=0,
                    status="skip_refine",
                    error=None,
                )
            )
    else:
        from notebooklm_slide_refiner.vertex_refine import build_vertex_config, load_prompt

        vertex_config = build_vertex_config()
        prompt = load_prompt(remove_corner_marks=remove_corner_marks)
        semaphore = anyio.Semaphore(max(concurrency, 1))
        rate_limiter = TokenBucket(rps)
        send_channel, receive_channel = anyio.create_memory_object_stream[RefineOutcome](
            len(page_indices)
        )

        async def refine_one(page_index: int, raw_path: Path) -> None:
            enhanced_path = enhanced_dir / f"page_{page_index + 1:04d}.png"
            if enhanced_path.exists():
                outcome = RefineOutcome(
                    page_index=page_index,
                    enhanced_path=enhanced_path,
                    output_path=enhanced_path,
                    duration_ms=0,
                    status="skipped_refine",
                    error=None,
                )
                await send_channel.send(outcome)
                return

            start = time.monotonic()
            try:
                async with semaphore:
                    await rate_limiter.acquire()
                    refined_path, _duration_ms = refine_page_task(
                        raw_path=raw_path,
                        enhanced_path=enhanced_path,
                        prompt=prompt,
                        project=vertex_config.project,
                        location=vertex_config.location,
                    )
                duration_ms = int((time.monotonic() - start) * 1000)
                outcome = RefineOutcome(
                    page_index=page_index,
                    enhanced_path=refined_path,
                    output_path=refined_path,
                    duration_ms=duration_ms,
                    status="refined",
                    error=None,
                )
            except Exception as exc:  # noqa: BLE001
                duration_ms = int((time.monotonic() - start) * 1000)
                outcome = RefineOutcome(
                    page_index=page_index,
                    enhanced_path=None,
                    output_path=raw_path,
                    duration_ms=duration_ms,
                    status="failed",
                    error=str(exc),
                )
            await send_channel.send(outcome)

        async with anyio.create_task_group() as tg:
            for outcome in render_outcomes:
                if outcome.page_index in render_failures:
                    continue
                tg.start_soon(refine_one, outcome.page_index, outcome.raw_path)

        await send_channel.aclose()
        async with receive_channel:
            async for outcome in receive_channel:
                refine_outcomes.append(outcome)

        for outcome in refine_outcomes:
            if outcome.status == "failed":
                failures.append(outcome.page_index)

    refine_map = {outcome.page_index: outcome for outcome in refine_outcomes}

    image_paths: list[Path] = []
    for page_index in page_indices:
        render_outcome = render_map[page_index]
        refine_outcome = refine_map.get(page_index)
        if not refine_outcome:
            refine_outcome = RefineOutcome(
                page_index=page_index,
                enhanced_path=None,
                output_path=render_outcome.raw_path,
                duration_ms=0,
                status="failed",
                error=render_failures.get(page_index, "Unknown error"),
            )
        status = refine_outcome.status
        duration_ms = render_outcome.duration_ms + refine_outcome.duration_ms
        error = refine_outcome.error or render_failures.get(page_index)
        enhanced_path = (
            str(refine_outcome.enhanced_path) if refine_outcome.enhanced_path else None
        )
        manifest.append(
            ManifestEntry(
                page_index=page_index,
                raw_path=str(render_outcome.raw_path),
                enhanced_path=enhanced_path,
                status=status,
                duration_ms=duration_ms,
                error=error,
            )
        )
        if status != "failed":
            image_paths.append(refine_outcome.output_path)

    pptx_path = out_dir / "deck.pptx"
    pptx_output: Path | None = None
    if image_paths:
        pptx_output = assemble_ppt_task(
            image_paths=image_paths, pptx_path=pptx_path, resolution=resolution
        )
    else:
        LOGGER.error("No images available to assemble PPTX.")

    failure_pages = sorted({page + 1 for page in failures})
    if failure_pages:
        LOGGER.error("Failures on pages: %s", failure_pages)
        if not allow_partial:
            return FlowOutcome(failures=failure_pages, pptx_path=pptx_output)

    return FlowOutcome(failures=failure_pages, pptx_path=pptx_output)
