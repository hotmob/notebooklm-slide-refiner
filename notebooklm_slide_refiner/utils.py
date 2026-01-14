"""Shared utilities for parsing and image padding."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class Resolution:
    """Pixel resolution container."""

    width: int
    height: int


def parse_resolution(value: str) -> Resolution:
    """Parse resolution string like 1920x1080 into a Resolution."""

    if "x" not in value:
        raise ValueError(f"Invalid resolution format: {value}")
    width_str, height_str = value.lower().split("x", maxsplit=1)
    width = int(width_str)
    height = int(height_str)
    if width <= 0 or height <= 0:
        raise ValueError(f"Resolution must be positive: {value}")
    return Resolution(width=width, height=height)


def parse_pages(selection: str | None, total_pages: int) -> list[int]:
    """Parse page selection like 1-3,5 into zero-based indices."""

    if not selection:
        return list(range(total_pages))

    indices: list[int] = []
    for part in selection.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_str, end_str = part.split("-", maxsplit=1)
            start = int(start_str)
            end = int(end_str)
            if start <= 0 or end <= 0:
                raise ValueError("Page numbers must be positive.")
            indices.extend(range(start - 1, end))
        else:
            page = int(part)
            if page <= 0:
                raise ValueError("Page numbers must be positive.")
            indices.append(page - 1)

    filtered = [idx for idx in indices if 0 <= idx < total_pages]
    return sorted(set(filtered))


def letterbox_image(
    image: Image.Image,
    resolution: Resolution,
    background: str = "black",
) -> Image.Image:
    """Pad image to target resolution without cropping."""

    target_w, target_h = resolution.width, resolution.height
    if background == "edge_mean":
        background_color = _average_edge_color(image)
    else:
        background_color = (0, 0, 0)

    image_ratio = image.width / image.height
    target_ratio = target_w / target_h

    if image_ratio > target_ratio:
        new_w = target_w
        new_h = int(target_w / image_ratio)
    else:
        new_h = target_h
        new_w = int(target_h * image_ratio)

    resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (target_w, target_h), background_color)
    offset_x = (target_w - new_w) // 2
    offset_y = (target_h - new_h) // 2
    canvas.paste(resized, (offset_x, offset_y))
    return canvas


def _average_edge_color(image: Image.Image) -> tuple[int, int, int]:
    """Compute average edge color for padding."""

    rgb = image.convert("RGB")
    pixels = rgb.load()
    width, height = rgb.size
    samples: list[tuple[int, int, int]] = []
    for x in range(width):
        samples.append(pixels[x, 0])
        samples.append(pixels[x, height - 1])
    for y in range(height):
        samples.append(pixels[0, y])
        samples.append(pixels[width - 1, y])
    if not samples:
        return (0, 0, 0)
    avg = tuple(sum(channel) // len(samples) for channel in zip(*samples))
    return avg  # type: ignore[return-value]
