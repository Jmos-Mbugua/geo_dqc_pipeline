# Data quality summary

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
| Uasin Gishu | 123 | 21 | 17.1% | 29 | 29 | farm_overlap (10) |
| Nakuru | 116 | 12 | 10.3% | 12 | 12 | future_registration_date (2) |
| Kakamega | 103 | 9 | 8.7% | 9 | 9 | polygon_invalid (3) |
| Meru | 130 | 11 | 8.5% | 15 | 15 | duplicate_registration (4) |
| Bungoma | 127 | 10 | 7.9% | 10 | 10 | required_fields_missing (3) |
| (blank) | 1 | 1 | 100.0% | 1 | 1 | required_fields_missing (1) |

## Issues by enumerator (top 10 by share flagged)

| Enumerator | Records | Flagged records | Share flagged | Issues | Errors | Most common issue |
|:---|---:|---:|---:|---:|---:|:---|
| ENUM-UGS-03 | 35 | 7 | 20.0% | 11 | 11 | duplicate_registration (4) |
| ENUM-UGS-02 | 38 | 7 | 18.4% | 9 | 9 | farm_overlap (4) |
| ENUM-UGS-01 | 50 | 7 | 14.0% | 9 | 9 | required_fields_missing (3) |
| ENUM-KKG-02 | 48 | 6 | 12.5% | 6 | 6 | polygon_invalid (3) |
| ENUM-NKR-02 | 48 | 6 | 12.5% | 6 | 6 | farm_area_implausible (2) |
| ENUM-NKR-01 | 36 | 4 | 11.1% | 4 | 4 | required_fields_missing (1) |
| ENUM-MRU-02 | 40 | 4 | 10.0% | 5 | 5 | duplicate_registration (1) |
| ENUM-BGM-03 | 43 | 4 | 9.3% | 4 | 4 | required_fields_missing (1) |
| ENUM-MRU-01 | 43 | 4 | 9.3% | 5 | 5 | duplicate_registration (1) |
| ENUM-BGM-01 | 35 | 3 | 8.6% | 3 | 3 | required_fields_missing (1) |

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
