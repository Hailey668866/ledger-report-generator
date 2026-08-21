import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from ledger_reporter import __version__
from ledger_reporter.app_paths import app_cache_dir, resource_path
from ledger_reporter.domain.models import ReportBundle, SourceInspection
from ledger_reporter.exporters.excel import export_excel
from ledger_reporter.exporters.png import export_pngs
from ledger_reporter.io.source_settings import save_source_settings
from ledger_reporter.services.app_updates import ReleaseUpdate, check_for_update, download_update
from ledger_reporter.ui.fonts import ui_font
from ledger_reporter.ui.preview_dialog import PreviewDialog
from ledger_reporter.ui.source_picker import SourcePicker
from ledger_reporter.ui.source_settings_dialog import SourceSettingsDialog
from ledger_reporter.ui.uninstall_dialog import UninstallDialog
from ledger_reporter.ui.workers import (
    GenerationWorker,
    UpdateCheckWorker,
    UpdateDownloadWorker,
    ValidationWorker,
)
from ledger_reporter.uninstall import default_uninstall_targets

APP_STYLESHEET = """
QMainWindow, QWidget#mainBody {
    background: #f6f8f6;
    color: #26372e;
    font-size: 13px;
}
QFrame#brandBar {
    background: #ffffff;
    border-bottom: 1px solid #e2e7e4;
}
QLabel#brandTitle {
    font-size: 16px;
    font-weight: 700;
    color: #1e3027;
}
QLabel#readyDot {
    background: #aeb9b2;
    border-radius: 4px;
}
QLabel#readyDot[ready="true"] {
    background: #2d955e;
}
QLabel#statusLabel {
    color: #627168;
    font-size: 11px;
}
QLabel#sectionTitle {
    font-size: 12px;
    font-weight: 700;
    color: #627168;
}
QWidget#sourcePicker {
    background: #ffffff;
    border: 1px solid #d8e0db;
    border-radius: 6px;
}
QLabel#sourceIcon {
    background: #e5f1e9;
    color: #197345;
    border-radius: 5px;
    font-size: 12px;
    font-weight: 800;
}
QLabel#sourceTitle {
    font-weight: 700;
    color: #26372e;
}
QLabel#sourcePath {
    color: #77847c;
    font-size: 11px;
}
QFrame#periodCard {
    background: #eef4f0;
    border-left: 3px solid #268452;
}
QLabel#periodLabel {
    color: #738078;
    font-size: 10px;
}
QLabel#periodValue {
    color: #25382d;
    font-size: 12px;
    font-weight: 700;
}
QLabel#planDetail {
    color: #77847c;
    font-size: 10px;
}
QFrame#resultBar {
    border-top: 1px solid #e3e8e5;
}
QLabel#resultTitle {
    color: #24372d;
    font-size: 12px;
    font-weight: 700;
}
QLabel#resultMeta {
    color: #7a867f;
    font-size: 10px;
}
QPushButton {
    min-height: 34px;
    padding: 0 14px;
    border-radius: 5px;
    border: 1px solid #cbd6d0;
    background: #ffffff;
    color: #30443a;
    font-weight: 600;
}
QPushButton:hover {
    background: #f3f7f4;
    border-color: #9caf9f;
}
QPushButton:pressed {
    background: #e8f0eb;
}
QPushButton:disabled {
    color: #9aa49e;
    background: #f1f3f2;
    border-color: #dde3df;
}
QPushButton#primaryButton {
    border-color: #9caf9f;
    color: #236c46;
}
QPushButton#primaryButton:hover {
    background: #eef6f1;
}
QPushButton#generateButton {
    min-height: 42px;
    background: #177746;
    border-color: #177746;
    color: #ffffff;
}
QPushButton#generateButton:hover {
    background: #11663b;
}
QPushButton#previewButton {
    border-color: #86b79c;
    color: #166c40;
    font-weight: 700;
}
QPushButton#destructiveButton {
    background: #c43d4b;
    border-color: #c43d4b;
    color: #ffffff;
}
QPushButton#secondaryButton {
    min-width: 94px;
}
QTableWidget#previewTable {
    background: #ffffff;
    border: 1px solid #d9e0e8;
    gridline-color: #b7c0bb;
}
"""


