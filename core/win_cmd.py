"""
Helpers seguros para lançar processos no Windows sem shell=True.

Estratégia de console externo:
- Preferir ``CREATE_NEW_CONSOLE`` direto no argv do processo alvo
  (CreateProcess recebe a lista corretamente; sem re-serialização via cmd.exe).
- ``cmd.exe /k`` só quando explicitamente necessário; o quoting do cmd.exe
  **não** garante round-trip seguro para credenciais com metacaracteres.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Optional, Sequence

CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def quote_for_cmd(arg: str) -> str:
    """
    Aspas para interpretação pelo ``cmd.exe`` (não regras Unix/shlex posix).

    Regras principais (documentação Microsoft / comportamental do cmd):
    - Espaços e metacaracteres ``& | < > ^ ( ) % ! "`` exigem aspas.
    - Aspas internas são dobradas (``"`` → ``""``).
    - ``%`` e ``!`` (expansão de variáveis / delayed expansion) **não** podem
      ser neutralizados de forma completa apenas com aspas; por isso credenciais
      não devem passar por ``cmd /k`` quando evitável.

    Esta função é útil para display e para casos sem segredos. Para execução
    com credenciais, use ``open_external_console_argv`` (CreateProcess direto).
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


def open_external_console_argv(
    argv: Sequence[str],
    *,
    title: str = "PSExecGUI",
) -> subprocess.Popen:
    """
    Abre o processo em um console novo (CREATE_NEW_CONSOLE), sem cmd.exe.

    Motivo: preservar experiência de terminal externo sem re-serializar argv
    através das regras frágeis do ``cmd.exe /k``. Em Windows, o Python passa
    a lista a CreateProcess com quoting compatível com CommandLineToArgvW.

    Limitação de UX: a janela fecha quando o processo termina (não há ``/k``).
    Em troca, credenciais e metacaracteres não passam por uma segunda camada
    de parsing do CMD.

    ATENÇÃO DE SEGURANÇA: com PsExec ``-p``, a senha permanece visível na
    command line do processo (limitação inerente). Nunca grave esse argv em log.
    """
    del title  # reservado para futuras melhorias (SetConsoleTitle)
    return popen_argv(list(argv), creationflags=CREATE_NEW_CONSOLE)


def open_external_cmd_k(command_line: str, *, title: str = "PSExecGUI") -> subprocess.Popen:
    """
    Abre ``cmd /k <comando>`` — uso restrito (sem segredos recomendado).

    Preferir ``open_external_console_argv`` para PsExec com credenciais.
    """
    del title
    argv = ["cmd.exe", "/k", command_line]
    return popen_argv(argv, creationflags=CREATE_NEW_CONSOLE)


def open_external_cmd_k_argv(argv: Sequence[str], *, title: str = "PSExecGUI") -> subprocess.Popen:
    """
    Compat: serializa argv para cmd /k.

    Preferir ``open_external_console_argv`` quando o alvo for o próprio argv
    (ex.: PsExec). Mantido para callers que realmente precisam de ``/k``.
    """
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
