"""CLI entrypoint for NotebookLM Slide Refiner."""

from __future__ import annotations

import argparse
import logging
import sys
from functools import partial
from pathlib import Path

import anyio
from dotenv import find_dotenv, load_dotenv

from notebooklm_slide_refiner.flows import build_deck_flow
from notebooklm_slide_refiner.utils import parse_resolution


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NotebookLM Slide Refiner")
    parser.add_argument("--input", required=True, help="Input PDF path")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--resolution", default="1920x1080", help="Target resolution WxH")
    parser.add_argument("--dpi", type=int, default=200, help="Render DPI")
    parser.add_argument("--concurrency", type=int, default=5, help="Refine concurrency")
    parser.add_argument("--rps", type=float, default=2.0, help="Refine requests per second")
    parser.add_argument("--skip-refine", action="store_true", help="Skip Vertex refine")
    parser.add_argument(
        "--remove-corner-marks",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--pages", default=None, help="Page range like 1-3,5,7-9")
    parser.add_argument(
        "--background",
        default="black",
        choices=["black", "edge_mean"],
        help="Letterbox background color",
    )
    parser.add_argument(
        "--allow-partial",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Allow partial output when pages fail",
    )
    parser.add_argument(
        "--extract-text",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Extract text from PDF pages to text files",
    )
    parser.add_argument(
        "--use-text-files",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Use extracted text files for refinement prompt",
    )
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    load_dotenv(find_dotenv(usecwd=True))

    parser = build_parser()
    args = parser.parse_args()

    resolution = parse_resolution(args.resolution)

    flow_runner = partial(
        build_deck_flow,
        input_pdf=Path(args.input),
        out_dir=Path(args.out),
        resolution=resolution,
        dpi=args.dpi,
        concurrency=args.concurrency,
        rps=args.rps,
        skip_refine=args.skip_refine,
        pages=args.pages,
        remove_corner_marks=args.remove_corner_marks,
        background=args.background,
        background=args.background,
        allow_partial=args.allow_partial,
        extract_text=args.extract_text,
        use_text_files=args.use_text_files,
    )
    outcome = anyio.run(flow_runner)

    if outcome.failures and not args.allow_partial:
        sys.exit(1)

    if outcome.failures and not args.allow_partial:
        sys.exit(1)


if __name__ == "__main__":
    main()
