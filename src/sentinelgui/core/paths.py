"""Output-path helpers. Qt-free — never import PySide6.

Pure, headless-testable helpers for composing the project/date output layout
``<output_dir>/<project>/<scene-datetime>/<prefix>_...``: sanitizing a
user-typed project/location name into a filesystem-safe folder name, and
formatting a STAC acquisition datetime into a folder name.
"""

import re
from datetime import datetime

# Characters illegal in a path component on Windows (the strictest of the three
# target OSes), plus the path separators. Control chars are handled separately.
_ILLEGAL = r'<>:"/\|?*'
_ILLEGAL_RE = re.compile(f"[{re.escape(_ILLEGAL)}\x00-\x1f]+")
_WHITESPACE_RE = re.compile(r"\s+")

# Windows reserved device names (case-insensitive), which cannot be folder names.
_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

_MAX_LEN = 100


def sanitize_folder_name(text: str) -> str:
    """Turn arbitrary user text into a single filesystem-safe folder name.

    Collapses whitespace runs to a single hyphen, strips characters illegal on
    Windows/macOS/Linux (and control chars), trims leading/trailing dots/spaces/
    hyphens, caps the length, and avoids Windows reserved device names. Returns
    ``""`` for empty or all-invalid input so the caller can apply a fallback.
    """
    if not text:
        return ""

    cleaned = _WHITESPACE_RE.sub(" ", text.strip())
    cleaned = _ILLEGAL_RE.sub("", cleaned)
    cleaned = _WHITESPACE_RE.sub("-", cleaned.strip())
    cleaned = cleaned.strip(" .-")
    cleaned = cleaned[:_MAX_LEN].strip(" .-")

    if not cleaned or cleaned.lower() in _RESERVED:
        return ""

    return cleaned


def scene_datetime_folder(iso: str) -> str:
    """Format a STAC ISO-8601 acquisition datetime as a ``YYYY-MM-DD_HHMMSS`` folder.

    Accepts the shapes STAC emits, e.g. ``2024-08-30T10:18:16.322000Z`` or
    ``2024-06-15T10:23:45Z`` (fractional seconds and a trailing ``Z`` are both
    optional). Raises ``ValueError`` on empty or unparseable input so the caller
    can fall back to a flat path.
    """
    if not iso:
        raise ValueError("empty datetime string")

    text = iso.strip()
    # datetime.fromisoformat handles offsets but not a bare trailing "Z".
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    dt = datetime.fromisoformat(normalized)
    return dt.strftime("%Y-%m-%d_%H%M%S")
