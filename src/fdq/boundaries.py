"""Download and validate Kenya's county (ADM1) boundaries from geoBoundaries."""

import io
import json
import logging
import urllib.request

import geopandas as gpd
from pyproj import CRS
from shapely.geometry.base import BaseGeometry

logger = logging.getLogger(__name__)

GEOBOUNDARIES_API_URL = "https://www.geoboundaries.org/api/current/{release}/{iso}/{adm}/"
COUNTY_NAME_COLUMN = "shapeName"
EXPECTED_COUNTY_COUNT = 47
EXPECTED_CRS = "EPSG:4326"
USER_AGENT = "field-data-quality-kenya/0.1"
PROVENANCE_KEYS = [
    "boundaryName",
    "boundaryType",
    "boundaryYearRepresented",
    "boundarySource",
    "boundaryLicense",
    "admUnitCount",
    "sourceDataUpdateDate",
]


def build_api_url(iso: str = "KEN", adm: str = "ADM1", release: str = "gbOpen") -> str:
    """Build the geoBoundaries metadata API URL.

    Args:
        iso: ISO 3166-1 alpha-3 country code.
        adm: Administrative level, e.g. "ADM1".
        release: geoBoundaries release type, e.g. "gbOpen".

    Returns:
        The API URL, which returns JSON metadata including download links.
    """
    return GEOBOUNDARIES_API_URL.format(release=release, iso=iso, adm=adm)


def fetch_bytes(url: str, timeout: float = 120) -> bytes:
    """Download a URL and return its raw bytes.

    Args:
        url: URL to download.
        timeout: Seconds to wait before giving up.

    Returns:
        The response body.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_metadata(url: str) -> dict:
    """Fetch the geoBoundaries JSON metadata for one boundary set.

    Args:
        url: A geoBoundaries API URL (see build_api_url).

    Returns:
        The parsed metadata.
    """
    return json.loads(fetch_bytes(url, timeout=60))


def select_download_url(metadata: dict, simplified: bool = False) -> str:
    """Pick the GeoJSON download link out of geoBoundaries metadata.

    Args:
        metadata: Parsed API response.
        simplified: If True, use the lighter simplified geometry.

    Returns:
        The GeoJSON download URL.

    Raises:
        KeyError: If the metadata has no such link.
    """
    key = "simplifiedGeometryGeoJSON" if simplified else "gjDownloadURL"
    if not metadata.get(key):
        raise KeyError(f"geoBoundaries metadata has no '{key}' link")
    return metadata[key]


def parse_boundaries(raw: bytes) -> gpd.GeoDataFrame:
    """Parse GeoJSON bytes into a GeoDataFrame.

    Args:
        raw: GeoJSON file contents.

    Returns:
        The boundaries as a GeoDataFrame.
    """
    return gpd.read_file(io.BytesIO(raw))


def validate_boundaries(
    counties: gpd.GeoDataFrame,
    expected_count: int = EXPECTED_COUNTY_COUNT,
    expected_crs: str = EXPECTED_CRS,
) -> None:
    """Check the CRS and log the number of counties and invalid geometries.

    Args:
        counties: County boundaries.
        expected_count: Number of counties expected (Kenya has 47).
        expected_crs: CRS the data must be in.

    Raises:
        ValueError: If the CRS is missing or not the expected one.
    """
    if counties.crs is None or CRS(counties.crs) != CRS(expected_crs):
        raise ValueError(f"Expected CRS {expected_crs}, got {counties.crs}")
    logger.info("CRS is %s", expected_crs)

    count = len(counties)
    if count == expected_count:
        logger.info("Found %d counties", count)
    else:
        logger.warning("Found %d counties, expected %d", count, expected_count)

    n_invalid = int((~counties.geometry.is_valid).sum())
    if n_invalid:
        logger.warning("%d county geometries are invalid", n_invalid)


def provenance(metadata: dict, download_url: str, downloaded_on: str) -> dict:
    """Summarise where a boundary file came from, for a sidecar JSON file.

    Args:
        metadata: Parsed geoBoundaries API response.
        download_url: The URL the file was downloaded from.
        downloaded_on: ISO date of the download.

    Returns:
        Source, licence and download details.
    """
    record = {key: metadata.get(key) for key in PROVENANCE_KEYS}
    record["downloadURL"] = download_url
    record["downloadedOn"] = downloaded_on
    return record


def county_polygons(counties: gpd.GeoDataFrame, names: list[str]) -> dict[str, BaseGeometry]:
    """Look up the boundary polygon for each named county.

    Args:
        counties: County boundaries with a shapeName column.
        names: County names to select.

    Returns:
        A mapping of county name to (multi)polygon in EPSG:4326.

    Raises:
        ValueError: If a name is not in the boundaries.
    """
    lookup = dict(zip(counties[COUNTY_NAME_COLUMN], counties.geometry))
    missing = [name for name in names if name not in lookup]
    if missing:
        raise ValueError(f"Counties not found in boundaries: {missing}")
    return {name: lookup[name] for name in names}
