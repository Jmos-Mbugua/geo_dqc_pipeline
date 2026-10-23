# Data quality summary

**Batch:** weekly batch, seed 202643, run 2026-10-23

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
| Nakuru | 122 | 17 | 13.9% | 21 | 21 | duplicate_registration (4) |
| Kakamega | 116 | 16 | 13.8% | 22 | 22 | duplicate_registration (6) |
| Meru | 131 | 13 | 9.9% | 15 | 15 | farm_overlap (4) |
| Bungoma | 120 | 11 | 9.2% | 11 | 11 | farm_overlap (4) |
| Uasin Gishu | 110 | 6 | 5.5% | 6 | 6 | gps_outside_county (2) |
| (blank) | 1 | 1 | 100.0% | 1 | 1 | required_fields_missing (1) |

## Issues by enumerator (top 10 by share flagged)

| Enumerator | Records | Flagged records | Share flagged | Issues | Errors | Most common issue |
|:---|---:|---:|---:|---:|---:|:---|
| ENUM-NKR-03 | 41 | 7 | 17.1% | 8 | 8 | required_fields_missing (2) |
| ENUM-KKG-01 | 37 | 6 | 16.2% | 8 | 8 | duplicate_registration (2) |
| ENUM-NKR-01 | 44 | 7 | 15.9% | 9 | 9 | duplicate_registration (2) |
| ENUM-KKG-03 | 43 | 6 | 14.0% | 9 | 9 | duplicate_registration (3) |
| ENUM-MRU-02 | 31 | 4 | 12.9% | 5 | 5 | duplicate_registration (1) |
| ENUM-MRU-03 | 51 | 6 | 11.8% | 7 | 7 | farm_overlap (3) |
| ENUM-KKG-02 | 36 | 4 | 11.1% | 5 | 5 | duplicate_registration (1) |
| ENUM-BGM-03 | 47 | 5 | 10.6% | 5 | 5 | gps_invalid (2) |
| ENUM-BGM-02 | 39 | 4 | 10.3% | 4 | 4 | farm_overlap (2) |
| ENUM-BGM-01 | 35 | 3 | 8.6% | 3 | 3 | farm_overlap (2) |

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
