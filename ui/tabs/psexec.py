from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLineEdit, QComboBox, QSpinBox,
    QCheckBox, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QSizePolicy, QToolButton
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal
from utils.api import get_processor_groups, get_processor_count
from ui.style import ICON_FONT_PT, CARD_GRID_VERTICAL_SPACING
from utils.validator import AffinityValidator
from ui.widgets.card import CardWidget
from ui.widgets.flow import FlowLayout
import os


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("fieldLabel")
    lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    # Mantém alinhado com as outras abas (padrão antigo ~120)
    lbl.setMinimumWidth(120)
    palette = lbl.palette()
    # opacidade reduzida via stylesheet
    lbl.setStyleSheet("QLabel#fieldLabel { color: palette(windowText); opacity: 0.75; }")
    return lbl


def _icon_button(icon_char: str, tooltip: str = "", size: int = 32) -> QPushButton:
    btn = QPushButton(icon_char)
    font = QFont("Segoe MDL2 Assets", ICON_FONT_PT)
    btn.setFont(font)
    btn.setFixedSize(size, size)
    btn.setToolTip(tooltip)
    btn.setStyleSheet("""
        QPushButton {
            border: 1px solid palette(mid);
            border-radius: 4px;
            background: palette(button);
            color: palette(highlight);
            padding: 0;
        }
        QPushButton:hover { background: palette(light); }
        QPushButton:pressed { background: palette(dark); }
        QPushButton:disabled { color: palette(mid); }
    """)
    return btn


def _add_row(grid: QGridLayout, row: int, label_text: str, widget: QWidget):
    """Adiciona label + widget em uma linha do grid."""
    lbl = _make_label(label_text)
    grid.addWidget(lbl, row, 0, Qt.AlignmentFlag.AlignVCenter)
    grid.addWidget(widget, row, 1, Qt.AlignmentFlag.AlignVCenter)


def _grid_in_card(card: CardWidget) -> QGridLayout:
    grid = QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(CARD_GRID_VERTICAL_SPACING)
    grid.setColumnStretch(1, 1)
    card.content_layout.addLayout(grid)
    return grid


def _line_edit_with_clear_icon(password: bool = False):
    """
    Container com QLineEdit e ícone de remover à direita.
    Retorna (container, line_edit). O ícone só aparece quando há texto.
    """
    container = QWidget()
    container.setStyleSheet("""
        QWidget#AuthField {
            border: 1px solid palette(mid);
            border-radius: 4px;
            background: palette(base);
        }
        QWidget#AuthField:focus-within { border-color: palette(highlight); }
    """)
    container.setObjectName("AuthField")
    layout = QHBoxLayout(container)
    layout.setContentsMargins(4, 2, 4, 2)
    layout.setSpacing(4)

    line_edit = QLineEdit()
    line_edit.setStyleSheet("border: none; background: transparent; padding: 0 28px 0 0;")
    line_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    clear_btn = QToolButton()
    clear_btn.setText("\uE711")
    clear_btn.setFont(QFont("Segoe MDL2 Assets", 10))
    clear_btn.setFixedSize(22, 22)
    clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    clear_btn.setToolTip("Limpar")
    clear_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    clear_btn.setStyleSheet("""
        QToolButton { border: none; background: transparent; color: palette(highlight); }
        QToolButton:hover { background: palette(light); border-radius: 11px; }
        QToolButton:pressed { background: palette(dark); }
    """)
    clear_btn.hide()

    def on_text_changed(text):
        clear_btn.setVisible(bool(text.strip()))

    def on_clear():
        line_edit.clear()
        line_edit.setFocus()

    line_edit.textChanged.connect(on_text_changed)
    clear_btn.clicked.connect(on_clear)

    layout.addWidget(line_edit)
    layout.addWidget(clear_btn)
    return container, line_edit


# ── tab principal ─────────────────────────────────────────────────────────────

