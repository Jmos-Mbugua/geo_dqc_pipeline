"""End-to-end tests: run the pipeline (and its CLI) on a tiny fixture on disk."""

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from fdq import io, run
from fdq.geo import SQUARE_METRES_PER_ACRE, to_degrees, to_metres
from fdq.pipeline import ISSUE_COLUMNS, InputError, PipelinePaths, run_pipeline, validate_schema
from fdq.schema import SURVEY_COLUMNS

LON, LAT = 36.07, -0.30
CRS = "EPSG:21037"


def _farm_around(lon: float, lat: float, side_m: float):
    """A square farm of known size centred on a point."""
    centre = to_metres(gpd.points_from_xy([lon], [lat])[0], CRS)
    half = side_m / 2
    return to_degrees(box(centre.x - half, centre.y - half, centre.x + half, centre.y + half), CRS)


def _row(farmer_id: str, **overrides) -> dict:
    row = {
        "farmer_id": farmer_id,
        "farmer_name": "Grace Wanjiru",
        "national_id": f"2000000{farmer_id[-1]}",
        "phone": f"071000000{farmer_id[-1]}",
        "county": "Nakuru",
        "ward": "Njoro",
        "crop": "maize",
        "registration_date": "2026-03-10",
        "enumerator_id": "ENUM-NKR-01",
        "latitude": LAT,
        "longitude": LON + 0.01 * int(farmer_id[-1]),  # 1.1 km apart: no overlaps
    }
    row.update(overrides)
    return row


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    """Five registrations with three known problems, written like the real inputs.

    F1, F2: clean.  F3: crop missing.  F4: GPS in Baringo.  F5: 40-acre farm.
    The ground truth plants F3 and F4, plus a future date on F2 that the data
    does not actually contain (so it will be "missed"); F5's flag is not in
    the ground truth (so it is a "possible false alarm").
    """
    raw = tmp_path / "raw"
    registrations = pd.DataFrame(
        [
            _row("F1"),
            _row("F2", enumerator_id="ENUM-NKR-02"),
            _row("F3", crop=None),
            _row("F4", latitude=0.1, enumerator_id="ENUM-NKR-02"),
            _row("F5"),
        ],
        columns=SURVEY_COLUMNS,
    )
    io.write_registrations(registrations, raw / "farmer_registrations.csv")

    sides = {"F5": (40 * SQUARE_METRES_PER_ACRE) ** 0.5}
    farms = gpd.GeoDataFrame(
        {"farmer_id": registrations["farmer_id"]},
        geometry=[
            _farm_around(r.longitude, r.latitude, sides.get(r.farmer_id, 60.0)) for r in registrations.itertuples()
        ],
        crs="EPSG:4326",
    )
    io.write_farm_boundaries(farms, raw / "farm_boundaries.geojson")

    counties = gpd.GeoDataFrame(
        {"shapeName": ["Nakuru", "Baringo"]},
        geometry=[box(35.9, -0.6, 36.3, -0.2), box(35.9, -0.2, 36.3, 0.4)],
        crs="EPSG:4326",
    )
    counties.to_file(raw / "kenya_counties.geojson", driver="GeoJSON")

    truth = pd.DataFrame(
        {
            "farmer_id": ["F2", "F3", "F4"],
            "error_type": ["future_registration_date", "missing_required_field", "gps_outside_county"],
            "related_farmer_id": [None, None, None],
            "details": ["", "crop blank", ""],
        }
    )
    io.write_ground_truth(truth, raw / "planted_errors.csv")
    return raw


