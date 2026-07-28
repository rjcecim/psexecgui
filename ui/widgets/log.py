from PyQt6.QtWidgets import QTextEdit, QSizePolicy
from PyQt6.QtGui import QFont, QTextCursor
import re

from ui.style import FONT_MONO, SIZE_MONO
from ui.widgets.card import CardWidget


class LogOutputWidget(CardWidget):
    """Card expansível com o log de execução."""

    def __init__(self, parent=None):
        super().__init__("\uE9F9", "Log de Execução", parent)
        self._title_label.setText(self.tr("Log de Execução"))
        self.set_layout_stretch(1)
        self.set_expanding(True)
        self.set_collapsible(True, collapsed=False)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont(FONT_MONO, SIZE_MONO))
        self.text_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.text_edit.setMinimumHeight(56)
        self.content_layout.addWidget(self.text_edit, 1)

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
