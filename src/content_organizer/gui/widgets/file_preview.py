"""Review preview: the image itself, or a file-type tile for everything else."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QImageReader, QPainter, QPainterPath, QPaintEvent
from PyQt6.QtWidgets import QSizePolicy, QWidget

from content_organizer.categories import MediaType
from content_organizer.gui import icons, theme

_MEDIA_ICONS = {
    MediaType.VIDEO: ("video", "Video"),
    MediaType.IMAGE: ("image", "Image"),
    MediaType.AUDIO: ("music", "Audio"),
    MediaType.PROJECT: ("layers", "Project"),
    MediaType.OTHER: ("file", "File"),
}
_MAX_DECODE = QSize(1600, 1600)


def load_image(path: Path) -> QImage:
    """Decode an image scaled down to a sane size, honouring EXIF rotation."""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    too_big = size.width() > _MAX_DECODE.width() or size.height() > _MAX_DECODE.height()
    if size.isValid() and too_big:
        reader.setScaledSize(size.scaled(_MAX_DECODE, Qt.AspectRatioMode.KeepAspectRatio))
    return reader.read()


class FilePreview(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image = QImage()
        self._extension = ""
        self._media = MediaType.OTHER
        self.setMinimumSize(240, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("File preview")
        theme.manager().changed.connect(self.update)

    @property
    def mode(self) -> str:
        return "image" if not self._image.isNull() else "tile"

    def show_file(self, path: Path, media: MediaType) -> None:
        self._media = media
        self._extension = path.suffix.lstrip(".").upper() or "FILE"
        self._image = load_image(path) if media is MediaType.IMAGE else QImage()
        kind = _MEDIA_ICONS[media][1]
        tip = path.name if self.mode == "image" else f"No preview for {kind.lower()} files"
        self.setToolTip(tip)
        self.update()

    def clear(self) -> None:
        self._image = QImage()
        self._extension = ""
        self.update()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        frame = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(frame, theme.RADIUS_LG, theme.RADIUS_LG)
        painter.fillPath(clip, QColor(p.input))
        if self.mode == "image":
            self._paint_image(painter, frame)
        elif self._extension:
            self._paint_tile(painter, p, frame)
        painter.setPen(QColor(p.border))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(frame, theme.RADIUS_LG, theme.RADIUS_LG)
        painter.end()

    def _paint_image(self, painter: QPainter, frame: QRectF) -> None:
        area = frame.adjusted(12, 12, -12, -12)
        size = QSize(self._image.width(), self._image.height()).scaled(
            area.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio
        )
        target = QRectF(0, 0, size.width(), size.height())
        target.moveCenter(area.center())
        path = QPainterPath()
        path.addRoundedRect(target, theme.RADIUS, theme.RADIUS)
        painter.save()
        painter.setClipPath(path)
        painter.drawImage(target, self._image)
        painter.restore()

    def _paint_tile(self, painter: QPainter, p: theme.Palette, frame: QRectF) -> None:
        icon_name, kind = _MEDIA_ICONS[self._media]
        tile = QRectF(0, 0, 132, 160)
        tile.moveCenter(frame.center())
        tile.translate(0, -12)
        painter.setPen(QColor(p.border_strong))
        painter.setBrush(QColor(p.surface))
        painter.drawRoundedRect(tile, 14, 14)
        icons.icon(icon_name, p.text_muted).paint(
            painter, QRectF(tile.center().x() - 18, tile.top() + 30, 36, 36).toRect()
        )
        font = QFont(self.font())
        font.setPixelSize(26 if len(self._extension) <= 4 else 18)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(p.text))
        painter.drawText(
            QRectF(tile.left() + 6, tile.top() + 80, tile.width() - 12, 36),
            Qt.AlignmentFlag.AlignCenter,
            painter.fontMetrics().elidedText(
                self._extension, Qt.TextElideMode.ElideRight, round(tile.width() - 16)
            ),
        )
        small = QFont(self.font())
        small.setPixelSize(theme.FONT_CAPTION)
        painter.setFont(small)
        painter.setPen(QColor(p.text_faint))
        painter.drawText(
            QRectF(tile.left(), tile.top() + 116, tile.width(), 20),
            Qt.AlignmentFlag.AlignCenter,
            f"{kind} file",
        )
        painter.drawText(
            QRectF(frame.left(), tile.bottom() + 12, frame.width(), 20),
            Qt.AlignmentFlag.AlignCenter,
            "No preview available. Press O to open it.",
        )