def _choose_png_output_directory(parent: QWidget) -> Path | None:
    dialog = QFileDialog(parent, "选择图片保存文件夹")
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setLabelText(QFileDialog.DialogLabel.Accept, "选择此文件夹")
    dialog.setLabelText(QFileDialog.DialogLabel.Reject, "取消")
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    selected = dialog.selectedFiles()
    return Path(selected[0]) if selected else None


class MainWindow(QMainWindow):
    def __init__(
        self,
        report_service: object,
        source_settings_path: Path | None = None,
        *,
        current_version: str = __version__,
        update_cache_dir: Path | None = None,
        update_checker: Callable[[str], ReleaseUpdate | None] = check_for_update,
        update_downloader: Callable[..., Path] = download_update,
        auto_check_updates: bool = False,
    ) -> None:
        super().__init__()
        self.report_service = report_service
        self.source_settings_path = source_settings_path
        self.bundle: ReportBundle | None = None
        self.inspection: SourceInspection | None = None
        self.validation_thread: QThread | None = None
        self.validation_worker: ValidationWorker | None = None
        self.generation_thread: QThread | None = None
        self.generation_worker: GenerationWorker | None = None
        self.current_version = current_version
        self.update_cache_dir = update_cache_dir or app_cache_dir() / "updates"
        self.update_checker = update_checker
        self.update_downloader = update_downloader
        self.update_check_thread: QThread | None = None
        self.update_check_worker: UpdateCheckWorker | None = None
        self.update_check_manual = False
        self.update_download_thread: QThread | None = None
        self.update_download_worker: UpdateDownloadWorker | None = None
        self.update_progress: QProgressDialog | None = None

        self.setWindowTitle("台账报表生成器")
        self.setMinimumSize(720, 520)
        self.setFont(ui_font(10))
        self.setStyleSheet(APP_STYLESHEET)
        self.funds_picker = SourcePicker("资金台账")
        self.operations_picker = SourcePicker("运营台账")
        self.validate_button = QPushButton("校验数据源")
        self.validate_button.setObjectName("primaryButton")
        self.validate_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
        )
        self.source_settings_button = QPushButton("字段设置")
        self.source_settings_button.setObjectName("secondaryButton")
        self.generate_button = QPushButton("生成两张报表")
        self.generate_button.setObjectName("generateButton")
        self.generate_button.setMinimumHeight(42)
        self.generate_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.preview_button = QPushButton("预览报表")
        self.preview_button.setObjectName("previewButton")
        self.preview_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        )
        self.excel_button = QPushButton("导出 Excel")
        self.excel_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        self.png_button = QPushButton("导出图片")
        self.png_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        self.status_label = QLabel("请选择两份数据源")
        self.status_label.setObjectName("statusLabel")
        self.status_dot = QLabel()
        self.status_dot.setObjectName("readyDot")
        self.status_dot.setProperty("ready", False)
        self.status_dot.setFixedSize(8, 8)

        self.uninstall_targets = default_uninstall_targets()
        self.application_menu = self.menuBar().addMenu("应用")
        self.update_action = self.application_menu.addAction("检查更新…")
        self.update_action.triggered.connect(lambda: self.start_update_check(manual=True))
        self.application_menu.addSeparator()
        self.uninstall_action = self.application_menu.addAction("卸载台账报表生成器…")
        self.uninstall_action.setEnabled(self.uninstall_targets is not None)
        self.uninstall_action.triggered.connect(self.open_uninstall_dialog)

        for button in (
            self.validate_button,
            self.generate_button,
            self.preview_button,
            self.excel_button,
            self.png_button,
        ):
            button.setEnabled(False)

        root = QWidget()
        root.setObjectName("mainBody")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        brand_bar = QFrame()
        brand_bar.setObjectName("brandBar")
        brand_bar.setFixedHeight(58)
        brand_layout = QHBoxLayout(brand_bar)
        brand_layout.setContentsMargins(20, 0, 20, 0)
        brand_layout.setSpacing(10)
        self.brand_icon = QLabel()
        self.brand_icon.setFixedSize(34, 34)
        self.brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QPixmap(str(resource_path("app-icon.png")))
        self.brand_icon.setPixmap(
            icon.scaled(
                34,
                34,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.brand_title = QLabel("台账报表生成器")
        self.brand_title.setObjectName("brandTitle")
        brand_layout.addWidget(self.brand_icon)
        brand_layout.addWidget(self.brand_title)
        brand_layout.addStretch(1)
        brand_layout.addWidget(self.status_dot)
        brand_layout.addWidget(self.status_label)
        root_layout.addWidget(brand_bar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 22, 24, 22)
        body_layout.setSpacing(11)
        source_title = QLabel("数据源")
        source_title.setObjectName("sectionTitle")
        source_title_row = QHBoxLayout()
        source_title_row.addWidget(source_title)
        source_title_row.addStretch(1)
        source_title_row.addWidget(self.source_settings_button)
        body_layout.addLayout(source_title_row)
        body_layout.addWidget(self.funds_picker)
        body_layout.addWidget(self.operations_picker)

        self.period_panel = QWidget()
        period_layout = QHBoxLayout(self.period_panel)
        period_layout.setContentsMargins(0, 4, 0, 0)
        period_layout.setSpacing(9)
        summary_card, self.summary_period_value = self._period_card("经营汇总")
        weekly_card, self.weekly_period_value = self._period_card("自营项目")
        period_layout.addWidget(summary_card, 1)
        period_layout.addWidget(weekly_card, 1)
        self.period_panel.hide()
        body_layout.addWidget(self.period_panel)

        self.plan_detail_label = QLabel()
        self.plan_detail_label.setObjectName("planDetail")
        self.plan_detail_label.hide()
        body_layout.addWidget(self.plan_detail_label)

        workflow = QHBoxLayout()
        workflow.setSpacing(9)
        workflow.addWidget(self.validate_button)
        workflow.addWidget(self.generate_button, 1)
        body_layout.addLayout(workflow)

        self.result_bar = QFrame()
        self.result_bar.setObjectName("resultBar")
        result_layout = QHBoxLayout(self.result_bar)
        result_layout.setContentsMargins(0, 14, 0, 0)
        result_layout.setSpacing(8)
        result_copy = QVBoxLayout()
        result_copy.setContentsMargins(0, 0, 0, 0)
        result_copy.setSpacing(3)
        self.result_title = QLabel("报表已生成")
        self.result_title.setObjectName("resultTitle")
        self.result_meta = QLabel("2 张表 · 数据校验通过")
        self.result_meta.setObjectName("resultMeta")
        result_copy.addWidget(self.result_title)
        result_copy.addWidget(self.result_meta)
        result_layout.addLayout(result_copy, 1)
        result_layout.addWidget(self.preview_button)
        result_layout.addWidget(self.excel_button)
        result_layout.addWidget(self.png_button)
        self.result_bar.hide()
        body_layout.addWidget(self.result_bar)
        body_layout.addStretch(1)
        root_layout.addWidget(body, 1)
        self.setCentralWidget(root)

        self.funds_picker.path_changed.connect(self.refresh_ready)
        self.operations_picker.path_changed.connect(self.refresh_ready)
        self.validate_button.clicked.connect(self.start_validation)
        self.source_settings_button.clicked.connect(self.open_source_settings)
        self.generate_button.clicked.connect(self.start_generation)
        self.preview_button.clicked.connect(self.open_preview)
        self.excel_button.clicked.connect(self.export_excel_file)
        self.png_button.clicked.connect(self.export_png_files)

        if auto_check_updates:
            QTimer.singleShot(0, lambda: self.start_update_check(manual=False))

    @staticmethod
    def _period_card(label: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("periodCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 9, 12, 10)
        layout.setSpacing(3)
        title = QLabel(label)
        title.setObjectName("periodLabel")
        value = QLabel()
        value.setObjectName("periodValue")
        layout.addWidget(title)
        layout.addWidget(value)
        return card, value

    def _set_ready_status(self, text: str, *, ready: bool) -> None:
        self.status_label.setText(text)
        self.status_dot.setProperty("ready", ready)
        self.status_dot.style().unpolish(self.status_dot)
        self.status_dot.style().polish(self.status_dot)

    def _sources_ready(self) -> bool:
        return all(
            picker.path is not None
            and picker.path.is_file()
            and picker.path.suffix.lower() == ".xlsx"
            for picker in (self.funds_picker, self.operations_picker)
        )

    def _set_source_pickers_enabled(self, enabled: bool) -> None:
        self.funds_picker.setEnabled(enabled)
        self.operations_picker.setEnabled(enabled)
        self.source_settings_button.setEnabled(enabled)

    def _disable_result_actions(self) -> None:
        for button in (self.preview_button, self.excel_button, self.png_button):
            button.setEnabled(False)

    def _background_task_running(self) -> bool:
        for thread in (self.validation_thread, self.generation_thread):
            if thread is None:
                continue
            try:
                if thread.isRunning():
                    return True
            except RuntimeError:
                continue
        return False

    def _restore_idle_controls(self) -> None:
        if self._background_task_running():
            self.uninstall_action.setEnabled(False)
            return
        ready = self._sources_ready()
        self._set_source_pickers_enabled(True)
        self.validate_button.setEnabled(ready)
        self.generate_button.setEnabled(ready and self.inspection is not None)
        self.uninstall_action.setEnabled(self.uninstall_targets is not None)

    def refresh_ready(self, _path: object | None = None) -> None:
        ready = self._sources_ready()
        self.bundle = None
        self.inspection = None
        self.validate_button.setEnabled(ready)
        self.generate_button.setEnabled(False)
        self._disable_result_actions()
        self.period_panel.hide()
        self.plan_detail_label.hide()
        self.result_bar.hide()
        self._set_ready_status("可以校验数据源" if ready else "请选择两份数据源", ready=False)

    def on_validation_succeeded(self, inspection: SourceInspection) -> None:
        self.inspection = inspection
        plan = inspection.update_plan
        added = "、".join(item.label for item in plan.new_periods) or "无"
        refreshed = "、".join(item.label for item in plan.refresh_periods) or "无"
        latest = plan.latest
        week_name = latest.label.split("（", 1)[0]
        self.summary_period_value.setText(f"{inspection.fiscal_year}财年，截至 {latest.end:%m-%d}")
        self.weekly_period_value.setText(f"{latest.start.year}年{latest.start.month}月 {week_name}")
        self.plan_detail_label.setText(f"本次新增 {added} · 回刷 {refreshed}")
        self.period_panel.show()
        self.plan_detail_label.show()
        self._set_ready_status("数据源已就绪", ready=True)
        self.generate_button.setEnabled(not self._background_task_running())

    def on_validation_failed(self, message: str) -> None:
        self.inspection = None
        self.generate_button.setEnabled(False)
        self._set_ready_status("数据源校验失败", ready=False)
        QMessageBox.critical(self, "数据源校验失败", message)

    def on_generation_succeeded(self, bundle: ReportBundle) -> None:
        self.bundle = bundle
        self._set_ready_status("数据源已就绪", ready=True)
        self.result_bar.show()
        for button in (self.preview_button, self.excel_button, self.png_button):
            button.setEnabled(True)

    def on_generation_failed(self, message: str) -> None:
        self.bundle = None
        self._disable_result_actions()
        self.result_bar.hide()
        self._set_ready_status("生成失败", ready=False)
        QMessageBox.critical(self, "无法生成报表", message)

    def start_validation(self) -> None:
        if not self._sources_ready():
            return
        funds = self.funds_picker.path
        operations = self.operations_picker.path
        assert funds is not None and operations is not None
        self.validate_button.setEnabled(False)
        self.generate_button.setEnabled(False)
        self.uninstall_action.setEnabled(False)
        self._set_source_pickers_enabled(False)
        self._set_ready_status("正在校验数据源...", ready=False)
        self.validation_thread = QThread(self)
        self.validation_worker = ValidationWorker(
            self.report_service,
            funds,
            operations,
            datetime.now().astimezone().date(),
        )
        self.validation_worker.moveToThread(self.validation_thread)
        self.validation_thread.started.connect(self.validation_worker.run)
        self.validation_worker.succeeded.connect(self.on_validation_succeeded)
        self.validation_worker.failed.connect(self.on_validation_failed)
        self.validation_worker.finished.connect(self.validation_thread.quit)
        self.validation_worker.finished.connect(self.validation_worker.deleteLater)
        self.validation_thread.finished.connect(self.validation_thread.deleteLater)
        self.validation_thread.finished.connect(self.on_validation_finished)
        self.validation_thread.start()

    def on_validation_finished(self) -> None:
        self.validation_worker = None
        self.validation_thread = None
        self._restore_idle_controls()

    def start_generation(self) -> None:
        if not self._sources_ready() or self.inspection is None:
            return
        funds = self.funds_picker.path
        operations = self.operations_picker.path
        assert funds is not None and operations is not None
        self.bundle = None
        self._disable_result_actions()
        self.validate_button.setEnabled(False)
        self.generate_button.setEnabled(False)
        self.uninstall_action.setEnabled(False)
        self._set_source_pickers_enabled(False)
        self._set_ready_status("正在生成报表...", ready=False)
        self.generation_thread = QThread(self)
        self.generation_worker = GenerationWorker(
            self.report_service,
            funds,
            operations,
            datetime.now().astimezone().date(),
        )
        self.generation_worker.moveToThread(self.generation_thread)
        self.generation_thread.started.connect(self.generation_worker.run)
        self.generation_worker.succeeded.connect(self.on_generation_succeeded)
        self.generation_worker.failed.connect(self.on_generation_failed)
        self.generation_worker.finished.connect(self.generation_thread.quit)
        self.generation_worker.finished.connect(self.generation_worker.deleteLater)
        self.generation_thread.finished.connect(self.generation_thread.deleteLater)
        self.generation_thread.finished.connect(self.on_generation_finished)
        self.generation_thread.start()

    def on_generation_finished(self) -> None:
        self.generation_worker = None
        self.generation_thread = None
        self._restore_idle_controls()

    def start_update_check(self, manual: bool = False) -> None:
        if self.update_check_thread is not None or self.update_download_thread is not None:
            return
        self.update_check_manual = manual
        self.update_action.setEnabled(False)
        self.update_check_thread = QThread(self)
        self.update_check_worker = UpdateCheckWorker(self.update_checker, self.current_version)
        self.update_check_worker.moveToThread(self.update_check_thread)
        self.update_check_thread.started.connect(self.update_check_worker.run)
        self.update_check_worker.succeeded.connect(self.on_update_check_succeeded)
        self.update_check_worker.failed.connect(self.on_update_check_failed)
        self.update_check_worker.finished.connect(self.update_check_thread.quit)
        self.update_check_worker.finished.connect(self.update_check_worker.deleteLater)
        self.update_check_thread.finished.connect(self.update_check_thread.deleteLater)
        self.update_check_thread.finished.connect(self.on_update_check_finished)
        self.update_check_thread.start()

    def on_update_check_succeeded(self, update: ReleaseUpdate | None) -> None:
        if update is None:
            if self.update_check_manual:
                QMessageBox.information(self, "检查更新", "当前已是最新版。")
            return
        message = f"发现新版本 {update.version}，是否立即下载？"
        if update.notes.strip():
            message += f"\n\n{update.notes.strip()}"
        if (
            QMessageBox.question(
                self,
                "发现新版本",
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.start_update_download(update)

    def on_update_check_failed(self, message: str) -> None:
        if self.update_check_manual:
            QMessageBox.warning(self, "检查更新失败", message)

    def on_update_check_finished(self) -> None:
        self.update_check_worker = None
        self.update_check_thread = None
        self.update_action.setEnabled(self.update_download_thread is None)

    def start_update_download(self, update: ReleaseUpdate) -> None:
        if self.update_download_thread is not None:
            return
        self.update_action.setEnabled(False)
        self.update_progress = QProgressDialog("正在下载更新…", "取消", 0, 0, self)
        self.update_progress.setWindowTitle("下载更新")
        self.update_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.update_progress.setMinimumDuration(0)
        self.update_progress.setAutoClose(False)
        self.update_download_thread = QThread(self)
        self.update_download_worker = UpdateDownloadWorker(
            self.update_downloader, update, self.update_cache_dir
        )
        self.update_download_worker.moveToThread(self.update_download_thread)
        self.update_download_thread.started.connect(self.update_download_worker.run)
        self.update_download_worker.progress.connect(self.on_update_download_progress)
        self.update_download_worker.succeeded.connect(self.on_update_download_succeeded)
        self.update_download_worker.failed.connect(self.on_update_download_failed)
        self.update_download_worker.finished.connect(self.update_download_thread.quit)
        self.update_download_worker.finished.connect(self.update_download_worker.deleteLater)
        self.update_download_thread.finished.connect(self.update_download_thread.deleteLater)
        self.update_download_thread.finished.connect(self.on_update_download_finished)
        self.update_progress.canceled.connect(
            self.update_download_worker.cancel,
            Qt.ConnectionType.DirectConnection,
        )
        self.update_download_thread.start()

    def on_update_download_progress(self, received: int, total: int) -> None:
        if self.update_progress is None:
            return
        if total > 0:
            self.update_progress.setRange(0, total)
            self.update_progress.setValue(received)
        else:
            self.update_progress.setRange(0, 0)

    def on_update_download_succeeded(self, path: Path) -> None:
        if self.update_progress is not None:
            self.update_progress.close()
        self.open_update_installer(Path(path))

    def on_update_download_failed(self, message: str) -> None:
        if self.update_progress is not None:
            self.update_progress.close()
        if message != "更新下载已取消。":
            QMessageBox.warning(self, "更新下载失败", message)

    def on_update_download_finished(self) -> None:
        self.update_download_worker = None
        self.update_download_thread = None
        self.update_progress = None
        self.update_action.setEnabled(self.update_check_thread is None)

    def open_update_installer(self, path: Path) -> None:
        try:
            if sys.platform != "darwin":
                raise OSError("更新安装包只能在 macOS 上打开。")
            subprocess.run(["open", str(path)], check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            QMessageBox.warning(self, "无法打开更新", str(exc) or exc.__class__.__name__)

    def open_preview(self) -> None:
        if self.bundle is not None:
            PreviewDialog(self.bundle, self).exec()

    def open_source_settings(self) -> None:
        dialog = SourceSettingsDialog(self.report_service.source_settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        settings = dialog.selected_settings
        assert settings is not None
        if self.source_settings_path is not None:
            try:
                save_source_settings(self.source_settings_path, settings)
            except Exception as exc:  # noqa: BLE001 - UI boundary reports persistence failures.
                QMessageBox.critical(
                    self,
                    "字段设置保存失败",
                    str(exc) or exc.__class__.__name__,
                )
                return
        self.report_service.set_source_settings(settings)
        self.refresh_ready()
        if self._sources_ready():
            self.start_validation()

    def export_excel_file(self) -> None:
        if self.bundle is None:
            return
        default_name = f"{self.bundle.fiscal_year}财年台账报表.xlsx"
        value, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出 Excel",
            default_name,
            "Excel 工作簿 (*.xlsx)",
        )
        if not value:
            return
        path = Path(value)
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")
        try:
            export_excel(self.bundle, path)
        except Exception as exc:  # noqa: BLE001 - UI boundary reports exporter failures.
            self.status_label.setText("Excel 导出失败")
            QMessageBox.critical(self, "Excel 导出失败", str(exc) or exc.__class__.__name__)
        else:
            self.status_label.setText(f"已导出：{path.name}")

    def export_png_files(self) -> None:
        if self.bundle is None:
            return
        path = _choose_png_output_directory(self)
        if path is None:
            return
        try:
            export_pngs(self.bundle, path)
        except Exception as exc:  # noqa: BLE001 - UI boundary reports exporter failures.
            self.status_label.setText("图片导出失败")
            QMessageBox.critical(self, "图片导出失败", str(exc) or exc.__class__.__name__)
        else:
            self.status_label.setText(f"图片已导出至：{path.name}")

    def open_uninstall_dialog(self) -> None:
        if self.uninstall_targets is not None:
            UninstallDialog(self.uninstall_targets, self).exec()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._background_task_running() or self._update_task_running():
            self.status_label.setText("任务完成后即可关闭")
            event.ignore()
            return
        super().closeEvent(event)

    def _update_task_running(self) -> bool:
        return any(
            thread is not None and thread.isRunning()
            for thread in (self.update_check_thread, self.update_download_thread)
        )
