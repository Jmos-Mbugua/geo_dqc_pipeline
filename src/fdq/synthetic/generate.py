"""Generate a clean (error-free) simulated farmer registration dataset.

All randomness comes from a numpy Generator passed in by the caller, so the
same seed always produces the same data.
"""

import logging
import math
from datetime import date, timedelta

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely import affinity
from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseGeometry

from fdq.config import EXPORT_DATE  # noqa: F401  (re-exported for the planter and tests)
from fdq.geo import (
    SQUARE_METRES_PER_ACRE,
    WGS84,
    projected_crs_for_longitude,
    to_degrees,
    to_metres,
)
from fdq.schema import SURVEY_COLUMNS
from fdq.synthetic import reference as ref

logger = logging.getLogger(__name__)

MIN_FARM_ACRES = 0.2
MAX_FARM_ACRES = 5.0
REGISTRATION_START = date(2026, 2, 2)  # long-rains registration campaign
REGISTRATION_END = date(2026, 5, 29)
ENUMERATORS_PER_COUNTY = 3
COORDINATE_DECIMALS = 7  # ~1 cm, more than any phone GPS can resolve
MAX_RESAMPLE_ROUNDS = 20


def sample_points_in_polygon(
    polygon: BaseGeometry, n: int, rng: np.random.Generator, batch_size: int = 256
) -> list[Point]:
    """Draw random points inside a polygon by rejection sampling.

    Points are drawn uniformly in the bounding box and kept only if they fall
    inside. Uniform in degrees is close to uniform in area near the equator,
    where a degree of longitude and of latitude are almost the same length.

    Args:
        polygon: (Multi)polygon in EPSG:4326.
        n: Number of points to return.
        rng: Random number generator.
        batch_size: Candidate points drawn per attempt.

    Returns:
        n points inside the polygon.
    """
    shapely.prepare(polygon)  # caches a spatial index; speeds up repeated tests
    minx, miny, maxx, maxy = polygon.bounds
    points: list[Point] = []
    while len(points) < n:
        xs = rng.uniform(minx, maxx, batch_size)
        ys = rng.uniform(miny, maxy, batch_size)
        inside = shapely.contains_xy(polygon, xs, ys)
        points.extend(Point(x, y) for x, y in zip(xs[inside], ys[inside]))
    return points[:n]


def random_farm_acres(
    rng: np.random.Generator, low: float = MIN_FARM_ACRES, high: float = MAX_FARM_ACRES
) -> float:
    """Draw a farm size, log-uniform so small farms are more common than large.

    Args:
        rng: Random number generator.
        low: Smallest size in acres.
        high: Largest size in acres.

    Returns:
        Farm size in acres.
    """
    return float(math.exp(rng.uniform(math.log(low), math.log(high))))


def make_farm_polygon(
    centre: tuple[float, float], area_m2: float, rng: np.random.Generator
) -> Polygon:
    """Build an irregular farm polygon around a centre point, in metres.

    Vertices sit at evenly spaced (slightly jittered) angles around the centre
    with random distances from it. Because they go round the centre in angle
    order and every gap is under 180°, the edges can never cross: the polygon
    is valid and contains the centre by construction. It is then scaled to the
    exact target area.

    Args:
        centre: (x, y) in a projected CRS (metres).
        area_m2: Target area in square metres.
        rng: Random number generator.

    Returns:
        A valid polygon in the same projected CRS.
    """
    n_vertices = int(rng.integers(5, 9))
    step = 2 * math.pi / n_vertices
    angles = rng.uniform(0, 2 * math.pi) + step * (np.arange(n_vertices) + rng.uniform(-0.3, 0.3, n_vertices))
    radii = rng.uniform(0.75, 1.25, n_vertices)
    cx, cy = centre
    shape = Polygon(zip(cx + radii * np.cos(angles), cy + radii * np.sin(angles)))
    factor = math.sqrt(area_m2 / shape.area)
    return affinity.scale(shape, factor, factor, origin=centre)


def make_farm(point: Point, rng: np.random.Generator) -> Polygon:
    """Build a smallholding (0.2 to 5 acres) around a GPS point.

    The point is the star centre of the polygon, not its centroid, so it sits
    inside the farm but off-centre, like a homestead.

    Args:
        point: Farmer's GPS point in EPSG:4326.
        rng: Random number generator.

    Returns:
        The farm polygon in EPSG:4326.
    """
    crs = projected_crs_for_longitude(point.x)
    centre = to_metres(point, crs)
    area_m2 = random_farm_acres(rng) * SQUARE_METRES_PER_ACRE
    return to_degrees(make_farm_polygon((centre.x, centre.y), area_m2, rng), crs)


