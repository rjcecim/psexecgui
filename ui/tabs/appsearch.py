from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Optional, Tuple

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
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QToolButton,
    QAbstractItemView,
    QMessageBox,
)

from ui.style import ICON_FONT_PT, INPUT_HEIGHT
from ui.widgets.card import CardWidget, grid_in_card, add_row, make_field_label
from utils.psinfo import (
    InstalledApp,
    build_uninstall_remote_cmd,
    describe_uninstall,
    list_remote_installed_apps,
)

# Consultas remotas são I/O-bound; paralelizar acelera a varredura multi-host.
_SEARCH_MAX_WORKERS = 8


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # main.py fica na raiz do projeto
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _icon_button(icon_char: str, tooltip: str = "", size: int = INPUT_HEIGHT) -> QPushButton:
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


def load_hosts_file(path: str) -> List[str]:
    """Carrega lista de hosts do JSON no formato {\"hosts\": [\"HOST1\", ...]}."""
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "hosts" not in data:
        raise ValueError('Arquivo inválido: esperado um objeto com a chave "hosts".')
    hosts_raw = data["hosts"]
    if not isinstance(hosts_raw, list):
        raise ValueError('Arquivo inválido: "hosts" deve ser uma lista.')
    out: List[str] = []
    seen: set[str] = set()
    for item in hosts_raw:
        h = str(item or "").strip().strip("\\")
        if not h:
            continue
        key = h.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    if not out:
        raise ValueError("Nenhum host válido encontrado no arquivo.")
    return out


@dataclass
class SearchHit:
    host: str
    app: InstalledApp


class _AppSearchWorker(QThread):
    progress = pyqtSignal(int, int, str)  # done, total, último host concluído
    hitsFound = pyqtSignal(list)  # List[SearchHit] do host recém-consultado
    finished_ok = pyqtSignal(str)  # query
    finished_aborted = pyqtSignal(str)  # query (interrupção pelo usuário)
    finished_err = pyqtSignal(str)

    def __init__(self, hosts: List[str], query: str, max_workers: int = _SEARCH_MAX_WORKERS):
        super().__init__()
        self.hosts = list(hosts)
        self.query = (query or "").strip()
        self.max_workers = max(1, int(max_workers))
        self._abort = False

    def abort(self) -> None:
        self._abort = True

    @staticmethod
    def _scan_host(host: str, query_cf: str) -> Tuple[str, List[SearchHit]]:
        try:
            apps = list_remote_installed_apps(host)
        except Exception:
            apps = []
        hits: List[SearchHit] = []
        for app in apps:
            name = (app.display_name or "").casefold()
            if query_cf in name:
                hits.append(SearchHit(host=host, app=app))
        return host, hits

    def run(self) -> None:
        try:
            q = self.query.casefold()
            if not q:
                self.finished_err.emit("Informe o nome do aplicativo a pesquisar.")
                return
            if not self.hosts:
                self.finished_err.emit("Nenhum host para consultar.")
                return

            total = len(self.hosts)
            workers = min(self.max_workers, total)
            done = 0
            executor = ThreadPoolExecutor(max_workers=workers)
            futures = {
                executor.submit(self._scan_host, host, q): host for host in self.hosts
            }
            try:
                for fut in as_completed(futures):
                    if self._abort:
                        break
                    host = futures[fut]
                    try:
                        host, hits = fut.result()
                    except Exception:
                        hits = []
                    if self._abort:
                        break
                    done += 1
                    self.progress.emit(done, total, host)
                    if hits:
                        self.hitsFound.emit(hits)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

            if self._abort:
                self.finished_aborted.emit(self.query)
                return
            self.progress.emit(total, total, "")
            self.finished_ok.emit(self.query)
        except Exception as exc:
            self.finished_err.emit(f"Erro na pesquisa: {exc}")


