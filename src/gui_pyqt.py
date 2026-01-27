"""
Jacob's Content Organization Tool - Complete PyQt6 Implementation
Full-featured GUI with working charts, stats, and premium visuals.
"""

import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog, QMessageBox,
    QFrame, QProgressBar, QCheckBox, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QRectF
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QLinearGradient, QPainterPath

import logging

try:
    from organizer import ContentOrganizer, OrganizationStats
    from utils import validate_folder_path, download_ffmpeg
except ImportError:
    from .organizer import ContentOrganizer, OrganizationStats
    from .utils import validate_folder_path, download_ffmpeg

logger = logging.getLogger(__name__)


# Premium Colors
COLORS = {
    'bg_dark': '#0F172A',          # Slate 900 - Match reference
    'bg_card': '#1E293B',          # Slate 800 - Match reference
    'bg_card_hover': '#334155',    # Slate 700
    'accent_purple': '#8B5CF6',    # Purple 500 - Match reference
    'accent_blue': '#3B82F6',      # Blue 500
    'accent_orange': '#F59E0B',    # Amber 500 - Match reference
    'text_primary': '#F1F5F9',     # Slate 100 - Clean white
    'text_secondary': '#94A3B8',   # Slate 400
    'success': '#10B981',          # Green 500 - Match reference
    'border': '#334155',           # Slate 700
    'gradient_yellow': '#FFD60A',
    'gradient_green': '#32D74B',
    'gradient_blue': '#0A84FF',
}


# Premium Stylesheet
STYLESHEET = f"""
QMainWindow {{
    background-color: {COLORS['bg_dark']};
}}
QWidget {{
    color: {COLORS['text_primary']};
    font-family: 'Segoe UI', 'SF Pro Display', Arial;
}}
QLabel#title {{
    font-size: 36px;
    font-weight: bold;
}}
QLabel#subtitle {{
    font-size: 14px;
    color: {COLORS['text_secondary']};
}}
QLabel#cardTitle {{
    font-size: 16px;
    font-weight: bold;
}}
QLabel#hint {{
    font-size: 11px;
    color: {COLORS['text_secondary']};
}}
QLineEdit {{
    background-color: {COLORS['bg_card']};
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 10px;
    padding: 12px;
    color: {COLORS['text_primary']};
    font-size: 13px;
}}
QLineEdit:focus {{
    border: 1px solid rgba(139, 92, 246, 0.3);
    background-color: rgba(30, 41, 59, 0.8);
}}
QPushButton {{
    background-color: {COLORS['accent_blue']};
    color: white;
    border: none;
    border-radius: 12px;
    padding: 15px 30px;
    font-size: 16px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: #5A9FF2;
}}
QPushButton#secondaryButton {{
    background-color: {COLORS['accent_orange']};
}}
QPushButton#secondaryButton:hover {{
    background-color: #FFA520;
}}
QProgressBar {{
    border: none;
    border-radius: 25px;
    background-color: #1a1a1a;
    height: 50px;
    text-align: center;
    color: white;
    font-size: 18px;
    font-weight: bold;
}}
QProgressBar::chunk {{
    border-radius: 25px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS['gradient_yellow']}, 
        stop:0.5 {COLORS['gradient_green']}, 
        stop:1 {COLORS['gradient_blue']});
}}
QCheckBox {{
    color: {COLORS['text_primary']};
    spacing: 10px;
}}
QCheckBox::indicator {{
    width: 45px;
    height: 25px;
    border-radius: 12px;
}}
QCheckBox::indicator:unchecked {{
    background-color: {COLORS['border']};
}}
QCheckBox::indicator:checked {{
    background-color: {COLORS['success']};
}}
"""


