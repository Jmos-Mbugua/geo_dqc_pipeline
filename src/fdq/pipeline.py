"""The data quality pipeline: load, validate, check, report.

run_pipeline() is the only function here that touches files (through
fdq.io); everything else builds tables or text from data in memory.
"""

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import CRS

from fdq import config, io
from fdq.boundaries import COUNTY_NAME_COLUMN
from fdq.checks import CHECK_IDS, ERROR, WARNING, is_blank, run_all_checks
from fdq.evaluate import evaluate, missed_errors, possible_false_alarms
from fdq.geo import WGS84
from fdq.schema import SURVEY_COLUMNS

logger = logging.getLogger(__name__)

ISSUE_COLUMNS = ["farmer_id", "county", "enumerator_id", "check_id", "severity", "message"]
BLANK_LABEL = "(blank)"
TOP_ENUMERATORS = 10
MAX_LISTED = 20  # longest list of individual records in the summary
RIGHT_ALIGNED_TEXT_COLUMNS = {"Share", "Share flagged", "Recall"}  # numbers formatted as text


class InputError(Exception):
    """Input files are missing or do not match the expected schema."""


@dataclass(frozen=True)
class PipelinePaths:
    """Where the pipeline reads from and writes to."""

    registrations: Path
    farms: Path
    counties: Path
    truth: Path | None
    out_dir: Path

    @classmethod
    def from_dirs(cls, raw_dir: Path, out_dir: Path, truth: Path | None = None) -> "PipelinePaths":
        """Use the standard file names inside raw_dir.

        Args:
            raw_dir: Folder with the input files.
            out_dir: Folder for issues.csv and summary.md.
            truth: Ground-truth file; defaults to raw_dir/planted_errors.csv.

        Returns:
            The paths.
        """
        return cls(
            registrations=raw_dir / "farmer_registrations.csv",
            farms=raw_dir / "farm_boundaries.geojson",
            counties=raw_dir / "kenya_counties.geojson",
            truth=truth if truth is not None else raw_dir / "planted_errors.csv",
            out_dir=out_dir,
        )


@dataclass(frozen=True)
class PipelineResult:
    """What a pipeline run produced."""

    issues: pd.DataFrame
    summary: str
    evaluation: pd.DataFrame | None


# --- Validation ----------------------------------------------------------------


def check_inputs_exist(paths: PipelinePaths) -> None:
    """Make sure the three required input files exist.

    Args:
        paths: Pipeline paths.

    Raises:
        InputError: Listing every missing file.
    """
    missing = [p for p in (paths.registrations, paths.farms, paths.counties) if not p.is_file()]
    if missing:
        raise InputError("Missing input file(s): " + ", ".join(str(p) for p in missing))


def _crs_problem(name: str, gdf: gpd.GeoDataFrame) -> list[str]:
    if gdf.crs is None or CRS(gdf.crs) != CRS(WGS84):
        return [f"{name}: CRS must be {WGS84}, got {gdf.crs}"]
    return []


def _key_problems(name: str, ids: pd.Series) -> list[str]:
    problems = []
    if is_blank(ids).any():
        problems.append(f"{name}: {int(is_blank(ids).sum())} row(s) have no farmer_id")
    duplicated = ids[ids.duplicated() & ~is_blank(ids)]
    if len(duplicated):
        problems.append(f"{name}: farmer_id is not unique ({', '.join(sorted(set(duplicated))[:5])})")
    return problems


