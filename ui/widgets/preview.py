from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QLabel, QHBoxLayout
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal

from ui.style import FONT_MONO, SIZE_MONO, ICON_FONT_PT

class CommandPreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(0, 0, 0, 0)

        label_layout = QHBoxLayout()
        label_layout.setContentsMargins(0, 0, 0, 0)
        # \uE756 = CommandPrompt / Terminal (Segoe MDL2 Assets)
        self.icon_label = QLabel("\uE756")
        self.icon_label.setFont(QFont("Segoe MDL2 Assets", ICON_FONT_PT))
        self.icon_label.setStyleSheet("color: palette(highlight);")
        self.text_label = QLabel(self.tr("Pré-visualização do comando:"))
        label_layout.addWidget(self.icon_label)
        label_layout.addWidget(self.text_label)
        label_layout.addStretch()
        
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(QFont(FONT_MONO, SIZE_MONO))
        self.preview.setMaximumHeight(80)
        self.preview.setMinimumHeight(60)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        
        layout.addLayout(label_layout)
        layout.addWidget(self.preview)
        self.setLayout(layout)

    def set_command(self, command: str):
        self.preview.setPlainText(command)

    def get_command(self):
        return self.preview.toPlainText() 