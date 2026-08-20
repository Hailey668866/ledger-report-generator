from pathlib import Path
from dataclasses import replace

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QDialog, QFileDialog

from ledger_reporter.domain.models import SourceInspection, UpdatePlan
from ledger_reporter.io.source_settings import (
    DEFAULT_SOURCE_SETTINGS,
    SourceSettings,
    load_source_settings,
)
from ledger_reporter.ui import main_window as main_window_module
from ledger_reporter.ui.fonts import ui_font_family
from ledger_reporter.ui.main_window import MainWindow
from ledger_reporter.ui.workers import GenerationWorker, ValidationWorker


CUSTOM_SOURCE_SETTINGS = replace(DEFAULT_SOURCE_SETTINGS, funds_sheet="资金数据{年份}")


class FakeReportService:
    def __init__(self, bundle) -> None:
        self.bundle = bundle
        self.generation_error: Exception | None = None
        self.validation_error: Exception | None = None
        self.source_settings = DEFAULT_SOURCE_SETTINGS

    def set_source_settings(self, settings: SourceSettings) -> None:
        self.source_settings = settings

    def generate(self, funds: Path, operations: Path, today):
        if self.generation_error:
            raise self.generation_error
        return self.bundle

    def inspect_sources(self, funds: Path, operations: Path, today):
        if self.validation_error:
            raise self.validation_error
        period = self.bundle.latest_period
        return SourceInspection(
            self.bundle.fiscal_year,
            UpdatePlan(period, (period,), ()),
        )


@pytest.fixture
def fake_report_service(report_bundle):
    return FakeReportService(report_bundle)


def _select_sources(window: MainWindow, tmp_path: Path) -> tuple[Path, Path]:
    funds = tmp_path / "funds.xlsx"
    operations = tmp_path / "operations.xlsx"
    funds.touch()
    operations.touch()
    window.funds_picker.set_path(funds)
    window.operations_picker.set_path(operations)
    return funds, operations


def _use_source_settings_dialog(
    monkeypatch: pytest.MonkeyPatch,
    result: QDialog.DialogCode,
    created: list[tuple[SourceSettings, object]] | None = None,
) -> None:
    class FakeSourceSettingsDialog:
        selected_settings = CUSTOM_SOURCE_SETTINGS

        def __init__(self, current: SourceSettings, parent: object) -> None:
            if created is not None:
                created.append((current, parent))

        def exec(self) -> QDialog.DialogCode:
            return result

    monkeypatch.setattr(main_window_module, "SourceSettingsDialog", FakeSourceSettingsDialog)


def _show_generated_results(window: MainWindow, report_bundle) -> SourceInspection:
    period = report_bundle.latest_period
    inspection = SourceInspection(2026, UpdatePlan(period, (period,), ()))
    window.on_validation_succeeded(inspection)
    window.on_generation_succeeded(report_bundle)
    return inspection


def test_generate_requires_two_existing_sources_and_a_current_validation(
    qtbot,
    tmp_path: Path,
    fake_report_service,
) -> None:
    window = MainWindow(fake_report_service)
    qtbot.addWidget(window)

    assert not window.validate_button.isEnabled()
    assert not window.generate_button.isEnabled()
    assert not window.preview_button.isEnabled()
    _select_sources(window, tmp_path)
    assert window.validate_button.isEnabled()
    assert not window.generate_button.isEnabled()

    period = fake_report_service.bundle.latest_period
    window.on_validation_succeeded(SourceInspection(2026, UpdatePlan(period, (period,), ())))
    assert window.generate_button.isEnabled()
    assert "新增" in window.plan_detail_label.text()

    replacement = tmp_path / "replacement.xlsx"
    replacement.touch()
    window.funds_picker.set_path(replacement)
    assert not window.generate_button.isEnabled()
    assert window.inspection is None


def test_window_uses_an_available_chinese_font(qtbot, fake_report_service) -> None:
    window = MainWindow(fake_report_service)
    qtbot.addWidget(window)

    expected_family = ui_font_family()
    assert expected_family == "Noto Sans SC"
    assert window.font().family() == expected_family


def test_window_matches_approved_collapsed_preview_layout(qtbot, fake_report_service) -> None:
    window = MainWindow(fake_report_service)
    qtbot.addWidget(window)

    assert window.brand_title.text() == "台账报表生成器"
    assert not window.brand_icon.pixmap().isNull()
    assert window.funds_picker.button.text() == "选择文件"
    assert window.operations_picker.button.text() == "选择文件"
    assert window.period_panel.isHidden()
    assert window.result_bar.isHidden()
    assert window.generate_button.minimumHeight() == 42


