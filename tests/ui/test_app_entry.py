import sqlite3
from pathlib import Path

import ledger_reporter.__main__ as app_entry


class FakeApplication:
    def __init__(self, _arguments: list[str]) -> None:
        pass

    def setApplicationName(self, _name: str) -> None:
        pass

    def setOrganizationName(self, _name: str) -> None:
        pass


def test_corrupt_history_shows_startup_error_without_deleting_data(
    monkeypatch,
    tmp_path: Path,
) -> None:
    history_path = tmp_path / "history.sqlite3"
    original = b"not a sqlite database"
    history_path.write_bytes(original)
    shown: list[tuple[Path | None, Exception]] = []
    monkeypatch.setattr(app_entry, "QApplication", FakeApplication)
    monkeypatch.setattr(app_entry, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        app_entry,
        "_show_startup_error",
        lambda path, error: shown.append((path, error)),
        raising=False,
    )

    assert app_entry.main() == 1
    assert shown and shown[0][0] == history_path
    assert isinstance(shown[0][1], sqlite3.DatabaseError)
    assert history_path.read_bytes() == original


def test_startup_error_message_explains_safe_recovery(tmp_path: Path) -> None:
    history_path = tmp_path / "history.sqlite3"

    message = app_entry._startup_error_message(
        history_path,
        sqlite3.DatabaseError("file is not a database"),
    )

    assert str(history_path) in message
    assert "改名" in message
    assert "不会自动删除" in message
    assert "Excel/PNG" in message


def test_window_creation_failure_uses_application_error_instead_of_history_recovery(
    monkeypatch,
    tmp_path: Path,
) -> None:
    history_errors: list[tuple[Path | None, Exception]] = []
    application_errors: list[Exception] = []

    def fail_window(_service, _settings_path) -> None:
        raise RuntimeError("Qt initialization failed")

    monkeypatch.setattr(app_entry, "QApplication", FakeApplication)
    monkeypatch.setattr(app_entry, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(app_entry, "HistoryRepository", lambda _path: object())
    monkeypatch.setattr(app_entry, "MainWindow", fail_window)
    monkeypatch.setattr(
        app_entry,
        "_show_startup_error",
        lambda path, error: history_errors.append((path, error)),
    )
    monkeypatch.setattr(
        app_entry,
        "_show_application_startup_error",
        application_errors.append,
        raising=False,
    )

    assert app_entry.main() == 1
    assert history_errors == []
    assert len(application_errors) == 1


def test_application_error_message_does_not_blame_history() -> None:
    message = app_entry._application_startup_error_message(RuntimeError("Qt initialization failed"))

    assert "重新安装应用" in message
    assert "不要移动或删除历史文件" in message
    assert "history.sqlite3.backup" not in message


def test_source_settings_error_message_explains_safe_recovery(tmp_path: Path) -> None:
    settings_path = tmp_path / "source-fields.json"

    message = app_entry._source_settings_error_message(settings_path, ValueError("invalid JSON"))

    assert str(settings_path) in message
    assert "改名" in message
    assert "source-fields.json.backup" in message
    assert "不会自动删除" in message
    assert "历史" in message and "不受影响" in message
    assert "Excel/PNG" in message


def test_corrupt_source_settings_shows_settings_error_without_changing_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "source-fields.json"
    original = b"not json"
    settings_path.write_bytes(original)
    history_errors: list[tuple[Path | None, Exception]] = []
    settings_errors: list[tuple[Path, Exception]] = []
    application_errors: list[Exception] = []
    windows: list[tuple[object, ...]] = []

    def reject_window(*_args: object) -> None:
        windows.append(_args)
        raise AssertionError("配置加载失败后不应构造窗口")

    monkeypatch.setattr(app_entry, "QApplication", FakeApplication)
    monkeypatch.setattr(app_entry, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(app_entry, "HistoryRepository", lambda _path: object())
    monkeypatch.setattr(app_entry, "MainWindow", reject_window)
    monkeypatch.setattr(
        app_entry,
        "_show_startup_error",
        lambda path, error: history_errors.append((path, error)),
    )
    monkeypatch.setattr(
        app_entry,
        "_show_source_settings_error",
        lambda path, error: settings_errors.append((path, error)),
        raising=False,
    )
    monkeypatch.setattr(
        app_entry,
        "_show_application_startup_error",
        application_errors.append,
    )

    assert app_entry.main() == 1
    assert history_errors == []
    assert len(settings_errors) == 1
    assert settings_errors[0][0] == settings_path
    assert isinstance(settings_errors[0][1], ValueError)
    assert application_errors == []
    assert windows == []
    assert settings_path.read_bytes() == original


def test_smoke_ready_marker_is_written_after_window_processes_events(
    monkeypatch,
    tmp_path: Path,
) -> None:
    marker = tmp_path / "smoke" / "ready"
    events: list[str] = []
    captured: dict[str, object] = {"data_dir_calls": 0}
    settings = object()
    service = object()

    class SmokeApplication(FakeApplication):
        def processEvents(self) -> None:
            events.append("processEvents")

        def exec(self) -> int:
            events.append("exec")
            assert marker.read_text(encoding="ascii") == "ready\n"
            return 0

    class SmokeWindow:
        def __init__(self, received_service, settings_path: Path) -> None:
            captured["window_service"] = received_service
            captured["window_settings_path"] = settings_path

        def resize(self, _width: int, _height: int) -> None:
            events.append("resize")

        def show(self) -> None:
            events.append("show")

    monkeypatch.setenv("LEDGER_REPORTER_SMOKE_READY_FILE", str(marker))
    monkeypatch.setattr(app_entry, "QApplication", SmokeApplication)

    def fake_app_data_dir() -> Path:
        captured["data_dir_calls"] = int(captured["data_dir_calls"]) + 1
        return tmp_path / "data"

    def fake_repository(path: Path) -> object:
        captured["history_path"] = path
        return object()

    def fake_load_settings(path: Path) -> object:
        captured["loaded_settings_path"] = path
        return settings

    def fake_report_service(repository: object, received_settings: object) -> object:
        captured["service_repository"] = repository
        captured["service_settings"] = received_settings
        return service

    monkeypatch.setattr(app_entry, "app_data_dir", fake_app_data_dir)
    monkeypatch.setattr(app_entry, "HistoryRepository", fake_repository)
    monkeypatch.setattr(app_entry, "load_source_settings", fake_load_settings, raising=False)
    monkeypatch.setattr(app_entry, "ReportService", fake_report_service)
    monkeypatch.setattr(app_entry, "MainWindow", SmokeWindow)
    monkeypatch.setattr(app_entry, "_show_application_startup_error", lambda _error: None)

    assert app_entry.main() == 0
    assert events == ["resize", "show", "processEvents", "exec"]
    data_dir = tmp_path / "data"
    assert captured["data_dir_calls"] == 1
    assert captured["history_path"] == data_dir / "history.sqlite3"
    assert captured["loaded_settings_path"] == data_dir / "source-fields.json"
    assert captured["service_settings"] is settings
    assert captured["window_service"] is service
    assert captured["window_settings_path"] == data_dir / "source-fields.json"
