"""Logging seguro da aplicação (nunca registra senhas)."""

from __future__ import annotations

import datetime
import logging
import os
import sys
from typing import Iterable, Optional

from utils.redaction import redact_command_text

_LOGGER_NAME = "psexecgui"
_configured = False

# Arquivo de histórico de operações — única fonte de escrita: _append_history_line
HISTORY_FILENAME = "exec_history.log"
# Log estruturado do logger (separado do histórico de operações)
APP_LOG_FILENAME = "app.log"


def is_portable_mode() -> bool:
    """
    Modo portable: arquivo ``portable.flag`` ao lado do exe/script,
    ou variável de ambiente PSEXECGUI_PORTABLE=1.
    """
    if os.environ.get("PSEXECGUI_PORTABLE", "").strip() in ("1", "true", "True", "yes"):
        return True
    base = _app_dir()
    return os.path.isfile(os.path.join(base, "portable.flag"))


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_log_dir() -> str:
    """
    Diretório de logs:
    - portable / env: pasta do app
    - caso contrário: %LOCALAPPDATA%\\PSExecGUI\\logs
    """
    if is_portable_mode():
        path = os.path.join(_app_dir(), "logs")
    else:
        local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        path = os.path.join(local, "PSExecGUI", "logs")
    os.makedirs(path, exist_ok=True)
    return path


def get_history_log_path() -> str:
    return os.path.join(get_log_dir(), HISTORY_FILENAME)


def get_app_log_path() -> str:
    return os.path.join(get_log_dir(), APP_LOG_FILENAME)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """
    Configura o logger da aplicação.

    O FileHandler grava em ``app.log`` (diagnóstico). O histórico de operações
    (``exec_history.log``) é escrito **somente** por ``_append_history_line`` /
    ``log_operation`` — nunca pelo FileHandler, evitando duplicação.
    """
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    if _configured:
        return logger
    logger.setLevel(level)
    logger.propagate = False

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        fh = logging.FileHandler(get_app_log_path(), encoding="utf-8")
        fh.setFormatter(fmt)
        fh.setLevel(level)
        logger.addHandler(fh)
    except OSError:
        pass

    _configured = True
    return logger


def get_logger() -> logging.Logger:
    if not _configured:
        return configure_logging()
    return logging.getLogger(_LOGGER_NAME)


def _append_history_line(text: str) -> None:
    """Única função que escreve em exec_history.log."""
    try:
        path = get_history_log_path()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {text}\n")
    except OSError:
        pass


def log_operation(
    operation: str,
    *,
    detail: str = "",
    exit_code: Optional[int] = None,
    passwords: Optional[Iterable[str]] = None,
    level: int = logging.INFO,
) -> str:
    """
    Registra uma operação já sanitizada (única entrada no histórico).

    Escreve uma vez em ``exec_history.log`` e espelha no logger (``app.log``).
    """
    safe_detail = redact_command_text(detail or "", passwords=passwords)
    parts = [operation]
    if safe_detail:
        parts.append(safe_detail)
    if exit_code is not None:
        parts.append(f"exit_code={exit_code}")
    message = " | ".join(parts)
    get_logger().log(level, message)
    _append_history_line(message)
    return message


def append_history(
    text: str,
    passwords: Optional[Iterable[str]] = None,
) -> None:
    """
    API pública para histórico livre (UI).

    Preferir ``log_operation`` para operações tipadas. Não chamar ambos para
    a mesma operação.
    """
    safe = redact_command_text(text or "", passwords=passwords)
    _append_history_line(safe)


def reset_logging_for_tests() -> None:
    """Reinicia estado do logger (apenas testes)."""
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass
    _configured = False
