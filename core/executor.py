"""Executor assíncrono com resultado estruturado e leitura segura de pipes."""

from __future__ import annotations

import subprocess
import threading
from datetime import datetime
from typing import List, Optional, Sequence, Union

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from concurrent.futures import ThreadPoolExecutor, Future

from core.models import CommandSpec, ExecutionResult, OperationStatus, is_robocopy_success
from core.win_cmd import CREATE_NO_WINDOW, popen_argv
from utils.redaction import redact_command_text


def decode_best_effort(b: bytes) -> str:
    if not b:
        return ""
    try:
        return b.decode("utf-8-sig")
    except Exception:
        pass
    try:
        return b.decode("mbcs", errors="replace")
    except Exception:
        pass
    return b.decode("cp1252", errors="replace")


def _read_pipe(pipe, callback, prefix: str = "") -> str:
    """Lê um pipe linha a linha; evita deadlock ao rodar em thread dedicada."""
    chunks: List[str] = []
    try:
        for line_b in iter(pipe.readline, b""):
            line = decode_best_effort(line_b).rstrip("\r\n")
            if not line:
                continue
            chunks.append(line)
            text = f"{prefix}{line}" if prefix else line
            if callback:
                callback(text)
    except Exception:
        pass
    finally:
        try:
            pipe.close()
        except Exception:
            pass
    return "\n".join(chunks)


