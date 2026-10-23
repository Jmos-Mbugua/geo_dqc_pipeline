import numpy as np
import pytest
from shapely.geometry import Point, box

from fdq.geo import area_acres
from fdq.schema import SURVEY_COLUMNS
from fdq.synthetic.generate import (
    MAX_FARM_ACRES,
    MIN_FARM_ACRES,
    REGISTRATION_END,
    REGISTRATION_START,
    find_overlapping,
    generate_clean_survey,
    make_farm_polygon,
    random_farm_acres,
    sample_points_in_polygon,
)


def test_sample_points_in_polygon():
    l_shape = box(0, 0, 1, 1).union(box(1, 0, 2, 0.1))  # odd shape: lots of rejected points
    points = sample_points_in_polygon(l_shape, 50, np.random.default_rng(0))
    assert len(points) == 50
    assert all(l_shape.contains(p) for p in points)


def test_random_farm_acres_in_range():
    rng = np.random.default_rng(0)
    sizes = [random_farm_acres(rng) for _ in range(1000)]
    assert min(sizes) >= MIN_FARM_ACRES
    assert max(sizes) <= MAX_FARM_ACRES
    # Log-uniform: the median is the geometric mean (1 acre), not the midpoint (2.6).
    assert np.median(sizes) == pytest.approx(1.0, rel=0.15)


@pytest.mark.parametrize("seed", range(20))
def test_make_farm_polygon_is_valid_with_exact_area(seed):
    polygon = make_farm_polygon((500_000.0, 9_950_000.0), 4000.0, np.random.default_rng(seed))
    assert polygon.is_valid
    assert polygon.area == pytest.approx(4000.0)
    assert polygon.contains(Point(500_000.0, 9_950_000.0))


def test_find_overlapping():
    polygons = [box(0, 0, 2, 2), box(1, 1, 3, 3), box(10, 10, 11, 11)]
    assert find_overlapping(polygons) == {1}


def test_clean_survey_shape(clean_survey):
    assert len(clean_survey) == 200
    assert list(clean_survey.columns) == SURVEY_COLUMNS + ["geometry"]
    assert clean_survey.crs.to_epsg() == 4326
    assert clean_survey["farmer_id"].is_unique
    assert clean_survey["national_id"].is_unique
    assert clean_survey[SURVEY_COLUMNS].notna().all().all()


def test_clean_farms_are_valid_smallholdings(clean_survey):
    assert clean_survey.is_valid.all()
    acres = clean_survey.geometry.apply(area_acres)
    # Small tolerance: built in one Arc 1960 zone, measured in the centroid's zone.
    assert acres.min() >= MIN_FARM_ACRES * 0.99
    assert acres.max() <= MAX_FARM_ACRES * 1.01


def test_clean_points_inside_farm_and_county(clean_survey, county_polygons):
    for _, row in clean_survey.iterrows():
        point = Point(row["longitude"], row["latitude"])
        assert row["geometry"].contains(point)
        assert county_polygons[row["county"]].contains(point)


def test_clean_farms_do_not_overlap(clean_survey):
    assert find_overlapping(list(clean_survey.geometry)) == set()


def test_clean_dates_in_window(clean_survey):
    dates = clean_survey["registration_date"]
    assert dates.min() >= REGISTRATION_START.isoformat()
    assert dates.max() <= REGISTRATION_END.isoformat()


def test_same_seed_same_data(county_polygons):
    a = generate_clean_survey(county_polygons, 30, np.random.default_rng(7))
    b = generate_clean_survey(county_polygons, 30, np.random.default_rng(7))
    c = generate_clean_survey(county_polygons, 30, np.random.default_rng(8))
    assert a.equals(b)
    assert not a.equals(c)
