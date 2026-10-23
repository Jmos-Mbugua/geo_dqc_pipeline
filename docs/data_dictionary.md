# Data dictionary

The columns of every file the pipeline reads and writes, and the rules each column is checked against. Thresholds are in [src/fdq/config.py](../src/fdq/config.py). Where a column has no rule, this document says so.

**Blank** means empty, missing, or one of the placeholders `na`, `n/a`, `null`, `none`, `-` (case-insensitive, after trimming spaces).

**Rejected input** means the pipeline stops with exit code 1, before running any checks. All other rules produce rows in `issues.csv`.

## farmer_registrations.csv

One row per registration, as exported from the survey tool. Every column is read as text except latitude and longitude, so IDs and phone numbers keep their leading zeros.

| Column | Type | Example | Rule (check) |
|---|---|---|---|
| `farmer_id` | text | `FRM-00087` | Required and unique. A blank or repeated value is **rejected input**. The format is not checked. |
| `farmer_name` | text | `Grace Wafula` | Required (`required_fields_missing`). Not compared between records. Never shown on the map. |
| `national_id` | text | `21377731` | Required (`required_fields_missing`). The same value on two or more records is an error on all of them (`duplicate_registration`). The format is not checked. Never shown on the map. |
| `phone` | text | `0746050301` | Required (`required_fields_missing`). Normalised before comparing (`+254 712 345 678` → `0712345678`). The same number on two or more records is a warning on all of them (`duplicate_registration`). The format is not checked. Never shown on the map. |
| `county` | text | `Nakuru` | Required (`required_fields_missing`). The GPS point must lie inside this county's boundary (`gps_outside_county`). Compared after normalising case, spaces, hyphens and apostrophes, plus aliases (`Tharaka-Nithi` → `Tharaka`). |
| `ward` | text | `Njoro` | Optional. Not validated. |
| `crop` | text | `maize` | Required (`required_fields_missing`). Values are not checked against a list. |
| `registration_date` | text, `YYYY-MM-DD` | `2026-03-14` | Required (`required_fields_missing`). Must be a valid date, on or before the export date `2026-06-30` (`future_registration_date`). |
| `enumerator_id` | text | `ENUM-NKR-02` | Required (`required_fields_missing`). The format is not checked. Used to break down issues by enumerator in the summary. |
| `latitude` | decimal degrees, WGS84 | `-0.3576424` | Required (`required_fields_missing`). Must be numeric, not 0,0, and inside Kenya's bounding box (−4.75 to 5.48 N), with likely lat/lon swaps reported as such (`gps_invalid`). The point must be inside the registered county (`gps_outside_county`) and within 200 m of its own farm boundary (`farm_point_outside_polygon`, warning). |
| `longitude` | decimal degrees, WGS84 | `36.215773` | Required, with the same rules as latitude. Kenya's box is 33.85 to 41.95 E. |

## farm_boundaries.geojson

One farm polygon per farmer. CRS must be EPSG:4326, or the input is **rejected**.

| Column | Type | Rule (check) |
|---|---|---|
| `farmer_id` | text | Required and unique (**rejected input** otherwise). Links the farm to its registration. A registration without a farm, or a farm without a registration, is logged as a warning but not reported in `issues.csv`. |
| `geometry` | Polygon or MultiPolygon | Must be present, a polygon, and valid; self-intersections are reported with their location (`polygon_invalid`). Area, measured in metres in the farm's UTM zone, must be between 0.05 and 20 acres (`farm_area_implausible`). Must not overlap another farm by more than 20% of the smaller farm's area (`farm_overlap`). Invalid polygons are skipped by the area, distance and overlap checks. |

## kenya_counties.geojson

Kenya's 47 county boundaries from geoBoundaries (gbOpen, ADM1, 2020, public domain); source details are in `kenya_counties.source.json`. CRS must be EPSG:4326, or the input is **rejected**.

| Column | Type | Use |
|---|---|---|
| `shapeName` | text | County name, matched against `county` in the registrations. Required (**rejected input** if absent). Note the spelling `Tharaka` for Tharaka-Nithi. |
| `shapeISO`, `shapeID`, `shapeGroup`, `shapeType` | text | Not used. |
| `geometry` | (Multi)Polygon | Used for the point-in-county test. Simplified to 250 m for display on the map only. |

## planted_errors.csv (simulated data only)

The ground truth written by the simulator. Only `fdq.evaluate` reads it; the checks never do. If the file is absent, as it would be with real data, evaluation is skipped.

| Column | Type | Meaning |
|---|---|---|
| `farmer_id` | text | The record with the planted error. Each record has at most one planted error. |
| `error_type` | text | One of `missing_required_field`, `duplicate_registration`, `future_registration_date`, `gps_null_island`, `gps_latlon_swapped`, `gps_outside_county`, `polygon_self_intersecting`, `area_too_large`, `area_too_small`, `farm_overlap`. |
| `related_farmer_id` | text or blank | The other record involved: the overlap partner, or the original of a duplicate. |
| `details` | text | Human-readable description, e.g. `crop blank`, `424 acres`. |

## issues.csv (output)

One row per issue. A record can have several issues. Written as UTF-8 with a byte-order mark so it opens cleanly in Excel.

| Column | Type | Meaning |
|---|---|---|
| `farmer_id` | text | The record the issue is about. |
| `county` | text | The record's registered county (blank if missing), for filtering. |
| `enumerator_id` | text | Who collected the record, for follow-up. |
| `check_id` | text | The check that raised the issue (see the README table). |
| `severity` | `error` or `warning` | Error: the record cannot be trusted as it stands. Warning: worth reviewing; often legitimate in the field (shared family phone, GPS taken at the homestead). |
| `message` | text | What is wrong, with the values involved. Duplicate messages quote the shared ID or phone, so `issues.csv` is internal; the map shows a redacted version. |
