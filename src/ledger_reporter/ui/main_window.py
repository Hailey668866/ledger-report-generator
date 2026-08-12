from datetime import datetime
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtGui import QCloseEvent, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from ledger_reporter.domain.models import ReportBundle, SourceInspection
from ledger_reporter.exporters.excel import export_excel
from ledger_reporter.exporters.png import export_pngs
from ledger_reporter.ui.preview_dialog import PreviewDialog
from ledger_reporter.ui.source_picker import SourcePicker
from ledger_reporter.ui.workers import GenerationWorker, ValidationWorker

APP_STYLESHEET = """
QMainWindow, QWidget#mainBody {
    background: #f5f7fa;
    color: #202938;
    font-size: 13px;
}
QLabel#windowTitle {
    font-size: 23px;
    font-weight: 700;
    color: #202938;
}
QLabel#sectionTitle {
    font-size: 14px;
    font-weight: 700;
    color: #344054;
}
QFrame#sourcePanel, QFrame#statusPanel {
    background: #ffffff;
    border: 1px solid #d9e0e8;
    border-radius: 6px;
}
QLabel#sourceTitle {
    font-weight: 600;
    color: #344054;
}
QLabel#sourcePath {
    color: #667085;
}
QLabel#statusLabel {
    color: #344054;
    font-weight: 600;
}
QPushButton {
    min-height: 38px;
    padding: 0 16px;
    border-radius: 6px;
    border: 1px solid #cbd4df;
    background: #ffffff;
    color: #344054;
    font-weight: 600;
}
QPushButton:hover {
    background: #f1f4f8;
    border-color: #9eacbd;
}
QPushButton:pressed {
    background: #e8edf3;
}
QPushButton:disabled {
    color: #98a2b3;
    background: #eef1f5;
    border-color: #e1e6ed;
}
QPushButton#primaryButton {
    background: #315f9b;
    border-color: #315f9b;
    color: #ffffff;
}
QPushButton#primaryButton:hover {
    background: #274e82;
}
QPushButton#generateButton {
    background: #d96c75;
    border-color: #d96c75;
    color: #ffffff;
}
QPushButton#generateButton:hover {
    background: #c45a64;
}
QPushButton#secondaryButton {
    min-width: 82px;
}
QTableWidget#previewTable {
    background: #ffffff;
    border: 1px solid #d9e0e8;
    gridline-color: #b7c0bb;
}
"""


@lru_cache(maxsize=1)
def _ui_font_family() -> str | None:
    preferred = ("PingFang SC", "Microsoft YaHei", "Microsoft YaHei UI")
    available = set(QFontDatabase.families())
    for family in preferred:
        if family in available:
            return family

    font_paths = (
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("C:/Windows/Fonts/msyh.ttc"),
    )
    for path in font_paths:
        if not path.is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        for family in preferred:
            if family in families:
                return family
        if families:
            return families[0]
    return None


