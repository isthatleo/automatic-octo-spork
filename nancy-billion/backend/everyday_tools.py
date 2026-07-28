"""Real everyday-usage utility tools -- calculations, unit/currency
conversion, weather, password/QR generation, URL shortening, IP lookup.
Every external call here uses a real, verified, keyless public API
(Frankfurter for currency, Open-Meteo for weather, is.gd for URL
shortening, ip-api.com for IP geolocation) -- none of these are
placeholders or simulated data.
"""

from __future__ import annotations

import ast
import logging
import operator
import secrets
import string
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

EVERYDAY_TOOLS = [
    {
        "name": "calculate",
        "description": "Evaluate a real arithmetic expression (+ - * / ** % // and parentheses) and return the exact result. Safer and more precise than doing math in your head for anything non-trivial.",
        "input_schema": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
    },
    {
        "name": "convert_units",
        "description": "Convert a real value between units of length, weight/mass, temperature, volume, or speed (e.g. 10 km to miles, 98.6 f to c, 5 lb to kg).",
        "input_schema": {
            "type": "object",
            "properties": {
                "value": {"type": "number"},
                "from_unit": {"type": "string", "description": "e.g. 'km', 'mi', 'kg', 'lb', 'c', 'f', 'l', 'gal', 'mph', 'kph'"},
                "to_unit": {"type": "string"},
            },
            "required": ["value", "from_unit", "to_unit"],
        },
    },
    {
        "name": "convert_currency",
        "description": "Convert a real amount between real currencies using actual current exchange rates (European Central Bank reference rates via the Frankfurter API).",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "from_currency": {"type": "string", "description": "3-letter code, e.g. USD"},
                "to_currency": {"type": "string", "description": "3-letter code, e.g. EUR"},
            },
            "required": ["amount", "from_currency", "to_currency"],
        },
    },
    {
        "name": "get_weather",
        "description": "Get real current weather (and today's forecast) for a real place name, via live geocoding + the Open-Meteo weather API. Not simulated -- actual current conditions.",
        "input_schema": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]},
    },
    {
        "name": "generate_password",
        "description": "Generate a real cryptographically-random password (Python's `secrets` module, not a weak PRNG).",
        "input_schema": {
            "type": "object",
            "properties": {
                "length": {"type": "integer", "description": "Default 20."},
                "include_symbols": {"type": "boolean", "description": "Default true."},
            },
            "required": [],
        },
    },
    {
        "name": "generate_qr_code",
        "description": "Generate a real, scannable QR code image (PNG) encoding the given text/URL. You'll see the generated image.",
        "input_schema": {"type": "object", "properties": {"data": {"type": "string"}}, "required": ["data"]},
    },
    {
        "name": "shorten_url",
        "description": "Create a real, working shortened URL for a real link (via is.gd) -- the returned short link actually redirects.",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
    {
        "name": "get_public_ip_info",
        "description": "Look up real public IP + geolocation info -- either this machine's own public IP (omit ip), or a given IP/hostname.",
        "input_schema": {"type": "object", "properties": {"ip": {"type": "string", "description": "Optional -- omit for this machine's own public IP."}}, "required": []},
    },
]

# --- calculate -------------------------------------------------------------

_ALLOWED_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}
_ALLOWED_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Only numbers and + - * / ** % // with parentheses are allowed.")


async def calculate(expression: str) -> Dict[str, Any]:
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)
        return {"success": True, "expression": expression, "result": result}
    except Exception as e:
        return {"success": False, "error": f"Could not evaluate: {e}"}


# --- convert_units -----------------------------------------------------------

_LENGTH_TO_M = {"m": 1, "km": 1000, "cm": 0.01, "mm": 0.001, "mi": 1609.344, "yd": 0.9144, "ft": 0.3048, "in": 0.0254, "nmi": 1852}
_MASS_TO_KG = {"kg": 1, "g": 0.001, "mg": 1e-6, "lb": 0.45359237, "oz": 0.028349523125, "t": 1000, "st": 6.35029318}
_VOLUME_TO_L = {"l": 1, "ml": 0.001, "gal": 3.785411784, "qt": 0.946352946, "pt": 0.473176473, "cup": 0.2365882365, "floz": 0.0295735296}
_SPEED_TO_MPS = {"mps": 1, "kph": 1 / 3.6, "mph": 0.44704, "kn": 0.5144444444}