def enumerator_ids(county: str) -> list[str]:
    """List the enumerator IDs working in a county.

    Args:
        county: County name.

    Returns:
        IDs like "ENUM-NKR-01".
    """
    code = ref.COUNTY_CODES[county]
    return [f"ENUM-{code}-{k:02d}" for k in range(1, ENUMERATORS_PER_COUNTY + 1)]


def random_name(county: str, rng: np.random.Generator) -> str:
    """Make a plausible farmer name for a county.

    Args:
        county: County name, used to pick regionally common surnames.
        rng: Random number generator.

    Returns:
        "First Surname".
    """
    first_names = ref.FEMALE_FIRST_NAMES if rng.random() < 0.5 else ref.MALE_FIRST_NAMES
    return f"{rng.choice(first_names)} {rng.choice(ref.SURNAMES[county])}"


def random_phone(rng: np.random.Generator) -> str:
    """Make a Kenyan-format mobile number, as text to keep the leading zero.

    Args:
        rng: Random number generator.

    Returns:
        A number like "0712345678".
    """
    return f"07{int(rng.integers(0, 10**8)):08d}"


def random_date(rng: np.random.Generator, start: date, end: date) -> str:
    """Draw a date between start and end inclusive.

    Args:
        rng: Random number generator.
        start: Earliest date.
        end: Latest date.

    Returns:
        ISO date string, e.g. "2026-03-14".
    """
    return (start + timedelta(days=int(rng.integers(0, (end - start).days + 1)))).isoformat()


def find_overlapping(polygons: list[BaseGeometry]) -> set[int]:
    """Find polygons that touch or overlap an earlier polygon in the list.

    Intersects is a topological test, so running it in degrees is fine.

    Args:
        polygons: Polygons in EPSG:4326.

    Returns:
        Positions of the later polygon in each intersecting pair.
    """
    tree = shapely.STRtree(polygons)
    left, right = tree.query(polygons, predicate="intersects")
    return {int(j) for i, j in zip(left, right) if i < j}


def generate_clean_survey(
    county_polygons: dict[str, BaseGeometry], n_farmers: int, rng: np.random.Generator
) -> gpd.GeoDataFrame:
    """Generate error-free farmer registrations with farm polygons.

    Args:
        county_polygons: County name to boundary (EPSG:4326).
        n_farmers: Number of farmers.
        rng: Random number generator.

    Returns:
        One row per farmer with the survey columns, and the farm polygon as
        the geometry (EPSG:4326). Rows are in registration order and
        farmer_ids are assigned in that order.
    """
    names = sorted(county_polygons)
    counties = [str(c) for c in rng.choice(names, size=n_farmers)]

    points: list[Point] = [Point()] * n_farmers
    for name in names:
        rows = [i for i, c in enumerate(counties) if c == name]
        for row, point in zip(rows, sample_points_in_polygon(county_polygons[name], len(rows), rng)):
            points[row] = point
    farms = [make_farm(point, rng) for point in points]

    # Clean farms must not overlap, so every overlap found later was planted.
    for _ in range(MAX_RESAMPLE_ROUNDS):
        clashes = find_overlapping(farms)
        if not clashes:
            break
        logger.debug("Resampling %d overlapping clean farms", len(clashes))
        for row in sorted(clashes):
            points[row] = sample_points_in_polygon(county_polygons[counties[row]], 1, rng)[0]
            farms[row] = make_farm(points[row], rng)
    else:
        raise RuntimeError("Could not place clean farms without overlaps")

    national_ids = rng.choice(90_000_000, size=n_farmers, replace=False) + 10_000_000
    records = pd.DataFrame(
        {
            "farmer_name": [random_name(c, rng) for c in counties],
            "national_id": [str(x) for x in national_ids],
            "phone": [random_phone(rng) for _ in counties],
            "county": counties,
            "ward": [str(rng.choice(ref.WARDS[c])) for c in counties],
            "crop": [str(rng.choice(ref.CROPS[c])) for c in counties],
            "registration_date": [
                random_date(rng, REGISTRATION_START, REGISTRATION_END) for _ in counties
            ],
            "enumerator_id": [str(rng.choice(enumerator_ids(c))) for c in counties],
            "latitude": [round(p.y, COORDINATE_DECIMALS) for p in points],
            "longitude": [round(p.x, COORDINATE_DECIMALS) for p in points],
        }
    )
    survey = gpd.GeoDataFrame(records, geometry=farms, crs=WGS84)
    survey = survey.sort_values("registration_date", kind="stable").reset_index(drop=True)
    survey["farmer_id"] = [f"FRM-{i:05d}" for i in range(1, n_farmers + 1)]
    logger.info("Generated %d clean farmer records in %d counties", n_farmers, len(names))
    return survey[SURVEY_COLUMNS + ["geometry"]]
