from __future__ import annotations

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

# Tipografia: uma fonte de UI, uma monoespaçada para comandos/log, e tamanho dos ícones
FONT_UI = "Segoe UI"
FONT_UI_FALLBACK = "Segoe UI, sans-serif"
FONT_MONO = "Consolas"
SIZE_UI = 10
SIZE_UI_SMALL = 9
SIZE_MONO = 9
ICON_FONT_PT = 13

# Espaçamento vertical entre linhas de campos dentro dos cards (referência: card Conexão)
CARD_GRID_VERTICAL_SPACING = 2


def apply_ui_defaults(app: QApplication) -> None:
    """
    Padroniza fonte da interface e densidade dos widgets.
    - UI: Segoe UI para labels, botões, inputs (legível e nativo no Windows).
    - Ícones: Segoe MDL2 Assets continuam nos componentes que já usam.
    - Log/Preview: Consolas é aplicado nos widgets de texto (monoespaçado).
    """
    font = QFont(FONT_UI, SIZE_UI)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)

    base = app.styleSheet() or ""
    # Não definir font-family em QLabel/QPushButton/QToolButton no stylesheet,
    # para não sobrescrever os ícones (Segoe MDL2 Assets) definidos com setFont().
    # O app.setFont() acima já define Segoe UI como padrão para o resto.
    app.setStyleSheet(
        base
        + """
        QLineEdit {
            font-family: "Segoe UI";
            min-height: 22px;
            border: 1px solid palette(mid);
            border-radius: 4px;
            padding: 4px 8px;
        }
        QLineEdit:focus {
            border-color: palette(highlight);
        }
        QComboBox, QSpinBox, QCheckBox {
            font-family: "Segoe UI";
            min-height: 22px;
        }
        QPlainTextEdit, QTextEdit {
            padding: 2px;
        }
        QPushButton, QToolButton {
            min-height: 22px;
        }
        QTabBar::tab {
            padding: 4px 8px;
        }
        """
    )

