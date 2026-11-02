# Data quality summary

**Batch:** weekly batch, seed 202645, run 2026-11-02

600 farmer registrations and 600 farm boundaries checked against 9 checks. Registration dates are checked against the export date, 2026-06-30.
**89.3% of records are clean**; 76 issues were found on 64 records. Every issue is listed in `issues.csv`.

## Overview

|  | Records | Share |
|:---|---:|---:|
| Clean (no issues) | 536 | 89.3% |
| At least one error | 64 | 10.7% |
| Warnings only | 0 | 0.0% |
| Total | 600 | 100.0% |

## Issues by check and severity

| Check | Errors | Warnings | Records flagged |
|:---|---:|---:|---:|
| required_fields_missing | 8 | 0 | 8 |
| duplicate_registration | 12 | 0 | 12 |
| future_registration_date | 5 | 0 | 5 |
| gps_invalid | 8 | 0 | 8 |
| gps_outside_county | 8 | 0 | 8 |
| polygon_invalid | 7 | 0 | 7 |
| farm_area_implausible | 8 | 0 | 8 |
| farm_point_outside_polygon | 0 | 0 | 0 |
| farm_overlap | 20 | 0 | 20 |

## Issues by county

| County | Records | Flagged records | Share flagged | Issues | Errors | Most common issue |
|:---|---:|---:|---:|---:|---:|:---|
| Bungoma | 127 | 16 | 12.6% | 20 | 20 | farm_overlap (6) |
| Uasin Gishu | 112 | 14 | 12.5% | 16 | 16 | farm_overlap (6) |
| Nakuru | 116 | 13 | 11.2% | 15 | 15 | required_fields_missing (3) |
| Meru | 126 | 14 | 11.1% | 18 | 18 | duplicate_registration (4) |
| Kakamega | 118 | 6 | 5.1% | 6 | 6 | farm_overlap (2) |
| (blank) | 1 | 1 | 100.0% | 1 | 1 | required_fields_missing (1) |

## Issues by enumerator (top 10 by share flagged)

| Enumerator | Records | Flagged records | Share flagged | Issues | Errors | Most common issue |
|:---|---:|---:|---:|---:|---:|:---|
| ENUM-UGS-02 | 43 | 8 | 18.6% | 9 | 9 | farm_overlap (3) |
| ENUM-MRU-01 | 49 | 9 | 18.4% | 13 | 13 | duplicate_registration (4) |
| ENUM-BGM-02 | 50 | 8 | 16.0% | 11 | 11 | farm_overlap (5) |
| ENUM-NKR-01 | 43 | 6 | 14.0% | 7 | 7 | gps_outside_county (2) |
| ENUM-BGM-03 | 38 | 5 | 13.2% | 6 | 6 | farm_area_implausible (2) |
| ENUM-UGS-03 | 31 | 4 | 12.9% | 5 | 5 | farm_overlap (3) |
| ENUM-MRU-02 | 39 | 4 | 10.3% | 4 | 4 | gps_outside_county (2) |
| ENUM-BGM-01 | 40 | 4 | 10.0% | 4 | 4 | gps_invalid (2) |
| ENUM-NKR-03 | 40 | 4 | 10.0% | 5 | 5 | required_fields_missing (2) |
| ENUM-NKR-02 | 33 | 3 | 9.1% | 3 | 3 | future_registration_date (1) |

## Evaluation against planted errors

The input is simulated, so we know which errors were planted (`planted_errors.csv`). **Recall** is the share of planted errors that the check designed for them caught. **Explained** flags are on records that are part of a planted error, including expected side effects (a duplicate registration re-walks the same farm, so it also trips `farm_overlap`). Any other flag is a **possible false alarm** to review.

| Check | Planted | Recall | Records flagged | Explained by planted errors | Possible false alarms |
|:---|---:|---:|---:|---:|---:|
| required_fields_missing | 8 | 8/8 (100%) | 8 | 8 | 0 |
| duplicate_registration | 6 | 6/6 (100%) | 12 | 12 | 0 |
| future_registration_date | 5 | 5/5 (100%) | 5 | 5 | 0 |
| gps_invalid | 8 | 8/8 (100%) | 8 | 8 | 0 |
| gps_outside_county | 8 | 8/8 (100%) | 8 | 8 | 0 |
| polygon_invalid | 7 | 7/7 (100%) | 7 | 7 | 0 |
| farm_area_implausible | 8 | 8/8 (100%) | 8 | 8 | 0 |
| farm_point_outside_polygon | 0 | n/a | 0 | 0 | 0 |
| farm_overlap | 8 | 8/8 (100%) | 20 | 20 | 0 |

Overall: 58 of 58 planted errors caught (100.0%); 0 possible false alarm(s).
