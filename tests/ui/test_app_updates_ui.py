from pathlib import Path
from threading import Event
from time import monotonic

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QPushButton

from ledger_reporter.io.source_settings import DEFAULT_SOURCE_SETTINGS
from ledger_reporter.services.app_updates import ReleaseUpdate, UpdateCancelled
from ledger_reporter.ui import main_window as main_window_module
from ledger_reporter.ui.main_window import MainWindow
from ledger_reporter.ui.workers import UpdateDownloadWorker


class Service:
    source_settings = DEFAULT_SOURCE_SETTINGS


def test_window_has_manual_update_action(qtbot) -> None:
    window = MainWindow(Service())
    qtbot.addWidget(window)

    assert window.update_action.text() == "检查更新…"
    assert window.update_check_thread is None


def test_startup_update_check_is_scheduled_once(qtbot, monkeypatch) -> None:
    scheduled = []
    monkeypatch.setattr(
        main_window_module.QTimer,
        "singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )
    window = MainWindow(Service(), auto_check_updates=True)
    qtbot.addWidget(window)

    assert len(scheduled) == 1
    assert scheduled[0][0] == 0


def test_manual_check_reports_current_version(qtbot, monkeypatch) -> None:
    messages = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "information",
        lambda *args: messages.append(args[2]),
    )
    window = MainWindow(Service(), update_checker=lambda _version: None)
    qtbot.addWidget(window)

    window.start_update_check(manual=True)
    qtbot.waitUntil(lambda: window.update_check_thread is None)

    assert messages == ["当前已是最新版。"]


def test_automatic_failure_is_silent_and_manual_failure_is_visible(qtbot, monkeypatch) -> None:
    warnings = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "warning",
        lambda *args: warnings.append(args[2]),
    )
    window = MainWindow(Service())
    qtbot.addWidget(window)

    window.update_check_manual = False
    window.on_update_check_failed("离线")
    window.update_check_manual = True
    window.on_update_check_failed("离线")

    assert warnings == ["离线"]


def test_new_version_confirmation_starts_download(qtbot, monkeypatch, tmp_path: Path) -> None:
    update = ReleaseUpdate("0.2.0", "v0.2.0", "dmg", "sha", "修复导出")
    started = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    window = MainWindow(Service(), update_cache_dir=tmp_path)
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "start_update_download", lambda value: started.append(value))

    window.on_update_check_succeeded(update)

    assert started == [update]


def test_download_worker_reports_progress_and_supports_cancellation(tmp_path: Path) -> None:
    update = ReleaseUpdate("0.2.0", "v0.2.0", "dmg", "sha", "")
    events = []

    def downloader(received_update, cache_dir, *, progress, cancelled):
        assert received_update is update
        assert cache_dir == tmp_path
        progress(5, 10)
        events.append(cancelled())
        return tmp_path / "update.dmg"

    worker = UpdateDownloadWorker(downloader, update, tmp_path)
    worker.progress.connect(lambda received, total: events.append((received, total)))
    worker.succeeded.connect(lambda path: events.append(path))
    worker.cancel()

    worker.run()

    assert events == [(5, 10), True, tmp_path / "update.dmg"]


def test_window_download_uses_configured_cache(qtbot, monkeypatch, tmp_path: Path) -> None:
    update = ReleaseUpdate("0.2.0", "v0.2.0", "dmg", "sha", "")
    calls = []
    dmg = tmp_path / "update.dmg"

    def downloader(received_update, cache_dir, **_kwargs):
        calls.append((received_update, cache_dir))
        return dmg

    window = MainWindow(Service(), update_downloader=downloader, update_cache_dir=tmp_path)
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "open_update_installer", lambda path: calls.append(path))

    window.start_update_download(update)
    qtbot.waitUntil(lambda: window.update_download_thread is None)

    assert calls == [(update, tmp_path), dmg]


def test_download_cancel_button_reaches_running_worker(qtbot, tmp_path: Path) -> None:
    update = ReleaseUpdate("0.2.0", "v0.2.0", "dmg", "sha", "")
    started = Event()
    stopped = Event()

    def downloader(_update, _cache_dir, *, cancelled, **_kwargs):
        started.set()
        deadline = monotonic() + 1
        while not cancelled() and monotonic() < deadline:
            stopped.wait(0.01)
        if cancelled():
            stopped.set()
        raise UpdateCancelled("更新下载已取消。")

    window = MainWindow(Service(), update_downloader=downloader, update_cache_dir=tmp_path)
    qtbot.addWidget(window)
    window.start_update_download(update)
    assert started.wait(1)
    assert window.update_progress is not None
    cancel_button = next(
        button
        for button in window.update_progress.findChildren(QPushButton)
        if button.text() == "取消"
    )

    qtbot.mouseClick(cancel_button, Qt.MouseButton.LeftButton)
    prompt_cancel = stopped.wait(0.2)
    if window.update_download_worker is not None:
        window.update_download_worker.cancel()
    qtbot.waitUntil(lambda: window.update_download_thread is None)

    assert prompt_cancel


def test_verified_dmg_is_opened_with_macos_open(qtbot, monkeypatch, tmp_path: Path) -> None:
    calls = []
    dmg = tmp_path / "update.dmg"
    dmg.write_bytes(b"verified")
    monkeypatch.setattr(main_window_module.sys, "platform", "darwin")
    monkeypatch.setattr(
        main_window_module.subprocess,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    window = MainWindow(Service(), auto_check_updates=False)
    qtbot.addWidget(window)

    window.open_update_installer(dmg)

    assert calls == [((["open", str(dmg)],), {"check": True})]
