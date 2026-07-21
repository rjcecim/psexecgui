from __future__ import annotations

import os
import subprocess
from typing import Optional

from PyQt6 import sip
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QFileDialog,
    QSizePolicy,
    QPushButton,
    QCheckBox,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QGridLayout,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)

from ui.style import ICON_FONT_PT
from ui.widgets.card import CardWidget, grid_in_card, add_row, add_row_full_width
from ui.widgets.spinner import DotsSpinner
from utils.psinfo import (
    build_psinfo_target,
    parse_psinfo_output,
    format_key_values,
    parse_disks_table,
    list_remote_installed_apps,
)


def _icon_button(icon_char: str, tooltip: str = "", size: int = 32) -> QPushButton:
    btn = QPushButton(icon_char)
    font = QFont("Segoe MDL2 Assets", ICON_FONT_PT)
    btn.setFont(font)
    btn.setFixedSize(size, size)
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(
        """
        QPushButton {
            border: 1px solid palette(mid);
            border-radius: 4px;
            background: palette(button);
            color: palette(highlight);
            padding: 0;
        }
        QPushButton:hover { background: palette(light); border-color: palette(highlight); }
        QPushButton:pressed { background: palette(dark); }
        QPushButton:disabled { color: palette(mid); }
        """
    )
    return btn


class _PsInfoWorker(QThread):
    finished_ok = pyqtSignal(str, object)  # stdout, apps override (list[str] | None)
    finished_err = pyqtSignal(str)  # erro amigável

    def __init__(self, exe_path: str, host: str, include_apps: bool, include_disks: bool, accepteula: bool, nobanner: bool):
        super().__init__()
        self.exe_path = exe_path
        self.host = host
        self.include_apps = include_apps
        self.include_disks = include_disks
        self.accepteula = accepteula
        self.nobanner = nobanner

    def run(self) -> None:
        try:
            target = build_psinfo_target(self.host)
            if not target:
                self.finished_err.emit("Host remoto não informado.")
                return

            exe = (self.exe_path or "").strip()
            if exe:
                exe = os.path.normpath(exe.replace('"', "").replace("'", ""))
            else:
                default = r"C:\PSTools\PsInfo64.exe"
                exe = default if os.path.isfile(default) else "PsInfo64.exe"

            args = [exe, target]
            if self.include_apps:
                args.append("-s")
            if self.include_disks:
                args.append("-d")
            if self.accepteula:
                args.append("-accepteula")
            if self.nobanner:
                args.append("-nobanner")

            creationflags = 0
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                creationflags = subprocess.CREATE_NO_WINDOW

            proc = subprocess.run(
                args,
                capture_output=True,
                text=False,
                creationflags=creationflags,
            )

            stdout_b = proc.stdout or b""
            stderr_b = proc.stderr or b""

            def decode_best_effort(b: bytes) -> str:
                if not b:
                    return ""
                # 1) UTF-8 (alguns ambientes / tools usam)
                try:
                    return b.decode("utf-8-sig")
                except Exception:
                    pass
                # 2) Codepage do Windows ("mbcs" / ANSI) — resolve acentuação PT-BR na maioria dos casos
                try:
                    return b.decode("mbcs", errors="replace")
                except Exception:
                    pass
                # 3) Fallback CP1252
                return b.decode("cp1252", errors="replace")

            out = decode_best_effort(stdout_b).strip()
            err = decode_best_effort(stderr_b).strip()

            if proc.returncode != 0:
                msg = (
                    err
                    or (out if ("error" in out.lower()) else "")
                    or f"Falha ao executar PsInfo (exit code {proc.returncode})."
                )
                self.finished_err.emit(msg)
                if not out:
                    return

            # PsInfo64 -s costuma omitir apps 32-bit; complementa via Remote Registry (64+32).
            apps_override = None
            if self.include_apps:
                try:
                    remote_apps = list_remote_installed_apps(self.host)
                    if remote_apps:
                        apps_override = remote_apps
                except Exception:
                    apps_override = None

            # Mesmo com returncode != 0, o PsInfo às vezes escreve dados úteis em stdout.
            self.finished_ok.emit(out if out else err, apps_override)
        except FileNotFoundError:
            self.finished_err.emit("Não foi possível encontrar o PsInfo64.exe. Ajuste o caminho na aba PsInfo.")
        except Exception as exc:
            self.finished_err.emit(f"Erro ao executar PsInfo: {exc}")


