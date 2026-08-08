"""
Helpers seguros para lançar processos no Windows sem shell=True.

Quando cmd.exe é realmente necessário (terminal externo com /k para
acompanhamento visual), encapsulamos aqui e documentamos o motivo.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional, Sequence

CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def quote_for_cmd(arg: str) -> str:
    """
    Aspas para cmd.exe (Windows), não regras de Unix/shlex posix.

    Regra: se contém espaço ou caracteres especiais do cmd, envolva em aspas
    e dobre aspas internas.
    """
    if not arg:
        return '""'
    special = set(' \t&|<>()^%"!')
    if not any(ch in special for ch in arg):
        return arg
    return '"' + arg.replace('"', '""') + '"'


def argv_to_cmd_line(argv: Sequence[str]) -> str:
    """Converte lista de args em uma linha compatível com cmd.exe."""
    return " ".join(quote_for_cmd(a) for a in argv)


def popen_argv(
    argv: Sequence[str],
    *,
    cwd: Optional[str] = None,
    stdout=None,
    stderr=None,
    stdin=None,
    creationflags: int = 0,
    env: Optional[dict] = None,
) -> subprocess.Popen:
    """subprocess.Popen com lista de argumentos (shell=False)."""
    if not argv:
        raise ValueError("argv vazio")
    return subprocess.Popen(
        list(argv),
        cwd=cwd,
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
        shell=False,
        env=env,
        creationflags=creationflags,
    )


def open_external_cmd_k(command_line: str, *, title: str = "PSExecGUI") -> subprocess.Popen:
    """
    Abre um console externo com ``cmd /k <comando>``.

    Motivo do uso de cmd.exe: a experiência atual do app é acompanhar a saída
    PsExec em uma janela de terminal persistente. Não usamos shell=True;
    invocamos cmd.exe diretamente com argumentos em lista.

    ATENÇÃO DE SEGURANÇA: se ``command_line`` contiver ``-p <senha>``, a senha
    permanece visível na linha de comando do processo (limitação inerente do
    PsExec com credenciais explícitas). Nunca grave essa linha em log/arquivo.
    """
    # cmd /k: executa e mantém a janela aberta
    argv = ["cmd.exe", "/k", command_line]
    return popen_argv(argv, creationflags=CREATE_NEW_CONSOLE)


def open_external_cmd_k_argv(argv: Sequence[str], *, title: str = "PSExecGUI") -> subprocess.Popen:
    """Como open_external_cmd_k, mas a partir de argv estruturado."""
    return open_external_cmd_k(argv_to_cmd_line(argv), title=title)


def run_captured(
    argv: Sequence[str],
    *,
    timeout: Optional[float] = None,
    cwd: Optional[str] = None,
    creationflags: Optional[int] = None,
) -> subprocess.CompletedProcess:
    """subprocess.run sem shell, capturando stdout/stderr em bytes."""
    flags = CREATE_NO_WINDOW if creationflags is None else creationflags
    return subprocess.run(
        list(argv),
        capture_output=True,
        text=False,
        timeout=timeout,
        cwd=cwd,
        shell=False,
        creationflags=flags if sys.platform == "win32" else 0,
    )


def start_detached_file(path: str) -> subprocess.Popen:
    """
    Abre um .bat/.cmd em console externo sem shell=True.

    Usado apenas quando o arquivo NÃO contém senha (ex.: wrapper de UI).
    """
    argv = ["cmd.exe", "/k", quote_for_cmd(path)]
    return popen_argv(argv, creationflags=CREATE_NEW_CONSOLE)
