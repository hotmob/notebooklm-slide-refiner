"""Tests for page selection parsing."""

from notebooklm_slide_refiner.utils import parse_pages


def test_parse_pages_ranges() -> None:
    pages = parse_pages("1-3,5,7-9", total_pages=12)
    assert pages == [0, 1, 2, 4, 6, 7, 8]
