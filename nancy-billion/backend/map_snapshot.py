"""Static map snapshot for Telegram image attachments (see telegram_bot.py).

Keyless: geocodes via OpenStreetMap's Nominatim, then stitches a grid of
satellite tiles into one high-resolution image -- sent as a Telegram document
(not a compressed photo) so the recipient can actually pinch-zoom into real
street/town detail instead of Telegram's photo pipeline downscaling it.

Day tiles are ESRI World Imagery -- the same source the frontend's own
map/globe uses (see components/nancy/map-panel.tsx's ESRI_SAT constant). If
it's currently night at the target location (real solar-altitude calculation,
not a fixed local hour), NASA GIBS's VIIRS night-lights composite is used
instead, matching the app's own day/night-aware map.

Both tile servers have usage policies meant for low-volume/personal use --
swap in a paid static-map provider if this ever needs to scale beyond one
person's occasional requests.
"""

from __future__ import annotations

import asyncio
import io
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

USER_AGENT = "NancyBillion/1.0 (personal AI assistant, single-user local deployment)"

# ESRI's tile scheme is {z}/{y}/{x} (row before column) -- matches
# components/nancy/map-panel.tsx's ESRI_SAT constant.
ESRI_SAT_TEMPLATE = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"

# NASA GIBS VIIRS City Lights composite -- real night-lights satellite
# imagery, same {z}/{y}/{x} row-before-column convention. This layer only
# publishes up to zoom 8 (coarser than daytime imagery -- night lights data
# doesn't have street-level resolution to begin with).
GIBS_NIGHT_TEMPLATE = (
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_CityLights_2012/"
    "default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpg"
)
GIBS_MAX_ZOOM = 8

TILE_PX = 256
GRID_SIZE = 9  # odd, so there's a true center tile; ~2300px final image
NIGHT_GRID_SIZE = 7  # night imagery is capped at a lower zoom, so a smaller
# grid keeps the framing sensible instead of covering an excessive area
MIN_ZOOM = 3
MAX_ZOOM = 18
MAX_CONCURRENT_TILE_FETCHES = 16


@dataclass(frozen=True)
class GeocodeResult:
    lat: float
    lon: float
    display_name: str
    # (south, north, west, east) in degrees, from Nominatim.
    bbox: Tuple[float, float, float, float]


async def geocode(query: str) -> Optional[GeocodeResult]:
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1},
            )
            resp.raise_for_status()
            results = resp.json()
    except Exception as e:
        logger.warning("Geocode failed for %r: %s", query, e)
        return None

    if not results:
        return None
    top = results[0]
    bbox_raw = top.get("boundingbox")
    bbox = (
        tuple(float(v) for v in bbox_raw)
        if bbox_raw and len(bbox_raw) == 4
        else (float(top["lat"]) - 0.05, float(top["lat"]) + 0.05, float(top["lon"]) - 0.05, float(top["lon"]) + 0.05)
    )
    return GeocodeResult(
        lat=float(top["lat"]),
        lon=float(top["lon"]),
        display_name=top.get("display_name", query),
        bbox=bbox,  # type: ignore[arg-type]
    )


def solar_altitude_deg(lat: float, lon: float, when: Optional[datetime] = None) -> float:
    """Real solar altitude (degrees above horizon) at (lat, lon) and time
    (defaults to now, UTC) -- standard NOAA-style approximation, accurate to
    within a few minutes of actual sunrise/sunset. Negative means the sun is
    below the horizon (night)."""
    when = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
    n = when.timetuple().tm_yday
    utc_hour = when.hour + when.minute / 60 + when.second / 3600

    b = math.radians(360 / 365 * (n - 81))
    decl = math.radians(23.44) * math.sin(b * (365 / 360))  # solar declination
    eot = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)  # equation of time, minutes

    local_solar_time = utc_hour + (4 * lon + eot) / 60
    hour_angle = math.radians(15 * (local_solar_time - 12))

    lat_rad = math.radians(lat)
    sin_alt = math.sin(lat_rad) * math.sin(decl) + math.cos(lat_rad) * math.cos(decl) * math.cos(hour_angle)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))


