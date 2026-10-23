import math

import pandas as pd

from fdq.checks import CHECK_IDS
from fdq.evaluate import (
    EVALUATION_COLUMNS,
    INTENDED_CHECK,
    evaluate,
    expected_flags,
    missed_errors,
    possible_false_alarms,
)


def _truth(*rows: tuple) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["farmer_id", "error_type", "related_farmer_id", "details"])


def _issues(*pairs: tuple) -> pd.DataFrame:
    return pd.DataFrame(pairs, columns=["farmer_id", "check_id"])


def test_every_intended_check_exists():
    assert set(INTENDED_CHECK.values()) <= set(CHECK_IDS)


def test_expected_flags_include_partner_and_side_effects():
    truth = _truth(("F2", "duplicate_registration", "F1", ""))
    assert set(expected_flags(truth).itertuples(index=False, name=None)) == {
        ("F2", "duplicate_registration"),
        ("F1", "duplicate_registration"),
        ("F2", "farm_overlap"),
        ("F1", "farm_overlap"),
    }


def test_evaluate_counts_recall_and_false_alarms():
    truth = _truth(
        ("F1", "gps_null_island", None, ""),
        ("F2", "gps_latlon_swapped", None, ""),
        ("F3", "area_too_small", None, ""),
    )
    issues = _issues(
        ("F1", "gps_invalid"),
        ("F3", "farm_area_implausible"),
        ("F3", "farm_area_implausible"),  # counted once
        ("F9", "farm_area_implausible"),  # not planted
    )
    result = evaluate(issues, truth).set_index("check_id")
    assert list(result.reset_index().columns) == EVALUATION_COLUMNS
    assert list(result.index) == CHECK_IDS

    assert result.loc["gps_invalid", ["planted", "caught", "recall"]].tolist() == [2, 1, 0.5]
    area = result.loc["farm_area_implausible"]
    assert (area["flagged_records"], area["explained"], area["possible_false_alarms"]) == (2, 1, 1)
    assert math.isnan(result.loc["farm_overlap", "recall"])


def test_perfect_run_has_full_recall_and_no_false_alarms():
    truth = _truth(("F1", "farm_overlap", "F2", ""), ("F2", "farm_overlap", "F1", ""))
    issues = _issues(("F1", "farm_overlap"), ("F2", "farm_overlap"))
    result = evaluate(issues, truth).set_index("check_id")
    assert result.loc["farm_overlap", "recall"] == 1.0
    assert result["possible_false_alarms"].sum() == 0
    assert missed_errors(issues, truth).empty
    assert possible_false_alarms(issues, truth).empty


def test_missed_and_false_alarm_lists():
    truth = _truth(("F1", "future_registration_date", None, ""))
    issues = _issues(("F2", "polygon_invalid"))
    assert missed_errors(issues, truth)["farmer_id"].tolist() == ["F1"]
    assert possible_false_alarms(issues, truth)["farmer_id"].tolist() == ["F2"]


def test_empty_inputs():
    truth = _truth()
    result = evaluate(_issues(), truth)
    assert len(result) == len(CHECK_IDS)
    assert result["flagged_records"].sum() == 0
