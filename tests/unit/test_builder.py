"""Testes do CommandBuilder / CommandSpec."""

import os
from pathlib import Path

from core.builder import CommandBuilder
from core.models import CommandSpec, is_robocopy_success
from utils.redaction import REDACTED


def _builder_with_host(tmp_path: Path | None = None) -> CommandBuilder:
    b = CommandBuilder()
    b.set_psexec_params(
        {
            "host": "PC-TEST",
            "psexec_path": r"C:\PSTools",
            "user": r"DOM\admin",
            "password": "SenhaSecreta99",
            "-h": True,
            "-accepteula": True,
            "-nobanner": True,
            "extra_args": "",
            "timeout": 0,
            "affinity": "",
            "priority": "",
            "group": "Nenhum",
            "session_interactive": False,
            "session_id": 0,
            "-c": False,
            "-f": False,
            "-d": False,
            "-e": False,
            "-v": False,
            "-s": False,
            "-l": False,
            "remote_cmd": "",
        }
    )
    return b


def test_display_never_contains_password():
    b = _builder_with_host()
    b.set_file_selection(
        {"mode": "file", "file": r"C:\Temp\setup.exe", "folder": None}
    )
    b.psexec_params["-c"] = True
    display = b.build_psexec()
    assert "SenhaSecreta99" not in display
    assert REDACTED in display or "********" in display


def test_execution_spec_contains_password_in_args_only():
    b = _builder_with_host()
    b.set_file_selection(
        {"mode": "file", "file": r"C:\Temp\setup.exe", "folder": None}
    )
    b.psexec_params["-c"] = True
    spec = b.build_psexec_spec()
    assert isinstance(spec, CommandSpec)
    assert "SenhaSecreta99" in spec.argv
    assert "SenhaSecreta99" not in spec.display_command


def test_prefer_no_password_when_empty():
    b = _builder_with_host()
    b.psexec_params["password"] = ""
    b.psexec_params["user"] = ""
    b.set_file_selection(
        {"mode": "file", "file": r"C:\Temp\setup.exe", "folder": None}
    )
    argv = b._base_psexec_argv(include_password=True)
    assert "-p" not in argv
    assert "-u" not in argv


def test_exe_with_spaces_in_path():
    b = _builder_with_host()
    path = r"C:\Program Files\My App\setup.exe"
    b.set_file_selection({"mode": "file", "file": path, "folder": None})
    b.psexec_params["-c"] = True
    spec = b.build_psexec_spec()
    assert path in spec.argv or any("setup.exe" in a for a in spec.argv)


def test_set_file_accepts_dict():
    b = CommandBuilder()
    b.set_file({"mode": "file", "file": r"C:\a.msi", "folder": None})
    assert b.file_path == r"C:\a.msi"
    assert b.selection_mode == "file"


def test_set_file_accepts_string():
    b = CommandBuilder()
    b.set_file(r"C:\a.exe")
    assert b.file_path == r"C:\a.exe"


def test_msi_folder_mode_uses_msi_options(tmp_path: Path):
    """Regressão: folder mode MSI deve propagar opções da UI (não só /i)."""
    folder = tmp_path / "pkg"
    folder.mkdir()
    msi = folder / "app.msi"
    msi.write_bytes(b"fake")

    b = _builder_with_host()
    b.set_file_selection(
        {"mode": "folder", "file": str(msi), "folder": str(folder)}
    )
    b.set_robocopy_params({"dest": "Temp", "switches": "/NFL"})
    b.set_msi_params(
        {
            "enable": True,
            "action": "/i (Install)",
            "interface": "/qn (Quiet)",
            "restart": "/norestart",
            "log": False,
            "log_file": "",
            "repair": "",
            "update": "",
        }
    )
    spec = b._build_psexec_folder_spec()
    joined = " ".join(spec.argv)
    assert "msiexec" in joined
    assert "/qn" in joined
    assert "/norestart" in joined
    assert "SenhaSecreta99" not in spec.display_command


def test_powershell_params():
    b = _builder_with_host()
    b.set_file_selection(
        {"mode": "file", "file": r"C:\scripts\run.ps1", "folder": None}
    )
    b.set_robocopy_params({"dest": "Temp", "switches": "/NFL"})
    b.set_powershell_params(
        {
            "NoProfile": True,
            "NoExit": False,
            "ExecutionPolicy": "Bypass",
            "WindowStyle": "",
            "Command": "",
            "EncodedCommand": "",
        }
    )
    spec = b._build_psexec_ps_script_spec()
    assert "powershell" in spec.argv
    assert "-NoProfile" in spec.argv
    assert "Bypass" in spec.argv


def test_bat_params():
    b = _builder_with_host()
    b.set_file_selection(
        {"mode": "file", "file": r"C:\scripts\run.bat", "folder": None}
    )
    b.set_robocopy_params({"dest": "Temp", "switches": "/NFL"})
    b.set_cmd_params({"/C": True, "/K": False, "/Q": False, "/D": False, "/S": False, "Command": ""})
    spec = b._build_psexec_bat_script_spec()
    assert "cmd" in spec.argv
    assert "/C" in spec.argv


def test_manual_remote_cmd():
    b = _builder_with_host()
    b.set_file_selection(None)
    b.file_path = None
    b.folder_path = None
    b.psexec_params["remote_cmd"] = "ipconfig /all"
    display = b.build_psexec()
    assert "ipconfig" in display
    assert "SenhaSecreta99" not in display


def test_robocopy_success_codes():
    assert is_robocopy_success(0)
    assert is_robocopy_success(1)
    assert is_robocopy_success(7)
    assert not is_robocopy_success(8)
    assert not is_robocopy_success(16)


def test_psexec_flags():
    b = _builder_with_host()
    b.psexec_params["-s"] = True
    b.psexec_params["-d"] = True
    argv = b._base_psexec_argv(include_password=False)
    assert "-s" in argv
    assert "-d" in argv
    assert "-h" in argv


def test_unc_robocopy_dest(tmp_path: Path):
    src = tmp_path / "file.txt"
    src.write_text("x", encoding="utf-8")
    b = _builder_with_host()
    b.set_file_selection({"mode": "file", "file": str(src), "folder": None})
    b.set_robocopy_params({"dest": r"C:\Installers", "switches": "/NFL /NDL"})
    spec = b.build_robocopy_spec()
    assert spec is not None
    assert r"\\PC-TEST\C$\Installers" in " ".join(spec.argv)
