"""Typed dataclasses that cross the core/UI boundary. Qt-free — never import PySide6."""

from dataclasses import dataclass, field


@dataclass
class ProcessingParams:
    """Inputs for :meth:`core.processor.Sentinel2COGProcessor.process_scene`.

    The defaults mirror the ``.get(key, default)`` fallbacks the GUI worker used
    when this was passed as a loose dict, so switching call-sites to the dataclass
    keeps observable behavior identical.
    """

    scene_index: int
    bbox: tuple[float, float, float, float]
    bands_to_load: set[str]
    output: str
    algorithms: list[str] = field(default_factory=list)
    save_bands: bool = False
    save_color: bool = False
    rgb: bool = False
    bit_depth: int = 16
    ref_band: str | None = None