async def convert_units(value: float, from_unit: str, to_unit: str) -> Dict[str, Any]:
    f, t = from_unit.strip().lower(), to_unit.strip().lower()

    if f in ("c", "f", "k") and t in ("c", "f", "k"):
        celsius = {"c": value, "f": (value - 32) * 5 / 9, "k": value - 273.15}[f]
        result = {"c": celsius, "f": celsius * 9 / 5 + 32, "k": celsius + 273.15}[t]
        return {"success": True, "value": value, "from_unit": from_unit, "to_unit": to_unit, "result": result}

    for table in (_LENGTH_TO_M, _MASS_TO_KG, _VOLUME_TO_L, _SPEED_TO_MPS):
        if f in table and t in table:
            base = value * table[f]
            return {"success": True, "value": value, "from_unit": from_unit, "to_unit": to_unit, "result": base / table[t]}

    return {"success": False, "error": f"Don't know how to convert {from_unit!r} to {to_unit!r} (or they're not the same kind of unit)."}


# --- convert_currency --------------------------------------------------------

async def convert_currency(amount: float, from_currency: str, to_currency: str) -> Dict[str, Any]:
    frm, to = from_currency.strip().upper(), to_currency.strip().upper()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"https://api.frankfurter.dev/v1/latest", params={"base": frm, "symbols": to})
            resp.raise_for_status()
            data = resp.json()
        rate = data.get("rates", {}).get(to)
        if rate is None:
            return {"success": False, "error": f"No rate found for {frm} -> {to}"}
        return {"success": True, "amount": amount, "from_currency": frm, "to_currency": to, "rate": rate, "result": round(amount * rate, 4), "date": data.get("date")}
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- get_weather ---------------------------------------------------------

_WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog", 51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain", 71: "slight snow", 73: "moderate snow", 75: "heavy snow",
    80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    95: "thunderstorm", 96: "thunderstorm with slight hail", 99: "thunderstorm with heavy hail",
}


async def get_weather(location: str) -> Dict[str, Any]:
    from map_snapshot import geocode
    place = await geocode(location)
    if place is None:
        return {"success": False, "error": f"Could not find a location for {location!r}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": place.lat, "longitude": place.lon,
                    "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                    "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                    "temperature_unit": "celsius", "wind_speed_unit": "kmh", "timezone": "auto",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        current = data.get("current", {})
        daily = data.get("daily", {})
        code = current.get("weather_code")
        return {
            "success": True,
            "location": place.display_name,
            "temperature_c": current.get("temperature_2m"),
            "condition": _WEATHER_CODES.get(code, f"code {code}"),
            "humidity_percent": current.get("relative_humidity_2m"),
            "wind_kph": current.get("wind_speed_10m"),
            "today_high_c": (daily.get("temperature_2m_max") or [None])[0],
            "today_low_c": (daily.get("temperature_2m_min") or [None])[0],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- generate_password -----------------------------------------------------

async def generate_password(length: int = 20, include_symbols: bool = True) -> Dict[str, Any]:
    length = max(4, min(length or 20, 128))
    alphabet = string.ascii_letters + string.digits + ("!@#$%^&*()-_=+[]{}" if include_symbols else "")
    password = "".join(secrets.choice(alphabet) for _ in range(length))
    return {"success": True, "password": password, "length": length}


# --- generate_qr_code --------------------------------------------------------

async def generate_qr_code(data: str) -> Dict[str, Any]:
    try:
        import qrcode
        import io, base64
        img = qrcode.make(data)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return {"success": True, "data": data, "image_base64": base64.b64encode(buf.getvalue()).decode("ascii")}
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- shorten_url --------------------------------------------------------

async def shorten_url(url: str) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://is.gd/create.php", params={"format": "json", "url": url})
            resp.raise_for_status()
            data = resp.json()
        if "shorturl" in data:
            return {"success": True, "original_url": url, "short_url": data["shorturl"]}
        return {"success": False, "error": data.get("errormessage", "Unknown error from is.gd")}
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- get_public_ip_info --------------------------------------------------

async def get_public_ip_info(ip: Optional[str] = None) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"http://ip-api.com/json/{ip or ''}")
            resp.raise_for_status()
            data = resp.json()
        if data.get("status") != "success":
            return {"success": False, "error": data.get("message", "Lookup failed")}
        return {
            "success": True, "ip": data.get("query"), "city": data.get("city"), "region": data.get("regionName"),
            "country": data.get("country"), "isp": data.get("isp"), "lat": data.get("lat"), "lon": data.get("lon"),
            "timezone": data.get("timezone"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
