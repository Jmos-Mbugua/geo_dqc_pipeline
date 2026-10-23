import pytest
from shapely import affinity
from shapely.geometry import Point, box

from fdq.geo import (
    SQUARE_METRES_PER_ACRE,
    area_acres,
    area_m2,
    overlap_fraction,
    projected_crs_for_longitude,
    to_degrees,
    to_metres,
)


@pytest.mark.parametrize(
    "longitude, expected",
    [(34.7, "EPSG:21036"), (35.999, "EPSG:21036"), (36.0, "EPSG:21037"), (37.6, "EPSG:21037")],
)
def test_projected_crs_for_longitude(longitude, expected):
    assert projected_crs_for_longitude(longitude) == expected


def _square_in_degrees(lon: float, lat: float, side_m: float, crs: str):
    """A square of known size, built in metres and converted to degrees."""
    centre = to_metres(Point(lon, lat), crs)
    half = side_m / 2
    return to_degrees(box(centre.x - half, centre.y - half, centre.x + half, centre.y + half), crs)


@pytest.mark.parametrize("lon, lat, crs", [(36.07, -0.30, "EPSG:21037"), (34.75, 0.28, "EPSG:21036")])
def test_area_m2_of_known_square(lon, lat, crs):
    square = _square_in_degrees(lon, lat, 100.0, crs)
    assert area_m2(square) == pytest.approx(10_000, rel=1e-3)
    # The same shape measured in degrees is meaningless: a tiny number.
    assert square.area < 1e-5


def test_area_acres_of_one_acre():
    side = SQUARE_METRES_PER_ACRE**0.5
    assert area_acres(_square_in_degrees(36.07, -0.30, side, "EPSG:21037")) == pytest.approx(1.0, rel=1e-3)


def test_area_of_empty_geometry_is_zero():
    assert area_m2(Point()) == 0.0


def test_metres_round_trip():
    point = Point(36.07, -0.30)
    back = to_degrees(to_metres(point, "EPSG:21037"), "EPSG:21037")
    assert back.distance(point) < 1e-7  # degrees; about 1 cm


def test_overlap_fraction():
    crs = "EPSG:21037"
    a = _square_in_degrees(36.07, -0.30, 100.0, crs)
    half_shifted = to_degrees(affinity.translate(to_metres(a, crs), 50.0, 0.0), crs)
    far_away = to_degrees(affinity.translate(to_metres(a, crs), 500.0, 0.0), crs)

    assert overlap_fraction(a, a) == pytest.approx(1.0)
    assert overlap_fraction(a, half_shifted) == pytest.approx(0.5, rel=1e-3)
    assert overlap_fraction(a, far_away) == 0.0


def test_area_m2_series_measures_each_farm_in_its_own_zone():
    import geopandas as gpd

    from fdq.geo import area_m2_series, projected_crs_for_geoseries

    squares = gpd.GeoSeries(
        [
            _square_in_degrees(36.07, -0.30, 100.0, "EPSG:21037"),  # Nakuru, zone 37S
            _square_in_degrees(34.56, 0.57, 200.0, "EPSG:21036"),  # Bungoma, zone 36S
        ],
        crs="EPSG:4326",
    )
    assert projected_crs_for_geoseries(squares).tolist() == ["EPSG:21037", "EPSG:21036"]
    assert area_m2_series(squares).tolist() == pytest.approx([10_000, 40_000], rel=1e-3)
