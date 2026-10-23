"""Interactive review map (folium): farms coloured by data quality status.

Privacy rule: popups show only farmer_id, county, crop, area and issues.
Names, national IDs and phone numbers never reach the map; the duplicate
check's message (which quotes the shared ID or phone) is redacted.

Every value placed in a popup is HTML-escaped: folium inserts popup content
into the page as raw HTML, so unescaped field data could inject markup or
scripts into the reviewer's browser.
"""

import html
import logging

import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from branca.element import Element

from fdq.checks import ERROR, WARNING
from fdq.geo import ARC1960_UTM_37S, SQUARE_METRES_PER_ACRE, WGS84, area_m2_series

logger = logging.getLogger(__name__)

CLEAN = "clean"
STATUS_COLOURS = {CLEAN: "#2e7d32", WARNING: "#ef6c00", ERROR: "#c62828"}
STATUS_LABELS = {CLEAN: "Clean", WARNING: "Warnings only", ERROR: "At least one error"}
COUNTY_SIMPLIFY_TOLERANCE_M = 250.0
COUNTY_DECIMALS = 4  # ~11 m: plenty for outlines simplified at 250 m
FARM_DECIMALS = 6  # ~0.1 m: keeps the shape of the smallest farms
MARKER_RADIUS_PX = 5


# --- Data preparation (pure) ---------------------------------------------------


def farm_status(farmer_ids: pd.Series, issues: pd.DataFrame) -> pd.Series:
    """Classify each farm as clean, warning (warnings only) or error.

    Args:
        farmer_ids: The farms to classify.
        issues: Issues table with farmer_id and severity.

    Returns:
        "clean", "warning" or "error" per farm, aligned with farmer_ids.
    """
    with_error = set(issues.loc[issues["severity"] == ERROR, "farmer_id"])
    with_warning = set(issues.loc[issues["severity"] == WARNING, "farmer_id"])
    return farmer_ids.map(lambda f: ERROR if f in with_error else WARNING if f in with_warning else CLEAN)


def redact_message(check_id: str, message: str) -> str:
    """Remove personal data from an issue message before it goes on the map.

    duplicate_registration messages quote the shared value, e.g.
    "same national_id (23456789) as FRM-00012; same phone (0712345678) as
    FRM-00012"; this becomes "same national ID as FRM-00012; same phone
    number as FRM-00012". Other messages contain no personal data.

    Args:
        check_id: The check that raised the issue.
        message: The issue message.

    Returns:
        A message safe to publish.
    """
    if check_id != "duplicate_registration":
        return message
    parts = []
    for part in message.split("; "):
        label, _, others = part.partition(") as ")
        if not others:  # unexpected format: drop it rather than risk leaking
            parts.append("shares an identifier with another record")
            continue
        field = "national ID" if label.startswith("same national_id") else "phone number"
        parts.append(f"same {field} as {others}")
    return "; ".join(parts)


def popup_html(farmer_id: str, county: object, crop: object, acres: float, status: str, farm_issues: pd.DataFrame) -> str:
    """Build one farm's popup, with every data value HTML-escaped.

    Args:
        farmer_id: Farm's farmer_id.
        county: Registered county (may be missing).
        crop: Registered crop (may be missing).
        acres: Area in acres; NaN if it cannot be measured.
        status: "clean", "warning" or "error".
        farm_issues: This farm's rows of the issues table.

    Returns:
        HTML for the popup.
    """

    def text(value: object) -> str:
        return "(blank)" if value is None or pd.isna(value) else html.escape(str(value))

    area = "n/a (invalid polygon)" if pd.isna(acres) else f"{acres:,.2f} acres"
    lines = [
        f"<b>{text(farmer_id)}</b>",
        f"County: {text(county)}",
        f"Crop: {text(crop)}",
        f"Area: {area}",
        f'Status: <span style="color:{STATUS_COLOURS[status]};font-weight:bold">{STATUS_LABELS[status]}</span>',
    ]
    if farm_issues.empty:
        return "<br>".join(lines + ["No issues"])
    items = "".join(
        f"<li><b>{text(row.check_id)}</b> ({text(row.severity)}): {text(redact_message(row.check_id, row.message))}</li>"
        for row in farm_issues.itertuples()
    )
    return "<br>".join(lines) + f'<br>Issues:<ul style="margin:2px 0 0 0;padding-left:16px">{items}</ul>'


