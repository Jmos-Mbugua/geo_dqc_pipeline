"""Score the checks against the planted-errors ground truth.

Only meaningful for the simulated data, where we know which errors were
planted. The checks themselves never see the ground truth.

Two numbers per check:
- recall: of the planted errors this check is meant to catch, how many it
  flagged.
- possible false alarms: flagged records that no planted error explains.

A flag is "explained" when the record is part of a planted error the check
is designed for (including the partner record in a pair, such as the
original of a duplicate) or one that is expected to trip it as a side
effect (a duplicate registration re-walks the same farm, so it also trips
farm_overlap).
"""

import logging

import pandas as pd

from fdq.checks import CHECK_IDS

logger = logging.getLogger(__name__)

# Planted error type -> the check designed to catch it.
INTENDED_CHECK: dict[str, str] = {
    "missing_required_field": "required_fields_missing",
    "duplicate_registration": "duplicate_registration",
    "future_registration_date": "future_registration_date",
    "gps_null_island": "gps_invalid",
    "gps_latlon_swapped": "gps_invalid",
    "gps_outside_county": "gps_outside_county",
    "polygon_self_intersecting": "polygon_invalid",
    "area_too_large": "farm_area_implausible",
    "area_too_small": "farm_area_implausible",
    "farm_overlap": "farm_overlap",
}

# Planted error type -> other checks it is expected to trip, on both records involved.
SIDE_EFFECT_CHECKS: dict[str, list[str]] = {
    "duplicate_registration": ["farm_overlap"],
}

EVALUATION_COLUMNS = [
    "check_id",
    "planted",
    "caught",
    "recall",
    "flagged_records",
    "explained",
    "possible_false_alarms",
]


def expected_flags(truth: pd.DataFrame) -> pd.DataFrame:
    """List every (farmer_id, check_id) pair the planted errors explain.

    Args:
        truth: Ground truth with farmer_id, error_type, related_farmer_id.

    Returns:
        Unique farmer_id, check_id pairs.
    """
    unknown = set(truth["error_type"]) - set(INTENDED_CHECK)
    if unknown:
        logger.warning("Ground truth has error types with no intended check: %s", sorted(unknown))

    pairs = []
    for row in truth.itertuples(index=False):
        if row.error_type not in INTENDED_CHECK:
            continue
        check_ids = [INTENDED_CHECK[row.error_type], *SIDE_EFFECT_CHECKS.get(row.error_type, [])]
        records = [row.farmer_id] + ([row.related_farmer_id] if pd.notna(row.related_farmer_id) else [])
        pairs += [(record, check_id) for record in records for check_id in check_ids]
    return pd.DataFrame(pairs, columns=["farmer_id", "check_id"]).drop_duplicates(ignore_index=True)


def _flagged_pairs(issues: pd.DataFrame) -> set[tuple[str, str]]:
    return set(zip(issues["farmer_id"], issues["check_id"]))


def evaluate(issues: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    """Compute recall and possible false alarms for every check.

    Records are counted once per check, even if a check flags a record
    several times (for example a farm overlapping two others).

    Args:
        issues: Pipeline issues with farmer_id and check_id.
        truth: Ground truth with farmer_id, error_type, related_farmer_id.

    Returns:
        One row per check with EVALUATION_COLUMNS. recall is a fraction
        (0 to 1), or NaN for checks with no planted errors.
    """
    flagged = _flagged_pairs(issues)
    explained = set(expected_flags(truth).itertuples(index=False, name=None))
    intended = truth["error_type"].map(INTENDED_CHECK)

    rows = []
    for check_id in CHECK_IDS:
        targets = truth.loc[intended == check_id, "farmer_id"]
        caught = sum((farmer_id, check_id) in flagged for farmer_id in targets)
        check_flags = {pair for pair in flagged if pair[1] == check_id}
        n_explained = len(check_flags & explained)
        rows.append(
            {
                "check_id": check_id,
                "planted": len(targets),
                "caught": caught,
                "recall": caught / len(targets) if len(targets) else float("nan"),
                "flagged_records": len(check_flags),
                "explained": n_explained,
                "possible_false_alarms": len(check_flags) - n_explained,
            }
        )
    return pd.DataFrame(rows, columns=EVALUATION_COLUMNS)


def missed_errors(issues: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    """Planted errors that their intended check did not flag.

    Args:
        issues: Pipeline issues.
        truth: Ground truth.

    Returns:
        The ground-truth rows that were missed.
    """
    flagged = _flagged_pairs(issues)
    hit = [
        (farmer_id, INTENDED_CHECK.get(error_type)) in flagged
        for farmer_id, error_type in zip(truth["farmer_id"], truth["error_type"])
    ]
    return truth[~pd.Series(hit, index=truth.index, dtype=bool)]


def possible_false_alarms(issues: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    """Issues that no planted error explains.

    Args:
        issues: Pipeline issues.
        truth: Ground truth.

    Returns:
        The issue rows that may be false alarms.
    """
    explained = set(expected_flags(truth).itertuples(index=False, name=None))
    keep = [pair not in explained for pair in zip(issues["farmer_id"], issues["check_id"])]
    return issues[pd.Series(keep, index=issues.index, dtype=bool)]
