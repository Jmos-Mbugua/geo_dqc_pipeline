"""Plant known, labelled errors into a clean simulated survey.

Each affected record gets exactly one error, and every planted error is
written to a ground-truth table so the quality checks can be scored against it.
Planted geometries are kept clear of unrelated farms, so the only overlaps in
the output are the planted overlaps and duplicates.
"""

import logging
import math
from datetime import date, timedelta

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import affinity
from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseGeometry

from fdq.geo import SQUARE_METRES_PER_ACRE, projected_crs_for_longitude, to_degrees, to_metres
from fdq.synthetic.generate import (
    COORDINATE_DECIMALS,
    REGISTRATION_END,
    enumerator_ids,
    sample_points_in_polygon,
)

logger = logging.getLogger(__name__)

# Number of records per error type ("farm_overlap" counts pairs: 2 records each).
ERROR_COUNTS: dict[str, int] = {
    "gps_outside_county": 8,
    "farm_overlap": 4,
    "duplicate_registration": 6,
    "area_too_large": 4,
    "area_too_small": 4,
    "gps_null_island": 4,
    "gps_latlon_swapped": 4,
    "missing_required_field": 8,
    "future_registration_date": 5,
    "polygon_self_intersecting": 7,
}
# related_farmer_id: the other record involved (overlap partner, or the
# original of a duplicate); empty for single-record errors.
TRUTH_COLUMNS = ["farmer_id", "error_type", "related_farmer_id", "details"]
MISSING_FIELD_CYCLE = [
    "national_id",
    "farmer_name",
    "county",
    "crop",
    "enumerator_id",
    "phone",
    "registration_date",
    "latitude/longitude",
]
LARGE_FARM_ACRES = (100.0, 500.0)
TINY_FARM_M2 = (10.0, 40.0)
OVERLAP_FRACTION_RANGE = (0.5, 0.9)  # share of the smaller farm covered
DUPLICATE_SHIFT_M = (5.0, 15.0)
MAX_TRIES = 50


# --- Pure helpers: one small transformation each -------------------------


def scale_farm(polygon: Polygon, anchor: Point, target_m2: float) -> Polygon:
    """Resize a farm to a target area, keeping the anchor point fixed.

    Args:
        polygon: Farm polygon in EPSG:4326.
        anchor: Point to scale around (the farmer's GPS point).
        target_m2: New area in square metres.

    Returns:
        The resized polygon in EPSG:4326.
    """
    crs = projected_crs_for_longitude(anchor.x)
    polygon_m, anchor_m = to_metres(polygon, crs), to_metres(anchor, crs)
    factor = math.sqrt(target_m2 / polygon_m.area)
    return to_degrees(affinity.scale(polygon_m, factor, factor, origin=anchor_m), crs)


def translate_farm(polygon: Polygon, point: Point, dx_m: float, dy_m: float) -> tuple[Polygon, Point]:
    """Shift a farm and its GPS point by a distance in metres.

    Args:
        polygon: Farm polygon in EPSG:4326.
        point: Farmer's GPS point in EPSG:4326.
        dx_m: Eastward shift in metres.
        dy_m: Northward shift in metres.

    Returns:
        The shifted polygon and point in EPSG:4326.
    """
    crs = projected_crs_for_longitude(point.x)
    moved_polygon = affinity.translate(to_metres(polygon, crs), dx_m, dy_m)
    moved_point = affinity.translate(to_metres(point, crs), dx_m, dy_m)
    return to_degrees(moved_polygon, crs), to_degrees(moved_point, crs)


def relocate_farm(polygon: Polygon, old_point: Point, new_point: Point) -> Polygon:
    """Move a farm so it keeps its shape around a new GPS point.

    The farm's offsets from its point are measured in metres in the old UTM
    zone and re-applied around the new point in its own zone, so shape and
    area survive moves across the 36°E zone boundary.

    Args:
        polygon: Farm polygon in EPSG:4326.
        old_point: Current GPS point in EPSG:4326.
        new_point: Destination GPS point in EPSG:4326.

    Returns:
        The relocated polygon in EPSG:4326.
    """
    old_crs = projected_crs_for_longitude(old_point.x)
    new_crs = projected_crs_for_longitude(new_point.x)
    polygon_m, old_m = to_metres(polygon, old_crs), to_metres(old_point, old_crs)
    new_m = to_metres(new_point, new_crs)
    moved = affinity.translate(polygon_m, new_m.x - old_m.x, new_m.y - old_m.y)
    return to_degrees(moved, new_crs)


