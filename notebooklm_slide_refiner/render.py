"""PDF rendering utilities."""

from __future__ import annotations

from pathlib import Path

import fitz
from PIL import Image

from notebooklm_slide_refiner.utils import Resolution, letterbox_image


def render_pdf_page(
    pdf_path: Path,
    page_index: int,
    dpi: int,
    resolution: Resolution,
    background: str = "black",
) -> Image.Image:
    """Render a specific PDF page and letterbox to target resolution."""

    with fitz.open(pdf_path) as doc:
        page = doc.load_page(page_index)
        scale = dpi / 72
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return letterbox_image(image, resolution, background=background)
