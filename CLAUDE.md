# field-data-quality-kenya

## Goal
A data quality pipeline for agricultural field survey data collected through ODK, such as farmer registrations with GPS points and farm boundary polygons, as an agri-insurance company in Kenya would collect. The pipeline flags bad records (missing or duplicate data, out-of-bounds GPS, invalid polygons, implausible areas, overlaps) and produces clean data, a report and a review map. This is a portfolio and learning project: favour clear, well-explained code over clever code.

## Folder structure
- `src/fdq/`: the Python package. All pipeline logic lives here.
- `tests/`: pytest tests that mirror the modules in `src/fdq/`.
- `scripts/`: thin command-line entry points that call `fdq` functions. No logic here.
- `data/raw/`: input data, tracked in git. **Synthetic or anonymised only.** Never commit real farmer names, phone numbers, ID numbers or exact locations.
- `data/processed/`: pipeline outputs, git-ignored and always regenerable.
- `outputs/`: reports and maps (folium HTML).
- `docs/`: notes and design decisions.

## Setup and commands
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .          # makes `import fdq` work everywhere
pytest                    # run all tests
```

## Conventions
- **Type hints** on every function signature.
- **Docstrings** (Google style) on every public function: what it does, Args, Returns.
- **Small pure functions**: take data in, return new data out. No hidden I/O, no mutating inputs, no global state. Keep file reading and writing at the edges (in `scripts/` or dedicated I/O functions).
- **Every check gets a pytest test** with small hand-made fixtures covering a passing case, a failing case and edge cases (empty input, nulls).
- **Use `logging`, never `print`.** Each module does `logger = logging.getLogger(__name__)`, and logging is configured only in `scripts/`.

## CRS rule (non-negotiable)
- Data is stored and exchanged in **EPSG:4326** (WGS84 latitude/longitude), as ODK produces it.
- **All area and distance calculations must use a projected CRS, never degrees.** A degree isn't a fixed length on the ground (it's about 111 km of latitude, and the length of a degree of longitude shrinks away from the equator), so `.area` or `.distance` on EPSG:4326 data gives meaningless results.
- Default projected CRS: **EPSG:21037** (Arc 1960 / UTM zone 37S), which covers most of Kenya. For data west of 36°E, consider EPSG:21036 (UTM 36S). Results are in metres and square metres. Convert to hectares (÷ 10,000) or acres explicitly.
- Reproject with `gdf.to_crs(...)` inside the function that needs it, and return results in the original CRS.
- A test should cover any function that computes area or distance, using a known geometry.
