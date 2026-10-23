"""Generate the simulated farmer registration survey with planted errors.

Usage:
    python scripts/generate_survey.py [--seed 42] [--n-farmers 600]
"""

import argparse
import logging
from pathlib import Path

import numpy as np

from fdq import io
from fdq.boundaries import county_polygons
from fdq.synthetic.generate import generate_clean_survey
from fdq.synthetic.plant import plant_errors
from fdq.synthetic.reference import TARGET_COUNTIES

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"

logger = logging.getLogger("generate_survey")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=42, help="random seed (default 42)")
    parser.add_argument("--n-farmers", type=int, default=600, help="number of records (default 600)")
    parser.add_argument("--counties", type=Path, default=RAW_DIR / "kenya_counties.geojson")
    parser.add_argument("--out-dir", type=Path, default=RAW_DIR)
    return parser.parse_args()


def main() -> None:
    """Generate clean records, plant errors and write the three output files."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()
    rng = np.random.default_rng(args.seed)
    logger.info("Seed %d, %d farmers in %s", args.seed, args.n_farmers, ", ".join(TARGET_COUNTIES))

    polygons = county_polygons(io.read_counties(args.counties), TARGET_COUNTIES)
    clean = generate_clean_survey(polygons, args.n_farmers, rng)
    survey, truth = plant_errors(clean, polygons, rng)

    outputs = {
        "farmer_registrations.csv": io.write_registrations,
        "farm_boundaries.geojson": io.write_farm_boundaries,
    }
    for name, write in outputs.items():
        write(survey, args.out_dir / name)
        logger.info("Saved %s", args.out_dir / name)
    io.write_ground_truth(truth, args.out_dir / "planted_errors.csv")
    logger.info("Saved %s", args.out_dir / "planted_errors.csv")


if __name__ == "__main__":
    main()
