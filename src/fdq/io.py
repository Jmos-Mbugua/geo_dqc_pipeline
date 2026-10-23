"""Read and write the project's data files.

All file access lives here so the rest of the package can stay pure.
"""

from pathlib import Path

import folium

import geopandas as gpd
import pandas as pd

from fdq.geo import WGS84
from fdq.schema import SURVEY_COLUMNS, TEXT_COLUMNS

GEOJSON_COORDINATE_PRECISION = 7  # decimal places (~1 cm)


def read_counties(path: Path) -> gpd.GeoDataFrame:
    """Read the county boundaries GeoJSON.

    Args:
        path: Path to kenya_counties.geojson.

    Returns:
        County boundaries in EPSG:4326.
    """
    return gpd.read_file(path)


def write_registrations(survey: pd.DataFrame, path: Path) -> None:
    """Write farmer registrations to CSV (points as latitude/longitude columns).

    Args:
        survey: Records with at least the survey columns.
        path: Output CSV path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    survey[SURVEY_COLUMNS].to_csv(path, index=False)


def read_registrations(path: Path) -> pd.DataFrame:
    """Read farmer registrations, keeping IDs and phone numbers as text.

    Args:
        path: Path to farmer_registrations.csv.

    Returns:
        The registrations; latitude and longitude are floats, everything
        else is text, and blanks are missing values.
    """
    return pd.read_csv(path, dtype={col: "str" for col in TEXT_COLUMNS})


def write_farm_boundaries(survey: gpd.GeoDataFrame, path: Path) -> None:
    """Write farm polygons with their farmer_id to GeoJSON (EPSG:4326).

    Args:
        survey: Records with farmer_id and polygon geometry.
        path: Output GeoJSON path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    farms = survey[["farmer_id", "geometry"]].to_crs(WGS84)
    farms.to_file(path, driver="GeoJSON", COORDINATE_PRECISION=GEOJSON_COORDINATE_PRECISION)


def read_farm_boundaries(path: Path) -> gpd.GeoDataFrame:
    """Read farm polygons.

    Args:
        path: Path to farm_boundaries.geojson.

    Returns:
        farmer_id and polygon geometry in EPSG:4326.
    """
    return gpd.read_file(path)


def write_ground_truth(truth: pd.DataFrame, path: Path) -> None:
    """Write the planted-errors ground truth to CSV.

    Args:
        truth: farmer_id, error_type, related_farmer_id, details.
        path: Output CSV path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    truth.to_csv(path, index=False)


def read_ground_truth(path: Path) -> pd.DataFrame:
    """Read the planted-errors ground truth (simulated data only).

    Args:
        path: Path to planted_errors.csv.

    Returns:
        farmer_id, error_type, related_farmer_id, details, all as text.
    """
    return pd.read_csv(path, dtype="str")


def write_issues(issues: pd.DataFrame, path: Path) -> None:
    """Write the issues table to CSV, one row per issue.

    Written with a UTF-8 byte-order mark so Excel shows any non-ASCII
    characters in names and messages correctly.

    Args:
        issues: The pipeline's issues table.
        path: Output CSV path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    issues.to_csv(path, index=False, encoding="utf-8-sig")


def write_text(text: str, path: Path) -> None:
    """Write a text file (e.g. the Markdown summary) as UTF-8.

    Args:
        text: File contents.
        path: Output path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_map(fmap: folium.Map, path: Path) -> None:
    """Save a folium map as a standalone HTML page.

    Args:
        fmap: The map.
        path: Output HTML path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(path))
