"""Freeze the default values of ``ProcessingParams`` — they must match the
``.get(key, default)`` fallbacks the ProcessingWorker used with the old loose
dict, so the dict->dataclass migration stays behavior-neutral.

"""

from sentinelgui.core.models import ProcessingParams


def test_required_fields_and_defaults():
    params = ProcessingParams(
        scene_index=0,
        bbox=(11.0, 46.0, 11.5, 46.5),
        bands_to_load={"b04", "b08"},
        output="/tmp/out",
    )

    assert params.scene_index == 0
    assert params.bbox == (11.0, 46.0, 11.5, 46.5)
    assert params.bands_to_load == {"b04", "b08"}
    assert params.output == "/tmp/out"
    # Defaults must equal the worker's old .get() fallbacks.
    assert params.algorithms == []
    assert params.save_bands is False
    assert params.save_color is False
    assert params.rgb is False
    assert params.bit_depth == 16
    assert params.ref_band is None


def test_default_algorithms_list_is_not_shared():
    """field(default_factory=list) — each instance gets its own list."""
    a = ProcessingParams(0, (0.0, 0.0, 1.0, 1.0), {"b04"}, "/tmp/a")
    b = ProcessingParams(1, (0.0, 0.0, 1.0, 1.0), {"b04"}, "/tmp/b")
    a.algorithms.append("NDVI")
    assert b.algorithms == []
