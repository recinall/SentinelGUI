"""Characterization tests for create_overlay.py (hex_to_rgba + create_overlay).

These tests freeze the CURRENT, observable behavior of the overlay-generation logic
(colormap/normalization math, alpha compositing, degenerate branches, and error
handling) using small hand-built in-memory PIL images, so a future move of this
code into core/overlay.py cannot silently change semantics.

No network calls and no real disk I/O are performed:
- `PIL.Image.open` is monkeypatched (via `sentinelgui.create_overlay.Image.open`,
  which is the *same object* as `PIL.Image.open` since create_overlay.py does
  `from PIL import Image`) to return pre-built in-memory images instead of reading
  from `rgb_path` / `index_path`.
- `PIL.Image.Image.save` is monkeypatched (via `co.Image.Image.save`) to record the
  final image's array/mode instead of writing `output_path` to disk.

These are the two seams the next agent must preserve when this logic moves under
`core/overlay.py`.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

import sentinelgui.core.overlay as co
from sentinelgui.core.overlay import create_overlay, hex_to_rgba

# --------------------------------------------------------------------------- #
# Shared monkeypatch helpers
# --------------------------------------------------------------------------- #


class SavedImage:
    """Snapshot of the image that create_overlay() would have written to disk."""

    def __init__(self, image: Image.Image) -> None:
        self.array = np.array(image)
        self.mode = image.mode


def _capture_save(monkeypatch: pytest.MonkeyPatch) -> list[SavedImage]:
    """Patch PIL.Image.Image.save to record the final image instead of writing it."""
    saved: list[SavedImage] = []

    def fake_save(self: Image.Image, _path, *args, **kwargs) -> None:  # noqa: ANN001
        saved.append(SavedImage(self))

    monkeypatch.setattr(co.Image.Image, "save", fake_save)
    return saved


def _patch_open_sequence(monkeypatch: pytest.MonkeyPatch, images: list[Image.Image]) -> None:
    """Patch Image.open to return `images` in call order (1 per Image.open call)."""
    it = iter(images)

    def fake_open(_path):  # noqa: ANN001
        return next(it)

    monkeypatch.setattr(co.Image, "open", fake_open)


def _patch_open_raises(monkeypatch: pytest.MonkeyPatch, message: str) -> None:
    def fake_open(_path):  # noqa: ANN001
        raise OSError(message)

    monkeypatch.setattr(co.Image, "open", fake_open)


# --------------------------------------------------------------------------- #
# hex_to_rgba
# --------------------------------------------------------------------------- #


def test_hex_to_rgba_six_digit_with_hash():
    """6-digit '#RRGGBB' -> (r, g, b, 255)."""
    assert hex_to_rgba("#FF8000") == (255, 128, 0, 255)


def test_hex_to_rgba_six_digit_without_hash():
    """Leading '#' is optional for the 6-digit form."""
    assert hex_to_rgba("00FF00") == (0, 255, 0, 255)


def test_hex_to_rgba_eight_digit_with_alpha_and_hash():
    """8-digit '#RRGGBBAA' -> (r, g, b, a), alpha taken from the input, not forced to 255."""
    assert hex_to_rgba("#11223344") == (0x11, 0x22, 0x33, 0x44)


def test_hex_to_rgba_eight_digit_without_hash():
    assert hex_to_rgba("AABBCCDD") == (0xAA, 0xBB, 0xCC, 0xDD)


def test_hex_to_rgba_invalid_length_raises_value_error():
    with pytest.raises(ValueError, match="Invalid hex color format"):
        hex_to_rgba("#ABC")


# --------------------------------------------------------------------------- #
# create_overlay: mode='gradient', no rgb base
# --------------------------------------------------------------------------- #


def test_gradient_mode_no_rgb_produces_expected_rgba(monkeypatch):
    """Frozen output of the pure-gradient path: black->white LinearSegmentedColormap
    over levels_pct=[0, 100], normalized by the same percentiles of index_data.
    """
    saved = _capture_save(monkeypatch)
    index_arr = np.array([[0, 100], [200, 255]], dtype=np.uint8)
    index_img = Image.fromarray(index_arr, "L")
    _patch_open_sequence(monkeypatch, [index_img])

    create_overlay(
        None, "fake_index.png", "fake_out.tif",
        [0.0, 100.0], ["#000000", "#ffffff"], 0.7, 10.0, "gradient",
    )

    assert len(saved) == 1
    assert saved[0].mode == "RGBA"
    expected = np.array(
        [
            [[0, 0, 0, 255], [100, 100, 100, 255]],
            [[200, 200, 200, 255], [255, 255, 255, 255]],
        ],
        dtype=np.uint8,
    )
    np.testing.assert_array_equal(saved[0].array, expected)


def test_progress_callback_emits_expected_milestones(monkeypatch):
    """Freeze the exact milestone lines emitted on the success path (no-rgb run)
    so the injected-callback contract cannot drift silently.
    """
    _capture_save(monkeypatch)
    index_arr = np.array([[0, 100], [200, 255]], dtype=np.uint8)
    index_img = Image.fromarray(index_arr, "L")
    _patch_open_sequence(monkeypatch, [index_img])

    messages: list[str] = []
    create_overlay(
        None, "fake_index.png", "fake_out.tif",
        [0.0, 100.0], ["#000000", "#ffffff"], 0.7, 10.0, "gradient",
        progress=messages.append,
    )

    assert messages == [
        "Loaded index image",
        "Computed percentile levels",
        "Built overlay image",
        "Saving overlay to fake_out.tif",
    ]


def test_gradient_degenerate_vmin_gte_vmax_uses_single_color(monkeypatch):
    """When levels_val[0] >= levels_val[-1] (e.g. a constant index), the gradient
    branch degenerates to a single-color ListedColormap([colors[0]]).
    """
    saved = _capture_save(monkeypatch)
    index_arr = np.array([[5, 5], [5, 5]], dtype=np.uint8)  # constant -> vmin == vmax
    index_img = Image.fromarray(index_arr, "L")
    _patch_open_sequence(monkeypatch, [index_img])

    create_overlay(
        None, "fake_index.png", "fake_out.tif",
        [0.0, 100.0], ["#123456", "#abcdef"], 0.7, 10.0, "gradient",
    )

    expected = np.full((2, 2, 4), [18, 52, 86, 255], dtype=np.uint8)
    np.testing.assert_array_equal(saved[0].array, expected)


# --------------------------------------------------------------------------- #
# create_overlay: mode='class', no rgb base
# --------------------------------------------------------------------------- #


def test_class_mode_no_rgb_produces_expected_bins(monkeypatch):
    """Frozen BoundaryNorm binning: 4 levels (percentiles 0/25/50/100) -> 3 colors."""
    saved = _capture_save(monkeypatch)
    index_arr = np.array([[0, 50], [100, 200]], dtype=np.uint8)
    index_img = Image.fromarray(index_arr, "L")
    _patch_open_sequence(monkeypatch, [index_img])

    # np.percentile(index_arr, [0, 25, 50, 100]) == [0, 37.5, 75, 200]
    create_overlay(
        None, "fake_index.png", "fake_out.tif",
        [0.0, 25.0, 50.0, 100.0], ["#ff0000", "#00ff00", "#0000ff"], 0.7, 10.0, "class",
    )

    expected = np.array(
        [
            [[255, 0, 0, 255], [0, 255, 0, 255]],
            [[0, 0, 255, 255], [0, 0, 255, 255]],
        ],
        dtype=np.uint8,
    )
    np.testing.assert_array_equal(saved[0].array, expected)


def test_class_mode_non_monotonic_levels_gets_epsilon_fix(monkeypatch):
    """Mostly-constant data collapses several percentiles to the same value
    ([0, 0, 0, 100]); the monotonic epsilon-fix nudges levels[1] and levels[2]
    up by np.finfo(eps) so BoundaryNorm still gets strictly increasing edges,
    but the fix is small enough that only the true outlier lands in the last bin.
    """
    saved = _capture_save(monkeypatch)
    index_arr = np.array([[0, 0, 0, 0, 0], [0, 0, 0, 0, 100]], dtype=np.uint8)
    index_img = Image.fromarray(index_arr, "L")
    _patch_open_sequence(monkeypatch, [index_img])

    create_overlay(
        None, "fake_index.png", "fake_out.tif",
        [0.0, 25.0, 50.0, 100.0], ["#ff0000", "#00ff00", "#0000ff"], 0.7, 10.0, "class",
    )

    expected = np.full((2, 5, 4), [255, 0, 0, 255], dtype=np.uint8)
    expected[1, 4] = [0, 0, 255, 255]
    np.testing.assert_array_equal(saved[0].array, expected)


# --------------------------------------------------------------------------- #
# create_overlay: with an rgb base image
# --------------------------------------------------------------------------- #


def test_with_rgb_base_alpha_threshold_and_composite(monkeypatch):
    """With an rgb base: pixels below the threshold percentile become fully
    transparent (alpha 0), pixels at/above get alpha=int(opacity*255); the overlay
    is alpha-composited onto the base and the final image is converted to 'RGB'.
    """
    saved = _capture_save(monkeypatch)
    base_arr = np.zeros((2, 2, 4), dtype=np.uint8)
    base_arr[:, :, 0] = 200
    base_arr[:, :, 3] = 255
    base_img = Image.fromarray(base_arr, "RGBA")

    index_arr = np.array([[0, 100], [200, 255]], dtype=np.uint8)
    index_img = Image.fromarray(index_arr, "L")

    # base_image is opened first (rgb_path truthy), then index_image.
    _patch_open_sequence(monkeypatch, [base_img, index_img])

    create_overlay(
        "fake_rgb.png", "fake_index.png", "fake_out.tif",
        [0.0, 100.0], ["#000000", "#ffffff"], 0.5, 50.0, "gradient",
    )

    assert saved[0].mode == "RGB"
    # threshold_val = percentile(index_arr, 50) = 150 -> pixels 0,100 transparent
    # (fall back to opaque base red); pixels 200,255 composited at alpha=127.
    expected = np.array(
        [
            [[200, 0, 0], [200, 0, 0]],
            [[200, 100, 100], [227, 127, 127]],
        ],
        dtype=np.uint8,
    )
    np.testing.assert_array_equal(saved[0].array, expected)


def test_with_rgb_base_resizes_index_to_base_size_when_sizes_differ(monkeypatch):
    """If base_image.size != index_image.size, the index image is resized to the
    base's size with NEAREST resampling before anything else happens.
    """
    resize_calls = []
    orig_resize = Image.Image.resize

    def spy_resize(self, size, resample=None, *args, **kwargs):
        resize_calls.append((size, resample))
        return orig_resize(self, size, resample, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "resize", spy_resize)
    saved = _capture_save(monkeypatch)

    base_arr = np.zeros((2, 2, 4), dtype=np.uint8)
    base_arr[:, :, 0] = 200
    base_arr[:, :, 3] = 255
    base_img = Image.fromarray(base_arr, "RGBA")  # size (2, 2)

    index_arr = np.full((4, 4), 128, dtype=np.uint8)  # size (4, 4), uniform value
    index_img = Image.fromarray(index_arr, "L")

    _patch_open_sequence(monkeypatch, [base_img, index_img])

    create_overlay(
        "fake_rgb.png", "fake_index.png", "fake_out.tif",
        [0.0, 100.0], ["#000000", "#ffffff"], 0.5, 0.0, "gradient",
    )

    assert resize_calls == [((2, 2), Image.Resampling.NEAREST)]
    assert saved[0].array.shape == (2, 2, 3)  # resized down to base's (2, 2)


# --------------------------------------------------------------------------- #
# create_overlay: index image is RGB -> grayscale conversion + warning
# --------------------------------------------------------------------------- #


def test_index_image_rgb_converted_to_grayscale_with_warning(monkeypatch, capsys):
    """A 3-D (RGB) index image triggers a stderr warning and an 'L' conversion
    (standard ITU-R 601-2 luma weights) before any index math runs.
    """
    saved = _capture_save(monkeypatch)
    index_arr = np.zeros((2, 2, 3), dtype=np.uint8)
    index_arr[0, 0] = [10, 20, 30]
    index_arr[0, 1] = [255, 255, 255]
    index_arr[1, 0] = [0, 0, 0]
    index_arr[1, 1] = [128, 128, 128]
    index_img = Image.fromarray(index_arr, "RGB")
    _patch_open_sequence(monkeypatch, [index_img])

    create_overlay(
        None, "fake_index.png", "fake_out.tif",
        [0.0, 100.0], ["#000000", "#ffffff"], 0.5, 0.0, "gradient",
    )

    err = capsys.readouterr().err
    assert "Warning: Index image appears to be RGB. Converting to grayscale." in err

    expected = np.array(
        [
            [[18, 18, 18, 255], [255, 255, 255, 255]],
            [[0, 0, 0, 255], [128, 128, 128, 255]],
        ],
        dtype=np.uint8,
    )
    np.testing.assert_array_equal(saved[0].array, expected)


# --------------------------------------------------------------------------- #
# create_overlay: error / degenerate paths that call sys.exit(1)
# --------------------------------------------------------------------------- #


def test_empty_index_image_exits(monkeypatch, capsys):
    empty_img = Image.fromarray(np.zeros((0, 0), dtype=np.uint8), "L")
    _patch_open_sequence(monkeypatch, [empty_img])

    with pytest.raises(SystemExit) as exc_info:
        create_overlay(
            None, "idx.png", "out.tif",
            [0.0, 100.0], ["#000000", "#ffffff"], 0.5, 0.0, "gradient",
        )

    assert exc_info.value.code == 1
    assert "Error: Index image is empty." in capsys.readouterr().err


def test_percentile_nan_exits(monkeypatch, capsys):
    """A float ('F' mode) index image containing NaN makes np.percentile return
    NaN, which is treated as a fatal input error.
    """
    arr = np.array([[0.0, np.nan], [1.0, 2.0]], dtype=np.float32)
    nan_img = Image.fromarray(arr, "F")
    _patch_open_sequence(monkeypatch, [nan_img])

    with pytest.raises(SystemExit) as exc_info:
        create_overlay(
            None, "idx.tif", "out.tif",
            [0.0, 100.0], ["#000000", "#ffffff"], 0.5, 0.0, "gradient",
        )

    assert exc_info.value.code == 1
    assert (
        "Error: Percentile calculation resulted in NaN. Check index image."
        in capsys.readouterr().err
    )


def test_index_open_ioerror_exits_with_message(monkeypatch, capsys):
    _patch_open_raises(monkeypatch, "cannot identify image file")

    with pytest.raises(SystemExit) as exc_info:
        create_overlay(
            None, "idx.tif", "out.tif",
            [0.0, 100.0], ["#000000", "#ffffff"], 0.5, 0.0, "gradient",
        )

    assert exc_info.value.code == 1
    assert "Error opening index file: cannot identify image file" in capsys.readouterr().err


def test_rgb_open_ioerror_exits_with_message(monkeypatch, capsys):
    """When rgb_path is given, the RGB base is opened first; its IOError is
    reported (and exits) before the index file is ever touched.
    """
    _patch_open_raises(monkeypatch, "cannot identify image file")

    with pytest.raises(SystemExit) as exc_info:
        create_overlay(
            "rgb.tif", "idx.tif", "out.tif",
            [0.0, 100.0], ["#000000", "#ffffff"], 0.5, 0.0, "gradient",
        )

    assert exc_info.value.code == 1
    assert "Error opening RGB file: cannot identify image file" in capsys.readouterr().err