def is_night(lat: float, lon: float, when: Optional[datetime] = None) -> bool:
    """Night once the sun is a few degrees below the horizon (civil twilight)
    -- roughly matches when city lights actually become visible, rather than
    the stricter astronomical definition of sunset at exactly 0 degrees."""
    return solar_altitude_deg(lat, lon, when) < -3.0


def _deg2tile(lat: float, lon: float, zoom: int) -> Tuple[int, int]:
    lat_rad = math.radians(lat)
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


MAX_SPAN_DEG = 1.2  # cap how far a huge admin-boundary bbox (e.g. "Tokyo" the
# prefecture, not the city) can zoom the view out -- keeps a recognizable
# city/metro-area view instead of the whole region.


def _pick_zoom(bbox: Tuple[float, float, float, float], grid_size: int, max_zoom: int) -> int:
    """Choose a zoom level so a `grid_size` x `grid_size` tile grid comfortably
    covers the geocoded feature's bounding box -- a country gets a wide, zoomed
    -out view (up to MAX_SPAN_DEG); a street address gets a close one, same as
    the app's own map fitting a place on screen instead of one fixed zoom."""
    south, north, west, east = bbox
    lat_span = max(abs(north - south), 0.001)
    lon_span = max(abs(east - west), 0.001)
    span = min(max(lat_span, lon_span), MAX_SPAN_DEG)
    zoom = math.floor(math.log2((360.0 * grid_size) / span))
    return max(MIN_ZOOM, min(max_zoom, zoom))


async def _fetch_tile(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, url_template: str, x: int, y: int, zoom: int
) -> Optional[Image.Image]:
    url = url_template.format(z=zoom, y=y, x=x)
    async with sem:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return Image.open(io.BytesIO(resp.content)).convert("RGB")
        except Exception as e:
            logger.warning("Tile fetch failed (z=%s x=%s y=%s): %s", zoom, x, y, e)
            return None


async def fetch_map_snapshot(
    lat: float, lon: float, zoom: int, grid_size: int, url_template: str
) -> Optional[bytes]:
    """Fetch a `grid_size` x `grid_size` grid of tiles centered on (lat, lon)
    at `zoom` from `url_template`, stitched into one high-resolution PNG."""
    center_x, center_y = _deg2tile(lat, lon, zoom)
    half = grid_size // 2
    sem = asyncio.Semaphore(MAX_CONCURRENT_TILE_FETCHES)

    async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": USER_AGENT}) as client:
        coords = [(row, col) for row in range(-half, half + 1) for col in range(-half, half + 1)]
        tiles = await asyncio.gather(
            *(
                _fetch_tile(client, sem, url_template, center_x + col, center_y + row, zoom)
                for row, col in coords
            )
        )

    if all(t is None for t in tiles):
        return None

    canvas = Image.new("RGB", (grid_size * TILE_PX, grid_size * TILE_PX), color=(10, 10, 15))
    for (row, col), tile in zip(coords, tiles):
        if tile is None:
            continue
        px = (col + half) * TILE_PX
        py = (row + half) * TILE_PX
        canvas.paste(tile, (px, py))

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


async def snapshot_for_query(query: str) -> Optional[Tuple[bytes, str, bool]]:
    """Best-effort: geocode `query` and fetch a high-resolution satellite (or,
    if it's currently night there, real night-lights) map snapshot sized to
    the feature's real extent.

    Returns (png_bytes, display_name, was_night), or None if geocoding/fetch
    failed -- callers should fall back to a text-only reply in that case.
    """
    result = await geocode(query)
    if result is None:
        return None

    night = is_night(result.lat, result.lon)
    if night:
        zoom = _pick_zoom(result.bbox, NIGHT_GRID_SIZE, GIBS_MAX_ZOOM)
        image = await fetch_map_snapshot(result.lat, result.lon, zoom, NIGHT_GRID_SIZE, GIBS_NIGHT_TEMPLATE)
    else:
        zoom = _pick_zoom(result.bbox, GRID_SIZE, MAX_ZOOM)
        image = await fetch_map_snapshot(result.lat, result.lon, zoom, GRID_SIZE, ESRI_SAT_TEMPLATE)

    if image is None:
        return None
    return image, result.display_name, night
