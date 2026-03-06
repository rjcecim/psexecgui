from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLabel, QHBoxLayout
from PyQt6.QtGui import QFont, QTextCursor
import re

from ui.style import FONT_MONO, SIZE_MONO, ICON_FONT_PT

class LogOutputWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(0, 0, 0, 0)

        label_layout = QHBoxLayout()
        label_layout.setContentsMargins(0, 0, 0, 0)
        # \uE9F9 = BulletedList / Log (Segoe MDL2 Assets)
        self.icon_label = QLabel("\uE9F9")
        self.icon_label.setFont(QFont("Segoe MDL2 Assets", ICON_FONT_PT))
        self.icon_label.setStyleSheet("color: palette(highlight);")
        self.text_label = QLabel(self.tr("Log de Execução:"))
        label_layout.addWidget(self.icon_label)
        label_layout.addWidget(self.text_label)
        label_layout.addStretch()

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont(FONT_MONO, SIZE_MONO))
        self.text_edit.setMaximumHeight(120)  # Altura máxima reduzida
        self.text_edit.setMinimumHeight(80)   # Altura mínima

        layout.addLayout(label_layout)
        layout.addWidget(self.text_edit)
        self.setLayout(layout)

    def append_log(self, text: str):
        # Filtra linhas de animação (ex: '-', '\\', '|', '/') que aparecem sozinhas ou com espaços
        animation_lines = {'-', '\\', '|', '/'}
        if text.strip() in animation_lines:
            return
        # Detecta barra de progresso (ex: linhas com blocos e tamanho)
        progress_bar_pattern = re.compile(r'^[\s█▒]+[0-9.,]+ (KB|MB|GB) / [0-9.,]+ (KB|MB|GB)')
        if progress_bar_pattern.match(text):
            # Atualiza a última linha se for barra de progresso
            cursor = self.text_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deletePreviousChar()  # Remove o \n anterior
            cursor.insertText(text)
            self.text_edit.setTextCursor(cursor)
            self.text_edit.ensureCursorVisible()
            return
        self.text_edit.append(text)
        self.text_edit.moveCursor(QTextCursor.MoveOperation.End)

    def clear_log(self):
        self.text_edit.clear()