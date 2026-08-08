"""Marcador para testes de integração Windows (não rodam no CI unitário)."""

import pytest

pytestmark = [pytest.mark.windows, pytest.mark.integration]


def test_placeholder_windows_only():
    """Reservado para testes que exigem winreg/PsExec reais."""
    import sys

    if sys.platform != "win32":
        pytest.skip("Windows only")
    assert True
