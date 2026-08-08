"""Testes do ApplicationCatalog."""

import json
from pathlib import Path

import utils.app_catalog as catalog
from utils.app_catalog import (
    find_catalog_entry,
    validate_catalog_data,
)
from utils.psinfo import InstalledApp


def test_validate_ok():
    data = {
        "applications": [
            {
                "displayName": "WinRAR",
                "publisher": "win.rar GmbH",
                "match": ["WinRAR"],
                "uninstallArgs": "/S",
                "architecture": "x64",
                "requiresElevation": True,
                "requiresReboot": False,
            }
        ]
    }
    result = validate_catalog_data(data)
    assert result.ok
    assert len(result.entries) == 1


def test_validate_invalid_root():
    result = validate_catalog_data([])
    assert not result.ok


def test_validate_skips_bad_entry():
    data = {
        "applications": [
            {"displayName": "Ok", "match": ["Ok"]},
            "not-an-object",
            {"displayName": "", "match": ["x"]},
            {"displayName": "NoMatch"},
        ]
    }
    result = validate_catalog_data(data)
    assert len(result.entries) == 1
    assert result.warnings


def test_matching_prefers_longer_pattern(monkeypatch, tmp_path: Path):
    cat = {
        "applications": [
            {"displayName": "Driver", "match": ["Driver"], "uninstallArgs": "/S"},
            {
                "displayName": "IObit Driver Booster",
                "match": ["Driver Booster"],
                "uninstallArgs": "/VERYSILENT",
            },
        ]
    }
    path = tmp_path / "ApplicationCatalog.json"
    path.write_text(json.dumps(cat), encoding="utf-8")
    monkeypatch.setattr(catalog, "resolve_catalog_path", lambda: str(path))
    catalog._cached_path = None
    catalog._cached_mtime = None
    catalog._cached_entries = []

    entry = find_catalog_entry("IObit Driver Booster 10.0")
    assert entry is not None
    assert entry["displayName"] == "IObit Driver Booster"


def test_matching_publisher_tiebreak(monkeypatch, tmp_path: Path):
    cat = {
        "applications": [
            {
                "displayName": "App",
                "publisher": "Vendor A",
                "match": ["App"],
                "uninstallArgs": "/A",
            },
            {
                "displayName": "App",
                "publisher": "Vendor B",
                "match": ["App"],
                "uninstallArgs": "/B",
            },
        ]
    }
    path = tmp_path / "ApplicationCatalog.json"
    path.write_text(json.dumps(cat), encoding="utf-8")
    monkeypatch.setattr(catalog, "resolve_catalog_path", lambda: str(path))
    catalog._cached_path = None
    catalog._cached_mtime = None
    catalog._cached_entries = []

    entry = find_catalog_entry("App 1.0", "Vendor B Inc")
    assert entry is not None
    assert entry["uninstallArgs"] == "/B"


def test_catalog_uninstall_args_msi_ignored(monkeypatch, tmp_path: Path):
    from utils.app_catalog import catalog_uninstall_args

    cat = {
        "applications": [
            {"displayName": "Thing", "match": ["Thing"], "uninstallArgs": "/S"}
        ]
    }
    path = tmp_path / "ApplicationCatalog.json"
    path.write_text(json.dumps(cat), encoding="utf-8")
    monkeypatch.setattr(catalog, "resolve_catalog_path", lambda: str(path))
    catalog._cached_path = None
    catalog._cached_mtime = None
    catalog._cached_entries = []

    app = InstalledApp(
        display_name="Thing",
        version="1",
        publisher="X",
        display_line="Thing 1",
        product_code="{AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE}",
        uninstall_string="msiexec /x {...}",
        quiet_uninstall_string="",
        is_msi=True,
        arch="64",
    )
    assert catalog_uninstall_args(app) == ""
