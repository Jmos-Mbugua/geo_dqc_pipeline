"""Column names and field rules for the farmer registration survey.

Shared by the simulator and the quality checks so they always agree.
"""

SURVEY_COLUMNS: list[str] = [
    "farmer_id",
    "farmer_name",
    "national_id",
    "phone",
    "county",
    "ward",
    "crop",
    "registration_date",
    "enumerator_id",
    "latitude",
    "longitude",
]

# Every column except ward is required for a registration to be usable.
REQUIRED_FIELDS: list[str] = [c for c in SURVEY_COLUMNS if c != "ward"]

# Read these as text: IDs and phone numbers are labels, not numbers, and
# reading "0712345678" as a number silently drops the leading zero.
TEXT_COLUMNS: list[str] = [c for c in SURVEY_COLUMNS if c not in ("latitude", "longitude")]
