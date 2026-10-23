"""Data quality checks for farmer registrations and farm boundaries.

Every check takes the data and returns a DataFrame of flags with FLAG_COLUMNS
(farmer_id, check_id, severity, message): one row per flagged record, empty
if nothing is wrong. Checks never modify their inputs.

Each check stays in its own lane: when a record is unusable for a check (no
coordinates, coordinates outside Kenya, an invalid polygon), the check skips
it, because another check already reports that problem. This keeps one bad
value from producing a pile of misleading flags.

Inputs:
    registrations: DataFrame as returned by fdq.io.read_registrations.
    farms: GeoDataFrame with farmer_id and polygon geometry (EPSG:4326).
    counties: GeoDataFrame of county boundaries with a shapeName column.
"""

import logging
import re
from collections.abc import Iterable
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.validation import explain_validity

from fdq import config
from fdq.boundaries import COUNTY_NAME_COLUMN
from fdq.geo import SQUARE_METRES_PER_ACRE, WGS84, area_m2_series, projected_crs_for_geoseries
from fdq.schema import REQUIRED_FIELDS

logger = logging.getLogger(__name__)

FLAG_COLUMNS = ["farmer_id", "check_id", "severity", "message"]
ERROR = "error"
WARNING = "warning"
POLYGON_TYPES = ("Polygon", "MultiPolygon")


# --- Shared helpers ---------------------------------------------------------


def _flags(
    farmer_ids: Iterable, check_id: str, severity: str | Iterable[str], messages: Iterable[str]
) -> pd.DataFrame:
    """Build a flag table. severity is one value for all rows, or one per row."""
    severity = list(severity) if not isinstance(severity, str) else severity
    return pd.DataFrame(
        {"farmer_id": list(farmer_ids), "check_id": check_id, "severity": severity, "message": list(messages)},
        columns=FLAG_COLUMNS,
    )


def is_blank(values: pd.Series) -> pd.Series:
    """Mark missing values: NaN/None, empty strings and placeholders like "N/A".

    Args:
        values: Any column.

    Returns:
        Boolean Series, True where the value counts as missing.
    """
    text = values.astype("string").str.strip().str.casefold()
    return values.isna() | text.isin(config.MISSING_PLACEHOLDERS).fillna(False)


