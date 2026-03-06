from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy,
    QGridLayout,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPalette

from ui.style import FONT_UI, SIZE_UI, CARD_GRID_VERTICAL_SPACING


def make_field_label(text: str) -> QLabel:
    """Label padronizado para campos dentro de cards (mesma largura e estilo das abas)."""
    lbl = QLabel(text)
    lbl.setObjectName("fieldLabel")
    lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    lbl.setMinimumWidth(120)
    lbl.setStyleSheet("QLabel#fieldLabel { color: palette(windowText); opacity: 0.75; }")
    return lbl


def add_row(grid: QGridLayout, row: int, label_text: str, widget: QWidget) -> None:
    """Adiciona uma linha label + widget no grid do card."""
    lbl = make_field_label(label_text)
    grid.addWidget(lbl, row, 0, Qt.AlignmentFlag.AlignVCenter)
    grid.addWidget(widget, row, 1, Qt.AlignmentFlag.AlignVCenter)


def add_row_full_width(grid: QGridLayout, row: int, widget: QWidget) -> None:
    """Adiciona um widget ocupando toda a largura da linha (ex.: checkbox sem label)."""
    grid.addWidget(widget, row, 0, 1, 2, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)


def grid_in_card(card: "CardWidget") -> QGridLayout:
    """Cria um QGridLayout padronizado dentro do card e retorna para adicionar linhas."""
    grid = QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(CARD_GRID_VERTICAL_SPACING)
    grid.setColumnStretch(1, 1)
    card.content_layout.addLayout(grid)
    return grid


class CardWidget(QWidget):
    """
    Widget de card com cabeçalho (ícone Unicode + título em negrito),
    linha divisória e área de conteúdo em grid.
    """

    def __init__(self, icon_char: str, title: str, parent=None):
        super().__init__(parent)
        self._setup_style()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Container interno com fundo e bordas arredondadas via stylesheet
        self._container = QWidget()
        self._container.setObjectName("cardContainer")
        container_layout = QVBoxLayout(self._container)
        container_layout.setContentsMargins(8, 4, 8, 5)
        container_layout.setSpacing(0)

        # Cabeçalho (altura fixa para todos os cards ficarem iguais)
        header_widget = QWidget()
        header_widget.setFixedHeight(22)
        header = QHBoxLayout(header_widget)
        header.setSpacing(6)
        header.setContentsMargins(0, 0, 0, 0)

        self._icon_label = QLabel(icon_char)
        self._icon_label.setObjectName("cardIcon")
        icon_font = QFont()
        icon_font.setFamily("Segoe MDL2 Assets")
        icon_font.setPointSize(13)
        self._icon_label.setFont(icon_font)
        self._icon_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("cardTitle")
        title_font = QFont(FONT_UI, SIZE_UI)
        title_font.setBold(True)
        self._title_label.setFont(title_font)
        self._title_label.setWordWrap(False)
        self._title_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        header.addWidget(self._icon_label)
        header.addWidget(self._title_label)
        header.addStretch()

        container_layout.addWidget(header_widget)

        # Linha divisória
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("cardDivider")
        divider.setFixedHeight(1)
        container_layout.addWidget(divider)
        container_layout.addSpacing(2)

        # Área de conteúdo — o chamador adiciona widgets aqui
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(CARD_GRID_VERTICAL_SPACING)
        container_layout.addLayout(self.content_layout)

        outer.addWidget(self._container)

    def _setup_style(self):
        self.setStyleSheet("""
            QWidget#cardContainer {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 6px;
            }
            QLabel#cardIcon {
                color: palette(highlight);
            }
            QLabel#cardTitle {
                color: palette(windowText);
            }
            QFrame#cardDivider {
                color: palette(mid);
                background-color: palette(mid);
                border: none;
            }
        """)
