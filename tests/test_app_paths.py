import sys
from pathlib import Path

import pytest

from ledger_reporter.app_paths import APP_ID, app_data_dir, resource_path


def test_data_dir_can_be_overridden(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LEDGER_REPORTER_DATA_DIR", str(tmp_path))
    assert app_data_dir() == tmp_path


def test_resource_path_stays_inside_resources() -> None:
    path = resource_path("fy2026_baseline.json")
    assert path.name == "fy2026_baseline.json"
    assert path.parent.name == "resources"


def test_resource_path_rejects_escaping_resources_directory() -> None:
    with pytest.raises(ValueError):
        resource_path("../escape.json")


def test_resource_path_uses_pyinstaller_bundle_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert resource_path("file.json") == tmp_path / "ledger_reporter" / "resources" / "file.json"


def test_empty_local_app_data_falls_back_to_home_directory(monkeypatch) -> None:
    monkeypatch.delenv("LEDGER_REPORTER_DATA_DIR", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", "")
    assert app_data_dir() == Path.home() / APP_ID