def validate_schema(
    registrations: pd.DataFrame, farms: gpd.GeoDataFrame, counties: gpd.GeoDataFrame
) -> None:
    """Check the inputs have the columns, keys and CRS the checks rely on.

    farmer_id must be present and unique in both registrations and farms,
    because every issue is reported against it. Blank values in other
    columns are data problems for the checks to report, not schema errors.

    Args:
        registrations: Farmer registrations.
        farms: Farm polygons.
        counties: County boundaries.

    Raises:
        InputError: Listing every problem found.
    """
    problems = []
    missing = [c for c in SURVEY_COLUMNS if c not in registrations.columns]
    if missing:
        problems.append(f"registrations: missing column(s) {missing}")
    elif len(registrations):
        problems += _key_problems("registrations", registrations["farmer_id"])

    if "farmer_id" not in farms.columns:
        problems.append("farm boundaries: missing column 'farmer_id'")
    elif len(farms):
        problems += _key_problems("farm boundaries", farms["farmer_id"])
    problems += _crs_problem("farm boundaries", farms)

    if COUNTY_NAME_COLUMN not in counties.columns:
        problems.append(f"counties: missing column '{COUNTY_NAME_COLUMN}'")
    problems += _crs_problem("counties", counties)

    if problems:
        raise InputError("Input schema is wrong:\n  - " + "\n  - ".join(problems))


def unmatched_records(registrations: pd.DataFrame, farms: gpd.GeoDataFrame) -> tuple[set, set]:
    """Find registrations with no farm polygon, and polygons with no registration.

    Args:
        registrations: Farmer registrations.
        farms: Farm polygons.

    Returns:
        (registration farmer_ids without a farm, farm farmer_ids without a registration)
    """
    registered, mapped = set(registrations["farmer_id"]), set(farms["farmer_id"])
    return registered - mapped, mapped - registered


# --- Issues table and summary ----------------------------------------------------


def build_issues(flags: pd.DataFrame, registrations: pd.DataFrame) -> pd.DataFrame:
    """Add each flagged record's county and enumerator, for review and reporting.

    Args:
        flags: Output of run_all_checks.
        registrations: Farmer registrations.

    Returns:
        One row per issue with ISSUE_COLUMNS.
    """
    context = registrations[["farmer_id", "county", "enumerator_id"]]
    issues = flags.merge(context, on="farmer_id", how="left")
    return issues[ISSUE_COLUMNS]


def _pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def markdown_table(table: pd.DataFrame) -> str:
    """Render a DataFrame as a GitHub Markdown table (numbers right-aligned).

    Args:
        table: Data to render; the index is not included.

    Returns:
        The table as Markdown text.
    """
    header = "| " + " | ".join(str(c) for c in table.columns) + " |"
    align = "|" + "|".join(
        "---:" if pd.api.types.is_numeric_dtype(table[c]) or c in RIGHT_ALIGNED_TEXT_COLUMNS else ":---"
        for c in table.columns
    ) + "|"
    rows = ["| " + " | ".join(str(v) for v in row) + " |" for row in table.itertuples(index=False)]
    return "\n".join([header, align, *rows])


def counts_by_check(issues: pd.DataFrame) -> pd.DataFrame:
    """Count issues per check and severity, listing every check.

    Args:
        issues: The issues table.

    Returns:
        Check, Errors, Warnings, Records flagged.
    """
    rows = []
    for check_id in CHECK_IDS:
        mine = issues[issues["check_id"] == check_id]
        rows.append(
            {
                "Check": check_id,
                "Errors": int((mine["severity"] == ERROR).sum()),
                "Warnings": int((mine["severity"] == WARNING).sum()),
                "Records flagged": mine["farmer_id"].nunique(),
            }
        )
    return pd.DataFrame(rows)