def make_self_intersecting(polygon: Polygon, rng: np.random.Generator) -> Polygon:
    """Turn a valid polygon into a self-intersecting one ("bowtie").

    Swaps the order of two vertices that are not neighbours, which makes two
    edges cross: the same mistake as an enumerator walking a boundary out of
    order.

    Args:
        polygon: A valid polygon with at least 5 vertices.
        rng: Random number generator.

    Returns:
        A polygon with the same vertices for which is_valid is False.

    Raises:
        RuntimeError: If no swap produced an invalid polygon.
    """
    ring = list(polygon.exterior.coords)[:-1]
    for _ in range(MAX_TRIES):
        i = int(rng.integers(len(ring)))
        j = (i + 2) % len(ring)
        swapped = ring.copy()
        swapped[i], swapped[j] = swapped[j], swapped[i]
        candidate = Polygon(swapped)
        if not candidate.is_valid:
            return candidate
    raise RuntimeError("Could not make the polygon self-intersecting")


def misspell_name(name: str, rng: np.random.Generator) -> str:
    """Introduce a small, realistic spelling difference into a name.

    One of: drop a letter, swap two neighbouring letters, change a vowel, or
    put the surname first.

    Args:
        name: "First Surname".
        rng: Random number generator.

    Returns:
        A different but similar name.
    """
    words = name.split()
    for _ in range(MAX_TRIES):
        strategy = int(rng.integers(4))
        if strategy == 3:
            candidate = " ".join(reversed(words))
        else:
            k = int(rng.integers(len(words)))
            word = words[k]
            if strategy == 0:  # drop a letter (not the first)
                p = int(rng.integers(1, len(word)))
                word = word[:p] + word[p + 1 :]
            elif strategy == 1:  # swap two neighbouring letters (not the first)
                p = int(rng.integers(1, len(word) - 1))
                word = word[:p] + word[p + 1] + word[p] + word[p + 2 :]
            else:  # change one vowel, e.g. Wanjiku -> Wanjiko
                vowels = [p for p, ch in enumerate(word) if ch in "aeiou"]
                if not vowels:
                    continue
                p = int(rng.choice(vowels))
                word = word[:p] + str(rng.choice([v for v in "aeiou" if v != word[p]])) + word[p + 1 :]
            candidate = " ".join(words[:k] + [word] + words[k + 1 :])
        if candidate != name:
            return candidate
    raise RuntimeError(f"Could not misspell {name!r}")


def year_typo(iso_date: str) -> str:
    """Swap the last two digits of the year, e.g. 2026-03-14 -> 2062-03-14.

    Args:
        iso_date: Date as "YYYY-MM-DD".

    Returns:
        The same date with a transposed year.
    """
    d = date.fromisoformat(iso_date)
    year = str(d.year)
    return d.replace(year=int(year[:2] + year[3] + year[2])).isoformat()


