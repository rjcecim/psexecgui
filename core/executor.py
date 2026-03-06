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
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            # Leitura em tempo real
            while True:
                output = self.process.stdout.readline() if self.process.stdout else ''
                if output:
                    if is_robocopy:
                        self.outputReceived.emit(f"[ROBOCOPY] {output.rstrip()}")
                    else:
                        self.outputReceived.emit(output.rstrip())
                error = self.process.stderr.readline() if self.process.stderr else ''
                if error:
                    if is_robocopy:
                        self.errorReceived.emit(f"[ROBOCOPY] {error.rstrip()}")
                    else:
                        self.errorReceived.emit(error.rstrip())
                if self.process.poll() is not None:
                    break
            # Pega o restante
            if self.process.stdout:
                for line in self.process.stdout:
                    if is_robocopy:
                        self.outputReceived.emit(f"[ROBOCOPY] {line.rstrip()}")
                    else:
                        self.outputReceived.emit(line.rstrip())
            if self.process.stderr:
                for line in self.process.stderr:
                    if is_robocopy:
                        self.errorReceived.emit(f"[ROBOCOPY] {line.rstrip()}")
                    else:
                        self.errorReceived.emit(line.rstrip())
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