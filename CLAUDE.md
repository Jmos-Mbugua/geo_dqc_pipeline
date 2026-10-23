# field-data-quality-kenya

## Goal
A data quality pipeline for agricultural field survey data collected through ODK, such as farmer registrations with GPS points and farm boundary polygons, as an agri-insurance company in Kenya would collect. The pipeline flags bad records (missing or duplicate data, out-of-bounds GPS, invalid polygons, implausible areas, overlaps) and produces an issues list, a summary report and a review map (it does not write a cleaned dataset). This is a portfolio and learning project: favour clear, well-explained code over clever code.

## Folder structure
- `src/fdq/`: the Python package. All pipeline logic lives here.
- `tests/`: pytest tests that mirror the modules in `src/fdq/`.
- `scripts/`: thin command-line entry points for data preparation (download, simulate). No logic here.
- `src/fdq/run.py`: the pipeline's entry point (`python -m fdq.run`); `pipeline.py` holds the steps, `checks.py` the checks, `evaluate.py` the scoring against planted errors.
- `data/raw/`: input data, tracked in git. **Synthetic or anonymised only.** Never commit real farmer names, phone numbers, ID numbers or exact locations.
- `data/processed/`: pipeline outputs, git-ignored and always regenerable.
- `outputs/`: pipeline results: `issues.csv` (one row per issue) and `summary.md`. Tracked in git so the README can show them.
- `.github/workflows/`: `tests.yml` (pytest on every push/PR) and `scheduled_run.yml` (weekly batch: generate into `batch/`, run the pipeline, upload an artifact, commit `docs/index.html` and `outputs/`). The bot commits to `main`, so `git pull` before pushing.
- `docs/`: `index.html` is the interactive review map built by `fdq.map` (served by GitHub Pages); `data_dictionary.md` documents every column and its validation rule. **Update the data dictionary and the README checks table whenever a check or threshold changes.**

## Data
- `data/raw/farmer_registrations.csv`, `farm_boundaries.geojson` and `planted_errors.csv` are **simulated** by `scripts/generate_survey.py` (seed 42), using `fdq.synthetic`. Regenerating with the same seed gives byte-identical files.
- `planted_errors.csv` is the ground truth for scoring the checks. Never let the checks read it; only `fdq.evaluate` does, and the pipeline skips evaluation when the file is absent (as it will be for real data). New planted error types need an entry in `evaluate.INTENDED_CHECK`.
- Read registrations with `fdq.io.read_registrations` so IDs and phone numbers stay text (leading zeros).
- **Map privacy:** popups may show only farmer_id, county, crop, area and issues. Never names, national IDs or phone numbers; `map.redact_message` strips identifiers from issue messages, and `tests/test_map.py` scans the HTML for leaks. HTML-escape every value (folium renders popup content as raw HTML).
- Shared constants: required fields are in `fdq.schema`. All check thresholds, plus the survey `EXPORT_DATE`, are in `fdq.config`. Never hard-code a threshold in a check.

## Setup and commands
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .          # makes `import fdq` work everywhere
pytest                    # run all tests
python -m fdq.run         # run the pipeline (from the repo root); exit code 1 = bad input
```

## Conventions
- **Type hints** on every function signature.
- **Docstrings** (Google style) on every public function: what it does, Args, Returns.
- **Small pure functions**: take data in, return new data out. No hidden I/O, no mutating inputs, no global state. Keep file reading and writing at the edges (in `scripts/` or dedicated I/O functions).
- **Every check gets a pytest test** with small hand-made fixtures covering a passing case, a failing case and edge cases (empty input, nulls).
- **Use `logging`, never `print`.** Each module does `logger = logging.getLogger(__name__)`, and logging is configured only in entry points (`scripts/` and `fdq/run.py`).

## CRS rule (non-negotiable)
- Data is stored and exchanged in **EPSG:4326** (WGS84 latitude/longitude), as ODK produces it.
- **All area and distance calculations must use a projected CRS, never degrees.** A degree isn't a fixed length on the ground (it's about 111 km of latitude, and the length of a degree of longitude shrinks away from the equator), so `.area` or `.distance` on EPSG:4326 data gives meaningless results.
- Default projected CRS: **EPSG:21037** (Arc 1960 / UTM zone 37S), which covers most of Kenya. For data west of 36°E, consider EPSG:21036 (UTM 36S). Results are in metres and square metres. Convert to hectares (÷ 10,000) or acres explicitly.
- Reproject with `gdf.to_crs(...)` inside the function that needs it, and return results in the original CRS.
- A test should cover any function that computes area or distance, using a known geometry.
