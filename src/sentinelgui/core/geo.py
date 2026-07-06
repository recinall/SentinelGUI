"""Geographic coordinate helpers. Qt-free — never import PySide6.

Pure parsing/math used by the AOI tab: flexible coordinate parsing (decimal
degrees *and* degrees/minutes/seconds) and a center+window-in-km → bounding-box
conversion. Everything here is headless-testable.
"""

import re
from math import cos, radians

# Kilometres per degree. Latitude is ~constant; longitude shrinks with cos(lat).
_KM_PER_DEG_LAT = 110.574
_KM_PER_DEG_LON_EQUATOR = 111.32

# Hemisphere letters and the sign they imply. N/E are positive, S/W negative.
_HEMISPHERE = {"N": 1, "S": -1, "E": 1, "W": -1}

# Degrees (required), optional minutes ('/′), optional seconds ("/″, quote
# optional). Whitespace between components is tolerated.
_DMS_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*°"
    r"(?:\s*(\d+(?:\.\d+)?)\s*['′])?"
    r"(?:\s*(\d+(?:\.\d+)?)\s*[\"″]?)?$"
)


def _parse_dms(body: str) -> float:
    """Parse a sign-stripped, hemisphere-stripped DMS string to decimal degrees."""
    match = _DMS_RE.match(body)
    if match is None:
        raise ValueError(f"could not parse DMS coordinate: {body!r}")
    degrees = float(match.group(1))
    minutes = float(match.group(2)) if match.group(2) else 0.0
    seconds = float(match.group(3)) if match.group(3) else 0.0
    return degrees + minutes / 60.0 + seconds / 3600.0


def parse_coordinate(text: str) -> float:
    """Parse a coordinate string to decimal degrees.

    Accepts decimal degrees (``10.5``, ``-10.5``, ``10,5`` with a comma decimal
    separator) and degrees/minutes/seconds (``10°59'24.90"``, ``45°``,
    ``45°30'``) with an optional ``N``/``S``/``E``/``W`` hemisphere as a prefix
    or suffix (``S``/``W`` negate the value). Raises :class:`ValueError` on an
    empty or unparseable string.
    """
    if text is None:
        raise ValueError("empty coordinate")
    raw = text.strip()
    if not raw:
        raise ValueError("empty coordinate")

    body = raw.replace(",", ".")

    # Strip an optional hemisphere letter from either end.
    sign = 1
    upper = body.upper()
    if upper[-1] in _HEMISPHERE:
        sign = _HEMISPHERE[upper[-1]]
        body = body[:-1].strip()
    elif upper[0] in _HEMISPHERE:
        sign = _HEMISPHERE[upper[0]]
        body = body[1:].strip()

    # Strip an optional explicit sign.
    if body.startswith("-"):
        sign = -sign
        body = body[1:].strip()
    elif body.startswith("+"):
        body = body[1:].strip()

    if not body:
        raise ValueError(f"could not parse coordinate: {raw!r}")

    if any(mark in body for mark in "°'\"′″"):
        value = _parse_dms(body)
    else:
        try:
            value = float(body)
        except ValueError:
            raise ValueError(f"could not parse coordinate: {raw!r}") from None

    return sign * value


def bbox_from_center(
    lat: float, lon: float, width_km: float, height_km: float
) -> list[float]:
    """Build a WGS84 bounding box centered on ``(lat, lon)``.

    ``width_km``/``height_km`` are the *total* extent of the window (half is
    applied to each side). The longitude span is latitude-dependent
    (``dlon = (width_km / 2) / (111.32 * cos(lat))``). Returns
    ``[min_lon, min_lat, max_lon, max_lat]``. Raises :class:`ValueError` for an
    out-of-range center, a non-positive size, or a latitude where the longitude
    span is undefined (the poles).
    """
    if not (-90 <= lat <= 90):
        raise ValueError("Latitude must be between -90 and 90")
    if not (-180 <= lon <= 180):
        raise ValueError("Longitude must be between -180 and 180")
    if width_km <= 0 or height_km <= 0:
        raise ValueError("Window size (km) must be positive")

    dlat = (height_km / 2.0) / _KM_PER_DEG_LAT
    km_per_deg_lon = _KM_PER_DEG_LON_EQUATOR * cos(radians(lat))
    if km_per_deg_lon <= 0:
        raise ValueError("Cannot compute a longitude window at this latitude")
    dlon = (width_km / 2.0) / km_per_deg_lon

    return [lon - dlon, lat - dlat, lon + dlon, lat + dlat]
