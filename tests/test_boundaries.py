import logging

import geopandas as gpd
import pytest
from shapely.geometry import box

from fdq.boundaries import (
    build_api_url,
    county_polygons,
    provenance,
    select_download_url,
    validate_boundaries,
)


def _counties(n: int, crs: str | None = "EPSG:4326") -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"shapeName": [f"County {i}" for i in range(n)]},
        geometry=[box(i, 0, i + 1, 1) for i in range(n)],
        crs=crs,
    )


def test_build_api_url():
    assert build_api_url("KEN", "ADM1", "gbOpen") == "https://www.geoboundaries.org/api/current/gbOpen/KEN/ADM1/"


def test_select_download_url():
    metadata = {"gjDownloadURL": "full.geojson", "simplifiedGeometryGeoJSON": "simple.geojson"}
    assert select_download_url(metadata) == "full.geojson"
    assert select_download_url(metadata, simplified=True) == "simple.geojson"


def test_select_download_url_missing_link():
    with pytest.raises(KeyError):
        select_download_url({})


def test_validate_boundaries_passes_and_logs_count(caplog):
    with caplog.at_level(logging.INFO):
        validate_boundaries(_counties(47))
    assert "Found 47 counties" in caplog.text
    assert "WARNING" not in caplog.text


def test_validate_boundaries_warns_on_wrong_count(caplog):
    with caplog.at_level(logging.INFO):
        validate_boundaries(_counties(46))
    assert "expected 47" in caplog.text


@pytest.mark.parametrize("crs", ["EPSG:21037", None])
def test_validate_boundaries_rejects_wrong_crs(crs):
    with pytest.raises(ValueError):
        validate_boundaries(_counties(47, crs=crs))


def test_validate_boundaries_warns_on_invalid_geometry(caplog):
    counties = _counties(47)
    bowtie = gpd.GeoSeries.from_wkt(["POLYGON ((0 0, 1 1, 1 0, 0 1, 0 0))"]).iloc[0]
    counties.loc[0, "geometry"] = bowtie
    with caplog.at_level(logging.INFO):
        validate_boundaries(counties)
    assert "1 county geometries are invalid" in caplog.text


def test_county_polygons_selects_by_name():
    selected = county_polygons(_counties(3), ["County 2", "County 0"])
    assert list(selected) == ["County 2", "County 0"]
    assert selected["County 2"].bounds == (2.0, 0.0, 3.0, 1.0)


def test_county_polygons_unknown_name():
    with pytest.raises(ValueError, match="Atlantis"):
        county_polygons(_counties(3), ["Atlantis"])


def test_provenance_records_source():
    record = provenance({"boundaryLicense": "Public Domain", "extra": 1}, "http://x", "2026-10-23")
    assert record["boundaryLicense"] == "Public Domain"
    assert record["downloadURL"] == "http://x"
    assert "extra" not in record
