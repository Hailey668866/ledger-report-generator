from pathlib import Path

import pytest
from PySide6.QtCore import QThread
from PySide6.QtGui import QFontInfo

from ledger_reporter.domain.models import SourceInspection, UpdatePlan
from ledger_reporter.ui.main_window import MainWindow
from ledger_reporter.ui.workers import GenerationWorker, ValidationWorker


class FakeReportService:
    def __init__(self, bundle) -> None:
        self.bundle = bundle
        self.generation_error: Exception | None = None
        self.validation_error: Exception | None = None

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
    assert "新增" in window.status_label.text()

    replacement = tmp_path / "replacement.xlsx"
    replacement.touch()
    window.funds_picker.set_path(replacement)
    assert not window.generate_button.isEnabled()
    assert window.inspection is None


def test_window_uses_an_available_chinese_font(qtbot, fake_report_service) -> None:
    window = MainWindow(fake_report_service)
    qtbot.addWidget(window)

    assert QFontInfo(window.status_label.font()).family() in {
        "PingFang SC",
        "Microsoft YaHei",
        "Microsoft YaHei UI",
    }


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
        "ledger_reporter.ui.main_window.QFileDialog.getExistingDirectory",
        lambda *_args: "",
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
        "ledger_reporter.ui.main_window.QFileDialog.getExistingDirectory",
        lambda *_args: str(png_directory),
    )
    window.export_excel_file()
    window.export_png_files()
    assert excel_calls == [(report_bundle, excel_path.with_suffix(".xlsx"))]
    assert png_calls == [(report_bundle, png_directory)]


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
