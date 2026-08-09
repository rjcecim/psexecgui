from __future__ import annotations

import csv
import datetime
import os
import subprocess
from typing import Any, List, Optional, Union

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
    QFrame,
    QGridLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QToolButton,
    QAbstractItemView,
)

from ui.style import ICON_FONT_PT
from ui.widgets.card import CardWidget, grid_in_card, add_row, add_row_full_width, make_field_label
from ui.widgets.spinner import DotsSpinner
from utils.pstools import get_pstools_dir
from utils.psinfo import (
    InstalledApp,
    build_psinfo_target,
    build_uninstall_remote_cmd,
    describe_uninstall,
    parse_psinfo_output,
    format_key_values,
    parse_disks_table,
    list_remote_installed_apps,
)
from utils.app_catalog import resolve_uninstall_extras

# Timeout padrão para PsInfo remoto (host offline/problemático não deve travar a UI).
# Configurável via constante; documentado em documentation.md.
PSINFO_TIMEOUT_SECONDS = 90.0


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
    finished_ok = pyqtSignal(str, object)  # stdout, apps override (list[InstalledApp] | None)
    finished_err = pyqtSignal(str)  # erro amigável

    def __init__(
        self,
        exe_path: str,
        host: str,
        include_apps: bool,
        include_disks: bool,
        accepteula: bool,
        nobanner: bool,
        pstools_dir: str = "",
    ):
        super().__init__()
        self.exe_path = exe_path
        self.host = host
        self.include_apps = include_apps
        self.include_disks = include_disks
        self.accepteula = accepteula
        self.nobanner = nobanner
        self.pstools_dir = pstools_dir

    def run(self) -> None:
        try:
            from utils.pstools import resolve_pstools_tool

            target = build_psinfo_target(self.host)
            if not target:
                self.finished_err.emit("Host remoto não informado.")
                return

            exe = (self.exe_path or "").strip()
            if exe:
                exe = os.path.normpath(exe.replace('"', "").replace("'", ""))
            else:
                exe = resolve_pstools_tool(
                    self.pstools_dir or get_pstools_dir(),
                    ("PsInfo64.exe", "PsInfo.exe"),
                )
                if not exe:
                    exe = "PsInfo64.exe"

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

            try:
                proc = subprocess.run(
                    args,
                    capture_output=True,
                    text=False,
                    creationflags=creationflags,
                    timeout=PSINFO_TIMEOUT_SECONDS,
                    shell=False,
                )
            except subprocess.TimeoutExpired:
                self.finished_err.emit(
                    f"PsInfo excedeu o tempo limite ({int(PSINFO_TIMEOUT_SECONDS)}s). "
                    "O host pode estar inacessível ou sobrecarregado."
                )
                return
            except FileNotFoundError:
                self.finished_err.emit(
                    f"PsInfo não encontrado: {args[0] if args else '?'}."
                )
                return
            except OSError as exc:
                self.finished_err.emit(f"Falha ao iniciar PsInfo: {exc}")
                return

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
            self.finished_err.emit(
                "Não foi possível encontrar o PsInfo na pasta PSTools configurada."
            )
        except Exception as exc:
            self.finished_err.emit(f"Erro ao executar PsInfo: {exc}")


