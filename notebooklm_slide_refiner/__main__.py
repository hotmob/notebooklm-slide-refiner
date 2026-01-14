"""CLI entrypoint for NotebookLM Slide Refiner."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from notebooklm_slide_refiner.flows import build_deck_flow
from notebooklm_slide_refiner.render import parse_resolution


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NotebookLM Slide Refiner")
    parser.add_argument("--input", required=True, help="Input PDF path")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--resolution", default="1920x1080", help="Target resolution WxH")
    parser.add_argument("--dpi", type=int, default=None, help="Render DPI")
    parser.add_argument("--concurrency", type=int, default=5, help="Refine concurrency")
    parser.add_argument("--rps", type=float, default=2.0, help="Refine requests per second")
    parser.add_argument("--skip-refine", action="store_true", help="Skip refine stage")
    parser.add_argument("--pages", default=None, help="Page range like 1-3,5,7-9")
    parser.add_argument(
        "--remove-corner-marks",
        type=parse_bool,
        default=True,
        help="Remove corner marks in prompt",
    )
    parser.add_argument(
        "--keep-temp",
        type=parse_bool,
        default=True,
        help="Keep intermediate files",
    )
    return parser


def main() -> None:
    load_dotenv(find_dotenv(usecwd=True))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args()

    resolution = parse_resolution(args.resolution)

    flow = build_deck_flow(
        input_pdf=Path(args.input),
        out_dir=Path(args.out),
        resolution=resolution,
        dpi=args.dpi,
        concurrency=args.concurrency,
        rps=args.rps,
        skip_refine=args.skip_refine,
        pages=args.pages,
        remove_corner_marks=args.remove_corner_marks,
        keep_temp=args.keep_temp,
    )
    flow()


if __name__ == "__main__":
    main()