def breakdown(issues: pd.DataFrame, registrations: pd.DataFrame, column: str) -> pd.DataFrame:
    """Summarise issues per value of a column (county or enumerator).

    Args:
        issues: The issues table.
        registrations: Farmer registrations (for the number of records per group).
        column: "county" or "enumerator_id".

    Returns:
        One row per group, sorted by share of records flagged (highest
        first), with the "(blank)" group always last.
    """
    groups = registrations[column].fillna(BLANK_LABEL)
    labelled = issues.assign(**{column: issues[column].fillna(BLANK_LABEL)})
    by_group = labelled.groupby(column)

    table = pd.DataFrame(
        {
            "Records": groups.value_counts(),
            "Flagged records": by_group["farmer_id"].nunique(),
            "Issues": by_group.size(),
            "Errors": labelled[labelled["severity"] == ERROR].groupby(column).size(),
        }
    ).fillna(0).astype(int)
    top = by_group["check_id"].agg(lambda s: f"{s.value_counts().index[0]} ({s.value_counts().iloc[0]})")
    table["Most common issue"] = top.reindex(table.index).fillna("-")
    table["share"] = table["Flagged records"] / table["Records"].where(table["Records"] > 0)
    table["is_blank"] = table.index == BLANK_LABEL
    table = table.sort_values(["is_blank", "share", "Flagged records"], ascending=[True, False, False])
    table.insert(2, "Share flagged", [_pct(f, r) for f, r in zip(table["Flagged records"], table["Records"])])
    label = "County" if column == "county" else "Enumerator"
    return table.drop(columns=["share", "is_blank"]).rename_axis(label).reset_index()


def evaluation_table(evaluation: pd.DataFrame) -> pd.DataFrame:
    """Format the evaluation for the summary.

    Args:
        evaluation: Output of fdq.evaluate.evaluate.

    Returns:
        A display table.
    """
    recall = [
        "n/a" if planted == 0 else f"{caught}/{planted} ({caught / planted:.0%})"
        for caught, planted in zip(evaluation["caught"], evaluation["planted"])
    ]
    return pd.DataFrame(
        {
            "Check": evaluation["check_id"],
            "Planted": evaluation["planted"],
            "Recall": recall,
            "Records flagged": evaluation["flagged_records"],
            "Explained by planted errors": evaluation["explained"],
            "Possible false alarms": evaluation["possible_false_alarms"],
        }
    )


def summarise(
    issues: pd.DataFrame,
    registrations: pd.DataFrame,
    farms: gpd.GeoDataFrame,
    truth: pd.DataFrame | None = None,
    as_of: date = config.EXPORT_DATE,
) -> str:
    """Write the Markdown summary report.

    Args:
        issues: The issues table.
        registrations: Farmer registrations.
        farms: Farm polygons.
        truth: Ground truth, if available; adds the evaluation section.
        as_of: Export date the date check used.

    Returns:
        The report as Markdown.
    """
    total = len(registrations)
    ids = set(registrations["farmer_id"])
    flagged = set(issues["farmer_id"]) & ids
    with_error = set(issues.loc[issues["severity"] == ERROR, "farmer_id"]) & ids
    warning_only = flagged - with_error
    clean = total - len(flagged)

    overview = pd.DataFrame(
        {
            "": ["Clean (no issues)", "At least one error", "Warnings only", "Total"],
            "Records": [clean, len(with_error), len(warning_only), total],
            "Share": [_pct(n, total) for n in (clean, len(with_error), len(warning_only), total)],
        }
    )
    enumerators = breakdown(issues, registrations, "enumerator_id").head(TOP_ENUMERATORS)

    lines = [
        "# Data quality summary",
        "",
        f"{total} farmer registrations and {len(farms)} farm boundaries checked "
        f"against {len(CHECK_IDS)} checks. Registration dates are checked against the export date, {as_of.isoformat()}.",
        f"**{_pct(clean, total)} of records are clean**; {len(issues)} issues were found "
        f"on {len(flagged)} records. Every issue is listed in `issues.csv`.",
        "",
        "## Overview",
        "",
        markdown_table(overview),
        "",
        "## Issues by check and severity",
        "",
        markdown_table(counts_by_check(issues)),
        "",
        "## Issues by county",
        "",
        markdown_table(breakdown(issues, registrations, "county")),
        "",
        f"## Issues by enumerator (top {TOP_ENUMERATORS} by share flagged)",
        "",
        markdown_table(enumerators),
        "",
    ]
    if truth is not None:
        lines += _evaluation_section(issues, truth)
    return "\n".join(lines)