def test_field_settings_button_is_on_source_title_row_and_opens_current_settings(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
    fake_report_service,
) -> None:
    created: list[tuple[SourceSettings, object]] = []
    _use_source_settings_dialog(monkeypatch, QDialog.DialogCode.Rejected, created)
    window = MainWindow(fake_report_service)
    qtbot.addWidget(window)

    source_row = window.funds_picker.parentWidget().layout().itemAt(0).layout()
    assert source_row.itemAt(0).widget().text() == "数据源"
    assert source_row.itemAt(source_row.count() - 1).widget() is window.source_settings_button
    assert window.source_settings_button.text() == "字段设置"

    window.source_settings_button.click()

    assert created == [(fake_report_service.source_settings, window)]


def test_accepted_field_settings_are_saved_applied_and_revalidated(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_report_service,
    report_bundle,
) -> None:
    settings_path = tmp_path / "source-settings.json"
    _use_source_settings_dialog(monkeypatch, QDialog.DialogCode.Accepted)
    window = MainWindow(fake_report_service, settings_path)
    qtbot.addWidget(window)
    _select_sources(window, tmp_path)
    _show_generated_results(window, report_bundle)
    validation_calls: list[bool] = []
    monkeypatch.setattr(window, "start_validation", lambda: validation_calls.append(True))

    window.open_source_settings()

    assert load_source_settings(settings_path) == CUSTOM_SOURCE_SETTINGS
    assert fake_report_service.source_settings == CUSTOM_SOURCE_SETTINGS
    assert window.bundle is None
    assert window.inspection is None
    assert window.period_panel.isHidden()
    assert window.plan_detail_label.isHidden()
    assert window.result_bar.isHidden()
    assert validation_calls == [True]


def test_cancelled_field_settings_leave_service_and_results_unchanged(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_report_service,
    report_bundle,
) -> None:
    _use_source_settings_dialog(monkeypatch, QDialog.DialogCode.Rejected)
    window = MainWindow(fake_report_service, tmp_path / "source-settings.json")
    qtbot.addWidget(window)
    _select_sources(window, tmp_path)
    inspection = _show_generated_results(window, report_bundle)
    old_status = window.status_label.text()
    validation_calls: list[bool] = []
    monkeypatch.setattr(window, "start_validation", lambda: validation_calls.append(True))

    window.open_source_settings()

    assert fake_report_service.source_settings == DEFAULT_SOURCE_SETTINGS
    assert window.bundle is report_bundle
    assert window.inspection is inspection
    assert not window.period_panel.isHidden()
    assert not window.result_bar.isHidden()
    assert window.status_label.text() == old_status
    assert validation_calls == []


def test_field_settings_save_failure_preserves_service_and_results(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_report_service,
    report_bundle,
) -> None:
    messages: list[tuple[str, str]] = []
    _use_source_settings_dialog(monkeypatch, QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        main_window_module,
        "save_source_settings",
        lambda *_args: (_ for _ in ()).throw(PermissionError("目录不可写")),
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "critical",
        lambda _parent, title, message: messages.append((title, message)),
    )
    window = MainWindow(fake_report_service, tmp_path / "source-settings.json")
    qtbot.addWidget(window)
    _select_sources(window, tmp_path)
    inspection = _show_generated_results(window, report_bundle)
    old_status = window.status_label.text()
    validation_calls: list[bool] = []
    monkeypatch.setattr(window, "start_validation", lambda: validation_calls.append(True))

    window.open_source_settings()

    assert fake_report_service.source_settings == DEFAULT_SOURCE_SETTINGS
    assert window.bundle is report_bundle
    assert window.inspection is inspection
    assert not window.period_panel.isHidden()
    assert not window.result_bar.isHidden()
    assert window.status_label.text() == old_status
    assert validation_calls == []
    assert messages == [("字段设置保存失败", "目录不可写")]


def test_accepted_field_settings_with_one_source_are_saved_without_validation(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_report_service,
) -> None:
    settings_path = tmp_path / "source-settings.json"
    _use_source_settings_dialog(monkeypatch, QDialog.DialogCode.Accepted)
    window = MainWindow(fake_report_service, settings_path)
    qtbot.addWidget(window)
    funds = tmp_path / "funds.xlsx"
    funds.touch()
    window.funds_picker.set_path(funds)
    validation_calls: list[bool] = []
    monkeypatch.setattr(window, "start_validation", lambda: validation_calls.append(True))

    window.open_source_settings()

    assert load_source_settings(settings_path) == CUSTOM_SOURCE_SETTINGS
    assert fake_report_service.source_settings == CUSTOM_SOURCE_SETTINGS
    assert validation_calls == []


