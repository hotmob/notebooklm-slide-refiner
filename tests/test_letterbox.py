"""Tests for letterbox padding."""

from PIL import Image

from notebooklm_slide_refiner.render import Resolution, letterbox_image


def test_letterbox_size() -> None:
    image = Image.new("RGB", (800, 600), (255, 0, 0))
    resolution = Resolution(width=1920, height=1080)
    output = letterbox_image(image, resolution)
    assert output.size == (1920, 1080)
