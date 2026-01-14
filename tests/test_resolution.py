"""Tests for resolution parsing."""

from notebooklm_slide_refiner.render import parse_resolution


def test_parse_resolution() -> None:
    resolution = parse_resolution("1920x1080")
    assert resolution.width == 1920
    assert resolution.height == 1080