def test_accepted_field_settings_without_a_path_are_still_applied(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
    fake_report_service,
) -> None:
    _use_source_settings_dialog(monkeypatch, QDialog.DialogCode.Accepted)
    window = MainWindow(fake_report_service)
    qtbot.addWidget(window)

    window.open_source_settings()

    assert fake_report_service.source_settings == CUSTOM_SOURCE_SETTINGS


def test_validation_populates_period_cards_and_generation_omits_week_status(
    qtbot,
    fake_report_service,
    report_bundle,
) -> None:
    window = MainWindow(fake_report_service)
    qtbot.addWidget(window)
    period = report_bundle.latest_period

    window.on_validation_succeeded(SourceInspection(2026, UpdatePlan(period, (period,), ())))

    assert not window.period_panel.isHidden()
    assert window.summary_period_value.text() == "2026财年，截至 08-06"
    assert window.weekly_period_value.text() == "2026年8月 W1"
    assert window.status_label.text() == "数据源已就绪"

    window.on_generation_succeeded(report_bundle)

    assert not window.result_bar.isHidden()
    assert window.result_title.text() == "报表已生成"
    assert window.result_meta.text() == "2 张表 · 数据校验通过"
    visible_copy = (
        f"{window.status_label.text()} {window.result_title.text()} {window.result_meta.text()}"
    )
    assert "已生成：" not in visible_copy
    assert period.label not in visible_copy


def test_success_enables_lazy_preview_and_exports(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
    fake_report_service,
    report_bundle,
) -> None:
    created: list[tuple[object, object]] = []
    executed: list[bool] = []

    class FakePreviewDialog:
        def __init__(self, bundle, parent) -> None:
            created.append((bundle, parent))

        def exec(self) -> None:
            executed.append(True)

    monkeypatch.setattr(
        "ledger_reporter.ui.main_window.PreviewDialog",
        FakePreviewDialog,
    )
    window = MainWindow(fake_report_service)
    qtbot.addWidget(window)

    window.on_generation_succeeded(report_bundle)

    assert window.preview_button.isEnabled()
    assert window.excel_button.isEnabled()
    assert window.png_button.isEnabled()
    assert created == []
    window.open_preview()
    assert created == [(report_bundle, window)]
    assert executed == [True]


def test_export_dialogs_cancel_cleanly_and_pass_selected_paths(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_report_service,
    report_bundle,
) -> None:
    excel_calls: list[tuple[object, Path]] = []
    png_calls: list[tuple[object, Path]] = []
    window = MainWindow(fake_report_service)
    qtbot.addWidget(window)
    window.on_generation_succeeded(report_bundle)
    monkeypatch.setattr(
        "ledger_reporter.ui.main_window.export_excel",
        lambda bundle, path: excel_calls.append((bundle, path)),
    )
    monkeypatch.setattr(
        "ledger_reporter.ui.main_window.export_pngs",
        lambda bundle, path: png_calls.append((bundle, path)),
    )

    monkeypatch.setattr(
        "ledger_reporter.ui.main_window.QFileDialog.getSaveFileName",
        lambda *_args: ("", ""),
    )
    monkeypatch.setattr(
        "ledger_reporter.ui.main_window._choose_png_output_directory",
        lambda *_args: None,
    )
    window.export_excel_file()
    window.export_png_files()
    assert excel_calls == []
    assert png_calls == []

    excel_path = tmp_path / "2026财年台账报表"
    png_directory = tmp_path / "images"
    monkeypatch.setattr(
        "ledger_reporter.ui.main_window.QFileDialog.getSaveFileName",
        lambda *_args: (str(excel_path), ""),
    )
    monkeypatch.setattr(
        "ledger_reporter.ui.main_window._choose_png_output_directory",
        lambda *_args: png_directory,
    )
    window.export_excel_file()
    window.export_png_files()
    assert excel_calls == [(report_bundle, excel_path.with_suffix(".xlsx"))]
    assert png_calls == [(report_bundle, png_directory)]


def test_png_export_chooser_is_an_explicit_folder_only_dialog(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_report_service,
) -> None:
    dialogs: list[QFileDialog] = []
    window = MainWindow(fake_report_service)
    qtbot.addWidget(window)
    monkeypatch.setattr(
        QFileDialog,
        "exec",
        lambda dialog: dialogs.append(dialog) or QDialog.DialogCode.Accepted,
    )
    monkeypatch.setattr(QFileDialog, "selectedFiles", lambda _dialog: [str(tmp_path)])

    selected = main_window_module._choose_png_output_directory(window)

    assert selected == tmp_path
    assert len(dialogs) == 1
    dialog = dialogs[0]
    assert dialog.fileMode() == QFileDialog.FileMode.Directory
    assert dialog.testOption(QFileDialog.Option.ShowDirsOnly)
    assert dialog.testOption(QFileDialog.Option.DontUseNativeDialog)
    assert dialog.labelText(QFileDialog.DialogLabel.Accept) == "选择此文件夹"