class MainWindow(QMainWindow):
    def __init__(self, report_service: object) -> None:
        super().__init__()
        self.report_service = report_service
        self.bundle: ReportBundle | None = None
        self.inspection: SourceInspection | None = None
        self.validation_thread: QThread | None = None
        self.validation_worker: ValidationWorker | None = None
        self.generation_thread: QThread | None = None
        self.generation_worker: GenerationWorker | None = None

        self.setWindowTitle("台账报表生成器")
        self.setMinimumSize(720, 480)
        if font_family := _ui_font_family():
            self.setFont(QFont(font_family, 10))
        self.setStyleSheet(APP_STYLESHEET)
        self.funds_picker = SourcePicker("资金台账")
        self.operations_picker = SourcePicker("运营台账")
        self.validate_button = QPushButton("校验数据源")
        self.validate_button.setObjectName("primaryButton")
        self.validate_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
        )
        self.generate_button = QPushButton("生成两张报表")
        self.generate_button.setObjectName("generateButton")
        self.generate_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.preview_button = QPushButton("预览报表")
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
        self.status_label.setWordWrap(True)

        for button in (
            self.validate_button,
            self.generate_button,
            self.preview_button,
            self.excel_button,
            self.png_button,
        ):
            button.setEnabled(False)

        body = QWidget()
        body.setObjectName("mainBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        title = QLabel("台账报表生成器")
        title.setObjectName("windowTitle")
        layout.addWidget(title)
        source_title = QLabel("数据源")
        source_title.setObjectName("sectionTitle")
        layout.addWidget(source_title)

        source_panel = QFrame()
        source_panel.setObjectName("sourcePanel")
        source_layout = QVBoxLayout(source_panel)
        source_layout.setContentsMargins(18, 16, 18, 16)
        source_layout.setSpacing(14)
        source_layout.addWidget(self.funds_picker)
        source_layout.addWidget(self.operations_picker)
        layout.addWidget(source_panel)

        status_panel = QFrame()
        status_panel.setObjectName("statusPanel")
        status_layout = QHBoxLayout(status_panel)
        status_layout.setContentsMargins(16, 12, 16, 12)
        status_layout.addWidget(self.status_label)
        layout.addWidget(status_panel)

        workflow = QHBoxLayout()
        workflow.setSpacing(10)
        workflow.addWidget(self.validate_button)
        workflow.addWidget(self.generate_button)
        workflow.addStretch(1)
        layout.addLayout(workflow)
        layout.addStretch(1)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self.preview_button)
        actions.addStretch(1)
        actions.addWidget(self.excel_button)
        actions.addWidget(self.png_button)
        layout.addLayout(actions)
        self.setCentralWidget(body)

        self.funds_picker.path_changed.connect(self.refresh_ready)
        self.operations_picker.path_changed.connect(self.refresh_ready)
        self.validate_button.clicked.connect(self.start_validation)
        self.generate_button.clicked.connect(self.start_generation)
        self.preview_button.clicked.connect(self.open_preview)
        self.excel_button.clicked.connect(self.export_excel_file)
        self.png_button.clicked.connect(self.export_png_files)

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
            return
        ready = self._sources_ready()
        self._set_source_pickers_enabled(True)
        self.validate_button.setEnabled(ready)
        self.generate_button.setEnabled(ready and self.inspection is not None)

    def refresh_ready(self, _path: object | None = None) -> None:
        ready = self._sources_ready()
        self.bundle = None
        self.inspection = None
        self.validate_button.setEnabled(ready)
        self.generate_button.setEnabled(False)
        self._disable_result_actions()
        self.status_label.setText("可以校验数据源" if ready else "请选择两份数据源")

    def on_validation_succeeded(self, inspection: SourceInspection) -> None:
        self.inspection = inspection
        plan = inspection.update_plan
        added = "、".join(item.label for item in plan.new_periods) or "无"
        refreshed = "、".join(item.label for item in plan.refresh_periods) or "无"
        self.status_label.setText(
            f"{inspection.fiscal_year}财年 | 最新 {plan.latest.label} | "
            f"新增 {added} | 回刷 {refreshed}"
        )
        self.generate_button.setEnabled(not self._background_task_running())

    def on_validation_failed(self, message: str) -> None:
        self.inspection = None
        self.generate_button.setEnabled(False)
        self.status_label.setText("数据源校验失败")
        QMessageBox.critical(self, "数据源校验失败", message)

    def on_generation_succeeded(self, bundle: ReportBundle) -> None:
        self.bundle = bundle
        self.status_label.setText(f"已生成：{bundle.latest_period.label}")
        for button in (self.preview_button, self.excel_button, self.png_button):
            button.setEnabled(True)

    def on_generation_failed(self, message: str) -> None:
        self.bundle = None
        self._disable_result_actions()
        self.status_label.setText("生成失败")
        QMessageBox.critical(self, "无法生成报表", message)

    def start_validation(self) -> None:
        if not self._sources_ready():
            return
        funds = self.funds_picker.path
        operations = self.operations_picker.path
        assert funds is not None and operations is not None
        self.validate_button.setEnabled(False)
        self.generate_button.setEnabled(False)
        self._set_source_pickers_enabled(False)
        self.status_label.setText("正在校验数据源...")
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
        self._set_source_pickers_enabled(False)
        self.status_label.setText("正在生成报表...")
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

    def open_preview(self) -> None:
        if self.bundle is not None:
            PreviewDialog(self.bundle, self).exec()

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
        value = QFileDialog.getExistingDirectory(self, "选择图片保存文件夹")
        if not value:
            return
        path = Path(value)
        try:
            export_pngs(self.bundle, path)
        except Exception as exc:  # noqa: BLE001 - UI boundary reports exporter failures.
            self.status_label.setText("图片导出失败")
            QMessageBox.critical(self, "图片导出失败", str(exc) or exc.__class__.__name__)
        else:
            self.status_label.setText(f"图片已导出至：{path.name}")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._background_task_running():
            self.status_label.setText("任务完成后即可关闭")
            event.ignore()
            return
        super().closeEvent(event)
