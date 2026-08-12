from PySide6.QtCore import QProcess
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ledger_reporter.uninstall import UninstallTargets, write_uninstall_helper


class UninstallDialog(QDialog):
    def __init__(self, targets: UninstallTargets, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.targets = targets
        self.setWindowTitle("卸载台账报表生成器")
        self.setMinimumWidth(620)

        self.message_label = QLabel(
            "确认后应用将退出，并删除应用本体及以下应用内部数据。\n"
            "系统安装会请求管理员授权；取消系统授权则不会卸载。\n"
            "不会删除用户导出的 Excel/PNG。"
        )
        self.message_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)
        layout.addWidget(self.message_label)
        labels = ("应用", "数据", "缓存", "偏好设置", "日志", "临时数据")
        for label, path in zip(labels, targets.paths, strict=True):
            item = QLabel(f"{label}：{path}")
            item.setTextInteractionFlags(item.textInteractionFlags())
            item.setWordWrap(True)
            layout.addWidget(item)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self.cancel_button.setText("取消")
        self.uninstall_button = QPushButton("卸载")
        self.uninstall_button.setObjectName("destructiveButton")
        buttons.addButton(self.uninstall_button, QDialogButtonBox.ButtonRole.DestructiveRole)
        buttons.rejected.connect(self.reject)
        self.uninstall_button.clicked.connect(self.confirm_uninstall)
        layout.addWidget(buttons)

    def confirm_uninstall(self) -> None:
        helper = None
        try:
            helper = write_uninstall_helper(self.targets)
            launch_result = QProcess.startDetached("/bin/sh", [str(helper)])
            started = launch_result[0] if isinstance(launch_result, tuple) else launch_result
        except Exception as exc:  # noqa: BLE001 - UI boundary reports launcher failures.
            if helper is not None:
                helper.unlink(missing_ok=True)
            QMessageBox.critical(self, "无法启动卸载", str(exc) or exc.__class__.__name__)
            return
        if not started:
            helper.unlink(missing_ok=True)
            QMessageBox.critical(self, "无法启动卸载", "系统未能启动卸载助手，请重试。")
            return
        self.accept()
        QApplication.quit()