def overlap_onto(
    target: Polygon, mover: Polygon, mover_point: Point, min_fraction: float, rng: np.random.Generator
) -> tuple[Polygon, Point, float]:
    """Slide one farm onto another until they overlap heavily.

    The mover starts clear of the target, in a random direction, and slides
    towards it in small steps until at least min_fraction of the
    smaller farm is covered, so overlaps are heavy but partial rather than
    one farm swallowing the other. All of this is measured in metres.

    Args:
        target: Farm that stays put (EPSG:4326).
        mover: Farm that moves (EPSG:4326).
        mover_point: The mover's GPS point, moved along with it.
        min_fraction: Share of the smaller farm that must be covered.
        rng: Random number generator.

    Returns:
        The moved polygon, moved point and achieved overlap fraction.
    """
    crs = projected_crs_for_longitude(target.centroid.x)
    target_m, mover_m, point_m = (to_metres(g, crs) for g in (target, mover, mover_point))
    smaller = min(target_m.area, mover_m.area)
    angle = rng.uniform(0, 2 * math.pi)
    distance = math.sqrt(target_m.area) + math.sqrt(mover_m.area)  # far enough apart to start
    for _ in range(MAX_TRIES):
        dx = target_m.centroid.x + distance * math.cos(angle) - mover_m.centroid.x
        dy = target_m.centroid.y + distance * math.sin(angle) - mover_m.centroid.y
        moved = affinity.translate(mover_m, dx, dy)
        fraction = target_m.intersection(moved).area / smaller
        if fraction >= min_fraction:
            moved_point = affinity.translate(point_m, dx, dy)
            return to_degrees(moved, crs), to_degrees(moved_point, crs), fraction
        distance *= 0.9
    raise RuntimeError("Could not create a heavy overlap")


# --- Orchestration --------------------------------------------------------
# The private _plant_* helpers modify `survey`, which is always the working
# copy owned by plant_errors; the caller's data is never changed.


def _point(survey: gpd.GeoDataFrame, row: int) -> Point:
    return Point(survey.at[row, "longitude"], survey.at[row, "latitude"])


def _set_point(survey: gpd.GeoDataFrame, row: int, point: Point) -> None:
    survey.at[row, "latitude"] = round(point.y, COORDINATE_DECIMALS)
    survey.at[row, "longitude"] = round(point.x, COORDINATE_DECIMALS)


def _clashes(survey: gpd.GeoDataFrame, geom: BaseGeometry, ignore: set[int]) -> bool:
    """True if geom touches any farm other than the ones in `ignore`."""
    hits = survey.index[survey.geometry.intersects(geom)]
    return any(row not in ignore for row in hits)


def _truth(
    survey: gpd.GeoDataFrame, row: int, error_type: str, details: str, related_row: int | None = None
) -> dict:
    related = None if related_row is None else survey.at[related_row, "farmer_id"]
    return {
        "farmer_id": survey.at[row, "farmer_id"],
        "error_type": error_type,
        "related_farmer_id": related,
        "details": details,
    }


class _Pool:
    """Rows not yet used, in random order, so each record gets one error at most."""

    def __init__(self, survey: gpd.GeoDataFrame, rng: np.random.Generator) -> None:
        self.survey = survey
        self.rows = [int(i) for i in rng.permutation(len(survey))]

    def take(self, county: str | None = None) -> int:
        for k in range(len(self.rows) - 1, -1, -1):
            if county is None or self.survey.at[self.rows[k], "county"] == county:
                return self.rows.pop(k)
        raise ValueError(f"No unused records left (county={county})")


def _plant_outside_county(
    survey: gpd.GeoDataFrame, pool: _Pool, n: int, county_polygons: dict[str, BaseGeometry], rng: np.random.Generator
) -> list[dict]:
    truth = []
    names = sorted(county_polygons)
    while len(truth) < n:
        row = pool.take()
        registered = survey.at[row, "county"]
        other = str(rng.choice([c for c in names if c != registered]))
        new_point = sample_points_in_polygon(county_polygons[other], 1, rng)[0]
        farm = relocate_farm(survey.at[row, "geometry"], _point(survey, row), new_point)
        if _clashes(survey, farm, {row}):
            continue  # this row stays clean; try another
        survey.at[row, "geometry"] = farm
        _set_point(survey, row, new_point)
        truth.append(_truth(survey, row, "gps_outside_county", f"registered in {registered}, GPS in {other}"))
    return truth


