"""Identidade visual e resolução de assets (dev e PyInstaller)."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap

APP_NAME = "PSExecGUI"
APP_DISPLAY_NAME = "Instalador Remoto via PsExec"
APP_VERSION = "1.5.0"
ORG_NAME = "PSExecGUI"

# Marca: navy / azure / cyan (alinhado aos assets)
BRAND_NAVY = "#0F2744"
BRAND_AZURE = "#0063C4"
BRAND_CYAN = "#38BDF8"


def assets_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


def asset_path(name: str) -> Path:
    return assets_dir() / name


def app_icon() -> QIcon:
    ico = asset_path("icon.ico")
    if ico.is_file():
        return QIcon(str(ico))
    png = asset_path("app_icon.png")
    if png.is_file():
        return QIcon(str(png))
    return QIcon()


def app_mark_pixmap(size: int = 28) -> QPixmap:
    path = asset_path("app_mark.png")
    if not path.is_file():
        return QPixmap()
    pm = QPixmap(str(path))
    if pm.isNull():
        return pm
    return pm.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
