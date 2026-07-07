"""Headless tests for the project/date output-folder wiring in ``Sentinel2GUI``.

Feature: outputs are organized as ``<output_dir>/<project-or-MGRS>/<scene-datetime>/``.
Exercises the controller helpers (``_scene_output_dir`` / ``_project_dir``) offscreen
with a faked ``self.scenes`` — no network, no processing, no windows shown.
"""

import pytest

from sentinelgui.ui.main_window import Sentinel2GUI

_FAKE_SCENE = {
    "properties": {
        "datetime": "2024-08-30T10:18:16.322000Z",
        "mgrs:utm_zone": "32", "mgrs:latitude_band": "T", "mgrs:grid_square": "PS",
    }
}


@pytest.fixture
def window(qapp):
    w = Sentinel2GUI()
    yield w
    w.close()


def test_project_name_defaults_empty_and_reads_back(window):
    tab = window.output_tab
    assert tab.project_name() == ""
    tab.project_name_edit.setText("Vigneto Trento")
    assert tab.project_name() == "Vigneto Trento"


def test_scene_output_dir_uses_sanitized_project_and_datetime(window, tmp_path):
    window.output_tab.output_path_edit.setText(str(tmp_path))
    window.output_tab.project_name_edit.setText("Vigneto Trento")
    window.scenes = [_FAKE_SCENE]
    assert window._scene_output_dir(0) == tmp_path / "Vigneto-Trento" / "2024-08-30_101816"


def test_scene_output_dir_falls_back_to_mgrs_when_no_project(window, tmp_path):
    window.output_tab.output_path_edit.setText(str(tmp_path))
    window.output_tab.project_name_edit.setText("")
    window.scenes = [_FAKE_SCENE]
    assert window._scene_output_dir(0) == tmp_path / "32TPS" / "2024-08-30_101816"


def test_project_dir_stays_flat_without_project_or_scene(window, tmp_path):
    from pathlib import Path

    window.output_tab.output_path_edit.setText(str(tmp_path))
    window.output_tab.project_name_edit.setText("")
    assert window._project_dir() == Path(str(tmp_path))