class Executor(QObject):
    """
    Executa um comando em ThreadPoolExecutor (1 worker) e emite sinais Qt.

    Aceita ``str`` (legado, via shell=False + cmd quando necessário) ou
    ``CommandSpec`` / lista de argv.

    Cancelamento: encerra apenas o processo LOCAL. Processos remotos iniciados
    via PsExec podem continuar — ``ExecutionResult.remote_may_continue=True``.
    """

    outputReceived = pyqtSignal(str)
    errorReceived = pyqtSignal(str)
    finished = pyqtSignal(int)
    resultReady = pyqtSignal(object)  # ExecutionResult

    def __init__(self, parent=None):
        super().__init__(parent)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.future: Optional[Future] = None
        self.process: Optional[subprocess.Popen] = None
        self._cancel_requested = False
        self._last_result: Optional[ExecutionResult] = None
        self._passwords: List[str] = []

    def run(
        self,
        command: Union[str, CommandSpec, Sequence[str]],
        *,
        passwords: Optional[Sequence[str]] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.stop()
        self._cancel_requested = False
        self._passwords = [p for p in (passwords or []) if p]
        self.future = self.executor.submit(self._run_command, command, timeout)
        QTimer.singleShot(100, self._check_future)

    def _normalize_argv(
        self, command: Union[str, CommandSpec, Sequence[str]]
    ) -> tuple[List[str], bool, str]:
        """
        Retorna (argv, is_robocopy, display_safe).

        Strings legadas (ex.: robocopy "src" "dst" file) são convertidas via
        cmd.exe /c apenas quando necessário — documentado.
        """
        if isinstance(command, CommandSpec):
            argv = command.argv
            display = command.sanitized_display(self._passwords)
            is_rc = (command.metadata or {}).get("kind") == "robocopy" or (
                argv and "robocopy" in argv[0].lower()
            )
            return argv, bool(is_rc), display

        if isinstance(command, (list, tuple)):
            argv = [str(a) for a in command]
            is_rc = bool(argv) and "robocopy" in argv[0].lower()
            display = redact_command_text(" ".join(argv), passwords=self._passwords)
            return argv, is_rc, display

        # string legada
        text = str(command or "").strip()
        display = redact_command_text(text, passwords=self._passwords)
        is_rc = text.lower().lstrip().startswith("robocopy")
        # Usar cmd /c para strings legadas com quoting complexo do Windows.
        # Motivo: robocopy/paths com aspas já montados como string pela UI antiga.
        argv = ["cmd.exe", "/c", text]
        return argv, is_rc, display

    def _run_command(
        self,
        command: Union[str, CommandSpec, Sequence[str]],
        timeout: Optional[float],
    ) -> ExecutionResult:
        result = ExecutionResult(
            started_at=datetime.now(),
            status=OperationStatus.STARTED,
        )
        stdout_acc: List[str] = []
        stderr_acc: List[str] = []

        try:
            argv, is_robocopy, _display = self._normalize_argv(command)
            if not argv:
                result.exception = "Comando vazio"
                result.return_code = 1
                return result.finalize()

            prefix = "[ROBOCOPY] " if is_robocopy else ""
            creationflags = CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

            def on_out(line: str) -> None:
                stdout_acc.append(line)
                self.outputReceived.emit(line)

            def on_err(line: str) -> None:
                stderr_acc.append(line)
                self.errorReceived.emit(line)

            try:
                self.process = popen_argv(
                    argv,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=creationflags,
                )
            except FileNotFoundError as exc:
                msg = f"Executável não encontrado: {argv[0]}"
                self.errorReceived.emit(msg)
                result.exception = msg
                result.return_code = 1
                return result.finalize()
            except OSError as exc:
                safe = redact_command_text(str(exc), passwords=self._passwords)
                msg = f"Falha ao iniciar processo: {safe}"
                self.errorReceived.emit(msg)
                result.exception = msg
                result.return_code = 1
                return result.finalize()

            t_out = threading.Thread(
                target=lambda: _read_pipe(
                    self.process.stdout,
                    lambda ln: on_out(f"{prefix}{ln}" if prefix else ln),
                ),
                daemon=True,
            )
            t_err = threading.Thread(
                target=lambda: _read_pipe(
                    self.process.stderr,
                    lambda ln: on_err(f"{prefix}{ln}" if prefix else ln),
                ),
                daemon=True,
            )
            t_out.start()
            t_err.start()

            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                result.timed_out = True
                result.remote_may_continue = True
                try:
                    self.process.kill()
                except Exception:
                    pass
                self.process.wait(timeout=5)

            t_out.join(timeout=5)
            t_err.join(timeout=5)

            if self._cancel_requested:
                result.cancelled = True
                result.remote_may_continue = True

            result.return_code = self.process.returncode
            result.stdout = "\n".join(stdout_acc)
            result.stderr = "\n".join(stderr_acc)

            if is_robocopy and result.return_code is not None:
                result.metadata["robocopy_success"] = is_robocopy_success(result.return_code)
                if is_robocopy_success(result.return_code):
                    result.success = True
                    result.status = OperationStatus.COMPLETED
                    result.finished_at = datetime.now()
                    if result.started_at:
                        result.duration_seconds = (
                            result.finished_at - result.started_at
                        ).total_seconds()
                    return result

            return result.finalize()

        except Exception as exc:
            safe = redact_command_text(str(exc), passwords=self._passwords)
            self.errorReceived.emit(f"Error executing command: {safe}")
            result.exception = safe
            result.return_code = 1
            return result.finalize()
        finally:
            result.finished_at = result.finished_at or datetime.now()
            if result.started_at and result.duration_seconds is None:
                result.duration_seconds = (
                    result.finished_at - result.started_at
                ).total_seconds()
            self.process = None
            self._last_result = result

    def _check_future(self) -> None:
        if self.future is None:
            return
        if self.future.done():
            try:
                result = self.future.result()
                if not isinstance(result, ExecutionResult):
                    # compat: future retornou int
                    code = int(result) if result is not None else 1
                    result = ExecutionResult(return_code=code).finalize()
                self._last_result = result
                self.resultReady.emit(result)
                self.finished.emit(result.return_code if result.return_code is not None else 1)
            except Exception as e:
                safe = redact_command_text(str(e), passwords=self._passwords)
                self.errorReceived.emit(safe)
                result = ExecutionResult(
                    return_code=1,
                    exception=safe,
                    status=OperationStatus.FAILED,
                )
                self.resultReady.emit(result)
                self.finished.emit(1)
            self.future = None
        else:
            QTimer.singleShot(100, self._check_future)

    def stop(self) -> None:
        """
        Cancela a execução LOCAL.

        Limitação: se o comando já disparou trabalho remoto via PsExec,
        o processo remoto pode continuar. O resultado marca
        ``remote_may_continue=True``.
        """
        self._cancel_requested = True
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception:
                pass
            try:
                self.process.kill()
            except Exception:
                pass
        self.process = None
        if self.future:
            self.future.cancel()
            self.future = None

    @property
    def last_result(self) -> Optional[ExecutionResult]:
        return self._last_result

    def shutdown(self, wait: bool = False) -> None:
        self.stop()
        self.executor.shutdown(wait=wait, cancel_futures=True)
