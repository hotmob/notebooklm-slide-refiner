"""Prefect tasks for rendering, refining, and assembling slides."""

from __future__ import annotations

import time
from pathlib import Path

from prefect import get_run_logger, task

from notebooklm_slide_refiner.assemble import assemble_pptx
from notebooklm_slide_refiner.refine import (
    GeminiAPIError,
    backoff_sleep,
    get_refiner,
    is_retryable,
    load_prompt,
    rate_limit_wait,
)
from notebooklm_slide_refiner.render import Resolution, render_pdf_page


@task(name="render_page_task")
def render_page_task(
    pdf_path: Path,
    page_index: int,
    raw_path: Path,
    dpi: int,
    resolution: Resolution,
    background_mode: str,
) -> tuple[Path, int]:
    """Render a single PDF page into a raw PNG."""

    logger = get_run_logger()
    start = time.monotonic()
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    image = render_pdf_page(
        pdf_path=pdf_path,
        page_index=page_index,
        dpi=dpi,
        resolution=resolution,
        background_mode=background_mode,
    )
    image.save(raw_path, format="PNG")
    duration_ms = int((time.monotonic() - start) * 1000)
    logger.info("Rendered page %s to %s in %sms", page_index + 1, raw_path, duration_ms)
    return raw_path, duration_ms


@task(name="refine_page_task", retries=1, retry_delay_seconds=1)
def refine_page_task(
    raw_path: Path,
    enhanced_path: Path,
    remove_corner_marks: bool,
    rps: float,
    rate_limit_path: Path,
    max_attempts: int = 5,
) -> tuple[Path, int]:
    """Refine a raw PNG into an enhanced PNG."""

    logger = get_run_logger()
    prompt = load_prompt(remove_corner_marks=remove_corner_marks)
    refiner = get_refiner()

    start = time.monotonic()
    for attempt in range(max_attempts):
        try:
            rate_limit_wait(rate_limit_path, rps)
            refiner.refine(raw_path, enhanced_path, prompt)
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "Refined %s to %s in %sms", raw_path.name, enhanced_path, duration_ms
            )
            return enhanced_path, duration_ms
        except GeminiAPIError as exc:
            logger.warning("Gemini API error on attempt %s: %s", attempt + 1, exc)
            if attempt < max_attempts - 1 and is_retryable(exc.status_code):
                backoff_sleep(attempt + 1)
                continue
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Refine failed on attempt %s: %s", attempt + 1, exc)
            if attempt < max_attempts - 1:
                backoff_sleep(attempt + 1)
                continue
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

    logger = get_run_logger()
    assemble_pptx(image_paths, pptx_path, resolution)
    logger.info("Assembled PPTX at %s", pptx_path)
    return pptx_path
