"""Modelos de domínio tipados para construção e execução de comandos."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Sequence

from utils.redaction import format_argv_for_display, redact_command_text


class OperationStatus(str, Enum):
    """Estado de alto nível de uma operação administrativa."""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    UNKNOWN = "unknown"


@dataclass
class PsExecOptions:
    host: str = ""
    psexec_path: str = ""
    remote_cmd: str = ""
    user: str = ""
    password: str = ""
    elevate_h: bool = False
    elevate_s: bool = False
    elevate_l: bool = False
    session_interactive: bool = False
    session_id: int = 0
    priority: str = ""
    affinity: str = ""
    group: str = ""
    timeout: int = 0
    flag_d: bool = False
    flag_e: bool = False
    flag_c: bool = False
    flag_f: bool = False
    flag_v: bool = False
    flag_accepteula: bool = False
    flag_nobanner: bool = False
    extra_args: str = ""

    @classmethod
    def from_dict(cls, params: dict) -> "PsExecOptions":
        """Compatibilidade com o dicionário legado da UI."""
        p = params or {}
        return cls(
            host=str(p.get("host") or "").strip(),
            psexec_path=str(p.get("psexec_path") or "").strip(),
            remote_cmd=str(p.get("remote_cmd") or "").strip(),
            user=str(p.get("user") or "").strip(),
            password=str(p.get("password") or ""),
            elevate_h=bool(p.get("-h")),
            elevate_s=bool(p.get("-s")),
            elevate_l=bool(p.get("-l")),
            session_interactive=bool(p.get("session_interactive")),
            session_id=int(p.get("session_id") or 0),
            priority=str(p.get("priority") or ""),
            affinity=str(p.get("affinity") or "").strip(),
            group=str(p.get("group") or ""),
            timeout=int(p.get("timeout") or 0),
            flag_d=bool(p.get("-d")),
            flag_e=bool(p.get("-e")),
            flag_c=bool(p.get("-c")),
            flag_f=bool(p.get("-f")),
            flag_v=bool(p.get("-v")),
            flag_accepteula=bool(p.get("-accepteula")),
            flag_nobanner=bool(p.get("-nobanner")),
            extra_args=str(p.get("extra_args") or "").strip(),
        )

    def to_legacy_dict(self) -> dict:
        return {
            "host": self.host,
            "psexec_path": self.psexec_path,
            "remote_cmd": self.remote_cmd,
            "user": self.user,
            "password": self.password,
            "-h": self.elevate_h,
            "-s": self.elevate_s,
            "-l": self.elevate_l,
            "session_interactive": self.session_interactive,
            "session_id": self.session_id,
            "priority": self.priority,
            "affinity": self.affinity,
            "group": self.group,
            "timeout": self.timeout,
            "-d": self.flag_d,
            "-e": self.flag_e,
            "-c": self.flag_c,
            "-f": self.flag_f,
            "-v": self.flag_v,
            "-accepteula": self.flag_accepteula,
            "-nobanner": self.flag_nobanner,
            "extra_args": self.extra_args,
        }

    def clear_password(self) -> None:
        self.password = ""


@dataclass
class MSIOptions:
    enable: bool = False
    action: str = ""
    interface: str = ""
    restart: str = ""
    log: bool = False
    log_file: str = ""
    repair: str = ""
    update: str = ""

    @classmethod
    def from_dict(cls, params: dict) -> "MSIOptions":
        p = params or {}
        return cls(
            enable=bool(p.get("enable")),
            action=str(p.get("action") or ""),
            interface=str(p.get("interface") or ""),
            restart=str(p.get("restart") or ""),
            log=bool(p.get("log")),
            log_file=str(p.get("log_file") or ""),
            repair=str(p.get("repair") or ""),
            update=str(p.get("update") or ""),
        )


@dataclass
class RobocopyOptions:
    dest: str = "Temp"
    switches: str = "/NFL /NDL /NJH /NJS /nc /ns /np"

    @classmethod
    def from_dict(cls, params: Optional[dict]) -> Optional["RobocopyOptions"]:
        if not params:
            return None
        return cls(
            dest=str(params.get("dest") or "Temp"),
            switches=str(params.get("switches") or "/NFL /NDL /NJH /NJS /nc /ns /np"),
        )


@dataclass
class PowerShellOptions:
    NoProfile: bool = False
    NoExit: bool = False
    ExecutionPolicy: str = ""
    WindowStyle: str = ""
    Command: str = ""
    EncodedCommand: str = ""

    @classmethod
    def from_dict(cls, params: dict) -> "PowerShellOptions":
        p = params or {}
        return cls(
            NoProfile=bool(p.get("NoProfile")),
            NoExit=bool(p.get("NoExit")),
            ExecutionPolicy=str(p.get("ExecutionPolicy") or ""),
            WindowStyle=str(p.get("WindowStyle") or ""),
            Command=str(p.get("Command") or ""),
            EncodedCommand=str(p.get("EncodedCommand") or ""),
        )


@dataclass
class CmdOptions:
    slash_c: bool = False
    slash_k: bool = False
    slash_q: bool = False
    slash_d: bool = False
    slash_s: bool = False
    Command: str = ""

    @classmethod
    def from_dict(cls, params: dict) -> "CmdOptions":
        p = params or {}
        return cls(
            slash_c=bool(p.get("/C")),
            slash_k=bool(p.get("/K")),
            slash_q=bool(p.get("/Q")),
            slash_d=bool(p.get("/D")),
            slash_s=bool(p.get("/S")),
            Command=str(p.get("Command") or ""),
        )


@dataclass
class FileSelection:
    mode: str = "file"  # 'file' | 'folder'
    file: Optional[str] = None
    folder: Optional[str] = None

    @classmethod
    def from_any(cls, selection: Any) -> Optional["FileSelection"]:
        if selection is None:
            return None
        if isinstance(selection, FileSelection):
            return selection
        if isinstance(selection, dict):
            return cls(
                mode=str(selection.get("mode") or "file"),
                file=selection.get("file"),
                folder=selection.get("folder"),
            )
        if isinstance(selection, str):
            return cls(mode="file", file=selection, folder=None)
        return None


@dataclass
class CommandSpec:
    """
    Representação estruturada de um processo a executar.

    ``args`` é a lista real para subprocess (pode conter senha).
    ``display_command`` é SEMPRE sanitizado — nunca use para executar.
    """

    executable: str
    args: list[str] = field(default_factory=list)
    cwd: Optional[str] = None
    display_command: str = ""
    has_secrets: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    # Quando True, a execução preferida é terminal externo (experiência atual)
    prefer_external_console: bool = False
    # Texto legado multi-linha (robocopy\\npsexec) apenas para display
    legacy_display: str = ""

    @property
    def argv(self) -> list[str]:
        """Lista completa [executable, *args] para Popen."""
        if self.args and self.args[0] == self.executable:
            return list(self.args)
        return [self.executable, *self.args]

    @classmethod
    def from_argv(
        cls,
        argv: Sequence[str],
        *,
        has_secrets: bool = False,
        passwords: Optional[Sequence[str]] = None,
        cwd: Optional[str] = None,
        metadata: Optional[dict] = None,
        prefer_external_console: bool = False,
    ) -> "CommandSpec":
        argv_list = [str(a) for a in argv if a is not None]
        if not argv_list:
            raise ValueError("argv vazio")
        display = format_argv_for_display(argv_list)
        if passwords:
            display = redact_command_text(display, passwords=passwords)
        return cls(
            executable=argv_list[0],
            args=argv_list[1:],
            cwd=cwd,
            display_command=display,
            has_secrets=has_secrets or bool(passwords),
            metadata=dict(metadata or {}),
            prefer_external_console=prefer_external_console,
        )

    def sanitized_display(self, passwords: Optional[Sequence[str]] = None) -> str:
        text = self.display_command or format_argv_for_display(self.argv)
        return redact_command_text(text, passwords=passwords)


@dataclass
class ExecutionResult:
    return_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    cancelled: bool = False
    timed_out: bool = False
    success: bool = False
    exception: Optional[str] = None
    status: OperationStatus = OperationStatus.UNKNOWN
    # Cancelamento local não implica cancelamento remoto (PsExec)
    remote_may_continue: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def finalize(self) -> "ExecutionResult":
        if self.started_at and self.finished_at:
            self.duration_seconds = (self.finished_at - self.started_at).total_seconds()
        if self.cancelled:
            self.status = OperationStatus.CANCELLED
            self.success = False
        elif self.timed_out:
            self.status = OperationStatus.TIMED_OUT
            self.success = False
        elif self.exception:
            self.status = OperationStatus.FAILED
            self.success = False
        elif self.return_code is None:
            self.status = OperationStatus.UNKNOWN
            self.success = False
        elif self.return_code == 0:
            self.status = OperationStatus.COMPLETED
            self.success = True
        else:
            # Robocopy 0-7 tratado pelo chamador via metadata
            self.status = OperationStatus.FAILED
            self.success = False
        return self


def is_robocopy_success(exit_code: int) -> bool:
    """Robocopy: 0-7 = sucesso/avisos; >= 8 = falha."""
    return 0 <= int(exit_code) <= 7
