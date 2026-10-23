"""Tests for fdq.checks, using small hand-made fixtures (2 to 5 rows).

Locations are near Nakuru town (36.07 E, 0.30 S). Farm squares are built in
metres and converted to degrees, so their true size is known exactly.
"""

from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Polygon, box

from fdq import checks
from fdq.geo import SQUARE_METRES_PER_ACRE, to_degrees, to_metres
from fdq.schema import SURVEY_COLUMNS

LON, LAT = 36.07, -0.30
CRS = "EPSG:21037"
X0, Y0 = to_metres(gpd.points_from_xy([LON], [LAT])[0], CRS).coords[0]


# --- Fixture builders ----------------------------------------------------------


def registration(farmer_id: str, **overrides) -> dict:
    """One clean registration row; override any field."""
    row = {
        "farmer_id": farmer_id,
        "farmer_name": "Grace Wanjiru",
        "national_id": f"2{farmer_id[-7:].zfill(7)}",
        "phone": f"07{farmer_id[-8:].zfill(8)}",
        "county": "Nakuru",
        "ward": "Njoro",
        "crop": "maize",
        "registration_date": "2026-03-10",
        "enumerator_id": "ENUM-NKR-01",
        "latitude": LAT,
        "longitude": LON,
    }
    row.update(overrides)
    return row


def registrations(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=SURVEY_COLUMNS)


def square(east_m: float, north_m: float, side_m: float) -> Polygon:
    """A square farm in EPSG:4326 whose south-west corner is (east_m, north_m) from Nakuru."""
    x, y = X0 + east_m, Y0 + north_m
    return to_degrees(box(x, y, x + side_m, y + side_m), CRS)


def farms(geoms: dict) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"farmer_id": list(geoms)}, geometry=list(geoms.values()), crs="EPSG:4326")


ONE_ACRE_SIDE = SQUARE_METRES_PER_ACRE**0.5  # ~63.6 m


@pytest.fixture
def counties() -> gpd.GeoDataFrame:
    """Two neighbouring fake counties sharing the border at latitude -0.2."""
    return gpd.GeoDataFrame(
        {"shapeName": ["Nakuru", "Baringo"]},
        geometry=[box(35.9, -0.6, 36.3, -0.2), box(35.9, -0.2, 36.3, 0.4)],
        crs="EPSG:4326",
    )


def flagged_ids(flags: pd.DataFrame) -> list:
    assert list(flags.columns) == checks.FLAG_COLUMNS
    return sorted(flags["farmer_id"])


# --- Empty input: every check returns an empty table with the right columns ------


def test_all_checks_handle_empty_input(counties):
    empty_regs = registrations()
    empty_farms = farms({})
    results = [
        checks.required_fields_missing(empty_regs),
        checks.duplicate_registration(empty_regs),
        checks.future_registration_date(empty_regs),
        checks.gps_invalid(empty_regs),
        checks.gps_outside_county(empty_regs, counties),
        checks.polygon_invalid(empty_farms),
        checks.farm_area_implausible(empty_farms),
        checks.farm_point_outside_polygon(empty_regs, empty_farms),
        checks.farm_overlap(empty_farms),
    ]
    for result in results:
        assert list(result.columns) == checks.FLAG_COLUMNS
        assert result.empty


# --- required_fields_missing -------------------------------------------------------


def test_required_fields_missing_catches_blanks():
    data = registrations(
        registration("F1", national_id=None),
        registration("F2", crop="  N/A ", latitude=np.nan, longitude=np.nan),
        registration("F3"),
    )
    flags = checks.required_fields_missing(data)
    assert flagged_ids(flags) == ["F1", "F2"]
    assert (flags["severity"] == "error").all()
    assert flags.set_index("farmer_id").loc["F2", "message"].endswith("crop, latitude, longitude")


def test_required_fields_missing_passes_clean_data():
    data = registrations(registration("F1"), registration("F2", ward=None))  # ward is optional
    assert checks.required_fields_missing(data).empty


# --- duplicate_registration --------------------------------------------------------


def test_duplicate_registration_flags_both_records():
    data = registrations(
        registration("F1", national_id="23456789", farmer_name="Grace Wanjiru"),
        registration("F2", national_id="23456789", farmer_name="Grace Wanjiu"),
        registration("F3"),
    )
    flags = checks.duplicate_registration(data).set_index("farmer_id")
    assert sorted(flags.index) == ["F1", "F2"]
    assert (flags["severity"] == "error").all()
    assert "F2" in flags.loc["F1", "message"]
    assert "F1" in flags.loc["F2", "message"]


