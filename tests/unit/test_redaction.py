"""Testes unitários — redaction de credenciais."""

from utils.redaction import (
    REDACTED,
    format_argv_for_display,
    mask_password,
    redact_argv,
    redact_command_text,
)


def test_mask_password_empty():
    assert mask_password("") == ""
    assert mask_password(None) == ""


def test_mask_password_present():
    assert mask_password("secret") == REDACTED


def test_redact_command_text_flag():
    cmd = r'PsExec.exe \\HOST -u DOM\user -p SuperSecret123 -h cmd'
    out = redact_command_text(cmd)
    assert "SuperSecret123" not in out
    assert "-p ********" in out or f"-p {REDACTED}" in out


def test_redact_command_text_quoted():
    cmd = r'psexec \\PC -u user -p "my pass" -s'
    out = redact_command_text(cmd)
    assert "my pass" not in out


def test_redact_with_explicit_password():
    cmd = "something SuperSecret123 else"
    out = redact_command_text(cmd, passwords=["SuperSecret123"])
    assert "SuperSecret123" not in out
    assert REDACTED in out


def test_redact_argv():
    argv = ["PsExec.exe", r"\\HOST", "-u", "user", "-p", "Secret!", "-h", "cmd"]
    safe = redact_argv(argv)
    assert "Secret!" not in safe
    assert safe[safe.index("-p") + 1] == REDACTED


def test_format_argv_for_display():
    argv = ["PsExec.exe", r"\\HOST", "-p", "pwd"]
    text = format_argv_for_display(argv)
    assert "pwd" not in text
    assert REDACTED in text
