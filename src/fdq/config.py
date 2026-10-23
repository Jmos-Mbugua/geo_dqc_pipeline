"""Thresholds and settings for the quality checks.

Every number a check compares against lives here, so tuning the pipeline
never means editing check code.
"""

from datetime import date

# Date the survey was exported from ODK; registrations after it are impossible.
EXPORT_DATE = date(2026, 6, 30)

# Kenya's bounding box (min_lon, min_lat, max_lon, max_lat), from the county
# boundaries' total_bounds (33.912, -4.702, 41.906, 5.431) plus a ~5 km margin.
# A box is a coarse test: it also contains parts of Uganda, Tanzania, Somalia,
# Ethiopia and South Sudan. gps_outside_county does the precise test.
KENYA_BBOX = (33.85, -4.75, 41.95, 5.48)

# Plausible farm size for a smallholder registration, in acres.
MIN_PLAUSIBLE_FARM_ACRES = 0.05  # about 200 m², a kitchen garden
MAX_PLAUSIBLE_FARM_ACRES = 20.0

# How far (metres) a registration point may be from its own farm boundary.
MAX_POINT_TO_FARM_M = 200.0

# Two farms are flagged when their overlap exceeds this share of the smaller farm.
MIN_OVERLAP_FRACTION = 0.20

# Text values treated as blank (compared after strip() and casefold()).
MISSING_PLACEHOLDERS = frozenset({"", "na", "n/a", "null", "none", "-"})

# Registered county names (normalised) that the boundary data spells differently.
COUNTY_NAME_ALIASES = {"tharaka nithi": "tharaka"}
