"""Download Kenya's county boundaries (geoBoundaries gbOpen, ADM1).

Usage:
    python scripts/download_boundaries.py [--simplified]
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

from fdq import boundaries

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "data" / "raw" / "kenya_counties.geojson"

logger = logging.getLogger("download_boundaries")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output GeoJSON path")
    parser.add_argument(
        "--simplified", action="store_true", help="download the simplified (lighter) geometry"
    )
    return parser.parse_args()


def main() -> None:
    """Download, validate and save the county boundaries plus a provenance file."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    api_url = boundaries.build_api_url("KEN", "ADM1", "gbOpen")
    logger.info("Fetching metadata from %s", api_url)
    metadata = boundaries.fetch_metadata(api_url)
    download_url = boundaries.select_download_url(metadata, simplified=args.simplified)

    logger.info("Downloading %s", download_url)
    raw = boundaries.fetch_bytes(download_url)
    counties = boundaries.parse_boundaries(raw)
    boundaries.validate_boundaries(counties)

    # Save the file exactly as published, so the raw data is untouched source.
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(raw)
    logger.info("Saved %s (%.1f MB)", args.out, len(raw) / 1e6)

    source_path = args.out.with_suffix(".source.json")
    record = boundaries.provenance(metadata, download_url, date.today().isoformat())
    source_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    logger.info("Saved provenance to %s", source_path)


if __name__ == "__main__":
    main()
