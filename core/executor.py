import subprocess
import sys
import shlex
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtCore import QProcess
from concurrent.futures import ThreadPoolExecutor, Future

class Executor(QObject):
    outputReceived = pyqtSignal(str)
    errorReceived = pyqtSignal(str)
    finished = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.future = None
        self.process = None

    def run(self, command: str):
        self.stop()
        self._last_command = command  # Salva o comando para uso no _run_command
        self.future = self.executor.submit(self._run_command, command)
        QTimer.singleShot(100, self._check_future)

    def _run_command(self, command):
        try:
            import shlex
            import os
            # Detecta se é robocopy para prefixar saída
            is_robocopy = False
            try:
                parts = shlex.split(command)
                if parts and os.path.basename(parts[0]).lower() == 'robocopy':
                    is_robocopy = True
            except Exception:
                pass
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
                text=False,
            )

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

            # Leitura em tempo real
            while True:
                output_b = self.process.stdout.readline() if self.process.stdout else b""
                output = decode_best_effort(output_b).rstrip("\r\n")
                if output:
                    if is_robocopy:
                        self.outputReceived.emit(f"[ROBOCOPY] {output}")
                    else:
                        self.outputReceived.emit(output)
                error_b = self.process.stderr.readline() if self.process.stderr else b""
                error = decode_best_effort(error_b).rstrip("\r\n")
                if error:
                    if is_robocopy:
                        self.errorReceived.emit(f"[ROBOCOPY] {error}")
                    else:
                        self.errorReceived.emit(error)
                if self.process.poll() is not None:
                    break
            # Pega o restante
            if self.process.stdout:
                for line_b in self.process.stdout:
                    line = decode_best_effort(line_b).rstrip("\r\n")
                    if not line:
                        continue
                    if is_robocopy:
                        self.outputReceived.emit(f"[ROBOCOPY] {line}")
                    else:
                        self.outputReceived.emit(line)
            if self.process.stderr:
                for line_b in self.process.stderr:
                    line = decode_best_effort(line_b).rstrip("\r\n")
                    if not line:
                        continue
                    if is_robocopy:
                        self.errorReceived.emit(f"[ROBOCOPY] {line}")
                    else:
                        self.errorReceived.emit(line)
            return self.process.returncode
        except Exception as e:
            self.errorReceived.emit(f"Error executing command: {str(e)}")
            return 1
        finally:
            self.process = None

    def _check_future(self):
        if self.future is None:
            return
        if self.future.done():
            try:
                exit_code = self.future.result()
                self.finished.emit(exit_code)
            except Exception as e:
                self.errorReceived.emit(str(e))
                self.finished.emit(1)
            self.future = None
        else:
            QTimer.singleShot(100, self._check_future)

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception:
                pass
        self.process = None
        if self.future:
            self.future.cancel()
            self.future = None