def round_coordinates(gdf: gpd.GeoDataFrame, decimals: int) -> gpd.GeoDataFrame:
    """Round every coordinate, to shrink the GeoJSON embedded in the map.

    Rounding keeps each geometry's structure (unlike set_precision, which
    may repair or drop invalid parts), so invalid farms stay visibly invalid.

    Args:
        gdf: Geometries in EPSG:4326.
        decimals: Decimal places to keep.

    Returns:
        A copy with rounded coordinates.
    """
    rounded = shapely.transform(gdf.geometry.to_numpy(), lambda xy: np.round(xy, decimals))
    return gdf.set_geometry(gpd.GeoSeries(rounded, index=gdf.index, crs=gdf.crs))


def simplify_counties(
    counties: gpd.GeoDataFrame,
    tolerance_m: float = COUNTY_SIMPLIFY_TOLERANCE_M,
    decimals: int = COUNTY_DECIMALS,
) -> gpd.GeoDataFrame:
    """Simplify county outlines for display.

    The tolerance is a distance, so simplification happens in metres
    (UTM 37S) and the result is converted back to EPSG:4326.

    Args:
        counties: County boundaries with shapeName.
        tolerance_m: Largest allowed deviation from the original outline.
        decimals: Decimal places to keep in the output coordinates.

    Returns:
        County name and simplified geometry in EPSG:4326.
    """
    projected = counties[["shapeName", "geometry"]].to_crs(ARC1960_UTM_37S)
    projected = projected.set_geometry(projected.simplify(tolerance_m, preserve_topology=True))
    return round_coordinates(projected.to_crs(WGS84), decimals)


def farm_layer_data(
    registrations: pd.DataFrame, farms: gpd.GeoDataFrame, issues: pd.DataFrame
) -> gpd.GeoDataFrame:
    """Assemble what the map shows per farm: status, popup and geometry only.

    Args:
        registrations: Farmer registrations.
        farms: Farm polygons with farmer_id.
        issues: The issues table.

    Returns:
        farmer_id, status, popup and polygon geometry (EPSG:4326). No other
        registration fields are carried over.
    """
    data = farms[["farmer_id", "geometry"]].merge(
        registrations[["farmer_id", "county", "crop"]], on="farmer_id", how="left"
    )
    geoms = data.geometry
    measurable = geoms.notna() & ~geoms.is_empty & geoms.is_valid
    acres = pd.Series(np.nan, index=data.index)
    acres[measurable] = area_m2_series(geoms[measurable]) / SQUARE_METRES_PER_ACRE

    data["status"] = farm_status(data["farmer_id"], issues)
    issues_by_farm = dict(tuple(issues.groupby("farmer_id")))
    empty = issues.iloc[0:0]
    data["popup"] = [
        popup_html(row.farmer_id, row.county, row.crop, a, row.status, issues_by_farm.get(row.farmer_id, empty))
        for row, a in zip(data.itertuples(), acres)
    ]
    data = data[geoms.notna() & ~geoms.is_empty]
    return round_coordinates(data[["farmer_id", "status", "popup", "geometry"]], FARM_DECIMALS)


# --- Map assembly --------------------------------------------------------------


def _style(feature: dict) -> dict:
    colour = STATUS_COLOURS[feature["properties"]["status"]]
    return {"color": colour, "weight": 2, "fillColor": colour, "fillOpacity": 0.45}


