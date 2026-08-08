"""Testes de ExecutionResult e helpers Windows cmd."""

from datetime import datetime

from core.models import ExecutionResult, OperationStatus
from core.win_cmd import argv_to_cmd_line, quote_for_cmd


def test_execution_result_success():
    r = ExecutionResult(
        return_code=0,
        started_at=datetime(2024, 1, 1, 12, 0, 0),
        finished_at=datetime(2024, 1, 1, 12, 0, 5),
    )
    r.finalize()
    assert r.success
    assert r.status == OperationStatus.COMPLETED
    assert r.duration_seconds == 5.0


def test_execution_result_cancelled_remote_may_continue():
    r = ExecutionResult(return_code=1, cancelled=True, remote_may_continue=True)
    r.finalize()
    assert r.status == OperationStatus.CANCELLED
    assert not r.success
    assert r.remote_may_continue


def test_execution_result_timeout():
    r = ExecutionResult(timed_out=True, return_code=None)
    r.finalize()
    assert r.status == OperationStatus.TIMED_OUT


def test_quote_for_cmd_spaces():
    assert quote_for_cmd(r"C:\Program Files\a.exe") == r'"C:\Program Files\a.exe"'


def test_quote_for_cmd_simple():
    assert quote_for_cmd("ping") == "ping"


def test_argv_to_cmd_line():
    line = argv_to_cmd_line(["cmd.exe", "/c", r"C:\Program Files\x.exe"])
    assert "Program Files" in line
