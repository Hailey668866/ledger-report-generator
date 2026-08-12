from pathlib import Path

from PySide6.QtCore import QThread

from ledger_reporter.ui.main_window import MainWindow
from ledger_reporter.uninstall import UninstallTargets


class FakeReportService:
    pass


def _targets(tmp_path: Path) -> UninstallTargets:
    return UninstallTargets.for_home(
        tmp_path,
        tmp_path / "Applications" / "台账报表生成器.app",
        tmp_path / "temp",
    )


def test_uninstall_action_is_disabled_outside_an_installed_app(
    qtbot,
    monkeypatch,
) -> None:
    monkeypatch.setattr("ledger_reporter.ui.main_window.default_uninstall_targets", lambda: None)

    window = MainWindow(FakeReportService())
    qtbot.addWidget(window)

    assert window.application_menu.title() == "应用"
    assert window.uninstall_action.text() == "卸载台账报表生成器…"
    assert not window.uninstall_action.isEnabled()


def test_uninstall_action_opens_confirmation_dialog(
    qtbot,
    monkeypatch,
    tmp_path: Path,
) -> None:
    targets = _targets(tmp_path)
    opened: list[tuple[UninstallTargets, MainWindow]] = []

    class FakeUninstallDialog:
        def __init__(self, actual_targets, parent) -> None:
            opened.append((actual_targets, parent))

        def exec(self) -> None:
            pass

    monkeypatch.setattr(
        "ledger_reporter.ui.main_window.default_uninstall_targets",
        lambda: targets,
    )
    monkeypatch.setattr(
        "ledger_reporter.ui.main_window.UninstallDialog",
        FakeUninstallDialog,
    )
    window = MainWindow(FakeReportService())
    qtbot.addWidget(window)

    assert window.uninstall_action.isEnabled()
    window.uninstall_action.trigger()
    assert opened == [(targets, window)]


def test_uninstall_stays_disabled_while_background_work_is_running(
    qtbot,
    monkeypatch,
    tmp_path: Path,
) -> None:
    targets = _targets(tmp_path)
    monkeypatch.setattr(
        "ledger_reporter.ui.main_window.default_uninstall_targets",
        lambda: targets,
    )
    window = MainWindow(FakeReportService())
    qtbot.addWidget(window)
    thread = QThread(window)
    thread.start()
    window.validation_thread = thread

    window._restore_idle_controls()
    assert not window.uninstall_action.isEnabled()

    thread.quit()
    assert thread.wait(1000)
    window.on_validation_finished()
    assert window.uninstall_action.isEnabled()
