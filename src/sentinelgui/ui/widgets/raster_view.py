"""Interactive raster canvas for the results viewer.

A ``QGraphicsView`` that stacks two pixmap items — a base backdrop and an overlay —
and drives the overlay's transparency live. This is the *only* place that converts a
numpy array into a Qt image; the arrays themselves come from the Qt-free
:mod:`sentinelgui.core.raster_io`.

Opacity is applied via ``QGraphicsPixmapItem.setOpacity`` (cheap, no rebuild). The
threshold makes overlay pixels transparent where the overlay's single-band mask value
falls below the cutoff; it rebuilds the overlay's alpha channel only when it changes.
Pan is drag-to-scroll, zoom is the mouse wheel, and :meth:`fit` resets to fit-to-window.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView


class RasterView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self.base_item = QGraphicsPixmapItem()
        self.base_item.setZValue(0)
        self.overlay_item = QGraphicsPixmapItem()
        self.overlay_item.setZValue(1)
        self._scene.addItem(self.base_item)
        self._scene.addItem(self.overlay_item)

        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # cached overlay source so threshold changes can rebuild the alpha channel
        self._overlay_rgb: np.ndarray | None = None
        self._overlay_mask: np.ndarray | None = None
        self._threshold: float = 0.0

    # -- numpy -> Qt (the only Qt-image conversion in the app) --

    @staticmethod
    def numpy_to_qimage(arr: np.ndarray) -> QImage:
        """Convert an ``(H, W, 3)`` or ``(H, W, 4)`` uint8 array to a detached ``QImage``."""
        arr = np.ascontiguousarray(arr)
        height, width = arr.shape[:2]
        if arr.ndim == 3 and arr.shape[2] == 4:
            fmt = QImage.Format.Format_RGBA8888
            bytes_per_line = 4 * width
        elif arr.ndim == 3 and arr.shape[2] == 3:
            fmt = QImage.Format.Format_RGB888
            bytes_per_line = 3 * width
        else:
            raise ValueError(f"expected (H, W, 3|4) uint8, got shape {arr.shape}")
        image = QImage(arr.tobytes(), width, height, bytes_per_line, fmt)
        return image.copy()  # detach from the temporary bytes buffer

    # -- base --

    def set_base(self, rgb: np.ndarray) -> None:
        pixmap = QPixmap.fromImage(self.numpy_to_qimage(rgb))
        self.base_item.setPixmap(pixmap)
        self._scene.setSceneRect(self.base_item.boundingRect())
        self.fit()

    # -- overlay --

    def set_overlay(self, rgb: np.ndarray, mask: np.ndarray | None = None) -> None:
        """Show ``rgb`` as the overlay; ``mask`` (H, W in [0, 1]) enables thresholding."""
        self._overlay_rgb = np.ascontiguousarray(rgb)
        self._overlay_mask = None if mask is None else np.ascontiguousarray(mask)
        self.overlay_item.setVisible(True)
        self._rebuild_overlay()

    def clear_overlay(self) -> None:
        self._overlay_rgb = None
        self._overlay_mask = None
        self.overlay_item.setPixmap(QPixmap())
        self.overlay_item.setVisible(False)

    def has_overlay(self) -> bool:
        return self._overlay_rgb is not None

    def supports_threshold(self) -> bool:
        return self._overlay_mask is not None

    def _rebuild_overlay(self) -> None:
        if self._overlay_rgb is None:
            return
        height, width = self._overlay_rgb.shape[:2]
        rgba = np.empty((height, width, 4), dtype=np.uint8)
        rgba[..., :3] = self._overlay_rgb
        if self._overlay_mask is None:
            rgba[..., 3] = 255
        else:
            rgba[..., 3] = np.where(self._overlay_mask >= self._threshold, 255, 0)
        self.overlay_item.setPixmap(QPixmap.fromImage(self.numpy_to_qimage(rgba)))

    def set_overlay_opacity(self, value: float) -> None:
        """Set the overlay opacity, ``value`` in ``[0, 1]``."""
        self.overlay_item.setOpacity(max(0.0, min(1.0, value)))

    def set_overlay_threshold(self, value: float) -> None:
        """Hide overlay pixels whose mask value is below ``value`` (``[0, 1]``)."""
        self._threshold = max(0.0, min(1.0, value))
        self._rebuild_overlay()

    # -- pan / zoom --

    def fit(self) -> None:
        rect = self._scene.sceneRect()
        if not rect.isEmpty():
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event) -> None:
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)