def _plant_overlaps(
    survey: gpd.GeoDataFrame, pool: _Pool, n_pairs: int, county_polygons: dict[str, BaseGeometry], rng: np.random.Generator
) -> list[dict]:
    truth = []
    while len(truth) < 2 * n_pairs:
        a = pool.take()
        county = survey.at[a, "county"]
        b = pool.take(county)
        min_fraction = rng.uniform(*OVERLAP_FRACTION_RANGE)
        for _ in range(MAX_TRIES):
            farm, point, fraction = overlap_onto(
                survey.at[a, "geometry"], survey.at[b, "geometry"], _point(survey, b), min_fraction, rng
            )
            if county_polygons[county].contains(point) and not _clashes(survey, farm, {a, b}):
                break
        else:
            continue  # both rows stay clean; try another pair
        survey.at[b, "geometry"] = farm
        _set_point(survey, b, point)
        details = f"{fraction:.0%} of the smaller farm covered"
        truth.append(_truth(survey, a, "farm_overlap", details, related_row=b))
        truth.append(_truth(survey, b, "farm_overlap", details, related_row=a))
    return truth


def _plant_duplicates(
    survey: gpd.GeoDataFrame, pool: _Pool, n: int, county_polygons: dict[str, BaseGeometry], rng: np.random.Generator
) -> list[dict]:
    truth = []
    while len(truth) < n:
        original, dup = pool.take(), pool.take()
        county = survey.at[original, "county"]
        for _ in range(MAX_TRIES):
            distance = rng.uniform(*DUPLICATE_SHIFT_M)
            angle = rng.uniform(0, 2 * math.pi)
            farm, point = translate_farm(
                survey.at[original, "geometry"],
                _point(survey, original),
                distance * math.cos(angle),
                distance * math.sin(angle),
            )
            if county_polygons[county].contains(point) and not _clashes(survey, farm, {original, dup}):
                break
        else:
            continue

        for col in ("national_id", "phone", "county", "ward", "crop"):
            survey.at[dup, col] = survey.at[original, col]
        old_name = survey.at[original, "farmer_name"]
        survey.at[dup, "farmer_name"] = misspell_name(old_name, rng)
        first = date.fromisoformat(survey.at[original, "registration_date"])
        days_left = max((REGISTRATION_END - first).days, 0)
        offset = int(rng.integers(min(3, days_left), min(60, days_left) + 1))
        survey.at[dup, "registration_date"] = (first + timedelta(days=offset)).isoformat()
        survey.at[dup, "enumerator_id"] = str(rng.choice(enumerator_ids(county)))
        survey.at[dup, "geometry"] = farm
        _set_point(survey, dup, point)
        truth.append(
            _truth(
                survey,
                dup,
                "duplicate_registration",
                f"name '{old_name}' -> '{survey.at[dup, 'farmer_name']}'; "
                "farm re-walked, so it also overlaps the original",
                related_row=original,
            )
        )
    return truth


def _plant_area(
    survey: gpd.GeoDataFrame, pool: _Pool, n: int, rng: np.random.Generator, too_large: bool
) -> list[dict]:
    truth = []
    while len(truth) < n:
        row = pool.take()
        if too_large:
            target_m2 = rng.uniform(*LARGE_FARM_ACRES) * SQUARE_METRES_PER_ACRE
        else:
            target_m2 = rng.uniform(*TINY_FARM_M2)
        farm = scale_farm(survey.at[row, "geometry"], _point(survey, row), target_m2)
        if too_large and _clashes(survey, farm, {row}):
            continue
        survey.at[row, "geometry"] = farm
        if too_large:
            truth.append(_truth(survey, row, "area_too_large", f"{target_m2 / SQUARE_METRES_PER_ACRE:.0f} acres"))
        else:
            truth.append(_truth(survey, row, "area_too_small", f"{target_m2:.0f} m2"))
    return truth


def _plant_null_island(survey: gpd.GeoDataFrame, pool: _Pool, n: int) -> list[dict]:
    truth = []
    for _ in range(n):
        row = pool.take()
        survey.at[row, "latitude"] = 0.0
        survey.at[row, "longitude"] = 0.0
        truth.append(_truth(survey, row, "gps_null_island", "GPS saved as 0,0 (no fix)"))
    return truth


def _plant_swapped(survey: gpd.GeoDataFrame, pool: _Pool, n: int) -> list[dict]:
    truth = []
    for _ in range(n):
        row = pool.take()
        lat, lon = survey.at[row, "latitude"], survey.at[row, "longitude"]
        survey.at[row, "latitude"], survey.at[row, "longitude"] = lon, lat
        truth.append(_truth(survey, row, "gps_latlon_swapped", f"true position lat {lat}, lon {lon}"))
    return truth


