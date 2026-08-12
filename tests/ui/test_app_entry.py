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

    def fail_window(_service) -> None:
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
