import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from fdq.geo import area_acres, area_m2, overlap_fraction
from fdq.synthetic.generate import EXPORT_DATE, find_overlapping, make_farm
from fdq.synthetic.plant import (
    ERROR_COUNTS,
    LARGE_FARM_ACRES,
    OVERLAP_FRACTION_RANGE,
    TINY_FARM_M2,
    TRUTH_COLUMNS,
    make_self_intersecting,
    misspell_name,
    overlap_onto,
    plant_errors,
    relocate_farm,
    scale_farm,
    year_typo,
)

# --- Pure helpers ----------------------------------------------------------


@pytest.fixture
def farm() -> tuple:
    point = Point(36.07, -0.30)
    return make_farm(point, np.random.default_rng(0)), point


def test_scale_farm_hits_target_area(farm):
    polygon, point = farm
    scaled = scale_farm(polygon, point, 25.0)
    assert area_m2(scaled) == pytest.approx(25.0, rel=1e-3)
    assert scaled.contains(point)


def test_relocate_farm_keeps_area_across_zones(farm):
    polygon, point = farm
    new_point = Point(34.75, 0.28)  # west of 36°E: a different UTM zone
    moved = relocate_farm(polygon, point, new_point)
    assert moved.contains(new_point)
    assert area_m2(moved) == pytest.approx(area_m2(polygon), rel=0.01)


def test_make_self_intersecting(farm):
    polygon, _ = farm
    bowtie = make_self_intersecting(polygon, np.random.default_rng(0))
    assert polygon.is_valid
    assert not bowtie.is_valid
    # Same vertices, different order.
    assert sorted(bowtie.exterior.coords[:-1]) == sorted(polygon.exterior.coords[:-1])


@pytest.mark.parametrize("seed", range(20))
def test_misspell_name_is_similar_but_different(seed):
    name = "Grace Wanjiku"
    new = misspell_name(name, np.random.default_rng(seed))
    assert new != name
    assert abs(len(new) - len(name)) <= 1
    assert new[0].isupper()


def test_year_typo():
    assert year_typo("2026-03-14") == "2062-03-14"
    assert year_typo("2025-12-01") == "2052-12-01"


def test_overlap_onto(farm):
    target, _ = farm
    other_point = Point(36.2, -0.35)
    other = make_farm(other_point, np.random.default_rng(1))
    moved, moved_point, fraction = overlap_onto(target, other, other_point, 0.6, np.random.default_rng(0))
    assert fraction >= 0.6
    assert overlap_fraction(target, moved) == pytest.approx(fraction, abs=0.01)
    assert moved.contains(moved_point)


# --- The planted survey ---------------------------------------------------


def _rows(planted, error_type: str) -> pd.DataFrame:
    survey, truth = planted
    ids = truth.loc[truth["error_type"] == error_type, "farmer_id"]
    return survey[survey["farmer_id"].isin(ids)]


def test_truth_counts(planted):
    survey, truth = planted
    assert list(truth.columns) == TRUTH_COLUMNS
    assert truth["farmer_id"].is_unique  # at most one error per record
    expected = {k: v * (2 if k == "farm_overlap" else 1) for k, v in ERROR_COUNTS.items()}
    assert truth["error_type"].value_counts().to_dict() == expected
    assert len(survey) == 200


def test_untouched_records_unchanged(planted, clean_survey):
    survey, truth = planted
    untouched = ~survey["farmer_id"].isin(truth["farmer_id"])
    assert survey[untouched].equals(clean_survey[untouched])


def test_input_not_modified(clean_survey, county_polygons):
    before = clean_survey.copy()
    plant_errors(clean_survey, county_polygons, np.random.default_rng(5))
    assert clean_survey.equals(before)


def test_gps_outside_county(planted, county_polygons):
    for _, row in _rows(planted, "gps_outside_county").iterrows():
        point = Point(row["longitude"], row["latitude"])
        assert not county_polygons[row["county"]].contains(point)
        assert row["geometry"].contains(point)


def test_gps_null_island(planted):
    rows = _rows(planted, "gps_null_island")
    assert (rows["latitude"] == 0).all()
    assert (rows["longitude"] == 0).all()


def test_gps_latlon_swapped(planted):
    rows = _rows(planted, "gps_latlon_swapped")
    assert (rows["latitude"] > 30).all()  # Kenya's latitudes are within about ±5
    assert (rows["longitude"].abs() < 2).all()


def test_self_intersecting(planted):
    survey, _ = planted
    assert not _rows(planted, "polygon_self_intersecting").is_valid.any()
    assert (~survey.is_valid).sum() == ERROR_COUNTS["polygon_self_intersecting"]


def test_implausible_areas(planted):
    large = _rows(planted, "area_too_large").geometry.apply(area_acres)
    small = _rows(planted, "area_too_small").geometry.apply(area_m2)
    assert (large >= LARGE_FARM_ACRES[0] * 0.99).all()
    assert (small <= TINY_FARM_M2[1] * 1.01).all()


def test_overlaps_are_heavy(planted):
    survey, truth = planted
    geoms = survey.set_index("farmer_id").geometry
    for _, t in truth[truth["error_type"] == "farm_overlap"].iterrows():
        fraction = overlap_fraction(geoms[t["farmer_id"]], geoms[t["related_farmer_id"]])
        assert fraction >= OVERLAP_FRACTION_RANGE[0] - 0.01


def test_duplicates_share_national_id_with_different_name(planted):
    survey, _ = planted
    by_id = survey.set_index("farmer_id")
    for _, t in planted[1][planted[1]["error_type"] == "duplicate_registration"].iterrows():
        dup, original = by_id.loc[t["farmer_id"]], by_id.loc[t["related_farmer_id"]]
        assert (survey["national_id"] == dup["national_id"]).sum() == 2
        assert dup["national_id"] == original["national_id"]
        assert dup["farmer_name"] != original["farmer_name"]
        assert dup["registration_date"] >= original["registration_date"]


def test_missing_fields(planted):
    survey, truth = planted
    by_id = survey.set_index("farmer_id")
    for _, t in truth[truth["error_type"] == "missing_required_field"].iterrows():
        for field in t["details"].split()[0].split("/"):
            assert pd.isna(by_id.loc[t["farmer_id"], field])


def test_future_dates(planted):
    rows = _rows(planted, "future_registration_date")
    assert (rows["registration_date"] > EXPORT_DATE.isoformat()).all()
    assert (rows["registration_date"] > "2026-12-31").all()  # future even relative to today


def test_only_planted_overlaps(planted):
    """Every overlapping pair is a planted overlap or a duplicate with its original."""
    survey, truth = planted
    valid = survey[survey.is_valid].reset_index(drop=True)
    left, right = valid.sindex.query(valid.geometry, predicate="intersects")
    found = {
        frozenset((valid.at[i, "farmer_id"], valid.at[j, "farmer_id"])) for i, j in zip(left, right) if i < j
    }
    paired = truth.dropna(subset=["related_farmer_id"])
    expected = {frozenset(pair) for pair in zip(paired["farmer_id"], paired["related_farmer_id"])}
    assert found == expected


def test_same_seed_same_errors(clean_survey, county_polygons):
    a_survey, a_truth = plant_errors(clean_survey, county_polygons, np.random.default_rng(3))
    b_survey, b_truth = plant_errors(clean_survey, county_polygons, np.random.default_rng(3))
    assert a_truth.equals(b_truth)
    assert a_survey.equals(b_survey)