class PsInfoTab(QWidget):
    def __init__(self, parent=None, log_output=None, host_source: Optional[QLineEdit] = None):
        super().__init__(parent)
        self.log_output = log_output
        self._worker: Optional[_PsInfoWorker] = None
        self._host_source = host_source
        self._loading_card: Optional[CardWidget] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(3)

        # Área de resultados (cards) com rolagem
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(self.scroll.frameShape().NoFrame)
        self.results_root = QWidget()
        self.results_layout = QVBoxLayout(self.results_root)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(3)
        self.results_layout.addStretch()
        self.scroll.setWidget(self.results_root)
        root.addWidget(self.scroll)

        if host_source is not None:
            host_source.textChanged.connect(self._on_host_changed)

        self.destroyed.connect(self._abort_psinfo_worker)

        # Execução é disparada pelo MainWindow ao abrir/clicar no botão.

    def _ui_alive(self) -> bool:
        return not sip.isdeleted(self)

    def _abort_psinfo_worker(self, _destroyed: object = None) -> None:
        w = self._worker
        if w is None:
            return
        self._worker = None
        try:
            w.finished_ok.disconnect(self._on_psinfo_ok)
        except TypeError:
            pass
        try:
            w.finished_err.disconnect(self._on_psinfo_err)
        except TypeError:
            pass
        try:
            w.finished.disconnect(self._on_worker_thread_finished)
        except TypeError:
            pass
        if w.isRunning():
            w.finished.connect(w.deleteLater)
        else:
            w.deleteLater()

    def _get_host(self) -> str:
        if self._host_source is None:
            return ""
        return (self._host_source.text() or "").strip()

    def _on_host_changed(self, _text: str) -> None:
        # Não auto-executar a cada tecla; só mantém o host atualizado para a próxima execução.
        return

    def clear_results(self) -> None:
        # Remove tudo menos o stretch final
        while self.results_layout.count() > 1:
            item = self.results_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._loading_card = None

    def _set_loading(self, loading: bool, host: str = "") -> None:
        if not self._ui_alive():
            return
        if loading:
            self.clear_results()
            card = CardWidget("\uE895", self.tr("Coletando informações"))
            card.set_collapsible(False)

            wrap = QWidget()
            lay = QVBoxLayout(wrap)
            lay.setContentsMargins(0, 6, 0, 2)
            lay.setSpacing(8)

            msg = self.tr("Aguarde...") if not host else self.tr(f"Aguarde... ({host})")
            lbl = QLabel(msg)
            lbl.setStyleSheet("color: palette(windowText); opacity: 0.85;")

            spinner_row = QHBoxLayout()
            spinner_row.setContentsMargins(0, 0, 0, 0)
            spinner_row.addStretch()
            spinner = DotsSpinner()
            spinner_row.addWidget(spinner)
            spinner_row.addStretch()
            spinner_wrap = QWidget()
            spinner_wrap.setLayout(spinner_row)

            lay.addWidget(lbl)
            lay.addWidget(spinner_wrap)
            card.content_layout.addWidget(wrap)

            self._loading_card = card
            self.results_layout.insertWidget(self.results_layout.count() - 1, card)
        else:
            if self._loading_card is not None:
                card = self._loading_card
                self._loading_card = None
                if not sip.isdeleted(card):
                    card.deleteLater()

    def _add_text_card(self, icon: str, title: str, text: str) -> None:
        card = CardWidget(icon, title)
        card.set_collapsible(True, collapsed=False)
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(text or "")
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        editor.setStyleSheet("QPlainTextEdit { border: 1px solid palette(mid); border-radius: 4px; }")
        card.content_layout.addWidget(editor)
        self.results_layout.insertWidget(self.results_layout.count() - 1, card)

    def _add_system_card(self, icon: str, title: str, kv: list[tuple[str, str]]) -> None:
        card = CardWidget(icon, title)
        card.set_collapsible(True, collapsed=False)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)

        for row, (k, v) in enumerate(kv):
            k_lbl = QLabel(k)
            k_lbl.setStyleSheet("color: palette(windowText); opacity: 0.75;")
            k_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            k_lbl.setMinimumWidth(160)

            v_lbl = QLabel(v)
            v_lbl.setWordWrap(True)
            v_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            grid.addWidget(k_lbl, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(v_lbl, row, 1, Qt.AlignmentFlag.AlignTop)

        wrap = QWidget()
        wrap.setLayout(grid)
        card.content_layout.addWidget(wrap)
        self.results_layout.insertWidget(self.results_layout.count() - 1, card)

    def _add_apps_card(self, icon: str, title: str, apps: list[str]) -> None:
        card = CardWidget(icon, title)
        card.set_collapsible(True, collapsed=False)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)

        search = QLineEdit()
        search.setPlaceholderText(self.tr("Buscar aplicativo..."))
        count_lbl = QLabel("")
        count_lbl.setStyleSheet("color: palette(windowText); opacity: 0.75;")

        top.addWidget(search)
        top.addWidget(count_lbl)

        lst = QListWidget()
        lst.setStyleSheet("QListWidget { border: 1px solid palette(mid); border-radius: 4px; }")

        normalized = [a.strip() for a in apps if a and a.strip()]
        for a in normalized:
            QListWidgetItem(a, lst)

        def update_filter():
            q = (search.text() or "").strip().lower()
            visible = 0
            for i in range(lst.count()):
                item = lst.item(i)
                ok = (q in item.text().lower()) if q else True
                item.setHidden(not ok)
                if ok:
                    visible += 1
            count_lbl.setText(self.tr(f"{visible}/{len(normalized)}"))

        search.textChanged.connect(update_filter)
        update_filter()

        top_wrap = QWidget()
        top_wrap.setLayout(top)
        card.content_layout.addWidget(top_wrap)
        card.content_layout.addWidget(lst)

        self.results_layout.insertWidget(self.results_layout.count() - 1, card)

    def _add_disks_card(self, icon: str, title: str, disks_raw: list[str]) -> None:
        rows = parse_disks_table(disks_raw)
        if not rows:
            self._add_text_card(icon, title, "\n".join(disks_raw) if disks_raw else "")
            return

        card = CardWidget(icon, title)
        card.set_collapsible(True, collapsed=False)
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(
            [
                self.tr("Volume"),
                self.tr("Tipo"),
                self.tr("Formato"),
                self.tr("Rótulo"),
                self.tr("Tamanho"),
                self.tr("Livre"),
                self.tr("% Livre"),
            ]
        )
        table.setRowCount(len(rows))
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        table.setStyleSheet("QTableWidget { border: 1px solid palette(mid); border-radius: 4px; }")

        for r, row in enumerate(rows):
            values = [row.volume, row.type, row.format, row.label, row.size, row.free, row.free_pct]
            for c, val in enumerate(values):
                it = QTableWidgetItem(val)
                table.setItem(r, c, it)

        card.content_layout.addWidget(table)
        self.results_layout.insertWidget(self.results_layout.count() - 1, card)

    def run_psinfo(self) -> None:
        host = self._get_host()
        if not host:
            if self.log_output:
                self.log_output.append_log(self.tr("[PSINFO] Preencha o Host remoto na aba PsExec."))
            return

        if self._worker and self._worker.isRunning():
            return

        self._set_loading(True, host=host)

        # Sem UI de checkboxes: sempre executar com tudo marcado.
        self._worker = _PsInfoWorker(
            exe_path="",
            host=host,
            include_apps=True,
            include_disks=True,
            accepteula=True,
            nobanner=True,
        )
        self._worker.finished_ok.connect(self._on_psinfo_ok)
        self._worker.finished_err.connect(self._on_psinfo_err)
        self._worker.finished.connect(self._on_worker_thread_finished)
        self._worker.start()

        if self.log_output:
            self.log_output.append_log(self.tr(f"[PSINFO] Coletando informações de {host}..."))

    def _on_worker_thread_finished(self) -> None:
        self._set_loading(False)

    def _on_psinfo_err(self, msg: str) -> None:
        if not self._ui_alive():
            return
        self._set_loading(False)
        if self.log_output:
            self.log_output.append_log(self.tr(f"[PSINFO] {msg}"))
        self._add_text_card("\uE783", self.tr("Erro"), msg)

    def _on_psinfo_ok(self, stdout: str, apps_override=None) -> None:
        if not self._ui_alive():
            return
        self._set_loading(False)
        host = self._get_host()
        parsed = parse_psinfo_output(stdout, host=host)
        if apps_override:
            parsed.applications = list(apps_override)

        # Card Sistema (pares chave/valor)
        order = [
            "Kernel version",
            "Kernel build number",
            "Product type",
            "Product version",
            "Service pack",
            "System root",
            "Uptime",
            "Processors",
            "Processor type",
            "Processor speed",
            "Physical memory",
            "Video driver",
            "IE version",
            "Registered owner",
            "Registered organization",
        ]
        kv = format_key_values(parsed.system, order=order)
        if kv:
            self._add_system_card("\uE8FE", self.tr("Sistema"), kv)
        else:
            self._add_text_card("\uE8FE", self.tr("Sistema"), self.tr("Nenhuma informação de sistema foi detectada no output."))

        # Card Aplicativos
        if parsed.applications:
            self._add_apps_card("\uE71D", self.tr("Aplicativos"), parsed.applications)

        # Card Discos
        if parsed.disks_raw:
            self._add_disks_card("\uE7B8", self.tr("Discos"), parsed.disks_raw)

        if self.log_output:
            self.log_output.append_log(self.tr(f"[PSINFO] Coleta finalizada para {host}."))

