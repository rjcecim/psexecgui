"""
Política central de proteção de credenciais.

Toda representação destinada a UI, logs, histórico ou arquivos temporários
deve passar por estas funções. Não espalhe mascaramento ad-hoc pelo código.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional, Sequence

# Marcador padrão usado em preview/logs
REDACTED = "********"

# -p / -P seguido de valor (com ou sem aspas), em linha de comando estilo PsExec
_PASSWORD_FLAG_RE = re.compile(
    r'(?P<prefix>(?:^|[\s"])-p(?:\s+|=))'
    r'(?P<value>"[^"]*"|\'[^\']*\'|[^\s"\']+)',
    re.IGNORECASE,
)

# Também cobre formas coladas: -psenha (raro, mas defensivo)
_PASSWORD_GLUED_RE = re.compile(
    r'(?P<prefix>(?:^|[\s"])-p)(?P<value>[^\s"\'-][^\s]*)',
    re.IGNORECASE,
)


def mask_password(password: Optional[str], placeholder: str = REDACTED) -> str:
    """Retorna o placeholder se houver senha; string vazia se não houver."""
    if password is None or str(password).strip() == "":
        return ""
    return placeholder


def redact_command_text(
    text: str,
    passwords: Optional[Iterable[str]] = None,
    placeholder: str = REDACTED,
) -> str:
    """
    Sanitiza uma string de comando/log para exibição.

    1. Substitui valores explícitos de ``passwords`` (se fornecidos).
    2. Mascara qualquer argumento ``-p`` / ``-P`` restante (defesa em profundidade).
    """
    if not text:
        return text or ""

    result = text

    if passwords:
        # Senhas mais longas primeiro evita mascaramento parcial incorreto
        for pwd in sorted({p for p in passwords if p}, key=len, reverse=True):
            if not pwd:
                continue
            result = result.replace(pwd, placeholder)

    def _replace_flag(match: re.Match[str]) -> str:
        return f"{match.group('prefix')}{placeholder}"

    result = _PASSWORD_FLAG_RE.sub(_replace_flag, result)
    # Só aplica glued se ainda restar -p colado sem espaço (evita re-mascarar)
    result = _PASSWORD_GLUED_RE.sub(_replace_flag, result)
    return result


def redact_argv(
    argv: Sequence[str],
    placeholder: str = REDACTED,
) -> list[str]:
    """
    Sanitiza uma lista de argumentos (estilo subprocess).

    Trata ``-p`` / ``-P`` como flag cujo próximo elemento (ou valor após ``=``)
    é a senha.
    """
    out: list[str] = []
    skip_next = False
    for i, arg in enumerate(argv):
        if skip_next:
            out.append(placeholder)
            skip_next = False
            continue
        lower = arg.lower()
        if lower in ("-p", "/p"):
            out.append(arg)
            skip_next = True
            continue
        if lower.startswith("-p=") or lower.startswith("/p="):
            out.append(f"{arg[:3]}{placeholder}" if arg[2:3] == "=" else f"-p={placeholder}")
            continue
        # Forma "-psenha" (sem espaço) — defensivo
        if lower.startswith("-p") and len(arg) > 2 and arg[2] not in "=-":
            out.append(f"-p{placeholder}")
            continue
        out.append(arg)
    return out


def format_argv_for_display(argv: Sequence[str], placeholder: str = REDACTED) -> str:
    """Junta argv sanitizado em string legível para preview/log."""
    return " ".join(quote_arg_for_display(a) for a in redact_argv(argv, placeholder))


def quote_arg_for_display(arg: str) -> str:
    """Aspas simples para display quando há espaços (não para execução)."""
    if not arg:
        return '""'
    if any(ch in arg for ch in (' ', '\t', '"')):
        escaped = arg.replace('"', '\\"')
        return f'"{escaped}"'
    return arg


def assert_no_secrets(text: str, passwords: Optional[Iterable[str]] = None) -> str:
    """
    Garante que o texto não contém senhas conhecidas; sempre aplica redaction.
    Útil como última barreira antes de gravar em disco ou UI.
    """
    return redact_command_text(text, passwords=passwords)