class AnimatedToggle(QWidget):
    """Animated toggle switch with smooth pulse effect."""
    toggled = pyqtSignal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, 30)
        self.checked = True
        self.animation_progress = 1.0
        self.pulse_progress = 0.0
        
        # Animation timer
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._animate)
        
        # Pulse timer
        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self._pulse)
    
    def isChecked(self):
        return self.checked
    
    def setChecked(self, checked):
        if self.checked != checked:
            self.checked = checked
            self.animation_progress = 1.0 if checked else 0.0
            self.update()
    
    def mousePressEvent(self, event):
        self.checked = not self.checked
        # Start animation
        self.anim_timer.start(16)  # 60fps
        # Start pulse when turning on
        if self.checked:
            self.pulse_progress = 1.0
            self.pulse_timer.start(16)
        self.toggled.emit(self.checked)
    
    def _animate(self):
        target = 1.0 if self.checked else 0.0
        diff = target - self.animation_progress
        
        if abs(diff) < 0.05:
            self.animation_progress = target
            self.anim_timer.stop()
        else:
            self.animation_progress += diff * 0.2
        
        self.update()
    
    def _pulse(self):
        self.pulse_progress -= 0.05
        if self.pulse_progress <= 0:
            self.pulse_progress = 0
            self.pulse_timer.stop()
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w, h = self.width(), self.height()
        
        # Track color
        if self.checked:
            track_color = QColor("#34C759")
        else:
            track_color = QColor("#3A3A3C")
        
        # Draw track
        painter.setBrush(track_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, w, h, h // 2, h // 2)
        
        # Pulse effect (glow)
        if self.pulse_progress > 0:
            pulse_size = int(10 * self.pulse_progress)
            pulse_alpha = int(100 * self.pulse_progress)
            pulse_color = QColor(52, 199, 89, pulse_alpha)
            painter.setBrush(pulse_color)
            thumb_x = int(5 + (w - h) * self.animation_progress)
            painter.drawEllipse(
                thumb_x - pulse_size, h // 2 - h // 2 - pulse_size,
                h + pulse_size * 2, h + pulse_size * 2
            )
        
        # Draw thumb
        thumb_x = int(5 + (w - h) * self.animation_progress)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(thumb_x, 5, h - 10, h - 10)


class Card(QFrame):
    """Premium card with shadow - no visible border."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_card']};
                border-radius: 20px;
                border: none;
                padding: 20px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setXOffset(0)
        shadow.setYOffset(15)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(shadow)


class CircularProgress(QWidget):
    """Circular progress ring widget with color-coded segments."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(180, 180)
        self.segments = {}  # {category: (count, color)}
        self.total = 0
        self.text = "0"
    
    def setValue(self, value, max_val=None, text=None):
        self.total = value if max_val is None else max_val
        if text is not None:
            self.text = text
        self.update()
    
    def setSegments(self, segments):
        """Set colored segments. segments = {category: (count, color)}"""
        self.segments = segments
        self.total = sum(count for count, _ in segments.values())
        self.text = str(self.total)
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2
        radius = min(w, h) // 2 - 25
        
        # Background circle
        pen = QPen(QColor(COLORS['border']))
        pen.setWidth(15)
        painter.setPen(pen)
        painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
        
        # Draw colored segments
        if self.total > 0 and self.segments:
            start_angle = 90 * 16  # Start at top
            
            for category, (count, color) in self.segments.items():
                if count > 0:
                    # Calculate span
                    percentage = count / self.total
                    span_angle = int(percentage * 360 * 16)
                    
                    pen = QPen(QColor(color))
                    pen.setWidth(15)
                    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    painter.setPen(pen)
                    
                    painter.drawArc(
                        cx - radius, cy - radius, radius * 2, radius * 2,
                        start_angle, -span_angle
                    )
                    
                    start_angle -= span_angle
        
        # Center text
        painter.setPen(QColor(COLORS['text_primary']))
        font = QFont("Segoe UI", 32, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, self.text)


class WaveChart(QWidget):
    """Smooth flowing wave chart like stock market graphs."""
    clicked = pyqtSignal(str, str)  # month, year
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)  # Taller for tooltip
        self.setMouseTracking(True)  # Enable hover tracking
        self.data = {}  # {month: {year: count}}
        self.folder_paths = {}  # {(month, year): path}
        self.hover_index = -1
        self.hover_value = 0
    
    def setData(self, data, folder_paths):
        self.data = data
        self.folder_paths = folder_paths
        self.update()
    
    def mouseMoveEvent(self, event):
        if not self.data:
            return
        
        months = sorted(self.data.keys())
        if not months:
            return
        
        values = [sum(self.data[m].values()) for m in months]
        
        w = self.width()
        x_spacing = (w - 60) / max(1, len(months) - 1) if len(months) > 1 else 0
        margin = 30
        x = event.pos().x()
        
        old_hover = self.hover_index
        self.hover_index = -1
        self.hover_value = 0
        
        for i in range(len(months)):
            point_x = margin + i * x_spacing if len(months) > 1 else w // 2
            if abs(x - point_x) < 25:  # 25px hit area
                self.hover_index = i
                self.hover_value = values[i]
                break
        
        if old_hover != self.hover_index:
            self.update()
    
    def mousePressEvent(self, event):
        if self.hover_index >= 0 and self.data:
            months = sorted(self.data.keys())
            if self.hover_index < len(months):
                month = months[self.hover_index]
                for (m, year), path in self.folder_paths.items():
                    if m == month:
                        self.clicked.emit(month, year)
                        break
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w, h = self.width(), self.height()
        
        if not self.data:
            painter.setPen(QColor(COLORS['text_secondary']))
            font = QFont("Segoe UI", 14)
            painter.setFont(font)
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "No data yet")
            return
        
        months = sorted(self.data.keys())
        if not months:
            return
        
        values = [sum(self.data[m].values()) for m in months]
        if not values:
            return
        
        max_val = max(values)
        if max_val == 0:
            max_val = 1
        
        margin = 30
        bottom = h - 40
        chart_height = h - 70
        
        # Calculate points for the wave
        points = []
        if len(months) == 1:
            x = w // 2
            y = bottom - (values[0] / max_val) * chart_height
            points.append((x, y))
        else:
            x_spacing = (w - 2 * margin) / (len(months) - 1)
            for i, val in enumerate(values):
                x = margin + i * x_spacing
                y = bottom - (val / max_val) * chart_height
                points.append((x, y))
        
        if not points:
            return
        
        # Create smooth wave path
        path = QPainterPath()
        path.moveTo(points[0][0], points[0][1])
        
        if len(points) > 2:
            # Smooth curve through points using quadratic bezier
            for i in range(len(points) - 1):
                x1, y1 = points[i]
                x2, y2 = points[i + 1]
                
                # Control point for smooth curve
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                
                path.quadTo(cx, y1, x2, y2)
        else:
            # Just lines for 2 or fewer points
            for x, y in points[1:]:
                path.lineTo(x, y)
        
        # Create filled area under the curve
        filled_path = QPainterPath(path)
        filled_path.lineTo(points[-1][0], bottom)
        filled_path.lineTo(points[0][0], bottom)
        filled_path.closeSubpath()
        
        # Gradient fill
        gradient = QLinearGradient(0, 0, w, 0)
        gradient.setColorAt(0, QColor(COLORS['gradient_yellow']))
        gradient.setColorAt(0.5, QColor(COLORS['gradient_green']))
        gradient.setColorAt(1, QColor(COLORS['gradient_blue']))
        
        # Semi-transparent fill
        painter.setOpacity(0.3)
        painter.fillPath(filled_path, gradient)
        
        # Draw the wave line
        painter.setOpacity(1.0)
        pen = QPen()
        pen.setWidth(3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        
        # Gradient pen
        gradient_pen = QLinearGradient(0, 0, w, 0)
        gradient_pen.setColorAt(0, QColor(COLORS['gradient_yellow']))
        gradient_pen.setColorAt(0.5, QColor(COLORS['gradient_green']))
        gradient_pen.setColorAt(1, QColor(COLORS['gradient_blue']))
        pen.setBrush(gradient_pen)
        
        painter.setPen(pen)
        painter.drawPath(path)
        
        # Draw points
        for i, (x, y) in enumerate(points):
            # Point color
            progress = i / max(1, len(points) - 1)
            if progress < 0.5:
                t = progress * 2
                r = int(255 * (1 - t) + 50 * t)
                g = int(214 * (1 - t) + 215 * t)
                b = int(10 * (1 - t) + 75 * t)
            else:
                t = (progress - 0.5) * 2
                r = int(50 * (1 - t) + 10 * t)
                g = int(215 * (1 - t) + 132 * t)
                b = int(75 * (1 - t) + 255 * t)
            
            color = QColor(r, g, b)
            
            # Draw point
            if i == self.hover_index:
                painter.setBrush(color)
                painter.setPen(QPen(QColor(255, 255, 255), 2))
                painter.drawEllipse(int(x - 8), int(y - 8), 16, 16)
            else:
                painter.setBrush(color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(int(x - 5), int(y - 5), 10, 10)
            
            # Month label
            painter.setPen(QColor(COLORS['text_secondary']))
            font = QFont("Segoe UI", 10)
            painter.setFont(font)
            month_abbr = months[i][:3]
            text_rect = QRectF(x - 20, bottom + 5, 40, 20)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, month_abbr)
            
            # Value label on hover
            if i == self.hover_index:
                painter.setPen(QColor(COLORS['text_primary']))
                font = QFont("Segoe UI", 14, QFont.Weight.Bold)
                painter.setFont(font)
                value_text = str(values[i])
                text_rect = QRectF(x - 30, y - 30, 60, 20)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, value_text)