def test_pipeline_end_to_end(raw_dir: Path, tmp_path: Path):
    out = tmp_path / "out"
    map_file = tmp_path / "docs" / "index.html"
    result = run_pipeline(PipelinePaths.from_dirs(raw_dir, out, map_file=map_file))

    # issues.csv: one row per issue, with county and enumerator for review.
    issues = pd.read_csv(out / "issues.csv", dtype=str, encoding="utf-8-sig")
    assert list(issues.columns) == ISSUE_COLUMNS
    assert sorted(zip(issues["farmer_id"], issues["check_id"])) == [
        ("F3", "required_fields_missing"),
        ("F4", "gps_outside_county"),
        ("F5", "farm_area_implausible"),
    ]
    assert issues.set_index("farmer_id").loc["F4", "enumerator_id"] == "ENUM-NKR-02"

    # summary.md: every section, with the right headline numbers.
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert summary == result.summary
    for heading in [
        "## Overview",
        "## Issues by check and severity",
        "## Issues by county",
        "## Issues by enumerator",
        "## Evaluation against planted errors",
    ]:
        assert heading in summary
    assert "**40.0% of records are clean**" in summary
    assert "| farm_point_outside_polygon | 0 | 0 | 0 |" in summary  # zero-flag checks still listed

    # Evaluation: F3 and F4 caught, F2 missed, F5 a possible false alarm.
    evaluation = result.evaluation.set_index("check_id")
    assert evaluation.loc["required_fields_missing", "caught"] == 1
    assert evaluation.loc["gps_outside_county", "caught"] == 1
    assert evaluation.loc["future_registration_date", "caught"] == 0
    assert evaluation.loc["farm_area_implausible", "possible_false_alarms"] == 1
    assert "2 of 3 planted errors caught" in summary
    assert "### Missed planted errors\n\n- F2: future_registration_date" in summary
    assert "### Possible false alarms\n\n- F5: farm_area_implausible" in summary

    # The map: written, labelled as simulated, every farm present, no personal data.
    page = map_file.read_text(encoding="utf-8")
    assert "Simulated data" in page
    assert all(f'"farmer_id": "F{i}"' in page for i in range(1, 6))
    assert "Grace Wanjiru" not in page and "20000001" not in page


def test_pipeline_without_ground_truth(raw_dir: Path, tmp_path: Path):
    (raw_dir / "planted_errors.csv").unlink()
    result = run_pipeline(PipelinePaths.from_dirs(raw_dir, tmp_path / "out"))
    assert result.evaluation is None
    assert "Evaluation" not in result.summary


def test_cli_success_logs_each_check(raw_dir: Path, tmp_path: Path, caplog):
    with caplog.at_level(logging.INFO):
        code = run.main(["--raw-dir", str(raw_dir), "--out-dir", str(tmp_path / "out"), "--no-map"])
    assert code == run.EXIT_OK
    assert "Check gps_outside_county" in caplog.text
    assert "flagged 1 record(s)" in caplog.text
    assert (tmp_path / "out" / "issues.csv").is_file()


def test_cli_missing_input_exits_non_zero(raw_dir: Path, tmp_path: Path, caplog):
    (raw_dir / "farm_boundaries.geojson").unlink()
    code = run.main(["--raw-dir", str(raw_dir), "--out-dir", str(tmp_path / "out")])
    assert code == run.EXIT_INPUT_ERROR
    assert "Missing input file(s)" in caplog.text
    assert not (tmp_path / "out").exists()


def test_cli_wrong_schema_exits_non_zero(raw_dir: Path, tmp_path: Path, caplog):
    registrations = io.read_registrations(raw_dir / "farmer_registrations.csv")
    registrations.drop(columns="crop").to_csv(raw_dir / "farmer_registrations.csv", index=False)
    code = run.main(["--raw-dir", str(raw_dir), "--out-dir", str(tmp_path / "out")])
    assert code == run.EXIT_INPUT_ERROR
    assert "missing column(s) ['crop']" in caplog.text


# --- validate_schema on its own -------------------------------------------------


def _valid_inputs():
    registrations = pd.DataFrame([_row("F1"), _row("F2")], columns=SURVEY_COLUMNS)
    farms = gpd.GeoDataFrame({"farmer_id": ["F1", "F2"]}, geometry=[box(0, 0, 1, 1)] * 2, crs="EPSG:4326")
    counties = gpd.GeoDataFrame({"shapeName": ["Nakuru"]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:4326")
    return registrations, farms, counties


def test_validate_schema_accepts_valid_inputs():
    validate_schema(*_valid_inputs())


def test_validate_schema_rejects_duplicate_and_blank_ids():
    registrations, farms, counties = _valid_inputs()
    registrations.loc[1, "farmer_id"] = "F1"
    farms.loc[0, "farmer_id"] = None
    with pytest.raises(InputError, match="not unique") as excinfo:
        validate_schema(registrations, farms, counties)
    assert "no farmer_id" in str(excinfo.value)


def test_validate_schema_rejects_wrong_crs():
    registrations, farms, counties = _valid_inputs()
    with pytest.raises(InputError, match="CRS must be EPSG:4326"):
        validate_schema(registrations, farms.set_crs("EPSG:21037", allow_override=True), counties)
