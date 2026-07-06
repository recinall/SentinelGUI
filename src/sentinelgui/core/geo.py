"""Geographic coordinate helpers. Qt-free — never import PySide6.

Pure parsing/math used by the AOI tab: flexible coordinate parsing (decimal
degrees *and* degrees/minutes/seconds) and a center+window-in-km → bounding-box
conversion. Everything here is headless-testable.
"""

import re

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