def _evaluation_section(issues: pd.DataFrame, truth: pd.DataFrame) -> list[str]:
    evaluation = evaluate(issues, truth)
    missed = missed_errors(issues, truth)
    alarms = possible_false_alarms(issues, truth)
    total_planted = int(evaluation["planted"].sum())
    total_caught = int(evaluation["caught"].sum())

    lines = [
        "## Evaluation against planted errors",
        "",
        "The input is simulated, so we know which errors were planted (`planted_errors.csv`). "
        "**Recall** is the share of planted errors that the check designed for them caught. "
        "**Explained** flags are on records that are part of a planted error, including expected side effects "
        "(a duplicate registration re-walks the same farm, so it also trips `farm_overlap`). "
        "Any other flag is a **possible false alarm** to review.",
        "",
        markdown_table(evaluation_table(evaluation)),
        "",
        f"Overall: {total_caught} of {total_planted} planted errors caught "
        f"({_pct(total_caught, total_planted)}); {len(alarms)} possible false alarm(s).",
        "",
    ]
    if len(missed):
        lines += ["### Missed planted errors", ""]
        lines += [f"- {r.farmer_id}: {r.error_type} ({r.details})" for r in missed.head(MAX_LISTED).itertuples()]
        lines.append("")
    if len(alarms):
        lines += ["### Possible false alarms", ""]
        lines += [f"- {r.farmer_id}: {r.check_id}: {r.message}" for r in alarms.head(MAX_LISTED).itertuples()]
        lines.append("")
    return lines


# --- Orchestration -------------------------------------------------------------


def run_pipeline(paths: PipelinePaths) -> PipelineResult:
    """Run the whole pipeline: load, validate, check, report, evaluate.

    Args:
        paths: Input and output locations.

    Returns:
        The issues, the summary text and the evaluation (None without ground truth).

    Raises:
        InputError: If input files are missing or the schema is wrong.
    """
    logger.info("Step 1/5: checking input files exist")
    check_inputs_exist(paths)

    logger.info("Step 2/5: loading data")
    registrations = io.read_registrations(paths.registrations)
    farms = io.read_farm_boundaries(paths.farms)
    counties = io.read_counties(paths.counties)
    logger.info(
        "Loaded %d registrations, %d farm boundaries, %d counties", len(registrations), len(farms), len(counties)
    )

    logger.info("Step 3/5: validating input schema")
    validate_schema(registrations, farms, counties)
    no_farm, no_registration = unmatched_records(registrations, farms)
    if no_farm:
        logger.warning("%d registration(s) have no farm boundary", len(no_farm))
    if no_registration:
        logger.warning("%d farm boundary(ies) have no registration", len(no_registration))

    logger.info("Step 4/5: running %d checks", len(CHECK_IDS))
    issues = build_issues(run_all_checks(registrations, farms, counties), registrations)
    logger.info("Found %d issues on %d records", len(issues), issues["farmer_id"].nunique())

    logger.info("Step 5/5: writing outputs")
    truth = None
    evaluation = None
    if paths.truth is not None and paths.truth.is_file():
        truth = io.read_ground_truth(paths.truth)
        evaluation = evaluate(issues, truth)
        logger.info(
            "Evaluated against %s: %d of %d planted errors caught",
            paths.truth.name,
            int(evaluation["caught"].sum()),
            int(evaluation["planted"].sum()),
        )
    else:
        logger.info("No ground truth file found; skipping evaluation")

    summary = summarise(issues, registrations, farms, truth)
    io.write_issues(issues, paths.out_dir / "issues.csv")
    io.write_text(summary, paths.out_dir / "summary.md")
    logger.info("Wrote %s and %s", paths.out_dir / "issues.csv", paths.out_dir / "summary.md")
    return PipelineResult(issues=issues, summary=summary, evaluation=evaluation)
