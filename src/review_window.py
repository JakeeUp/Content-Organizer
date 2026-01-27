"""
Review window for PyQt6 - manually categorize uncategorized files.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from pathlib import Path
import shutil
import logging

logger = logging.getLogger(__name__)


class ReviewWindow(QDialog):
    """PyQt6 dialog for reviewing uncategorized files."""
    
    def __init__(self, parent, uncategorized_path, output_path):
        super().__init__(parent)
        
        self.uncategorized_path = uncategorized_path
        self.output_path = output_path
        
        self.files = list(uncategorized_path.glob("*.*"))
        self.current_index = 0
        
        if not self.files:
            QMessageBox.information(self, "No Files", "No files to review!")
            self.reject()
            return
        
        self.setWindowTitle("Review Uncategorized Files")
        self.setModal(True)
        self.resize(700, 500)
        
        # Styling
        self.setStyleSheet("""
            QDialog {
                background-color: #0B0E1A;
            }
            QLabel {
                color: white;
            }
            QPushButton {
                background-color: #4A90E2;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 15px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5A9FF2;
            }
        """)
        
        self._setup_ui()
        self._load_current_file()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(40, 40, 40, 40)
        
        # Title
        title = QLabel("Review Uncategorized Files")
        title.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        layout.addSpacing(20)
        
        # File info card
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #1A1F35;
                border-radius: 15px;
                padding: 20px;
            }
        """)
        card_layout = QVBoxLayout(card)
        
        self.file_label = QLabel()
        self.file_label.setFont(QFont("Segoe UI", 16))
        self.file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_label.setWordWrap(True)
        card_layout.addWidget(self.file_label)
        
        self.count_label = QLabel()
        self.count_label.setFont(QFont("Segoe UI", 12))
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count_label.setStyleSheet("color: #8B92B0;")
        card_layout.addWidget(self.count_label)
        
        layout.addWidget(card)
        
        layout.addSpacing(20)
        
        # Category buttons
        categories = [
            ("🎬 Finalized Video", "FinalizedVideos"),
            ("🎵 Sound Effect", "SoundEffects"),
            ("🎶 Music", "Music"),
            ("📁 Other", "Other")
        ]
        
        for text, category in categories:
            btn = QPushButton(text)
            btn.setMinimumHeight(60)
            btn.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
            btn.clicked.connect(lambda checked, c=category: self._categorize(c))
            layout.addWidget(btn)
        
        layout.addSpacing(20)
        
        # Navigation
        nav_layout = QHBoxLayout()
        
        skip_btn = QPushButton("⏭️ Skip")
        skip_btn.setMinimumHeight(50)
        skip_btn.setStyleSheet("background-color: #FF9500;")
        skip_btn.clicked.connect(self._skip)
        nav_layout.addWidget(skip_btn)
        
        done_btn = QPushButton("✅ Done")
        done_btn.setMinimumHeight(50)
        done_btn.setStyleSheet("background-color: #34C759;")
        done_btn.clicked.connect(self._finish)
        nav_layout.addWidget(done_btn)
        
        layout.addLayout(nav_layout)
    
    def _load_current_file(self):
        if self.current_index >= len(self.files):
            self._finish()
            return
        
        current_file = self.files[self.current_index]
        self.file_label.setText(f"📄 {current_file.name}")
        self.count_label.setText(f"File {self.current_index + 1} of {len(self.files)}")
    
    def _categorize(self, category):
        if self.current_index >= len(self.files):
            return
        
        current_file = self.files[self.current_index]
        destination_folder = self.output_path / category
        destination_folder.mkdir(parents=True, exist_ok=True)
        
        destination_path = destination_folder / current_file.name
        
        # Handle conflicts
        counter = 1
        while destination_path.exists():
            stem = current_file.stem
            destination_path = destination_folder / f"{stem}_{counter}{current_file.suffix}"
            counter += 1
        
        try:
            shutil.move(str(current_file), destination_path)
            logger.info(f"Categorized {current_file.name} -> {category}")
            self.current_index += 1
            self._load_current_file()
        except Exception as e:
            logger.error(f"Failed to move file: {e}")
            QMessageBox.critical(self, "Error", f"Failed to move file: {str(e)}")
    
    def _skip(self):
        self.current_index += 1
        self._load_current_file()
    
    def _finish(self):
        remaining = len(self.files) - self.current_index
        if remaining > 0:
            reply = QMessageBox.question(
                self, "Confirm",
                f"{remaining} files remaining. Finish anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        self.accept()