def _plant_missing(survey: gpd.GeoDataFrame, pool: _Pool, n: int) -> list[dict]:
    truth = []
    for i in range(n):
        row = pool.take()
        field = MISSING_FIELD_CYCLE[i % len(MISSING_FIELD_CYCLE)]
        for col in field.split("/"):
            survey.at[row, col] = np.nan if col in ("latitude", "longitude") else None
        truth.append(_truth(survey, row, "missing_required_field", f"{field} blank"))
    return truth


def _plant_future_dates(
    survey: gpd.GeoDataFrame, pool: _Pool, n: int, rng: np.random.Generator
) -> list[dict]:
    truth = []
    n_typos = math.ceil(0.6 * n)
    for i in range(n):
        row = pool.take()
        old = survey.at[row, "registration_date"]
        if i < n_typos:
            new, why = year_typo(old), "year digits transposed"
        else:
            new = (date(2027, 1, 1) + timedelta(days=int(rng.integers(0, 365)))).isoformat()
            why = "device clock wrong"
        survey.at[row, "registration_date"] = new
        truth.append(_truth(survey, row, "future_registration_date", f"{old} -> {new} ({why})"))
    return truth


def _plant_self_intersecting(
    survey: gpd.GeoDataFrame, pool: _Pool, n: int, rng: np.random.Generator
) -> list[dict]:
    truth = []
    for _ in range(n):
        row = pool.take()
        survey.at[row, "geometry"] = make_self_intersecting(survey.at[row, "geometry"], rng)
        truth.append(_truth(survey, row, "polygon_self_intersecting", "two vertices out of order"))
    return truth


def plant_errors(
    clean: gpd.GeoDataFrame,
    county_polygons: dict[str, BaseGeometry],
    rng: np.random.Generator,
    counts: dict[str, int] | None = None,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Plant labelled errors into a copy of a clean survey.

    Errors that move geometry are planted first, while every farm is still
    valid; self-intersecting polygons are planted last.

    Args:
        clean: Output of generate_clean_survey (RangeIndex, one row per farmer).
        county_polygons: County name to boundary (EPSG:4326).
        rng: Random number generator.
        counts: Records per error type; defaults to ERROR_COUNTS.

    Returns:
        The survey with errors, and the ground truth with TRUTH_COLUMNS
        (one row per affected record).
    """
    counts = ERROR_COUNTS if counts is None else counts
    survey = clean.copy()
    pool = _Pool(survey, rng)

    truth: list[dict] = []
    truth += _plant_outside_county(survey, pool, counts["gps_outside_county"], county_polygons, rng)
    truth += _plant_overlaps(survey, pool, counts["farm_overlap"], county_polygons, rng)
    truth += _plant_duplicates(survey, pool, counts["duplicate_registration"], county_polygons, rng)
    truth += _plant_area(survey, pool, counts["area_too_large"], rng, too_large=True)
    truth += _plant_area(survey, pool, counts["area_too_small"], rng, too_large=False)
    truth += _plant_null_island(survey, pool, counts["gps_null_island"])
    truth += _plant_swapped(survey, pool, counts["gps_latlon_swapped"])
    truth += _plant_missing(survey, pool, counts["missing_required_field"])
    truth += _plant_future_dates(survey, pool, counts["future_registration_date"], rng)
    truth += _plant_self_intersecting(survey, pool, counts["polygon_self_intersecting"], rng)

    ground_truth = pd.DataFrame(truth, columns=TRUTH_COLUMNS).sort_values("farmer_id").reset_index(drop=True)
    for error_type, n in ground_truth["error_type"].value_counts().sort_index().items():
        logger.info("Planted %-26s %d", error_type, n)
    logger.info(
        "Planted errors in %d of %d records (%.1f%%)",
        len(ground_truth),
        len(survey),
        100 * len(ground_truth) / len(survey),
    )
    return survey, ground_truth
