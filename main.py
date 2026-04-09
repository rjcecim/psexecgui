import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget, QPushButton,
    QHBoxLayout, QCheckBox, QLabel, QTabBar, QStyle, QStyleOptionTab
)
from PyQt6.QtCore import QCoreApplication, Qt, QRect, QSize
from PyQt6.QtGui import QFont, QFontMetrics, QPainter, QColor, QPalette
from ui.widgets.selector import FileSelectorWidget
from ui.tabs.psexec import PsExecTab
from ui.tabs.msi import MsiTab
from ui.tabs.robocopy import RobocopyTab
from core.builder import CommandBuilder
from ui.widgets.preview import CommandPreviewWidget
from ui.widgets.log import LogOutputWidget
from core.executor import Executor
import subprocess
import re
from ui.tabs.powershell import PowerShellTab
from ui.tabs.cmd import CmdTab
from ui.tabs.psinfo import PsInfoTab
from ui.mica import enable_mica_for_widget
import datetime


from ui.style import ICON_FONT_PT

_MDL2_FONT = QFont("Segoe MDL2 Assets", ICON_FONT_PT)


class _Mdl2TabBar(QTabBar):
    """TabBar que desenha ícone (char Unicode) + texto; ícone em tabData(UserRole)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._icon_font = QFont("Segoe MDL2 Assets", ICON_FONT_PT)
        # Cada aba usa o tamanho do seu conteúdo (sem expandir igualmente), evitando texto cortado
        self.setExpanding(False)

    def tabSizeHint(self, index):
        icon = self.tabData(index) or ""
        text = self.tabText(index)
        # Reservar espaço para texto em negrito (aba selecionada) para não cortar
        text_w = self.fontMetrics().horizontalAdvance(text)
        f_bold = QFont(self.font())
        f_bold.setBold(True)
        text_w = max(text_w, QFontMetrics(f_bold).horizontalAdvance(text))
        icon_w = QFontMetrics(self._icon_font).horizontalAdvance(icon) + 4 if (icon and isinstance(icon, str)) else 0
        total_w = 20 + icon_w + text_w
        return QSize(max(60, total_w), super().tabSizeHint(index).height())

    def paintEvent(self, event):
        painter = QPainter(self)
        current = self.currentIndex()
        tab_font = self.font()
        tab_font_bold = QFont(tab_font)
        tab_font_bold.setBold(True)
        for i in range(self.count()):
            opt = QStyleOptionTab()
            self.initStyleOption(opt, i)
            rect = self.tabRect(i)
            icon_char = self.tabData(i)
            text = self.tabText(i)
            opt.text = ""  # nós desenhamos ícone + texto abaixo
            self.style().drawControl(QStyle.ControlElement.CE_TabBarTab, opt, painter, self)
            highlight = self.palette().color(QPalette.ColorRole.Highlight)
            is_selected = i == current
            text_font = tab_font_bold if is_selected else tab_font
            if icon_char and isinstance(icon_char, str):
                painter.setFont(self._icon_font)
                painter.setPen(highlight)
                icon_w = painter.fontMetrics().horizontalAdvance(icon_char)
                painter.drawText(rect.adjusted(8, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, icon_char)
                painter.setFont(text_font)
                painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
                painter.drawText(rect.adjusted(8 + icon_w + 4, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
            else:
                painter.setFont(text_font)
                painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
                painter.drawText(rect.adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)


def _action_button(icon_char: str, tooltip: str, parent=None):
    """Botão apenas com char Unicode (sem texto), tamanho fixo e bem proporcionado."""
    btn = QPushButton(icon_char, parent)
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFont(_MDL2_FONT)
    btn.setFixedSize(40, 40)
    btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    btn.setStyleSheet("""
        QPushButton {
            border: 1px solid palette(mid);
            border-radius: 6px;
            background: palette(button);
            color: palette(highlight);
            padding: 0;
            min-width: 40px;
            min-height: 40px;
        }
        QPushButton:hover {
            background: palette(light);
            border-color: palette(highlight);
        }
        QPushButton:pressed {
            background: palette(dark);
        }
        QPushButton:disabled {
            color: palette(mid);
            background: palette(button);
        }
    """)
    return btn

# Tradução futura: strings em português
# Classe principal da janela do aplicativo
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._updating_remote_cmd = False
        self._last_tab_widget = None
        self.setWindowTitle(self.tr("Instalador Remoto via PsExec"))
        central = QWidget()
        vbox = QVBoxLayout(central)
        vbox.setSpacing(0)  # Elementos bem próximos na vertical
        vbox.setContentsMargins(4, 4, 4, 4)
        
        # Seleção de arquivo
        self.file_selector = FileSelectorWidget(self)
        vbox.addWidget(self.file_selector)
        
        # Tabs (ícone = char Unicode em TabBar customizada)
        self.tabs = QTabWidget()
        self.tabs.setTabBar(_Mdl2TabBar(self.tabs))
        self.log_output = LogOutputWidget()
        self.psexec_tab = PsExecTab(log_output=self.log_output)
        self.psinfo_tab = None
        self.msi_tab = MsiTab()
        self.robocopy_tab = RobocopyTab()
        self.powershell_tab = PowerShellTab()
        self.cmd_tab = CmdTab()
        # \uE8AF = Network/Computer (Segoe MDL2 Assets)
        self.tabs.addTab(self.psexec_tab, self.tr("PsExec"))
        self.tabs.tabBar().setTabData(0, "\uE8AF")
        vbox.addWidget(self.tabs)
        
        # Preview do comando - posicionado imediatamente abaixo das abas
        self.command_preview = CommandPreviewWidget()
        vbox.addWidget(self.command_preview)
        
        # Botões executar/parar/reiniciar: só char Unicode, sem texto (tooltip para acessibilidade)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        # \uE768 = Play, \uE71A = Stop, \uE72C = Refresh (Segoe MDL2 Assets)
        self.run_button = _action_button("\uE768", self.tr("Executar"), self)
        self.stop_button = _action_button("\uE71A", self.tr("Parar"), self)
        self.stop_button.setEnabled(False)
        self.restart_button = _action_button("\uE72C", self.tr("Reiniciar"), self)
        button_layout.addWidget(self.run_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.restart_button)
        button_layout.setSpacing(4)
        vbox.addLayout(button_layout)
        
        # Log de saída - posicionado por último
        vbox.addWidget(self.log_output)
        
        self.setCentralWidget(central)
        self._apply_initial_geometry()
        
        # Instâncias auxiliares
        self.command_builder = CommandBuilder()
        self.executor = Executor()
        self._rustdesk_collecting = False
        self._rustdesk_out_lines = []
        self._rustdesk_err_lines = []
        
        # Conexões
        self.file_selector.fileSelected.connect(self.on_file_selected)
        self.psexec_tab.host_edit.textChanged.connect(self.update_command)
        self.psexec_tab.openPsInfoRequested.connect(self.open_psinfo_tab)
        self.psexec_tab.openRustDeskRequested.connect(self.on_rustdesk_clicked)
        self.psexec_tab.psexec_path_edit.textChanged.connect(self.update_command)
        self.psexec_tab.user_edit.textChanged.connect(self.update_command)
        self.psexec_tab.pass_edit.textChanged.connect(self.update_command)
        # Conexões dos checkboxes de elevação
        self.psexec_tab.flag_h.stateChanged.connect(self.update_command)
        self.psexec_tab.flag_s.stateChanged.connect(self.update_command)
        self.psexec_tab.flag_l.stateChanged.connect(self.update_command)
        self.psexec_tab.session_interactive.stateChanged.connect(self.update_command)
        self.psexec_tab.session_id_spin.valueChanged.connect(self.update_command)
        self.psexec_tab.priority_combo.currentTextChanged.connect(self.update_command)
        self.psexec_tab.affinity_edit.textChanged.connect(self.update_command)
        self.psexec_tab.group_combo.currentTextChanged.connect(self.update_command)
        self.psexec_tab.timeout_spin.valueChanged.connect(self.update_command)
        for cb in [self.psexec_tab.flag_d, self.psexec_tab.flag_e, self.psexec_tab.flag_c, self.psexec_tab.flag_f, self.psexec_tab.flag_v, self.psexec_tab.flag_accepteula, self.psexec_tab.flag_nobanner]:
            cb.stateChanged.connect(self.update_command)
        self.psexec_tab.extra_args.textChanged.connect(self.update_command)
        self.msi_tab.action_combo.currentTextChanged.connect(self.update_command)
        self.msi_tab.interface_combo.currentTextChanged.connect(self.update_command)
        self.msi_tab.restart_combo.currentTextChanged.connect(self.update_command)
        self.msi_tab.log_checkbox.stateChanged.connect(self.update_command)
        self.msi_tab.log_file_edit.textChanged.connect(self.update_command)
        self.msi_tab.repair_spin.textChanged.connect(self.update_command)
        self.msi_tab.update_edit.textChanged.connect(self.update_command)
        # Conexões do Robocopy
        self.robocopy_tab.dest_edit.textChanged.connect(self.update_command)
        for cb in self.robocopy_tab.switches:
            cb.stateChanged.connect(self.update_command)
        self.psexec_tab.remote_cmd_edit.textChanged.connect(self.on_remote_cmd_edit_changed)
        self.run_button.clicked.connect(self.on_run)
        self.stop_button.clicked.connect(self.on_stop)
        self.restart_button.clicked.connect(self.on_restart)
        self.executor.outputReceived.connect(self.log_output.append_log)
        self.executor.errorReceived.connect(self.log_output.append_log)
        self.executor.finished.connect(self.on_process_finished)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        
        # Estado inicial: não adiciona a aba MSI nem Robocopy
        self.msi_tab_index = None
        self.robocopy_tab_index = None
        self.update_command()
        self._update_psinfo_mode_ui()
        self._last_tab_widget = self.tabs.currentWidget()

    def _escape_quotes(self, s: str) -> str:
        return (s or "").replace('"', '\\"')

    def _quote_if_needed(self, s: str) -> str:
        s = (s or "").strip()
        if not s:
            return s
        return f'"{s}"' if " " in s else s

    def _build_psexec_exe(self) -> str:
        p = (self.psexec_tab.psexec_path_edit.text() or "").strip()
        if p:
            p = os.path.normpath(p.replace('"', "").replace("'", ""))
            return self._quote_if_needed(p)
        return "PsExec.exe"

    def on_rustdesk_clicked(self) -> None:
        """
        Fluxo:
        1) Executa remoto: rustdesk.exe --get-id (via PsExec com -h -s)
        2) Extrai ID do stdout
        3) Executa local: rustdesk.exe --id <ID>
        """
        host = (self.psexec_tab.host_edit.text() or "").strip().strip("\\")
        if not host:
            ph = self.psexec_tab.host_edit.placeholderText()
            self.log_output.append_log(self.tr(f"[RUSTDESK] Por favor, insira um host ({ph})."))
            return

        # Não interferir em execuções internas em andamento (robocopy etc.)
        if getattr(self.executor, "future", None) is not None or getattr(self.executor, "process", None) is not None:
            self.log_output.append_log(self.tr("[RUSTDESK] Aguarde a execução atual terminar antes de usar RustDesk."))
            return

        if self._rustdesk_collecting:
            return

        self._rustdesk_collecting = True
        self._rustdesk_out_lines = []
        self._rustdesk_err_lines = []
        self._rustdesk_last_path = None

        psexec_exe = self._build_psexec_exe()
        user = (self.psexec_tab.user_edit.text() or "").strip()
        password = (self.psexec_tab.pass_edit.text() or "").strip()

        creds = ""
        if user:
            creds += f' -u "{self._escape_quotes(user)}"'
        if password:
            creds += f' -p "{self._escape_quotes(password)}"'

        # Forçar elevação para coletar ID de forma mais consistente
        forced_flags = " -h -s -accepteula -nobanner"

        rustdesk_remote_paths = [
            r"C:\Program Files\RustDesk\rustdesk.exe",
            r"C:\Program Files (x86)\RustDesk\rustdesk.exe",
        ]

        def build_cmd(remote_path: str) -> str:
            # Formato solicitado:
            # PsExec.exe \\HOST -h -s "C:\Program Files\RustDesk\rustdesk.exe" --get-id
            return f'{psexec_exe} \\\\{host}{creds}{forced_flags} "{remote_path}" --get-id'

        cmd = build_cmd(rustdesk_remote_paths[0])

        self.log_output.append_log(self.tr(f"[RUSTDESK] Conectando em {host} e coletando ID..."))

        def on_out(line: str) -> None:
            if line is None:
                return
            t = str(line).strip()
            if t:
                self._rustdesk_out_lines.append(t)

        def on_err(line: str) -> None:
            if line is None:
                return
            t = str(line).strip()
            if t:
                self._rustdesk_err_lines.append(t)

        def on_done(exit_code: int) -> None:
            # desconectar handlers temporários
            try:
                self.executor.outputReceived.disconnect(on_out)
            except Exception:
                pass
            try:
                self.executor.errorReceived.disconnect(on_err)
            except Exception:
                pass
            try:
                self.executor.finished.disconnect(on_done)
            except Exception:
                pass

            self._rustdesk_collecting = False

            out_text = "\n".join(self._rustdesk_out_lines).strip()
            err_text = "\n".join(self._rustdesk_err_lines).strip()

            # 1) Tenta extrair ID do stdout (geralmente vem só o número)
            rust_id = ""
            for ln in self._rustdesk_out_lines:
                cand = re.sub(r"\D", "", ln)
                if len(cand) >= 6:
                    rust_id = cand
                    break

            # 2) Se não achou ID, e parece "arquivo não encontrado", tentar o segundo caminho e repetir 1 vez
            not_found_markers = [
                "could not be found",
                "não foi possível encontrar",
                "nao foi possivel encontrar",
                "não foi encontrado",
                "nao foi encontrado",
                "o sistema não pode encontrar",
                "o sistema nao pode encontrar",
            ]
            is_not_found = any(m in (err_text.lower() if err_text else "") for m in not_found_markers)

            if not rust_id and is_not_found and getattr(self, "_rustdesk_last_path", None) != rustdesk_remote_paths[1]:
                # segunda tentativa
                self._rustdesk_last_path = rustdesk_remote_paths[1]
                self._rustdesk_collecting = True
                self._rustdesk_out_lines = []
                self._rustdesk_err_lines = []

                self.log_output.append_log(self.tr("[RUSTDESK] Tentando caminho alternativo do RustDesk no host..."))

                self.executor.outputReceived.connect(on_out)
                self.executor.errorReceived.connect(on_err)
                self.executor.finished.connect(on_done)
                self.executor.run(build_cmd(rustdesk_remote_paths[1]))
                return

            if not rust_id:
                if exit_code != 0 and ("couldn't access" in err_text.lower() or "couldnt access" in err_text.lower()):
                    # PsExec não conseguiu acessar o host
                    self.log_output.append_log(self.tr("[RUSTDESK] ERRO: Não foi possível conectar ao host (rede/RPC/credenciais)."))
                    if err_text:
                        self.log_output.append_log(self.tr(f"[RUSTDESK] Detalhes: {err_text}"))
                elif is_not_found:
                    self.log_output.append_log(self.tr("[RUSTDESK] ERRO: RustDesk não encontrado no host."))
                elif err_text:
                    self.log_output.append_log(self.tr(f"[RUSTDESK] ERRO: {err_text}"))
                else:
                    self.log_output.append_log(self.tr("[RUSTDESK] ERRO: Não foi possível obter o ID do RustDesk."))
                return

            self.log_output.append_log(self.tr(f"[RUSTDESK] ID detectado: {rust_id}"))

            # Abrir RustDesk local com o ID
            local_candidates = []
            local_candidates.append(r"C:\PSTools\rustdesk.exe")
            pf = os.environ.get("ProgramFiles", r"C:\Program Files")
            pfx86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
            local_candidates.append(os.path.join(pf, "RustDesk", "rustdesk.exe"))
            local_candidates.append(os.path.join(pfx86, "RustDesk", "rustdesk.exe"))

            local_exe = None
            for c in local_candidates:
                if os.path.isfile(c):
                    local_exe = c
                    break
            if local_exe is None:
                local_exe = "rustdesk.exe"

            try:
                # Sempre usar o ID detectado nesta execução
                args = [local_exe, "--connect", rust_id]
                subprocess.Popen(args)
                self.log_output.append_log(self.tr(f"[RUSTDESK] Executando local: {local_exe} --connect {rust_id}"))
                self.log_output.append_log(self.tr("[RUSTDESK] Abrindo RustDesk..."))
            except FileNotFoundError:
                self.log_output.append_log(self.tr("[RUSTDESK] ERRO: RustDesk não encontrado no PC local."))
            except Exception as exc:
                self.log_output.append_log(self.tr(f"[RUSTDESK] ERRO ao abrir RustDesk local: {exc}"))

        self._rustdesk_last_path = rustdesk_remote_paths[0]
        self.executor.outputReceived.connect(on_out)
        self.executor.errorReceived.connect(on_err)
        self.executor.finished.connect(on_done)
        self.executor.run(cmd)

        # Conexões das abas PowerShellTab
        self.powershell_tab.noprofile_checkbox.stateChanged.connect(self.update_command)
        self.powershell_tab.noexit_checkbox.stateChanged.connect(self.update_command)
        self.powershell_tab.execpol_combo.currentTextChanged.connect(self.update_command)
        self.powershell_tab.winstyle_combo.currentTextChanged.connect(self.update_command)
        self.powershell_tab.command_edit.textChanged.connect(self.update_command)
        self.powershell_tab.encoded_edit.textChanged.connect(self.update_command)
        # Conexões das abas CmdTab
        self.cmd_tab.c_checkbox.stateChanged.connect(self.update_command)
        self.cmd_tab.k_checkbox.stateChanged.connect(self.update_command)
        self.cmd_tab.q_checkbox.stateChanged.connect(self.update_command)
        self.cmd_tab.d_checkbox.stateChanged.connect(self.update_command)
        self.cmd_tab.s_checkbox.stateChanged.connect(self.update_command)
        self.cmd_tab.command_edit.textChanged.connect(self.update_command)

    def open_psinfo_tab(self) -> None:
        """
        Cria a aba PsInfo sob demanda e foca nela.
        """
        host = self.psexec_tab.host_edit.text().strip()
        if not host:
            self.log_output.append_log(self.tr("[PSINFO] Preencha o Host remoto antes de abrir o PsInfo."))
            return

        # Se já existe, apenas focar
        if self.psinfo_tab is not None:
            idx = self.tabs.indexOf(self.psinfo_tab)
            if idx != -1:
                self.tabs.setCurrentIndex(idx)
                # Sempre re-executar para o host atual
                self.psinfo_tab.run_psinfo()
                self._update_psinfo_mode_ui()
                return

        self.psinfo_tab = PsInfoTab(log_output=self.log_output, host_source=self.psexec_tab.host_edit)
        # PsInfo deve ser sempre a última aba
        self.tabs.addTab(self.psinfo_tab, self.tr("PsInfo"))
        psinfo_idx = self.tabs.indexOf(self.psinfo_tab)
        self.tabs.tabBar().setTabData(psinfo_idx, "\uE946")  # Info
        self.tabs.setCurrentIndex(psinfo_idx)
        self.psinfo_tab.run_psinfo()
        self._update_psinfo_mode_ui()

    def _on_tab_changed(self, _index: int) -> None:
        # Se o usuário saiu da aba PsInfo, encerrá-la (remover a aba)
        if self.psinfo_tab is not None:
            prev = self._last_tab_widget
            current = self.tabs.currentWidget()
            if prev == self.psinfo_tab and current != self.psinfo_tab:
                idx = self.tabs.indexOf(self.psinfo_tab)
                if idx != -1:
                    self.tabs.removeTab(idx)
                self.psinfo_tab.deleteLater()
                self.psinfo_tab = None
        self._update_psinfo_mode_ui()
        self._last_tab_widget = self.tabs.currentWidget()

    def _update_psinfo_mode_ui(self) -> None:
        """
        A aba PsInfo é uma tela de inventário; não precisa do preview do comando e log.
        """
        is_psinfo = self.psinfo_tab is not None and self.tabs.currentWidget() == self.psinfo_tab
        self.command_preview.setVisible(not is_psinfo)
        self.log_output.setVisible(not is_psinfo)
        self.run_button.setVisible(not is_psinfo)
        self.stop_button.setVisible(not is_psinfo)
        self.restart_button.setVisible(not is_psinfo)

    def _apply_initial_geometry(self):
        """
        Define um tamanho inicial dinâmico baseado no conteúdo (sizeHint),
        com limites seguros pela tela. Isso permite uma janela mais estreita
        quando os conteúdos (ex: Flags) conseguem quebrar linha.
        """
        screen = QApplication.primaryScreen()
        if not screen:
            self.resize(980, 700)
            return

        avail = screen.availableGeometry()
        # Pede ao Qt o tamanho ideal do layout atual
        self.centralWidget().adjustSize()
        self.adjustSize()
        hint = self.sizeHint()

        min_w = 760
        min_h = 620
        max_w = int(avail.width() * 0.92)
        max_h = int(avail.height() * 0.92)

        w = max(min_w, hint.width())
        h = max(min_h, hint.height())
        w = min(w, max_w)
        h = min(h, max_h)

        self.resize(w, h)
        rect = self.frameGeometry()
        rect.moveCenter(avail.center())
        self.move(rect.topLeft())

    def on_file_selected(self, selection):
        # selection: {'mode': 'file'|'folder', 'file': caminho, 'folder': caminho ou None}
        if isinstance(selection, dict):
            self.command_builder.set_file_selection(selection)
            file_path = selection['file']
            is_msi = file_path.lower().endswith('.msi')
            is_exe = file_path.lower().endswith('.exe')
        else:
            # Compatibilidade retroativa
            self.command_builder.set_file({'mode': 'file', 'file': selection, 'folder': None})
            file_path = selection
            is_msi = file_path.lower().endswith('.msi')
            is_exe = file_path.lower().endswith('.exe')
        # Desabilita -c e -f para msi, ps1, bat
        ext = file_path.lower().split('.')[-1] if '.' in file_path else ''
        if ext in ['msi', 'ps1', 'bat']:
            self.psexec_tab.flag_c.setChecked(False)
            self.psexec_tab.flag_c.setEnabled(False)
            self.psexec_tab.flag_f.setChecked(False)
            self.psexec_tab.flag_f.setEnabled(False)
        else:
            self.psexec_tab.flag_c.setEnabled(True)
            self.psexec_tab.flag_f.setEnabled(True)
        # NOVO: Preencher campo -File da aba PowerShell automaticamente
        self.update_tab_visibility(is_msi, is_exe)
        self.update_command()

    def should_enable_robocopy(self):
        selected_file = getattr(self.file_selector, 'selected_file', None)
        if not selected_file:
            return False
        ext = selected_file.lower().split('.')[-1] if '.' in selected_file else ''
        if ext == 'exe':
            return False
        # CORREÇÃO: Só desabilitar robocopy se houver comando remoto manual
        # Não desabilitar se houver apenas parâmetros da aba CMD ou PowerShell
        remote_cmd = self.psexec_tab.remote_cmd_edit.text().strip()
        if remote_cmd and remote_cmd != 'Comando gerado automaticamente':
            # Verificar se é realmente um comando manual ou apenas parâmetros de aba
            # Se o comando contém apenas parâmetros como cmd, powershell, etc., não desabilitar
            if remote_cmd.lower() in ['cmd', 'cmd.exe', 'powershell', 'powershell.exe']:
                return True
            # Se contém outros comandos, desabilitar robocopy
            return False
        return True

    def update_tab_visibility(self, is_msi, is_exe):
        """Atualiza a visibilidade das abas mantendo a ordem: PsExec, MSI, PowerShell, CMD, Robocopy, (PsInfo opcional por último)"""
        robocopy_enabled = self.should_enable_robocopy()
        selected_file = self.file_selector.selected_file if hasattr(self.file_selector, 'selected_file') else None
        ext = selected_file.lower().split('.')[-1] if selected_file and '.' in selected_file else ''
        remote_cmd = self.psexec_tab.remote_cmd_edit.text().strip().lower()
        show_powershell_tab = False
        show_cmd_tab = False
        powershell_by_file = False
        cmd_by_file = False
        # Lógica para exibir abas extras
        if ext == 'ps1':
            show_powershell_tab = True
            powershell_by_file = True
        if ext == 'bat':
            show_cmd_tab = True
            cmd_by_file = True
        # Se comando remoto for powershell ou cmd, mostrar aba correspondente
        if remote_cmd in ['powershell', 'powershell.exe']:
            show_powershell_tab = True
            powershell_by_file = False
        if remote_cmd in ['cmd', 'cmd.exe']:
            show_cmd_tab = True
            cmd_by_file = False
        # Remover abas dinâmicas, preservando PsExec e (se existir) PsInfo
        psinfo_widget = self.psinfo_tab
        for i in range(self.tabs.count() - 1, -1, -1):
            w = self.tabs.widget(i)
            if w is self.psexec_tab:
                continue
            if psinfo_widget is not None and w is psinfo_widget:
                continue
            self.tabs.removeTab(i)

        # Índice onde os tabs dinâmicos serão inseridos (antes do PsInfo, se ele existir)
        insert_at = self.tabs.count()
        if psinfo_widget is not None:
            idx = self.tabs.indexOf(psinfo_widget)
            if idx != -1:
                insert_at = idx

        def _insert_tab(widget, title: str, icon_char: str) -> None:
            nonlocal insert_at
            self.tabs.insertTab(insert_at, widget, title)
            self.tabs.tabBar().setTabData(insert_at, icon_char)
            insert_at += 1

        # Adiciona MSI / PowerShell / CMD / Robocopy (ícone = char Unicode)
        # \uE8A5 = Package/MSI, \uE756 = PowerShell, \uE7ED = CMD/Console, \uE8B7 = Copy/Robocopy
        if is_msi:
            _insert_tab(self.msi_tab, self.tr("MSI"), "\uE8A5")
        if show_powershell_tab:
            _insert_tab(self.powershell_tab, self.tr("PowerShell"), "\uE756")
            self.powershell_tab.set_command_fields_enabled(not powershell_by_file)
        if show_cmd_tab:
            _insert_tab(self.cmd_tab, self.tr("CMD"), "\uE7ED")
            self.cmd_tab.set_command_field_enabled(not cmd_by_file)
        if robocopy_enabled:
            _insert_tab(self.robocopy_tab, self.tr("Robocopy"), "\uE8B7")

    def build_command_for_execution(self):
        """
        Centraliza a lógica de montagem do comando para execução, preview e log.
        Escolhe o método correto do CommandBuilder conforme a aba ativa e contexto.
        """
        selection = getattr(self.file_selector, 'selected_file', None)
        selection_mode = getattr(self.file_selector, 'selection_mode', None)
        remote_cmd = self.psexec_tab.remote_cmd_edit.text().strip().lower()
        
        # Se há arquivo selecionado, verificar se deve usar comandos especiais
        if selection:
            ext = selection.lower().split('.')[-1] if '.' in selection else ''
            
            # CORREÇÃO: Sempre usar build_full_command se robocopy estiver habilitado
            # Isso garante que o robocopy seja incluído mesmo com parâmetros da aba CMD ou PowerShell
            if self.should_enable_robocopy():
                return self.command_builder.build_full_command()
            
            # Se robocopy não está habilitado, usar comandos específicos
            # Se é arquivo .bat e aba CMD está ativa, usar _build_psexec_bat_script
            if ext == 'bat' and self.tabs.currentWidget() == self.cmd_tab:
                return self.command_builder._build_psexec_bat_script()
            
            # Se é arquivo .ps1, usar _build_psexec_ps_script
            if ext == 'ps1':
                return self.command_builder._build_psexec_ps_script()
            
            # Caso contrário, usar build_psexec
            return self.command_builder.build_psexec()
        
        # Se não há arquivo selecionado (comando manual)
        # Se comando remoto powershell
        if remote_cmd in ['powershell', 'powershell.exe']:
            return self.command_builder._build_psexec_ps_script()
        # Se comando remoto cmd
        if remote_cmd in ['cmd', 'cmd.exe']:
            return self.command_builder._build_psexec_bat_script()
        # Se aba CMD ativa
        if self.tabs.currentWidget() == self.cmd_tab:
            return self.command_builder._build_psexec_bat_script()
        # Se aba PowerShell ativa
        if self.tabs.currentWidget() == self.powershell_tab:
            return self.command_builder._build_psexec_ps_script()
        # Caso padrão
        return self.command_builder.build_psexec()

    def update_command(self):
        from PyQt6.QtWidgets import QApplication
        # Parâmetros MSI
        msi_params = {
            'enable': True,  # Sempre habilitado se for MSI
            'action': self.msi_tab.action_combo.currentText(),
            'interface': self.msi_tab.interface_combo.currentText(),
            'restart': self.msi_tab.restart_combo.currentText(),
            'log': self.msi_tab.log_checkbox.isChecked(),
            'log_file': self.msi_tab.log_file_edit.text(),
            'repair': self.msi_tab.repair_spin.text(),
            'update': self.msi_tab.update_edit.text(),
        }
        self.command_builder.set_msi_params(msi_params)

        # Recupera seleção do FileSelectorWidget
        selection = getattr(self.file_selector, 'selected_file', None)
        selection_folder = getattr(self.file_selector, 'selected_folder', None)
        selection_mode = getattr(self.file_selector, 'selection_mode', None)
        # Monta dict de seleção
        if selection_mode == 'folder' and selection and selection_folder:
            file_selection = {'mode': 'folder', 'file': selection, 'folder': selection_folder}
        elif selection:
            file_selection = {'mode': 'file', 'file': selection, 'folder': None}
        else:
            file_selection = None
        robocopy_enabled = self.should_enable_robocopy()
        # NOVO: Detectar extensão
        ext = selection.lower().split('.')[-1] if selection and '.' in selection else ''
        remote_cmd = self.psexec_tab.remote_cmd_edit.text().strip().lower()
        # --- CORREÇÃO: Sempre preservar parâmetros da aba PowerShell se ela existir ---
        if hasattr(self, 'powershell_tab') and self.powershell_tab:
            self.command_builder.set_powershell_params(self.powershell_tab.get_params())
        else:
            self.command_builder.set_powershell_params({})
        # --- CORREÇÃO: Sempre preservar parâmetros da aba CMD se ela existir ---
        if hasattr(self, 'cmd_tab') and self.cmd_tab:
            self.command_builder.set_cmd_params(self.cmd_tab.get_params())
        else:
            self.command_builder.set_cmd_params({})
        if file_selection:
            self.command_builder.set_file_selection(file_selection)
            self._updating_remote_cmd = True
            self.psexec_tab.remote_cmd_edit.setReadOnly(True)
            self.psexec_tab.remote_cmd_edit.setText('Comando gerado automaticamente')
            QApplication.processEvents()
            self.psexec_tab.remote_cmd_edit.repaint()
            self._updating_remote_cmd = False
            robocopy_dest = self.robocopy_tab.dest_edit.text() or 'C:\\Temp'
            psexec_params = {
                'host': self.psexec_tab.host_edit.text(),
                'psexec_path': self.psexec_tab.psexec_path_edit.text(),
                'remote_cmd': self.psexec_tab.remote_cmd_edit.text(),
                'user': self.psexec_tab.user_edit.text(),
                'password': self.psexec_tab.pass_edit.text(),
                '-h': self.psexec_tab.flag_h.isChecked(),
                '-s': self.psexec_tab.flag_s.isChecked(),
                '-l': self.psexec_tab.flag_l.isChecked(),
                'session_interactive': self.psexec_tab.session_interactive.isChecked(),
                'session_id': self.psexec_tab.session_id_spin.value(),
                'priority': self.psexec_tab.priority_combo.currentData() or "",
                'affinity': self.psexec_tab.affinity_edit.text(),
                'group': self.psexec_tab.group_combo.currentText(),
                'timeout': self.psexec_tab.timeout_spin.value(),
                '-d': self.psexec_tab.flag_d.isChecked(),
                '-e': self.psexec_tab.flag_e.isChecked(),
                '-c': self.psexec_tab.flag_c.isChecked(),
                '-f': self.psexec_tab.flag_f.isChecked(),
                '-v': self.psexec_tab.flag_v.isChecked(),
                '-accepteula': self.psexec_tab.flag_accepteula.isChecked(),
                '-nobanner': self.psexec_tab.flag_nobanner.isChecked(),
                'extra_args': self.psexec_tab.extra_args.text(),
            }
            robocopy_params = self.robocopy_tab.get_params() if robocopy_enabled else None
            self.command_builder.set_robocopy_params(robocopy_params)
            self.command_builder.set_psexec_params(psexec_params)
            # Atualizar preview SEMPRE usando build_command_for_execution
            command = self.build_command_for_execution()
            self.command_preview.set_command(command)
        else:
            self.psexec_tab.remote_cmd_edit.setReadOnly(False)
            psexec_params = {
                'host': self.psexec_tab.host_edit.text(),
                'psexec_path': self.psexec_tab.psexec_path_edit.text(),
                'remote_cmd': self.psexec_tab.remote_cmd_edit.text(),
                'user': self.psexec_tab.user_edit.text(),
                'password': self.psexec_tab.pass_edit.text(),
                '-h': self.psexec_tab.flag_h.isChecked(),
                '-s': self.psexec_tab.flag_s.isChecked(),
                '-l': self.psexec_tab.flag_l.isChecked(),
                'session_interactive': self.psexec_tab.session_interactive.isChecked(),
                'session_id': self.psexec_tab.session_id_spin.value(),
                'priority': self.psexec_tab.priority_combo.currentData() or "",
                'affinity': self.psexec_tab.affinity_edit.text(),
                'group': self.psexec_tab.group_combo.currentText(),
                'timeout': self.psexec_tab.timeout_spin.value(),
                '-d': self.psexec_tab.flag_d.isChecked(),
                '-e': self.psexec_tab.flag_e.isChecked(),
                '-c': self.psexec_tab.flag_c.isChecked(),
                '-f': self.psexec_tab.flag_f.isChecked(),
                '-v': self.psexec_tab.flag_v.isChecked(),
                '-accepteula': self.psexec_tab.flag_accepteula.isChecked(),
                '-nobanner': self.psexec_tab.flag_nobanner.isChecked(),
                'extra_args': self.psexec_tab.extra_args.text(),
            }
            self.command_builder.set_psexec_params(psexec_params)
            self.command_builder.set_robocopy_params(None)
            # Atualizar preview SEMPRE usando build_command_for_execution
            command = self.build_command_for_execution()
            self.command_preview.set_command(command)

    def log_to_file(self, text: str):
        """
        Salva uma linha de log no arquivo 'exec_history.log' na pasta do app ou do executável.
        Cria o arquivo se não existir, ou anexa se já existir.
        """
        import sys
        if getattr(sys, 'frozen', False):
            # Executável empacotado (PyInstaller, etc)
            app_dir = os.path.dirname(sys.executable)
        else:
            # Execução normal (script .py)
            app_dir = os.path.dirname(os.path.abspath(__file__))
        log_path = os.path.join(app_dir, 'exec_history.log')
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {text}\n")

    def on_run(self):
        full_command = self.build_command_for_execution()
        self.log_output.clear_log()
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.log_output.append_log(f"[DEBUG] Comando completo: {full_command}")
        # Salva no log de arquivo
        self.log_to_file(full_command)
        import subprocess
        if '\n' in full_command:
            robocopy_cmd, psexec_cmd = full_command.split('\n', 1)
            def run_psexec_if_success(exit_code):
                self.executor.finished.disconnect(run_psexec_if_success)
                # Robocopy: 0 = nada copiado, 1 = arquivos copiados com sucesso, 2 = arquivos extras
                # Códigos 0 e 1 são sucesso; 2 também é aceitável (cópia ok, só há extras no destino)
                robocopy_ok = exit_code in (0, 1, 2)
                if robocopy_ok and psexec_cmd:
                    # CORREÇÃO: Executar PsExec diretamente no cmd, não dentro de PowerShell
                    subprocess.Popen(f'start cmd /k {psexec_cmd}', shell=True)
                    self.log_output.append_log(self.tr("Comando executado em terminal externo."))
                self.run_button.setEnabled(True)
                self.stop_button.setEnabled(False)
            self.executor.finished.connect(run_psexec_if_success)
            self.executor.run(robocopy_cmd)
            return
        psexec_cmd = full_command
        if psexec_cmd:
            # CORREÇÃO: Executar PsExec diretamente no cmd, não dentro de PowerShell
            subprocess.Popen(f'start cmd /k {psexec_cmd}', shell=True)
            self.log_output.append_log(self.tr("Comando executado em terminal externo."))
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def on_stop(self):
        self.executor.stop()
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def on_process_finished(self, exit_code):
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.log_output.append_log(self.tr(f"Processo finalizado com código {exit_code}"))

    def on_remote_cmd_changed(self, text):
        # Evita loop de atualização
        if getattr(self, '_updating_remote_cmd', False):
            return
        # Desabilita o botão de browser se o campo de comando remoto não estiver vazio
        self.file_selector.file_button.setEnabled(text.strip() == "")
        self.file_selector.folder_button.setEnabled(text.strip() == "")

    def on_remote_cmd_edit_changed(self, text):
        selected_file = self.file_selector.selected_file
        is_msi = selected_file and selected_file.lower().endswith('.msi')
        is_exe = selected_file and selected_file.lower().endswith('.exe')
        # Não há mais checkbox manual, apenas atualizar abas e comando
        self.update_tab_visibility(is_msi, is_exe)
        self.update_command()

    def on_restart(self):
        """Reinicia o aplicativo completamente."""
        import os
        import sys
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def closeEvent(self, event):
        self.executor.stop()
        # Se o executor tiver método shutdown (ThreadPoolExecutor), finalize-o corretamente
        if hasattr(self.executor, 'executor') and hasattr(self.executor.executor, 'shutdown'):
            try:
                self.executor.executor.shutdown(wait=False)
            except Exception:
                pass
        super().closeEvent(event)

if __name__ == "__main__":
    import traceback
    class StreamToLog:
        def __init__(self, log_func):
            self.log_func = log_func
        def write(self, msg):
            msg = str(msg)
            if msg and not msg.isspace():
                self.log_func(msg.rstrip())
        def flush(self):
            pass
    app = QApplication(sys.argv)
    # Padrão global de densidade/tamanho dos widgets (sutil)
    from ui.style import apply_ui_defaults
    apply_ui_defaults(app)
    QCoreApplication.setApplicationName("Instalador Remoto PsExec")
    window = MainWindow()
    # Tenta habilitar efeito Mica / backdrop do Windows 11
    enable_mica_for_widget(window)
    # Redireciona stdout/stderr para o log interno
    sys.stdout = StreamToLog(window.log_output.append_log)
    sys.stderr = StreamToLog(window.log_output.append_log)
    # Handler global para exceções não capturadas
    def excepthook(type, value, tb):
        lines = traceback.format_exception(type, value, tb)
        window.log_output.append_log(''.join(lines))
    sys.excepthook = excepthook
    window.show()
    sys.exit(app.exec()) 