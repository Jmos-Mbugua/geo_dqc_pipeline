from fdq import io
from fdq.schema import SURVEY_COLUMNS


def test_registrations_round_trip_keeps_text(planted, tmp_path):
    survey, _ = planted
    path = tmp_path / "registrations.csv"
    io.write_registrations(survey, path)
    back = io.read_registrations(path)

    assert list(back.columns) == SURVEY_COLUMNS
    assert len(back) == len(survey)
    # Phone numbers keep their leading zero because they are read as text.
    assert back["phone"].dropna().str.startswith("07").all()
    assert back["national_id"].dropna().str.len().eq(8).all()


def test_farm_boundaries_round_trip(planted, tmp_path):
    survey, _ = planted
    path = tmp_path / "farms.geojson"
    io.write_farm_boundaries(survey, path)
    back = io.read_farm_boundaries(path)

    assert list(back.columns) == ["farmer_id", "geometry"]
    assert back.crs.to_epsg() == 4326
    assert back["farmer_id"].tolist() == survey["farmer_id"].tolist()
    # Self-intersecting polygons survive the round trip as invalid geometry.
    assert (~back.is_valid).sum() == (~survey.is_valid).sum()
