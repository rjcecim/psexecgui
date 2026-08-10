from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

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
)
from utils.app_catalog import resolve_uninstall_extras
from utils.hosts import load_hosts_file, app_dir as _hosts_app_dir
from utils.app_settings import SETTINGS_SAVE_ERROR_MSG, SettingsWriteError
from utils.remote_registry_query import (
    REMOTE_REGISTRY_TIMEOUT_SECONDS,
    run_remote_inventory_batch,
)
from utils.search_settings import (
    MAX_SEARCH_MAX_WORKERS,
    MIN_SEARCH_MAX_WORKERS,
    get_search_max_workers,
    resolve_configured_hosts_path,
    set_search_hosts_path,
)


def _app_dir() -> str:
    return _hosts_app_dir()


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


@dataclass
class SearchHit:
    host: str
    app: InstalledApp
    # status do host no momento do hit (consultado com sucesso)
    host_ok: bool = True


class _AppSearchWorker(QThread):
    # generation, done, failed, total, último host, ok, error_kind
    progress = pyqtSignal(int, int, int, int, str, bool, str)
    # generation, List[SearchHit]
    hitsFound = pyqtSignal(int, list)
    finished_ok = pyqtSignal(int, str)  # generation, query
    finished_aborted = pyqtSignal(int, str)  # generation, query
    finished_err = pyqtSignal(int, str)  # generation, msg

    def __init__(
        self,
        hosts: List[str],
        query: str,
        max_workers: int = 8,
        *,
        generation: int = 0,
        timeout: float = REMOTE_REGISTRY_TIMEOUT_SECONDS,
    ):
        super().__init__()
        self.hosts = list(hosts)
        self.query = (query or "").strip()
        try:
            n = int(max_workers)
        except (TypeError, ValueError):
            n = 8
        self.max_workers = max(MIN_SEARCH_MAX_WORKERS, min(MAX_SEARCH_MAX_WORKERS, n))
        self.generation = int(generation)
        self.timeout = float(timeout) if timeout else REMOTE_REGISTRY_TIMEOUT_SECONDS
        self._abort = False

    def abort(self) -> None:
        self._abort = True

    def run(self) -> None:
        gen = self.generation
        try:
            q = self.query.casefold()
            if not q:
                self.finished_err.emit(gen, "Informe o nome do aplicativo a pesquisar.")
                return
            if not self.hosts:
                self.finished_err.emit(gen, "Nenhum host para consultar.")
                return

            total = len(self.hosts)
            workers = min(self.max_workers, total)
            done = 0
            failed = 0
            saw_cancel = False

            for status in run_remote_inventory_batch(
                self.hosts,
                max_workers=workers,
                timeout=self.timeout,
                should_cancel=lambda: self._abort,
            ):
                if self._abort and status.error_kind == "cancelled":
                    saw_cancel = True
                    # Não conta hosts cancelados (já iniciados) como "falha de rede";
                    # ainda incrementa progresso para refletir vagas liberadas.
                    done += 1
                    self.progress.emit(
                        gen, done, failed, total, status.host, False, "cancelled"
                    )
                    continue

                hits: List[SearchHit] = []
                ok = bool(status.ok)
                error_kind = status.error_kind or ("" if ok else "internal_error")
                if ok:
                    for app in status.apps:
                        name = (app.display_name or "").casefold()
                        if q in name:
                            hits.append(
                                SearchHit(host=status.host, app=app, host_ok=True)
                            )
                done += 1
                if not ok:
                    failed += 1
                self.progress.emit(
                    gen, done, failed, total, status.host, ok, error_kind
                )
                if hits:
                    self.hitsFound.emit(gen, hits)

            if self._abort or saw_cancel:
                self.finished_aborted.emit(gen, self.query)
                return
            self.progress.emit(gen, total, failed, total, "", True, "")
            self.finished_ok.emit(gen, self.query)
        except Exception as exc:
            self.finished_err.emit(gen, f"Erro na pesquisa: {exc}")


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
        self._hosts_failed = 0
        self._hosts_done = 0
        self._hosts_total = 0
        # Após interrupção, ignora sinais tardios do worker antigo
        self._accepting_search_results = False
        self._search_generation = 0

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

        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 2, 0, 0)
        stats_row.setSpacing(16)
        self.ok_count_lbl = QLabel(self.tr("Sucesso: 0"))
        self.fail_count_lbl = QLabel(self.tr("Falharam: 0"))
        self.progress_lbl = QLabel("")
        for lbl in (self.ok_count_lbl, self.fail_count_lbl, self.progress_lbl):
            lbl.setStyleSheet("color: palette(windowText); opacity: 0.85;")
            lbl.setVisible(False)
        self.ok_count_lbl.setStyleSheet(
            "color: palette(highlight); font-weight: 600;"
        )
        self.fail_count_lbl.setStyleSheet(
            "color: #c42b1c; font-weight: 600;"
        )
        stats_row.addWidget(self.ok_count_lbl)
        stats_row.addWidget(self.fail_count_lbl)
        stats_row.addWidget(self.progress_lbl, 1)
        stats_wrap = QWidget()
        stats_wrap.setLayout(stats_row)
        self._stats_wrap = stats_wrap
        self._stats_wrap.setVisible(False)

        search_card.content_layout.addWidget(self.progress)
        search_card.content_layout.addWidget(self._stats_wrap)

        root.addWidget(search_card, 0)

        # ── Card Resultados ────────────────────────────────────────────
        results_card = CardWidget("\uE71D", self.tr("Resultados"))
        results_card.set_collapsible(True, collapsed=False)
        results_card.set_expanding(True)

        self.summary_lbl = QLabel("")
        self.summary_lbl.setStyleSheet("color: palette(windowText); opacity: 0.75;")
        results_card.content_layout.addWidget(self.summary_lbl, 0)

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(8)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(self.tr("Buscar aplicativo..."))
        self.filter_count_lbl = QLabel("")
        self.filter_count_lbl.setStyleSheet("color: palette(windowText); opacity: 0.75;")
        filter_row.addWidget(self.filter_edit)
        filter_row.addWidget(self.filter_count_lbl)
        filter_wrap = QWidget()
        filter_wrap.setLayout(filter_row)
        results_card.content_layout.addWidget(filter_wrap, 0)
        self.filter_edit.textChanged.connect(self._apply_results_filter)

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
            self.tr("Opcional — vazio usa ApplicationCatalog.json. EXE: /S. MSI: REBOOT=ReallySuppress")
        )
        self.extras_edit.setToolTip(
            self.tr(
                "Se preenchido, sobrescreve o ApplicationCatalog.json.\n"
                "Se vazio, usa uninstallArgs do catálogo quando o app for reconhecido.\n"
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
        path, _origin = resolve_configured_hosts_path()
        if path and os.path.isfile(path):
            self._set_hosts_path(path, persist=False)
        else:
            self.hosts_path_edit.clear()
            self.hosts_path_edit.setPlaceholderText(
                self.tr(
                    "hosts.json não encontrado — selecione um arquivo "
                    "(veja hosts.example.json)"
                )
            )

    def _set_hosts_path(self, path: str, *, persist: bool = True) -> None:
        p = os.path.normpath(path)
        # Windows pode devolver "c:\..."; exibir "C:\" em caixa alta
        if len(p) >= 2 and p[1] == ":":
            p = p[0].upper() + p[1:]
        if persist:
            try:
                set_search_hosts_path(p)
            except SettingsWriteError as exc:
                msg = getattr(exc, "message", None) or SETTINGS_SAVE_ERROR_MSG
                QMessageBox.warning(self, self.tr("Configurações"), self.tr(msg))
                return
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

    def _disconnect_worker_signals(self, w: _AppSearchWorker) -> None:
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

    def _is_current_generation(self, generation: int) -> bool:
        return (
            self._accepting_search_results
            and int(generation) == int(self._search_generation)
        )

    def _abort_worker(self, _destroyed: object = None) -> None:
        w = self._worker
        if w is None:
            return
        self._worker = None
        self._accepting_search_results = False
        self._disconnect_worker_signals(w)
        w.abort()
        if w.isRunning():
            # Aguarda o lote encerrar processos filhos (terminate + join).
            w.wait(max(3000, int(REMOTE_REGISTRY_TIMEOUT_SECONDS * 1000) // 3))
        if w.isRunning():
            w.finished.connect(w.deleteLater)
        else:
            w.deleteLater()

    def shutdown(self, wait_ms: int = 8000) -> None:
        """Aborta pesquisa, encerra filhos RR e espera a QThread."""
        self._accepting_search_results = False
        w = self._worker
        if w is None:
            return
        self._worker = None
        self._disconnect_worker_signals(w)
        w.abort()
        if w.isRunning():
            w.wait(max(0, int(wait_ms)))
        if w.isRunning():
            w.finished.connect(w.deleteLater)
        else:
            w.deleteLater()

    def stop_search(self) -> None:
        """
        Interrompe a pesquisa: para o agendamento, encerra processos filhos
        ativos e descarta resultados posteriores.
        """
        w = self._worker
        if w is None or not w.isRunning():
            return
        self._accepting_search_results = False
        w.abort()
        self.stop_btn.setEnabled(False)
        self.progress_lbl.setText(self.tr("Interrompendo pesquisa..."))
        if self.log_output:
            self.log_output.append_log(
                self.tr(
                    "[PESQUISA] Interrupção solicitada. "
                    "Consultas ativas estão sendo encerradas."
                )
            )

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
        self._hosts_failed = 0
        self._hosts_done = 0
        self._hosts_total = len(hosts)
        self._search_generation += 1
        generation = self._search_generation
        self._accepting_search_results = True
        self.table.setRowCount(0)
        self._apply_results_filter()
        self.summary_lbl.setText(self.tr("Pesquisando..."))
        self.search_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.app_edit.setEnabled(False)
        self.browse_hosts_btn.setEnabled(False)
        self.progress.setVisible(True)
        self._stats_wrap.setVisible(True)
        self.ok_count_lbl.setVisible(True)
        self.fail_count_lbl.setVisible(True)
        self.progress_lbl.setVisible(True)
        self.progress.setMaximum(len(hosts))
        self.progress.setValue(0)
        self.progress.setFormat(f"%v / %m hosts")
        self._update_live_stats(0, 0, len(hosts), "")
        self.progress_lbl.setText(self.tr("Iniciando pesquisa..."))

        configured_workers = get_search_max_workers()
        effective_workers = min(configured_workers, len(hosts))
        self._worker = _AppSearchWorker(
            hosts,
            query,
            max_workers=effective_workers,
            generation=generation,
            timeout=REMOTE_REGISTRY_TIMEOUT_SECONDS,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.hitsFound.connect(self._on_hits_found)
        self._worker.finished_ok.connect(self._on_search_ok)
        self._worker.finished_aborted.connect(self._on_search_aborted)
        self._worker.finished_err.connect(self._on_search_err)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

        if self.log_output:
            self.log_output.append_log(
                self.tr(
                    f"[PESQUISA] Buscando '{query}' em {len(hosts)} host(s) "
                    f"({effective_workers} consultas simultâneas, "
                    f"timeout {int(REMOTE_REGISTRY_TIMEOUT_SECONDS)}s/host)..."
                )
            )

    def _update_live_stats(self, done: int, failed: int, total: int, host: str = "") -> None:
        """Atualiza contadores de sucesso/falha em tempo real."""
        ok = max(0, done - failed)
        self.ok_count_lbl.setText(self.tr(f"Sucesso: {ok}"))
        self.fail_count_lbl.setText(self.tr(f"Falharam: {failed}"))
        if host:
            self.progress_lbl.setText(
                self.tr(f"{done} de {total} consultados — último: {host}")
            )
        elif done > 0:
            self.progress_lbl.setText(self.tr(f"{done} de {total} consultados"))
        else:
            self.progress_lbl.setText(self.tr(f"0 de {total} consultados"))

    def _on_progress(
        self,
        generation: int,
        done: int,
        failed: int,
        total: int,
        host: str,
        _ok: bool,
        error_kind: str = "",
    ) -> None:
        if not self._ui_alive() or int(generation) != int(self._search_generation):
            return
        self._hosts_done = done
        self._hosts_failed = failed
        self._hosts_total = total
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(min(done, total))
        self._update_live_stats(done, failed, total, host)
        if host and not _ok and error_kind and self.log_output:
            kind_labels = {
                "auth": "falha de autenticação",
                "remote_registry": "Remote Registry/RPC indisponível",
                "unreachable": "host inacessível",
                "invalid_host": "host inválido",
                "timed_out": "consulta expirada (timeout)",
                "cancelled": "consulta cancelada",
                "internal_error": "erro interno na consulta",
            }
            label = kind_labels.get(error_kind, error_kind)
            self.log_output.append_log(
                self.tr(f"[PESQUISA] {host}: {label}")
            )
        if self._accepting_search_results:
            self._update_summary(final=False)

    def _on_worker_finished(self) -> None:
        if not self._ui_alive():
            return
        self.search_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.app_edit.setEnabled(True)
        self.browse_hosts_btn.setEnabled(True)

    def _on_search_err(self, generation: int, msg: str) -> None:
        if not self._ui_alive() or int(generation) != int(self._search_generation):
            return
        self._accepting_search_results = False
        self.progress.setVisible(False)
        self._stats_wrap.setVisible(True)
        self.ok_count_lbl.setVisible(True)
        self.fail_count_lbl.setVisible(True)
        self.progress_lbl.setVisible(True)
        self.progress_lbl.setText(self.tr(f"Falha: {msg}"))
        if self.log_output:
            self.log_output.append_log(self.tr(f"[PESQUISA] {msg}"))

    def _on_hits_found(self, generation: int, hits: list) -> None:
        """Exibe imediatamente as correspondências do host recém-consultado."""
        if not self._ui_alive() or not self._is_current_generation(generation) or not hits:
            return
        for hit in hits:
            if isinstance(hit, SearchHit):
                self._hits.append(hit)
                self._append_hit_row(hit)
        self._apply_results_filter()
        self._update_summary(final=False)

    def _on_search_ok(self, generation: int, query: str) -> None:
        if not self._ui_alive() or int(generation) != int(self._search_generation):
            return
        self._accepting_search_results = False
        self._active_query = query or self._active_query
        self.progress.setValue(self.progress.maximum())
        total = self._hosts_total or self.progress.maximum()
        failed = self._hosts_failed
        self._update_live_stats(total, failed, total, "")
        self.progress_lbl.setText(
            self.tr("Pesquisa concluída — ")
            + self.tr(f"{total} de {total} consultados")
        )
        self._update_summary(final=True)
        computers = {h.host.casefold() for h in self._hits}
        if self.log_output:
            self.log_output.append_log(
                self.tr(
                    f"[PESQUISA] Concluída: {len(computers)} computador(es) com app, "
                    f"{len(self._hits)} correspondência(s), "
                    f"{failed} host(s) falharam."
                )
            )

    def _on_search_aborted(self, generation: int, query: str) -> None:
        if not self._ui_alive() or int(generation) != int(self._search_generation):
            return
        self._accepting_search_results = False
        self._active_query = query or self._active_query
        done = self._hosts_done or self.progress.value()
        total = self._hosts_total or self.progress.maximum()
        failed = self._hosts_failed
        self._update_live_stats(done, failed, total, "")
        self.progress_lbl.setText(
            self.tr("Pesquisa interrompida — ")
            + self.tr(f"{done} de {total} consultados")
        )
        self._update_summary(final=True, interrupted=True)
        computers = {h.host.casefold() for h in self._hits}
        if self.log_output:
            self.log_output.append_log(
                self.tr(
                    f"[PESQUISA] Interrompida: {len(computers)} computador(es) com app, "
                    f"{len(self._hits)} correspondência(s) até o momento "
                    f"({done} de {total} hosts processados, {failed} falha(s)). "
                    "Consultas ativas foram encerradas."
                )
            )

    def _apply_results_filter(self) -> None:
        """Filtra a tabela de resultados (mesmo padrão do PsInfo: nome/editor/versão/tipo + computador)."""
        if not self._ui_alive():
            return
        q = (self.filter_edit.text() or "").strip().lower()
        total = self.table.rowCount()
        visible = 0
        for r in range(total):
            parts = []
            for c in range(5):  # Computador, Nome, Editor, Versão, Tipo
                it = self.table.item(r, c)
                parts.append(it.text() if it else "")
            text = " ".join(parts).lower()
            ok = (q in text) if q else True
            self.table.setRowHidden(r, not ok)
            if ok:
                visible += 1
        self.filter_count_lbl.setText(self.tr(f"{visible}/{total}") if total else "")

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
                        self.tr(
                            f"Nenhum computador com aplicativo correspondente a “{query}”."
                        )
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
            extras_now = resolve_uninstall_extras(app, self._current_extras())
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
        extras_manual = self._current_extras()
        for btn in list(self._trash_buttons):
            if sip.isdeleted(btn):
                continue
            app_obj = getattr(btn, "_installed_app", None)
            if isinstance(app_obj, InstalledApp):
                btn.setToolTip(
                    describe_uninstall(
                        app_obj, resolve_uninstall_extras(app_obj, extras_manual)
                    )
                )

    def _on_uninstall_clicked(self, hit: SearchHit) -> None:
        if not self._ui_alive():
            return
        manual = self._current_extras()
        extras = resolve_uninstall_extras(hit.app, manual)
        try:
            remote_cmd = build_uninstall_remote_cmd(hit.app, extras)
        except ValueError as exc:
            if self.log_output:
                self.log_output.append_log(self.tr(f"[PESQUISA] {exc}"))
            return

        if extras and not manual and self.log_output:
            self.log_output.append_log(
                self.tr(
                    f"[PESQUISA] Parametros do catálogo para {hit.app.display_name}: {extras}"
                )
            )

        self.uninstallRequested.emit(hit.host, remote_cmd, hit.app.display_line)
