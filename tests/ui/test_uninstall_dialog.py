from pathlib import Path

from PySide6.QtWidgets import QDialog

from ledger_reporter.ui.uninstall_dialog import UninstallDialog
from ledger_reporter.uninstall import UninstallTargets


def _targets(tmp_path: Path) -> UninstallTargets:
    return UninstallTargets.for_home(
        tmp_path,
        tmp_path / "Applications" / "台账报表生成器.app",
        tmp_path / "temp",
    )


def test_dialog_lists_every_target_and_export_files_are_preserved(qtbot, tmp_path: Path) -> None:
    targets = _targets(tmp_path)

    dialog = UninstallDialog(targets)
    qtbot.addWidget(dialog)
    text = " ".join(label.text() for label in dialog.findChildren(type(dialog.message_label)))

    for target in targets.paths:
        assert str(target) in text
    assert "不会删除用户导出的 Excel/PNG" in text
    assert "应用将退出" in text
    assert "取消系统授权则不会卸载" in text
    assert dialog.uninstall_button.text() == "卸载"


def test_cancel_does_not_launch_helper(qtbot, monkeypatch, tmp_path: Path) -> None:
    launched: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        "ledger_reporter.ui.uninstall_dialog.QProcess.startDetached",
        lambda command, arguments: launched.append((command, arguments)),
    )
    dialog = UninstallDialog(_targets(tmp_path))
    qtbot.addWidget(dialog)

    dialog.reject()

    assert launched == []


def test_confirm_launches_only_generated_helper_and_quits(
    qtbot,
    monkeypatch,
    tmp_path: Path,
) -> None:
    helper = tmp_path / "uninstall.sh"
    launched: list[tuple[str, list[str]]] = []
    quit_calls: list[bool] = []
    targets = _targets(tmp_path)
    monkeypatch.setattr(
        "ledger_reporter.ui.uninstall_dialog.write_uninstall_helper",
        lambda actual: helper if actual == targets else None,
    )
    monkeypatch.setattr(
        "ledger_reporter.ui.uninstall_dialog.QProcess.startDetached",
        lambda command, arguments: launched.append((command, arguments)) or True,
    )
    monkeypatch.setattr(
        "ledger_reporter.ui.uninstall_dialog.QApplication.quit",
        lambda: quit_calls.append(True),
    )
    dialog = UninstallDialog(targets)
    qtbot.addWidget(dialog)

    dialog.confirm_uninstall()

    assert launched == [("/bin/sh", [str(helper)])]
    assert quit_calls == [True]
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_failed_launch_removes_helper_and_keeps_application_open(
    qtbot,
    monkeypatch,
    tmp_path: Path,
) -> None:
    helper = tmp_path / "uninstall.sh"
    helper.write_text("#!/bin/sh\n", encoding="utf-8")
    messages: list[tuple[str, str]] = []
    quit_calls: list[bool] = []
    monkeypatch.setattr(
        "ledger_reporter.ui.uninstall_dialog.write_uninstall_helper",
        lambda _targets: helper,
    )
    monkeypatch.setattr(
        "ledger_reporter.ui.uninstall_dialog.QProcess.startDetached",
        lambda _command, _arguments: (False, -1),
    )
    monkeypatch.setattr(
        "ledger_reporter.ui.uninstall_dialog.QMessageBox.critical",
        lambda _parent, title, message: messages.append((title, message)),
    )
    monkeypatch.setattr(
        "ledger_reporter.ui.uninstall_dialog.QApplication.quit",
        lambda: quit_calls.append(True),
    )
    dialog = UninstallDialog(_targets(tmp_path))
    qtbot.addWidget(dialog)

    dialog.confirm_uninstall()

    assert not helper.exists()
    assert messages == [("无法启动卸载", "系统未能启动卸载助手，请重试。")]
    assert quit_calls == []
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_cancel_button_uses_chinese_label(qtbot, tmp_path: Path) -> None:
    dialog = UninstallDialog(_targets(tmp_path))
    qtbot.addWidget(dialog)

    assert dialog.cancel_button.text() == "取消"