def _coordinates(registrations: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Latitude and longitude as floats; anything non-numeric becomes NaN."""
    lat = pd.to_numeric(registrations["latitude"], errors="coerce")
    lon = pd.to_numeric(registrations["longitude"], errors="coerce")
    return lat, lon


def _in_bbox(lon: pd.Series, lat: pd.Series, bbox: tuple[float, float, float, float]) -> pd.Series:
    """True where (lon, lat) falls inside the bounding box."""
    min_lon, min_lat, max_lon, max_lat = bbox
    return lon.between(min_lon, max_lon) & lat.between(min_lat, max_lat)


def _usable_points(registrations: pd.DataFrame, bbox: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    """Registration points that have coordinates inside the bounding box.

    Points outside it are gps_invalid's job, and measuring them in a Kenyan
    UTM zone would give meaningless numbers anyway.
    """
    lat, lon = _coordinates(registrations)
    usable = lat.notna() & lon.notna() & _in_bbox(lon, lat, bbox)
    return gpd.GeoDataFrame(
        registrations.loc[usable, ["farmer_id", "county"]],
        geometry=gpd.points_from_xy(lon[usable], lat[usable]),
        crs=WGS84,
    )


def _measurable_farms(farms: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Farms whose geometry is a valid, non-empty polygon.

    Area, distance and overlap are undefined (or misleading) for anything
    else, and polygon_invalid reports those records.
    """
    geoms = farms.geometry
    ok = geoms.notna() & ~geoms.is_empty & geoms.geom_type.isin(POLYGON_TYPES) & geoms.is_valid
    return farms[ok]


def normalise_phone(phone: object) -> str | None:
    """Reduce a Kenyan phone number to its 10-digit local form.

    "+254 712 345 678", "254712345678" and "0712-345-678" all become
    "0712345678", so the same number written differently still matches.

    Args:
        phone: Phone number as text, or a missing value.

    Returns:
        Digits only, in local 0XXXXXXXXX form; None if there are no digits.
    """
    if phone is None or pd.isna(phone):
        return None
    digits = re.sub(r"\D", "", str(phone))
    if digits.startswith("254") and len(digits) == 12:
        digits = "0" + digits[3:]
    return digits or None


def normalise_county_name(name: str) -> str:
    """Normalise a county name so spelling variants compare equal.

    Lower-cases, treats hyphens as spaces, drops apostrophes, collapses
    spaces, then applies config.COUNTY_NAME_ALIASES ("Tharaka-Nithi" ->
    "tharaka", the boundary data's spelling).

    Args:
        name: County name as typed or as in the boundary data.

    Returns:
        The normalised name.
    """
    text = " ".join(str(name).casefold().replace("-", " ").replace("'", "").split())
    return config.COUNTY_NAME_ALIASES.get(text, text)


# --- Attribute checks ----------------------------------------------------------


def required_fields_missing(
    registrations: pd.DataFrame, required: list[str] = REQUIRED_FIELDS
) -> pd.DataFrame:
    """Flag records with a blank required field.

    A field that is absent from the data altogether counts as blank for
    every record.

    Args:
        registrations: Farmer registrations.
        required: Columns that must be filled in.

    Returns:
        One error per record, listing every missing field.
    """
    blank = pd.DataFrame(
        {
            field: is_blank(registrations[field]) if field in registrations else True
            for field in required
        },
        index=registrations.index,
    )
    has_blank = blank.any(axis=1)
    messages = [
        "missing required field(s): " + ", ".join(blank.columns[row])
        for row in blank[has_blank].to_numpy()
    ]
    return _flags(registrations.loc[has_blank, "farmer_id"], "required_fields_missing", ERROR, messages)


def duplicate_registration(registrations: pd.DataFrame) -> pd.DataFrame:
    """Flag every record that shares a national_id or phone number with another.

    Both (all) records in a duplicate group are flagged, each naming the
    others. A shared national_id is an error: one person, registered twice.
    A shared phone only is a warning: family members often share a phone.

    Args:
        registrations: Farmer registrations.

    Returns:
        One flag per record; the message lists every shared value.
    """
    keys = {
        "national_id": (registrations["national_id"].astype("string").str.strip(), ERROR),
        "phone": (registrations["phone"].map(normalise_phone), WARNING),
    }
    findings: dict[object, list[tuple[str, str]]] = {}
    for label, (values, severity) in keys.items():
        present = ~is_blank(values)
        groups = registrations.loc[present, "farmer_id"].groupby(values[present])
        for value, members in groups:
            if len(members) < 2:
                continue
            for row, farmer_id in members.items():
                others = ", ".join(members.drop(row))
                findings.setdefault(row, []).append((severity, f"same {label} ({value}) as {others}"))

    rows = sorted(findings)
    severities = [ERROR if any(s == ERROR for s, _ in findings[r]) else WARNING for r in rows]
    messages = ["; ".join(text for _, text in findings[r]) for r in rows]
    return _flags(registrations.loc[rows, "farmer_id"], "duplicate_registration", severities, messages)


def future_registration_date(registrations: pd.DataFrame, as_of: date = config.EXPORT_DATE) -> pd.DataFrame:
    """Flag registration dates after the export date, or that are not dates at all.

    Blank dates are left to required_fields_missing.

    Args:
        registrations: Farmer registrations, registration_date as "YYYY-MM-DD".
        as_of: The latest possible date (the survey export date).

    Returns:
        One error per bad date.
    """
    raw = registrations["registration_date"]
    parsed = pd.to_datetime(raw, format="%Y-%m-%d", errors="coerce")
    unparseable = ~is_blank(raw) & parsed.isna()
    future = parsed > pd.Timestamp(as_of)

    flagged = unparseable | future
    messages = [
        f"registration date '{value}' is not a valid YYYY-MM-DD date"
        if bad_format
        else f"registration date {value} is after the export date {as_of.isoformat()}"
        for value, bad_format in zip(raw[flagged], unparseable[flagged])
    ]
    return _flags(registrations.loc[flagged, "farmer_id"], "future_registration_date", ERROR, messages)


# --- GPS point checks ----------------------------------------------------------


def gps_invalid(
    registrations: pd.DataFrame, bbox: tuple[float, float, float, float] = config.KENYA_BBOX
) -> pd.DataFrame:
    """Flag GPS points that cannot be right: 0,0, outside Kenya, or swapped.

    Points on the equator (latitude 0) are legitimate in Kenya, so only an
    exact 0,0 pair counts as "no fix". A point outside the box that lands
    inside it once latitude and longitude are swapped is reported as
    "likely swapped". Missing coordinates are left to required_fields_missing.

    Args:
        registrations: Farmer registrations.
        bbox: (min_lon, min_lat, max_lon, max_lat) of Kenya.

    Returns:
        One error per bad point.
    """
    lat, lon = _coordinates(registrations)
    typed = registrations["latitude"].notna() & registrations["longitude"].notna()
    not_numeric = typed & (lat.isna() | lon.isna())
    present = lat.notna() & lon.notna()
    null_island = present & (lat == 0) & (lon == 0)
    outside = present & ~null_island & ~_in_bbox(lon, lat, bbox)
    swapped = outside & _in_bbox(lat, lon, bbox)  # swap them back: now in Kenya?

    flagged = not_numeric | null_island | outside
    messages = np.select(
        [not_numeric[flagged], null_island[flagged], swapped[flagged]],
        [
            "latitude/longitude is not a number",
            "GPS is 0,0 (no fix was captured)",
            "GPS is outside Kenya; latitude and longitude look swapped",
        ],
        default="GPS is outside Kenya's bounding box",
    )
    details = [f" (lat {a}, lon {o})" for a, o in zip(registrations.loc[flagged, "latitude"], registrations.loc[flagged, "longitude"])]
    messages = [m + d for m, d in zip(messages, details)]
    return _flags(registrations.loc[flagged, "farmer_id"], "gps_invalid", ERROR, messages)


def gps_outside_county(
    registrations: pd.DataFrame,
    counties: gpd.GeoDataFrame,
    bbox: tuple[float, float, float, float] = config.KENYA_BBOX,
) -> pd.DataFrame:
    """Flag GPS points that are not inside the farmer's registered county.

    Points outside Kenya's bounding box and records with no county are
    skipped (gps_invalid and required_fields_missing report those).

    Args:
        registrations: Farmer registrations.
        counties: County boundaries with a shapeName column.
        bbox: Kenya's bounding box.

    Returns:
        One error per point in the wrong county, or in no county at all.
    """
    points = _usable_points(registrations, bbox)
    points = points[~is_blank(points["county"])]
    polygons = counties[[COUNTY_NAME_COLUMN, "geometry"]].to_crs(points.crs)

    joined = gpd.sjoin(points, polygons, how="left", predicate="intersects")
    found = joined.groupby(level=0)[COUNTY_NAME_COLUMN].agg(lambda names: list(names.dropna()))

    ids, messages = [], []
    for row, point in points.iterrows():
        registered = point["county"]
        actual = found[row]
        if normalise_county_name(registered) in {normalise_county_name(n) for n in actual}:
            continue
        ids.append(point["farmer_id"])
        if actual:
            messages.append(f"GPS point is in {' / '.join(actual)}, but the farmer is registered in {registered}")
        else:
            messages.append(f"GPS point is not inside any Kenyan county (registered in {registered})")
    return _flags(ids, "gps_outside_county", ERROR, messages)


# --- Farm polygon checks ---------------------------------------------------


def polygon_invalid(farms: gpd.GeoDataFrame) -> pd.DataFrame:
    """Flag farm geometries that are missing, not polygons, or invalid.

    Invalid includes self-intersecting boundaries; the message carries
    shapely's explain_validity, e.g. "Self-intersection[36.07 -0.30]",
    which gives the location of the problem.

    Args:
        farms: Farm polygons with farmer_id.

    Returns:
        One error per bad geometry.
    """
    geoms = farms.geometry
    missing = geoms.isna() | geoms.is_empty
    wrong_type = ~missing & ~geoms.geom_type.isin(POLYGON_TYPES)
    invalid = ~missing & ~wrong_type & ~geoms.is_valid

    flagged = missing | wrong_type | invalid
    messages = []
    for geom, is_missing, is_wrong_type in zip(geoms[flagged], missing[flagged], wrong_type[flagged]):
        if is_missing:
            messages.append("farm boundary is missing or empty")
        elif is_wrong_type:
            messages.append(f"farm boundary is a {geom.geom_type}, not a polygon")
        else:
            messages.append(f"invalid polygon: {explain_validity(geom)}")
    return _flags(farms.loc[flagged, "farmer_id"], "polygon_invalid", ERROR, messages)


def farm_area_implausible(
    farms: gpd.GeoDataFrame,
    min_acres: float = config.MIN_PLAUSIBLE_FARM_ACRES,
    max_acres: float = config.MAX_PLAUSIBLE_FARM_ACRES,
) -> pd.DataFrame:
    """Flag farms whose area is implausibly small or large.

    Area is measured in metres in each farm's UTM zone, never in degrees.
    Invalid polygons are skipped: their area is not meaningful.

    Args:
        farms: Farm polygons with farmer_id.
        min_acres: Smallest plausible farm.
        max_acres: Largest plausible farm.

    Returns:
        One error per implausible farm, stating its area.
    """
    measurable = _measurable_farms(farms)
    area_m2 = area_m2_series(measurable.geometry)
    acres = area_m2 / SQUARE_METRES_PER_ACRE

    too_small = acres < min_acres
    too_large = acres > max_acres
    flagged = too_small | too_large
    messages = [
        f"farm area {a:.3f} acres ({m:,.0f} sq m) is below the plausible minimum of {min_acres} acres"
        if small
        else f"farm area {a:,.1f} acres is above the plausible maximum of {max_acres} acres"
        for a, m, small in zip(acres[flagged], area_m2[flagged], too_small[flagged])
    ]
    return _flags(measurable.loc[flagged, "farmer_id"], "farm_area_implausible", ERROR, messages)


def farm_point_outside_polygon(
    registrations: pd.DataFrame,
    farms: gpd.GeoDataFrame,
    max_distance_m: float = config.MAX_POINT_TO_FARM_M,
    bbox: tuple[float, float, float, float] = config.KENYA_BBOX,
) -> pd.DataFrame:
    """Flag registration points more than max_distance_m from their own farm.

    Distance is 0 inside the farm and measured to the nearest boundary edge
    outside it, in metres in the farm's UTM zone. Points outside Kenya and
    farms with unusable geometry are skipped (other checks report them).
    A warning, not an error: enumerators often capture GPS at the homestead.

    Args:
        registrations: Farmer registrations.
        farms: Farm polygons with farmer_id.
        max_distance_m: Largest acceptable distance.
        bbox: Kenya's bounding box.

    Returns:
        One warning per point too far from its farm.
    """
    points = _usable_points(registrations, bbox)
    if points.empty or farms.empty:  # merging an empty table can hit a key dtype mismatch
        return _flags([], "farm_point_outside_polygon", WARNING, [])
    paired = points.merge(
        _measurable_farms(farms)[["farmer_id", "geometry"]].rename(columns={"geometry": "farm"}),
        on="farmer_id",
    )
    point_geoms = gpd.GeoSeries(paired.geometry, crs=WGS84)
    farm_geoms = gpd.GeoSeries(paired["farm"], crs=farms.crs)

    zones = projected_crs_for_geoseries(farm_geoms)
    distance_m = pd.Series(float("nan"), index=paired.index)
    for crs in zones.unique():
        in_zone = zones == crs
        distance_m[in_zone] = point_geoms[in_zone].to_crs(crs).distance(farm_geoms[in_zone].to_crs(crs))

    flagged = distance_m > max_distance_m
    messages = [
        f"registration point is {d:,.0f} m from its farm boundary (limit {max_distance_m:,.0f} m)"
        for d in distance_m[flagged]
    ]
    return _flags(paired.loc[flagged, "farmer_id"], "farm_point_outside_polygon", WARNING, messages)


def farm_overlap(farms: gpd.GeoDataFrame, min_fraction: float = config.MIN_OVERLAP_FRACTION) -> pd.DataFrame:
    """Flag pairs of farms that overlap by more than min_fraction of the smaller one.

    Candidate pairs come from a spatial index (fast, works in any CRS). Each
    pair's overlap is then measured with both farms in the same UTM zone.
    Both farms in a pair are flagged, each naming the other.

    Args:
        farms: Farm polygons with farmer_id.
        min_fraction: Overlap share of the smaller farm above which to flag.

    Returns:
        One error per farm per overlapping partner.
    """
    valid = _measurable_farms(farms).reset_index(drop=True)
    left, right = valid.sindex.query(valid.geometry, predicate="intersects")
    keep = left < right  # drop self-matches and the mirror copy of each pair
    left, right = left[keep], right[keep]

    a = valid.geometry.iloc[left].reset_index(drop=True)
    b = valid.geometry.iloc[right].reset_index(drop=True)
    zones = projected_crs_for_geoseries(a)
    fraction = pd.Series(float("nan"), index=a.index)
    for crs in zones.unique():
        in_zone = zones == crs
        a_m, b_m = a[in_zone].to_crs(crs), b[in_zone].to_crs(crs)
        smaller = np.minimum(a_m.area, b_m.area)
        fraction[in_zone] = a_m.intersection(b_m).area / smaller

    heavy = (fraction > min_fraction).to_numpy()
    ids_a = valid["farmer_id"].iloc[left[heavy]].tolist()
    ids_b = valid["farmer_id"].iloc[right[heavy]].tolist()
    shares = fraction[heavy].tolist()
    ids = ids_a + ids_b
    messages = [f"overlaps {other} by {s:.0%} of the smaller farm" for other, s in zip(ids_b + ids_a, shares + shares)]
    return _flags(ids, "farm_overlap", ERROR, messages)


# --- All together --------------------------------------------------------------


def run_all_checks(
    registrations: pd.DataFrame, farms: gpd.GeoDataFrame, counties: gpd.GeoDataFrame
) -> pd.DataFrame:
    """Run every check and combine the flags.

    Args:
        registrations: Farmer registrations.
        farms: Farm polygons with farmer_id.
        counties: County boundaries.

    Returns:
        All flags, in check order.
    """
    results = [
        required_fields_missing(registrations),
        duplicate_registration(registrations),
        future_registration_date(registrations),
        gps_invalid(registrations),
        gps_outside_county(registrations, counties),
        polygon_invalid(farms),
        farm_area_implausible(farms),
        farm_point_outside_polygon(registrations, farms),
        farm_overlap(farms),
    ]
    flags = pd.concat(results, ignore_index=True)
    for check_id, n in flags["check_id"].value_counts(sort=False).items():
        logger.info("%-28s %d flags", check_id, n)
    return flags
