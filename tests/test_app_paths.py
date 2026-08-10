from pathlib import Path

from ledger_reporter.app_paths import app_data_dir, resource_path


def test_data_dir_can_be_overridden(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LEDGER_REPORTER_DATA_DIR", str(tmp_path))
    assert app_data_dir() == tmp_path


def test_resource_path_stays_inside_resources() -> None:
    path = resource_path("fy2026_baseline.json")
    assert path.name == "fy2026_baseline.json"
    assert path.parent.name == "resources"