def test_duplicate_phone_in_different_formats_is_a_warning():
    data = registrations(
        registration("F1", phone="0712345678"),
        registration("F2", phone="+254 712 345 678"),
    )
    flags = checks.duplicate_registration(data)
    assert flagged_ids(flags) == ["F1", "F2"]
    assert (flags["severity"] == "warning").all()


def test_duplicate_registration_passes_clean_data():
    data = registrations(registration("F1"), registration("F2"), registration("F3", national_id=None, phone=None))
    assert checks.duplicate_registration(data).empty


def test_blank_ids_are_not_duplicates_of_each_other():
    data = registrations(registration("F1", national_id=""), registration("F2", national_id="N/A"))
    assert checks.duplicate_registration(data).empty


# --- future_registration_date ------------------------------------------------------


def test_future_registration_date_catches_future_and_garbage():
    data = registrations(
        registration("F1", registration_date="2062-03-06"),
        registration("F2", registration_date="06/03/2026"),
        registration("F3"),
    )
    flags = checks.future_registration_date(data, as_of=date(2026, 6, 30)).set_index("farmer_id")
    assert sorted(flags.index) == ["F1", "F2"]
    assert "after the export date" in flags.loc["F1", "message"]
    assert "not a valid" in flags.loc["F2", "message"]


def test_future_registration_date_passes_clean_data():
    data = registrations(
        registration("F1", registration_date="2026-06-30"),  # on the export date: fine
        registration("F2", registration_date=None),  # blank: required_fields_missing's job
    )
    assert checks.future_registration_date(data, as_of=date(2026, 6, 30)).empty


# --- gps_invalid -------------------------------------------------------------------


def test_gps_invalid_catches_null_island_swapped_and_outside():
    data = registrations(
        registration("F1", latitude=0.0, longitude=0.0),
        registration("F2", latitude=LON, longitude=LAT),
        registration("F3", latitude=51.5, longitude=-0.12),  # London
        registration("F4"),
    )
    flags = checks.gps_invalid(data).set_index("farmer_id")
    assert sorted(flags.index) == ["F1", "F2", "F3"]
    assert "0,0" in flags.loc["F1", "message"]
    assert "swapped" in flags.loc["F2", "message"]
    assert "bounding box" in flags.loc["F3", "message"]


def test_gps_invalid_passes_clean_data_including_the_equator():
    data = registrations(
        registration("F1"),
        registration("F2", latitude=0.0, longitude=37.65),  # on the equator in Meru: real
        registration("F3", latitude=np.nan, longitude=np.nan),  # missing: not this check's job
    )
    assert checks.gps_invalid(data).empty


# --- gps_outside_county ------------------------------------------------------------


def test_gps_outside_county_catches_wrong_and_no_county(counties):
    data = registrations(
        registration("F1", latitude=0.1),  # in Baringo, registered Nakuru
        registration("F2", longitude=34.2),  # inside Kenya's box, but in neither fake county
        registration("F3"),
    )
    flags = checks.gps_outside_county(data, counties).set_index("farmer_id")
    assert sorted(flags.index) == ["F1", "F2"]
    assert "is in Baringo" in flags.loc["F1", "message"]
    assert "not inside any" in flags.loc["F2", "message"]


def test_gps_outside_county_passes_clean_data_and_edge_cases(counties):
    data = registrations(
        registration("F1"),
        registration("F2", county=" nakuru "),  # case and spaces differ
        registration("F3", latitude=-0.2),  # exactly on the shared border
        registration("F4", latitude=0.0, longitude=0.0),  # outside Kenya: gps_invalid's job
        registration("F5", county=None),  # blank county: required_fields_missing's job
    )
    assert checks.gps_outside_county(data, counties).empty


def test_county_name_normalisation():
    assert checks.normalise_county_name("Tharaka-Nithi") == "tharaka"
    assert checks.normalise_county_name("Murang'a") == checks.normalise_county_name("muranga")
    assert checks.normalise_county_name("Elgeyo-Marakwet") == checks.normalise_county_name("Elgeyo Marakwet")


# --- polygon_invalid ---------------------------------------------------------------


def test_polygon_invalid_catches_self_intersection_and_bad_types():
    bowtie = Polygon([(LON, LAT), (LON + 0.001, LAT + 0.001), (LON + 0.001, LAT), (LON, LAT + 0.001)])
    data = farms(
        {
            "F1": bowtie,
            "F2": LineString([(LON, LAT), (LON + 0.001, LAT)]),
            "F3": None,
            "F4": square(0, 0, 50),
        }
    )
    flags = checks.polygon_invalid(data).set_index("farmer_id")
    assert sorted(flags.index) == ["F1", "F2", "F3"]
    assert "Self-intersection" in flags.loc["F1", "message"]
    assert "LineString" in flags.loc["F2", "message"]
    assert "missing" in flags.loc["F3", "message"]


