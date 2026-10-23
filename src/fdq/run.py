"""Command-line entry point for the data quality pipeline.

Usage (from the repository root):
    python -m fdq.run [--raw-dir data/raw] [--out-dir outputs] [--truth PATH] [--no-eval] [--verbose]

Exit codes: 0 on success, 1 if input files are missing or the schema is wrong.
"""

import argparse
import logging
import sys
from pathlib import Path

from fdq.pipeline import InputError, PipelinePaths, run_pipeline

EXIT_OK = 0
EXIT_INPUT_ERROR = 1
LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

logger = logging.getLogger("fdq.run")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Arguments without the program name; None means sys.argv.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(prog="python -m fdq.run", description="Run the field data quality pipeline.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"), help="input folder (default data/raw)")
    parser.add_argument("--out-dir", type=Path, default=Path("outputs"), help="output folder (default outputs)")
    parser.add_argument("--truth", type=Path, help="ground-truth CSV (default RAW_DIR/planted_errors.csv)")
    parser.add_argument("--no-eval", action="store_true", help="skip evaluation against ground truth")
    parser.add_argument("--verbose", action="store_true", help="log debug messages too")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the pipeline and return the process exit code.

    Args:
        argv: Arguments without the program name; None means sys.argv.

    Returns:
        EXIT_OK or EXIT_INPUT_ERROR.
    """
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format=LOG_FORMAT)

    paths = PipelinePaths.from_dirs(args.raw_dir, args.out_dir, truth=args.truth)
    if args.no_eval:
        paths = PipelinePaths(paths.registrations, paths.farms, paths.counties, None, paths.out_dir)

    try:
        run_pipeline(paths)
    except InputError as exc:
        logger.error("%s", exc)
        return EXIT_INPUT_ERROR
    logger.info("Done")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