class AppSearchTab(QWidget):
    """Tela de pesquisa de aplicativos instalados em múltiplos hosts."""

    # host, remote_cmd, rótulo do app (para log)
    uninstallRequested = pyqtSignal(str, str, str)

    def __init__(self, parent=None, log_output=None):
        super().__init__(parent)
        self.log_output = log_output
        self._worker: Optional[_AppSearchWorker] = None
        self._hosts_path = ""
        self._hits: List[SearchHit] = []
        self._active_query = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(3)

        # ── Card Pesquisa ──────────────────────────────────────────────
        search_card = CardWidget("\uE721", self.tr("Pesquisa"))
        search_card.set_collapsible(True, collapsed=False)
        grid = grid_in_card(search_card)

        self.app_edit = QLineEdit()
        self.app_edit.setPlaceholderText(self.tr("Nome completo ou parte do nome do aplicativo"))
        # \uE721 = Find / lupa ; \uE71A = Stop (Segoe MDL2 Assets)
        self.search_btn = _icon_button("\uE721", self.tr("Pesquisar"))
        self.search_btn.clicked.connect(self.start_search)
        self.stop_btn = _icon_button("\uE71A", self.tr("Parar pesquisa"))
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_search)
        self.app_edit.returnPressed.connect(self.start_search)
        app_wrap = QWidget()
        app_lay = QHBoxLayout(app_wrap)
        app_lay.setContentsMargins(0, 0, 0, 0)
        app_lay.setSpacing(6)
        app_lay.addWidget(self.app_edit, 1)
        app_lay.addWidget(self.search_btn)
        app_lay.addWidget(self.stop_btn)
        add_row(grid, 0, self.tr("Aplicativo a pesquisar"), app_wrap)

        hosts_wrap = QWidget()
        hosts_lay = QHBoxLayout(hosts_wrap)
        hosts_lay.setContentsMargins(0, 0, 0, 0)
        hosts_lay.setSpacing(6)
        self.hosts_path_edit = QLineEdit()
        self.hosts_path_edit.setReadOnly(True)
        self.hosts_path_edit.setPlaceholderText(self.tr("Arquivo hosts.json"))
        self.browse_hosts_btn = _icon_button("\uED43", self.tr("Selecionar arquivo JSON de hosts"))
        self.browse_hosts_btn.clicked.connect(self._browse_hosts_file)
        hosts_lay.addWidget(self.hosts_path_edit, 1)
        hosts_lay.addWidget(self.browse_hosts_btn)
        add_row(grid, 1, self.tr("Arquivo de hosts"), hosts_wrap)

        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%v / %m hosts")
        self.progress.setVisible(False)
        self.progress.setFixedHeight(18)
        self.progress_lbl = QLabel("")
        self.progress_lbl.setStyleSheet("color: palette(windowText); opacity: 0.75;")
        self.progress_lbl.setVisible(False)
        search_card.content_layout.addWidget(self.progress)
        search_card.content_layout.addWidget(self.progress_lbl)

        root.addWidget(search_card, 0)

        # ── Card Resultados ────────────────────────────────────────────
        results_card = CardWidget("\uE71D", self.tr("Resultados"))
        results_card.set_collapsible(True, collapsed=False)
        results_card.set_expanding(True)

        self.summary_lbl = QLabel("")
        self.summary_lbl.setStyleSheet("color: palette(windowText); opacity: 0.75;")
        results_card.content_layout.addWidget(self.summary_lbl, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            [
                self.tr("Computador"),
                self.tr("Nome"),
                self.tr("Editor"),
                self.tr("Versão"),
                self.tr("Tipo"),
                self.tr("Ações"),
            ]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 48)
        self.table.setStyleSheet(
            """
            QTableWidget { border: 1px solid palette(mid); border-radius: 4px; }
            QTableWidget::item { padding: 4px 6px; }
            """
        )
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.setMinimumHeight(80)
        results_card.content_layout.addWidget(self.table, 1)

        extras_row = QHBoxLayout()
        extras_row.setContentsMargins(0, 4, 0, 0)
        extras_row.setSpacing(10)
        extras_lbl = make_field_label(self.tr("Parametros Extras"))
        self.extras_edit = QLineEdit()
        self.extras_edit.setPlaceholderText(
            self.tr("EXE: ex. /S (WinRAR). MSI: ex. REBOOT=ReallySuppress")
        )
        self.extras_edit.setToolTip(
            self.tr(
                "Anexado ao comando padrão de cada app.\n"
                "EXE: switches do fabricante (WinRAR: /S).\n"
                "MSI: adicionais além de /qn /norestart."
            )
        )
        extras_row.addWidget(extras_lbl)
        extras_row.addWidget(self.extras_edit, 1)
        extras_wrap = QWidget()
        extras_wrap.setLayout(extras_row)
        results_card.content_layout.addWidget(extras_wrap, 0)
        self._trash_buttons: list = []
        self.extras_edit.textChanged.connect(lambda _t: self._refresh_trash_tooltips())

        root.addWidget(results_card, 1)

        self.destroyed.connect(self._abort_worker)
        self._init_hosts_file()

    def _ui_alive(self) -> bool:
        return not sip.isdeleted(self)

    def _init_hosts_file(self) -> None:
        default = os.path.join(_app_dir(), "hosts.json")
        if os.path.isfile(default):
            self._set_hosts_path(default)
        else:
            self.hosts_path_edit.clear()
            self.hosts_path_edit.setPlaceholderText(
                self.tr("hosts.json não encontrado — selecione um arquivo JSON")
            )

    def _set_hosts_path(self, path: str) -> None:
        p = os.path.normpath(path)
        # Windows pode devolver "c:\..."; exibir "C:\" em caixa alta
        if len(p) >= 2 and p[1] == ":":
            p = p[0].upper() + p[1:]
        self._hosts_path = p
        self.hosts_path_edit.setText(self._hosts_path)

    def _browse_hosts_file(self) -> None:
        start = self._hosts_path or _app_dir()
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Selecionar arquivo de hosts"),
            start,
            self.tr("JSON (*.json)"),
        )
        if path:
            self._set_hosts_path(path)

    def _abort_worker(self, _destroyed: object = None) -> None:
        w = self._worker
        if w is None:
            return
        self._worker = None
        for signal, slot in (
            (w.progress, self._on_progress),
            (w.hitsFound, self._on_hits_found),
            (w.finished_ok, self._on_search_ok),
            (w.finished_aborted, self._on_search_aborted),
            (w.finished_err, self._on_search_err),
            (w.finished, self._on_worker_finished),
        ):
            try:
                signal.disconnect(slot)
            except TypeError:
                pass
        w.abort()
        if w.isRunning():
            w.finished.connect(w.deleteLater)
        else:
            w.deleteLater()

    def stop_search(self) -> None:
        """Interrompe a pesquisa em andamento (após o host atual)."""
        w = self._worker
        if w is None or not w.isRunning():
            return
        w.abort()
        self.stop_btn.setEnabled(False)
        self.progress_lbl.setText(self.tr("Interrompendo pesquisa..."))
        if self.log_output:
            self.log_output.append_log(self.tr("[PESQUISA] Interrupção solicitada pelo usuário."))

    def start_search(self) -> None:
        if self._worker and self._worker.isRunning():
            return

        query = (self.app_edit.text() or "").strip()
        if not query:
            QMessageBox.warning(
                self,
                self.tr("Pesquisa de Aplicativos"),
                self.tr("Informe o aplicativo a pesquisar."),
            )
            return

        if not self._hosts_path or not os.path.isfile(self._hosts_path):
            QMessageBox.warning(
                self,
                self.tr("Pesquisa de Aplicativos"),
                self.tr("Selecione um arquivo hosts.json válido."),
            )
            return

        try:
            hosts = load_hosts_file(self._hosts_path)
        except Exception as exc:
            QMessageBox.warning(
                self,
                self.tr("Pesquisa de Aplicativos"),
                self.tr(f"Não foi possível ler o arquivo de hosts:\n{exc}"),
            )
            return

        self._hits = []
        self._trash_buttons = []
        self._active_query = query
        self.table.setRowCount(0)
        self.summary_lbl.setText(self.tr("Pesquisando..."))
        self.search_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.app_edit.setEnabled(False)
        self.browse_hosts_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress_lbl.setVisible(True)
        self.progress.setMaximum(len(hosts))
        self.progress.setValue(0)
        self.progress.setFormat(f"%v / %m hosts")
        self.progress_lbl.setText(self.tr("Iniciando pesquisa..."))

        self._worker = _AppSearchWorker(hosts, query)
        self._worker.progress.connect(self._on_progress)
        self._worker.hitsFound.connect(self._on_hits_found)
        self._worker.finished_ok.connect(self._on_search_ok)
        self._worker.finished_aborted.connect(self._on_search_aborted)
        self._worker.finished_err.connect(self._on_search_err)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

        workers = min(_SEARCH_MAX_WORKERS, len(hosts))
        if self.log_output:
            self.log_output.append_log(
                self.tr(
                    f"[PESQUISA] Buscando '{query}' em {len(hosts)} host(s) "
                    f"({workers} threads)..."
                )
            )

    def _on_progress(self, done: int, total: int, host: str) -> None:
        if not self._ui_alive():
            return
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(done)
        if host:
            self.progress_lbl.setText(
                self.tr(f"{done} de {total} hosts consultados — último: {host}")
            )
        else:
            self.progress_lbl.setText(self.tr(f"{done} de {total} hosts consultados"))

    def _on_worker_finished(self) -> None:
        if not self._ui_alive():
            return
        self.search_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.app_edit.setEnabled(True)
        self.browse_hosts_btn.setEnabled(True)

    def _on_search_err(self, msg: str) -> None:
        if not self._ui_alive():
            return
        self.progress.setVisible(False)
        self.progress_lbl.setVisible(True)
        self.progress_lbl.setText(self.tr(f"Falha: {msg}"))
        if self.log_output:
            self.log_output.append_log(self.tr(f"[PESQUISA] {msg}"))

    def _on_hits_found(self, hits: list) -> None:
        """Exibe imediatamente as correspondências do host recém-consultado."""
        if not self._ui_alive() or not hits:
            return
        for hit in hits:
            if isinstance(hit, SearchHit):
                self._hits.append(hit)
                self._append_hit_row(hit)
        self._update_summary(final=False)

    def _on_search_ok(self, query: str) -> None:
        if not self._ui_alive():
            return
        self._active_query = query or self._active_query
        self.progress.setValue(self.progress.maximum())
        self.progress_lbl.setText(
            self.tr(f"Pesquisa concluída — {self.progress.maximum()} hosts consultados")
        )
        self._update_summary(final=True)
        computers = {h.host.casefold() for h in self._hits}
        if self.log_output:
            self.log_output.append_log(
                self.tr(
                    f"[PESQUISA] Concluída: {len(computers)} computador(es), "
                    f"{len(self._hits)} correspondência(s)."
                )
            )

    def _on_search_aborted(self, query: str) -> None:
        if not self._ui_alive():
            return
        self._active_query = query or self._active_query
        done = self.progress.value()
        total = self.progress.maximum()
        self.progress_lbl.setText(
            self.tr(f"Pesquisa interrompida — {done} de {total} hosts consultados")
        )
        self._update_summary(final=True, interrupted=True)
        computers = {h.host.casefold() for h in self._hits}
        if self.log_output:
            self.log_output.append_log(
                self.tr(
                    f"[PESQUISA] Interrompida: {len(computers)} computador(es), "
                    f"{len(self._hits)} correspondência(s) até o momento."
                )
            )

    def _update_summary(self, final: bool = False, interrupted: bool = False) -> None:
        query = getattr(self, "_active_query", "") or ""
        computers = {h.host.casefold() for h in self._hits}
        count_hosts = len(computers)
        count_apps = len(self._hits)
        if count_apps == 0:
            if final:
                if interrupted:
                    self.summary_lbl.setText(
                        self.tr(
                            f"Pesquisa interrompida — nenhum computador com "
                            f"aplicativo correspondente a “{query}” até o momento."
                        )
                    )
                else:
                    self.summary_lbl.setText(
                        self.tr(f"Nenhum computador com aplicativo correspondente a “{query}”.")
                    )
            else:
                self.summary_lbl.setText(self.tr("Pesquisando..."))
            return
        if interrupted:
            prefix = self.tr("Interrompida — ")
        elif final:
            prefix = ""
        else:
            prefix = self.tr("Em andamento — ")
        self.summary_lbl.setText(
            self.tr(
                f"{prefix}Aplicativo encontrado em {count_hosts} computador(es) "
                f"({count_apps} correspondência(s) para “{query}”)."
            )
        )

    def _append_hit_row(self, hit: SearchHit) -> None:
        app = hit.app
        name = app.display_name or app.display_line
        kind = "MSI" if (app.is_msi and app.product_code) else "EXE"
        try:
            build_uninstall_remote_cmd(app, "")
            can_uninstall = True
        except ValueError:
            can_uninstall = False

        row = self.table.rowCount()
        self.table.insertRow(row)

        host_item = QTableWidgetItem(hit.host)
        name_item = QTableWidgetItem(name)
        name_item.setData(Qt.ItemDataRole.UserRole, hit)
        pub_item = QTableWidgetItem(app.publisher or "")
        ver_item = QTableWidgetItem(app.version or "")
        kind_item = QTableWidgetItem(kind)
        kind_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        self.table.setItem(row, 0, host_item)
        self.table.setItem(row, 1, name_item)
        self.table.setItem(row, 2, pub_item)
        self.table.setItem(row, 3, ver_item)
        self.table.setItem(row, 4, kind_item)

        trash = QToolButton()
        trash.setText("\uE74D")
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
        if can_uninstall:
            extras_now = ""
            if self.extras_edit is not None and not sip.isdeleted(self.extras_edit):
                extras_now = (self.extras_edit.text() or "").strip()
            trash.setToolTip(describe_uninstall(app, extras_now))
            trash._installed_app = app  # type: ignore[attr-defined]
            self._trash_buttons.append(trash)
            trash.clicked.connect(
                lambda _checked=False, h=hit: self._on_uninstall_clicked(h)
            )
        else:
            trash.setEnabled(False)
            trash.setToolTip(self.tr("Desinstalação indisponível (sem UninstallString)"))

        cell = QWidget()
        cell_lay = QHBoxLayout(cell)
        cell_lay.setContentsMargins(0, 0, 0, 0)
        cell_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cell_lay.addWidget(trash)
        self.table.setCellWidget(row, 5, cell)

    def _current_extras(self) -> str:
        if self.extras_edit is None or sip.isdeleted(self.extras_edit):
            return ""
        return (self.extras_edit.text() or "").strip()

    def _refresh_trash_tooltips(self) -> None:
        if not self._ui_alive():
            return
        extras_now = self._current_extras()
        for btn in list(self._trash_buttons):
            if sip.isdeleted(btn):
                continue
            app_obj = getattr(btn, "_installed_app", None)
            if isinstance(app_obj, InstalledApp):
                btn.setToolTip(describe_uninstall(app_obj, extras_now))

    def _on_uninstall_clicked(self, hit: SearchHit) -> None:
        if not self._ui_alive():
            return
        extras = self._current_extras()
        try:
            remote_cmd = build_uninstall_remote_cmd(hit.app, extras)
        except ValueError as exc:
            if self.log_output:
                self.log_output.append_log(self.tr(f"[PESQUISA] {exc}"))
            return

        self.uninstallRequested.emit(hit.host, remote_cmd, hit.app.display_line)
