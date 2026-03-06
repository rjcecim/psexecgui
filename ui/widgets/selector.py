from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QLabel, QPushButton, QFileDialog, QFileIconProvider, QMenu, QToolButton, QMessageBox)
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtCore import pyqtSignal, Qt, QFileInfo
import os
import subprocess

from ui.style import ICON_FONT_PT

_MDL2_FONT = QFont("Segoe MDL2 Assets", ICON_FONT_PT)
_MDL2_BTN_STYLE = f"""
    QToolButton, QPushButton {{
        border: 1px solid palette(mid);
        border-radius: 4px;
        background: palette(button);
        font-family: "Segoe MDL2 Assets";
        font-size: {ICON_FONT_PT}pt;
        color: palette(highlight);
    }}
    QToolButton:hover, QPushButton:hover {{ background: palette(light); }}
    QToolButton:pressed, QPushButton:pressed {{ background: palette(dark); }}
    QToolButton:disabled, QPushButton:disabled {{ color: palette(mid); }}
"""

class FileSelectorWidget(QWidget):
    # Sinal emitido quando um arquivo ou pasta é selecionado
    fileSelected = pyqtSignal(dict)  # Emite dict: {'mode': 'file'|'folder', 'file': ..., 'folder': ...}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_file = None
        self.selected_folder = None
        self.selection_mode = None  # 'file' ou 'folder'
        self.layout_widget = QHBoxLayout(self)
        # Compacto como no layout original
        self.layout_widget.setContentsMargins(0, 0, 0, 0)
        self.layout_widget.setSpacing(5)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(32, 32)
        self.name_label = QLabel(self.tr("Nenhum arquivo ou pasta selecionado"))

        # \uED25 = OpenFile (Segoe MDL2 Assets)
        self.file_button = QToolButton()
        self.file_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.file_button.setText("\uED25")
        self.file_button.setFont(_MDL2_FONT)
        self.file_button.setStyleSheet(_MDL2_BTN_STYLE)
        self.file_button.setToolTip(self.tr("Selecionar arquivo"))
        self.file_button.setFixedSize(32, 32)
        self.file_button.clicked.connect(self.open_file_dialog)

        # \uED43 = FolderOpen (Segoe MDL2 Assets)
        self.folder_button = QToolButton()
        self.folder_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.folder_button.setText("\uED43")
        self.folder_button.setFont(_MDL2_FONT)
        self.folder_button.setStyleSheet(_MDL2_BTN_STYLE)
        self.folder_button.setToolTip(self.tr("Selecionar pasta"))
        self.folder_button.setFixedSize(32, 32)
        self.folder_button.clicked.connect(self.open_folder_dialog)

        # \uE946 = Info / Help (Segoe MDL2 Assets)
        self.help_button = QPushButton("\uE946")
        self.help_button.setFont(_MDL2_FONT)
        self.help_button.setStyleSheet(_MDL2_BTN_STYLE)
        self.help_button.setToolTip(self.tr("Executar arquivo com /? para ver argumentos disponíveis"))
        self.help_button.setFixedSize(32, 32)
        self.help_button.setEnabled(False)
        self.help_button.clicked.connect(self.show_help)

        self.layout_widget.addWidget(self.icon_label)
        self.layout_widget.addWidget(self.name_label)
        self.layout_widget.addWidget(self.file_button)
        self.layout_widget.addWidget(self.folder_button)
        self.layout_widget.addWidget(self.help_button)
        self.setLayout(self.layout_widget)

    def _create_open_menu(self):
        # Não é mais necessário, mas mantido para compatibilidade se chamado em outro lugar
        return QMenu(self)

    def open_file_dialog(self):
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        file_dialog.setNameFilter(self.tr("Arquivos executáveis (*.exe *.msi *.bat *.ps1)"))
        if file_dialog.exec():
            file_path = file_dialog.selectedFiles()[0]
            self.set_file(file_path)
            self.selection_mode = 'file'
            self.selected_folder = None
            self.fileSelected.emit({'mode': 'file', 'file': file_path, 'folder': None})

    def open_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("Selecionar pasta"))
        if folder:
            self.selected_folder = folder
            self.selection_mode = 'folder'
            # Agora abrir diálogo para escolher arquivo dentro da pasta (inclusive subpastas)
            file_path = self._choose_file_in_folder(folder)
            if file_path:
                self.set_file(file_path, folder)
                self.fileSelected.emit({'mode': 'folder', 'file': file_path, 'folder': folder})

    def _choose_file_in_folder(self, folder):
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        file_dialog.setDirectory(folder)
        file_dialog.setNameFilter(self.tr("Arquivos executáveis (*.exe *.msi *.bat *.ps1)"))
        file_dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        # Habilita navegação em subpastas
        if file_dialog.exec():
            return file_dialog.selectedFiles()[0]
        return None

    def set_file(self, file_path, folder=None):
        self.selected_file = file_path
        self.selected_folder = folder
        if folder:
            display = f"{os.path.basename(folder)}: {os.path.relpath(file_path, folder)}"
        else:
            display = os.path.basename(file_path)
        self.name_label.setText(display)
        icon_provider = QFileIconProvider()
        icon = icon_provider.icon(QFileIconProvider.IconType.File)
        if os.path.exists(file_path):
            file_info = QFileInfo(file_path)
            icon = icon_provider.icon(file_info)
        pixmap = icon.pixmap(32, 32)
        self.icon_label.setPixmap(pixmap)

        # Habilitar botão de ajuda apenas se for arquivo .exe
        is_exe = file_path.lower().endswith('.exe')
        self.help_button.setEnabled(is_exe)

    def show_help(self):
        """Executa o arquivo com /? para mostrar argumentos disponíveis"""
        if not self.selected_file or not self.selected_file.lower().endswith('.exe'):
            return

        try:
            # Executar o arquivo com /? em um terminal externo
            exe_path = self.selected_file.replace('"', '')
            subprocess.Popen(f'start cmd /k "\"{exe_path}\" /?"', shell=True)
        except Exception as e:
            print(f"Erro ao executar {self.selected_file} /?: {e}") 

    def ask_file_or_folder(self):
        # Não é mais necessário, pois agora há dois botões
        pass 