def test_generation_failure_resets_status_and_shows_message(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
    fake_report_service,
) -> None:
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "ledger_reporter.ui.main_window.QMessageBox.critical",
        lambda _parent, title, message: messages.append((title, message)),
    )
    window = MainWindow(fake_report_service)
    qtbot.addWidget(window)

    window.on_generation_failed("缺少字段")

    assert window.status_label.text() == "生成失败"
    assert messages == [("无法生成报表", "缺少字段")]


def test_workers_emit_success_failure_and_finished(fake_report_service) -> None:
    funds = Path("funds.xlsx")
    operations = Path("operations.xlsx")
    generated: list[object] = []
    inspected: list[object] = []
    failures: list[str] = []
    finished: list[str] = []
    generation_worker = GenerationWorker(
        fake_report_service,
        funds,
        operations,
        fake_report_service.bundle.latest_period.end,
    )
    validation_worker = ValidationWorker(
        fake_report_service,
        funds,
        operations,
        fake_report_service.bundle.latest_period.end,
    )
    generation_worker.succeeded.connect(generated.append)
    generation_worker.failed.connect(failures.append)
    generation_worker.finished.connect(lambda: finished.append("generation"))
    validation_worker.succeeded.connect(inspected.append)
    validation_worker.failed.connect(failures.append)
    validation_worker.finished.connect(lambda: finished.append("validation"))

    generation_worker.run()
    validation_worker.run()
    fake_report_service.generation_error = ValueError("生成错误")
    generation_worker.run()

    assert generated == [fake_report_service.bundle]
    assert len(inspected) == 1
    assert failures == ["生成错误"]
    assert finished == ["generation", "validation", "generation"]


def test_threaded_workflow_releases_finished_threads(
    qtbot,
    tmp_path: Path,
    fake_report_service,
) -> None:
    window = MainWindow(fake_report_service)
    qtbot.addWidget(window)
    _select_sources(window, tmp_path)

    window.start_validation()
    qtbot.waitUntil(lambda: window.inspection is not None)
    qtbot.waitUntil(lambda: window.validation_thread is None)

    window.start_generation()
    qtbot.waitUntil(lambda: window.bundle is not None)
    qtbot.waitUntil(lambda: window.generation_thread is None)

    assert window.funds_picker.isEnabled()
    assert window.operations_picker.isEnabled()
    assert window.preview_button.isEnabled()


def test_field_settings_button_is_disabled_during_background_tasks(
    qtbot,
    tmp_path: Path,
    fake_report_service,
) -> None:
    window = MainWindow(fake_report_service)
    qtbot.addWidget(window)
    _select_sources(window, tmp_path)

    window.start_validation()
    assert not window.source_settings_button.isEnabled()
    qtbot.waitUntil(lambda: window.validation_thread is None)
    assert window.source_settings_button.isEnabled()

    window.start_generation()
    assert not window.source_settings_button.isEnabled()
    qtbot.waitUntil(lambda: window.generation_thread is None)
    assert window.source_settings_button.isEnabled()


def test_controls_stay_disabled_until_all_background_threads_finish(
    qtbot,
    tmp_path: Path,
    fake_report_service,
) -> None:
    window = MainWindow(fake_report_service)
    qtbot.addWidget(window)
    _select_sources(window, tmp_path)
    window._set_source_pickers_enabled(False)
    window.validate_button.setEnabled(False)
    window.generate_button.setEnabled(False)

    validation_thread = QThread(window)
    validation_thread.start()
    window.validation_thread = validation_thread
    period = fake_report_service.bundle.latest_period
    window.on_validation_succeeded(SourceInspection(2026, UpdatePlan(period, (period,), ())))
    assert not window.generate_button.isEnabled()

    generation_thread = QThread(window)
    generation_thread.start()
    window.generation_thread = generation_thread
    validation_thread.quit()
    assert validation_thread.wait(1000)
    window.on_validation_finished()
    assert not window.funds_picker.isEnabled()
    assert not window.generate_button.isEnabled()

    generation_thread.quit()
    assert generation_thread.wait(1000)
    window.on_generation_finished()
    assert window.funds_picker.isEnabled()
    assert window.generate_button.isEnabled()