def test_polygon_invalid_passes_clean_data():
    assert checks.polygon_invalid(farms({"F1": square(0, 0, 50), "F2": square(500, 0, 80)})).empty


# --- farm_area_implausible ---------------------------------------------------------


def test_farm_area_implausible_catches_tiny_and_huge():
    data = farms(
        {
            "F1": square(0, 0, 5),  # 25 m², about 0.006 acres
            "F2": square(1000, 0, ONE_ACRE_SIDE * 5),  # 25 acres
            "F3": square(3000, 0, ONE_ACRE_SIDE),  # 1 acre
        }
    )
    flags = checks.farm_area_implausible(data).set_index("farmer_id")
    assert sorted(flags.index) == ["F1", "F2"]
    assert "below" in flags.loc["F1", "message"]
    assert "25.0 acres" in flags.loc["F2", "message"]


def test_farm_area_implausible_passes_clean_data():
    # 1 acre in degrees is about 3e-7 "square degrees": measuring without
    # projecting would wrongly call it tiny. These must pass.
    data = farms({"F1": square(0, 0, ONE_ACRE_SIDE), "F2": square(500, 0, ONE_ACRE_SIDE * 3)})
    assert checks.farm_area_implausible(data).empty


def test_farm_area_implausible_skips_invalid_and_missing():
    bowtie = Polygon([(LON, LAT), (LON + 0.001, LAT + 0.001), (LON + 0.001, LAT), (LON, LAT + 0.001)])
    assert checks.farm_area_implausible(farms({"F1": bowtie, "F2": None})).empty


# --- farm_point_outside_polygon ----------------------------------------------------


def test_farm_point_outside_polygon_catches_far_point():
    data = registrations(registration("F1"), registration("F2"))
    farm_data = farms({"F1": square(500, 0, 50), "F2": square(-25, -25, 50)})  # F1's farm is 500 m east
    flags = checks.farm_point_outside_polygon(data, farm_data)
    assert flagged_ids(flags) == ["F1"]
    assert flags["severity"].iloc[0] == "warning"
    assert "500 m" in flags["message"].iloc[0]


def test_farm_point_outside_polygon_passes_clean_data():
    data = registrations(registration("F1"), registration("F2"), registration("F3", latitude=0.0, longitude=0.0))
    farm_data = farms(
        {
            "F1": square(-25, -25, 50),  # point inside
            "F2": square(150, 0, 50),  # 150 m away: within the 200 m limit
            "F3": square(-25, -25, 50),  # point at 0,0: gps_invalid's job
        }
    )
    assert checks.farm_point_outside_polygon(data, farm_data).empty


# --- farm_overlap ------------------------------------------------------------------


def test_farm_overlap_flags_both_farms():
    data = farms(
        {
            "F1": square(0, 0, 100),
            "F2": square(50, 0, 100),  # half of F1 covered
            "F3": square(1000, 0, 100),
        }
    )
    flags = checks.farm_overlap(data).set_index("farmer_id")
    assert sorted(flags.index) == ["F1", "F2"]
    assert flags.loc["F1", "message"] == "overlaps F2 by 50% of the smaller farm"
    assert flags.loc["F2", "message"] == "overlaps F1 by 50% of the smaller farm"


def test_farm_overlap_passes_clean_data():
    data = farms(
        {
            "F1": square(0, 0, 100),
            "F2": square(100, 0, 100),  # shares an edge only
            "F3": square(0, 90, 100),  # overlaps F1 by 10%: under the 20% threshold
        }
    )
    assert checks.farm_overlap(data).empty


def test_farm_overlap_ignores_invalid_polygons():
    bowtie = Polygon([(LON, LAT), (LON + 0.001, LAT + 0.001), (LON + 0.001, LAT), (LON, LAT + 0.001)])
    assert checks.farm_overlap(farms({"F1": bowtie, "F2": square(0, 0, 100)})).empty


# --- run_all_checks ----------------------------------------------------------------


def test_run_all_checks_combines_results(counties):
    data = registrations(registration("F1", national_id=None), registration("F2"))
    farm_data = farms({"F1": square(-25, -25, 50), "F2": square(5000, 0, 50)})
    flags = checks.run_all_checks(data, farm_data, counties)
    assert sorted(flags["check_id"]) == ["farm_point_outside_polygon", "required_fields_missing"]
