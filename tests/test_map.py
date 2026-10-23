import html

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon, box

from fdq.geo import area_m2_series, to_degrees, to_metres
from fdq.map import (
    CLEAN,
    build_map,
    farm_layer_data,
    farm_status,
    popup_html,
    redact_message,
    round_coordinates,
    simplify_counties,
)
from fdq.schema import SURVEY_COLUMNS

LON, LAT = 36.07, -0.30
BOWTIE = Polygon([(LON, LAT), (LON + 0.001, LAT + 0.001), (LON + 0.001, LAT), (LON, LAT + 0.001)])


def _issues(*rows: tuple) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["farmer_id", "check_id", "severity", "message"])


@pytest.fixture
def data():
    """Three farms: clean, warning only, error (a duplicate pair shares F3's identifiers)."""
    registrations = pd.DataFrame(
        [
            ["F1", "Grace Wanjiru", "23456789", "0712345678", "Nakuru", "Njoro", "maize", "2026-03-01", "E1", LAT, LON],
            ["F2", "Peter Kamau", "34567890", "0723456789", "Nakuru", "Njoro", "<b>beans</b>", "2026-03-01", "E1", LAT, LON + 0.01],
            ["F3", "Mary Wafula", "45678901", "0734567890", None, "Njoro", "wheat", "2026-03-01", "E1", LAT, LON + 0.02],
        ],
        columns=SURVEY_COLUMNS,
    )
    farms = gpd.GeoDataFrame(
        {"farmer_id": ["F1", "F2", "F3"]},
        geometry=[box(LON, LAT, LON + 0.0005, LAT + 0.0005), box(LON + 0.01, LAT, LON + 0.0105, LAT + 0.0005), BOWTIE],
        crs="EPSG:4326",
    )
    counties = gpd.GeoDataFrame({"shapeName": ["Nakuru"]}, geometry=[box(35.9, -0.6, 36.3, -0.2)], crs="EPSG:4326")
    issues = _issues(
        ("F2", "farm_point_outside_polygon", "warning", "registration point is 300 m from its farm boundary"),
        ("F3", "duplicate_registration", "error", "same national_id (45678901) as F9; same phone (0734567890) as F9"),
        ("F3", "polygon_invalid", "error", "invalid polygon: Self-intersection[36.0705 -0.2995]"),
    )
    return registrations, farms, counties, issues


def test_farm_status():
    ids = pd.Series(["F1", "F2", "F3"])
    issues = _issues(("F2", "x", "warning", ""), ("F3", "x", "warning", ""), ("F3", "y", "error", ""))
    assert farm_status(ids, issues).tolist() == [CLEAN, "warning", "error"]


def test_redact_message_removes_identifiers():
    message = "same national_id (45678901) as F9; same phone (0734567890) as F9, F10"
    redacted = redact_message("duplicate_registration", message)
    assert redacted == "same national ID as F9; same phone number as F9, F10"
    assert "45678901" not in redacted and "0734567890" not in redacted


def test_redact_message_leaves_other_checks_alone():
    message = "GPS is 0,0 (no fix was captured) (lat 0.0, lon 0.0)"
    assert redact_message("gps_invalid", message) == message


def test_popup_escapes_html():
    issues = _issues(("F1", "x", "error", "<script>alert(1)</script>"))
    html = popup_html("F1", "Nakuru", "<img src=x onerror=alert(1)>", 1.0, "error", issues)
    assert "<script>" not in html and "<img" not in html
    assert "&lt;script&gt;" in html


def test_farm_layer_data(data):
    registrations, farms, _, issues = data
    layer = farm_layer_data(registrations, farms, issues)
    assert list(layer.columns) == ["farmer_id", "status", "popup", "geometry"]  # nothing else carried over
    assert layer["status"].tolist() == [CLEAN, "warning", "error"]
    popups = dict(zip(layer["farmer_id"], layer["popup"]))
    assert "No issues" in popups["F1"]
    assert "n/a (invalid polygon)" in popups["F3"]
    assert "County: (blank)" in popups["F3"]
    assert "&lt;b&gt;beans&lt;/b&gt;" in popups["F2"]


def test_popup_area_is_measured_in_metres():
    side_m = 63.6149  # one acre
    x, y = to_metres(gpd.points_from_xy([LON], [LAT])[0], "EPSG:21037").coords[0]
    farm = to_degrees(box(x, y, x + side_m, y + side_m), "EPSG:21037")
    registrations = pd.DataFrame([["F1", "", "1", "0", "Nakuru", "", "maize", "", "", LAT, LON]], columns=SURVEY_COLUMNS)
    farms = gpd.GeoDataFrame({"farmer_id": ["F1"]}, geometry=[farm], crs="EPSG:4326")
    layer = farm_layer_data(registrations, farms, _issues())
    assert "Area: 1.00 acres" in layer["popup"].iloc[0]


def test_simplify_counties_reduces_vertices_and_keeps_crs():
    from shapely.geometry import Point

    wiggly = Point(LON, LAT).buffer(0.2, quad_segs=256)  # ~1000 vertices, radius ~22 km
    counties = gpd.GeoDataFrame({"shapeName": ["Round"], "extra": [1]}, geometry=[wiggly], crs="EPSG:4326")
    simple = simplify_counties(counties, tolerance_m=250)
    assert simple.crs.to_epsg() == 4326
    assert list(simple.columns) == ["shapeName", "geometry"]
    assert simple.count_coordinates().sum() < len(wiggly.exterior.coords) / 4
    # Area barely changes: simplification stays within 250 m of the outline.
    before, after = area_m2_series(counties.geometry).iloc[0], area_m2_series(simple.geometry).iloc[0]
    assert after == pytest.approx(before, rel=0.02)


def test_round_coordinates_keeps_invalid_polygons_invalid():
    gdf = gpd.GeoDataFrame(geometry=[BOWTIE], crs="EPSG:4326")
    rounded = round_coordinates(gdf, 4)
    assert not rounded.is_valid.iloc[0]


def test_map_html_has_legend_title_and_no_personal_data(data, tmp_path):
    registrations, farms, counties, issues = data
    path = tmp_path / "map.html"
    build_map(registrations, farms, counties, issues).save(str(path))
    page = path.read_text(encoding="utf-8")

    assert "Simulated data" in page
    assert "Farm status" in page and "At least one error (1)" in page and "Clean (1)" in page
    assert "same national ID as F9" in page
    # Popup HTML is stored JSON-encoded ("<" becomes "<"), so look for each
    # value both as-is and HTML-escaped.
    for column in ("farmer_name", "national_id", "phone"):
        for value in registrations[column].dropna():
            for form in {value, html.escape(value)}:
                assert form not in page, f"{column} value {value!r} leaked into the map"
