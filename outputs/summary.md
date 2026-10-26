# Data quality summary

**Batch:** weekly batch, seed 202644, run 2026-10-26

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
| Kakamega | 115 | 18 | 15.7% | 22 | 22 | farm_overlap (8) |
| Uasin Gishu | 124 | 14 | 11.3% | 16 | 16 | farm_area_implausible (5) |
| Nakuru | 119 | 12 | 10.1% | 14 | 14 | gps_invalid (3) |
| Bungoma | 140 | 12 | 8.6% | 14 | 14 | farm_overlap (4) |
| Meru | 101 | 7 | 6.9% | 9 | 9 | gps_invalid (3) |
| (blank) | 1 | 1 | 100.0% | 1 | 1 | required_fields_missing (1) |

## Issues by enumerator (top 10 by share flagged)

| Enumerator | Records | Flagged records | Share flagged | Issues | Errors | Most common issue |
|:---|---:|---:|---:|---:|---:|:---|
| ENUM-UGS-03 | 34 | 6 | 17.6% | 6 | 6 | polygon_invalid (2) |
| ENUM-KKG-03 | 40 | 7 | 17.5% | 10 | 10 | farm_overlap (4) |
| ENUM-MRU-03 | 31 | 5 | 16.1% | 6 | 6 | future_registration_date (2) |
| ENUM-KKG-01 | 28 | 4 | 14.3% | 5 | 5 | farm_overlap (2) |
| ENUM-BGM-01 | 51 | 7 | 13.7% | 8 | 8 | required_fields_missing (2) |
| ENUM-KKG-02 | 46 | 6 | 13.0% | 6 | 6 | farm_overlap (2) |
| ENUM-NKR-01 | 39 | 5 | 12.8% | 5 | 5 | gps_invalid (3) |
| ENUM-NKR-02 | 40 | 5 | 12.5% | 7 | 7 | duplicate_registration (2) |
| ENUM-BGM-03 | 44 | 4 | 9.1% | 5 | 5 | farm_overlap (2) |
| ENUM-UGS-01 | 44 | 4 | 9.1% | 6 | 6 | duplicate_registration (2) |

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
