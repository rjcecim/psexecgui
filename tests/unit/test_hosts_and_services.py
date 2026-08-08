"""Testes de hosts.json e serviços (sem rede)."""

import json
from pathlib import Path

from services.ops import RustDeskService, build_psexec_argv, CredentialContext
from utils.hosts import load_hosts_file
from utils.redaction import REDACTED


def test_load_hosts(tmp_path: Path):
    p = tmp_path / "hosts.json"
    p.write_text(json.dumps({"hosts": ["PC-A", "PC-B", "PC-A", ""]}), encoding="utf-8")
    hosts = load_hosts_file(str(p))
    assert hosts == ["PC-A", "PC-B"]


def test_load_hosts_rejects_injection(tmp_path: Path):
    p = tmp_path / "hosts.json"
    p.write_text(
        json.dumps({"hosts": ["PC-OK", "bad&host", "also|bad"]}),
        encoding="utf-8",
    )
    hosts = load_hosts_file(str(p))
    assert hosts == ["PC-OK"]


def test_rustdesk_extract_id():
    assert RustDeskService.extract_id(["abc", "123456789"]) == "123456789"
    assert RustDeskService.extract_id(["nope"]) == ""


def test_build_psexec_argv_redaction_path():
    creds = CredentialContext(user="u", password="secret")
    real = build_psexec_argv(
        psexec_exe="PsExec.exe",
        host="PC",
        remote_argv=["cmd", "/c", "whoami"],
        creds=creds,
        include_password=True,
    )
    disp = build_psexec_argv(
        psexec_exe="PsExec.exe",
        host="PC",
        remote_argv=["cmd", "/c", "whoami"],
        creds=creds,
        include_password=False,
    )
    assert "secret" in real
    assert "secret" not in disp
    assert REDACTED in disp or "********" in disp
    creds.clear()
    assert creds.password == ""