def _title_html(counts: pd.Series, label: str | None = None) -> str:
    total = int(counts.sum())
    batch = f"<div>Batch: {html.escape(label)}</div>" if label else ""
    return f"""
    <div style="position:fixed;top:12px;left:60px;z-index:9999;background:white;padding:8px 12px;
                border:1px solid #999;border-radius:4px;font:13px/1.4 sans-serif;max-width:340px;">
      <div style="font-size:15px;font-weight:bold;">Farm registration quality review</div>
      <div>{total} farms in five Kenyan counties, coloured by data quality status. Click a farm for details.</div>{batch}
      <div style="margin-top:4px;color:#c62828;font-weight:bold;">Simulated data: no real farmers or farms.</div>
    </div>"""


def _legend_html(counts: pd.Series) -> str:
    rows = "".join(
        f'<div><span style="display:inline-block;width:12px;height:12px;background:{STATUS_COLOURS[s]};'
        f'margin-right:6px;vertical-align:middle;opacity:0.8;"></span>{STATUS_LABELS[s]} ({int(counts.get(s, 0))})</div>'
        for s in (CLEAN, WARNING, ERROR)
    )
    return f"""
    <div style="position:fixed;bottom:28px;left:12px;z-index:9999;background:white;padding:8px 12px;
                border:1px solid #999;border-radius:4px;font:13px/1.6 sans-serif;">
      <div style="font-weight:bold;">Farm status</div>{rows}
      <div><span style="display:inline-block;width:12px;height:2px;background:#555;margin-right:6px;
           vertical-align:middle;"></span>County boundary</div>
    </div>"""


def build_map(
    registrations: pd.DataFrame,
    farms: gpd.GeoDataFrame,
    counties: gpd.GeoDataFrame,
    issues: pd.DataFrame,
    label: str | None = None,
) -> folium.Map:
    """Build the review map.

    Layers: county outlines, farm polygons (visible when zoomed in) and a
    dot per farm (visible at any zoom), all toggleable.

    Args:
        registrations: Farmer registrations.
        farms: Farm polygons with farmer_id.
        counties: County boundaries with shapeName.
        issues: The issues table.
        label: Optional description of the data batch for the title box.

    Returns:
        The folium map, zoomed to the farms.
    """
    layer = farm_layer_data(registrations, farms, issues)
    counts = layer["status"].value_counts()

    # OpenStreetMap needs no API key (CartoDB basemaps now do).
    fmap = folium.Map(tiles=None, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(fmap)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri",
        name="Satellite (Esri)",
    ).add_to(fmap)

    folium.GeoJson(
        simplify_counties(counties),
        name="County boundaries",
        style_function=lambda _: {"color": "#555", "weight": 1.2, "fill": False},
        tooltip=folium.GeoJsonTooltip(fields=["shapeName"], labels=False),
    ).add_to(fmap)

    popup = folium.GeoJsonPopup(fields=["popup"], labels=False, max_width=360)
    folium.GeoJson(layer, name="Farm boundaries", style_function=_style, popup=popup).add_to(fmap)

    # One dot per farm at its bounding-box centre (works for invalid polygons too).
    bounds = layer.geometry.bounds
    centres = gpd.points_from_xy((bounds["minx"] + bounds["maxx"]) / 2, (bounds["miny"] + bounds["maxy"]) / 2, crs=WGS84)
    dots = round_coordinates(layer.set_geometry(centres), FARM_DECIMALS)
    folium.GeoJson(
        dots,
        name="Farm locations (dots)",
        marker=folium.CircleMarker(radius=MARKER_RADIUS_PX, weight=1, fill=True),
        style_function=lambda f: {**_style(f), "fillOpacity": 0.9, "color": "white"},
        popup=folium.GeoJsonPopup(fields=["popup"], labels=False, max_width=360),
    ).add_to(fmap)

    folium.LayerControl(collapsed=True).add_to(fmap)
    fmap.get_root().html.add_child(Element(_title_html(counts, label)))
    fmap.get_root().html.add_child(Element(_legend_html(counts)))

    minx, miny, maxx, maxy = layer.total_bounds
    fmap.fit_bounds([[miny, minx], [maxy, maxx]])
    logger.info(
        "Map: %d farms (%s)", len(layer), ", ".join(f"{STATUS_LABELS[s]}: {int(counts.get(s, 0))}" for s in STATUS_COLOURS)
    )
    return fmap