class OrganizeThread(QThread):
    """Background organization thread."""
    progress = pyqtSignal(float, str, str)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    
    def __init__(self, organizer, everything, output, use_ffmpeg, clean_names, organize_by_date):
        super().__init__()
        self.organizer = organizer
        self.everything = everything
        self.output = output
        self.use_ffmpeg = use_ffmpeg
        self.clean_names = clean_names
        self.organize_by_date = organize_by_date
    
    def run(self):
        try:
            stats = self.organizer.organize_files(
                self.everything, self.output,
                self.use_ffmpeg, self.clean_names,
                self._progress_callback,
                self.organize_by_date
            )
            self.finished.emit(stats)
        except Exception as e:
            logger.error(f"Organization failed: {e}", exc_info=True)
            self.error.emit(str(e))
    
    def _progress_callback(self, progress, filename, category):
        self.progress.emit(progress, filename, category)


class MainApp(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        
        self.organizer = ContentOrganizer()
        
        self.everything_folder = ""
        self.output_folder = ""
        self.is_organizing = False
        
        self.monthly_data = defaultdict(lambda: defaultdict(int))
        self.category_counts = defaultdict(int)
        self.folder_paths = {}
        
        self._setup_ui()
        QTimer.singleShot(1000, self._check_ffmpeg)
    
    def _setup_ui(self):
        self.setWindowTitle("Jacob's Content Organization Tool")
        self.setMinimumSize(1500, 1000)  # Even wider to prevent clipping
        self.resize(1500, 1000)
        self.setStyleSheet(STYLESHEET)
        self._center_window()
        
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        self._create_header(main_layout)
        
        columns = QHBoxLayout()
        columns.setSpacing(15)
        
        # Left
        left_col = QVBoxLayout()
        left_col.setSpacing(15)
        self._create_folders_card(left_col)
        self._create_options_card(left_col)
        left_col.addStretch()
        columns.addLayout(left_col, 1)
        
        # Middle
        middle_col = QVBoxLayout()
        middle_col.setSpacing(15)
        self._create_progress_card(middle_col)
        self._create_chart_card(middle_col)
        columns.addLayout(middle_col, 1)
        
        # Right
        right_col = QVBoxLayout()
        right_col.setSpacing(15)
        self._create_stats_card(right_col)
        self._create_categories_card(right_col)
        right_col.addStretch()
        columns.addLayout(right_col, 1)
        
        main_layout.addLayout(columns)
        self._create_action_buttons(main_layout)
    
    def _center_window(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
    
    def _create_header(self, layout):
        header_layout = QVBoxLayout()
        header_layout.setSpacing(5)
        
        title = QLabel("Jacob's Content Organizer")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title)
        
        subtitle = QLabel("✨ Professional content management with intelligent detection")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(subtitle)
        
        layout.addLayout(header_layout)
    
    def _create_folders_card(self, layout):
        card = Card()
        card_layout = QVBoxLayout(card)
        
        lbl = QLabel("📥 Everything Folder")
        lbl.setObjectName("cardTitle")
        card_layout.addWidget(lbl)
        
        hint = QLabel("Your messy inbox")
        hint.setObjectName("hint")
        card_layout.addWidget(hint)
        
        folder_layout = QHBoxLayout()
        self.everything_input = QLineEdit()
        self.everything_input.setPlaceholderText("Select folder...")
        folder_layout.addWidget(self.everything_input)
        
        btn = QPushButton("Browse")
        btn.clicked.connect(self._browse_everything)
        btn.setFixedWidth(100)
        folder_layout.addWidget(btn)
        card_layout.addLayout(folder_layout)
        
        card_layout.addSpacing(15)
        
        lbl2 = QLabel("📂 Output Folder")
        lbl2.setObjectName("cardTitle")
        card_layout.addWidget(lbl2)
        
        hint2 = QLabel("Organized destination")
        hint2.setObjectName("hint")
        card_layout.addWidget(hint2)
        
        output_layout = QHBoxLayout()
        self.output_input = QLineEdit()
        self.output_input.setPlaceholderText("Select folder...")
        output_layout.addWidget(self.output_input)
        
        btn2 = QPushButton("Browse")
        btn2.clicked.connect(self._browse_output)
        btn2.setFixedWidth(100)
        output_layout.addWidget(btn2)
        card_layout.addLayout(output_layout)
        
        layout.addWidget(card)
    
    def _create_options_card(self, layout):
        card = Card()
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(18)
        
        title = QLabel("Options")
        title.setObjectName("cardTitle")
        card_layout.addWidget(title)
        card_layout.addSpacing(15)
        
        # FFmpeg toggle
        ffmpeg_row = QHBoxLayout()
        ffmpeg_label = QLabel("Video Analysis - Detect aspect ratios")
        ffmpeg_label.setStyleSheet("font-size: 14px; color: white;")
        ffmpeg_row.addWidget(ffmpeg_label)
        ffmpeg_row.addStretch()
        self.ffmpeg_toggle = AnimatedToggle()
        self.ffmpeg_toggle.setChecked(True)
        ffmpeg_row.addWidget(self.ffmpeg_toggle)
        card_layout.addLayout(ffmpeg_row)
        
        # Date toggle
        date_row = QHBoxLayout()
        date_label = QLabel("Date Folders - Month/Year sorting")
        date_label.setStyleSheet("font-size: 14px; color: white;")
        date_row.addWidget(date_label)
        date_row.addStretch()
        self.date_toggle = AnimatedToggle()
        self.date_toggle.setChecked(True)
        date_row.addWidget(self.date_toggle)
        card_layout.addLayout(date_row)
        
        # Clean names toggle
        clean_row = QHBoxLayout()
        clean_label = QLabel("Clean Names - Remove tags")
        clean_label.setStyleSheet("font-size: 14px; color: white;")
        clean_row.addWidget(clean_label)
        clean_row.addStretch()
        self.clean_toggle = AnimatedToggle()
        self.clean_toggle.setChecked(False)
        clean_row.addWidget(self.clean_toggle)
        card_layout.addLayout(clean_row)
        
        layout.addWidget(card)
    
    def _create_progress_card(self, layout):
        card = Card()
        card_layout = QVBoxLayout(card)
        
        self.progress_title = QLabel("Ready")
        self.progress_title.setObjectName("cardTitle")
        card_layout.addWidget(self.progress_title)
        card_layout.addSpacing(10)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        card_layout.addWidget(self.progress_bar)
        card_layout.addSpacing(10)
        
        self.status_label = QLabel("Select folders to begin")
        self.status_label.setObjectName("hint")
        self.status_label.setWordWrap(True)
        card_layout.addWidget(self.status_label)
        
        layout.addWidget(card)
    
    def _create_chart_card(self, layout):
        card = Card()
        card_layout = QVBoxLayout(card)
        
        title = QLabel("Monthly Distribution")
        title.setObjectName("cardTitle")
        card_layout.addWidget(title)
        
        hint = QLabel("Click points to open folder")
        hint.setObjectName("hint")
        card_layout.addWidget(hint)
        card_layout.addSpacing(10)
        
        self.chart = WaveChart()
        self.chart.clicked.connect(self._open_month_folder)
        card_layout.addWidget(self.chart)
        
        layout.addWidget(card)
    
    def _create_stats_card(self, layout):
        card = Card()
        card_layout = QVBoxLayout(card)
        
        title = QLabel("Total Files")
        title.setObjectName("cardTitle")
        card_layout.addWidget(title)
        
        # Folder selector for tracking
        track_layout = QHBoxLayout()
        track_layout.setSpacing(10)
        
        self.track_folder_input = QLineEdit()
        self.track_folder_input.setPlaceholderText("Select folder to track...")
        self.track_folder_input.setReadOnly(True)
        self.track_folder_input.setStyleSheet("font-size: 11px; padding: 8px;")
        track_layout.addWidget(self.track_folder_input)
        
        track_btn = QPushButton("Browse")
        track_btn.setFixedWidth(80)
        track_btn.setFixedHeight(35)
        track_btn.clicked.connect(self._browse_track_folder)
        track_layout.addWidget(track_btn)
        
        card_layout.addLayout(track_layout)
        card_layout.addSpacing(15)
        
        self.circular_progress = CircularProgress()
        card_layout.addWidget(self.circular_progress, alignment=Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(card)
    
    def _browse_track_folder(self):
        """Select a folder to track in the Total Files section."""
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Track")
        if folder:
            self.track_folder_input.setText(folder)
            self._scan_track_folder(Path(folder))
    
    def _scan_track_folder(self, folder_path):
        """Scan the tracked folder and update stats using REAL categorization."""
        category_counts = defaultdict(int)
        total = 0
        
        # Recursively scan and categorize each file
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = Path(root) / file
                ext = file_path.suffix.lower()
                
                # Skip non-media files
                if ext not in (self.organizer.VIDEO_EXTS | self.organizer.IMAGE_EXTS | 
                              self.organizer.AUDIO_EXTS | self.organizer.PREMIERE_EXTS):
                    continue
                
                # Use the organizer's ACTUAL categorization logic
                try:
                    # Check if file is already in an organized folder
                    parent_name = file_path.parent.name
                    
                    if parent_name in ['VerticalVideos', 'HorizontalVideos', 'FinalizedVideos', 
                                      'Images', 'SoundEffects', 'PremiereProjects', 'Music']:
                        # Already organized - use folder name
                        if parent_name == 'SoundEffects':
                            category_counts['SoundEffects'] += 1
                        elif parent_name == 'Music':
                            category_counts['SoundEffects'] += 1  # Group with audio
                        else:
                            category_counts[parent_name] += 1
                    else:
                        # Not organized yet - categorize by file type
                        if ext in self.organizer.IMAGE_EXTS:
                            category_counts['Images'] += 1
                        elif ext in self.organizer.AUDIO_EXTS:
                            category_counts['SoundEffects'] += 1
                        elif ext in self.organizer.PREMIERE_EXTS:
                            category_counts['PremiereProjects'] += 1
                        elif ext in self.organizer.VIDEO_EXTS:
                            # For videos, we need FFmpeg to determine vertical/horizontal
                            # For now, just count as generic
                            if self.ffmpeg_toggle.isChecked() and self.organizer.ffmpeg_available:
                                metadata = self.organizer._get_video_metadata(file_path)
                                if metadata:
                                    aspect = self.organizer._get_aspect_ratio(metadata)
                                    if aspect == 'vertical':
                                        category_counts['VerticalVideos'] += 1
                                    elif aspect == 'horizontal':
                                        category_counts['HorizontalVideos'] += 1
                                    else:
                                        # Unknown aspect
                                        category_counts['HorizontalVideos'] += 1
                                else:
                                    # FFmpeg failed
                                    category_counts['HorizontalVideos'] += 1
                            else:
                                # FFmpeg disabled - guess horizontal
                                category_counts['HorizontalVideos'] += 1
                    
                    total += 1
                except Exception as e:
                    logger.error(f"Error categorizing {file_path}: {e}")
                    continue
        
        # Update category bars
        segments = {}
        for key, (count_label, progress_bar, color) in self.category_bars.items():
            count = category_counts.get(key, 0)
            count_label.setText(str(count))
            
            if count > 0:
                segments[key] = (count, color)
            
            if total > 0:
                percentage = int((count / total) * 100)
                progress_bar.setValue(percentage)
            else:
                progress_bar.setValue(0)
        
        # Update circular progress
        if segments and total > 0:
            self.circular_progress.setSegments(segments)
        else:
            self.circular_progress.setValue(total, total, str(total))
    
    def _create_categories_card(self, layout):
        card = Card()
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(15)  # More spacing
        
        title = QLabel("Categories")
        title.setObjectName("cardTitle")
        card_layout.addWidget(title)
        card_layout.addSpacing(20)
        
        self.category_bars = {}
        categories = [
            ("Vertical Videos", "VerticalVideos", "#0A84FF"),
            ("Horizontal Videos", "HorizontalVideos", "#32D74B"),
            ("Finalized Videos", "FinalizedVideos", "#FFD60A"),  # Changed from Clips!
            ("Images", "Images", "#FF9500"),
            ("Audio", "SoundEffects", "#7B68EE"),
            ("Premiere Projects", "PremiereProjects", "#FF2D55"),  # Magenta
        ]
        
        for icon_text, key, color in categories:
            # Container for each category
            cat_container = QVBoxLayout()
            cat_container.setSpacing(8)
            
            # Label row
            label_row = QHBoxLayout()
            lbl = QLabel(icon_text)
            lbl.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 14px; font-weight: bold;")  # White and larger
            lbl.setMinimumWidth(200)  # Even wider to prevent clipping
            label_row.addWidget(lbl)
            label_row.addStretch()
            
            count = QLabel("0")
            count.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 16px; font-weight: bold;")
            count.setMinimumWidth(60)  # Space for larger numbers
            label_row.addWidget(count)
            
            cat_container.addLayout(label_row)
            
            # Progress bar
            progress = QProgressBar()
            progress.setMaximum(100)
            progress.setValue(0)
            progress.setTextVisible(False)
            progress.setFixedHeight(10)  # Slightly taller
            progress.setStyleSheet(f"""
                QProgressBar {{
                    border: none;
                    border-radius: 5px;
                    background-color: #2A2F45;
                }}
                QProgressBar::chunk {{
                    border-radius: 5px;
                    background-color: {color};
                }}
            """)
            cat_container.addWidget(progress)
            
            self.category_bars[key] = (count, progress, color)
            card_layout.addLayout(cat_container)
        
        layout.addWidget(card)
    
    def _create_action_buttons(self, layout):
        # Action bar like reference (Shop/Send/Receive style)
        action_container = QWidget()
        action_container.setFixedHeight(120)
        action_container.setStyleSheet(f"background: transparent;")
        
        button_layout = QHBoxLayout(action_container)
        button_layout.setSpacing(60)
        button_layout.setContentsMargins(0, 20, 0, 20)
        button_layout.addStretch()
        
        # Organize button (Purple circle with play icon)
        organize_container = QVBoxLayout()
        organize_container.setSpacing(8)
        
        self.organize_btn = QPushButton("▶")
        self.organize_btn.setFixedSize(70, 70)
        self.organize_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {COLORS['accent_purple']}, stop:1 #A78BFA);
                border: none;
                border-radius: 35px;
                color: white;
                font-size: 28px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: #A78BFA;
            }}
            QPushButton:pressed {{
                background: {COLORS['accent_purple']};
            }}
        """)
        self.organize_btn.clicked.connect(self.start_organizing)
        
        organize_label = QLabel("Organize")
        organize_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        organize_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px;")
        
        organize_container.addWidget(self.organize_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        organize_container.addWidget(organize_label)
        button_layout.addLayout(organize_container)
        
        # Review button (Orange circle with check icon)
        review_container = QVBoxLayout()
        review_container.setSpacing(8)
        
        self.review_btn = QPushButton("✓")
        self.review_btn.setFixedSize(70, 70)
        self.review_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {COLORS['accent_orange']}, stop:1 #FCA5A5);
                border: none;
                border-radius: 35px;
                color: white;
                font-size: 32px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: #FCA5A5;
            }}
            QPushButton:pressed {{
                background: {COLORS['accent_orange']};
            }}
        """)
        self.review_btn.clicked.connect(self.open_review)
        
        review_label = QLabel("Review")
        review_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        review_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px;")
        
        review_container.addWidget(self.review_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        review_container.addWidget(review_label)
        button_layout.addLayout(review_container)
        
        button_layout.addStretch()
        
        layout.addWidget(action_container)
    
    def _check_ffmpeg(self):
        if not self.organizer.ffmpeg_available:
            reply = QMessageBox.question(
                self, "FFmpeg Required",
                "FFmpeg is needed for video analysis.\n\nDownload now? (Takes ~1-2 minutes)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._download_ffmpeg_threaded()
            else:
                self.ffmpeg_toggle.setChecked(False)
    
    def _download_ffmpeg_threaded(self):
        """Download FFmpeg with REAL file-size-based progress."""
        from PyQt6.QtWidgets import QProgressDialog
        
        # Create progress dialog
        self.ffmpeg_dialog = QProgressDialog(
            "📥 Starting download...",
            "Cancel",
            0, 100,
            self
        )
        self.ffmpeg_dialog.setWindowTitle("Downloading FFmpeg")
        self.ffmpeg_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.ffmpeg_dialog.setMinimumDuration(0)
        self.ffmpeg_dialog.setValue(0)
        self.ffmpeg_dialog.show()
        
        self.ffmpeg_canceled = False
        self.ffmpeg_dialog.canceled.connect(lambda: setattr(self, 'ffmpeg_canceled', True))
        
        # Start download in thread
        import threading
        self.ffmpeg_zip_path = Path.cwd() / "ffmpeg" / "ffmpeg.zip"
        self.ffmpeg_total_size = 77 * 1024 * 1024  # ~77MB expected
        
        def download():
            try:
                from utils import download_ffmpeg
            except ImportError:
                from src.utils import download_ffmpeg
            success = download_ffmpeg()
            QTimer.singleShot(0, lambda: self._ffmpeg_complete(success))
        
        thread = threading.Thread(target=download, daemon=True)
        thread.start()
        
        # Poll file size every 500ms
        self.ffmpeg_poll_timer = QTimer(self)
        self.ffmpeg_poll_timer.timeout.connect(self._poll_ffmpeg_progress)
        self.ffmpeg_poll_timer.start(500)
    
    def _poll_ffmpeg_progress(self):
        """Poll the download file size to show real progress."""
        if self.ffmpeg_canceled:
            self.ffmpeg_poll_timer.stop()
            return
        
        try:
            if self.ffmpeg_zip_path.exists():
                current_size = self.ffmpeg_zip_path.stat().st_size
                downloaded_mb = current_size / (1024 * 1024)
                total_mb = self.ffmpeg_total_size / (1024 * 1024)
                percent = min(99, int((current_size / self.ffmpeg_total_size) * 100))
                
                self.ffmpeg_dialog.setValue(percent)
                self.ffmpeg_dialog.setLabelText(
                    f"📥 Downloading FFmpeg...\n\n{downloaded_mb:.1f} MB / {total_mb:.0f} MB"
                )
                
                # If download complete (file stopped growing), show extraction
                if current_size >= self.ffmpeg_total_size * 0.95:
                    self.ffmpeg_dialog.setLabelText(
                        f"📦 Extracting FFmpeg...\n\nThis may take 30 seconds..."
                    )
                    self.ffmpeg_dialog.setValue(100)
        except:
            pass
    
    def _ffmpeg_complete(self, success):
        """Handle FFmpeg download completion."""
        logger.info(f"FFmpeg completion callback called with success={success}")
        
        # Stop polling timer
        if hasattr(self, 'ffmpeg_poll_timer'):
            self.ffmpeg_poll_timer.stop()
        
        try:
            self.ffmpeg_dialog.close()
            logger.info("Closed FFmpeg dialog")
        except Exception as e:
            logger.error(f"Error closing dialog: {e}")
        
        if success:
            # CRITICAL: Force FFmpeg recheck after download!
            logger.info("Forcing FFmpeg recheck...")
            self.organizer.recheck_ffmpeg()
            logger.info(f"FFmpeg now available: {self.organizer.ffmpeg_available}")
            
            QMessageBox.information(
                self, "Success",
                "FFmpeg installed successfully!\n\nVideo analysis is now enabled."
            )
        
        if success:
            QMessageBox.information(
                self, "✅ Success", 
                "FFmpeg installed successfully!\n\nYou can now use video analysis."
            )
            self.organizer._ffmpeg_available = True
        else:
            QMessageBox.critical(
                self, "❌ Download Failed", 
                "Could not install FFmpeg.\n\nVideo analysis will be disabled."
            )
            self.ffmpeg_toggle.setChecked(False)
    
    def _browse_everything(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Everything Folder")
        if folder:
            self.everything_folder = folder
            self.everything_input.setText(folder)
            # Auto-analyze and show chart
            self._auto_analyze()
    
    def _auto_analyze(self):
        """Automatically analyze files and show chart when folder is selected."""
        if not self.everything_folder:
            return
        
        everything = Path(self.everything_folder)
        
        # Quick scan in background
        monthly_analysis = defaultdict(int)
        file_types = defaultdict(int)
        total_files = 0
        
        # RECURSIVELY scan all subdirectories
        for root, dirs, files in os.walk(everything):
            for file in files:
                file_path = Path(root) / file
                try:
                    mod_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    month_key = mod_time.strftime("%B")
                    monthly_analysis[month_key] += 1
                    
                    ext = file_path.suffix.lower()
                    if ext in self.organizer.VIDEO_EXTS:
                        file_types['Videos'] += 1
                    elif ext in self.organizer.IMAGE_EXTS:
                        file_types['Images'] += 1
                    elif ext in self.organizer.AUDIO_EXTS:
                        file_types['Audio'] += 1
                    
                    total_files += 1
                except:
                    pass
        
        # Update chart immediately
        if monthly_analysis:
            chart_data = {}
            year = datetime.now().strftime("%Y")
            for month, count in monthly_analysis.items():
                chart_data[month] = {year: count}
            self.chart.setData(chart_data, {})
        
        # Show total but DON'T show segments yet (wait until after organizing)
        self.circular_progress.setValue(total_files, total_files, str(total_files))
        self.status_label.setText(f"Found {total_files} files across {len(monthly_analysis)} months")
        
        # DON'T update category bars yet - wait for actual organization
    
    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_folder = folder
            self.output_input.setText(folder)
    
    def start_organizing(self):
        if self.is_organizing:
            return
        
        if not self.everything_folder:
            QMessageBox.critical(self, "Error", "Select Everything folder")
            return
        
        if not self.output_folder:
            QMessageBox.critical(self, "Error", "Select Output folder")
            return
        
        everything = Path(self.everything_folder)
        output = Path(self.output_folder)
        
        if everything == output:
            QMessageBox.critical(self, "Error", "Folders must be different")
            return
        
        # ANALYZE FILES FIRST to build chart data
        self.progress_title.setText("Analyzing files...")
        self.status_label.setText("Scanning file dates...")
        QApplication.processEvents()
        
        # Scan all files and group by creation month
        monthly_analysis = defaultdict(int)
        total_files = 0
        
        for root, dirs, files in os.walk(everything):
            for file in files:
                file_path = Path(root) / file
                try:
                    # Get file modification time
                    mod_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    month_key = mod_time.strftime("%B")  # Full month name
                    year = mod_time.strftime("%Y")
                    monthly_analysis[month_key] += 1
                    total_files += 1
                except:
                    pass
        
        # Update chart with pre-organization data
        if monthly_analysis:
            # Convert to format chart expects
            chart_data = {}
            for month, count in monthly_analysis.items():
                chart_data[month] = {datetime.now().strftime("%Y"): count}
            
            self.chart.setData(chart_data, {})
            self.circular_progress.setValue(total_files, total_files, str(total_files))
        
        # Reset for actual organization
        self.monthly_data.clear()
        self.category_counts.clear()
        self.folder_paths.clear()
        for count_label, progress_bar, color in self.category_bars.values():
            count_label.setText("0")
            progress_bar.setValue(0)
        
        self.is_organizing = True
        self.organize_btn.setEnabled(False)
        self.organize_btn.setText("⏸")
        self.progress_bar.setValue(0)
        
        # CRITICAL: Force FFmpeg recheck before organizing!
        logger.info("=== FORCING FFMPEG RECHECK BEFORE ORGANIZING ===")
        self.organizer.recheck_ffmpeg()
        logger.info(f"FFmpeg toggle checked: {self.ffmpeg_toggle.isChecked()}")
        logger.info(f"FFmpeg available: {self.organizer.ffmpeg_available}")
        logger.info("=== END FFMPEG CHECK ===")
        
        ffmpeg_status = "✅ Video analysis ON" if self.ffmpeg_toggle.isChecked() else "⚠️ Video analysis OFF"
        self.progress_title.setText(f"Starting... {ffmpeg_status}")
        
        logger.info(f"Starting organization with FFmpeg: {self.ffmpeg_toggle.isChecked()}")
        logger.info(f"FFmpeg available: {self.organizer.ffmpeg_available}")
        
        self.thread = OrganizeThread(
            self.organizer, everything, output,
            self.ffmpeg_toggle.isChecked(),
            self.clean_toggle.isChecked(),
            self.date_toggle.isChecked()
        )
        
        self.thread.progress.connect(self._update_progress)
        self.thread.finished.connect(self._show_complete)
        self.thread.error.connect(self._show_error)
        self.thread.start()
    
    def _update_progress(self, progress, filename, category):
        pct = int(progress * 100)
        self.progress_bar.setValue(pct)
        self.progress_title.setText(f"Organizing... {pct}%")
        self.status_label.setText(f"📄 {filename}")
        
        total = int(self.organizer.stats.total * progress)
        
        if self.date_toggle.isChecked() and '/' in category:
            parts = category.split('/')
            if len(parts) >= 3:
                base_category = parts[0]
                year = parts[1]
                month = parts[2]
                
                self.monthly_data[month][year] += 1
                output = Path(self.output_folder)
                folder_path = output / base_category / year / month
                self.folder_paths[(month, year)] = str(folder_path)
                self.chart.setData(dict(self.monthly_data), self.folder_paths)
        
        base_cat = category.split('/')[0] if '/' in category else category
        self.category_counts[base_cat] += 1
        
        # Update category bars
        total_files = self.organizer.stats.total
        segments = {}
        
        for key, (count_label, progress_bar, color) in self.category_bars.items():
            if key in self.category_counts:
                count = self.category_counts[key]
                count_label.setText(str(count))
                # Update progress bar percentage
                if total_files > 0:
                    percentage = int((count / total_files) * 100)
                    progress_bar.setValue(percentage)
                
                # Add to segments for circular progress
                segments[key] = (count, color)
        
        # Update circular progress with color segments
        if segments:
            self.circular_progress.setSegments(segments)
        else:
            self.circular_progress.setValue(total, total_files, str(total))
    
    def _show_complete(self, stats):
        self.progress_bar.setValue(100)
        self.progress_title.setText("✅ Complete!")
        
        # If tracking the output folder, update it
        if hasattr(self, 'track_folder_input') and self.track_folder_input.text() == self.output_folder:
            self.status_label.setText(f"Updating tracked folder...")
            self._scan_track_folder(Path(self.output_folder))
        
        self.status_label.setText(f"Organized {stats.organized} files!")
        
        self.is_organizing = False
        self.organize_btn.setEnabled(True)
        self.organize_btn.setText("▶")
        
        if stats.needs_review > 0:
            reply = QMessageBox.question(
                self, "Review Files",
                f"{stats.needs_review} files need review. Open now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.open_review()
    
    def _show_error(self, msg):
        self.progress_title.setText("❌ Error")
        self.status_label.setText(f"Failed: {msg}")
        
        self.is_organizing = False
        self.organize_btn.setEnabled(True)
        self.organize_btn.setText("▶")
        
        QMessageBox.critical(self, "Error", msg)
    
    def _open_month_folder(self, month, year):
        """Open folder in file explorer."""
        for (m, y), path in self.folder_paths.items():
            if m == month and y == year:
                try:
                    if os.name == 'nt':
                        os.startfile(path)
                    elif sys.platform == 'darwin':
                        subprocess.run(['open', path])
                    else:
                        subprocess.run(['xdg-open', path])
                except Exception as e:
                    logger.error(f"Failed to open folder: {e}")
                break
    
    def open_review(self):
        output = validate_folder_path(self.output_folder)
        if not output:
            QMessageBox.critical(self, "Error", "Set output folder first")
            return
        
        uncategorized = output / 'Uncategorized'
        if not uncategorized.exists() or not any(uncategorized.iterdir()):
            QMessageBox.information(self, "No Files", "No files need review!")
            return
        
        try:
            from review_window import ReviewWindow
        except ImportError:
            from .review_window import ReviewWindow
        self.review_window = ReviewWindow(self, uncategorized, output)
        self.review_window.show()


def run_app():
    """Run the PyQt6 application."""
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 13))
    window = MainApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
