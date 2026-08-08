"""Testes de parse PsInfo / uninstall / product code."""

from utils.psinfo import (
    InstalledApp,
    build_uninstall_remote_cmd,
    extract_uninstall_executable,
    parse_disks_table,
    parse_psinfo_output,
    quote_uninstall_command,
)


SAMPLE_PSINFO = """
PsInfo v1.78 - Sysinternals
System information for \\\\PC-TEST:

Uptime:                    1 day
Kernel version:            Windows 10 Pro
Applications:
Foo App 1.0
Bar Tool 2.1
Volume Type Format Label Size Free Free
C: Fixed NTFS SYSTEM 476.10 GB 277.68 GB 58.3%
"""


def test_parse_psinfo_system_and_apps():
    result = parse_psinfo_output(SAMPLE_PSINFO, host="PC-TEST")
    assert result.host == "PC-TEST"
    assert "Kernel version" in result.system
    assert any("Foo App" in a for a in result.applications)


def test_parse_disks():
    rows = parse_disks_table(
        [
            "Volume Type Format Label Size Free Free",
            "C: Fixed NTFS SYSTEM 476.10 GB 277.68 GB 58.3%",
        ]
    )
    assert len(rows) == 1
    assert rows[0].volume == "C:"
    assert rows[0].free_pct == "58.3%"


def test_product_code_msi_uninstall():
    app = InstalledApp(
        display_name="Demo",
        version="1",
        publisher="Co",
        display_line="Demo 1",
        product_code="{12345678-1234-1234-1234-1234567890AB}",
        uninstall_string=r"MsiExec.exe /I{12345678-1234-1234-1234-1234567890AB}",
        quiet_uninstall_string="",
        is_msi=True,
        arch="64",
    )
    cmd = build_uninstall_remote_cmd(app)
    assert "msiexec /x" in cmd
    assert "{12345678-1234-1234-1234-1234567890AB}" in cmd
    assert "/qn" in cmd


def test_uninstall_string_with_spaces():
    us = r"C:\Program Files\WinRAR\uninstall.exe"
    exe = extract_uninstall_executable(us)
    assert exe == us
    quoted = quote_uninstall_command(us)
    assert quoted.startswith('"')


def test_exe_uninstall_with_extras():
    app = InstalledApp(
        display_name="WinRAR",
        version="6",
        publisher="win.rar",
        display_line="WinRAR 6",
        product_code="",
        uninstall_string=r"C:\Program Files\WinRAR\uninstall.exe",
        quiet_uninstall_string="",
        is_msi=False,
        arch="64",
    )
    cmd = build_uninstall_remote_cmd(app, "/S")
    assert "/S" in cmd
    assert "uninstall.exe" in cmd