class PsInfoTab(QWidget):
    # remote_cmd, rótulo do app (para log)
    uninstallRequested = pyqtSignal(str, str)

    def __init__(
        self,
        parent=None,
        log_output=None,
        host_source: Optional[QLineEdit] = None,
    ):
        super().__init__(parent)
        self.log_output = log_output
        self._worker: Optional[_PsInfoWorker] = None
        self._host_source = host_source
        self._loading_card: Optional[CardWidget] = None
        self._apps_extra_params: Optional[QLineEdit] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(3)

        # Barra da pesquisa completa: renovar inventário
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: palette(windowText); opacity: 0.75;")
        self.refresh_btn = _icon_button("\uE72C", self.tr("Renovar (buscar informações novamente)"), size=28)
        self.refresh_btn.clicked.connect(self.run_psinfo)
        toolbar.addWidget(self._status_lbl, 1)
        toolbar.addWidget(self.refresh_btn, 0, Qt.AlignmentFlag.AlignRight)
        root.addLayout(toolbar)

        # Área dos cards (sem scrollbar externo)
        self.results_root = QWidget()
        self.results_layout = QVBoxLayout(self.results_root)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(3)
        self.results_layout.addStretch(1)
        root.addWidget(self.results_root, 1)

        if host_source is not None:
            host_source.textChanged.connect(self._on_host_changed)

        self.destroyed.connect(self._abort_psinfo_worker)

        # Execução é disparada pelo MainWindow ao abrir/clicar no botão.

    def _ui_alive(self) -> bool:
        return not sip.isdeleted(self)

    def _add_result_card(self, card: CardWidget, stretch: int = 1) -> None:
        """Insere o card antes do stretch final e registra o stretch para restaurar ao expandir."""
        card.set_layout_stretch(stretch)
        layout_stretch = 0 if card.is_collapsed else stretch
        idx = max(0, self.results_layout.count() - 1)
        self.results_layout.insertWidget(idx, card, layout_stretch)
        try:
            card.collapsedChanged.disconnect(self._redistribute_card_space)
        except TypeError:
            pass
        card.collapsedChanged.connect(lambda _collapsed=False: self._redistribute_card_space())
        self._redistribute_card_space()

    def _iter_result_cards(self):
        for i in range(self.results_layout.count()):
            item = self.results_layout.itemAt(i)
            w = item.widget() if item is not None else None
            if isinstance(w, CardWidget):
                yield w

    def _redistribute_card_space(self) -> None:
        """
        Com algum card expandido: eles preenchem a janela (stretch final = 0).
        Com todos minimizados: só cabeçalhos no topo (stretch final = 1).
        """
        if self.results_layout.count() == 0:
            return

        cards = list(self._iter_result_cards())
        expanded = [c for c in cards if not c.is_collapsed]
        last = self.results_layout.count() - 1

        if not expanded:
            # Todos minimizados → cabeçalhos no topo + espaço vazio embaixo
            for c in cards:
                idx = self.results_layout.indexOf(c)
                if idx >= 0:
                    self.results_layout.setStretch(idx, 0)
            self.results_layout.setStretch(last, 1)
        else:
            # Há card(s) aberto(s) → preenchem a janela inteira
            self.results_layout.setStretch(last, 0)
            for c in cards:
                idx = self.results_layout.indexOf(c)
                if idx < 0:
                    continue
                if c.is_collapsed:
                    self.results_layout.setStretch(idx, 0)
                else:
                    self.results_layout.setStretch(idx, max(1, c.layout_stretch))

        self.results_layout.activate()
        self.updateGeometry()

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
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.results_layout.addStretch(1)
        self._loading_card = None
        self._apps_extra_params = None

    def _set_loading(self, loading: bool, host: str = "") -> None:
        if not self._ui_alive():
            return
        self.refresh_btn.setEnabled(not loading)
        if loading:
            self.clear_results()
            host_disp = host or self._get_host()
            self._status_lbl.setText(
                self.tr(f"Coletando inventário de {host_disp}...") if host_disp else self.tr("Coletando inventário...")
            )
            card = CardWidget("\uE895", self.tr("Coletando informações"))
            card.set_collapsible(False)
            card.set_expanding(True)

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

            lay.addStretch(1)
            lay.addWidget(lbl, 0, Qt.AlignmentFlag.AlignHCenter)
            lay.addWidget(spinner_wrap)
            lay.addStretch(1)
            card.content_layout.addWidget(wrap, 1)

            self._loading_card = card
            self._add_result_card(card, 1)
        else:
            if self._loading_card is not None:
                card = self._loading_card
                self._loading_card = None
                if not sip.isdeleted(card):
                    card.deleteLater()

    def _add_text_card(self, icon: str, title: str, text: str) -> None:
        card = CardWidget(icon, title)
        card.set_collapsible(True, collapsed=False)
        card.set_expanding(True)
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(text or "")
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        editor.setStyleSheet("QPlainTextEdit { border: 1px solid palette(mid); border-radius: 4px; }")
        editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card.content_layout.addWidget(editor, 1)
        self._add_result_card(card, 1)

    def _add_system_card(self, icon: str, title: str, kv: list[tuple[str, str]]) -> None:
        card = CardWidget(icon, title)
        card.set_collapsible(True, collapsed=False)
        card.set_expanding(True)
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
        inner = QScrollArea()
        inner.setWidgetResizable(True)
        inner.setFrameShape(QFrame.Shape.NoFrame)
        inner.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner.setWidget(wrap)
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card.content_layout.addWidget(inner, 1)
        self._wire_card_download(card, "sistema", list(kv))
        self._add_result_card(card, 2)

    def _add_apps_card(self, icon: str, title: str, apps: List[Union[InstalledApp, str]]) -> None:
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

        normalized: List[Union[InstalledApp, str]] = []
        for a in apps:
            if isinstance(a, InstalledApp):
                if a.display_name.strip() or a.display_line.strip():
                    normalized.append(a)
            elif a and str(a).strip():
                normalized.append(str(a).strip())

        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(
            [self.tr("Nome"), self.tr("Editor"), self.tr("Versão"), self.tr("Tipo"), ""]
        )
        table.setRowCount(len(normalized))
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(4, 36)
        table.setStyleSheet(
            """
            QTableWidget { border: 1px solid palette(mid); border-radius: 4px; }
            QTableWidget::item { padding: 4px 6px; }
            """
        )
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        table.setMinimumHeight(80)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        trash_buttons: list = []

        for row, app in enumerate(normalized):
            if isinstance(app, InstalledApp):
                name = app.display_name or app.display_line
                publisher = app.publisher or ""
                version = app.version or ""
                kind = "MSI" if (app.is_msi and app.product_code) else "EXE"
                try:
                    build_uninstall_remote_cmd(app, "")
                    can_uninstall = True
                except ValueError:
                    can_uninstall = False
            else:
                name = str(app)
                publisher = ""
                version = ""
                kind = ""
                can_uninstall = False

            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, app if isinstance(app, InstalledApp) else None)
            publisher_item = QTableWidgetItem(publisher)
            version_item = QTableWidgetItem(version)
            kind_item = QTableWidgetItem(kind)
            kind_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 0, name_item)
            table.setItem(row, 1, publisher_item)
            table.setItem(row, 2, version_item)
            table.setItem(row, 3, kind_item)

            trash = QToolButton()
            trash.setText("\uE74D")  # Delete
            trash.setFont(QFont("Segoe MDL2 Assets", 11))
            trash.setCursor(Qt.CursorShape.PointingHandCursor)
            trash.setAutoRaise(True)
            trash.setFixedSize(26, 26)
            trash.setStyleSheet(
                """
                QToolButton {
                    border: none;
                    background: transparent;
                    color: palette(windowText);
                }
                QToolButton:hover {
                    background: palette(light);
                    border-radius: 4px;
                    color: #c42b1c;
                }
                QToolButton:disabled { color: palette(mid); }
                """
            )
            if can_uninstall and isinstance(app, InstalledApp):
                trash.setToolTip(describe_uninstall(app, resolve_uninstall_extras(app, "")))
                trash._installed_app = app  # type: ignore[attr-defined]
                trash_buttons.append(trash)
                trash.clicked.connect(lambda _checked=False, a=app: self._on_uninstall_clicked(a))
            else:
                trash.setEnabled(False)
                trash.setToolTip(self.tr("Desinstalação indisponível (sem UninstallString)"))

            cell = QWidget()
            cell_lay = QHBoxLayout(cell)
            cell_lay.setContentsMargins(0, 0, 0, 0)
            cell_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_lay.addWidget(trash)
            table.setCellWidget(row, 4, cell)

        def update_filter():
            q = (search.text() or "").strip().lower()
            visible = 0
            for r in range(table.rowCount()):
                name_it = table.item(r, 0)
                pub_it = table.item(r, 1)
                ver_it = table.item(r, 2)
                kind_it = table.item(r, 3)
                text = (
                    f"{name_it.text() if name_it else ''} "
                    f"{pub_it.text() if pub_it else ''} "
                    f"{ver_it.text() if ver_it else ''} "
                    f"{kind_it.text() if kind_it else ''}"
                ).lower()
                ok = (q in text) if q else True
                table.setRowHidden(r, not ok)
                if ok:
                    visible += 1
            count_lbl.setText(self.tr(f"{visible}/{len(normalized)}"))

        search.textChanged.connect(update_filter)
        update_filter()

        top_wrap = QWidget()
        top_wrap.setLayout(top)
        card.set_expanding(True)
        card.content_layout.addWidget(top_wrap, 0)
        card.content_layout.addWidget(table, 1)

        extras_row = QHBoxLayout()
        extras_row.setContentsMargins(0, 4, 0, 0)
        extras_row.setSpacing(10)
        extras_lbl = make_field_label(self.tr("Parametros Extras"))
        extras_edit = QLineEdit()
        extras_edit.setPlaceholderText(
            self.tr("Opcional — vazio usa ApplicationCatalog.json. EXE: /S. MSI: REBOOT=ReallySuppress")
        )
        extras_edit.setToolTip(
            self.tr(
                "Se preenchido, sobrescreve o ApplicationCatalog.json.\n"
                "Se vazio, usa uninstallArgs do catálogo quando o app for reconhecido.\n"
                "EXE: switches do fabricante (WinRAR: /S).\n"
                "MSI: adicionais além de /qn /norestart."
            )
        )
        extras_row.addWidget(extras_lbl)
        extras_row.addWidget(extras_edit, 1)
        extras_wrap = QWidget()
        extras_wrap.setLayout(extras_row)
        card.content_layout.addWidget(extras_wrap, 0)
        self._apps_extra_params = extras_edit

        def refresh_trash_tooltips():
            extras_manual = (extras_edit.text() or "").strip()
            for btn in trash_buttons:
                app_obj = getattr(btn, "_installed_app", None)
                if isinstance(app_obj, InstalledApp):
                    btn.setToolTip(
                        describe_uninstall(app_obj, resolve_uninstall_extras(app_obj, extras_manual))
                    )

        extras_edit.textChanged.connect(lambda _t: refresh_trash_tooltips())
        refresh_trash_tooltips()

        self._wire_card_download(card, "aplicativos", list(normalized))
        self._add_result_card(card, 3)


    def _on_uninstall_clicked(self, app: InstalledApp) -> None:
        if not self._ui_alive():
            return
        host = self._get_host()
        if not host:
            if self.log_output:
                self.log_output.append_log(self.tr("[PSINFO] Host remoto não informado."))
            return

        manual = ""
        if self._apps_extra_params is not None and not sip.isdeleted(self._apps_extra_params):
            manual = (self._apps_extra_params.text() or "").strip()
        extras = resolve_uninstall_extras(app, manual)

        try:
            remote_cmd = build_uninstall_remote_cmd(app, extras)
        except ValueError as exc:
            if self.log_output:
                self.log_output.append_log(self.tr(f"[PSINFO] {exc}"))
            return

        if extras and not manual and self.log_output:
            self.log_output.append_log(
                self.tr(f"[PSINFO] Parametros do catálogo para {app.display_name}: {extras}")
            )

        self.uninstallRequested.emit(remote_cmd, app.display_line)

    def _wire_card_download(self, card: CardWidget, kind: str, payload: Any) -> None:
        card.set_downloadable(True)
        card.downloadRequested.connect(lambda k=kind, p=payload: self._download_card_data(k, p))

    def _download_card_data(self, kind: str, payload: Any) -> None:
        host = (self._get_host() or "host").strip().strip("\\") or "host"
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_host = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in host)

        if kind == "sistema":
            default_name = f"psinfo_{safe_host}_sistema_{stamp}.txt"
            filt = self.tr("Texto (*.txt)")
            path, _ = QFileDialog.getSaveFileName(self, self.tr("Salvar Sistema"), default_name, filt)
            if not path:
                return
            lines = [f"Host: {host}", f"Gerado: {stamp}", ""]
            for k, v in payload or []:
                lines.append(f"{k}: {v}")
            text = "\n".join(lines) + "\n"
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        elif kind == "aplicativos":
            default_name = f"psinfo_{safe_host}_aplicativos_{stamp}.csv"
            filt = self.tr("CSV (*.csv)")
            path, _ = QFileDialog.getSaveFileName(self, self.tr("Salvar Aplicativos"), default_name, filt)
            if not path:
                return
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Nome", "Editor", "Versao", "Tipo", "ProductCode", "UninstallString"])
                for app in payload or []:
                    if isinstance(app, InstalledApp):
                        kind_app = "MSI" if (app.is_msi and app.product_code) else "EXE"
                        w.writerow(
                            [
                                app.display_name,
                                app.publisher,
                                app.version,
                                kind_app,
                                app.product_code,
                                app.uninstall_string or app.quiet_uninstall_string,
                            ]
                        )
                    else:
                        w.writerow([str(app), "", "", "", "", ""])
        elif kind == "discos":
            default_name = f"psinfo_{safe_host}_discos_{stamp}.csv"
            filt = self.tr("CSV (*.csv)")
            path, _ = QFileDialog.getSaveFileName(self, self.tr("Salvar Discos"), default_name, filt)
            if not path:
                return
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Volume", "Tipo", "Formato", "Rotulo", "Tamanho", "Livre", "PctLivre"])
                for row in payload or []:
                    w.writerow(
                        [row.volume, row.type, row.format, row.label, row.size, row.free, row.free_pct]
                    )
        else:
            return

        if self.log_output:
            self.log_output.append_log(self.tr(f"[PSINFO] Arquivo salvo: {path}"))
        self._status_lbl.setText(self.tr(f"Arquivo salvo: {os.path.basename(path)}"))

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

        # Ocupa fatia da tela; rolagem só se houver muitos volumes
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        table.setMinimumHeight(56)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        card.set_expanding(True)
        card.content_layout.addWidget(table, 1)
        self._wire_card_download(card, "discos", list(rows))
        self._add_result_card(card, 1)

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
            pstools_dir=get_pstools_dir(),
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
        self._status_lbl.setText(self.tr("Falha na coleta"))
        self._add_text_card("\uE783", self.tr("Erro"), msg)

    def _on_psinfo_ok(self, stdout: str, apps_override=None) -> None:
        if not self._ui_alive():
            return
        self._set_loading(False)
        host = self._get_host()
        parsed = parse_psinfo_output(stdout, host=host)

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

        # Card Aplicativos (preferir lista rica do Remote Registry)
        if apps_override:
            self._add_apps_card("\uE71D", self.tr("Aplicativos"), list(apps_override))
        elif parsed.applications:
            self._add_apps_card("\uE71D", self.tr("Aplicativos"), parsed.applications)

        # Card Discos
        if parsed.disks_raw:
            self._add_disks_card("\uE7B8", self.tr("Discos"), parsed.disks_raw)

        if self.log_output:
            self.log_output.append_log(self.tr(f"[PSINFO] Coleta finalizada para {host}."))
        self._status_lbl.setText(self.tr(f"Inventário de {host}") if host else self.tr("Inventário atualizado"))