class PsExecTab(QWidget):
    openPsInfoRequested = pyqtSignal()
    openRustDeskRequested = pyqtSignal()

    def __init__(self, parent=None, log_output=None):
        super().__init__(parent)
        self.log_output = log_output

        # Layout direto na aba (sem barra de rolagem — todos os cards visíveis)
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(3)

        # ── Card 1 — Conexão ─────────────────────────────────────────────────
        card1 = CardWidget("\uEA18", self.tr("Conexão"))
        g1 = _grid_in_card(card1)

        # PsExec.exe
        psexec_row = QHBoxLayout()
        psexec_row.setSpacing(4)
        psexec_row.setContentsMargins(0, 0, 0, 0)
        self.psexec_path_edit = QLineEdit()
        self.psexec_path_edit.setPlaceholderText(
            self.tr("Caminho para PsExec.exe (deixe vazio para usar PATH)")
        )
        self.psexec_path_edit.setText(r"C:\PSTools\PsExec.exe")
        self.psexec_path_edit.setToolTip(
            self.tr("Caminho completo para PsExec.exe")
        )
        self.psexec_browse_button = _icon_button("\uED25", self.tr("Procurar PsExec.exe"))
        self.psexec_browse_button.clicked.connect(self.browse_psexec)
        psexec_row.addWidget(self.psexec_path_edit)
        psexec_row.addWidget(self.psexec_browse_button)
        psexec_container = QWidget()
        psexec_container.setLayout(psexec_row)
        psexec_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_row(g1, 0, self.tr("PsExec.exe"), psexec_container)

        # Host remoto
        host_row = QHBoxLayout()
        host_row.setSpacing(4)
        host_row.setContentsMargins(0, 0, 0, 0)
        host_clear_container, self.host_edit = _line_edit_with_clear_icon()
        self.host_edit.setPlaceholderText("ex: 192.168.1.100 ou computador.local")
        self.host_edit.setToolTip(self.tr("Nome ou IP do computador remoto"))
        self.ping_button = _icon_button("\uEA18", self.tr("Ping para o host"))
        self.ping_button.clicked.connect(self.ping_host)
        self.psinfo_button = _icon_button("\uE946", self.tr("Abrir PsInfo (inventário)"))
        self.psinfo_button.clicked.connect(self.openPsInfoRequested.emit)
        # \uE8B7 (Copy) já usado em Robocopy; aqui usamos \uE774 (Link) como ação de conexão
        self.rustdesk_button = _icon_button("\uE774", self.tr("Conectar via RustDesk"))
        self.rustdesk_button.clicked.connect(self.openRustDeskRequested.emit)
        host_row.addWidget(host_clear_container)
        host_row.addWidget(self.ping_button)
        host_row.addWidget(self.psinfo_button)
        host_row.addWidget(self.rustdesk_button)
        host_container = QWidget()
        host_container.setLayout(host_row)
        host_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_row(g1, 1, self.tr("Host remoto"), host_container)

        # Comando remoto
        remote_cmd_container, self.remote_cmd_edit = _line_edit_with_clear_icon()
        self.remote_cmd_edit.setPlaceholderText(
            self.tr(r"Programa remoto a executar, ex: \\SERVIDOR\cmd.exe")
        )
        self.remote_cmd_edit.setToolTip(
            self.tr("Comando completo a ser executado remotamente")
        )
        self.remote_cmd_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_row(g1, 2, self.tr("Comando remoto"), remote_cmd_container)

        vbox.addWidget(card1)

        # ── Card 2 — Autenticação ─────────────────────────────────────────────
        card2 = CardWidget("\uE8D7", self.tr("Autenticação"))
        g2 = _grid_in_card(card2)

        user_container, self.user_edit = _line_edit_with_clear_icon(password=False)
        self.user_edit.setPlaceholderText(r"DOMAIN\user")
        self.user_edit.setToolTip(self.tr(r"Usuário no formato DOMAIN\user"))
        _add_row(g2, 0, self.tr("Usuário"), user_container)

        pass_container, self.pass_edit = _line_edit_with_clear_icon(password=True)
        self.pass_edit.setPlaceholderText(self.tr("Senha"))
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_edit.setToolTip(self.tr("Senha do usuário"))
        _add_row(g2, 1, self.tr("Senha"), pass_container)

        vbox.addWidget(card2)

        # ── Card 3 — Privilégios e Sessão ─────────────────────────────────────
        card3 = CardWidget("\uE8D4", self.tr("Privilégios e Sessão"))
        g3 = _grid_in_card(card3)

        # Elevação
        elev_row = QHBoxLayout()
        elev_row.setSpacing(10)
        elev_row.setContentsMargins(0, 0, 0, 0)
        self.flag_h = QCheckBox("-h  " + self.tr("Elevado"))
        self.flag_h.setToolTip(self.tr("Executar com privilégios elevados"))
        self.flag_s = QCheckBox("-s  SYSTEM")
        self.flag_s.setToolTip(self.tr("Executar como System"))
        self.flag_l = QCheckBox("-l  " + self.tr("Limitado"))
        self.flag_l.setToolTip(self.tr("Executar com privilégios limitados"))
        elev_row.addWidget(self.flag_h)
        elev_row.addWidget(self.flag_s)
        elev_row.addWidget(self.flag_l)
        elev_row.addStretch()
        elev_container = QWidget()
        elev_container.setLayout(elev_row)
        elev_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_row(g3, 0, self.tr("Elevação"), elev_container)

        # Sessão
        session_row = QHBoxLayout()
        session_row.setSpacing(8)
        session_row.setContentsMargins(0, 0, 0, 0)
        self.session_interactive = QCheckBox(self.tr("Interativo (-i)"))
        self.session_interactive.setToolTip(
            self.tr("Torna o processo interativo na sessão especificada")
        )
        self.session_id_spin = QSpinBox()
        self.session_id_spin.setRange(0, 2147483647)
        self.session_id_spin.setValue(0)
        self.session_id_spin.setToolTip(
            self.tr("ID da sessão Windows (0 = console)")
        )
        self.session_id_spin.setEnabled(False)
        self.session_id_spin.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        session_id_label = QLabel(self.tr("ID da sessão"))
        session_id_label.setStyleSheet("color: palette(windowText);")
        self.session_interactive.stateChanged.connect(self.on_session_interactive_changed)
        session_row.addWidget(self.session_interactive)
        session_row.addWidget(session_id_label)
        session_row.addWidget(self.session_id_spin)
        session_container = QWidget()
        session_container.setLayout(session_row)
        session_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_row(g3, 1, self.tr("Sessão"), session_container)

        vbox.addWidget(card3)

        # ── Card 4 — Desempenho ───────────────────────────────────────────────
        card4 = CardWidget("\uE950", self.tr("Desempenho"))
        g4 = _grid_in_card(card4)

        # Prioridade
        self.priority_combo = QComboBox()
        self.priority_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.priority_combo.addItem(self.tr("Padrão (sem alteração)"), "")
        self.priority_combo.addItem(self.tr("-low  Baixa"), "-low")
        self.priority_combo.addItem(self.tr("-belownormal  Abaixo do normal"), "-belownormal")
        self.priority_combo.addItem(self.tr("-abovenormal  Acima do normal"), "-abovenormal")
        self.priority_combo.addItem(self.tr("-high  Alta"), "-high")
        self.priority_combo.addItem(self.tr("-realtime  Tempo real"), "-realtime")
        self.priority_combo.addItem(self.tr("-background  Segundo plano"), "-background")
        self.priority_combo.setCurrentIndex(0)
        self.priority_combo.currentIndexChanged.connect(self.on_priority_changed)
        _add_row(g4, 0, self.tr("Prioridade"), self.priority_combo)

        # Grupo CPU
        self.group_combo = QComboBox()
        self.group_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.group_combo.addItem(self.tr("Nenhum"), None)
        self.processor_groups = get_processor_groups()
        for group_id in self.processor_groups:
            self.group_combo.addItem(str(group_id), group_id)
        self.group_combo.setCurrentIndex(0)
        self.group_combo.currentIndexChanged.connect(self.on_group_changed)
        _add_row(g4, 1, self.tr("Grupo CPU"), self.group_combo)

        # Afinidade CPU
        self.affinity_edit = QLineEdit()
        self.affinity_edit.setEnabled(False)
        self.affinity_edit.setPlaceholderText(self.tr("Campo desabilitado"))
        self.affinity_edit.setToolTip(
            self.tr("Selecione um grupo de processador para habilitar")
        )
        self.current_max_cpu = get_processor_count(0)
        self.affinity_validator = AffinityValidator(self.current_max_cpu, self.affinity_edit)
        self.affinity_edit.setValidator(self.affinity_validator)
        _add_row(g4, 2, self.tr("Afinidade CPU"), self.affinity_edit)

        vbox.addWidget(card4)

        # ── Card 5 — Flags e Argumentos ──────────────────────────────────────
        card5 = CardWidget("\uE115", self.tr("Flags e Argumentos"))
        g5 = _grid_in_card(card5)

        # Timeout
        timeout_row = QHBoxLayout()
        timeout_row.setSpacing(6)
        timeout_row.setContentsMargins(0, 0, 0, 0)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(0, 9999)
        self.timeout_spin.setValue(0)
        self.timeout_spin.setToolTip(self.tr("Timeout em segundos (0 = sem timeout)"))
        self.timeout_spin.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        timeout_suffix = QLabel(self.tr("segundos"))
        timeout_suffix.setStyleSheet("color: palette(windowText);")
        timeout_row.addWidget(self.timeout_spin)
        timeout_row.addWidget(timeout_suffix)
        timeout_container = QWidget()
        timeout_container.setLayout(timeout_row)
        timeout_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_row(g5, 0, self.tr("Timeout"), timeout_container)

        # Flags
        flags_flow = FlowLayout(margin=0, h_spacing=10, v_spacing=6)
        self.flag_d = QCheckBox("-d")
        self.flag_d.setToolTip(self.tr("Não aguardar o processo terminar"))
        self.flag_e = QCheckBox("-e")
        self.flag_e.setToolTip(self.tr("Não carregar o perfil do usuário"))
        self.flag_c = QCheckBox("-c")
        self.flag_c.setToolTip(self.tr("Copiar o arquivo especificado para o sistema remoto"))
        self.flag_f = QCheckBox("-f")
        self.flag_f.setToolTip(self.tr("Copiar o arquivo apenas se for mais novo"))
        self.flag_v = QCheckBox("-v")
        self.flag_v.setToolTip(self.tr("Modo verbose"))
        self.flag_accepteula = QCheckBox("-accepteula")
        self.flag_accepteula.setToolTip(self.tr("Aceitar automaticamente o EULA"))
        self.flag_nobanner = QCheckBox("-nobanner")
        self.flag_nobanner.setToolTip(self.tr("Não exibir banner"))
        for cb in [
            self.flag_d, self.flag_e, self.flag_c, self.flag_f,
            self.flag_v, self.flag_accepteula, self.flag_nobanner,
        ]:
            flags_flow.addWidget(cb)
        flags_container = QWidget()
        flags_container.setLayout(flags_flow)
        flags_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_row(g5, 1, self.tr("Flags"), flags_container)

        # Args extras
        extra_args_container, self.extra_args = _line_edit_with_clear_icon()
        self.extra_args.setPlaceholderText(self.tr("Argumentos adicionais para o arquivo"))
        self.extra_args.setToolTip(self.tr("Argumentos extras para passar ao arquivo executado"))
        _add_row(g5, 2, self.tr("Args extras"), extra_args_container)

        vbox.addWidget(card5)

        # Tooltips de prioridade
        self._priority_tooltips = [
            self.tr("Prioridade padrão"),
            self.tr("Baixa prioridade"),
            self.tr("Abaixo do normal"),
            self.tr("Acima do normal"),
            self.tr("Alta prioridade"),
            self.tr("Tempo real"),
            self.tr("Em segundo plano"),
        ]
        self.update_priority_tooltip()
        self.update_affinity_for_group()

    # ── slots ─────────────────────────────────────────────────────────────────

    def on_session_interactive_changed(self, state):
        self.session_id_spin.setEnabled(state == 2)

    def on_priority_changed(self, _index):
        self.update_priority_tooltip()

    def on_group_changed(self, _index):
        self.update_affinity_for_group()

    def update_affinity_for_group(self):
        if self.group_combo.currentIndex() == 0:
            self.affinity_edit.setEnabled(False)
            self.affinity_edit.clear()
            self.affinity_edit.setPlaceholderText(self.tr("Campo desabilitado"))
            self.affinity_edit.setToolTip(
                self.tr("Selecione um grupo de processador para habilitar")
            )
            return

        group_id = self.group_combo.currentData()
        if group_id is None:
            return
        try:
            cpu_count = get_processor_count(group_id)
            self.current_max_cpu = cpu_count
            self.affinity_validator = AffinityValidator(cpu_count, self.affinity_edit)
            self.affinity_edit.setValidator(self.affinity_validator)
            self.affinity_edit.setEnabled(True)
            self.affinity_edit.setPlaceholderText(f"1-{cpu_count} (ex: 1,2,3)")
            self.affinity_edit.setToolTip(
                f"CPUs do grupo {group_id} (1-{cpu_count}) separadas por vírgula"
            )
        except Exception as exc:
            print(f"Erro ao obter CPUs do grupo {group_id}: {exc}")
            self.affinity_edit.setEnabled(True)
            self.affinity_edit.setPlaceholderText("1-8 (ex: 1,2,3)")
            self.affinity_edit.setToolTip(
                f"CPUs do grupo {group_id} separadas por vírgula"
            )

    def update_priority_tooltip(self):
        idx = self.priority_combo.currentIndex()
        if 0 <= idx < len(self._priority_tooltips):
            self.priority_combo.setToolTip(self._priority_tooltips[idx])

    def browse_psexec(self):
        dlg = QFileDialog(self)
        dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
        dlg.setNameFilter(self.tr("Executáveis (*.exe)"))
        dlg.setWindowTitle(self.tr("Selecionar PsExec.exe"))
        if dlg.exec():
            files = dlg.selectedFiles()
            if files:
                self.psexec_path_edit.setText(files[0])

    def ping_host(self):
        import subprocess
        host = self.host_edit.text().strip()
        if not host:
            if self.log_output:
                self.log_output.append_log(self.tr("[PING] Por favor, insira um host para ping."))
            return
        try:
            subprocess.Popen(f'start cmd /k "ping -n 4 -w 1000 {host}"', shell=True)
        except Exception as exc:
            if self.log_output:
                self.log_output.append_log(f"[PING] Erro ao executar ping: {exc}")
