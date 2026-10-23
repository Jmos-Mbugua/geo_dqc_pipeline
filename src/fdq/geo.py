"""Coordinate reference system helpers.

Data is stored in EPSG:4326 (degrees). Anything that measures area or
distance must first move into a projected CRS (metres); these helpers do that
for single shapely geometries.
"""

from functools import lru_cache

import pyproj
import shapely
from shapely.geometry.base import BaseGeometry

WGS84 = "EPSG:4326"
ARC1960_UTM_36S = "EPSG:21036"
ARC1960_UTM_37S = "EPSG:21037"
SQUARE_METRES_PER_ACRE = 4046.8564224
UTM_ZONE_BOUNDARY_LONGITUDE = 36.0


def projected_crs_for_longitude(longitude: float) -> str:
    """Pick the Kenyan UTM zone (Arc 1960 datum) that contains a longitude.

    Args:
        longitude: Longitude in decimal degrees.

    Returns:
        "EPSG:21036" (UTM 36S) west of 36°E, otherwise "EPSG:21037" (UTM 37S).
    """
    if longitude < UTM_ZONE_BOUNDARY_LONGITUDE:
        return ARC1960_UTM_36S
    return ARC1960_UTM_37S


def projected_crs_for_geometry(geom: BaseGeometry) -> str:
    """Pick the UTM zone for a geometry stored in EPSG:4326.

    Taking the centroid in degrees is fine here: it is only used to choose a
    zone, never to measure anything.

    Args:
        geom: A non-empty geometry in EPSG:4326.

    Returns:
        The EPSG code of the projected CRS to measure it in.
    """
    return projected_crs_for_longitude(geom.centroid.x)


@lru_cache(maxsize=None)
def _transformer(source_crs: str, target_crs: str) -> pyproj.Transformer:
    """Build (and cache) a transformer; always_xy keeps (lon, lat) order."""
    return pyproj.Transformer.from_crs(source_crs, target_crs, always_xy=True)


def to_metres(geom: BaseGeometry, crs: str) -> BaseGeometry:
    """Reproject a geometry from EPSG:4326 into a projected CRS.

    Args:
        geom: Geometry in EPSG:4326.
        crs: Target projected CRS, e.g. "EPSG:21037".

    Returns:
        The same geometry with coordinates in metres.
    """
    return shapely.transform(geom, _transformer(WGS84, crs).transform, interleaved=False)


def to_degrees(geom: BaseGeometry, crs: str) -> BaseGeometry:
    """Reproject a geometry from a projected CRS back to EPSG:4326.

    Args:
        geom: Geometry with coordinates in metres.
        crs: The projected CRS the geometry is currently in.

    Returns:
        The same geometry in EPSG:4326 (lon, lat).
    """
    return shapely.transform(geom, _transformer(crs, WGS84).transform, interleaved=False)


def area_m2(geom: BaseGeometry) -> float:
    """Measure a geometry's area in square metres.

    Args:
        geom: Geometry in EPSG:4326.

    Returns:
        Area in m², measured in the geometry's UTM zone. 0.0 if empty.
    """
    if geom.is_empty:
        return 0.0
    return to_metres(geom, projected_crs_for_geometry(geom)).area


def area_acres(geom: BaseGeometry) -> float:
    """Measure a geometry's area in acres.

    Args:
        geom: Geometry in EPSG:4326.

    Returns:
        Area in acres.
    """
    return area_m2(geom) / SQUARE_METRES_PER_ACRE


def overlap_fraction(a: BaseGeometry, b: BaseGeometry) -> float:
    """Share of the smaller polygon that is covered by the other one.

    Args:
        a: Polygon in EPSG:4326.
        b: Polygon in EPSG:4326.

    Returns:
        Intersection area divided by the smaller polygon's area (0.0 to 1.0).
    """
    crs = projected_crs_for_geometry(a)
    a_m, b_m = to_metres(a, crs), to_metres(b, crs)
    smaller = min(a_m.area, b_m.area)
    if smaller == 0:
        return 0.0
    return a_m.intersection(b_m).area / smaller
